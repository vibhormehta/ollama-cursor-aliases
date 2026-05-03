# Ollama aliases for Cursor

> **Personal learning only.** This repo is a **homelab / side-project** sandbox for wiring **Cursor** to **local Ollama** (aliases, LiteLLM, notes). It is **not** official work product from any employer, and it contains **no** proprietary business logic—see **`DISCLAIMER.md`**. For a longer narrative of what we tried and what broke, see **`docs/CURSOR_LITELLM_OLLAMA_EXPERIENCE.md`**. To publish your own copy on GitHub safely, see **`docs/PUBLISH_TO_GITHUB.md`**.

Cursor’s custom model field rejects colons (`:`) in the model name. Ollama’s real tags look like `qwen2.5-coder:32b` and `gemma4:31b`, so the IDE will not accept them even when the API is correct.

This repo holds **Modelfiles** that define colon-free names pointing at the same weights:

| Cursor-safe name   | Ollama source     |
| ------------------ | ----------------- |
| `qwen25-coder-32b` | `qwen2.5-coder:32b` |
| `gemma4-31b`       | `gemma4:31b`        |

## On the Ollama host

Pull the real models if needed, then create the aliases (from the repo root):

```bash
./scripts/create-aliases.sh
```

Or one at a time:

```bash
ollama create qwen25-coder-32b -f modelfiles/qwen25-coder-32b
ollama create gemma4-31b     -f modelfiles/gemma4-31b
```

**Note:** Some Ollama versions do not treat `ollama create ... -f -` with stdin as a real Modelfile; use a file path as above.

## In Cursor

Settings → Models → add a custom OpenAI-compatible model:

- **Base URL:** `https://<your-ollama-host>/v1`
- **Model:** `qwen25-coder-32b` or `gemma4-31b` (exactly as created)

## Smoke test

```bash
curl -sS -X POST "https://<your-ollama-host>/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen25-coder-32b","messages":[{"role":"user","content":"hi"}],"max_tokens":5}'
```

You should get JSON with `choices`. If you cannot run `ollama create` on the server, the alternative is a reverse proxy that rewrites the JSON `model` field to the real tagged name before forwarding to Ollama.

### SSH tunnel (Cursor on a different machine)

From the **Cursor host**, the repo includes **`scripts/tunnel-to-llm.sh`**: it forwards local ports **4000** (LiteLLM) and **11434** (Ollama) over SSH to the LLM server—same pattern as a manual `ssh -L 4000:127.0.0.1:4000 …`. See **`litellm-proxy/README.md`**.

### Cloudflare Tunnel

Ollama is already at **`https://ollama.tradechefpro.com`**. Add **`litellm.tradechefpro.com`** (or similar) on the **same tunnel** pointing to **`http://127.0.0.1:4000`** for LiteLLM. See **`cloudflare/README.md`** and **`cloudflare/config.example.yml`**.

### If Cursor still rejects model names (proxy + catalog id)

Use a small OpenAI-compatible proxy so Cursor only ever selects a **normal** model id (e.g. `gpt-4o`) while the proxy routes to Ollama. In **`litellm-proxy/config.yaml`**, set `litellm_params.model` to real tags from **`ollama list`** on the LLM host (e.g. `"ollama/qwen2.5-coder:32b"`), not made-up names. See **`litellm-proxy/README.md`** for Docker Compose and Cursor settings.

### Lessons learned (longer write-up)

**`docs/CURSOR_LITELLM_OLLAMA_EXPERIENCE.md`** — Cursor credits vs proxy, shim (streaming, SSE, unwrap), huge-context stalls, `-cursor` Modelfiles, fake tool JSON, Agent vs chat, and sunsetting checklist.

**`docs/PUBLISH_TO_GITHUB.md`** — how to put this on a **personal** GitHub repo with a clear description so it reads as learning, not company software.

## Publish to GitHub

Use a **personal** repo and a description that says **learning / homelab** (see **`docs/PUBLISH_TO_GITHUB.md`** and **`DISCLAIMER.md`**).

From `/home/vib/ollama-cursor-aliases` (or after copying this tree elsewhere):

```bash
gh auth login
cd /home/vib/ollama-cursor-aliases
gh repo create ollama-cursor-aliases --public --source=. --remote=origin \
  --description "Personal learning: Cursor + LiteLLM + Ollama (not employer work)" --push
```

If you prefer the website: create an empty repository (no README), then:

```bash
git remote add origin https://github.com/<you>/ollama-cursor-aliases.git
git push -u origin main
```
