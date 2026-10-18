"""
SPEC 18 — Döndürme (revolve) takım gövdesi ve yüz adları.

Kesit bölgeleri (SPEC 17 `SketchRegion`, uv) eskiz düzlemindeki bir eksen etrafında döner. Hacim Pappus:
V = θ · ρ̄ · A. Bölge ekseni kesmez; eksene değen kenar yüzey üretmez. Yan yüzler `yan:<src>`, açı < 360°
ise kapaklar `bas`, `son` adını alır. `geometry/revolve.py` SPEC 28'indir; bu dosya ondan bağımsızdır.
Birimler: mm, derece.
"""

from __future__ import annotations

from collections.abc import Sequence

from geometry.part import Part
from sketch.model import Plane, SketchRegion


def revolve(
    regions: Sequence[SketchRegion],
    plane: Plane,
    eksen_p: tuple[float, float],
    eksen_y: tuple[float, float],
    aci: float = 360.0,
    name: str = "dondurme",
) -> Part:
    """Bölgeleri uv'de `eksen_p` noktasından geçen `eksen_y` yönlü eksen etrafında `aci` derece döndürür.

    Dönen gövde adlıdır (yerel adlar, özellik kimliğini ağaç ekler). Hatalar (`GeometryError`): boş bölge,
    ekseni kesen bölge, aci ∉ (0, 360], |eksen_y| = 0, sonsuz değer.
    """
    raise NotImplementedError("SPEC 18: revolve")
