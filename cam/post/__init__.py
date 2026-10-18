"""
Postprosesör katmanı (SPEC 30): tezgâh profili, tezgâh sınır denetimi, blok planı ve ISO biçimleyici.
SPEC 31 aynı planı Siemens Sinumerik ve Heidenhain Klartext'e biçimler.

- `post(ops, machine, ...)` = `check_machine` + `plan` + `format(..., dialect_for(machine))`; programın başına
  `(POST <AD> <DIL>)` ve doğrulanmamış profilde `(DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN)`.
- `read_program(text, machine, tools)`: dile göre okuyucu; yorumlar ve `G53 G0 Z` yola yansımaz.
"""

from __future__ import annotations

from cam.gcode.cycles import DrillOp
from cam.gcode.dialect import Dialect
from cam.model import AxisLimits, MachineProfile, Setup, Tool, Toolpath
from cam.post.blocks import (
    Arc,
    Block,
    Comment,
    Cycle,
    CycleEnd,
    End,
    Linear,
    MachineZ,
    Rapid,
    Spindle,
    Start,
    ToolChange,
    ToolLength,
)
from cam.post.check import check_machine, machine_extents
from cam.post.format_iso import HAAS, format, plan
from cam.post.machine import builtin_machines, load_machine, save_machine

__all__ = [
    "HAAS",
    "Arc",
    "AxisLimits",
    "Block",
    "Comment",
    "Cycle",
    "CycleEnd",
    "End",
    "Linear",
    "MachineProfile",
    "MachineZ",
    "Rapid",
    "Spindle",
    "Start",
    "ToolChange",
    "ToolLength",
    "builtin_machines",
    "check_machine",
    "dialect_for",
    "format",
    "load_machine",
    "machine_extents",
    "plan",
    "post",
    "read_program",
    "save_machine",
]


def dialect_for(machine: MachineProfile) -> Dialect:
    """grbl → GRBL, fanuc → FANUC, haas → HAAS (SPEC 31: sinumerik, heidenhain)."""
    raise NotImplementedError("SPEC 30: dialect_for")


def post(
    ops: list[Toolpath | DrillOp],
    machine: MachineProfile,
    setup: Setup | None = None,
    program_no: int = 1,
    safe_z: float | None = None,
    stock_top: float | None = None,
    length_offsets: dict[int, float] | None = None,
) -> str:
    raise NotImplementedError("SPEC 30: post")


def read_program(
    text: str, machine: MachineProfile, tools: dict[int, Tool], arc_tol: float = 0.005
) -> list[Toolpath]:
    raise NotImplementedError("SPEC 30: read_program")
