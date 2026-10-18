"""SPEC 04 Ek B — tezgâh güvenliği testleri (inceleme 2026-10-18 bulguları K1, K2, K3).

- K1: yuvarlanınca başlangıçla aynı noktaya düşen çok kısa yay tam daireye dönüşmemeli.
- K2: op geçişlerinde ve program sonunda güvenli Z'ye geri çekme; takım değişimi güvenli Z'de,
  öncesinde M5; XY konumlama güvenli Z'de, iniş ayrı satırda.
- K3: Fanuc'ta G54 ve her takım değişiminden sonra G43 H<n>; okuyucu G43 H'yi denetler.
"""

from __future__ import annotations

import math

import pytest

from cam.gcode import FANUC, GRBL, read, write
from cam.model import CamError, Move, MoveType, Tool, ToolKind, Toolpath

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW


def freze6() -> Tool:
    return Tool(1, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0)


def freze10() -> Tool:
    return Tool(2, "freze10", ToolKind.FLAT, D=10.0, flute_length=30.0)


def lines_of(text: str) -> list[str]:
    assert text.endswith("\n")
    return text[:-1].split("\n")


# ---------------------------------------------------------------- K1: çok kısa yay


def tiny_arc_path(t: MoveType, theta: float, dz: float = 0.0) -> Toolpath:
    """r = 10, merkez (0, 0), başlangıç (10, 0, -1); bitiş θ açısında (G3: +θ, G2: −θ)."""
    s = 1.0 if t is G3 else -1.0
    end = (10 * math.cos(theta), s * 10 * math.sin(theta), -1.0 + dz)
    return Toolpath(
        "kisa", freze6(), (10.0, 0.0, -1.0), rpm=10_000.0, moves=[Move(t, end, feed=300.0, center=(0.0, 0.0))]
    )


@pytest.mark.parametrize("t", [G2, G3], ids=["G2", "G3"])
@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_tiny_arc_not_written_as_full_circle(t, dialect):
    """İnceleme deneyi: r = 10, 0.0004 mm'lik yay. Yuvarlanınca uçlar aynı → tam daire (62.8 mm)
    yazılmamalı. Geri okunan yol boyu modeldekine 2·ε içinde eşit olmalı."""
    tp = tiny_arc_path(t, 4e-5)
    assert tp.length() == pytest.approx(4e-4, rel=1e-6)
    (got,) = read(write([tp], dialect), {1: tp.tool}, dialect)
    assert got.length() <= 1e-3
    assert not any(m.type in (G2, G3) for m in got.moves)


def test_tiny_helix_keeps_z():
    """Kısa yay helis ise (Δz = 2) Z hareketi kaybolmaz: okunan son nokta modeldekiyle ≤ ε."""
    tp = tiny_arc_path(G3, 4e-5, dz=2.0)
    (got,) = read(write([tp], GRBL), {1: tp.tool}, GRBL)
    assert got.moves[-1].end == pytest.approx(tp.moves[-1].end, abs=5e-4 + 1e-9)
    assert got.length() == pytest.approx(tp.length(), abs=2e-3)


@pytest.mark.parametrize("t", [G2, G3], ids=["G2", "G3"])
def test_near_full_arc_stays_full_circle(t):
    """Tersi: 2π − 4e-5 rad'lık yay yuvarlanınca tam daire olur; bu doğru (boy farkı ≤ 1e-3 mm)."""
    tp = tiny_arc_path(t, 2 * math.pi - 4e-5)
    assert tp.length() == pytest.approx(20 * math.pi, abs=1e-3)
    (got,) = read(write([tp], GRBL), {1: tp.tool}, GRBL)
    assert [m.type for m in got.moves] == [t]
    assert got.length() == pytest.approx(tp.length(), abs=1e-3)


# ---------------------------------------------------------------- K2: güvenli Z


def deep_ops() -> list[Toolpath]:
    """op1 T1 Z−1'de biter (geri çekme yok); op2 aynı takım; op3 T2. Op başları Z5."""
    t1, t2 = freze6(), freze10()
    op1 = Toolpath(
        "op1",
        t1,
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -1.0), feed=100.0),
            Move(G1, (20.0, 0.0, -1.0), feed=300.0),
        ],
    )
    op2 = Toolpath(
        "op2",
        t1,
        (40.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (40.0, 0.0, -2.0), feed=100.0),
        ],
    )
    op3 = Toolpath(
        "op3",
        t2,
        (100.0, 100.0, 5.0),
        rpm=8_000.0,
        moves=[
            Move(G1, (100.0, 100.0, -3.0), feed=80.0),
        ],
    )
    return [op1, op2, op3]


# Güvenli Z = op başlarının en yükseği (5). Her geçişte önce `G0 Z5.`; takım değişiminden önce M5;
# program sonunda da M5'ten önce geri çekme.
DEEP_GRBL = """\
G21 G90 G17 G94
T1
S10000 M3
G0 X0. Y0. Z5.
G1 Z-1. F100.
X20. F300.
G0 Z5.
G0 X40. Y0. Z5.
G1 Z-2. F100.
G0 Z5.
M5
T2 M0
S8000 M3
G0 X100. Y100. Z5.
G1 Z-3. F80.
G0 Z5.
M5
M30
"""

