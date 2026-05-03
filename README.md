# Ollama aliases for Cursor

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

## Publish to GitHub

From `/home/vib/ollama-cursor-aliases` (or after copying this tree elsewhere), authenticate and create the remote repo in one step:

```bash
gh auth login
cd /home/vib/ollama-cursor-aliases
gh repo create ollama-cursor-aliases --public --source=. --remote=origin --push
```

If you prefer the website: create an empty repository (no README), then:

```bash
git remote add origin https://github.com/<you>/ollama-cursor-aliases.git
git push -u origin main
```
