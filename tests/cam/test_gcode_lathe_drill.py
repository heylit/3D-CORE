"""SPEC 21 Ek E3 — torna G-code'da eksenel delme testleri (K12–K15).

Testler sadece SPEC 21 metninden (Ek E3) ve sabit arayüzlerden (cam/model.py, cam.lathe_ops ve cam.torna_ek
imzaları) yazıldı; cam/gcode/lathe.py gövdesi okunmadı. Geometri uydurmadır.

Eksenel yol: takımı DRILL/CONE türü `Tool`, bütün noktalar x = 0, yay yok, css = None. Yazımda `G97`, `X0.` ve
yalnız `Z` satırları; okumada eksenden ayrılan `G0` (tc noktasına `X<2x_tc>`) eksenden çıkıştır, yola
girmez ve yolu kapatır. Okunan eksenel yol (tc = (x_tc, z_tc), P_A = yolun başı):
- start = (0, 0, z_tc): takım değişiminden sonraki ilk `G0 X0.` z_tc'de;
- moves = [G0 → P_A (z_A ≠ z_tc ise)] + özgün hareketler + [G0 Z<z_tc> (son nokta z_tc'de değilse)].
Toleranslar (K10): x 0,25·10⁻³, z 0,5·10⁻³ mm; ilerleme 0,5·10⁻³ mm/dev; yay merkezi 1e-2 mm.
Okuyucu hata mesajında 'satır <n>' (1 tabanlı metin satırı).
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from cam.gcode import fmt
from cam.gcode.lathe import read_lathe, write_lathe
from cam.lathe_ops import TurnCut, face, groove, turn
from cam.model import (
    ARCS,
    CamError,
    CylinderStock,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Tool,
    ToolKind,
    Toolpath,
)

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
TC = (50.0, 50.0)
TOL = 1e-9
TOL_X = 0.25e-3
TOL_Z = 0.5e-3
TOL_F = 0.5e-3
TOL_C = 1e-2

BAR = CylinderStock(D=50.0, zmin=-100.0, zmax=0.0)


def drill(id: int = 5, D: float = 10.0, name: str = "matkap-10", **kw) -> Tool:
    return Tool(id, name, ToolKind.DRILL, D=D, flute_length=40.0, **kw)


def cone(id: int = 6) -> Tool:
    return Tool(id, "punta-90", ToolKind.CONE, D=12.0, flute_length=20.0, tip_angle=90.0)


MATKAP = drill()


def axial(
    tool: Tool = MATKAP, start=(0.0, 0.0, 2.0), moves=None, rpm=800.0, css=None, name="delme"
) -> Toolpath:
    """K12'deki "tam" biçimli yol (q = 10, e = 0,5, cl = 2)."""
    if moves is None:
        moves = [
            Move(G1, (0.0, 0.0, -10.0), feed=0.12),
            Move(G0, (0.0, 0.0, 2.0)),
            Move(G0, (0.0, 0.0, -9.5)),
            Move(G1, (0.0, 0.0, -20.0), feed=0.12),
            Move(G0, (0.0, 0.0, 2.0)),
        ]
    return Toolpath(name, tool, start, moves, rpm=rpm, plane=Plane.ZX, feed_mode=FeedMode.PER_REV, css=css)


def write(ops, spindle="M3", tc=TC) -> str:
    return write_lathe(ops, spindle=spindle, tool_change=tc)


def body(text: str) -> list[str]:
    """Satırlar, baştaki N numarası atılmış."""
    return [re.sub(r"^N\d+ ", "", s) for s in text.splitlines()]


def is_rapid(line: str, word: str) -> bool:
    """`G0 <word>` veya kip sürdüğü için yalnız `<word>`."""
    return re.fullmatch(rf"(G0 )?{re.escape(word)}", line) is not None


# ------------------------------------------------------------------ K12 altın metin

GOLDEN = """%
O0001
N10 G21 G18 G40 G99 G54
N20 G0 X100. Z50.
N30 T0505
N40 G97 S800 M3
N50 G0 X0.
N60 Z2.
N70 G1 Z-10. F0.12
N80 G0 Z2.
N90 Z-9.5
N100 G1 Z-20.
N110 G0 Z2.
N120 Z50.
N130 X100.
N140 M5
N150 M30
%
"""


