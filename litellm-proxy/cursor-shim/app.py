"""
Reverse proxy in front of LiteLLM.

Cursor often routes custom OpenAI traffic only when the OpenAI API key toggle is ON.
That path can POST OpenAI Responses-style JSON (e.g. `input`, `instructions`) to
`/v1/chat/completions`, while LiteLLM expects `messages`. We normalize here.
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


async def proxy_request(request: Request) -> Response:
    path = request.url.path
    if not path.startswith("/"):
        path = "/" + path
    url = f"{UPSTREAM}{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    body = await request.body()
    new_len: int | None = None

    if (
        request.method == "POST"
        and path.rstrip("/") == "/v1/chat/completions"
        and body
        and request.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json"
    ):
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                normalized = normalize_chat_completion_json(parsed)
                if normalized.get("messages") and not parsed.get("messages"):
                    body = json.dumps(normalized, separators=(",", ":")).encode()
                    new_len = len(body)
        except (json.JSONDecodeError, TypeError):
            pass

    headers = build_upstream_headers(request, new_len)

    client_timeout = httpx.Timeout(600.0, connect=30.0)
    # httpx closes the connection when AsyncClient exits. We must keep the client
    # alive until StreamingResponse finishes yielding chunks (SSE / chunked bodies).
    client = httpx.AsyncClient(timeout=client_timeout)
    try:
        req = client.build_request(
            request.method,
            url,
            headers=headers,
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
