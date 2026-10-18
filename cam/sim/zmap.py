"""
SPEC 05 — Z-haritası (yükseklik haritası): kutu stok üzerinde hücre başına malzemenin üst Z'si.

Hücre (i, j) merkezindeki düşey doğru üzerinde kalan malzemenin üstü z[j, i]; alt sınır stok tabanı zmin.
nx = ⌈Lx/Δ⌉, dx = Lx/nx (gerçek adım ≤ Δ, stok tam örtülür); merkez x_i = x0 + (i + ½)·dx.
Hacim V = Σ (z − zmin)·dx·dy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.model import Stock


@dataclass
class ZMap:
    x0: float
    y0: float
    dx: float
    dy: float
    nx: int
    ny: int
    zmin: float
    zmax: float
    z: np.ndarray

    @classmethod
    def from_stock(cls, stock: Stock, cell: float, max_cells: int = 20000000) -> ZMap:
        """Stoğun XY dikdörtgenini ≤ cell adımlı hücrelere böler; her hücre z = zmax ile başlar."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def xs(self) -> np.ndarray:
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def ys(self) -> np.ndarray:
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        """Hücre merkezleri (X, Y), her biri (ny, nx)."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def volume(self) -> float:
        """V = Σ (z − zmin)·dx·dy"""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def copy(self) -> ZMap:
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def window(self, xlo: float, xhi: float, ylo: float, yhi: float) -> tuple[slice, slice] | None:
        """Merkezi [xlo, xhi] × [ylo, yhi] içindeki hücreler: (satır dilimi, sütun dilimi); yoksa None."""
        raise NotImplementedError("SPEC 05: uygulanmadı")
