"""
SPEC 06b — Waterline (sabit Z kontur) ince işleme.

Seviye z için girişim bölgesi I(z) = {c : z_CL(c) > z}. Lifler (X ve Y, ortak s_f ızgarası) üzerinde
her (lif, üçgen) çiftinin girişim aralığı tek aralıktır (z_tri içbükey); aralık uçları kontur noktalarıdır.
Örgü (weave) çizgesinin yarım-kenar yüzlerinden kapalı döngüler çıkar; döngüler uyarlamalı bölünür.
Tırmanma (M3): I(z) hareket yönünün sağında → dış sınır CW, iç sınır CCW.

Birimler: mm.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.cutter import Cutter
from cam.dropcutter import TriMesh
from cam.model import Tool, Toolpath


def waterline_loops(
    mesh: TriMesh,
    tool: Tool | Cutter,
    z: float,
    fiber_step: float,
    tol: float,
    ds_min: float,
    climb: bool = True,
) -> list[np.ndarray]:
    """z seviyesindeki döngüler; her biri (k, 2) XY, kapanış noktası tekrar edilmez."""
    raise NotImplementedError("SPEC 06b: waterline_loops")


@dataclass
class Waterline:
    """Waterline yolu parametreleri; z_levels kesin azalan."""

    z_levels: list[float]
    fiber_step: float
    tol: float
    ds_min: float
    feed: float
    plunge_feed: float
    rpm: float
    z_safe: float
    clearance: float = 1.0
    climb: bool = True

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 06b: Waterline")


def waterline(mesh: TriMesh, tool: Tool, w: Waterline) -> Toolpath:
    """Seviyeler yukarıdan aşağı; her döngü: G0 z_safe, G0 z + clearance, G1 dalma, G1 döngü, G0 z_safe."""
    raise NotImplementedError("SPEC 06b: waterline")
