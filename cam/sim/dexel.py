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

from cam.model import CamError, Stock
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
    lo: np.ndarray  # (ny, nx, K)
    hi: np.ndarray  # (ny, nx, K)

    @classmethod
    def from_stock(cls, stock: Stock, cell: float, max_cells: int = 20_000_000) -> DexelMap:
        """Her hücrede tek aralık [zmin, zmax]."""
        g = ZMap.from_stock(stock, cell, max_cells)
        lo = np.full((g.ny, g.nx, 1), g.zmin)
        hi = np.full((g.ny, g.nx, 1), g.zmax)
        return cls(g.x0, g.y0, g.dx, g.dy, g.nx, g.ny, g.zmin, g.zmax, lo, hi)

    def _grid(self) -> ZMap:
        return ZMap(self.x0, self.y0, self.dx, self.dy, self.nx, self.ny, self.zmin, self.zmax, self.top())

    def xs(self) -> np.ndarray:
        return self.x0 + (np.arange(self.nx) + 0.5) * self.dx

    def ys(self) -> np.ndarray:
        return self.y0 + (np.arange(self.ny) + 0.5) * self.dy

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        return np.meshgrid(self.xs(), self.ys())

    def window(self, xlo: float, xhi: float, ylo: float, yhi: float):
        return self._grid().window(xlo, xhi, ylo, yhi)

    def copy(self) -> DexelMap:
        return DexelMap(
            self.x0,
            self.y0,
            self.dx,
            self.dy,
            self.nx,
            self.ny,
            self.zmin,
            self.zmax,
            self.lo.copy(),
            self.hi.copy(),
        )

    def intervals(self, i: int, j: int) -> list[tuple[float, float]]:
        """Hücre (sütun i, satır j) aralıkları, sıralı ve ayrık."""
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            raise CamError(f"Dexel: hücre ({i}, {j}) ızgara dışında ({self.nx}×{self.ny})")
        lo, hi = self.lo[j, i], self.hi[j, i]
        return [(float(a), float(b)) for a, b in zip(lo, hi, strict=True) if b > a]

    def top(self) -> np.ndarray:
        """Üst yüzey (ny, nx): en üst aralığın u'su, aralık yoksa zmin."""
        t = self.hi.max(axis=2)
        return np.where(np.isfinite(t), t, self.zmin)

    def volume(self) -> float:
        """V = Σ Σ (u − l)·dx·dy"""
        L = np.where(self.hi > self.lo, self.hi - self.lo, 0.0)
        return float(L.sum() * self.dx * self.dy)

    def flipped(self) -> DexelMap:
        """X eksenine paralel 180° çevirme: hücre j → ny − 1 − j, (l, u) → (s − u, s − l), s = zmin + zmax."""
        s = self.zmin + self.zmax
        bos = ~(self.hi > self.lo)
        lo = np.where(bos, np.inf, s - self.hi)[::-1, :, ::-1].copy()
        hi = np.where(bos, -np.inf, s - self.lo)[::-1, :, ::-1].copy()
        return DexelMap(self.x0, self.y0, self.dx, self.dy, self.nx, self.ny, self.zmin, self.zmax, lo, hi)

    def subtract(self, i: int, j: int, a: float, b: float) -> None:
        """Tek hücreden [a, b] aralığını çıkarır (a < b)."""
        if not a < b:
            raise CamError(f"Dexel: çıkarılan aralıkta a < b olmalı ({a}, {b})")
        self.intervals(i, j)  # sınır denetimi
        w = (slice(j, j + 1), slice(i, i + 1))
        self.remove(w, np.array([[a]], dtype=float), np.array([[b]], dtype=float))

    def remove(self, w, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Penceredeki her hücreden [a, b] çıkarır (a ≥ b → dokunma).

        Dönüş: (hücre başına kaldırılan boy, en alçak kaldırılan z; kaldırma yoksa inf).
        """
        lo = self.lo[w]
        hi = self.hi[w]
        A = a[..., None]
        B = b[..., None]
        gecerli = hi > lo
        k_lo = np.maximum(lo, A)
        k_hi = np.minimum(hi, B)
        kesilen = gecerli & (k_hi > k_lo) & (B > A)
        boy = np.where(kesilen, k_hi - k_lo, 0.0).sum(axis=2)
        en_alt = np.where(kesilen, k_lo, np.inf).min(axis=2)
        if not kesilen.any():
            return boy, en_alt
        # sol ve sağ parçalar
        sl_lo, sl_hi = lo, np.where(kesilen, np.minimum(hi, A), hi)
        sa_lo, sa_hi = np.where(kesilen, np.maximum(lo, B), np.inf), np.where(kesilen, hi, -np.inf)
        c_lo = np.concatenate([sl_lo, sa_lo], axis=2)
        c_hi = np.concatenate([sl_hi, sa_hi], axis=2)
        iyi = c_hi > c_lo
        c_lo = np.where(iyi, c_lo, np.inf)
        c_hi = np.where(iyi, c_hi, -np.inf)
        sira = np.argsort(c_lo, axis=2, kind="stable")
        c_lo = np.take_along_axis(c_lo, sira, axis=2)
        c_hi = np.take_along_axis(c_hi, sira, axis=2)
        K = self.lo.shape[2]
        gerek = max(1, int(iyi.sum(axis=2).max()))
        if gerek > K:
            ek = gerek - K
            shape = (self.ny, self.nx, ek)
            self.lo = np.concatenate([self.lo, np.full(shape, np.inf)], axis=2)
            self.hi = np.concatenate([self.hi, np.full(shape, -np.inf)], axis=2)
            K = gerek
        self.lo[w] = c_lo[..., :K] if c_lo.shape[2] >= K else _pad(c_lo, K, np.inf)
        self.hi[w] = c_hi[..., :K] if c_hi.shape[2] >= K else _pad(c_hi, K, -np.inf)
        return boy, en_alt


def _pad(x: np.ndarray, K: int, v: float) -> np.ndarray:
    return np.concatenate([x, np.full(x.shape[:2] + (K - x.shape[2],), v)], axis=2)
