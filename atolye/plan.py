"""SPEC 38 — SPEC 29 `MillPlan` → iş föyü uyarlayıcısı."""

from __future__ import annotations

from typing import TYPE_CHECKING

from atolye.is_foyu import JobSheet, build_job_sheet
from cam.gcode import GRBL, Dialect
from cam.model import ToolLibrary
from cam.sim import Machine
from geometry.drawing.dimensions import format_value

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
    n = len(plan.setups)
    ops = [plan.ops_for(i) for i in range(n)]
    names = [[po.name for po in plan.ops if po.setup == i] for i in range(n)]
    uyarilar = [f"{u.feature}: {u.code} — {u.detail}" for u in plan.unplanned]
    uyarilar += [f"{p.feature}: {p.code} = {format_value(p.value)} — {p.detail}" for p in plan.notes]
    dims = ()
    if part is not None:
        from geometry.drawing.sheet import make_drawing

        dims = tuple(d for pv in make_drawing(part).views for d in pv.view.dims)
    return build_job_sheet(
        title,
        plan.setups,
        ops,
        lib,
        plan.material,
        dialect=dialect,
        machine=machine,
        n_max=n_max,
        names=names,
        dims=dims,
        warnings=uyarilar,
        part=part,
        date=date,
    )
