# LiteLLM proxy for Cursor (catalog model ids → Ollama)

Cursor may reject custom model **names** even when the API works. This proxy accepts OpenAI-style calls where Cursor sends a model id it already allows (for example `gpt-4o`), and LiteLLM forwards to Ollama using **`litellm_params.model`**.

**Important:** That backend string must be a **real Ollama model name**—exactly what appears in `ollama list` or `GET /api/tags` (e.g. `ollama/qwen2.5-coder:32b`, `ollama/gemma4:31b`). Hyphenated **aliases** you create for Cursor’s UI are optional and only help when talking **directly** to Ollama’s OpenAI API; LiteLLM still passes through to Ollama, so if an alias is wrong or missing on the LLM host, Ollama returns “invalid model” and Cursor only repeats that upstream error. Match the tag on the LLM host and restart the proxy after edits.

## What you run where

| Component | Typical location |
| --------- | ---------------- |
| **Ollama** | Machine with GPUs (same host as proxy, or remote URL). |
| **LiteLLM** | Same host as Ollama, or a small VM that can reach Ollama over HTTP(S). |
| **Cursor** | Your laptop: Override OpenAI Base URL → `https://your-proxy-host/v1`. |

Put TLS (Caddy, nginx, Traefik) in front of LiteLLM if Cursor must use `https://`.

### SSH tunnel from the Cursor host (same idea as tunneling Ollama)

If LiteLLM only listens on the LLM server’s loopback, forward ports over SSH so Cursor can use **localhost**:

```bash
# From the repo on your laptop:
chmod +x scripts/tunnel-to-llm.sh
./scripts/tunnel-to-llm.sh you@your-llm-server
```

That forwards **`127.0.0.1:4000` → server `127.0.0.1:4000`** (LiteLLM) and **`127.0.0.1:11434` → server `127.0.0.1:11434`** (Ollama). Leave the terminal open.

Then in Cursor:

- **Override OpenAI Base URL:** `http://127.0.0.1:4000/v1`
- **API key:** same as LiteLLM `master_key` (e.g. `sk-cursor-local`)
- **Model:** `gpt-4o` / `gpt-4o-mini`

To tunnel **only** LiteLLM (free port 11434 for something else): `OLLAMA_LOCAL= ./scripts/tunnel-to-llm.sh you@server`

### Cloudflare Tunnel (`cloudflared`)

Ollama is already at **`https://ollama.tradechefpro.com`**. Add a second hostname (e.g. **`litellm.tradechefpro.com`**) on the same tunnel to **`http://127.0.0.1:4000`**. Cursor then uses **`https://litellm.tradechefpro.com/v1`** and your LiteLLM `master_key`. See **`../cloudflare/README.md`**.

## Configure `config.yaml`

Edit `model_list` entries:

- **`model_name`**: Must match what you select in Cursor (e.g. `gpt-4o`, `gpt-4o-mini`).
- **`litellm_params.model`**: LiteLLM → Ollama route: `ollama/<exact-tag>` where `<exact-tag>` matches **`ollama list`** on the LLM server (colons allowed; **quote the whole value in YAML**, e.g. `"ollama/qwen2.5-coder:32b"`).
- **`litellm_params.api_base`**: Ollama base URL (no `/v1`).
  - Ollama on the Docker host: `http://host.docker.internal:11434` (used in the default `config.yaml` with `extra_hosts` in Compose).
  - Remote Ollama: `https://your-ollama-host` (see `config.remote-ollama.example.yaml`).

**Master key:** `general_settings.master_key` must match what you type in Cursor as the OpenAI API key (default in this folder: `sk-cursor-local`). Change it if you expose the proxy publicly.

## Run with Docker Compose

On the **Ollama host**, confirm tags before editing LiteLLM:

```bash
curl -sS http://127.0.0.1:11434/api/tags | python3 -c "import sys,json; print([m['name'] for m in json.load(sys.stdin).get('models',[])])"
```

Use those strings (after the `ollama/` prefix in `config.yaml`) exactly. Then:

```bash
cd litellm-proxy
docker compose up -d
```

