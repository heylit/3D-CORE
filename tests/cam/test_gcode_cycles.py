"""SPEC 04 — delik çevrimleri (G81, G83) ve `DrillOp` testleri: K10, K11, K12, K13.

Testler sadece SPEC 04 metninden yazıldı; `cam/gcode/` uygulama kodu okunmadı.

Kanonik açılım (SPEC 04 Teori "Delik çevrimleri"; Smid Bölüm 21–22; LinuxCNC G81/G83):
  G81: G0 (x, y, z_akım) → G0 (x, y, r) → G1 (x, y, z) F → G0 (x, y, z_dön)
  G83: G0 (x, y, z_akım) → G0 (x, y, r) → k = 1..n: (k > 1 ise G0 (x, y, d_{k−1} + c)) →
       G1 (x, y, d_k) F → G0 (x, y, r); sonra G0 (x, y, z_dön)
  d_k = max(r − k·q, z), n = ⌈(r − z)/q⌉; z_dön = z0 (G98) veya r (G99); sıfır boylu hareket yazılmaz.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL, DrillOp, read, write
from cam.model import CamError, Move, MoveType, Tool, ToolKind, Toolpath

G0, G1 = MoveType.RAPID, MoveType.LINEAR
EPS = 0.5e-3 + 1e-9  # mm, 3 basamak yuvarlama sınırı (SPEC 04 Teori)

HOLES3 = [(10.0, 10.0), (20.0, 10.0), (20.0, 20.0)]


def matkap5() -> Tool:
    return Tool(3, "matkap5", ToolKind.DRILL, D=5.0, flute_length=40.0)


def g81(retract: str = "G98", **kw) -> DrillOp:
    """3 delikli G81: z0 = 10, R düzlemi r = 2, dip z = −5, F100."""
    args = dict(
        name="delik",
        tool=matkap5(),
        rpm=2000.0,
        start=(0.0, 0.0, 10.0),
        holes=list(HOLES3),
        z=-5.0,
        r=2.0,
        feed=100.0,
        kind="G81",
        q=None,
        retract=retract,
    )
    args.update(kw)
    return DrillOp(**args)


def g83(retract: str = "G98", **kw) -> DrillOp:
    """K11 verisi: tek delik (5, 5), r = 2, z = −10, q = 3, z0 = 10, F100."""
    args = dict(
        name="gagalama",
        tool=matkap5(),
        rpm=2000.0,
        start=(0.0, 0.0, 10.0),
        holes=[(5.0, 5.0)],
        z=-10.0,
        r=2.0,
        feed=100.0,
        kind="G83",
        q=3.0,
        retract=retract,
    )
    args.update(kw)
    return DrillOp(**args)


def assert_moves(tp: Toolpath, expected: list[tuple[MoveType, tuple[float, float, float]]], tol=1e-12):
    """Hareket tipleri ve uçlar beklenen listeyle aynı; G1'lerde F = 100."""
    assert [m.type for m in tp.moves] == [t for t, _ in expected]
    for i, (m, (_, e)) in enumerate(zip(tp.moves, expected, strict=True)):
        assert np.max(np.abs(np.subtract(m.end, e))) <= tol, (i, m.end, e)
        if m.type is G1:
            assert m.feed == pytest.approx(100.0, abs=0.05 + 1e-9)


def assert_no_zero_length(tp: Toolpath) -> None:
    """SPEC: boyu sıfır olan hareket yazılmaz."""
    pts = tp.points()
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    assert np.all(seg > 1e-9), seg


def with_retract(tp: Toolpath, safe_z: float) -> Toolpath:
    """SPEC 04 Ek B: yazıcı program sonunda güvenli Z'nin altındaysa `G0 Z<safe_z>` ekler;
    okununca bu, yolun son hareketidir."""
    x, y, z = tp.points()[-1]
    if z >= safe_z:
        return tp
    return Toolpath(tp.name, tp.tool, tp.start, [*tp.moves, Move(G0, (x, y, safe_z))], tp.rpm)