def test_k12_altin_metin():
    assert write([axial()]).splitlines() == GOLDEN.splitlines()
    assert write([axial()]) == GOLDEN


def test_k12_m4_tek_fark():
    a = GOLDEN.splitlines()
    b = write([axial()], spindle="M4").splitlines()
    assert len(a) == len(b)
    fark = [(x, y) for x, y in zip(a, b, strict=True) if x != y]
    assert fark == [("N40 G97 S800 M3", "N40 G97 S800 M4")]


def check_moves(tp, beklenen):
    assert len(tp.moves) == len(beklenen)
    for m, (t, end, feed) in zip(tp.moves, beklenen, strict=True):
        assert m.type is t
        assert m.end == pytest.approx(end, abs=TOL)
        if feed is None:
            assert m.feed is None
        else:
            assert m.feed == pytest.approx(feed, abs=1e-12)


GOLDEN_MOVES = [
    (G0, (0.0, 0.0, 2.0), None),
    (G1, (0.0, 0.0, -10.0), 0.12),
    (G0, (0.0, 0.0, 2.0), None),
    (G0, (0.0, 0.0, -9.5), None),
    (G1, (0.0, 0.0, -20.0), 0.12),
    (G0, (0.0, 0.0, 2.0), None),
    (G0, (0.0, 0.0, 50.0), None),
]


def test_k12_altin_okuma():
    (tp,) = read_lathe(GOLDEN, {5: MATKAP})
    tp.validate()
    assert tp.tool == MATKAP
    assert tp.name.startswith("T5-")
    assert tp.plane is Plane.ZX and tp.feed_mode is FeedMode.PER_REV
    assert tp.rpm == 800 and tp.css is None
    assert tp.start == pytest.approx((0.0, 0.0, 50.0), abs=TOL)
    check_moves(tp, GOLDEN_MOVES)  # son G0 X100. eksenden çıkış: yola girmiyor
    for p in tp.points():
        assert abs(p[0]) <= TOL and p[1] == 0.0


def test_k12_altin_okuma_spindle_verilmis():
    (tp,) = read_lathe(GOLDEN, {5: MATKAP}, spindle="M3")
    check_moves(tp, GOLDEN_MOVES)
    with pytest.raises(CamError):
        read_lathe(GOLDEN, {5: MATKAP}, spindle="M4")


# ------------------------------------------------------------------ K13 yazıcı


def ltool(id: int) -> LatheTool:
    return LatheTool(id, f"T{id}", LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=93.0, eps_r=55.0)


def lathe_a() -> Toolpath:
    return Toolpath(
        "torna-a",
        ltool(1),
        (21.0, 0.0, 1.0),
        [
            Move(G0, (12.0, 0.0, 1.0)),
            Move(G1, (12.0, 0.0, -10.0), feed=0.2),
            Move(G1, (21.0, 0.0, -10.0), feed=0.2),
            Move(G0, (21.0, 0.0, 1.0)),
        ],
        rpm=2500.0,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=180.0,
    )


def lathe_b() -> Toolpath:
    return Toolpath(
        "torna-b",
        ltool(2),
        (20.0, 0.0, 1.0),
        [
            Move(G1, (20.0, 0.0, -5.0), feed=0.15),
            Move(G1, (24.0, 0.0, -5.0), feed=0.15),
            Move(G0, (24.0, 0.0, 1.0)),
        ],
        rpm=2000.0,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=150.0,
    )


