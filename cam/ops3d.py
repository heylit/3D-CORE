"""
SPEC 06 — 3D takım yolları: raster ince işleme ve drop-cutter tabanlı katmanlı kaba işleme.

Birimler: mm, mm/dk, dev/dk. İskelet: gövdeler henüz yazılmadı.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.dropcutter import TriMesh
from cam.model import Stock, Tool, Toolpath


@dataclass
class Raster:
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    stepover: float
    ds: float
    tol: float
    ds_min: float
    feed: float
    plunge_feed: float
    rpm: float
    z_safe: float
    direction: str = "x"
    clearance: float = 1.0

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 06: Raster doğrulaması")


def raster_lines(r: Raster) -> list[float]:
    """Sıraların sabit koordinatları: m = ⌈(üst − alt)/s⌉ + 1, eşit aralıklı, ilk ve son kenarda."""
    raise NotImplementedError("SPEC 06: raster_lines")


def finish(mesh: TriMesh, tool: Tool, r: Raster, floor: float | None = None) -> Toolpath:
    """Raster ince işleme (uyarlamalı bölme, zigzag)."""
    raise NotImplementedError("SPEC 06: finish")


def rough(
    mesh: TriMesh,
    stock: Stock,
    tool: Tool,
    r: Raster,
    a_p: float,
    z_bottom: float,
    allowance: float = 0.0,
) -> Toolpath:
    """Katmanlı kaba işleme: her seviyede z_CL = max(z_δ, z_i)."""
    raise NotImplementedError("SPEC 06: rough")