def assert_same_path(got: Toolpath, exp: Toolpath, tol: float = EPS) -> None:
    assert [m.type for m in got.moves] == [m.type for m in exp.moves]
    np.testing.assert_allclose(got.points(), exp.points(), rtol=0, atol=tol)
    for g, e in zip(got.moves, exp.moves, strict=True):
        if e.type is G1:
            assert abs(g.feed - e.feed) <= 0.05 + 1e-9


# ---------------------------------------------------------------- K10: G81 açılımı


# G98: dönüş z0 = 10. Elle, delik başına 4 hareket (ilk G0 z_akım = 10'da XY gezisi):
G81_G98 = [
    (G0, (10.0, 10.0, 10.0)),
    (G0, (10.0, 10.0, 2.0)),
    (G1, (10.0, 10.0, -5.0)),
    (G0, (10.0, 10.0, 10.0)),
    (G0, (20.0, 10.0, 10.0)),
    (G0, (20.0, 10.0, 2.0)),
    (G1, (20.0, 10.0, -5.0)),
    (G0, (20.0, 10.0, 10.0)),
    (G0, (20.0, 20.0, 10.0)),
    (G0, (20.0, 20.0, 2.0)),
    (G1, (20.0, 20.0, -5.0)),
    (G0, (20.0, 20.0, 10.0)),
]

# G99: dönüş r = 2. 2. ve 3. delikte z_akım = r → "G0 (x, y, r)" sıfır boylu, yazılmaz:
G81_G99 = [
    (G0, (10.0, 10.0, 10.0)),
    (G0, (10.0, 10.0, 2.0)),
    (G1, (10.0, 10.0, -5.0)),
    (G0, (10.0, 10.0, 2.0)),
    (G0, (20.0, 10.0, 2.0)),
    (G1, (20.0, 10.0, -5.0)),
    (G0, (20.0, 10.0, 2.0)),
    (G0, (20.0, 20.0, 2.0)),
    (G1, (20.0, 20.0, -5.0)),
    (G0, (20.0, 20.0, 2.0)),
]


@pytest.mark.parametrize("retract, expected", [("G98", G81_G98), ("G99", G81_G99)])
@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_g81_canonical_expansion(retract, expected, dialect):
    """K10: 3 delik, G98 ve G99 için hareket listesi elle yazılmış beklenenle aynı; sıfır boy yok."""
    op = g81(retract)
    tp = op.to_toolpath(dialect)
    tp.validate()
    assert tp.tool == op.tool
    assert tp.rpm == pytest.approx(2000.0)
    assert tp.start == pytest.approx((0.0, 0.0, 10.0), abs=1e-12)
    assert_moves(tp, expected)
    assert_no_zero_length(tp)


def test_g81_zero_length_moves_skipped_at_start():
    """K10 ek: başlangıç ilk deliğin üstünde ve z0 = r = 2 → ilk iki G0 sıfır boylu, yazılmaz.

    start (10, 10, 2), delikler (10,10), (20,10), G98 (z_dön = z0 = 2):
      delik 1: G1 (10,10,−5), G0 (10,10,2);  delik 2: G0 (20,10,2), G1 (20,10,−5), G0 (20,10,2).
    """
    op = g81("G98", start=(10.0, 10.0, 2.0), holes=[(10.0, 10.0), (20.0, 10.0)])
    tp = op.to_toolpath(GRBL)
    assert_moves(
        tp,
        [
            (G1, (10.0, 10.0, -5.0)),
            (G0, (10.0, 10.0, 2.0)),
            (G0, (20.0, 10.0, 2.0)),
            (G1, (20.0, 10.0, -5.0)),
            (G0, (20.0, 10.0, 2.0)),
        ],
    )
    assert_no_zero_length(tp)


# ---------------------------------------------------------------- K11: G83 analitik


