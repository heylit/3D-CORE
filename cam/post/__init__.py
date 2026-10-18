"""
Postprosesör katmanı (SPEC 30): tezgâh profili, tezgâh sınır denetimi, blok planı ve ISO biçimleyici.
SPEC 31 aynı planı Siemens Sinumerik ve Heidenhain Klartext'e biçimler (`format_sinumerik`,
`format_heidenhain`; okuyucular `read_sinumerik`, `read_heidenhain`).

- `post(ops, machine, ...)` = `check_machine` + `plan` + `format(..., dialect_for(machine))`; programın başına
  `(POST <AD> <DIL>)` ve doğrulanmamış profilde `(DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN)`.
- `read_program(text, machine, tools)`: dile göre okuyucu; yorumlar ve `G53 G0 Z` yola yansımaz.
"""

from __future__ import annotations

from dataclasses import replace

from cam.gcode.cycles import DrillOp
from cam.gcode.dialect import FANUC, GRBL, Dialect
from cam.gcode.reader import _read
from cam.model import AxisLimits, CamError, MachineProfile, Setup, Tool, Toolpath
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
from cam.post.check import check_machine, check_safe_z, machine_extents
from cam.post.format_heidenhain import HEIDENHAIN, format_heidenhain
from cam.post.format_iso import HAAS, _guvenli_z, format, plan
from cam.post.format_sinumerik import SINUMERIK, format_sinumerik
from cam.post.lathe import check_lathe, post_lathe
from cam.post.machine import builtin_machines, load_machine, save_machine
from cam.post.read_heidenhain import read_heidenhain
from cam.post.read_sinumerik import read_sinumerik

__all__ = [
    "HAAS",
    "HEIDENHAIN",
    "SINUMERIK",
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
    "check_lathe",
    "check_machine",
    "dialect_for",
    "format",
    "format_heidenhain",
    "format_sinumerik",
    "load_machine",
    "machine_extents",
    "plan",
    "post",
    "post_lathe",
    "read_heidenhain",
    "read_program",
    "read_sinumerik",
    "save_machine",
]


UYARI = "DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN"
DILLER = {"grbl": GRBL, "fanuc": FANUC, "haas": HAAS, "sinumerik": SINUMERIK, "heidenhain": HEIDENHAIN}


def dialect_for(machine: MachineProfile) -> Dialect:
    """grbl → GRBL, fanuc → FANUC, haas → HAAS, sinumerik → SINUMERIK, heidenhain → HEIDENHAIN (SPEC 31)."""
    d = DILLER.get(machine.controller)
    if d is None:
        raise CamError(f"Tezgâh profili '{machine.name}': {machine.controller} dili henüz yok (SPEC 31)")
    return d


def post(
    ops: list[Toolpath | DrillOp],
    machine: MachineProfile,
    setup: Setup | None = None,
    program_no: int = 1,
    safe_z: float | None = None,
    stock_top: float | None = None,
    length_offsets: dict[int, float] | None = None,
) -> str:
    """Denetim + plan + biçim. İş sıfırı kodu `setup.wcs.code` (yoksa G54); koordinat basamağı profilden.

    Önce bütün denetimler: ihlalde CamError, metin üretilmez."""
    if length_offsets is not None:
        raise CamError("length_offsets (G43.1 takım boyu farkı) henüz desteklenmiyor (SPEC 14)")
    check_machine(machine, ops, setup, program_no)
    d = replace(dialect_for(machine), decimals=machine.decimals)
    check_safe_z(machine, ops, setup, _guvenli_z(ops, d, safe_z, stock_top))
    blocks = plan(ops, d, program_no, safe_z, stock_top, tool_change_z=machine.tool_change_z)
    wcs = "G54" if setup is None else setup.wcs.code
    yorum = [Comment(f"POST {machine.name} {machine.controller.upper()}")]
    if not machine.verified:
        yorum.append(Comment(UYARI))
    blocks = [Start(program_no, wcs), *yorum, *blocks[1:]]
    if machine.controller == "sinumerik":
        return format_sinumerik(blocks, d)
    if machine.controller == "heidenhain":
        return format_heidenhain(blocks, machine.presets or {}, d, str(program_no))
    return format(blocks, d)


def read_program(
    text: str, machine: MachineProfile, tools: dict[int, Tool], arc_tol: float = 0.005
) -> list[Toolpath]:
    """Profilin diliyle okuma (yorumlar ve `G53 G0 Z` / `M91` yola yansımaz)."""
    if machine.controller == "sinumerik":
        return read_sinumerik(text, tools, arc_tol)
    if machine.controller == "heidenhain":
        return read_heidenhain(text, tools, arc_tol)
    return _read(text, tools, dialect_for(machine), arc_tol, machine_z=True)
