#!/usr/bin/env bash
# docker compose wrapper for litellm-proxy (uses sudo + SUDO_PASSWORD from .env if needed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/litellm-proxy"
if [[ -r /home/vib/.env ]]; then set -a && . /home/vib/.env && set +a; fi
run() { docker compose -f "$ROOT/litellm-proxy/docker-compose.yml" "$@"; }
if docker info >/dev/null 2>&1; then
  run "$@"
elif [[ -n "${SUDO_PASSWORD:-}" ]]; then
  printf '%s\n' "$SUDO_PASSWORD" | sudo -S -E docker compose -f "$ROOT/litellm-proxy/docker-compose.yml" "$@"
else
  echo "docker: permission denied. Use: sudo usermod -aG docker \$USER && newgrp docker" >&2
  exit 1
fi
