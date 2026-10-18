"""
SPEC 42 — eş zamanlı 5 eksen ince işleme: eksen boyunca drop-cutter, normal tahmini, yönelim
stratejileri, sap / tutucu çarpışmasından yana eğimle kaçınma, yönelim sürekliliği.

Birimler: mm, mm/dk, derece.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import Tool, Toolpath
from cam.ops3d import Raster


def drop_along(mesh: TriMesh, tool: Tool, point, a, x_hint=None) -> np.ndarray:
    """`point`'ten geçen `a` doğrultulu çizgide eksen boyunca drop; takım ucu (WCS)."""
    raise NotImplementedError("SPEC 42: drop_along")


def surface_normal(mesh: TriMesh, tool: Tool, x: float, y: float, h_n: float | None = None) -> np.ndarray:
    """Ofset yüzeyden (z_c = drop + R) merkezi farkla birim normal."""
    raise NotImplementedError("SPEC 42: surface_normal")


@dataclass
class Orientation:
    """Takım ekseni stratejisi: "sabit", "normal", "noktaya", "noktadan"; açılar derece."""

    kind: str
    a: tuple[float, float, float] | None = None
    lead: float = 0.0
    tilt: float = 0.0
    point: tuple[float, float, float] | None = None
    max_tilt: float = 90.0

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 42: Orientation")


@dataclass
class Avoid:
    """Gövde çarpışmasında yana eğim adımı ve sınırı [derece], çarpışma toleransı [mm]."""

    dtilt: float = 2.0
    tilt_max: float = 30.0
    tol: float = 1e-6

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 42: Avoid")


def finish5(
    mesh: TriMesh,
    tool: Tool,
    raster: Raster,
    orient: Orientation,
    avoid: Avoid | None = None,
    max_dangle: float = 5.0,
    floor: float | None = None,
) -> Toolpath:
    """Küresel uçla 5 eksen raster ince işleme; her Move.axis dolu, frame = None."""
    raise NotImplementedError("SPEC 42: finish5")
