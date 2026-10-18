"""
SPEC 05 — Tek yönlü (Z) dexel: her hücre merkezinden geçen düşey ışın üzerinde malzeme aralık listesi.

Aralıklar sıralı ve ayrıktır: l_1 < u_1 < l_2 < u_2 < … Kaldırma [a, b] aralık farkıdır:
    [l, u] − [a, b] = [l, min(u, a)] ∪ [max(l, b), u]   (boyu > 0 olan parçalar kalır)
Hacim V = Σ Σ (u − l)·dx·dy. Üst yüzey top = max u (aralık yoksa zmin).
Ters çevirme (ikinci bağlama, X eksenine paralel 180°): y → ymin + ymax − y, z → zmin + zmax − z.

Saklama: lo, hi dizileri (ny, nx, K); boş yuva lo = +inf, hi = −inf. Gerekirse K büyür.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.model import Stock
from cam.sim.zmap import ZMap


@dataclass
class DexelMap:
    x0: float
    y0: float
    dx: float
    dy: float
    nx: int
    ny: int
    zmin: float
    zmax: float
    lo: np.ndarray
    hi: np.ndarray

    @classmethod
    def from_stock(cls, stock: Stock, cell: float, max_cells: int = 20000000) -> DexelMap:
        """Her hücrede tek aralık [zmin, zmax]."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def _grid(self) -> ZMap:
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def xs(self) -> np.ndarray:
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def ys(self) -> np.ndarray:
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def window(self, xlo: float, xhi: float, ylo: float, yhi: float):
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def copy(self) -> DexelMap:
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def intervals(self, i: int, j: int) -> list[tuple[float, float]]:
        """Hücre (sütun i, satır j) aralıkları, sıralı ve ayrık."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def top(self) -> np.ndarray:
        """Üst yüzey (ny, nx): en üst aralığın u'su, aralık yoksa zmin."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def volume(self) -> float:
        """V = Σ Σ (u − l)·dx·dy"""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def flipped(self) -> DexelMap:
        """X eksenine paralel 180° çevirme: hücre j → ny − 1 − j, (l, u) → (s − u, s − l), s = zmin + zmax."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def subtract(self, i: int, j: int, a: float, b: float) -> None:
        """Tek hücreden [a, b] aralığını çıkarır (a < b)."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def remove(self, w, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Penceredeki her hücreden [a, b] çıkarır (a ≥ b → dokunma).

        Dönüş: (hücre başına kaldırılan boy, en alçak kaldırılan z; kaldırma yoksa inf)."""
        raise NotImplementedError("SPEC 05: uygulanmadı")
