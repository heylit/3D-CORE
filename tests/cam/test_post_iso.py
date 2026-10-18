"""SPEC 30 — `post` ile GRBL / Fanuc / Haas yazımı: takım değişim konumu (K11), Haas altın metni (K12),
yorumlar (K13), `dialect_for` ve `read_program`.

Testler SPEC 30 metninden (Arayüz "Yazma ve okuma", "Haas dili", "Takım değişim konumu", K11–K13) yazıldı.
Fanuc'ta yorum satırlarının N numarası alıp almadığı SPEC'te yazmadığı için Fanuc karşılaştırmaları
N numaraları atılarak yapılır (`n_siz`).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL, read, write
from cam.model import CamError, Move
from cam.post import HAAS, builtin_machines, dialect_for, post, read_program
from tests.cam.post_ortak import (
    G1,
    UYARI,
    altin_yol,
    iki_takim,
    kurulum,
    n_siz,
    satirlar,
    takim,
    yorumsuz,
)

TOL = 0.5e-3 + 1e-9


def ornek(ad: str):
    return builtin_machines()[ad]


GRBL_M = "ORNEK-GRBL-ROUTER"
FANUC_M = "ORNEK-FANUC-DIK"
HAAS_M = "ORNEK-HAAS-DIK"

# İş sıfırları (makine koordinatı): örnek profillerin kursları içinde, L = 100 mm takımla.
KURULUM = {
    GRBL_M: kurulum((300.0, 200.0, -160.0)),  # z_ölçü = z − 60 ∈ [−120, 0]
    FANUC_M: kurulum((0.0, 0.0, -200.0)),  # z_ölçü = z − 100 ∈ [−500, 0]
    HAAS_M: kurulum((0.0, 0.0, -200.0)),  # z_ölçü = z − 100 ∈ [−450, 0]
}


# ---------------------------------------------------------------- dialect_for


def test_dialect_for():
    """Arayüz: grbl → GRBL, fanuc → FANUC, haas → HAAS."""
    assert dialect_for(ornek(GRBL_M)) == GRBL
    assert dialect_for(ornek(FANUC_M)) == FANUC
    assert dialect_for(ornek(HAAS_M)) == HAAS


# ---------------------------------------------------------------- K12: Haas altın metni

GOLDEN_HAAS = """\
%
O00001
G21 G90 G17 G94 G40 G49 G80 G54
(POST ORNEK-HAAS-DIK HAAS)
(DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN)
T1 M06
S10000 M3
G0 G43 X0. Y0. Z5. H01
G1 Z-1. F100.
X10. F300.
Y10.
G3 X0. I-5. J0.
G1 Y0.
G0 Z5.
M5
M30
%
"""


def test_K12_haas_golden():
    """K12: Ek A yolu, safe_z = 5, ORNEK-HAAS-DIK (tool_change_z = None kopyası), G54 → satır satır."""
    m = replace(ornek(HAAS_M), tool_change_z=None)
    out = post([altin_yol(takim(1))], m, KURULUM[HAAS_M], safe_z=5.0)
    assert satirlar(out) == satirlar(GOLDEN_HAAS)
    assert out == GOLDEN_HAAS


def test_K12_haas_two_digit_h_and_m06():
    """Haas: `T2 M06` ve `H02`; iki takımlı programda ikinci takım da iki haneli."""
    m = replace(ornek(HAAS_M), tool_change_z=None)
    ls = satirlar(post(iki_takim(), m, KURULUM[HAAS_M]))
    assert "T2 M06" in ls
    assert "G0 G43 X40. Y0. Z5. H02" in ls
    assert not any(ln.startswith("N") for ln in ls)  # Haas'ta satır numarası yok


# ---------------------------------------------------------------- K13: yorumlar

BAS = {GRBL_M: 1, FANUC_M: 3, HAAS_M: 3}  # dilin baş satırı sayısı (GRBL: G21...; Fanuc/Haas: % O... G21...)


@pytest.mark.parametrize("ad", [GRBL_M, FANUC_M, HAAS_M])
def test_K13_comments_unverified(ad):
    """K13: verified = False → baş satırlarından hemen sonra iki yorum (ASCII, büyük harf)."""
    m = replace(ornek(ad), tool_change_z=None)
    ls = n_siz(post([altin_yol(takim(1))], m, KURULUM[ad]))
    n = BAS[ad]
    assert ls[n] == f"(POST {m.name} {m.controller.upper()})"
    assert ls[n + 1] == UYARI
    assert sum(ln.startswith("(") for ln in ls) == 2
    assert all(ln.isascii() for ln in ls)


@pytest.mark.parametrize("ad", [GRBL_M, FANUC_M, HAAS_M])
def test_K13_comments_verified(ad):
    """K13: verified = True → yalnız `(POST ...)`."""
    m = replace(ornek(ad), tool_change_z=None, verified=True)
    ls = n_siz(post([altin_yol(takim(1))], m, KURULUM[ad]))
    n = BAS[ad]
    assert ls[n] == f"(POST {m.name} {m.controller.upper()})"
    assert UYARI not in ls
    assert sum(ln.startswith("(") for ln in ls) == 1


@pytest.mark.parametrize("ad", [GRBL_M, FANUC_M])
def test_post_equals_write_plus_comments(ad):
    """Yorumlar dışında `post` çıktısı `cam.gcode.write` ile aynı (GRBL / Fanuc, tool_change_z yok)."""
    m = replace(ornek(ad), tool_change_z=None)
    ops = iki_takim()
    d = dialect_for(m)
    assert yorumsuz(n_siz(post(ops, m, KURULUM[ad], safe_z=7.5))) == n_siz(write(ops, d, safe_z=7.5))


@pytest.mark.parametrize("ad", [GRBL_M, FANUC_M, HAAS_M])
def test_K13_reader_ignores_comments(ad):
    """K13: okuyucu yorumları yok sayar: `read_program(post)` = yorumsuz metnin okunuşu."""
    m = replace(ornek(ad), tool_change_z=None)
    ops = iki_takim()
    tools = {1: ops[0].tool, 2: ops[1].tool}
    text = post(ops, m, KURULUM[ad])
    got = read_program(text, m, tools)
    assert len(got) == 2
    d = GRBL if ad == GRBL_M else FANUC  # Haas ve Fanuc aynı hareketleri yazar
    _ayni(got, read(write(ops, d), tools, d))


def _ayni(got, exp) -> None:
    assert len(got) == len(exp)
    for g, e in zip(got, exp, strict=True):
        assert g.tool == e.tool and g.rpm == e.rpm
        assert [mv.type for mv in g.moves] == [mv.type for mv in e.moves]
        np.testing.assert_allclose(g.points(), e.points(), rtol=0, atol=TOL)


# ---------------------------------------------------------------- K11: takım değişim konumu

GOLDEN_FANUC_TCZ = [
    "%",
    "O0001",
    "G21 G90 G17 G94 G40 G49 G80 G54",
    "(POST ORNEK-FANUC-DIK FANUC)",
    UYARI,
    "G53 G0 Z0.",  # ilk takımdan önce de (SPEC: iş mili makine sıfırında varsayılmaz)
    "T1 M6",
    "S10000 M3",
    "G0 G43 X0. Y0. Z5. H1",
    "G1 Z-1. F100.",
    "X20. F300.",
    "G0 Z5.",  # Ek B: güvenli Z
    "M5",  # Ek B: iş mili durur
    "G53 G0 Z0.",  # SPEC 30: sonra makine takım değişim yüksekliği
    "T2 M6",
    "S8000 M3",
    "G0 G43 X40. Y0. Z5. H2",  # op başı üç eksenli G0 (Z bilinmiyor)
    "G1 Z-2. F80.",
    "G0 Z5.",
    "M5",
    "M30",
    "%",
]


def test_K11_tool_change_position_sequence():
    """K11: tool_change_z = 0, iki takımlı program: takım değişiminden önce sırayla
    `G0 Z<safe_z>`, `M5`, `G53 G0 Z0.`, `T2 M6`."""
    m = ornek(FANUC_M)
    assert m.tool_change_z == 0.0
    ls = n_siz(post(iki_takim(), m, KURULUM[FANUC_M]))
    i = ls.index("T2 M6")
    assert ls[i - 3 : i + 1] == ["G0 Z5.", "M5", "G53 G0 Z0.", "T2 M6"]
    assert ls == GOLDEN_FANUC_TCZ


def test_K11_tool_change_z_value_and_grbl():
    """`tool_change_z` değeri yazılır (−12.5 → `G53 G0 Z-12.5`); GRBL 1.1'de de G53 var."""
    m = replace(ornek(FANUC_M), tool_change_z=-12.5)
    ls = n_siz(post(iki_takim(), m, KURULUM[FANUC_M]))
    assert ls.count("G53 G0 Z-12.5") == 2
    g = replace(ornek(GRBL_M), tool_change_z=-1.0)
    ls = satirlar(post(iki_takim(), g, KURULUM[GRBL_M]))
    i = ls.index("T2 M0")
    assert ls[i - 3 : i + 1] == ["G0 Z5.", "M5", "G53 G0 Z-1.", "T2 M0"]


