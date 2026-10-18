"""
SPEC 52 — Silindirik yükseklik haritası (PolarMap): açı θ ve eksen boyu z ızgarası,
her hücrede malzemenin radyal aralığı [r_iç(θ, z), r_dış(θ, z)].

Hacim (hücre ortası örneklemesi): V = Σ ½·(r_dış² − r_iç²)·Δθ[rad]·Δz.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.model import CylinderStock
from cam.sim.radial import RadialMap


@dataclass
class PolarMap:
    """θ_j = (j + ½)·Δθ, z_i = z0 + (i + ½)·dz; r_in, r_out (n_theta, n_z)."""

    z0: float
    dz: float
    n_theta: int
    n_z: int
    r_in: np.ndarray
    r_out: np.ndarray

    @classmethod
    def from_stock(
        cls, stock: CylinderStock, dtheta_deg: float = 1.0, dz: float = 0.05, max_cells: int = 20_000_000
    ) -> PolarMap:
        """CylinderStock → harita; dz stok boyunu tam böler (⌈L/dz⌉ hücre); n_θ·n_z > max_cells → CamError."""
        raise NotImplementedError

    @classmethod
    def from_radial(cls, rmap: RadialMap, dtheta_deg: float = 1.0, dz: float | None = None) -> PolarMap:
        """SPEC 22 RadialMap (dönel simetrik) → harita; her θ aynı. dz None → rmap.dz."""
        raise NotImplementedError

    def thetas(self) -> np.ndarray:
        """Hücre açıları [derece], (n_theta,)."""
        raise NotImplementedError

    def centers(self) -> np.ndarray:
        """Hücre z merkezleri, (n_z,)."""
        raise NotImplementedError

    def volume(self) -> float:
        raise NotImplementedError

    def copy(self) -> PolarMap:
        raise NotImplementedError
