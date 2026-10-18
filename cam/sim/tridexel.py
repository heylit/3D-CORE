"""
SPEC 43 — Tri-dexel: X, Y ve Z yönündeki üç dik ışın ailesi; her ışında SPEC 05 aralık listesi.

Z ışınları XY hücre merkezlerinden (05 ile aynı ızgara), X ışınları YZ, Y ışınları XZ hücre merkezlerinden.
Hacim her aileden ayrı: V_z = Σ (u − l)·dx·dy, V_x = Σ (u − l)·dy·dz, V_y = Σ (u − l)·dx·dz;
rapor edilen V = (V_x + V_y + V_z)/3.

Işın–takım kesişimi takım çerçevesinde (uç orijinde, eksen +z): kesen kısım dışbükey dönel cisim
{ d ≤ R, h(d) ≤ z ≤ L_f }, gövde SPEC 05 basamakları (ρ_j, H_j).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cam.model import Stock, Tool


@dataclass
class TriDexel:
    x0: float
    y0: float
    z0: float
    dx: float
    dy: float
    dz: float
    nx: int
    ny: int
    nz: int
    rays: dict[str, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict, repr=False)

    @classmethod
    def from_stock(cls, stock: Stock, cell: float, max_rays: int = 3_000_000) -> TriDexel:
        """Her ışında stok boyunca tek aralık."""
        raise NotImplementedError("SPEC 43")

    def intervals(self, axis: str, i: int, j: int) -> list[tuple[float, float]]:
        """axis ∈ {"x", "y", "z"}: Z için (i, j) = (x, y) hücresi, X için (y, z), Y için (x, z)."""
        raise NotImplementedError("SPEC 43")

    def volumes(self) -> tuple[float, float, float]:
        """(V_x, V_y, V_z)"""
        raise NotImplementedError("SPEC 43")

    def volume(self) -> float:
        """V = (V_x + V_y + V_z)/3"""
        raise NotImplementedError("SPEC 43")

    def copy(self) -> TriDexel:
        raise NotImplementedError("SPEC 43")


def ray_tool(tool: Tool, origin, direction, tip, axis, part: str = "kesen") -> tuple[float, float] | None:
    """Işın origin + s·direction ile takım katısının kesişimi [s_giriş, s_çıkış]; kesişim yoksa None.

    part = "kesen": kesen kısım; part = "govde": gövde basamakları (en derin kesişim).
    """
    raise NotImplementedError("SPEC 43")
