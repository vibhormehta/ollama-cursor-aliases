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

2. **API key**  
   - Use the same value as `master_key` in `config.yaml` (default `sk-cursor-local`).

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

## Troubleshooting

- **502 / connection errors**: From inside the LiteLLM container/host, `curl` Ollama’s root or `/api/tags` using the same `api_base` you configured.
- **Invalid model / upstream error with the real Ollama name**: Fix `litellm_params.model` to match `ollama list` on the target host, restart LiteLLM. Cursor can stay on `gpt-4o`; the bug is the LiteLLM → Ollama route, not the dropdown label.
- **Wrong routing**: Cursor must send a `model` string that exactly matches a `model_name` in `config.yaml` (e.g. `gpt-4o`).
- **Auth errors**: Bearer token must match `master_key`, or remove `master_key` only on trusted localhost (follow LiteLLM docs for disabling auth—discouraged on the public internet).