def test_k13_karisik_program_takim_degisimleri():
    L = body(write([lathe_a(), axial(), lathe_b()]))
    assert L[:4] == ["%", "O0001", "G21 G18 G40 G99 G54", "G0 X100. Z50."]
    assert L[-3:] == ["M5", "M30", "%"]
    assert L.count("T0101") == 1 and L.count("T0505") == 1 and L.count("T0202") == 1

    # torna → eksenel: Z<z_tc>, X<2x_tc>, M5, T, G97, X0., Z<z_A>
    i = L.index("T0505")
    assert is_rapid(L[i - 3], "Z50.") and is_rapid(L[i - 2], "X100.") and L[i - 1] == "M5"
    assert L[i + 1] == "G97 S800 M3"
    assert is_rapid(L[i + 2], "X0.") and is_rapid(L[i + 3], "Z2.")

    # eksenel → torna: Z<z_tc>, X<2x_tc>, M5, T, G50, G96, X<2x_A>, Z<z_A>
    j = L.index("T0202")
    assert is_rapid(L[j - 3], "Z50.") and is_rapid(L[j - 2], "X100.") and L[j - 1] == "M5"
    assert L[j + 1] == "G50 S2000" and L[j + 2] == "G96 S150 M3"
    assert is_rapid(L[j + 3], "X40.") and is_rapid(L[j + 4], "Z1.")

    # eksenel bölüm (iş mili satırından geri çekme X100.'e kadar): G96 yok, her satır X0. veya yalnız Z
    bolum = L[i + 2 : j - 2]
    assert bolum, L
    for s in bolum:
        w = s.split()
        assert "G96" not in w and "G50" not in w, s
        assert {k[0] for k in w} <= {"G", "X", "Z", "F"}, s
        assert set(w) & {"G2", "G3", "G32"} == set(), s
        xs = [k for k in w if k[0] == "X"]
        zs = [k for k in w if k[0] == "Z"]
        assert (xs == ["X0."] and not zs) or (not xs and len(zs) == 1), s


def test_k13_eksenel_bolumde_g96_yok_tum_program():
    L = body(write([lathe_a(), axial()]))
    i = L.index("T0505")
    assert all("G96" not in s.split() for s in L[i:])


@pytest.mark.parametrize(
    "tp",
    [
        pytest.param(axial(start=(1e-6, 0.0, 2.0)), id="start-x"),
        pytest.param(axial(start=(-1e-6, 0.0, 2.0)), id="start-x-negatif"),
        pytest.param(axial(start=(5.0, 0.0, 2.0)), id="start-x-5"),
        pytest.param(
            axial(moves=[Move(G1, (1e-6, 0.0, -10.0), feed=0.12), Move(G0, (1e-6, 0.0, 2.0))]), id="hareket-x"
        ),
        pytest.param(
            axial(moves=[Move(G1, (0.0, 0.0, -10.0), feed=0.12), Move(G0, (3.0, 0.0, -10.0))]),
            id="g0-eksen-disi",
        ),
        pytest.param(axial(moves=[Move(G2, (0.0, 0.0, -2.0), feed=0.1, center=(0.0, 0.0))]), id="yay-g2"),
        pytest.param(axial(moves=[Move(G3, (0.0, 0.0, -2.0), feed=0.1, center=(0.0, 0.0))]), id="yay-g3"),
        pytest.param(axial(css=100.0), id="css"),
        pytest.param(axial(tool=Tool(5, "freze", ToolKind.FLAT, D=10.0, flute_length=20.0)), id="flat"),
        pytest.param(axial(tool=Tool(5, "kuresel", ToolKind.BALL, D=10.0, flute_length=20.0)), id="ball"),
        pytest.param(axial(tool=drill(id=0)), id="takim-0"),
        pytest.param(axial(tool=drill(id=100)), id="takim-100"),
    ],
)
def test_k13_yazici_hatalari(tp):
    with pytest.raises(CamError):
        write([tp])


def test_k13_hata_karisik_programda_da():
    with pytest.raises(CamError):
        write([lathe_a(), axial(start=(1e-6, 0.0, 2.0)), lathe_b()])


def test_k13_tc_yolun_altinda():
    with pytest.raises(CamError):
        write([axial()], tc=(50.0, 1.0))  # yolun en büyük z'si 2
    with pytest.raises(CamError):
        write([lathe_a(), axial()], tc=(5.0, 50.0))  # torna yolunun x'i 21'e çıkar


def test_k13_cone_takim_kabul():
    t = cone()
    L = body(write([axial(tool=t)]))
    assert "T0606" in L
    assert "G97 S800 M3" in L


# ------------------------------------------------------------------ K14 okuyucu

