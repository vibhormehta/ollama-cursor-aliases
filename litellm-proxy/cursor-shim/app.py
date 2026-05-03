"""
Reverse proxy in front of LiteLLM.

Cursor often routes custom OpenAI traffic only when the OpenAI API key toggle is ON.
That path can POST OpenAI Responses-style JSON (e.g. `input`, `instructions`) to
`/v1/chat/completions`, while LiteLLM expects `messages`. We normalize here.

For chat completions, Cursor usually uses stream=true. Local models sometimes return
assistant content as JSON (e.g. {"thought":...}). We always call LiteLLM with
stream=false for /v1/chat/completions, unwrap the final JSON, then synthesize SSE
so the client still gets a normal streamed response.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

UPSTREAM = os.environ.get("UPSTREAM", "http://litellm:4000").rstrip("/")
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    parts.append(str(block["text"]))
                elif "text" in block:
                    parts.append(str(block["text"]))
        return "".join(parts)
    return str(content)


def _block_to_message(block: dict[str, Any]) -> dict[str, Any] | None:
    role = block.get("role")
    if role in ("user", "assistant", "system", "developer", "tool"):
        return {
            "role": role,
            "content": _content_to_str(block.get("content")),
        }
    btype = block.get("type")
    if btype in ("message", "input_message"):
        r = block.get("role", "user")
        if r not in ("user", "assistant", "system", "developer", "tool"):
            r = "user"
        return {"role": r, "content": _content_to_str(block.get("content"))}
    return None


def responses_like_input_to_messages(data: dict[str, Any]) -> list[dict[str, Any]]:
    inp = data.get("input")
    messages: list[dict[str, Any]] = []

    if isinstance(inp, str) and inp.strip():
        messages.append({"role": "user", "content": inp})

    elif isinstance(inp, list):
        for block in inp:
            if isinstance(block, str) and block.strip():
                messages.append({"role": "user", "content": block})
            elif isinstance(block, dict):
                m = _block_to_message(block)
                if m is not None and (m.get("content") or m["role"] == "assistant"):
                    messages.append(m)

    instr = data.get("instructions")
    if isinstance(instr, str) and instr.strip():
        messages.insert(0, {"role": "system", "content": instr})

    return messages


def normalize_chat_completion_json(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("messages"):
        return raw
    new_messages = responses_like_input_to_messages(raw)
    if not new_messages:
        return raw
    out = dict(raw)
    out["messages"] = new_messages
    out.pop("input", None)
    out.pop("instructions", None)
    return out


def unwrap_chat_completion_response(resp: dict[str, Any]) -> dict[str, Any]:
    """If the assistant put JSON (thought/action/content) in message.content, unwrap for the client."""
    choices = resp.get("choices")
    if not isinstance(choices, list):
        return resp
    out = dict(resp)
    new_choices: list[Any] = []
    for ch in choices:
        if not isinstance(ch, dict):
            new_choices.append(ch)
            continue
        ch2 = dict(ch)
        msg = ch2.get("message")
        if not isinstance(msg, dict):
            new_choices.append(ch2)
            continue
        msg2 = dict(msg)
        content = msg2.get("content")
        if isinstance(content, str):
            stripped = content.strip()
            if stripped.startswith("{"):
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    obj = None
                if isinstance(obj, dict):
                    inner = obj.get("content")
                    if isinstance(inner, str) and len(inner.strip()) >= 40:
                        msg2["content"] = inner
                    elif isinstance(obj.get("thought"), str) and obj["thought"].strip():
                        th = str(obj["thought"]).strip()
                        msg2["content"] = (
                            "*The model returned only planning metadata, not the full answer.* "
                            "Send the same request again, or try another model / a new chat.\n\n---\n\n"
                            + th
                        )
        ch2["message"] = msg2
        new_choices.append(ch2)
    out["choices"] = new_choices
    return out


def build_upstream_headers(request: Request, new_content_length: int | None) -> list[tuple[bytes, bytes]]:
    headers: list[tuple[bytes, bytes]] = []
    for k, v in request.headers.raw:
        lk = k.decode("latin-1").lower()
        if lk in HOP_BY_HOP or lk == "host":
            continue
        if lk == "content-length" and new_content_length is not None:
            continue
        headers.append((k, v))
    if new_content_length is not None:
        headers.append((b"content-length", str(new_content_length).encode()))
    return headers


def _sse_chunk(
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None,
) -> bytes:
    obj: dict[str, Any] = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return b"data: " + json.dumps(obj, ensure_ascii=False).encode() + b"\n\n"


def chat_completion_to_sse_parts(completion: dict[str, Any]) -> list[bytes]:
    """Turn a full chat.completion JSON into OpenAI-style SSE data lines."""
    cid = str(completion.get("id") or "chatcmpl-cursor-shim")
    created = int(completion.get("created") or 0)
    model = str(completion.get("model") or "")
    text = ""
    choices = completion.get("choices") or []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            text = msg["content"]
    parts: list[bytes] = []
    parts.append(_sse_chunk(cid, created, model, {"role": "assistant"}, None))
    step = 512
    for i in range(0, len(text), step):
        parts.append(_sse_chunk(cid, created, model, {"content": text[i : i + step]}, None))
    parts.append(_sse_chunk(cid, created, model, {}, "stop"))
    parts.append(b"data: [DONE]\n\n")
    return parts


async def proxy_request(request: Request) -> Response:
    path = request.url.path
    if not path.startswith("/"):
        path = "/" + path
    url = f"{UPSTREAM}{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    body = await request.body()
    ct = request.headers.get("content-type", "").split(";")[0].strip().lower()

    is_chat = (
        request.method == "POST"
        and path.rstrip("/") == "/v1/chat/completions"
        and body
        and ct == "application/json"
    )

    body_upstream = body
    upstream_len: int | None = None
    client_wants_sse = False

    if is_chat:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                client_wants_sse = bool(parsed.get("stream", False))
                normalized = normalize_chat_completion_json(parsed)
                if normalized.get("messages") and not parsed.get("messages"):
                    body_upstream = json.dumps(normalized, separators=(",", ":")).encode()
                p2 = json.loads(body_upstream)
                if isinstance(p2, dict):
                    p2 = dict(p2)
                    p2["stream"] = False
                    body_upstream = json.dumps(p2, separators=(",", ":")).encode()
                upstream_len = len(body_upstream)
        except (json.JSONDecodeError, TypeError):
            upstream_len = len(body_upstream) if body_upstream else None

    headers = build_upstream_headers(request, upstream_len)
    client_timeout = httpx.Timeout(600.0, connect=30.0)

    # Chat completions: always buffered upstream (stream=false) so we can unwrap JSON-in-content; then
    # re-emit as SSE if the client asked for stream=true (Cursor), else JSON (curl / OpenAI default).
    if is_chat:
        client = httpx.AsyncClient(timeout=client_timeout)
        upstream = None
        try:
            req = client.build_request(
                request.method,
                url,
                headers=headers,
                content=body_upstream if body_upstream else None,
            )
            upstream = await client.send(req, stream=False)
            raw = upstream.content
            status_code = upstream.status_code
            if status_code != 200 or not raw.strip().startswith(b"{"):
                return Response(
                    content=raw,
                    status_code=status_code,
                    media_type=upstream.headers.get("content-type", "application/json"),
                )
            try:
                payload_obj = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return Response(content=raw, status_code=status_code, media_type="application/json")
            if not isinstance(payload_obj, dict):
                return Response(content=raw, status_code=status_code, media_type="application/json")
            payload = unwrap_chat_completion_response(payload_obj)
        finally:
            if upstream is not None:
                try:
                    await upstream.aclose()
                except Exception:
                    pass
            await client.aclose()

        if client_wants_sse:
            sse_parts = chat_completion_to_sse_parts(payload)
            hdrs = {
                "content-type": "text/event-stream; charset=utf-8",
                "cache-control": "no-cache",
                "connection": "keep-alive",
            }

            async def sse_stream():
                for part in sse_parts:
                    yield part

            return StreamingResponse(sse_stream(), status_code=200, headers=hdrs)

        out_bytes = json.dumps(payload, ensure_ascii=False).encode()
        return Response(
            content=out_bytes,
            status_code=status_code,
            media_type="application/json",
            headers={"content-length": str(len(out_bytes))},
        )

    # Non-chat: streaming pass-through
    client = httpx.AsyncClient(timeout=client_timeout)
    try:
        req = client.build_request(
            request.method,
            url,
            headers=build_upstream_headers(request, len(body) if body else None),
            content=body if body else None,
        )
        upstream = await client.send(req, stream=True)
    except Exception:
        await client.aclose()
        raise

    out_headers = [
        (k, v)
        for k, v in upstream.headers.multi_items()
        if k.lower() not in HOP_BY_HOP
    ]
    status_code = upstream.status_code

    async def stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=status_code,
        headers=dict(out_headers),
    )


async def catch_all(request: Request) -> Response:
    return await proxy_request(request)


app = Starlette(
    routes=[
        Route("/{full_path:path}", endpoint=catch_all, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]),
    ]
)