@pytest.mark.parametrize("ad", [FANUC_M, HAAS_M])
def test_K11_only_difference_is_g53(ad):
    """tool_change_z'li çıktıdan G53 satırları atılınca tool_change_z'siz çıktı kalır."""
    m = ornek(ad)
    ops = iki_takim()
    a = n_siz(post(ops, m, KURULUM[ad]))
    b = n_siz(post(ops, replace(m, tool_change_z=None), KURULUM[ad]))
    assert sum(ln.startswith("G53 ") for ln in a) == 2
    assert [ln for ln in a if not ln.startswith("G53 ")] == b


@pytest.mark.parametrize("ad", [GRBL_M, FANUC_M, HAAS_M])
def test_K11_reader_accepts_g53(ad):
    """K11: okuyucu `G53 G0 Z` satırını kabul eder; yol G53'süz programın yoluyla aynı (≤ ε)."""
    m = replace(ornek(ad), tool_change_z=-1.0)
    ops = iki_takim()
    tools = {1: ops[0].tool, 2: ops[1].tool}
    got = read_program(post(ops, m, KURULUM[ad]), m, tools)
    exp = read_program(post(ops, replace(m, tool_change_z=None), KURULUM[ad]), m, tools)
    _ayni(got, exp)
    assert [g.tool.id for g in got] == [1, 2]


