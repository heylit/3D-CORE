"""
SPEC 52 — Silindirik yükseklik haritası (PolarMap): açı θ ve eksen boyu z ızgarası,
her hücrede malzemenin radyal aralığı [r_iç(θ, z), r_dış(θ, z)].

Hacim (hücre ortası örneklemesi): V = Σ ½·(r_dış² − r_iç²)·Δθ[rad]·Δz.
Boş hücre r_iç = r_dış (hacim 0).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.model import CamError, CylinderStock
from cam.sim.radial import RadialMap


def _n_theta(dtheta_deg: float) -> int:
    """Δθ = 360/n_θ ≤ istenen adım; n_θ = ⌈360/Δθ⌉."""
    if not (isinstance(dtheta_deg, int | float) and math.isfinite(dtheta_deg) and 0 < dtheta_deg <= 360):
        raise CamError(f"Açı adımı 0 < Δθ ≤ 360 olmalı (dtheta_deg={dtheta_deg!r})")
    return max(1, math.ceil(360.0 / dtheta_deg - 1e-9))


def _pos(ad: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float) or not (math.isfinite(v) and v > 0):
        raise CamError(f"PolarMap: {ad} pozitif ve sonlu olmalı ({v!r})")
    return float(v)


@dataclass
class PolarMap:
    """θ_j = (j + ½)·Δθ, z_i = z0 + (i + ½)·dz; r_in, r_out (n_theta, n_z)."""

    z0: float
    dz: float
    n_theta: int
    n_z: int
    r_in: np.ndarray
    r_out: np.ndarray

    def __post_init__(self) -> None:
        self.r_in = np.asarray(self.r_in, dtype=float)
        self.r_out = np.asarray(self.r_out, dtype=float)
        shape = (self.n_theta, self.n_z)
        if self.n_theta < 1 or self.n_z < 1 or self.r_in.shape != shape or self.r_out.shape != shape:
            raise CamError(f"PolarMap: r_in ve r_out {shape} boyutunda olmalı")

    @property
    def dtheta(self) -> float:
        """Açı adımı [derece]."""
        return 360.0 / self.n_theta

    @property
    def z1(self) -> float:
        """Izgaranın üst sınırı."""
        return self.z0 + self.n_z * self.dz

    @classmethod
    def from_stock(
        cls, stock: CylinderStock, dtheta_deg: float = 1.0, dz: float = 0.05, max_cells: int = 20_000_000
    ) -> PolarMap:
        """CylinderStock → harita; dz stok boyunu tam böler (⌈L/dz⌉ hücre); n_θ·n_z > max_cells → CamError."""
        if not isinstance(stock, CylinderStock):
            raise CamError(f"PolarMap CylinderStock ister ({type(stock).__name__})")
        n_t = _n_theta(dtheta_deg)
        L = stock.zmax - stock.zmin
        n_z = max(1, math.ceil(L / _pos("dz", dz) - 1e-9))
        if n_t * n_z > max_cells:
            raise CamError(f"Izgara çok büyük ({n_t}×{n_z} > max_cells={max_cells})")
        r_in = np.full((n_t, n_z), stock.d / 2)
        r_out = np.full((n_t, n_z), stock.D / 2)
        return cls(float(stock.zmin), L / n_z, n_t, n_z, r_in, r_out)

    @classmethod
    def from_radial(cls, rmap: RadialMap, dtheta_deg: float = 1.0, dz: float | None = None) -> PolarMap:
        """SPEC 22 RadialMap (dönel simetrik) → harita; her θ aynı. dz None → rmap.dz (başka dz → CamError).

        Hücrede tek aralık olmalı (alt kesik yok); boş hücre r_iç = r_dış = 0.
        """
        if not isinstance(rmap, RadialMap):
            raise CamError(f"from_radial RadialMap ister ({type(rmap).__name__})")
        if dz is not None and abs(_pos("dz", dz) - rmap.dz) > 1e-12 * max(1.0, rmap.dz):
            raise CamError(f"from_radial: dz RadialMap hücre boyuyla aynı olmalı ({dz} ≠ {rmap.dz})")
        n_t = _n_theta(dtheta_deg)
        lo = np.zeros(rmap.nz)
        hi = np.zeros(rmap.nz)
        for i, iv in enumerate(rmap.iv):
            if len(iv) > 1:
                raise CamError(f"from_radial: hücre {i} birden çok aralık içeriyor (tek aralık gerekir)")
            if iv:
                lo[i], hi[i] = iv[0]
        r_in = np.tile(lo, (n_t, 1))
        r_out = np.tile(hi, (n_t, 1))
        return cls(float(rmap.z0), float(rmap.dz), n_t, rmap.nz, r_in, r_out)

    def thetas(self) -> np.ndarray:
        """Hücre açıları [derece], (n_theta,)."""
        return (np.arange(self.n_theta) + 0.5) * self.dtheta

    def centers(self) -> np.ndarray:
        """Hücre z merkezleri, (n_z,)."""
        return self.z0 + (np.arange(self.n_z) + 0.5) * self.dz

    def volume(self) -> float:
        dV = 0.5 * math.radians(self.dtheta) * self.dz
        return float(np.sum(np.maximum(self.r_out**2 - self.r_in**2, 0.0)) * dV)

    def copy(self) -> PolarMap:
        return PolarMap(self.z0, self.dz, self.n_theta, self.n_z, self.r_in.copy(), self.r_out.copy())
