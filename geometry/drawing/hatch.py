"""Tarama (SPEC 16): paralel doğruların bölgeyle kesişimi. Saf numpy."""

from __future__ import annotations

from geometry.drawing.types import Line2D
from geometry.part import Region


def hatch(regions: list[Region], s: float = 3.0, theta: float = 45.0) -> list[Line2D]:
    """n·p = (k + ½)·s doğrularının bölgelerle kesişimi, TARAMA katmanı."""
    raise NotImplementedError
