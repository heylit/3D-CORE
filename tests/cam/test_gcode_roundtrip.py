"""SPEC 04 — gidiş-dönüş `read(write(yollar))` testleri: K4, K5 (ve K2 altın yolun geri okunması).

Testler sadece SPEC 04 metninden yazıldı; `cam/gcode/` uygulama kodu okunmadı.

Toleranslar (SPEC 04 Teori "Sayı biçimi ve tolerans", "Okuyucuda yay doğrulama", K4):
- uç nokta: koordinat başına ε = 0.5·10^-3 mm (3 basamak yuvarlama), + 1e-9 kayan nokta payı;
- ilerleme: 0.5·10^-1 = 0.05 mm/dk (F 1 basamak), + 1e-9;
- yay merkezi: 1e-2 mm. Gerekçe: I, J yuvarlanmış merkezden yazılır (hata ≤ ε√2), okuyucu merkezi
  orta dikmeye izdüşürür; |r0 − r1| ≤ 2.83e-3 iken kiriş L ≥ r/2 için kayma ≈ |r0 − r1|·r/(L/2) ≤ ~1.1e-2
  üst sınırdır, pratikte çok daha küçük. SPEC K4 değeri 1e-2 aynen alındı;
- devir: tam (tam sayı devir yazılır ve okunur).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL, read, write
from cam.model import Move, MoveType, Tool, ToolKind, Toolpath

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
ARCS = (G2, G3)

TOL_END = 0.5e-3 + 1e-9  # mm, koordinat başına
TOL_FEED = 0.05 + 1e-9  # mm/dk
TOL_CENTER = 1e-2  # mm (Öklid uzaklığı)

SEED = 20261018  # sabit tohum: test her çalışmada aynı yolu üretir
N_MOVES = 200

PHI_MIN = 2 * math.asin(0.25)  # kiriş L = 2r·sin(φ/2) ≥ r/2  ⇔  sin(φ/2) ≥ 1/4


def freze6() -> Tool:
    return Tool(1, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0)


def freze10() -> Tool:
    return Tool(2, "freze10", ToolKind.FLAT, D=10.0, flute_length=30.0)


# ---------------------------------------------------------------- rastgele yol üretici


def random_path(seed: int = SEED, n: int = N_MOVES) -> tuple[Toolpath, dict[str, int]]:
    """Sabit tohumlu rastgele takım yolu ve kategori sayaçları.

    - G0 / G1: kutu [-100, 100]² × [-20, 10] içinde yeni nokta; %30 olasılıkla sadece bir eksen değişir.
      Her eksen değişimi ≥ 0.01 mm (yuvarlanınca da farklı kalsın, sıfır boylu hareket olmasın).
    - G2 / G3: önce merkez seçilir (r ∈ [1, 50], başlangıçtan rastgele yönde), bitiş aynı yarıçapta:
      açı farkı φ ∈ [φ_min, 2π − φ_min] (kiriş ≥ r/2) veya tam daire (bitiş XY = başlangıç XY).
      %40 helis (Δz ∈ ±[0.1, 5]).
    - İlerleme: %50 öncekinin aynısı (modal bastırmayı da dener), değilse U(50, 3000).
    """
    rng = np.random.default_rng(seed)
    p = np.array([rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(0, 10)])
    start = tuple(float(v) for v in p)
    feed = float(rng.uniform(50, 3000))
    moves: list[Move] = []
    count = {"G0": 0, "G1": 0, "G2": 0, "G3": 0, "tam_daire": 0, "helis": 0}

    def shifted(old: float, lo: float, hi: float) -> float:
        new = float(rng.uniform(lo, hi))
        if abs(new - old) < 0.01:
            new = old + 1.0
        return new

    for _ in range(n):
        kind = rng.choice(["G0", "G1", "G2", "G3"], p=[0.15, 0.35, 0.25, 0.25])
        if rng.random() >= 0.5:
            feed = float(rng.uniform(50, 3000))
        if kind in ("G0", "G1"):
            q = p.copy()
            lims = [(-100, 100), (-100, 100), (-20, 10)]
            axes = [int(rng.integers(3))] if rng.random() < 0.3 else [0, 1, 2]
            for a in axes:
                q[a] = shifted(p[a], *lims[a])
            t = G0 if kind == "G0" else G1
            moves.append(Move(t, tuple(q), feed=None if t is G0 else feed))
        else:
            r = float(rng.uniform(1, 50))
            a = float(rng.uniform(0, 2 * math.pi))
            c = p[:2] - r * np.array([math.cos(a), math.sin(a)])  # p, merkezden a açısında
            full = rng.random() < 0.15
            if full:
                xy = p[:2].copy()  # tam daire: aynı XY
            else:
                phi = float(rng.uniform(PHI_MIN, 2 * math.pi - PHI_MIN))
                xy = c + r * np.array([math.cos(a + phi), math.sin(a + phi)])
            z = p[2]
            if rng.random() < 0.4:
                dz = float(rng.uniform(0.1, 5.0)) * (1 if rng.random() < 0.5 else -1)
                z = p[2] + dz
                count["helis"] += 1
            q = np.array([xy[0], xy[1], z])
            count["tam_daire"] += int(full)
            t = G2 if kind == "G2" else G3
            moves.append(Move(t, tuple(q), feed=feed, center=(float(c[0]), float(c[1]))))
        count[kind] += 1
        p = np.array(moves[-1].end)

    tp = Toolpath("rastgele", freze6(), start, moves=moves, rpm=12_000.0)
    return tp, count


def test_random_generator_self_check():
    """Üretici kendini doğrular: yol geçerli, 200 hareket, her kategori temsil ediliyor,
    yaylarda kiriş ≥ r/2 veya tam daire, yarıçap 1..50 mm."""
    tp, count = random_path()
    tp.validate()
    assert len(tp.moves) == N_MOVES
    for k in ("G0", "G1", "G2", "G3", "tam_daire", "helis"):
        assert count[k] >= 3, (k, count)
    p0 = np.array(tp.start)
    for m in tp.moves:
        p1 = np.array(m.end)
        if m.type in ARCS:
            r = math.dist(p0[:2], m.center)
            assert 1.0 <= r <= 50.0
            L = math.dist(p0[:2], p1[:2])
            assert L == 0.0 or L >= r / 2 - 1e-9
        else:
            assert np.max(np.abs(p1 - p0)) >= 0.01
        p0 = p1


def assert_paths_close(got: Toolpath, exp: Toolpath) -> None:
    """Hareket tipleri aynı; uç ≤ TOL_END (koordinat başına), F ≤ TOL_FEED, merkez ≤ TOL_CENTER."""
    assert len(got.moves) == len(exp.moves)
    np.testing.assert_allclose(got.start, exp.start, rtol=0, atol=TOL_END)
    for i, (g, e) in enumerate(zip(got.moves, exp.moves, strict=True)):
        assert g.type is e.type, i
        assert np.max(np.abs(np.subtract(g.end, e.end))) <= TOL_END, (i, g.end, e.end)
        if e.type is not G0:
            assert g.feed is not None
            assert abs(g.feed - e.feed) <= TOL_FEED, (i, g.feed, e.feed)
        if e.type in ARCS:
            assert g.center is not None
            assert math.dist(g.center, e.center) <= TOL_CENTER, (i, g.center, e.center)


def with_retract(tp: Toolpath, safe_z: float) -> Toolpath:
    """SPEC 04 Ek B: yazıcı program sonunda güvenli Z'nin (verilmezse op başlarının en yükseği)
    altındaysa `G0 Z<safe_z>` ekler; okununca bu, yolun son hareketidir."""
    x, y, z = tp.points()[-1]
    if round(z, 3) >= round(safe_z, 3):
        return tp
    return Toolpath(tp.name, tp.tool, tp.start, [*tp.moves, Move(G0, (x, y, safe_z))], tp.rpm)


# ---------------------------------------------------------------- K4: gidiş-dönüş


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_random_roundtrip(dialect):
    """K4: 200 hareketlik rastgele yol (G0/G1/G2/G3, helis, tam daire) yazılıp okununca aynı."""
    tp, _ = random_path()
    tools = {1: tp.tool}
    got = read(write([tp], dialect), tools, dialect)
    assert len(got) == 1
    g = got[0]
    g.validate()  # SPEC: çıkan her yol Toolpath.validate()'ten geçer
    assert g.tool == tp.tool
    assert g.rpm == 12_000  # devir tam
    assert g.name == "T1-1"  # Ek A: yol adı T<n>-<k>
    assert_paths_close(g, with_retract(tp, tp.start[2]))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_random_roundtrip_other_seeds(seed):
    """K4 ek: başka sabit tohumlarla da (GRBL) gidiş-dönüş tolerans içinde."""
    tp, _ = random_path(seed)
    got = read(write([tp], GRBL), {1: tp.tool}, GRBL)
    assert len(got) == 1
    got[0].validate()
    assert_paths_close(got[0], with_retract(tp, tp.start[2]))


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_golden_path_roundtrip_exact(dialect):
    """K2 yolu tüm değerleri 3 basamakta tam gösterilebilir: geri okuma 1e-12 içinde aynı."""
    tp = Toolpath(
        "altin",
        freze6(),
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -1.0), feed=100.0),
            Move(G1, (10.0, 0.0, -1.0), feed=300.0),
            Move(G1, (10.0, 10.0, -1.0), feed=300.0),
            Move(G3, (0.0, 10.0, -1.0), feed=300.0, center=(5.0, 10.0)),
            Move(G1, (0.0, 0.0, -1.0), feed=300.0),
            Move(G0, (0.0, 0.0, 5.0)),
        ],
    )
    (g,) = read(write([tp], dialect), {1: tp.tool}, dialect)
    assert [m.type for m in g.moves] == [m.type for m in tp.moves]
    np.testing.assert_allclose(g.points(), tp.points(), rtol=0, atol=1e-12)
    assert g.moves[3].center == pytest.approx((5.0, 10.0), abs=1e-12)
    assert [m.feed for m in g.moves[:5]] == pytest.approx([100.0, 300.0, 300.0, 300.0, 300.0])


# ---------------------------------------------------------------- K5: çok takımlı program


def three_ops() -> list[Toolpath]:
    """İki takım, üç op: op1 ve op2 T1 / 10000, op3 T2 / 8000."""
    t1, t2 = freze6(), freze10()
    op1 = Toolpath(
        "op1",
        t1,
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -1.0), feed=100.0),
            Move(G1, (20.0, 0.0, -1.0), feed=300.0),
            Move(G0, (20.0, 0.0, 5.0)),
        ],
    )
    op2 = Toolpath(
        "op2",
        t1,
        (40.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (40.0, 0.0, -2.0), feed=100.0),
            Move(G2, (50.0, 0.0, -2.0), feed=300.0, center=(45.0, 0.0)),
            Move(G0, (50.0, 0.0, 5.0)),
        ],
    )
    op3 = Toolpath(
        "op3",
        t2,
        (0.0, 30.0, 5.0),
        rpm=8_000.0,
        moves=[
            Move(G1, (0.0, 30.0, -3.0), feed=80.0),
            Move(G1, (30.0, 30.0, -3.0), feed=150.0),
            Move(G0, (30.0, 30.0, 5.0)),
        ],
    )
    return [op1, op2, op3]


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["GRBL", "FANUC"])
def test_multi_tool_program_reads_two_paths(dialect):
    """K5: iki takım, üç op → iki yol. SPEC Arayüz `read`: aynı takım ve devirle art arda gelen op'lar
    tek yol; aradaki op başı `G0` sıradan hareket. Beklenen yol 1 = op1 + [G0 → op2.start] + op2."""
    op1, op2, op3 = three_ops()
    tools = {1: op1.tool, 2: op3.tool}
    got = read(write([op1, op2, op3], dialect), tools, dialect)
    assert len(got) == 2
    p1, p2 = got
    for g in got:
        g.validate()

    assert p1.name == "T1-1" and p2.name == "T2-2"  # Ek A: k çıktı listesindeki sıra
    assert p1.tool == op1.tool and p2.tool == op3.tool
    assert p1.rpm == 10_000 and p2.rpm == 8_000

    merged = Toolpath(
        "bek", op1.tool, op1.start, rpm=10_000.0, moves=[*op1.moves, Move(G0, op2.start), *op2.moves]
    )
    assert_paths_close(p1, merged)
    assert_paths_close(p2, op3)
    assert len(p1.moves) == 3 + 1 + 3


def test_rpm_change_starts_new_path():
    """SPEC Arayüz `read`: `S` değişiminde yeni yol başlar. Üç op, hepsi T1; op2 ve op3 12000 dev/dk
    → iki yol: T1-1 (op1), T1-2 (op2 + G0 → op3.start + op3).
    Ek B: op'lar Z0'da bittiği için her geçişte ve sonda güvenli Z5'e `G0` geri çekme var;
    devir değişiminden önceki geri çekme ilk yola aittir."""
    t1 = freze6()
    op1 = Toolpath("a", t1, (0.0, 0.0, 5.0), rpm=10_000.0, moves=[Move(G1, (0.0, 0.0, 0.0), feed=100.0)])
    op2 = Toolpath("b", t1, (10.0, 0.0, 5.0), rpm=12_000.0, moves=[Move(G1, (10.0, 0.0, 0.0), feed=100.0)])
    op3 = Toolpath("c", t1, (20.0, 0.0, 5.0), rpm=12_000.0, moves=[Move(G1, (20.0, 0.0, 0.0), feed=200.0)])
    got = read(write([op1, op2, op3], GRBL), {1: t1}, GRBL)
    assert [g.name for g in got] == ["T1-1", "T1-2"]
    assert [g.rpm for g in got] == [10_000, 12_000]
    assert_paths_close(got[0], with_retract(op1, 5.0))
    assert_paths_close(
        got[1],
        Toolpath(
            "bek",
            t1,
            op2.start,
            rpm=12_000.0,
            moves=[
                *op2.moves,
                Move(G0, (10.0, 0.0, 5.0)),
                Move(G0, op3.start),
                *op3.moves,
                Move(G0, (20.0, 0.0, 5.0)),
            ],
        ),
    )
