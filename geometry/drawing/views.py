"""HLR ile görünüş ve kesit (SPEC 16). OCCT gerektirir."""

from __future__ import annotations

from geometry.drawing.types import View
from geometry.part import Part


def project(part: Part, direction: str, tol: float = 0.01, axes: bool = True) -> View:
    """direction ∈ {"on", "ust", "sol", "sag"} yönünde dik izdüşüm, gizli çizgiler ayrılmış."""
    raise NotImplementedError


def section(
    part: Part,
    direction: str,
    offset: float,
    name: str = "A-A",
    s: float = 3.0,
    theta: float = 45.0,
    tol: float = 0.01,
) -> View:
    """Görünüş düzlemine paralel kesit (on: y = offset, ust: z = offset, sol/sag: x = offset)."""
    raise NotImplementedError
