#!/bin/sh
# Hook'ların ortak yardımcısı: projenin .venv Python'unu bulur.
if [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"      # Windows
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"              # Linux / macOS / bulut oturumu
else
  PY="python"
fi
