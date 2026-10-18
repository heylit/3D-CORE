"""
SPEC 29 §7 — İşlem planının simülasyonla doğrulanması: freze SPEC 05 (dexel, ikinci bağlamada ters
çevrilmiş harita), torna SPEC 22.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.plan import MillPlan
from cam.plan_turn import TurnPlan
from cam.sim import Collision, Machine
from geometry.part import Part


@dataclass(frozen=True)
class PlanCheck:
    ok: bool
    collisions: tuple[Collision, ...]
    removed_volume: float
    rest_volume: float
    gouge_volume: float
    expected_rest: float  # freze: Σ kose_artigi; torna: 0
    total_time: float  # s, bağlamaların toplamı


def verify_mill(plan: MillPlan, part: Part, cell: float = 0.5, machine: Machine | None = None) -> PlanCheck:
    raise NotImplementedError


def verify_turn(plan: TurnPlan, cell: float = 0.25, machine: Machine | None = None) -> PlanCheck:
    raise NotImplementedError
