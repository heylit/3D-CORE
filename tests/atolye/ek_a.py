"""SPEC 38 Ek A — uydurma iş (SPEC 14 Ek A ile aynı takımlar) ve K12 için ikinci bağlama.

Yalnız SPEC 38 metninden kuruldu; `atolye` uygulama kodu okunmadı.
"""

from __future__ import annotations

from cam.gcode import DrillOp
from cam.model import Move, MoveType, Setup, Stock, Tool, ToolHolder, ToolKind, ToolLibrary, Toolpath, Wcs
from cam.sim import Machine

H = ToolHolder("BT30-ER", 60, ((0, 15), (40, 20)))


def T1(holder: ToolHolder | None = H) -> Tool:
    """freze6: L = 60 + 30 = 90."""
    return Tool(1, "freze6", ToolKind.FLAT, D=6, flute_length=20, flutes=3, stickout=30, holder=holder)


def T2(holder: ToolHolder | None = H) -> Tool:
    """matkap5: L = 60 + 45 = 105."""
    return Tool(2, "matkap5", ToolKind.DRILL, D=5, flute_length=40, flutes=2, stickout=45, holder=holder)


def lib(t1: Tool | None = None, t2: Tool | None = None) -> ToolLibrary:
    """Sıra bilerek ters: föy ilk kullanım sırasını izler."""
    return ToolLibrary([t2 or T2(), t1 or T1()])


def setup() -> Setup:
    return Setup(
        "on-yuz",
        Wcs("G55", (-250, -190, -80)),
        Stock(0, 0, -20, 50, 40, 0),
        fixtures=[Stock(-15, 0, -20, -5, 40, 10)],
    )


def tp1(t1: Tool | None = None) -> Toolpath:
    """cep: G1 16 mm F100 (9,6 s) + G1 10 mm F300 (2 s) = 11,6 s."""
    return Toolpath(
        "cep",
        t1 or T1(),
        start=(5, 5, 15),
        moves=[Move(MoveType.LINEAR, (5, 5, -1), 100), Move(MoveType.LINEAR, (15, 5, -1), 300)],
        rpm=10000,
    )


def tp2(t2: Tool | None = None) -> Toolpath:
    """delik: bağlantı G0 0,32 s + takım değişimi 10 s + G1 20 mm F150 (8 s) = 18,32 s."""
    return Toolpath(
        "delik",
        t2 or T2(),
        start=(20, 20, 15),
        moves=[Move(MoveType.LINEAR, (20, 20, -5), 150)],
        rpm=3000,
    )


def ops() -> list[Toolpath]:
    return [tp1(), tp2()]


def machine() -> Machine:
    return Machine(rapid=(6000, 6000, 3000), accel=None, tool_change=10)


MATERIAL = "al"

# ---------------------------------------------------------------- K12: iki bağlamalı iş


def drill4() -> DrillOp:
    """G83 gagalamalı 4 delik, T2; dip z = −8 (derinlik ölçüm listesine girmez)."""
    return DrillOp(
        "delik4",
        T2(),
        rpm=2500,
        start=(10, 10, 15),
        holes=[(10, 10), (40, 10), (40, 30), (10, 30)],
        z=-8,
        r=2,
        feed=120,
        kind="G83",
        q=3,
    )


def setup2() -> Setup:
    return Setup("arka-yuz", Wcs("G56", (-250, -190, -100)), Stock(0, 0, -18, 50, 40, 0))


def face2() -> Toolpath:
    """Tek yüz alma, T1, derinlik 0,5."""
    return Toolpath(
        "yuz",
        T1(),
        start=(-5, 3, 10),
        moves=[
            Move(MoveType.RAPID, (-5, 3, 2)),
            Move(MoveType.LINEAR, (-5, 3, -0.5), 200),
            Move(MoveType.LINEAR, (55, 3, -0.5), 600),
            Move(MoveType.LINEAR, (55, 9, -0.5), 600),
            Move(MoveType.LINEAR, (-5, 9, -0.5), 600),
            Move(MoveType.RAPID, (-5, 9, 10)),
        ],
        rpm=8000,
    )
