"""
CalculiX (ccx) girdi dosyası (.inp) yazıcısı (SPEC 13).

Eşleme: `bar1d` (1B) → T3D2, `tet4` (3B) → C3D4; malzeme `*ELASTIC` E, ν; sınır koşulları
`*BOUNDARY`, yükler `*CLOAD`. Gerçel sayılar `format(x, ".12e")` ile yazılır (ccx alanı en çok 20 karakter).
Kaynak: CalculiX CrunchiX User's Manual 2.21.
"""

from __future__ import annotations

from pathlib import Path

from core.model import Model


def to_inp(model: Model) -> str:
    """Modeli CalculiX girdi metnine çevirir. Desteklenmeyen model → ModelError."""
    raise NotImplementedError("SPEC 13: to_inp")


def write_inp(model: Model, path: str | Path) -> None:
    """to_inp çıktısını dosyaya yazar."""
    raise NotImplementedError("SPEC 13: write_inp")
