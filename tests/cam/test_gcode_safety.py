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
from tests.reference.gcode_check import safety
from tests.reference.gcode_ref import RefMachine

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW


def freze6() -> Tool:
    return Tool(1, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0)


def freze10() -> Tool:
    return Tool(2, "freze10", ToolKind.FLAT, D=10.0, flute_length=30.0)


def lines_of(text: str) -> list[str]:
    assert text.endswith("\n")
    return text[:-1].split("\n")


# ---------------------------------------------------------------- K1: çok kısa yay


CUT_TYPES = {G1, G2, G3}
SAFE_Z = 5.0  # Ek C1: yol Z−1'de kesiyor; güvenli Z kesme seviyesinin üstünde verilmeli


def cutting(tp: Toolpath) -> list[Move]:
    """Okunan yolun kesme hareketleri (güvenli Z'den iniş ve geri çekme G0'ları hariç)."""
    return [m for m in tp.moves if m.type is not G0]


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
    yazılmamalı. Geri okunan kesme boyu modeldekine 2·ε içinde eşit olmalı."""
    tp = tiny_arc_path(t, 4e-5)
    assert tp.length() == pytest.approx(4e-4, rel=1e-6)
    (got,) = read(write([tp], dialect, safe_z=SAFE_Z), {1: tp.tool}, dialect)
    assert got.length(CUT_TYPES) <= 1e-3
    assert not any(m.type in (G2, G3) for m in got.moves)


def test_tiny_helix_keeps_z():
    """Kısa yay helis ise (Δz = 2) Z hareketi kaybolmaz: okunan son nokta modeldekiyle ≤ ε."""
    tp = tiny_arc_path(G3, 4e-5, dz=2.0)
    (got,) = read(write([tp], GRBL, safe_z=SAFE_Z), {1: tp.tool}, GRBL)
    assert cutting(got)[-1].end == pytest.approx(tp.moves[-1].end, abs=5e-4 + 1e-9)
    assert got.length(CUT_TYPES) == pytest.approx(tp.length(), abs=2e-3)


@pytest.mark.parametrize("t", [G2, G3], ids=["G2", "G3"])
def test_near_full_arc_stays_full_circle(t):
    """Tersi: 2π − 4e-5 rad'lık yay yuvarlanınca tam daire olur; bu doğru (boy farkı ≤ 1e-3 mm)."""
    tp = tiny_arc_path(t, 2 * math.pi - 4e-5)
    assert tp.length() == pytest.approx(20 * math.pi, abs=1e-3)
    (got,) = read(write([tp], GRBL, safe_z=SAFE_Z), {1: tp.tool}, GRBL)
    assert [m.type for m in cutting(got)] == [t]
    assert got.length(CUT_TYPES) == pytest.approx(tp.length(), abs=1e-3)


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


# ---------------------------------------------------------------- Ek C: güvenli Z kesme seviyesinin üstünde
#
# Kaynak: SPEC 04 Ek C. z_kesme = XY'de yer değiştiren (> 1e-9 mm) G1/G2/G3 hareketlerinin başlangıç
# ve bitiş Z'lerinin en yükseği; yalnız Z'de dalma/geri çekme sayılmaz. safe_z (verilen ya da varsayılan)
# z_kesme'den kesin büyük olmalı (C1). stock_top verilirse safe_z > stock_top ve stock_top altında XY G0
# yok (C2). Güvenlik denetimi bağımsız referans tezgâhla (tests/reference/gcode_ref, gcode_check).


def ref_machine(d) -> RefMachine:
    return RefMachine(tool_change=d.tool_change, peck_clearance=d.peck_clearance)


def review_ops() -> list[Toolpath]:
    """İnceleme deneyi (Ek C): başları Z−1 olan, farklı takımlı iki yol; ikisi de Z−1'de XY kesiyor."""
    op1 = Toolpath(
        "op1", freze6(), (0.0, 0.0, -1.0), rpm=10_000.0, moves=[Move(G1, (20.0, 0.0, -1.0), feed=300.0)]
    )
    op2 = Toolpath(
        "op2",
        freze10(),
        (100.0, 100.0, -1.0),
        rpm=1_000.0,
        moves=[Move(G1, (120.0, 100.0, -1.0), feed=300.0)],
    )
    return [op1, op2]


