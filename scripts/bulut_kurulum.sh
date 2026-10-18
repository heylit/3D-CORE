#!/bin/bash
# Bulut (Claude Code web) oturumu başlangıç kurulumu. Yerelde hiçbir şey yapmaz.
# .claude/settings.json içindeki SessionStart hook'u çağırır.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}"

if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then uv venv -q .venv; else python3 -m venv .venv; fi
fi
if command -v uv >/dev/null 2>&1; then
  uv pip install -q -p .venv/bin/python -e ".[dev,cad]"
else
  .venv/bin/python -m pip install -q -e ".[dev,cad]"
fi
git config core.hooksPath .githooks
echo "[bulut_kurulum] .venv hazır, hook'lar etkin."
