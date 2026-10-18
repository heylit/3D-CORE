"""
SPEC 22 — Torna talaş simülasyonu (radyal dexel), süre, hızlı çarpma, kenar boyu aşımı, tutucu ve ayna
çarpışması, çakma; SPEC 24 olay listesi.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cam.model import CylinderStock, Setup, Toolpath
from cam.sim.radial import RadialMap
from cam.sim.simulate import Collision, SimStep
from cam.sim.timing import Machine

KINDS = ("hizli_carpma", "kenar_asimi", "tutucu_carpma", "ayna_carpma", "cakma")


@dataclass
class LatheSimResult:
    rmap: RadialMap
    steps: list[SimStep]
    start: tuple[float, float, float]
    total_time: float
    op_times: list[float]
    event_cell: np.ndarray  # int32
    event_k: np.ndarray  # int32
    event_iv_off: np.ndarray  # int64, olay sayısı + 1
    event_iv: np.ndarray  # float64 (M, 2)
    offsets: np.ndarray  # int64, nz + 1
    collisions: list[Collision] = field(default_factory=list)
    removed_volume: float = 0.0
    part: RadialMap | None = None

    def points(self) -> np.ndarray:
        """Nokta 0 + her adımın bitişi, (n+1, 3)."""
        raise NotImplementedError

    def cumulative_time(self) -> np.ndarray:
        """Nokta k'ye varış zamanı [s], (n+1,); nokta 0'da 0."""
        raise NotImplementedError

    def section_at(self, k: int) -> list[list[tuple[float, float]]]:
        """k adımdan sonraki kesit; 0 ≤ k ≤ n, aksi CamError."""
        raise NotImplementedError

    def rest_volume(self) -> float:
        raise NotImplementedError

    def gouge_volume(self) -> float:
        raise NotImplementedError


def simulate_lathe(
    ops: list[Toolpath],
    stock: CylinderStock | Setup,
    cell: float = 0.5,
    machine: Machine | None = None,
    part: RadialMap | None = None,
    arc_tol: float = 1e-3,
    tol: float = 1e-6,
    gouge_tol: float = 1e-3,
    max_cells: int = 1_000_000,
    initial: RadialMap | None = None,
) -> LatheSimResult:
    raise NotImplementedError