# ------------------------------------------- K15: inceleme deneyi


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_review_case_without_safe_z_raises(dialect):
    """K15: varsayılan güvenli Z = op başlarının en yükseği = −1 = z_kesme → CamError
    (eskiden takım Z−1'de değişip XY'de hızlı gidiyordu)."""
    with pytest.raises(CamError):
        write(review_ops(), dialect)


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_review_case_with_safe_z_is_safe(dialect):
    """K15: aynı yollar safe_z = 5 ile yazılır; referans tezgâhta ham malzeme üstü 0 için güvenlik
    ihlali yok (malzeme içinden XY G0 yok, takım değişimi Z ≥ 0'da, M5 önce, program sonu var)."""
    text = write(review_ops(), dialect, safe_z=5.0)
    tr = ref_machine(dialect).run(text)
    assert safety(tr, z_safe=0.0) == []


# ------------------------------------------- K16: z_kesme


def flat_cut_at_z0() -> Toolpath:
    """Başı (0, 0, 0); Z0'da XY'de kesen G1."""
    return Toolpath(
        "z0", freze6(), (0.0, 0.0, 0.0), rpm=10_000.0, moves=[Move(G1, (10.0, 0.0, 0.0), feed=300.0)]
    )


def test_xy_cut_at_z0_needs_safe_z_above():
    """K16: XY'li G1 Z0'da → safe_z = 0 (= z_kesme) CamError, varsayılan (op başı 0) de CamError;
    safe_z = 0.001 geçer."""
    tp = flat_cut_at_z0()
    with pytest.raises(CamError):
        write([tp], GRBL, safe_z=0.0)
    with pytest.raises(CamError):
        write([tp], GRBL)
    assert "G0 X0. Y0. Z0.001" in write([tp], GRBL, safe_z=0.001)


def test_safe_z_error_message_names_values():
    """K16 / C1: mesaj iki değeri (safe_z ve z_kesme) ve "safe_z" önerisini içerir."""
    tp = Toolpath(
        "m", freze6(), (0.0, 0.0, 2.5), rpm=10_000.0, moves=[Move(G1, (10.0, 0.0, 2.5), feed=300.0)]
    )
    with pytest.raises(CamError, match="safe_z") as e:
        write([tp], GRBL)
    assert "2.5" in str(e.value)


def test_plunge_and_retract_do_not_raise_cut_level():
    """K16: yalnız Z'de dalma (0 → −3) ve geri çekme (−3 → +2, G1) z_kesme'ye girmez:
    z_kesme = −3 (XY'li G1), safe_z = 0 (op başı) geçer."""
    tp = Toolpath(
        "dalma",
        freze6(),
        (0.0, 0.0, 0.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -3.0), feed=100.0),
            Move(G1, (10.0, 0.0, -3.0), feed=300.0),
            Move(G1, (10.0, 0.0, 2.0), feed=100.0),
        ],
    )
    write([tp], GRBL, safe_z=0.0)
    write([tp], GRBL)


def test_rapid_moves_do_not_raise_cut_level():
    """K16: G0 kesme hareketi değildir: yol içinde Z2'de XY G0 olsa da z_kesme = −3."""
    tp = Toolpath(
        "g0",
        freze6(),
        (0.0, 0.0, 2.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -3.0), feed=100.0),
            Move(G1, (10.0, 0.0, -3.0), feed=300.0),
            Move(G0, (10.0, 0.0, 2.0)),
            Move(G0, (30.0, 0.0, 2.0)),
            Move(G1, (30.0, 0.0, -3.0), feed=100.0),
        ],
    )
    write([tp], GRBL, safe_z=2.0)


@pytest.mark.parametrize(
    "z0, z1, z_cut",
    [(-2.0, -2.0, -2.0), (-5.0, -1.0, -1.0), (-1.0, -4.0, -1.0)],
    ids=["yay", "helis_yukari_bitis", "helis_asagi_baslangic"],
)
@pytest.mark.parametrize("t", [G2, G3], ids=["G2", "G3"])
def test_arc_and_helix_ends_count(t, z0, z1, z_cut):
    """K16: yay ve helis uçları sayılır. Yay (10, 0, z0) → (0, ±10, z1), merkez (0, 0), op başı = yay başı:
    z_kesme = max(z0, z1); safe_z = z_kesme → CamError, z_kesme + 0.001 geçer."""
    s = 1.0 if t is G3 else -1.0
    tp = Toolpath(
        "yay",
        freze6(),
        (10.0, 0.0, z0),
        rpm=10_000.0,
        moves=[Move(t, (0.0, s * 10.0, z1), feed=300.0, center=(0.0, 0.0))],
    )
    with pytest.raises(CamError):
        write([tp], GRBL, safe_z=z_cut)
    write([tp], GRBL, safe_z=z_cut + 0.001)


