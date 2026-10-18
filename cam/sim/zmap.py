"""
SPEC 05 — Z-haritası (yükseklik haritası): kutu stok üzerinde hücre başına malzemenin üst Z'si.

Hücre (i, j) merkezindeki düşey doğru üzerinde kalan malzemenin üstü z[j, i]; alt sınır stok tabanı zmin.
nx = ⌈Lx/Δ⌉, dx = Lx/nx (gerçek adım ≤ Δ, stok tam örtülür); merkez x_i = x0 + (i + ½)·dx.
Hacim V = Σ (z − zmin)·dx·dy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.model import CamError, Stock

_EPS = 1e-9  # mm: pencere sınırında merkezleri kapsamak için pay


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
    z: np.ndarray  # (ny, nx)

    @classmethod
    def from_stock(cls, stock: Stock, cell: float, max_cells: int = 20_000_000) -> ZMap:
        """Stoğun XY dikdörtgenini ≤ cell adımlı hücrelere böler; her hücre z = zmax ile başlar."""
        if not isinstance(stock, Stock):
            raise CamError(f"Z-haritası yalnız kutu stokla kurulur ({type(stock).__name__})")
        if not (isinstance(cell, int | float) and math.isfinite(cell) and cell > 0):
            raise CamError(f"Hücre boyu pozitif ve sonlu olmalı (cell={cell})")
        Lx = stock.xmax - stock.xmin
        Ly = stock.ymax - stock.ymin
        nx = max(1, math.ceil(Lx / cell - 1e-12))
        ny = max(1, math.ceil(Ly / cell - 1e-12))
        if nx * ny > max_cells:
            raise CamError(f"Z-haritası çok büyük: {nx}×{ny} hücre > {max_cells} (hücreyi büyütün)")
        z = np.full((ny, nx), float(stock.zmax))
        return cls(
            x0=float(stock.xmin),
            y0=float(stock.ymin),
            dx=Lx / nx,
            dy=Ly / ny,
            nx=nx,
            ny=ny,
            zmin=float(stock.zmin),
            zmax=float(stock.zmax),
            z=z,
        )

    def xs(self) -> np.ndarray:
        return self.x0 + (np.arange(self.nx) + 0.5) * self.dx

    def ys(self) -> np.ndarray:
        return self.y0 + (np.arange(self.ny) + 0.5) * self.dy

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        """Hücre merkezleri (X, Y), her biri (ny, nx)."""
        return np.meshgrid(self.xs(), self.ys())

    def volume(self) -> float:
        """V = Σ (z − zmin)·dx·dy"""
        return float(np.sum(self.z - self.zmin) * self.dx * self.dy)

    def copy(self) -> ZMap:
        return ZMap(self.x0, self.y0, self.dx, self.dy, self.nx, self.ny, self.zmin, self.zmax, self.z.copy())

    def window(self, xlo: float, xhi: float, ylo: float, yhi: float) -> tuple[slice, slice] | None:
        """Merkezi [xlo, xhi] × [ylo, yhi] içindeki hücreler: (satır dilimi, sütun dilimi); yoksa None."""
        i0 = max(0, math.ceil((xlo - self.x0) / self.dx - 0.5 - _EPS))
        i1 = min(self.nx - 1, math.floor((xhi - self.x0) / self.dx - 0.5 + _EPS))
        j0 = max(0, math.ceil((ylo - self.y0) / self.dy - 0.5 - _EPS))
        j1 = min(self.ny - 1, math.floor((yhi - self.y0) / self.dy - 0.5 + _EPS))
        if i0 > i1 or j0 > j1:
            return None
        return slice(j0, j1 + 1), slice(i0, i1 + 1)
