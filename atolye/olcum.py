"""SPEC 38 — İlk parça ölçüm listesi ve ISO 2768-1 genel doğrusal tolerans (§6).

Kaynak: ISO 2768-1:1989, Tablo 1. Aralık sınırı alt aralığa aittir (3 → "0,5–3").
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from atolye.is_foyu import InspectionItem
from cam.gcode import DrillOp
from cam.model import ARCS, CamError, MoveType, Setup, Toolpath
from geometry.drawing.dimensions import format_value
from geometry.drawing.types import Dimension

# Aralıkların üst sınırları (mm); ilk aralık 0,5'ten başlar
SINIRLAR = (3.0, 6.0, 30.0, 120.0, 400.0, 1000.0, 2000.0, 4000.0)
TABLO: dict[str, tuple[float | None, ...]] = {
    "f": (0.05, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, None),
    "m": (0.1, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0),
    "c": (0.2, 0.3, 0.5, 0.8, 1.2, 2.0, 3.0, 4.0),
    "v": (None, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0, 8.0),
}
ESIT = 1e-6  # mm, aynı derinlik sayılma toleransı


def tolerance_2768(nominal: float, cls: str = "m") -> float:
    """ISO 2768-1 Tablo 1: nominal ölçünün ±t genel toleransı. Tanımsızsa CamError."""
    if cls not in TABLO:
        raise CamError(f"ISO 2768-1: bilinmeyen tolerans sınıfı {cls!r} (f, m, c, v)")
    if not (isinstance(nominal, int | float) and math.isfinite(nominal)):
        raise CamError(f"ISO 2768-1: nominal ölçü sonlu olmalı ({nominal})")
    if nominal < 0.5 or nominal > SINIRLAR[-1]:
        raise CamError(f"ISO 2768-1: {nominal} mm için genel tolerans tanımsız (0,5–4000 mm)")
    i = next(k for k, ust in enumerate(SINIRLAR) if nominal <= ust)
    t = TABLO[cls][i]
    if t is None:
        raise CamError(f"ISO 2768-1: '{cls}' sınıfında {nominal} mm için tolerans tanımsız; resimde belirtin")
    return t


def kesme_z_min(op: Toolpath | DrillOp) -> float | None:
    """Kesme hareketlerinin (G1/G2/G3 uç noktaları) en alçak Z'si; DrillOp'ta delik dibi. Kesme yoksa None."""
    if isinstance(op, DrillOp):
        return float(op.z)
    zs = [m.end[2] for m in op.moves if m.type is MoveType.LINEAR or m.type in ARCS]
    return float(min(zs)) if zs else None


def _kalem(no: int, text: str, nominal: float, cls: str) -> InspectionItem:
    t = tolerance_2768(nominal, cls)
    return InspectionItem(no, text, float(nominal), t, nominal - t, nominal + t)


def inspection_items(
    dims: Sequence[Dimension],
    setups: Sequence[Setup],
    ops: Sequence[Sequence[Toolpath | DrillOp]],
    cls: str = "m",
) -> list[InspectionItem]:
    """Resim ölçüleri (verildiği sırayla) + bağlama başına derinlikler (artan)."""
    if cls not in TABLO:
        raise CamError(f"ISO 2768-1: bilinmeyen tolerans sınıfı {cls!r} (f, m, c, v)")
    kalemler: list[tuple[str, float]] = [(d.text, float(d.value)) for d in dims]
    for setup, liste in zip(setups, ops, strict=True):
        z_ust = setup.stock.zmax
        derinlikler = sorted(
            z_ust - z
            for op in liste
            if isinstance(op, Toolpath) and (z := kesme_z_min(op)) is not None and z_ust - z > 0
        )
        tekil: list[float] = []
        for d in derinlikler:
            if not tekil or d - tekil[-1] > ESIT:
                tekil.append(d)
        kalemler += [(f"{setup.name}: derinlik {format_value(d)}", d) for d in tekil]
    return [_kalem(i, text, nominal, cls) for i, (text, nominal) in enumerate(kalemler, start=1)]
