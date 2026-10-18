"""
SPEC 17 — çözülmüş eskizden ekstrüzyona hazır bölgeler ve yaylı döngü alanı.

Kurallar: specs/17-kroki.md "Bölgeler". Alan: A = ½ Σ (u_i v_{i+1} − u_{i+1} v_i) + Σ ½ r² (α − sin α).
"""

from __future__ import annotations

from sketch.model import Sketch, SketchRegion


def regions(sketch: Sketch) -> list[SketchRegion]:
    """Profil öğelerinden bölgeler (dış CCW, delik CW). Sağlanmamış kısıt, açık zincir, dallanma,
    kesişen döngü → SketchError."""
    raise NotImplementedError("SPEC 17: regions")


def area(region: SketchRegion) -> float:
    """Bölge alanı, delikler düşülmüş (mm²)."""
    raise NotImplementedError("SPEC 17: area")