DEEP_FANUC = """\
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80 G54
N20 T1 M6
N30 S10000 M3
N40 G0 G43 X0. Y0. Z5. H1
N50 G1 Z-1. F100.
N60 X20. F300.
N70 G0 Z5.
N80 G0 X40. Y0. Z5.
N90 G1 Z-2. F100.
N100 G0 Z5.
N110 M5
N120 T2 M6
N130 S8000 M3
N140 G0 G43 X100. Y100. Z5. H2
N150 G1 Z-3. F80.
N160 G0 Z5.
N170 M5
N180 M30
%
"""


def test_grbl_retracts_between_ops_and_stops_spindle():
    """K2: GRBL'de op geçişi ve takım değişimi güvenli Z'de; T2 M0'dan önce M5."""
    assert write(deep_ops(), GRBL) == DEEP_GRBL


def test_fanuc_retracts_and_applies_length_offset():
    """K2 + K3: Fanuc'ta aynı geri çekmeler, G54 ve her takımdan sonra G43 H<n>."""
    assert write(deep_ops(), FANUC) == DEEP_FANUC


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_no_rapid_xy_below_safe_z_between_ops(dialect):
    """K2 genel denetim: op'lara ait olmayan satırlarda (geçiş) XY değişen hiçbir G0 güvenli Z'nin
    altında değil ve T kelimesi güvenli Z'de (ilk takımda konum bilinmiyor: makine sıfırında).
    Konum, metindeki eksen kelimelerinden izlenir."""
    ops = deep_ops()
    text = write(ops, dialect)
    z = None
    for ln in lines_of(text):
        words = ln.split()
        if words and words[0].startswith("N"):
            words = words[1:]
        ax = {w[0]: float(w[1:]) for w in words if w[0] in "XYZ"}
        if any(w.startswith("T") for w in words):
            assert z is None or z >= 5.0, ln
        if "G0" in words and ("X" in ax or "Y" in ax):
            assert ax.get("Z", z) >= 5.0, ln
        z = ax.get("Z", z)


def test_explicit_safe_z_and_separate_descent():
    """K2: verilen güvenli Z (20) op başından (5) yüksekse XY konumlama Z20'de, iniş ayrı satırda."""
    op1, op2, _ = deep_ops()
    assert lines_of(write([op1, op2], GRBL, safe_z=20.0)) == [
        "G21 G90 G17 G94",
        "T1",
        "S10000 M3",
        "G0 X0. Y0. Z20.",
        "Z5.",
        "G1 Z-1. F100.",
        "X20. F300.",
        "G0 Z20.",
        "G0 X40. Y0. Z20.",
        "Z5.",
        "G1 Z-2. F100.",
        "G0 Z20.",
        "M5",
        "M30",
    ]


def test_safe_z_below_op_start_raises():
    """K2: güvenli Z bir op başından alçaksa CamError (sessiz hata yok)."""
    with pytest.raises(CamError):
        write(deep_ops(), GRBL, safe_z=4.0)


def test_rpm_change_retracts_before_new_speed():
    """K2: aynı takımda sadece devir değişse de önce geri çekme, sonra S."""
    t1 = freze6()
    op1 = Toolpath("a", t1, (0.0, 0.0, 5.0), rpm=10_000.0, moves=[Move(G1, (0.0, 0.0, -1.0), feed=100.0)])
    op2 = Toolpath("b", t1, (10.0, 0.0, 5.0), rpm=12_000.0, moves=[Move(G1, (10.0, 0.0, -1.0), feed=100.0)])
    ls = lines_of(write([op1, op2], GRBL))
    assert ls[ls.index("G1 Z-1. F100.") + 1 : ls.index("G0 X10. Y0. Z5.") + 1] == [
        "G0 Z5.",
        "S12000 M3",
        "G0 X10. Y0. Z5.",
    ]


def test_safe_program_reads_back():
    """Geri çekmeler okunurken sıradan G0 hareketleridir; program okunabilir ve doğrulanır."""
    ops = deep_ops()
    for d in (GRBL, FANUC):
        paths = read(write(ops, d), {1: ops[0].tool, 2: ops[2].tool}, d)
        assert [p.name for p in paths] == ["T1-1", "T2-2"]
        assert paths[0].moves[2].type is G0 and paths[0].moves[2].end == pytest.approx((20, 0, 5))


# ---------------------------------------------------------------- K3: G43 H okuma


def prog(*body: str) -> str:
    return "\n".join(["G21 G90 G17 G94", "T1 M6", "S1000 M3", *body, "M5", "M30"]) + "\n"


def test_reader_accepts_g43_with_matching_h():
    (tp,) = read(prog("G0 G43 X0. Y0. Z5. H1", "G1 Z-1. F100."), {1: freze6()}, FANUC)
    assert tp.start == pytest.approx((0.0, 0.0, 5.0))
    assert tp.moves[0].end == pytest.approx((0.0, 0.0, -1.0))


@pytest.mark.parametrize(
    "line",
    ["G0 G43 X0. Y0. Z5. H2", "G0 G43 X0. Y0. Z5.", "G0 X0. Y0. Z5. H1"],
    ids=["H≠T", "H yok", "G43 yok"],
)
def test_reader_rejects_bad_length_offset(line):
    """K3: yanlış telafi numarası takımı kırar → CamError, satır numarasıyla."""
    with pytest.raises(CamError, match="satır 4"):
        read(prog(line), {1: freze6(), 2: freze10()}, FANUC)
