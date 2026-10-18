"""
SPEC 43 — Çok eksenli simülasyon sürücüsü: program → tri-dexel, süre, çarpışma ve çakma kayıtları.

Hareket k: uç p₀ → p₁ doğrusal, eksen a₀ → a₁ slerp. Sabit eksenli harekette süpürülen küme
takım ⊕ [p₀, p₁] dışbükeydir; değişen eksenli hareket n = ⌈θ·ρ_max / σ⌉ alt adıma bölünür.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cam.dropcutter import TriMesh
from cam.model import Stock, Toolpath
from cam.sim.simulate import Collision, SimStep
from cam.sim.timing import Machine
from cam.sim.tridexel import TriDexel


@dataclass
class SimResult5:
    tridexel: TriDexel
    steps: list[SimStep]
    collisions: list[Collision] = field(default_factory=list)
    removed_volume: float = 0.0
    total_time: float = 0.0

    def rest_volume(self) -> float:
        """Kalan malzeme: malzeme ∖ parça (aileler ortalaması); parça yoksa CamError."""
        raise NotImplementedError("SPEC 43")

    def gouge_volume(self) -> float:
        """Çakma hacmi: parça ∖ malzeme (aileler ortalaması); parça yoksa CamError."""
        raise NotImplementedError("SPEC 43")


def simulate5(
    ops: list[Toolpath],
    stock: Stock,
    cell: float = 1.0,
    machine: Machine | None = None,
    part: TriMesh | None = None,
    sigma: float | None = None,
    arc_tol: float = 1e-3,
    tol: float = 1e-6,
    gouge_tol: float = 1e-3,
    max_rays: int = 3_000_000,
    initial: TriDexel | None = None,
) -> SimResult5:
    """Çok eksenli programı kutu stok üzerinde tri-dexel ile simüle eder."""
    raise NotImplementedError("SPEC 43")