If your user cannot talk to the Docker socket (`permission denied`), either run `sudo usermod -aG docker "$USER"` and re-login, or use **`../scripts/docker-litellm.sh`** from the repo root (reads **`SUDO_PASSWORD`** from `/home/vib/.env` — keep `.env` out of git).

Smoke test (proxy on localhost:4000):

```bash
curl -sS http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-cursor-local" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"max_tokens":20}'
```

You should see JSON with `choices`; the backend should be your Ollama model.

## Cursor settings

1. **Settings → Models**  
   - Enable **Override OpenAI Base URL** (wording may vary by version).  
   - Set base URL to your proxy’s OpenAI-compatible root, e.g. `https://proxy.example.com/v1` or `http://127.0.0.1:4000/v1` for local testing.

2. **API key (`sk-…` field + toggle)**  
   - Value should match LiteLLM **`master_key`** in `config.yaml` (default `sk-cursor-local`).  
   - **If chat works with the OpenAI API Key toggle OFF, leave it OFF.** Turning it **on** can switch Cursor to a different client path that POSTs **`/v1/chat/completions`** with a body **without `messages`** (e.g. Responses-style `input`). LiteLLM then errors: `Router.acompletion() missing 1 required positional argument: 'messages'` (HTTP 500). That is a **Cursor ↔ LiteLLM wire-format mismatch**, not a bad `master_key`.  
   - LiteLLM’s separate **`/cursor`** integration (base URL ending in **`/cursor`**, virtual keys / dashboard) is for Cursor’s documented flow; this repo’s simple **`/v1` + `master_key`** setup targets **plain Chat Completions** JSON.

3. **Model**  
   - In the chat/composer model picker, choose **`gpt-4o`** or **`gpt-4o-mini`** (or whatever `model_name` you defined)—**not** the Ollama tag. LiteLLM maps that id to Ollama.

4. **Plan / BYOK**  
   Custom base URL and API key behavior can depend on your Cursor plan; if the UI blocks overrides, check subscription docs or support.

## Run without Docker

```bash
pip install 'litellm[proxy]'
litellm --config config.yaml --port 4000
```

Use the same `api_base` rules; on Linux without Docker, `api_base: http://127.0.0.1:11434` is typical for local Ollama.

## See every request in `docker logs` (did Cursor hit LiteLLM?)

Compose enables **`--detailed_debug`** and **`LITELLM_LOG=DEBUG`**. After `docker compose up -d`, run:

```bash
sudo docker logs -f --timestamps litellm-proxy-litellm-1
```

You should see each **`GET/POST`** to **`/v1/...`** (and more detail around routing). **Disable** `--detailed_debug` / set `LITELLM_LOG` back when finished — debug output can include **message text** (privacy).

Per-request only (no global spam): some builds honor **`"litellm_request_debug": true`** in the JSON body of a single `curl` test.

## Troubleshooting

- **`Router.acompletion() missing … 'messages'` (500) from Cursor after enabling OpenAI API Key:** Cursor is sending a **non–chat-completions** payload to **`/v1/chat/completions`** (missing `messages`). **Workaround:** keep the **OpenAI API Key toggle OFF** while keeping **`https://…/v1`** override; many builds still send the bearer token from the key field for custom bases. If you must have the toggle on, upgrade LiteLLM often, watch [Cursor forum threads on Responses vs chat completions](https://forum.cursor.com/search?q=litellm%20chat%20completions), or put a small **reverse proxy** in front of LiteLLM that normalizes `input` → `messages` before forwarding.
- **502 / connection errors**: From inside the LiteLLM container/host, `curl` Ollama’s root or `/api/tags` using the same `api_base` you configured.
- **Invalid model / upstream error with the real Ollama name**: Fix `litellm_params.model` to match `ollama list` on the target host, restart LiteLLM. Cursor can stay on `gpt-4o`; the bug is the LiteLLM → Ollama route, not the dropdown label.
- **Wrong routing**: Cursor must send a `model` string that exactly matches a `model_name` in `config.yaml` (e.g. `gpt-4o`).
- **Auth errors**: Bearer token must match `master_key`, or remove `master_key` only on trusted localhost (follow LiteLLM docs for disabling auth—discouraged on the public internet).