HEAD = ["%", "O0001", "G21 G18 G40 G99 G54", "G0 X100. Z50.", "T0505", "G97 S800 M3", "G0 X0.", "Z2."]
TAIL = ["G0 Z50.", "X100.", "M5", "M30", "%"]


def prog(*lines: str, head: list[str] | None = None, tail: list[str] | None = None) -> str:
    return "\n".join((HEAD if head is None else head) + list(lines) + (TAIL if tail is None else tail)) + "\n"


def test_k14_tools_icinde_tool_ve_lathe_tool_birlikte():
    metin = write([lathe_a(), axial(), lathe_b()])
    tools = {1: ltool(1), 5: MATKAP, 2: ltool(2)}
    a, d, b = read_lathe(metin, tools, spindle="M3")
    assert a.tool == ltool(1) and d.tool == MATKAP and b.tool == ltool(2)
    check_moves(d, GOLDEN_MOVES)
    assert d.css is None and d.rpm == 800
    assert b.css == 150 and b.rpm == 2000


def test_k14_u_w_artimsal():
    metin = prog(
        "G1 W-12. F0.12",
        "G0 W12.",
        "U0 W-11.5",
        "G1 W-10.5",
        "G0 W22.",
        head=[
            "%",
            "O0001",
            "G21 G18 G40 G99 G54",
            "G0 X100. Z50.",
            "T0505",
            "G97 S800 M3",
            "G0 X0.",
            "W-48.",
        ],
    )
    (tp,) = read_lathe(metin, {5: MATKAP})
    tp.validate()
    assert tp.start == pytest.approx((0.0, 0.0, 50.0), abs=TOL)
    check_moves(tp, GOLDEN_MOVES)


def test_k14_u_ile_eksene_giris():
    """İlk G0 artımsal U-100. ile X100.'den eksene iner."""
    head = ["%", "O0001", "G21 G18 G40 G99 G54", "G0 X100. Z50.", "T0505", "G97 S800 M3", "G0 U-100.", "Z2."]
    metin = prog("G1 Z-10. F0.12", head=head)
    (tp,) = read_lathe(metin, {5: MATKAP})
    assert tp.start == pytest.approx((0.0, 0.0, 50.0), abs=TOL)
    check_moves(
        tp, [(G0, (0.0, 0.0, 2.0), None), (G1, (0.0, 0.0, -10.0), 0.12), (G0, (0.0, 0.0, 50.0), None)]
    )


def test_k14_cikistan_sonra_is_mili_degisimi_yeni_yol():
    metin = prog(
        "G1 Z-10. F0.12",
        tail=[
            "G0 Z50.",
            "X100.",
            "G97 S900 M3",
            "G0 X0.",
            "Z1.",
            "G1 Z-5. F0.1",
            "G0 Z50.",
            "X100.",
            "M5",
            "M30",
            "%",
        ],
    )
    a, b = read_lathe(metin, {5: MATKAP})
    assert a.rpm == 800 and b.rpm == 900
    check_moves(a, [(G0, (0.0, 0.0, 2.0), None), (G1, (0.0, 0.0, -10.0), 0.12), (G0, (0.0, 0.0, 50.0), None)])
    assert b.start == pytest.approx((0.0, 0.0, 50.0), abs=TOL)
    check_moves(b, [(G0, (0.0, 0.0, 1.0), None), (G1, (0.0, 0.0, -5.0), 0.1), (G0, (0.0, 0.0, 50.0), None)])
    for tp in (a, b):
        assert all(abs(p[0]) <= TOL for p in tp.points())


def test_k14_cone_takim_okunuyor():
    t = cone()
    (tp,) = read_lathe(write([axial(tool=t)]), {6: t})
    assert tp.tool == t
    check_moves(tp, GOLDEN_MOVES)


def test_k14_flat_takim_secilmis():
    flat = Tool(5, "freze", ToolKind.FLAT, D=10.0, flute_length=20.0)
    with pytest.raises(CamError, match=r"satır 5\b"):
        read_lathe(prog("G1 Z-10. F0.12"), {5: flat})