# r = 2, z = −10, q = 3, c = 0.5 → n = ⌈12/3⌉ = 4; d = −1, −4, −7, −10.
# G1 boyları: 3 (2 → −1), 3.5 (−0.5 → −4), 3.5 (−3.5 → −7), 3.5 (−6.5 → −10) → toplam 13.5 = 12 + 3·0.5.
G83_G98 = [
    (G0, (5.0, 5.0, 10.0)),
    (G0, (5.0, 5.0, 2.0)),
    (G1, (5.0, 5.0, -1.0)),
    (G0, (5.0, 5.0, 2.0)),
    (G0, (5.0, 5.0, -0.5)),
    (G1, (5.0, 5.0, -4.0)),
    (G0, (5.0, 5.0, 2.0)),
    (G0, (5.0, 5.0, -3.5)),
    (G1, (5.0, 5.0, -7.0)),
    (G0, (5.0, 5.0, 2.0)),
    (G0, (5.0, 5.0, -6.5)),
    (G1, (5.0, 5.0, -10.0)),
    (G0, (5.0, 5.0, 2.0)),
    (G0, (5.0, 5.0, 10.0)),  # G98: z_dön = z0 = 10
]


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_g83_analytic(dialect):
    """K11: n = 4, G1 sayısı 4, toplam G1 boyu 13.5 mm (rel 1e-12), son derinlik tam z = −10."""
    tp = g83().to_toolpath(dialect)
    tp.validate()
    g1 = [m for m in tp.moves if m.type is G1]
    assert len(g1) == 4
    assert tp.length({G1}) == pytest.approx(12.0 + 3 * 0.5, rel=1e-12)
    assert g1[-1].end[2] == -10.0  # tam z (max(r − n·q, z) = z)
    assert min(m.end[2] for m in tp.moves) == -10.0  # dibin altına inilmez
    assert_moves(tp, G83_G98)
    assert_no_zero_length(tp)


def test_g83_g99_drops_final_zero_rapid():
    """G99: z_dön = r → son "G0 (x, y, z_dön)" sıfır boylu, yazılmaz: G83_G98 eksi son satır."""
    tp = g83("G99").to_toolpath(GRBL)
    assert_moves(tp, G83_G98[:-1])
    assert_no_zero_length(tp)


def test_g83_last_peck_clamped_to_z():
    """q (r − z)'yi bölmüyorsa: r = 2, z = −9, q = 3 → n = ⌈11/3⌉ = 4, d = −1, −4, −7, max(−10, −9) = −9.

    Toplam G1 boyu = (r − z) + (n − 1)·c = 11 + 3·0.5 = 12.5 mm; son derinlik tam −9.
    """
    tp = g83(z=-9.0).to_toolpath(GRBL)
    g1 = [m for m in tp.moves if m.type is G1]
    assert [m.end[2] for m in g1] == [-1.0, -4.0, -7.0, -9.0]
    assert tp.length({G1}) == pytest.approx(11.0 + 3 * 0.5, rel=1e-12)


def test_g83_peck_clearance_from_dialect():
    """`peck_clearance` dialect'ten gelir: c = 1 → toplam G1 = 12 + 3·1 = 15 mm; geri giriş d_{k−1} + 1."""
    d = dataclasses.replace(GRBL, peck_clearance=1.0)
    tp = g83().to_toolpath(d)
    assert tp.length({G1}) == pytest.approx(15.0, rel=1e-12)
    g0_z = [m.end[2] for m in tp.moves if m.type is G0]
    for zz in (0.0, -3.0, -6.0):  # −1 + 1, −4 + 1, −7 + 1
        assert zz in g0_z


