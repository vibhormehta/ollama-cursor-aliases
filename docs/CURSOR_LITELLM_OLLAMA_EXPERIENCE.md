# Cursor + LiteLLM + Ollama — field notes and lessons learned

This document captures real-world behavior we hit while wiring **Cursor** to **local Ollama** through **LiteLLM** (and a small **cursor-shim**). Use it when reviving or debugging the stack; operational steps still live in **`litellm-proxy/README.md`** and **`README.md`**.

**Publication context:** this material is meant for a **public, personal learning repo**—not an employer deliverable. See the repo root **`DISCLAIMER.md`** and **`docs/PUBLISH_TO_GITHUB.md`** so anyone (including your company) can see the intent: **homelab notes**, no proprietary systems, **educational only**.

---

## 1. What we were trying to do

- **Problem:** Cursor’s UI often only allows **catalog model ids** (e.g. `gpt-4o`, `gpt-4o-mini`) and may reject raw Ollama tags with **`:`** in the name.
- **Approach:** **LiteLLM** maps those ids to real Ollama models (`ollama/qwen2.5-coder:32b`, etc.) behind **`master_key`** auth.
- **Exposure:** **`cursor-shim`** on host port **4000** → **LiteLLM** (internal) → **Ollama** on the host (`host.docker.internal:11434` in Compose). Optional **Cloudflare Tunnel** to `https://litellm…/v1`.

---

## 2. Cursor: base URL, API key toggle, and credits

| Symptom | Likely cause |
| -------- | ------------- |
| Traffic uses **Cursor credits**, OpenAI usage dashboard doesn’t show your key | **OpenAI API key toggle OFF** — many builds still **don’t** send traffic to your custom base for that path. |
| **500** from LiteLLM (`Router.acompletion() missing … 'messages'`) after turning toggle **ON** | Cursor sometimes sends **Responses-style** bodies (`input`, `instructions`) to **`/v1/chat/completions`**. LiteLLM expects **`messages`**. |

**Mitigation (implemented):** **`cursor-shim`** rewrites `input` / `instructions` into **`messages`** before LiteLLM. You generally need the **toggle ON** so requests actually hit your proxy, **and** the shim on port 4000.

“**User API key rate limit exceeded**” often came from **Cursor / OpenAI** side or another path—not LiteLLM—when LiteLLM logs showed no matching 429.

---

## 3. `cursor-shim` — what it fixes (and why it grew)

### 3.1 Request path

- **`POST /v1/chat/completions`:** normalize **Responses-like** JSON → **`messages`**.

### 3.2 Streaming bug (single `{` in UI, GPU busy)

- **Bug:** `async with httpx.AsyncClient()` exited **before** `StreamingResponse` finished reading the upstream body → connection closed → client saw **one character** (often `{`).
- **Fix:** keep the **httpx client open** until the stream generator’s **`finally`**.

### 3.3 Cursor uses `stream: true`; unwrap only ran on `stream: false`

- **Symptom:** Model returned **`{"thought": ...}`** or **`{"function_call": ...}`** in **`message.content`**; Cursor showed raw JSON; “unwrap” logic never ran.
- **Fix:** for **all** chat completions, shim calls LiteLLM with **`stream: false`**, runs **`unwrap_chat_completion_response`**, then:
  - if the **client** asked **`stream: true`**, **re-synthesize OpenAI-style SSE** (`data: …` + `[DONE]`);
  - if **`stream: false`** (e.g. `curl`, **`verify.sh`**), return one **JSON** body.

### 3.4 Unwrap rules (high level)

- If `content` parses as JSON with a real **`content`** string (long enough), **replace** `message.content` with that string.
- If only **`thought`**: replace with a **short** note — **do not echo** the thought text back (Cursor would **re-feed** it → “self talking” loop).
- If **`function_call`** (fake tool JSON): replace with a short note (not executed).

---

## 4. LiteLLM + Ollama: performance and “stuck”

### 4.1 Huge prompts and `num_ctx`

