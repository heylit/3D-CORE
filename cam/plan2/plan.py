"""SPEC 57 — Otomatik plan: freze (çok bağlama, 3+2 yönelim) ve torna (ters bağlama)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cam.gcode import GRBL, Dialect
from cam.model import CylinderStock, Frame, MachineProfile, Setup, Stock, ToolLibrary
from cam.plan import DEFAULT_OPTIONS, MillOptions, MillPlan, Unplanned
from cam.plan_turn import TurnOptions, TurnPlan
from cam.plan_verify import PlanCheck
from cam.profile import Profile
from geometry.part import Part

UNPLANNED_CODES = ("stok_yok", "stok_kucuk", "erisim_yok", "cene_engeli", "kavrama_yuzeyi_yok", "aday_siniri")


@dataclass(frozen=True)
class AutoOptions:
    mill: MillOptions = DEFAULT_OPTIONS
    m: float = 1.0
    g: float = 5.0
    clearance: float = 1.0
    c_tc: float = 1.0
    c_rot: float = 0.1
    ang_tol: float = 0.5
    max_candidates: int = 16
    verify: bool = True


DEFAULT_AUTO = AutoOptions()  # dondurulmuş: paylaşılan varsayılan güvenli


@dataclass(frozen=True)
class AutoPlan:
    stock: Stock | CylinderStock
    clamps: tuple[Setup, ...]
    frames: tuple[tuple[Frame, ...], ...]
    plans: tuple[MillPlan, ...]
    order: tuple[tuple[str, ...], ...]
    tool_changes: int
    rotations: int
    unplanned: tuple[Unplanned, ...]
    checks: tuple[PlanCheck, ...]

    def summary(self) -> list[dict]:
        raise NotImplementedError("SPEC 57: AutoPlan.summary")

    def gcode(self, lib: ToolLibrary, dialect: Dialect = GRBL) -> list[str]:
        raise NotImplementedError("SPEC 57: AutoPlan.gcode")


def plan_auto(
    part: Part,
    lib: ToolLibrary,
    material: str,
    machine: MachineProfile,
    catalog=None,
    stock: Stock | None = None,
    fixtures: Sequence = (),
    options: AutoOptions = DEFAULT_AUTO,
) -> AutoPlan:
    """Stok, en az bağlama, yönelimler, sıralama ve doğrulama (SPEC 57 §1–5, §7)."""
    raise NotImplementedError("SPEC 57: plan_auto")


def plan_auto_turn(
    outer: Profile,
    lib: ToolLibrary,
    material: str,
    options: TurnOptions,
    catalog=None,
    stock: CylinderStock | None = None,
    grip: float = 20.0,
    inner: Profile | None = None,
) -> tuple[TurnPlan, ...]:
    """Torna: bir ya da iki bağlama (ters bağlama, SPEC 57 §6)."""
    raise NotImplementedError("SPEC 57: plan_auto_turn")