@pytest.mark.parametrize("q, n", [(12.0, 1), (5.0, 3), (1.0, 12), (0.7, 18)])
def test_g83_peck_count_formula(q, n):
    """n = ⌈(r − z)/q⌉, toplam G1 = (r − z) + (n − 1)·c (r − z = 12, c = 0.5)."""
    assert math.ceil(12.0 / q) == n
    tp = g83(q=q).to_toolpath(GRBL)
    g1 = [m for m in tp.moves if m.type is G1]
    assert len(g1) == n
    assert g1[-1].end[2] == -10.0
    assert tp.length({G1}) == pytest.approx(12.0 + (n - 1) * 0.5, rel=1e-9)


# ---------------------------------------------------------------- K12: dil bağımsızlığı


# Ek A kurallarından elle: op başı G0 X Y Z, sonra ilk delik `G98 G81 X Y Z R F`, sonraki delikler
# sadece değişen X / Y, en sonda G80.
FANUC_G81 = """\
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80 G54
N20 T3 M6
N30 S2000 M3
N40 G0 G43 X0. Y0. Z10. H3
N50 G98 G81 X10. Y10. Z-5. R2. F100.
N60 X20.
N70 Y20.
N80 G80
N90 M5
N100 M30
%
"""

# GRBL: çevrim yok, G81_G98 kanonik açılımı modal bastırmayla G0/G1 olarak.
GRBL_G81 = """\
G21 G90 G17 G94
T3
S2000 M3
G0 X0. Y0. Z10.
X10. Y10.
Z2.
G1 Z-5. F100.
G0 Z10.
X20.
Z2.
G1 Z-5.
G0 Z10.
Y20.
Z2.
G1 Z-5.
G0 Z10.
M5
M30
"""


def test_fanuc_writes_g81_cycle_text():
    """K12: Fanuc'ta `G98 G81 ... G80` (Ek A çevrim kuralı)."""
    assert write([g81()], FANUC) == FANUC_G81


def test_fanuc_writes_g99_and_g83_words():
    """K12: G99 dönüşü ve G83'te `R` ile `F` arasında `Q`."""
    ls = write([g81("G99")], FANUC).split("\n")
    assert "N50 G99 G81 X10. Y10. Z-5. R2. F100." in ls
    ls = write([g83()], FANUC).split("\n")
    assert "N50 G98 G83 X5. Y5. Z-10. R2. Q3. F100." in ls
    assert "N60 G80" in ls


def test_grbl_writes_expanded_cycle_text():
    """K12: GRBL'de çevrim yok; açılmış G0/G1 (canned_cycles = False)."""
    out = write([g81()], GRBL)
    assert out == GRBL_G81
    words = set(out.split())
    assert not words & {"G80", "G81", "G83", "G98", "G99"}
    words = set(write([g83()], GRBL).split())
    assert not words & {"G80", "G81", "G83", "G98", "G99"}
    assert not any(w.startswith(("Q", "R")) for w in words)


@pytest.mark.parametrize("make", [g81, g83], ids=["G81", "G83"])
@pytest.mark.parametrize("retract", ["G98", "G99"])
def test_both_dialects_read_back_to_canonical(make, retract):
    """K12: aynı DrillOp, Fanuc (çevrim) ve GRBL (açılmış) yazılıp okununca aynı yol (≤ ε) ve
    `DrillOp.to_toolpath()` ile aynı (Ek B: G99'da sondaki geri çekme dahil)."""
    op = make(retract)
    tools = {3: op.tool}
    (pf,) = read(write([op], FANUC), tools, FANUC)
    (pg,) = read(write([op], GRBL), tools, GRBL)
    pf.validate()
    pg.validate()
    assert_same_path(pf, with_retract(op.to_toolpath(FANUC), op.start[2]))
    assert_same_path(pg, with_retract(op.to_toolpath(GRBL), op.start[2]))
    assert_same_path(pf, pg)
    assert pf.name == pg.name == "T3-1"
    assert pf.rpm == pg.rpm == 2000