def test_cut_level_over_all_ops():
    """K16: z_kesme tüm yolların en yükseği: ikinci yol Z1'de kesiyorsa safe_z = 1 CamError (ilk yol
    Z−5'te kesse de); 1.001 geçer."""
    op1 = Toolpath(
        "a", freze6(), (0.0, 0.0, -5.0), rpm=10_000.0, moves=[Move(G1, (10.0, 0.0, -5.0), feed=300.0)]
    )
    op2 = Toolpath(
        "b", freze6(), (0.0, 10.0, 1.0), rpm=10_000.0, moves=[Move(G1, (10.0, 10.0, 1.0), feed=300.0)]
    )
    with pytest.raises(CamError):
        write([op1, op2], GRBL, safe_z=1.0)
    write([op1, op2], GRBL, safe_z=1.001)


# ------------------------------------------- K17: stock_top (yollar)


@pytest.mark.parametrize("stock_top", [5.0, 6.0], ids=["esit", "ustte"])
def test_safe_z_not_above_stock_top_raises(stock_top):
    """K17 / C2: safe_z (varsayılan 5) ≤ stock_top → CamError."""
    with pytest.raises(CamError):
        write(deep_ops(), GRBL, stock_top=stock_top)
    with pytest.raises(CamError):
        write(deep_ops(), GRBL, safe_z=5.0, stock_top=stock_top)


@pytest.mark.parametrize("dialect, golden", [(GRBL, DEEP_GRBL), (FANUC, DEEP_FANUC)], ids=["GRBL", "FANUC"])
def test_stock_top_only_checks_text_unchanged(dialect, golden):
    """K17: geçerli stock_top (0 ve 4.999) yalnız denetler; metin Ek B altın metniyle aynı.
    stock_top verilmeyince (None) de aynı (Ek B davranışı)."""
    assert write(deep_ops(), dialect, stock_top=0.0) == golden
    assert write(deep_ops(), dialect, stock_top=4.999) == golden
    assert write(deep_ops(), dialect, stock_top=None) == golden


def rapid_inside(z_g0: float) -> Toolpath:
    """Yol içinde Z = z_g0'da X'te hızlı hareket: Z−2'de kes, z_g0'a çık, G0 ile X30'a git, kes."""
    return Toolpath(
        "ici",
        freze6(),
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -2.0), feed=100.0),
            Move(G1, (10.0, 0.0, -2.0), feed=300.0),
            Move(G0, (10.0, 0.0, z_g0)),
            Move(G0, (30.0, 0.0, z_g0)),
            Move(G1, (30.0, 0.0, -2.0), feed=100.0),
            Move(G1, (40.0, 0.0, -2.0), feed=300.0),
            Move(G0, (40.0, 0.0, 5.0)),
        ],
    )


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_rapid_xy_below_stock_top_in_path_raises(dialect):
    """K17 / C2: stock_top = 0 iken yol içinde Z−0.5'te XY G0 → CamError (op adı, sıra, Z mesajda)."""
    with pytest.raises(CamError, match="ici"):
        write([rapid_inside(-0.5)], dialect, stock_top=0.0)


@pytest.mark.parametrize("z_g0", [0.0, 1.0], ids=["esit", "ustte"])
def test_rapid_xy_at_or_above_stock_top_allowed(z_g0):
    """K17 / C2: XY G0 stock_top'ta (eşit) veya üstündeyse kabul; stock_top verilmezse Z−0.5 de kabul."""
    write([rapid_inside(z_g0)], GRBL, stock_top=0.0)
    write([rapid_inside(-0.5)], GRBL)


def test_rapid_z_only_below_stock_top_allowed():
    """K17 / C2: yalnız Z'de G0 (XY yer değiştirmesi yok) stock_top altında olabilir: Z−0.5'e G0 iniş."""
    tp = Toolpath(
        "inis",
        freze6(),
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G0, (0.0, 0.0, -0.5)),
            Move(G1, (0.0, 0.0, -2.0), feed=100.0),
            Move(G1, (10.0, 0.0, -2.0), feed=300.0),
            Move(G0, (10.0, 0.0, 5.0)),
        ],
    )
    write([tp], GRBL, stock_top=0.0)
