"""
SPEC 54 Karar 3 — Dosyadan parça açma: STEP / STL okumanın §1 biçimli sarmalayıcısı.

`Part.from_step` ya da `geometry.mesh.read_stl` çağrılır; çıkan her hata
`<dosya adı>: <ne oldu> — <ne yapılabilir>` biçimli `GeometryError`'a çevrilir, neden `__cause__`'da kalır.
"""

from __future__ import annotations

from pathlib import Path

from geometry.part import Part

UZANTILAR = (".step", ".stp", ".stl")


def parca_oku(yol: str | Path, ad: str | None = None) -> Part:
    """STEP ya da STL dosyasından tek katı parça; bozuk / boş / katısız / kapalı olmayan → GeometryError."""
    raise NotImplementedError("SPEC 54: parca_oku")
