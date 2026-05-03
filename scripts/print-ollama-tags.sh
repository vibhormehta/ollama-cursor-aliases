#!/usr/bin/env bash
# List Ollama model names (for matching litellm_params.model to ollama/<tag>).
set -euo pipefail
BASE="${OLLAMA_BASE:-http://127.0.0.1:11434}"
exec curl -sS "${BASE%/}/api/tags" | python3 -c "import sys,json; print([m['name'] for m in json.load(sys.stdin).get('models',[])])"