# ---------------------------------------------------------------- profil alanlarının yazıma etkisi


def test_decimals_from_profile():
    """`machine.decimals` koordinat basamağıdır: 4 → `X1.2346`, 3 → `X1.235`."""
    tp = altin_yol(takim(1))
    tp.moves.insert(2, Move(G1, (1.23456, 0.0, -1.0), feed=300.0))
    m3 = replace(ornek(FANUC_M), tool_change_z=None)
    m4 = replace(m3, decimals=4)
    s3 = " ".join(n_siz(post([tp], m3, KURULUM[FANUC_M])))
    s4 = " ".join(n_siz(post([tp], m4, KURULUM[FANUC_M])))
    assert "X1.235 " in s3
    assert "X1.2346 " in s4


def test_program_no_digits():
    """Program numarası hane sayısı dilden: Fanuc `O0042`, Haas `O00042`."""
    f = n_siz(post([altin_yol(takim(1))], ornek(FANUC_M), KURULUM[FANUC_M], program_no=42))
    h = n_siz(post([altin_yol(takim(1))], ornek(HAAS_M), KURULUM[HAAS_M], program_no=42))
    assert f[1] == "O0042"
    assert h[1] == "O00042"


def test_post_passes_safe_z_and_stock_top():
    """`safe_z` ve `stock_top` yazıcıdaki anlamıyla geçirilir (Ek C2: safe_z > stock_top)."""
    m = replace(ornek(GRBL_M), tool_change_z=None)
    ls = satirlar(post([altin_yol(takim(1))], m, KURULUM[GRBL_M], safe_z=8.0, stock_top=0.0))
    assert "G0 X0. Y0. Z8." in ls
    with pytest.raises(CamError):
        post([altin_yol(takim(1))], m, KURULUM[GRBL_M], safe_z=8.0, stock_top=9.0)


def test_rapid_list_untouched():
    """`G0` satırında F yok (rapid alanı yalnız süre tahmini içindir)."""
    m = replace(ornek(HAAS_M), tool_change_z=None)
    for ln in satirlar(post(iki_takim(), m, KURULUM[HAAS_M])):
        if ln.startswith("G0 "):
            assert " F" not in ln
