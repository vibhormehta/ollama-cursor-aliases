# Cloudflare Tunnel for LiteLLM (and Ollama)

This exposes **LiteLLM** on the LLM host (`http://127.0.0.1:4000`) through **Cloudflare**, the same way **Ollama** is already exposed at **`https://ollama.tradechefpro.com`** → port **11434**.

## Domain layout (this setup)

| Hostname | Points to (localhost on LLM server) |
| -------- | ----------------------------------- |
| `ollama.tradechefpro.com` | `http://127.0.0.1:11434` (already in use) |
| `litellm.tradechefpro.com` | `http://127.0.0.1:4000` (LiteLLM — add this) |

Add **`litellm.tradechefpro.com`** as a **Public hostname** on the **same** Cloudflare Tunnel as Ollama (recommended): one `cloudflared` config, two `ingress` rules. Alternatively create a second tunnel only if you prefer isolation.

## On the LLM server

1. **Install `cloudflared`** ([releases](https://github.com/cloudflare/cloudflared/releases)) if needed.

2. **Tunnel** — if Ollama already uses a tunnel, reuse it; otherwise:

   ```bash
   cloudflared tunnel login
   cloudflared tunnel create tradechefpro-llm
   ```

3. **DNS** — create the LiteLLM hostname in the same zone:

   ```bash
   cloudflared tunnel route dns <tunnel-name-or-id> litellm.tradechefpro.com
   ```

   Or in **Zero Trust → Networks → Tunnels → [tunnel] → Public hostnames**, add:

   - Subdomain / domain: `litellm.tradechefpro.com`  
   - Service: `http://127.0.0.1:4000`

   Keep your existing **`ollama.tradechefpro.com`** → `http://127.0.0.1:11434` rule unchanged.

4. **Ingress config** — merge with your live tunnel config so **both** hostnames appear **before** the catch-all. See **`config.example.yml`** in this folder.

5. **Run / reload `cloudflared`** (restart the tunnel service after editing config).

6. Ensure LiteLLM is up: `docker compose up -d` in `litellm-proxy/`.

## Quick test (no permanent hostname)

```bash
cloudflared tunnel --url http://127.0.0.1:4000
```

Use the `trycloudflare.com` URL + `/v1` only for debugging.

## In Cursor

- **Override OpenAI Base URL:** `https://litellm.tradechefpro.com/v1`  
- **API key:** LiteLLM `master_key` (e.g. `sk-cursor-local` unless you changed it)  
- **Model:** `gpt-4o` / `gpt-4o-mini`

Direct Ollama from tools/scripts stays **`https://ollama.tradechefpro.com/v1`** when you call Ollama’s OpenAI-compatible API without LiteLLM.

## Operational notes

- **Streaming**: Generally fine through Cloudflare Tunnel for chat completions.  
- **Auth**: Use a **strong** `master_key` on public URLs; optional **Cloudflare Access** in front of `litellm.tradechefpro.com`.  
- **Secrets:** Do not commit `~/.cloudflared/*.json` or tunnel UUIDs.