def test_k14_ball_takim_secilmis():
    ball = Tool(5, "kuresel", ToolKind.BALL, D=10.0, flute_length=20.0)
    with pytest.raises(CamError, match=r"satır 5\b"):
        read_lathe(prog("G1 Z-10. F0.12"), {5: ball})


def test_k14_g96_kipinde_baslayan_eksenel_yol():
    head = [
        "%",
        "O0001",
        "G21 G18 G40 G99 G54",
        "G0 X100. Z50.",
        "G50 S2000",
        "G96 S100 M3",
        "T0505",
        "G0 X0.",
        "Z2.",
    ]
    with pytest.raises(CamError, match=r"satır \d+"):
        read_lathe(prog("G1 Z-10. F0.12", head=head), {5: MATKAP})


def test_k14_g96_sonra_t_sonra_g97_degil_g96():
    """T'den sonra iş mili G96'ya geçerse yeni yol G96 kipinde başlar → CamError."""
    head = [
        "%",
        "O0001",
        "G21 G18 G40 G99 G54",
        "G0 X100. Z50.",
        "T0505",
        "G50 S2000",
        "G96 S100 M3",
        "G0 X0.",
    ]
    with pytest.raises(CamError, match=r"satır \d+"):
        read_lathe(prog("Z2.", "G1 Z-10. F0.12", head=head), {5: MATKAP})


def test_k14_t_sonrasi_ilk_g0_eksen_disinda():
    head = ["%", "O0001", "G21 G18 G40 G99 G54", "G0 X100. Z50.", "T0505", "G97 S800 M3", "G0 X10.", "X0."]
    with pytest.raises(CamError, match=r"satır 7\b"):
        read_lathe(prog("Z2.", "G1 Z-10. F0.12", head=head), {5: MATKAP})


# HEAD 8 satır: gövdenin ilk satırı 9
@pytest.mark.parametrize(
    "satir",
    [
        "G2 X0. Z-2. I0. K-2. F0.1",
        "G3 X0. Z-2. I0. K-2. F0.1",
        "G2 X0. Z-2. R2. F0.1",
        "G32 Z-10. F1.5",
        "G1 X2. Z-10. F0.12",
        "G1 X0.002 F0.12",
        "G1 U4. W-5. F0.12",
    ],
)
def test_k14_eksenel_yolda_yasak_hareket(satir):
    with pytest.raises(CamError, match=r"satır 9\b"):
        read_lathe(prog(satir), {5: MATKAP})


def test_k14_yasak_hareket_once_kesmeden_sonra():
    with pytest.raises(CamError, match=r"satır 10\b"):
        read_lathe(prog("G1 Z-10. F0.12", "G1 X1. Z-12."), {5: MATKAP})


@pytest.mark.parametrize("hareket", ["G0 Z60.", "G0 X0.", "G1 Z40. F0.1", "Z45."])
def test_k14_cikistan_sonra_t_olmadan_hareket(hareket):
    # satır 9: G1, 10: G0 Z50., 11: X100. (çıkış), 12: hareket
    metin = prog("G1 Z-10. F0.12", tail=["G0 Z50.", "X100.", hareket, "M5", "M30", "%"])
    with pytest.raises(CamError, match=r"satır 12\b"):
        read_lathe(metin, {5: MATKAP})


def test_k14_cikis_g0_yola_girmiyor_ve_yolu_kapatiyor():
    metin = prog("G1 Z-10. F0.12", tail=["G0 Z50.", "X100.", "M5", "M30", "%"])
    (tp,) = read_lathe(metin, {5: MATKAP})
    assert tp.moves[-1].end == pytest.approx((0.0, 0.0, 50.0), abs=TOL)
    assert all(abs(p[0]) <= TOL for p in tp.points())


# ------------------------------------------------------------------ K15 gidiş-dönüş


def same_point(a, b) -> None:
    assert abs(a[0] - b[0]) <= TOL_X, (a, b)
    assert a[1] == 0.0
    assert abs(a[2] - b[2]) <= TOL_Z, (a, b)


