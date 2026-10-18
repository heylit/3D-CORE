"""SPEC 30 — yazıcının iki aşaması: blok planı `plan()` ve biçimleyici `format()` (K2).

Testler SPEC 30 metninden ("Yazıcının iki aşaması", blok listesi, K2) ve SPEC 04 Ek A altın
metinlerinden yazıldı. Beklenen bloklar Ek A altın metninin satırlarından elle türetildi:
- bloklar yuvarlanmış değerleri taşır (yazılacak sayının ta kendisi);
- modal bastırma plandadır: değişmeyen eksen / F `None`;
- op başı G0 her zaman üç eksenli; Fanuc'ta takım değişiminden sonraki ilk G0'da `g43_h` = takım no;
- program sonu (`M5 M30` / `%`) dilin son satırlarıdır: tek `End()` bloğu.
"""

from __future__ import annotations

import pytest

from cam.gcode import FANUC, GRBL, write
from cam.post import (
    Arc,
    End,
    Linear,
    MachineZ,
    Rapid,
    Spindle,
    Start,
    ToolChange,
    format,
    plan,
)
from tests.cam.post_ortak import altin_yol, iki_takim

GOLDEN_GRBL = """\
G21 G90 G17 G94
T1
S10000 M3
G0 X0. Y0. Z5.
G1 Z-1. F100.
X10. F300.
Y10.
G3 X0. I-5. J0.
G1 Y0.
G0 Z5.
M5
M30
"""

GOLDEN_FANUC = """\
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80 G54
N20 T1 M6
N30 S10000 M3
N40 G0 G43 X0. Y0. Z5. H1
N50 G1 Z-1. F100.
N60 X10. F300.
N70 Y10.
N80 G3 X0. I-5. J0.
N90 G1 Y0.
N100 G0 Z5.
N110 M5
N120 M30
%
"""


def altin_bloklar(g43_h: int | None) -> list:
    """Ek A yolunun elle yazılmış blok listesi (satır satır altın metinden)."""
    return [
        Start(1),  # baş satırları (GRBL: G21 G90 G17 G94; Fanuc: % O0001 ... G54)
        ToolChange(1, True),  # T1 / T1 M6
        Spindle(10000),  # S10000 M3
        Rapid(0.0, 0.0, 5.0, g43_h),  # G0 (G43) X0. Y0. Z5. (H1)
        Linear(None, None, -1.0, 100.0),  # G1 Z-1. F100.
        Linear(10.0, None, None, 300.0),  # X10. F300.
        Linear(None, 10.0, None, None),  # Y10.
        Arc(0.0, None, None, -5.0, 0.0, True, None),  # G3 X0. I-5. J0.
        Linear(None, 0.0, None, None),  # G1 Y0.
        Rapid(None, None, 5.0),  # G0 Z5.
        End(),  # M5 M30 (%)
    ]


def test_K2_plan_golden_grbl():
    """K2: GRBL'de takım boyu telafisi yok → op başı G0'da g43_h None."""
    assert plan([altin_yol()], GRBL) == altin_bloklar(None)


def test_K2_plan_golden_fanuc():
    """K2: Fanuc'ta takım değişiminden sonraki ilk G0 `G43 ... H1` → g43_h = 1."""
    assert plan([altin_yol()], FANUC) == altin_bloklar(1)


def test_K2_plan_default_dialect_is_grbl():
    assert plan([altin_yol()]) == altin_bloklar(None)


def test_K2_blocks_carry_rounded_values():
    """Bloklar yuvarlanmış değeri taşır: 10.00049 → 10.0 (3 basamak), F 300.04 → 300.0;
    yuvarlanınca aynı kalan eksen yazılmaz (None)."""
    tp = altin_yol()
    m = tp.moves
    m[1] = type(m[1])(m[1].type, (10.00049, 0.0, -1.0), feed=300.04)
    m[2] = type(m[2])(m[2].type, (10.0002, 10.0, -1.0), feed=300.0)
    bl = plan([tp], GRBL)
    assert bl[5] == Linear(10.0, None, None, 300.0)
    assert bl[6] == Linear(None, 10.0, None, None)


def test_K2_format_of_hand_written_blocks():
    """Biçimleyici karar vermez, yalnız yazar: elle yazılmış bloklar altın metni verir."""
    assert format(altin_bloklar(None), GRBL) == GOLDEN_GRBL
    assert format(altin_bloklar(1), FANUC) == GOLDEN_FANUC


@pytest.mark.parametrize("d,golden", [(GRBL, GOLDEN_GRBL), (FANUC, GOLDEN_FANUC)], ids=["GRBL", "Fanuc"])
def test_K2_write_is_format_of_plan(d, golden):
    """`write = format(plan(...), dialect)`: Ek A yolunda üçü de altın metin."""
    assert format(plan([altin_yol()], d), d) == golden
    assert write([altin_yol()], d) == golden


def iki_takim_bloklar(g43: bool, tool_change_z: float | None = None) -> list:
    """op1 kesme derinliğinde biter → güvenli Z'ye geri çekme, M5, (G53 Z), T2, S8000 M3, op2.

    Güvenli Z verilmedi: op başlarının en yükseği 5."""
    mz = [] if tool_change_z is None else [MachineZ(tool_change_z)]
    return [
        Start(1),
        *mz,
        ToolChange(1, True),
        Spindle(10000),
        Rapid(0.0, 0.0, 5.0, 1 if g43 else None),
        Linear(None, None, -1.0, 100.0),
        Linear(20.0, None, None, 300.0),
        Rapid(None, None, 5.0),  # Ek B: takım değişiminden önce güvenli Z
        Spindle(None),  # Ek B: iş mili dönerken takım değiştirilmez (M5)
        *mz,  # SPEC 30: geri çekme ve M5'ten sonra G53 G0 Z<tool_change_z>
        ToolChange(2, False),
        Spindle(8000),
        Rapid(40.0, 0.0, 5.0, 2 if g43 else None),  # op başı üç eksenli G0
        Linear(None, None, -2.0, 80.0),
        Rapid(None, None, 5.0),
        End(),
    ]


@pytest.mark.parametrize("d", [GRBL, FANUC], ids=["GRBL", "Fanuc"])
def test_K2_plan_two_tools(d):
    """Ek B güvenlik kararları planda: geri çekme, M5 sonra takım değişimi."""
    assert plan(iki_takim(), d) == iki_takim_bloklar(d is FANUC)


def test_K2_plan_tool_change_z():
    """SPEC 30 "Takım değişim konumu": her takım değişiminden önce (ilki dahil) `MachineZ`;
    ikincide güvenli Z'ye çekme ve M5'ten sonra."""
    assert plan(iki_takim(), FANUC, tool_change_z=0.0) == iki_takim_bloklar(True, 0.0)
    assert plan(iki_takim(), FANUC, tool_change_z=-12.5) == iki_takim_bloklar(True, -12.5)


def test_K2_plan_program_no():
    assert plan([altin_yol()], FANUC, program_no=42)[0] == Start(42)
