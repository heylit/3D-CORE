"""
SPEC 05 — Simülasyon sürücüsü: program → z-haritası, süre, olay listesi, çarpışma ve çakma kayıtları.

Global adım indeksi k: nokta 0 = ilk yolun başlangıcı, adım k'nin bitişi nokta k. Ardışık iki yol arasında
uçlar farklıysa doğrusal G0 bağlantı adımı eklenir. Her adım alt adımlara (boy ≤ min(R, L_f)/2) bölünür:
malzeme sonucu alt adımdan bağımsızdır (min), çarpışma denetimi hareket içindeki ilerlemeyi görür.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cam.gcode import GRBL, DrillOp
from cam.model import MoveType, Stock, Toolpath
from cam.sim.dexel import DexelMap
from cam.sim.timing import Machine
from cam.sim.zmap import ZMap

KINDS = ("hizli_carpma", "sap_carpma", "tutucu_carpma", "cakma")


@dataclass
class Collision:
    """Çarpışma / çakma kaydı. at: hücre merkezi ve orada takım yüzeyinin Z'si (en derin batma noktası)."""

    kind: str
    k: int
    op: int
    at: tuple[float, float, float]
    depth: float


@dataclass
class SimStep:
    """Bir adım (hareket veya bağlantı). t0: başlangıç zamanı [s] (takım değişimi dahil), removed [mm³]."""

    k: int
    op: int
    type: MoveType
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    center: tuple[float, float] | None
    feed: float | None
    link: bool
    t0: float
    duration: float
    removed: float
    mrr: float


@dataclass
class SimResult:
    zmap: ZMap
    steps: list[SimStep]
    start: tuple[float, float, float]
    total_time: float
    op_times: list[float]
    event_cell: np.ndarray
    event_k: np.ndarray
    event_z: np.ndarray
    offsets: np.ndarray
    collisions: list[Collision] = field(default_factory=list)
    removed_volume: float = 0.0
    part_z: np.ndarray | None = None
    dexel: DexelMap | None = None
    z0: np.ndarray | None = None

    def points(self) -> np.ndarray:
        """Nokta 0 + her adımın bitişi, (n+1, 3)."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def cumulative_time(self) -> np.ndarray:
        """Nokta k'ye varış zamanı [s], (n+1,); nokta 0'da 0."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def zmap_at(self, k: int) -> np.ndarray:
        """k adımdan sonraki yüzey: her hücrede k' ≤ k olan son olayın z'si, olay yoksa zmax."""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def _part_mask(self) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def rest_volume(self) -> float:
        """Kalan malzeme V = Σ max(z − max(z_P, zmin), 0)·dx·dy"""
        raise NotImplementedError("SPEC 05: uygulanmadı")

    def gouge_volume(self) -> float:
        """Çakma hacmi V = Σ max(z_P − z, 0)·dx·dy (z_P > zmin hücrelerde)"""
        raise NotImplementedError("SPEC 05: uygulanmadı")


def simulate(
    ops: list[Toolpath | DrillOp],
    stock: Stock,
    cell: float = 1.0,
    machine: Machine | None = None,
    part_z: np.ndarray | None = None,
    arc_tol: float = 0.001,
    tol: float = 1e-06,
    gouge_tol: float = 0.001,
    dialect=GRBL,
    max_cells: int = 20000000,
    model: str = "zmap",
    initial: ZMap | DexelMap | None = None,
) -> SimResult:
    """Freze programını kutu stok üzerinde z-haritasıyla simüle eder (SPEC 05)."""
    raise NotImplementedError("SPEC 05: uygulanmadı")
