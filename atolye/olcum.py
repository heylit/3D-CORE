"""SPEC 38 — İlk parça ölçüm listesi ve ISO 2768-1 genel doğrusal tolerans (§6)."""

from __future__ import annotations

from collections.abc import Sequence

from atolye.is_foyu import InspectionItem
from cam.gcode import DrillOp
from cam.model import Setup, Toolpath
from geometry.drawing.types import Dimension


def tolerance_2768(nominal: float, cls: str = "m") -> float:
    """ISO 2768-1 Tablo 1: nominal ölçünün ±t genel toleransı. Tanımsızsa CamError."""
    raise NotImplementedError("SPEC 38: tolerance_2768")


def inspection_items(
    dims: Sequence[Dimension],
    setups: Sequence[Setup],
    ops: Sequence[Sequence[Toolpath | DrillOp]],
    cls: str = "m",
) -> list[InspectionItem]:
    """Resim ölçüleri (verildiği sırayla) + bağlama başına derinlikler (artan)."""
    raise NotImplementedError("SPEC 38: inspection_items")
