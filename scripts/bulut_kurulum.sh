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
  uv pip install -q -p .venv/bin/python -e ".[dev,cad,viz,web,mesh]"
else
  .venv/bin/python -m pip install -q -e ".[dev,cad,viz,web,mesh]"
fi
# pyvista ekransız çizim (SPEC 15): bulutta ekran yok, VTK OSMesa ile çizer. Kurulamazsa viz testleri düşer.
if [ ! -e /usr/lib/x86_64-linux-gnu/libOSMesa.so.8 ] && command -v apt-get >/dev/null 2>&1; then
  (apt-get install -y -qq libosmesa6 || (apt-get update -qq && apt-get install -y -qq libosmesa6)) >/dev/null 2>&1 \
    || echo "[bulut_kurulum] UYARI: libosmesa6 kurulamadı; pyvista ekransız çizemez."
fi
# gmsh (SPEC 12) wheel'i bu sistem kütüphanelerini ister.
if ! ldconfig -p 2>/dev/null | grep -q libGLU.so.1 && command -v apt-get >/dev/null 2>&1; then
  GMSH_PAKET="libglu1-mesa libxcursor1 libxinerama1 libxft2"
  (apt-get install -y -qq $GMSH_PAKET || (apt-get update -qq && apt-get install -y -qq $GMSH_PAKET)) >/dev/null 2>&1 \
    || echo "[bulut_kurulum] UYARI: gmsh kütüphaneleri kurulamadı; mesh testleri düşer."
fi
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow" >> "$CLAUDE_ENV_FILE"
fi
git config core.hooksPath .githooks
echo "[bulut_kurulum] .venv hazır, hook'lar etkin."
