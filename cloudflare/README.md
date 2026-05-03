# Cloudflare Tunnel for LiteLLM (and Ollama)

This exposes **LiteLLM** on the LLM host (usually `http://127.0.0.1:4000`) through **Cloudflare**, same pattern as tunneling Ollama on **11434**: no inbound firewall port-forward; HTTPS at the edge.

## On the LLM server

1. **Install `cloudflared`** (package or [GitHub releases](https://github.com/cloudflare/cloudflared/releases)).

2. **Log in and create a tunnel** (one-time browser step):

   ```bash
   cloudflared tunnel login
   cloudflared tunnel create litellm-proxy
   ```

   Note the printed **tunnel UUID** and the path to the **credentials JSON**.

3. **DNS**: attach a hostname to the tunnel (pick your zone):

   ```bash
   cloudflared tunnel route dns litellm-proxy litellm.example.com
   ```

   Or add a **Public hostname** in Zero Trust → Networks → Tunnels → your tunnel → **Configure**.

4. **Config file**: copy `config.example.yml` to e.g. `~/.cloudflared/litellm.yml` and set:

   - `tunnel:` → your tunnel UUID  
   - `credentials-file:` → path to the `.json` credentials  
   - `hostname:` → the same FQDN you routed (`litellm.example.com`)  
   - `service:` → `http://127.0.0.1:4000` (LiteLLM container listening on the host)

   To expose **Ollama** the same way you already do, add another ingress rule:

   ```yaml
   - hostname: ollama.example.com
     service: http://127.0.0.1:11434
   ```

   Order matters: specific hostnames first, catch-all last.

5. **Run the tunnel** (systemd unit recommended):

   ```bash
   cloudflared tunnel --config ~/.cloudflared/litellm.yml run
   ```

   Ensure **Docker LiteLLM is up** (`docker compose up -d` in `litellm-proxy/`) before depending on the tunnel.

## Quick test (no named hostname)

For a throwaway URL while debugging:

```bash
cloudflared tunnel --url http://127.0.0.1:4000
```

Use the printed `trycloudflare.com` URL; append `/v1` for OpenAI-style clients. Not for production.

## In Cursor (your laptop)

- **Override OpenAI Base URL:** `https://litellm.example.com/v1`  
- **API key:** LiteLLM `master_key` (e.g. `sk-cursor-local` unless you changed it)  
- **Model:** `gpt-4o` / `gpt-4o-mini` (catalog ids mapped in LiteLLM config)

Cloudflare terminates TLS; Cursor talks HTTPS to Cloudflare, `cloudflared` forwards HTTP to localhost **4000**.

## Operational notes

- **Streaming**: Cloudflare Tunnel supports streaming responses; LiteLLM/Ollama streaming used by Cursor generally works.  
- **Auth**: Put a **strong** `master_key` in LiteLLM config if the hostname is public; optionally add **Cloudflare Access** in front of the hostname for extra login.  
- **Secrets:** Do not commit `~/.cloudflared/*.json` or tunnel UUIDs into git.
