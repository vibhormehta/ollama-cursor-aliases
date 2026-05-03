#!/usr/bin/env bash
# SSH local port forwards from this machine (e.g. laptop running Cursor) to the LLM server.
#
#   ./scripts/tunnel-to-llm.sh user@llm.example.com
#
# Forwards (defaults):
#   localhost:4000  -> remote 127.0.0.1:4000  (LiteLLM OpenAI proxy)
#   localhost:11434 -> remote 127.0.0.1:11434 (Ollama, optional)
#
# Env:
#   LITELLM_LOCAL=4000          local LiteLLM listen port
#   OLLAMA_LOCAL=11434          local Ollama listen port (set empty to skip Ollama forward)
#   REMOTE_BIND=127.0.0.1       where services listen on the server
#   EXTRA_SSH_OPTS              extra args for ssh (e.g. -i ~/.ssh/id_ed25519)
#
# Cursor with LiteLLM: Base URL http://127.0.0.1:${LITELLM_LOCAL:-4000}/v1 , API key = proxy master_key.
# Raw Ollama OpenAI API: http://127.0.0.1:${OLLAMA_LOCAL:-11434}/v1
#
set -euo pipefail
REMOTE="${1:-}"
if [[ -z "$REMOTE" ]]; then
  echo "usage: $0 user@llm-host" >&2
  echo "example: $0 vib@ollama.tradechefpro.com" >&2
  exit 1
fi

LITELLM_LOCAL="${LITELLM_LOCAL:-4000}"
OLLAMA_LOCAL="${OLLAMA_LOCAL:-11434}"
RB="${REMOTE_BIND:-127.0.0.1}"

SSH_OPTS=(-N -T)
SSH_OPTS+=(-L "${LITELLM_LOCAL}:${RB}:4000")
if [[ -n "${OLLAMA_LOCAL}" ]]; then
  SSH_OPTS+=(-L "${OLLAMA_LOCAL}:${RB}:11434")
fi
# shellcheck disable=SC2206
EXTRA=(${EXTRA_SSH_OPTS:-})

echo "Forwarding:"
echo "  http://127.0.0.1:${LITELLM_LOCAL}/v1  -> ${REMOTE} ${RB}:4000  (LiteLLM)"
if [[ -n "${OLLAMA_LOCAL}" ]]; then
  echo "  http://127.0.0.1:${OLLAMA_LOCAL}/v1 -> ${REMOTE} ${RB}:11434 (Ollama)"
fi
echo "Leave this running. Press Ctrl+C to stop."
exec ssh "${SSH_OPTS[@]}" "${EXTRA[@]}" "$REMOTE"
