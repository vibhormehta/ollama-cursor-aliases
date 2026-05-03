#!/usr/bin/env bash
# Create colon-free Ollama model names for use in Cursor (custom model id rejects ':').
# Requires the source models to already be pulled, e.g. ollama pull qwen2.5-coder:32b
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ollama create qwen25-coder-32b -f "$ROOT/modelfiles/qwen25-coder-32b"
ollama create gemma4-31b -f "$ROOT/modelfiles/gemma4-31b"
echo "Done. In Cursor, use model ids: qwen25-coder-32b, gemma4-31b (OpenAI base URL: https://<host>/v1)."