def check_lathe(orig: Toolpath, got: Toolpath, tc=TC) -> None:
    """Torna yolu: K10 ölçütü (SPEC 21 test_gcode_lathe_roundtrip.py ile aynı kural)."""
    got.validate()
    assert got.plane is Plane.ZX and got.feed_mode is FeedMode.PER_REV
    assert got.tool == orig.tool
    assert got.name.startswith(f"T{orig.tool.id}-")
    assert got.rpm == round(orig.rpm)
    assert got.css == (None if orig.css is None else round(orig.css))
    x_tc, z_tc = tc
    xA, _, zA = orig.start
    same_point(got.start, (xA, 0.0, z_tc))
    k = 0
    if fmt(zA, 3) != fmt(z_tc, 3):
        k = 1
        assert got.moves[0].type is G0
        same_point(got.moves[0].end, orig.start)
    n = len(orig.moves)
    assert len(got.moves) >= k + n
    for i, (m0, m1) in enumerate(zip(orig.moves, got.moves[k : k + n], strict=True)):
        assert m1.type is m0.type, (i, m0, m1)
        same_point(m1.end, m0.end)
        if m0.type is G0:
            assert m1.feed is None
        else:
            assert abs(m1.feed - m0.feed) <= TOL_F, (i, m0.feed, m1.feed)
        if m0.type in ARCS:
            assert np.hypot(*np.subtract(m1.center, m0.center)) <= TOL_C, (i, m0.center, m1.center)
    tail = got.moves[k + n :]
    assert len(tail) <= 2
    p = got.moves[k + n - 1].end
    for m in tail:
        assert m.type is G0
        moved = [abs(m.end[0] - p[0]) > 1e-9, abs(m.end[2] - p[2]) > 1e-9]
        assert sum(moved) == 1
        p = m.end
    same_point(p, (x_tc, 0.0, z_tc))


def check_axial(orig: Toolpath, got: Toolpath, tc=TC) -> None:
    """Eksenel yol: K10 toleransları; bütün noktalar x = 0, çıkış G0'ı (X<2x_tc>) yolda yok."""
    got.validate()
    assert got.plane is Plane.ZX and got.feed_mode is FeedMode.PER_REV
    assert got.tool == orig.tool
    assert got.name.startswith(f"T{orig.tool.id}-")
    assert got.rpm == round(orig.rpm)
    assert got.css is None
    for p in got.points():
        assert abs(p[0]) <= TOL and p[1] == 0.0, p
    _, z_tc = tc
    zA = orig.start[2]
    same_point(got.start, (0.0, 0.0, z_tc))
    k = 0
    if fmt(zA, 3) != fmt(z_tc, 3):
        k = 1
        assert got.moves[0].type is G0
        same_point(got.moves[0].end, orig.start)
    n = len(orig.moves)
    assert len(got.moves) >= k + n
    for i, (m0, m1) in enumerate(zip(orig.moves, got.moves[k : k + n], strict=True)):
        assert m1.type is m0.type, (i, m0, m1)
        same_point(m1.end, m0.end)
        if m0.type is G0:
            assert m1.feed is None
        else:
            assert abs(m1.feed - m0.feed) <= TOL_F, (i, m0.feed, m1.feed)
    tail = got.moves[k + n :]
    z_last = orig.moves[-1].end[2] if orig.moves else zA
    if fmt(z_last, 3) == fmt(z_tc, 3):
        assert tail == []
    else:
        assert len(tail) == 1 and tail[0].type is G0
        same_point(tail[0].end, (0.0, 0.0, z_tc))


def cut(a_p: float | None = 2.0, css: float | None = 180.0) -> TurnCut:
    return TurnCut(feed=0.2, rpm=2000.0, css=css, a_p=a_p)


def gtool(id: int) -> LatheTool:
    return LatheTool(
        id, f"K{id}", LatheToolKind.GROOVE, nose_r=0.2, tip=3, kappa_r=90.0, eps_r=90.0, width=3.0
    )


def kirma(tool: Tool) -> Toolpath:
    """ "kirma" biçimi (q = 2, e = 0,3, cl = 1): z_top = −3, uç −9'a üç pasoda."""
    return Toolpath(
        "kirma",
        tool,
        (0.0, 0.0, -2.0),
        [
            Move(G1, (0.0, 0.0, -5.0), feed=0.08),
            Move(G0, (0.0, 0.0, -4.7)),
            Move(G1, (0.0, 0.0, -7.0), feed=0.08),
            Move(G0, (0.0, 0.0, -6.7)),
            Move(G1, (0.0, 0.0, -9.0), feed=0.08),
            Move(G0, (0.0, 0.0, -2.0)),
        ],
        rpm=1200.4,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=None,
    )


