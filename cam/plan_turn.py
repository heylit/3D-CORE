"""
SPEC 29 §6 — Otomatik işlem planı (torna): SPEC 27 torna özelliklerinden SPEC 20 işlemlerine (alın, kaba,
finiş, kanal, iç işlem), takım ve kesme verisi SPEC 14'ten, G-code SPEC 21'den.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cam.model import CylinderStock, Setup, ToolLibrary, Wcs
from cam.plan import PlannedOp, PlanNote, Unplanned
from cam.profile import Profile
from cam.turn_features import TurnFeatures

KINDS = ("alin", "dis_kaba", "ic_kaba", "ic_finis", "dis_finis", "kanal")


@dataclass(frozen=True)
class TurnOptions:
    rpm_max: float  # zorunlu (G50)
    finish_allowance: float = 0.2
    clearance: float = 1.0
    strict: bool = False


@dataclass(frozen=True)
class TurnPlan:
    material: str
    outer: TurnFeatures
    inner: TurnFeatures | None
    setup: Setup
    ops: tuple[PlannedOp, ...]
    unplanned: tuple[Unplanned, ...]
    notes: tuple[PlanNote, ...]

    def summary(self) -> list[dict]:
        raise NotImplementedError

    def gcode(self, spindle: str, tool_change: tuple[float, float], program_no: int = 1) -> str:
        """SPEC 21 `write_lathe`."""
        raise NotImplementedError


def plan_turn(
    outer: Profile,
    stock: CylinderStock,
    lib: ToolLibrary,
    material: str,
    options: TurnOptions,
    inner: Profile | None = None,
    wcs: Wcs | None = None,
    fixtures: Sequence[CylinderStock] = (),
) -> TurnPlan:
    raise NotImplementedError
