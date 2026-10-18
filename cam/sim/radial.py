"""
SPEC 22 — Radyal dexel: dönel simetrik malzemenin yarı kesiti (z, r).

Z ekseni nz hücreye bölünür; hücre i, merkezindeki z_i = z0 + (i + ½)·dz doğrusu üzerinde malzemenin
r aralık listesini tutar: [(l_1, u_1), (l_2, u_2), …], 0 ≤ l_1 < u_1 < l_2 < …, her aralığın boyu > 0.
Hacim (Pappus, hücre başına kesin): V = Σ π·(u² − l²)·dz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cam.model import CylinderStock
from cam.profile import Profile, Region


@dataclass
class RadialMap:
    z0: float
    dz: float
    nz: int
    r_max: float
    iv: list[list[tuple[float, float]]] = field(default_factory=list, repr=False)  # hücre başına aralıklar

    @classmethod
    def from_stock(
        cls,
        stock: CylinderStock,
        cell: float,
        fixtures: list[CylinderStock] = (),
        max_cells: int = 1_000_000,
    ) -> RadialMap:
        """Stok boyu tam bölünür (dz = L/⌈L/Δ⌉); bağlama elemanları için alta / üste tam hücreler eklenir."""
        raise NotImplementedError

    @classmethod
    def empty_like(cls, grid: RadialMap) -> RadialMap:
        raise NotImplementedError

    def centers(self) -> np.ndarray:
        """Hücre merkezleri z_i, (nz,)."""
        raise NotImplementedError

    def intervals(self, i: int) -> list[tuple[float, float]]:
        raise NotImplementedError

    def subtract(self, i: int, a: float, b: float) -> None:
        """Hücre i'den [a, b] çıkarır; a ≥ b → CamError."""
        raise NotImplementedError

    def add(self, i: int, a: float, b: float) -> None:
        """Hücre i'ye [a, b] ekler (çakışan / değen aralıklarla birleştirerek)."""
        raise NotImplementedError

    def outer(self) -> np.ndarray:
        """Dış yarıçap max u (aralık yoksa 0), (nz,)."""
        raise NotImplementedError

    def inner(self) -> np.ndarray:
        """İç yarıçap min l (aralık yoksa 0), (nz,)."""
        raise NotImplementedError

    def volume(self) -> float:
        """V = Σ π·(u² − l²)·dz"""
        raise NotImplementedError

    def copy(self) -> RadialMap:
        raise NotImplementedError


def profile_rmap(region: Region | Profile, grid: RadialMap) -> RadialMap:
    """(u, v) = (z, x) düzleminde kapalı bölgenin her z_i doğrusundaki aralıkları (çift–tek kuralı)."""
    raise NotImplementedError


def mesh_rmap(V: np.ndarray, T: np.ndarray, grid: RadialMap) -> RadialMap:
    """Dönel simetrik ağın y = 0, x ≥ 0 yarı düzlem kesitinden parça haritası."""
    raise NotImplementedError


def part_rmap(part, grid: RadialMap, tol: float = 0.01) -> RadialMap:
    """part.mesh(tol) + mesh_rmap."""
    raise NotImplementedError