def tam(tool: Tool) -> Toolpath:
    """ "tam" biçimi (q = 10, e = 0,5, cl = 2): z_top = −3, uç −23,123'e."""
    return Toolpath(
        "tam",
        tool,
        (0.0, 0.0, -1.0),
        [
            Move(G1, (0.0, 0.0, -13.0614), feed=0.123),
            Move(G0, (0.0, 0.0, -1.0)),
            Move(G0, (0.0, 0.0, -12.5614)),
            Move(G1, (0.0, 0.0, -23.123), feed=0.123),
            Move(G0, (0.0, 0.0, -1.0)),
        ],
        rpm=799.6,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=None,
    )


def test_k15_spec20_ve_eksenel_yollar_gidis_donus():
    ops = [
        face(BAR, ltool(1), cut(), z_face=-3.0),
        turn(BAR, ltool(2), cut(), x_final=20.0, z_end=-30.0),
        tam(drill(5)),
        kirma(cone(6)),
        groove(BAR, gtool(7), cut(a_p=None), z_left=-20.0, z_right=-12.0, x_top=25.0, x_bottom=20.0),
    ]
    tools = {tp.tool.id: tp.tool for tp in ops}
    got = read_lathe(write(ops), tools, spindle="M3")
    assert len(got) == len(ops)
    check_lathe(ops[0], got[0])
    check_lathe(ops[1], got[1])
    check_axial(ops[2], got[2])
    check_axial(ops[3], got[3])
    check_lathe(ops[4], got[4])


def test_k15_ayni_matkap_iki_eksenel_yol_farkli_devir():
    """Aynı takım, farklı devir: taret dönmez, sadece iş mili satırı; okunan iki yol da x = 0'da."""
    t = drill(5)
    a = tam(t)
    b = Toolpath(
        "tam-2",
        t,
        (0.0, 0.0, 1.0),
        [Move(G1, (0.0, 0.0, -4.0), feed=0.1), Move(G0, (0.0, 0.0, 1.0))],
        rpm=1500.0,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=None,
    )
    metin = write([a, b])
    assert body(metin).count("T0505") == 1
    got = read_lathe(metin, {5: t})
    assert len(got) == 2
    check_axial(a, got[0])
    assert got[1].rpm == 1500
    for tp in got:
        assert all(abs(p[0]) <= TOL for p in tp.points())


def test_k15_spec40_delme_ve_punta_yollari():
    torna_ek = pytest.importorskip("cam.torna_ek")
    DrillCut = torna_ek.DrillCut
    m10 = drill(5, tip_angle=118.0)
    m6 = drill(8, D=6.0, name="matkap-6", tip_angle=118.0)
    ops = [
        face(BAR, ltool(1), cut(), z_face=-3.0),
        torna_ek.lathe_center(BAR, cone(6), DrillCut(feed=0.05, rpm=1200.0), z_top=-3.0, d_c=6.0),
        torna_ek.lathe_drill(
            BAR, m10, DrillCut(feed=0.1, rpm=900.0, peck=8.0, mode="tam"), z_top=-3.0, z_bottom=-28.0
        ),
        torna_ek.lathe_drill(
            BAR,
            m6,
            DrillCut(feed=0.08, rpm=1400.0, peck=4.0, mode="kirma", retract=0.3),
            z_top=-3.0,
            z_bottom=-15.0,
            full_diameter=True,
        ),
        turn(BAR, ltool(2), cut(), x_final=20.0, z_end=-30.0),
    ]
    tools = {tp.tool.id: tp.tool for tp in ops}
    got = read_lathe(write(ops), tools, spindle="M3")
    assert len(got) == len(ops)
    check_lathe(ops[0], got[0])
    for i in (1, 2, 3):
        check_axial(ops[i], got[i])
    check_lathe(ops[4], got[4])
