"""
Yazıcının iki aşaması (SPEC 30) ve ISO ailesi (GRBL, Fanuc, Haas) biçimleyicisi.

- `plan(...)`: modal durum makinesi ve bütün güvenlik mantığı (SPEC 04 Ek B/C) → blok listesi.
- `format(blocks, dialect)`: blokları satırlara çevirir; karar vermez.
`cam.gcode.write(...)` = `format(plan(...), dialect)` (çıktı bayt bayt aynı).

`HAAS`: Fanuc ailesi; `O00001` (5 hane), satır numarası yok, `T1 M06`, `H01` (iki hane).
"""

from __future__ import annotations

from cam.gcode.cycles import DrillOp
from cam.gcode.dialect import GRBL, Dialect
from cam.model import Toolpath
from cam.post.blocks import Block

# Fanuc ailesinden Haas. `M06` ve iki haneli `H01` yazımı kod commit'inde Dialect alanlarıyla gelir;
# o zamana kadar `post()` Haas'ı yazmaz (NotImplementedError), bu nesne cam.gcode.write'a verilmemelidir.
HAAS = Dialect(
    name="Haas",
    decimals=3,
    feed_decimals=1,
    line_numbers=False,
    line_step=10,
    header=("%", "O{program_no:05d}", "G21 G90 G17 G94 G40 G49 G80 G54"),
    footer=("M5", "M30", "%"),
    tool_change="M6",
    canned_cycles=True,
    peck_clearance=0.5,
    tool_length_comp=True,
)


def plan(
    ops: list[Toolpath | DrillOp],
    dialect: Dialect = GRBL,
    program_no: int = 1,
    safe_z: float | None = None,
    stock_top: float | None = None,
    tool_change_z: float | None = None,
) -> list[Block]:
    """Dilden bağımsız blok planı; koordinat basamağı `dialect.decimals`.

    Parametreler `cam.gcode.write` ile aynı anlamdadır."""
    raise NotImplementedError("SPEC 30: plan")


def format(blocks: list[Block], dialect: Dialect) -> str:  # noqa: A001  SPEC 30 adı
    """Blok listesi → program metni ('\\n' ile biten)."""
    raise NotImplementedError("SPEC 30: format")
