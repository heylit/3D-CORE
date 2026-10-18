"""SPEC 38 — SPEC 29 `MillPlan` → iş föyü uyarlayıcısı."""

from __future__ import annotations

from typing import TYPE_CHECKING

from atolye.is_foyu import JobSheet
from cam.gcode import GRBL, Dialect
from cam.model import ToolLibrary
from cam.sim import Machine

if TYPE_CHECKING:
    from cam.plan import MillPlan

    from geometry.part import Part


def from_mill_plan(
    plan: MillPlan,
    lib: ToolLibrary,
    title: str,
    dialect: Dialect = GRBL,
    machine: Machine | None = None,
    n_max: float | None = None,
    part: Part | None = None,
    date: str | None = None,
) -> JobSheet:
    """Planın bağlamaları, op'ları, adları, uyarıları ve notlarıyla `build_job_sheet`."""
    raise NotImplementedError("SPEC 38: from_mill_plan")