def test_reader_cycle_ended_by_motion_word():
    """Ek A: okuyucuda çevrim G80 ile veya G0/G1/G2/G3 ile biter. G98'de z0 = çevrimin ilk satırındaki
    Z konumu (10). İki delik (10,10), (20,10), sonra `G0 Z20.` → (20, 10, 20)."""
    text = (
        "G21 G90 G17 G94\nT3\nS2000 M3\nG0 X0. Y0. Z10.\n"
        "G98 G81 X10. Y10. Z-5. R2. F100.\nX20.\nG0 Z20.\nM5\nM30\n"
    )
    (tp,) = read(text, {3: matkap5()}, FANUC)
    assert_moves(tp, [*G81_G98[:8], (G0, (20.0, 10.0, 20.0))])


def test_drill_then_toolpath_same_tool_merges():
    """Fanuc: G80 sonrası konum son deliğin (x, y, z_dön) noktası (Ek A). Aynı takım ve devirde
    ardından gelen yol tek yol olarak okunur: açılım + G0 (yol başı) + yol hareketleri."""
    op = g81()
    tp2 = Toolpath(
        "sonra", op.tool, (30.0, 30.0, 10.0), rpm=2000.0, moves=[Move(G1, (30.0, 30.0, -1.0), feed=100.0)]
    )
    (got,) = read(write([op, tp2], FANUC), {3: op.tool}, FANUC)
    exp = op.to_toolpath(FANUC)
    exp = Toolpath("bek", op.tool, exp.start, rpm=2000.0, moves=[*exp.moves, Move(G0, tp2.start), *tp2.moves])
    assert_same_path(got, with_retract(exp, 10.0))


# ---------------------------------------------------------------- K13: DrillOp.validate


INVALID = [
    ("rpm = 0", g81, {"rpm": 0.0}),
    ("rpm < 0", g81, {"rpm": -100.0}),
    ("feed = 0", g81, {"feed": 0.0}),
    ("feed < 0", g81, {"feed": -5.0}),
    ("delik yok", g81, {"holes": []}),
    ("z = r", g81, {"z": 2.0}),
    ("z > r", g81, {"z": 3.0}),
    ("r > start z", g81, {"r": 11.0}),
    ("kind G82", g81, {"kind": "G82"}),
    ("kind G73", g83, {"kind": "G73"}),
    ("G83 q yok", g83, {"q": None}),
    ("G83 q = 0", g83, {"q": 0.0}),
    ("G83 q < 0", g83, {"q": -1.0}),
    ("retract G97", g81, {"retract": "G97"}),
    ("retract boş", g83, {"retract": ""}),
]


@pytest.mark.parametrize("make, kw", [c[1:] for c in INVALID], ids=[c[0] for c in INVALID])
def test_drillop_validate_rejects(make, kw):
    """K13: DrillOp.validate() her hata durumunu yakalar; write da reddeder (önce doğrular)."""
    op = make(**kw)
    with pytest.raises(CamError):
        op.validate()
    with pytest.raises(CamError):
        write([op], GRBL)
    with pytest.raises(CamError):
        write([op], FANUC)


def test_drillop_valid_boundaries():
    """Sınır değerler geçerli: r = start z (r ≤ z0), G81'de q verilmese de olur, G99."""
    g81(r=10.0).validate()
    g81("G99").validate()
    g83(q=0.6).validate()


@pytest.mark.parametrize("q", [0.5, 0.4])
def test_g83_clearance_not_less_than_q_raises(q):
    """K13: G83'te c < q değilse (c = 0.5 ≥ q) to_toolpath → CamError (geri giriş dibin altına iner)."""
    op = g83(q=q)
    with pytest.raises(CamError):
        op.to_toolpath(GRBL)
    with pytest.raises(CamError):
        op.to_toolpath(FANUC)


def test_g83_clearance_from_custom_dialect_raises():
    """K13: c dialect'ten: q = 3, peck_clearance = 3 → c ≥ q → CamError."""
    d = dataclasses.replace(FANUC, peck_clearance=3.0)
    with pytest.raises(CamError):
        g83().to_toolpath(d)