- **Symptom:** **minutes** of GPU, **0 bytes** to `curl`, Cursor **“Taking longer than expected…”**, Ollama log **`truncating input prompt`** to **32k** tokens.
- **Cause:** Composer/Agent sends **very large** contexts; **31B+** models spend forever on **prefill**; clients **time out** and disconnect → queue and **“Stopping…”** wedged states.
- **Mitigation:** in **`config.yaml`**, **`extra_body.options.num_ctx: 8192`** (tunable). Tradeoff: long context is **truncated**, first token is much faster.

### 4.2 Generation cap

- **`num_predict: 8192`** (Ollama) passed via the same **`extra_body.options`** so long answers are less likely to stop after a tiny JSON blob.

### 4.3 When everything “hangs”

- **`ollama ps`** stuck on **Stopping…**, **`curl` to Ollama** never returns → **`sudo systemctl restart ollama`** (or kill stuck runner) then retry.

### 4.4 Docker Compose

- **`docker compose`** must run from **`litellm-proxy/`** (where **`docker-compose.yml`** lives), not `~`.

---

## 5. Local models vs “normal” chat (Ollama UI)

- **Ollama Web / short chat:** clean prompts → model answers in **prose**.
- **Cursor:** long system + product framing → local models often **imitated** **ReAct / tool / `thought` / `function_call` JSON** inside **`message.content`** — not real tool execution.

**Mitigation:** **`-cursor` Modelfiles** (`qwen2.5-cursor:32b`, `gemma4-cursor:31b`) — same weights, **system** text forbidding JSON envelopes and **thought-only** replies. After editing Modelfiles: **`ollama create … -f …`** again.

**Reality:** smaller / misaligned models still slip; the **shim** is a safety net, not a substitute for a **strong instruct model**.

---

## 6. Code changes and Agent mode

- **Ollama / LiteLLM only return text.** They do not edit the workspace.
- **Cursor** applies edits when **Composer/Agent** gets valid **`tool_calls`** (or you apply chat output manually).
- Local models printing **`{"function_call": …}`** as **text** are **not** Cursor running **Read**/**Write** — that’s **hallucinated format**.

For **reliable** automated edits, use **Cursor’s built-in models** or a **hosted API** Cursor fully supports for tools—not a best-effort local mimic.

---

## 7. Repo layout (quick map)

| Piece | Role |
| ----- | ---- |
| **`litellm-proxy/config.yaml`** | `model_name` (Cursor id) → `ollama/…` + `num_ctx` / `num_predict` |
| **`litellm-proxy/docker-compose.yml`** | LiteLLM + **cursor-shim** on **4000** |
| **`litellm-proxy/cursor-shim/app.py`** | Request normalize + buffered chat + unwrap + SSE |
| **`modelfiles/*-cursor-*`** | Ollama derivatives with anti-JSON system prompts |
| **`scripts/create-aliases.sh`** | Creates colon-free aliases **and** `-cursor` models |
| **`scripts/verify.sh`** | YAML, Ollama tags, compose, proxy smoke tests |
| **`cloudflare/README.md`** | Tunnel hostname for LiteLLM |

---

## 8. Sunsetting / cleanup checklist

When pausing the experiment:

1. **Cursor:** disable **Override OpenAI Base URL** (or point elsewhere); turn off **OpenAI API key** toggle if you no longer use BYOK to the proxy.
2. **Server:** `cd litellm-proxy && docker compose down` (optional; you said you may stop LiteLLM later).
3. **Cloudflare:** remove or repoint **`litellm.…`** ingress if you decommission the service.
4. **Git:** this repo’s **`docs/`** + README link preserve the design for a future attempt.

---

## 9. Takeaway

**Cursor + local Ollama through a custom OpenAI base is workable for chat-shaped completions** if you accept **truncated context**, **latency**, and **guardrails** (Modelfiles + shim). **Agent-quality tool use and long-context “same as GPT” behavior** are where hosted Cursor/OpenAI paths still win unless you invest in **models and formats** that faithfully implement **tool calling**, not JSON cosplay in `content`.

---

*Last updated from internal debugging sessions (Cursor, LiteLLM `main-latest`, Ollama 0.22, Linux + NVIDIA).*
