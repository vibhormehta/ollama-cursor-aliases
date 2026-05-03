#!/usr/bin/env bash
# Local checks: YAML, Ollama tags, optional public Ollama URL, optional docker compose.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
ok() { echo -e "${GREEN}OK${NC} $*"; }
fail() { echo -e "${RED}FAIL${NC} $*"; exit 1; }

echo "== Parse YAML =="
python3 - <<'PY' || fail "yaml parse"
import sys, pathlib
import yaml
for p in [
    pathlib.Path("litellm-proxy/config.yaml"),
    pathlib.Path("litellm-proxy/config.remote-ollama.example.yaml"),
]:
    yaml.safe_load(p.read_text())
    print("  ", p, "OK")
PY
ok "YAML"

echo "== Ollama (local) =="
if ! command -v ollama >/dev/null 2>&1; then
  fail "ollama CLI not in PATH"
fi
if ! curl -sS -m 2 "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
  fail "Ollama not responding on 127.0.0.1:11434"
fi
python3 - <<'PY' || fail "expected models missing in Ollama"
import json, sys, urllib.request, pathlib, yaml
req = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5)
data = json.load(req)
names = [m["name"] for m in data.get("models", [])]
names_set = set(names)

def tag_ok(tag: str) -> bool:
    if tag in names_set:
        return True
    return any(n.startswith(tag + ":") for n in names)

cfg = yaml.safe_load(pathlib.Path("litellm-proxy/config.yaml").read_text())
for entry in cfg.get("model_list", []):
    lit = entry.get("litellm_params", {}).get("model", "")
    if not lit.startswith("ollama/"):
        continue
    tag = lit.split("/", 1)[1].strip().strip('"').strip("'")
    if not tag_ok(tag):
        print("Missing Ollama tag from config:", tag, file=sys.stderr)
        print("Have:", sorted(names)[:30], file=sys.stderr)
        sys.exit(1)
    print("  present:", tag)
PY
ok "Ollama has qwen2.5-coder / gemma4 family"

echo "== LiteLLM config model strings =="
python3 - <<'PY'
import yaml, pathlib
c = yaml.safe_load(pathlib.Path("litellm-proxy/config.yaml").read_text())
for m in c.get("model_list", []):
    name = m.get("model_name")
    model = m.get("litellm_params", {}).get("model", "")
    print(f"  Cursor→{name!r}  backend→{model!r}")
PY
ok "config dump"

if [[ -n "${OLLAMA_PUBLIC_BASE:-}" ]]; then
  echo "== Ollama (public) $OLLAMA_PUBLIC_BASE =="
  curl -sS -m 15 "${OLLAMA_PUBLIC_BASE%/}/api/tags" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  models:', len(d.get('models',[])))" \
    || fail "public Ollama not reachable"
  ok "public /api/tags"
fi

if command -v docker >/dev/null 2>&1; then
  echo "== docker compose =="
  docker compose -f "$ROOT/litellm-proxy/docker-compose.yml" config -q && ok "compose config"
else
  echo "== docker (skip) =="
  echo "  docker not installed; skipped compose check"
fi

echo "== Proxy smoke (if litellm on :4000) =="
ready=0
for _ in 1 2 3 4 5 6; do
  if curl -sS -m 2 "http://127.0.0.1:4000/v1/models" -H "Authorization: Bearer sk-cursor-local" -o /dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" -eq 1 ]]; then
  curl -sS -m 120 "http://127.0.0.1:4000/v1/chat/completions" \
    -H "Authorization: Bearer sk-cursor-local" \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"max_tokens":3}' | python3 -c "import sys,json; j=json.load(sys.stdin); assert 'choices' in j, j; print('  choices:', len(j['choices']))" \
    && ok "LiteLLM on :4000" || fail "LiteLLM on :4000 bad response"
else
  echo "  (no service on 127.0.0.1:4000 — start with: cd litellm-proxy && docker compose up -d)"
fi

ok "All checks passed"
