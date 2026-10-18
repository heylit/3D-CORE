"""SPEC 03 — cam/ops2d.py testleri (K10–K16), Ek A (K17–K19) ve SPEC 03b (K5–K8: r < s ≤ D cep).

Testler sadece SPEC 03 "Arayüz" bölümündeki imzalardan yazıldı; uygulama kodu okunmadı.
Takım yolu geometrisi (G1 doğru, G2/G3 yay, merkez mutlak XY) ve bölge sınırına uzaklık
tests/cam/ref2d.py'de analitik olarak, cam.geom2d'den bağımsız hesaplanır.

Kaynaklar:
- Paso derinlikleri: n = ⌈H / a_p⌉, z_i = z_top − i·H/n (SPEC 03 "Paso derinlikleri").
- Tırmanma frezeleme (M3, malzeme ilerlemenin sağında): dış kontur CW, iç kontur CCW
  (Sandvik Coromant, Metal Cutting Technical Guide). Yön işareti: yönlü alan (shoelace), CW < 0.
- Takım yarıçapı telafisi: merkez yolu R ± r (daire), dikdörtgen dış ofset çevresi 2(a+b) + 2πr.
- Erişilemeyen köşe kalanı: dışbükey 90° köşede takım merkezi (x0+r, y0+r)'den köşeye yaklaşamaz;
  x < x0+r, y < y0+r ve (x0+r, y0+r)'ye uzaklığı > r olan noktalar (alan r² − πr²/4) hariç tutulur.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, MoveType, Stock, Tool, ToolKind, Toolpath
from cam.ops2d import Cut, contour, depths, face, pocket
from cam.profile import Line, Profile, Region
from cam.rest import COVER_TOL
from tests.cam.ref2d import (
    Egriler,
    RefBolge,
    curves_of,
    cut_depths,
    cutting_moves,
    grid,
    moves_of,
    sample_xy,
    shoelace,
)

D = 6.0
r = D / 2


def make_tool(kind: ToolKind = ToolKind.FLAT) -> Tool:
    """Ø6 düz parmak freze (uydurma)."""
    return Tool(id=1, name="freze6", kind=kind, D=D, flute_length=20.0)


def make_cut(**kw) -> Cut:
    """Varsayılan: z 0 → −5, a_p 2 (n = ⌈5/2⌉ = 3 paso), z_safe 10, clearance 1."""
    args = dict(z_top=0.0, z_bottom=-5.0, a_p=2.0, feed=800.0, plunge_feed=200.0, rpm=10_000.0, z_safe=10.0)
    args.update(kw)
    return Cut(**args)


# ---------------------------------------------------------------- test bölgeleri (kendi tanımımız)

RECT = ("poly", [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)])
ISLAND = ("circle", (30.0, 20.0), 6.0)
L_SHAPE = ("poly", [(0.0, 0.0), (50.0, 0.0), (50.0, 20.0), (20.0, 20.0), (20.0, 45.0), (0.0, 45.0)])
CIRCLE = ("circle", (0.0, 0.0), 20.0)
DUMBBELL = (
    "poly",
    [
        (0.0, 0.0),
        (20.0, 0.0),
        (20.0, 8.0),
        (30.0, 8.0),
        (30.0, 0.0),
        (50.0, 0.0),
        (50.0, 20.0),
        (30.0, 20.0),
        (30.0, 12.0),
        (20.0, 12.0),
        (20.0, 20.0),
        (0.0, 20.0),
    ],
)  # köprü genişliği 4 < D: takım köprüye giremez, iki ayrı cep


def to_profile(ring) -> Profile:
    if ring[0] == "poly":
        return Profile.polygon(ring[1])
    return Profile.circle(ring[1], ring[2])


def to_region(ref: RefBolge) -> Region:
    return Region(to_profile(ref.outer), [to_profile(h) for h in ref.holes])


POCKETS = {
    "dikdortgen_ada": RefBolge(RECT, [ISLAND]),
    "L": RefBolge(L_SHAPE),
    "daire": RefBolge(CIRCLE),
    "halter": RefBolge(DUMBBELL),
}


def corner_unreachable(P: np.ndarray, corners) -> np.ndarray:
    """Dışbükey 90° köşelerde takımın erişemediği nokta maskesi.

    corners: [(x0, y0, sx, sy)] — köşe ve bölgenin içine doğru eksen yönleri (±1).
    Yerel u = (x − x0)·sx, v = (y − y0)·sy; u < r, v < r ve |(u, v) − (r, r)| > r → erişilemez.
    """
    mask = np.zeros(len(P), dtype=bool)
    for x0, y0, sx, sy in corners:
        u = (P[:, 0] - x0) * sx
        v = (P[:, 1] - y0) * sy
        mask |= (u < r) & (v < r) & (np.hypot(u - r, v - r) > r)
    return mask


RECT_CORNERS = [(0.0, 0.0, 1, 1), (60.0, 0.0, -1, 1), (60.0, 40.0, -1, -1), (0.0, 40.0, 1, -1)]


def pass_loop_area(tp: Toolpath, z: float) -> float:
    """Bir pasodaki yatay kesme hareketlerinin örnek noktalarıyla yönlü alan (shoelace)."""
    pts = np.vstack([p.sample(0.5)[:, :2] for p in cutting_moves(tp, z)])
    return shoelace(pts)


def pass_length(tp: Toolpath, z: float) -> float:
    """Bir pasodaki yatay kesme hareketlerinin toplam boyu (yay: R·Δθ)."""
    return sum(p.length_xy() for p in cutting_moves(tp, z))


# ---------------------------------------------------------------- K10: depths


def test_depths_exact_division():
    """H = 10, a_p = 2,5 → n = 4: −2,5, −5, −7,5, −10."""
    assert depths(0.0, -10.0, 2.5) == pytest.approx([-2.5, -5.0, -7.5, -10.0], abs=1e-12)


def test_depths_inexact_division_equal_steps():
    """H = 10, a_p = 3 → n = ⌈3,33⌉ = 4, eşit adım H/n = 2,5 (3'lük 3 paso + 1'lik kalan DEĞİL)."""
    assert depths(0.0, -10.0, 3.0) == pytest.approx([-2.5, -5.0, -7.5, -10.0], abs=1e-12)


def test_depths_last_is_exactly_bottom():
    """H = 3, a_p = 0,7 → n = ⌈4,29⌉ = 5, adım 0,6: 1,4, 0,8, 0,2, −0,4, −1,0; son değer tam z_bottom (==)."""
    z = depths(2.0, -1.0, 0.7)
    assert z == pytest.approx([1.4, 0.8, 0.2, -0.4, -1.0], abs=1e-12)
    assert z[-1] == -1.0


@pytest.mark.parametrize("z_top, z_bottom, a_p", [(0.0, -10.0, 20.0), (5.0, 0.0, 5.0), (0.3, -0.9, 0.11)])
def test_depths_properties(z_top, z_bottom, a_p):
    """Genel: n = ⌈H/a_p⌉ eleman, kesin azalan, adımlar eşit ve ≤ a_p, son = z_bottom."""
    z = depths(z_top, z_bottom, a_p)
    H = z_top - z_bottom
    n = math.ceil(H / a_p)
    assert len(z) == n
    assert z[-1] == z_bottom
    steps = np.diff([z_top, *z])
    assert np.all(steps < 0)
    assert np.allclose(-steps, H / n, atol=1e-12)
    assert np.all(-steps <= a_p + 1e-12)


# ---------------------------------------------------------------- K11: face

FACE_STOCK = Stock(xmin=0.0, ymin=0.0, zmin=-20.0, xmax=100.0, ymax=50.0, zmax=0.0)
FACE_S = 5.5


def face_path() -> Toolpath:
    """100×50 üst yüz, z 0 → −1, a_p 0,6 (2 paso: −0,5, −1), s = 5,5 (≤ D), clearance 1."""
    cut = make_cut(z_top=0.0, z_bottom=-1.0, a_p=0.6, stepover=FACE_S, clearance=1.0)
    return face(FACE_STOCK, make_tool(), cut)


def x_rows(tp: Toolpath, z: float):
    """X'e paralel kesme hareketleri (Δy = 0, Δx ≠ 0)."""
    return [
        p for p in cutting_moves(tp, z) if abs(p.p1[1] - p.p0[1]) < 1e-12 and abs(p.p1[0] - p.p0[0]) > 1e-12
    ]


def test_face_rows():
    """m = ⌈50/5,5⌉ + 1 = 11 sıra, y = 0, 5, …, 50 (aralık 50/10 = 5 ≤ s); her sıra x ∈ [−4, 104]
    (x_min − r − clearance, x_max + r + clearance); ardışık sıralar zıt yönde (zigzag)."""
    tp = face_path()
    m = math.ceil(50.0 / FACE_S) + 1
    for z in depths(0.0, -1.0, 0.6):
        rows = x_rows(tp, z)
        ys = sorted({round(float(p.p0[1]), 9) for p in rows})
        assert len(ys) == m
        assert np.allclose(ys, np.linspace(0.0, 50.0, m), atol=1e-9)
        assert np.all(np.diff(ys) <= FACE_S + 1e-9)
        for y in ys:
            xs = [x for p in rows if abs(p.p0[1] - y) < 1e-9 for x in (p.p0[0], p.p1[0])]
            assert min(xs) == pytest.approx(-r - 1.0, abs=1e-9)
            assert max(xs) == pytest.approx(100.0 + r + 1.0, abs=1e-9)
        # zigzag: sıraların yönü sırayla değişir
        signs = [np.sign(p.p1[0] - p.p0[0]) for p in rows]
        y_order = [float(p.p0[1]) for p in rows]
        assert y_order == sorted(y_order)
        firsts = []
        for s, y in zip(signs, y_order, strict=True):
            if not firsts or abs(firsts[-1][1] - y) > 1e-9:
                firsts.append((s, y))
        assert all(firsts[i][0] == -firsts[i + 1][0] for i in range(len(firsts) - 1))


def test_face_cut_length_closed_form():
    """Paso başına kesme boyu = m·(L_x + 2r + 2c) + (y_max − y_min) = 11·108 + 50 = 1238 mm."""
    tp = face_path()
    m = math.ceil(50.0 / FACE_S) + 1
    expected = m * (100.0 + 2 * r + 2 * 1.0) + 50.0
    for z in depths(0.0, -1.0, 0.6):
        assert pass_length(tp, z) == pytest.approx(expected, rel=1e-9)


def test_face_covers_top_surface():
    """Son pasoda (z_bottom) üst yüzdeki her ızgara noktası bir kesme hareketine ≤ r + 1e-9 uzaklıkta."""
    tp = face_path()
    curves = curves_of(cutting_moves(tp, -1.0))
    P = grid(0.0, 100.0, 0.0, 50.0, 40, 40)
    assert np.max(curves.distance(P)) <= r + 1e-9


# ---------------------------------------------------------------- K12: contour

CC, CR = (50.0, 40.0), 20.0  # daire konturu merkezi ve yarıçapı


@pytest.mark.parametrize("side, Rexp", [("dis", CR + r), ("ic", CR - r)])
def test_contour_circle_radius(side, Rexp):
    """Daire konturunda merkez yolu R ± r = 23 / 17 yarıçaplı yay(lar), merkez (50, 40);
    boy 2π(R ± r) her pasoda."""
    cut = make_cut()
    tp = contour(Profile.circle(CC, CR), make_tool(), cut, side)
    zs = depths(cut.z_top, cut.z_bottom, cut.a_p)
    assert cut_depths(tp) == pytest.approx(zs, abs=1e-12)
    for z in zs:
        mv = cutting_moves(tp, z)
        assert mv
        for p in mv:
            assert p.type in (MoveType.ARC_CW, MoveType.ARC_CCW)
            assert math.hypot(p.center[0] - CC[0], p.center[1] - CC[1]) <= 1e-9
            for q in (p.p0, p.p1):
                assert math.hypot(q[0] - CC[0], q[1] - CC[1]) == pytest.approx(Rexp, abs=1e-9)
        assert pass_length(tp, z) == pytest.approx(2 * math.pi * Rexp, rel=1e-9)


@pytest.mark.parametrize(
    "side, Lexp",
    [
        ("dis", 2 * (40.0 + 20.0) + 2 * math.pi * r),  # 4 kenar + 4 çeyrek yay
        ("ic", 2 * (40.0 - 2 * r + 20.0 - 2 * r)),  # keskin köşeli 34×14
        ("uzerinde", 2 * (40.0 + 20.0)),  # ofsetsiz
    ],
)
def test_contour_rectangle_length(side, Lexp):
    """40×20 dikdörtgen konturu: her pasoda yol boyu kapalı form; yol ∂Ω'ya |ofset| uzaklıkta."""
    cut = make_cut()
    tp = contour(Profile.rectangle(0.0, 0.0, 40.0, 20.0), make_tool(), cut, side)
    zs = depths(cut.z_top, cut.z_bottom, cut.a_p)
    assert cut_depths(tp) == pytest.approx(zs, abs=1e-12)
    bnd = Egriler()
    bnd.polygon([(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)])
    dexp = 0.0 if side == "uzerinde" else r
    for z in zs:
        assert pass_length(tp, z) == pytest.approx(Lexp, rel=1e-9)
        pts = sample_xy(cutting_moves(tp, z))
        assert np.max(np.abs(bnd.distance(pts) - dexp)) <= 1e-9


@pytest.mark.parametrize("shape", ["daire", "dikdortgen"])
@pytest.mark.parametrize(
    "side, climb, sign",
    [
        ("dis", True, -1),
        ("ic", True, +1),
        ("dis", False, +1),
        ("ic", False, -1),
    ],
)
def test_contour_direction(shape, side, climb, sign):
    """Tırmanma (M3, malzeme sağda): dış kontur CW (yönlü alan < 0), iç kontur CCW (> 0);
    climb=False tersine çevirir. Profil CW verilse de sonuç aynı (yön kurala göre seçilir)."""
    prof = Profile.circle(CC, CR) if shape == "daire" else Profile.rectangle(0.0, 0.0, 40.0, 20.0)
    cut = make_cut()
    for p in (prof, prof.reversed()):
        tp = contour(p, make_tool(), cut, side, climb=climb)
        for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
            assert np.sign(pass_loop_area(tp, z)) == sign


def test_contour_open_profile_on():
    """Açık profil (0,0)→(30,0)→(30,20), "uzerinde": her pasoda yol profilin kendisi, boy 30 + 20 = 50."""
    prof = Profile([Line((0.0, 0.0), (30.0, 0.0)), Line((30.0, 0.0), (30.0, 20.0))], closed=False)
    cut = make_cut()
    tp = contour(prof, make_tool(), cut, "uzerinde")
    ref = Egriler()
    ref.line((0.0, 0.0), (30.0, 0.0))
    ref.line((30.0, 0.0), (30.0, 20.0))
    for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
        assert pass_length(tp, z) == pytest.approx(50.0, rel=1e-9)
        assert np.max(ref.distance(sample_xy(cutting_moves(tp, z)))) <= 1e-9


# ---------------------------------------------------------------- K13: cep çakma yok


def pocket_path(name: str, s: float, **cut_kw) -> Toolpath:
    kw = dict(z_top=0.0, z_bottom=-2.0, a_p=5.0, stepover=s)
    kw.update(cut_kw)
    return pocket(to_region(POCKETS[name]), make_tool(), make_cut(**kw))


@pytest.mark.parametrize(
    "name, s",
    [
        ("dikdortgen_ada", 3.0),
        ("L", 3.0),
        ("daire", 2.7),
        ("halter", 3.0),
        # SPEC 03b K6: r < s ≤ D
        ("dikdortgen_ada", 0.7 * D),
        ("dikdortgen_ada", D),
        ("L", 0.6 * D),
        ("L", D),
        ("daire", 0.95 * D),
        ("halter", D),
    ],
)
def test_pocket_no_gouge(name, s):
    """K13 (ve SPEC 03b K6, r < s ≤ D): tüm kesme hareketleri (G1 dalma ve bağlantılar dahil)
    üzerindeki örnek noktalar: dist(p, ∂Ω) ≥ r − 1e-9 ve p ∈ Ω (adanın dışında)."""
    ref = POCKETS[name]
    tp = pocket_path(name, s)
    parts = [p for p in moves_of(tp) if p.type is not MoveType.RAPID]
    assert parts
    P = sample_xy(parts, step=0.25)
    assert np.min(ref.boundary().distance(P)) >= r - 1e-9
    assert np.all(ref.contains(P))


def test_pocket_no_gouge_multi_pass():
    """Aynı kontrol 3 pasoda (z 0 → −5, a_p 2) adalı cep için."""
    ref = POCKETS["dikdortgen_ada"]
    tp = pocket_path("dikdortgen_ada", 3.0, z_bottom=-5.0, a_p=2.0)
    parts = [p for p in moves_of(tp) if p.type is not MoveType.RAPID]
    P = sample_xy(parts, step=0.25)
    assert np.min(ref.boundary().distance(P)) >= r - 1e-9
    assert np.all(ref.contains(P))


def test_pocket_dumbbell_two_islands_of_work():
    """Köprü (w = 4 < D) takıma kapalı: köprünün ortası (25, 10) hiçbir kesme hareketinin r yakınında
    değil, her iki karenin merkezi (10,10), (40,10) ise işleniyor."""
    tp = pocket_path("halter", 3.0)
    curves = curves_of(cutting_moves(tp, -2.0))
    dist = curves.distance(np.array([(25.0, 10.0), (10.0, 10.0), (40.0, 10.0)]))
    assert dist[0] > r
    assert dist[1] <= r and dist[2] <= r


# ---------------------------------------------------------------- K14: cep kalan malzeme yok


def assert_covered(tp: Toolpath, P: np.ndarray, z: float, tol: float = r + 1e-9) -> None:
    curves = curves_of(cutting_moves(tp, z))
    dist = curves.distance(P)
    worst = int(np.argmax(dist))
    assert dist[worst] <= tol, f"kalan malzeme: {P[worst]} uzaklık {dist[worst]}"


@pytest.mark.parametrize("s", [0.4 * D, 0.5 * D])
def test_pocket_rectangle_full_coverage(s):
    """60×40 dikdörtgen cep, s = 0,4D ve 0,5D (Ek A1: cepte s ≤ r): erişilemez köşe kalanları dışında
    her ızgara noktası bir kesme hareketine ≤ r + 1e-9."""
    cut = make_cut(z_top=0.0, z_bottom=-2.0, a_p=5.0, stepover=s)
    tp = pocket(Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), make_tool(), cut)
    P = grid(0.0, 60.0, 0.0, 40.0, 40, 40)
    P = P[~corner_unreachable(P, RECT_CORNERS)]
    assert_covered(tp, P, -2.0)


def test_pocket_circle_full_coverage():
    """R = 20 dairesel cep, s = 0,5D = r (Ek A1 sınırı): halkalar 17, 14, …; daire içindeki
    (merkez dahil) her ızgara noktası ≤ r + 1e-9."""
    tp = pocket_path("daire", 0.5 * D)
    P = grid(-20.0, 20.0, -20.0, 20.0, 40, 40)
    P = P[np.hypot(P[:, 0], P[:, 1]) <= 20.0]
    assert_covered(tp, P, -2.0)


def test_pocket_island_full_coverage():
    """60×40 cep, (30,20) merkezli R = 6 ada, s = 0,5D: adanın dışındaki ve köşe kalanları dışındaki
    her ızgara noktası ≤ r + 1e-9 (ada çevresi içbükey olmadığından tamamen erişilebilir)."""
    tp = pocket_path("dikdortgen_ada", 0.5 * D)
    P = grid(0.0, 60.0, 0.0, 40.0, 40, 40)
    keep = (np.hypot(P[:, 0] - 30.0, P[:, 1] - 20.0) >= 6.0) & ~corner_unreachable(P, RECT_CORNERS)
    assert_covered(tp, P[keep], -2.0)


def test_pocket_island_coverage_every_pass():
    """Çok pasolu adalı cepte her pasoda aynı kapsama (paso başına aynı halkalar)."""
    tp = pocket_path("dikdortgen_ada", 0.5 * D, z_bottom=-5.0, a_p=2.0)
    P = grid(0.0, 60.0, 0.0, 40.0, 30, 30)
    keep = (np.hypot(P[:, 0] - 30.0, P[:, 1] - 20.0) >= 6.0) & ~corner_unreachable(P, RECT_CORNERS)
    for z in depths(0.0, -5.0, 2.0):
        assert_covered(tp, P[keep], z)


# ---------------------------------------------------------------- K15: hareket kuralları


def _pocket_case(name: str, s: float, climb: bool = True) -> tuple[Toolpath, Cut]:
    c = make_cut(stepover=s)
    return pocket(to_region(POCKETS[name]), make_tool(), c, climb=climb), c


def _face_case() -> tuple[Toolpath, Cut]:
    c = make_cut(z_top=0.0, z_bottom=-1.0, a_p=0.6, stepover=FACE_S)
    return face(FACE_STOCK, make_tool(), c), c


def _contour_case(side: str) -> tuple[Toolpath, Cut]:
    c = make_cut()
    if side == "dis":
        return contour(Profile.rectangle(0.0, 0.0, 40.0, 20.0), make_tool(), c, "dis"), c
    return contour(Profile.circle(CC, CR), make_tool(), c, "ic", climb=False), c


# Kural kontrolü için örnek yollar: yüz alma, kontur (dış/iç), adalı, halter ve L cep (çok pasolu);
# SPEC 03b K6: r < s ≤ D cepler de aynı kurallara uyar.
PATH_BUILDERS = {
    "face": _face_case,
    "kontur_dis": lambda: _contour_case("dis"),
    "kontur_ic": lambda: _contour_case("ic"),
    "cep_ada": lambda: _pocket_case("dikdortgen_ada", 3.0),
    "cep_halter": lambda: _pocket_case("halter", 3.0),
    "cep_L": lambda: _pocket_case("L", 3.0),
    "cep_ada_0.7D": lambda: _pocket_case("dikdortgen_ada", 0.7 * D),
    "cep_ada_D": lambda: _pocket_case("dikdortgen_ada", D),
    "cep_L_0.6D": lambda: _pocket_case("L", 0.6 * D),
    "cep_L_D_konvansiyonel": lambda: _pocket_case("L", D, climb=False),
    "cep_daire_0.95D": lambda: _pocket_case("daire", 0.95 * D),
    "cep_halter_D": lambda: _pocket_case("halter", D),
}


class _LazyPaths(dict):
    """Yollar ilk istendiklerinde (test gövdesinde) üretilir: üretim hatası o testin hatası olur."""

    def __missing__(self, name: str) -> tuple[Toolpath, Cut]:
        self[name] = PATH_BUILDERS[name]()
        return self[name]


@pytest.fixture(scope="module")
def paths():
    return _LazyPaths()


PATH_NAMES = list(PATH_BUILDERS)


@pytest.mark.parametrize("name", PATH_NAMES)
def test_path_starts_and_ends_at_safe_z(paths, name):
    tp, cut = paths[name]
    assert tp.start[2] == pytest.approx(cut.z_safe, abs=1e-12)
    assert tp.moves
    assert tp.moves[-1].end[2] == pytest.approx(cut.z_safe, abs=1e-12)


@pytest.mark.parametrize("name", PATH_NAMES)
def test_path_validates(paths, name):
    """validate() geçer; rpm ve takım Cut/Tool'dan gelir."""
    tp, cut = paths[name]
    tp.validate()
    assert tp.rpm == cut.rpm
    assert tp.tool.D == D


@pytest.mark.parametrize("name", PATH_NAMES)
def test_pass_depths_match(paths, name):
    """Yatay kesme hareketlerinin Z değerleri tam olarak depths(z_top, z_bottom, a_p)."""
    tp, cut = paths[name]
    assert cut_depths(tp) == pytest.approx(depths(cut.z_top, cut.z_bottom, cut.a_p), abs=1e-12)


@pytest.mark.parametrize("name", PATH_NAMES)
def test_rapid_moves_rules(paths, name):
    """G0 kuralları (SPEC "Hareket kuralları"):
    - XY değiştiren G0'lar z_safe'te (iki ucu da);
    - aşağı inen G0 en fazla z_prev + clearance'a iner (z_prev: bir önceki paso derinliği, ilk pasoda z_top),
      ardından düşey G1 dalma plunge_feed ile paso derinliğine gelir;
    - böylece hiçbir G0 o anki paso derinliğine (ve altına) inmez: z_prev + clearance > z_k.
    """
    tp, cut = paths[name]
    zs = depths(cut.z_top, cut.z_bottom, cut.a_p)
    prev_of = {z: (cut.z_top if i == 0 else zs[i - 1]) for i, z in enumerate(zs)}
    mv = moves_of(tp)
    for i, p in enumerate(mv):
        if p.type is not MoveType.RAPID:
            continue
        if math.hypot(*(p.p1[:2] - p.p0[:2])) > 1e-12:
            assert p.p0[2] == pytest.approx(cut.z_safe, abs=1e-12)
            assert p.p1[2] == pytest.approx(cut.z_safe, abs=1e-12)
        elif p.p1[2] < p.p0[2]:
            assert i + 1 < len(mv)
            nxt = mv[i + 1]
            assert nxt.is_plunge
            assert nxt.feed == cut.plunge_feed
            z_target = float(nxt.p1[2])
            zk = min(zs, key=lambda z, zt=z_target: abs(z - zt))
            assert z_target == pytest.approx(zk, abs=1e-12)
            assert p.p1[2] == pytest.approx(prev_of[zk] + cut.clearance, abs=1e-12)
            assert p.p1[2] > z_target


@pytest.mark.parametrize("name", PATH_NAMES)
def test_feeds(paths, name):
    """Yatay kesme hareketleri feed ile, düşey dalmalar plunge_feed ile."""
    tp, cut = paths[name]
    for p in moves_of(tp):
        if p.type is MoveType.RAPID:
            continue
        if p.horizontal:
            assert p.feed == cut.feed
        elif p.is_plunge:
            assert p.feed == cut.plunge_feed


@pytest.mark.parametrize("s", [3.0, 0.8 * D, D], ids=["r", "0.8D", "D"])
def test_pocket_inner_link_stays_down(s):
    """Adasız dikdörtgen cepte (tek ağaç) halkalar arası geçiş inmeden G1 ile: paso başına tek dalma
    (SPEC 03b K6: r < s ≤ D'de de)."""
    cut = make_cut(stepover=s)
    tp = pocket(Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), make_tool(), cut)
    plunges = [p for p in moves_of(tp) if p.is_plunge]
    assert len(plunges) == len(depths(cut.z_top, cut.z_bottom, cut.a_p))


# ---------------------------------------------------------------- K16: hatalı girdiler


@pytest.mark.parametrize(
    "bad",
    [
        dict(z_top=-5.0, z_bottom=-5.0),  # z_top > z_bottom değil
        dict(z_top=-6.0, z_bottom=-5.0),
        dict(a_p=0.0),
        dict(a_p=-1.0),
        dict(feed=0.0),
        dict(plunge_feed=-10.0),
        dict(rpm=0.0),
        dict(z_safe=0.0),  # z_safe > z_top değil
        dict(clearance=-0.5),
        dict(stepover=0.0),
        dict(stepover=D + 0.1),  # s > D
    ],
)
def test_bad_cut_raises(bad):
    """Cut alan kısıtları (kurulumda veya kullanımda) → CamError."""
    kw = dict(stepover=3.0)
    kw.update(bad)
    with pytest.raises(CamError):
        cut = make_cut(**kw)
        pocket(Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), make_tool(), cut)


def test_stepover_required_for_pocket_and_face():
    """stepover cep ve yüz almada zorunlu; konturda gerekmez."""
    cut = make_cut()
    with pytest.raises(CamError):
        pocket(Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), make_tool(), cut)
    with pytest.raises(CamError):
        face(FACE_STOCK, make_tool(), make_cut(z_top=0.0, z_bottom=-1.0, a_p=0.6))
    contour(Profile.rectangle(0.0, 0.0, 40.0, 20.0), make_tool(), cut, "dis")


def test_stepover_equal_D_allowed():
    """Sınır değer s = D yüz almada kabul edilir (0 < s ≤ D; Ek A1 yüz almayı değiştirmez).
    SPEC 03b K8: cepte de sınır yine s = D."""
    tp = face(FACE_STOCK, make_tool(), make_cut(z_top=0.0, z_bottom=-1.0, a_p=0.6, stepover=D))
    tp.validate()
    tp = pocket(Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), make_tool(), make_cut(stepover=D))
    tp.validate()


def test_tool_does_not_fit_raises():
    """İç ofset boş: R = 2 < r = 3 dairede "ic" kontur ve 5×5 (2r = 6 > 5) cep → CamError."""
    with pytest.raises(CamError):
        contour(Profile.circle((0.0, 0.0), 2.0), make_tool(), make_cut(), "ic")
    with pytest.raises(CamError):
        pocket(Region(Profile.rectangle(0.0, 0.0, 5.0, 5.0)), make_tool(), make_cut(stepover=3.0))


@pytest.mark.parametrize("side", ["dis", "ic"])
def test_open_profile_offset_side_raises(side):
    """Açık profilde sadece "uzerinde" geçerli."""
    prof = Profile([Line((0.0, 0.0), (30.0, 0.0)), Line((30.0, 0.0), (30.0, 20.0))], closed=False)
    with pytest.raises(CamError):
        contour(prof, make_tool(), make_cut(), side)


def test_unknown_side_raises():
    with pytest.raises(CamError):
        contour(Profile.rectangle(0.0, 0.0, 40.0, 20.0), make_tool(), make_cut(), "sol")


@pytest.mark.parametrize("kind", [ToolKind.BALL, ToolKind.DRILL])
def test_non_flat_tool_raises(kind):
    """Bu SPEC sadece ToolKind.FLAT kabul eder (Kapsam dışı)."""
    tool = make_tool(kind)
    with pytest.raises(CamError):
        contour(Profile.rectangle(0.0, 0.0, 40.0, 20.0), tool, make_cut(), "dis")
    with pytest.raises(CamError):
        pocket(Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), tool, make_cut(stepover=3.0))
    with pytest.raises(CamError):
        face(FACE_STOCK, tool, make_cut(z_top=0.0, z_bottom=-1.0, a_p=0.6, stepover=3.0))


# ---------------------------------------------------------------- Ek A: cep güvenliği (K17–K19)
#
# Kaynak: SPEC 03 Ek A. A1: cepte yan paso s ≤ r (kanıt Ek A'da: δ(p) < r olan nokta halkaya,
# δ(p) ≥ s olan nokta çocuk bölgeye düşer; s ≤ r ise arada nokta kalmaz). A2: merkezden kesmeyen
# takım (Tool.center_cutting = False) pocket ve contour'da düz dalamaz; face girişleri ham malzemenin dışında.
#
# Erişilebilir nokta (K14 "köşe kalanları hariç"in genel hâli): p, takım merkezinin gidebileceği bir c'ye
# (c ∈ Ω, dist(c, ∂Ω) ≥ r) |p − c| ≤ r uzaklıktaysa erişilebilir; yani p ∈ (Ω ⊖ B_r) ⊕ B_r (açılış).
# Aday merkezler p + ρ·(cos φ, sin φ), ρ ∈ {0,3; 0,6; 0,9; 1}·r, 72 açı: bulunan her c gerçek bir merkez
# olduğundan maske yalnızca gerçekten erişilebilir noktaları seçer (ölçüt zayıflar, yanlış alarm vermez).


def reachable(ref: RefBolge, P: np.ndarray) -> np.ndarray:
    """Takımın (yarıçap r) bölgenin içinden erişebildiği örnek noktaların maskesi (yukarıdaki tanım)."""
    bnd = ref.boundary()
    d = bnd.distance(P)
    in_closed = ref.contains(P) | (d <= 1e-9)  # sınır üstündeki noktalar da cebin parçası
    ok = in_closed & (d >= r)
    phi = np.linspace(0.0, 2 * math.pi, 72, endpoint=False)
    U = np.stack([np.cos(phi), np.sin(phi)], axis=1)
    for i in np.flatnonzero(in_closed & ~ok):
        C = np.vstack([P[i] + rho * r * U for rho in (0.3, 0.6, 0.9, 1.0)])
        ok[i] = bool(np.any(ref.contains(C) & (bnd.distance(C) >= r - 1e-12)))
    return ok


def assert_no_residue(ref: RefBolge, s: float, n: int = 45, tol: float = r + 1e-9) -> None:
    """K14 ölçütü: tek pasolu cepte (z 0 → −2) erişilebilir her ızgara noktası bir kesme hareketine
    ≤ tol (SPEC 03 / Ek A: r + 1e-9; SPEC 03b K5: r + COVER_TOL + 1e-9)."""
    tp = pocket(to_region(ref), make_tool(), make_cut(z_top=0.0, z_bottom=-2.0, a_p=5.0, stepover=s))
    tp.validate()
    pts = np.array(ref.outer[1]) if ref.outer[0] == "poly" else None
    if pts is None:
        (cx, cy), R = ref.outer[1], ref.outer[2]
        x0, x1, y0, y1 = cx - R, cx + R, cy - R, cy + R
    else:
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
    P = grid(float(x0), float(x1), float(y0), float(y1), n, n)
    P = P[reachable(ref, P)]
    assert len(P) > 0
    assert_covered(tp, P, -2.0, tol)


def test_reachable_matches_rectangle_corner_formula():
    """Öz denetim: dikdörtgende genel erişilebilirlik maskesi elle yazılmış 90° köşe formülüyle aynı
    (iki formülün sınırına çok yakın noktalar hariç)."""
    ref = RefBolge(RECT)
    P = grid(0.0, 60.0, 0.0, 40.0, 61, 41)
    exp = ~corner_unreachable(P, RECT_CORNERS)
    got = reachable(ref, P)
    near = np.zeros(len(P), dtype=bool)
    for x0, y0, sx, sy in RECT_CORNERS:
        u, v = (P[:, 0] - x0) * sx, (P[:, 1] - y0) * sy
        near |= (u < r) & (v < r) & (np.abs(np.hypot(u - r, v - r) - r) < 0.05)
    assert np.array_equal(got[~near], exp[~near])


# ------------------------------------------- K17: cepte s = r sınırı (Ek A1) → SPEC 03b K8
#
# Ek A1 cepte s > r'yi CamError yapmıştı. SPEC 03b (kalan malzeme denetimli halka ağacı) bu kuralı kaldırır:
# cepte yine 0 < s ≤ D; r < s ≤ D değerleri K5 ölçütüyle (≤ r + COVER_TOL + 1e-9) kalan malzemesiz
# kabul edilir.

S_LIMIT_POCKETS = {
    "dikdortgen": RefBolge(RECT),
    "L": RefBolge(L_SHAPE),
    "dikdortgen_ada": RefBolge(RECT, [ISLAND]),
}
TOL_03B = r + COVER_TOL + 1e-9  # SPEC 03b "kalan malzeme yok" ölçütü


@pytest.mark.parametrize("name", list(S_LIMIT_POCKETS))
def test_pocket_stepover_equal_r_accepted_no_residue(name):
    """K17: s = r (sınır) kabul edilir ve kalan malzeme yok (K14 ölçütü, köşe kalanları hariç)."""
    assert_no_residue(S_LIMIT_POCKETS[name], r)


@pytest.mark.parametrize("name", ["dikdortgen", "L", "daire"])
@pytest.mark.parametrize("s", [r + 1e-6, 0.8 * D, D], ids=["r+1e-6", "0.8D", "D"])
def test_pocket_stepover_above_r_accepted(name, s):
    """SPEC 03b K8: Ek A1'in s > r → CamError beklentisi kalktı; bu değerler kabul edilir ve K5'e göre
    kalan malzeme yok (erişilebilir her nokta bir kesme hareketine ≤ r + COVER_TOL + 1e-9)."""
    ref = POCKETS.get(name) or S_LIMIT_POCKETS[name]
    assert_no_residue(ref, s, n=40, tol=TOL_03B)


def test_pocket_stepover_error_message():
    """SPEC 03b K7/K8: cepte s > D → CamError kalır; mesaj s'yi verir."""
    with pytest.raises(CamError, match=r"6\.5"):
        pocket(to_region(S_LIMIT_POCKETS["dikdortgen"]), make_tool(), make_cut(stepover=D + 0.5))


@pytest.mark.parametrize("s", [D + 1e-6, 1.5 * D])
@pytest.mark.parametrize("name", ["dikdortgen", "L"])
def test_pocket_stepover_above_D_raises(name, s):
    """SPEC 03b K7: cepte s > D → CamError."""
    with pytest.raises(CamError):
        pocket(to_region(S_LIMIT_POCKETS[name]), make_tool(), make_cut(stepover=s))


def test_l_pocket_arm_middle_not_left_uncut():
    """Ek A1'in nedeni: L cepte (kollar 20 geniş) denetimsiz ağaç s = 0,6D'de kolların ortasını kesmeden
    bırakıyordu. SPEC 03b K8: s = 0,6D kabul edilir ve kol ortaları (10, 35), (35, 10) kesilir
    (s = r'de de)."""
    for s in (0.6 * D, r):
        tp = pocket(
            to_region(S_LIMIT_POCKETS["L"]),
            make_tool(),
            make_cut(z_top=0.0, z_bottom=-2.0, a_p=5.0, stepover=s),
        )
        dist = curves_of(cutting_moves(tp, -2.0)).distance(np.array([(10.0, 35.0), (35.0, 10.0)]))
        assert np.all(dist <= TOL_03B)


@pytest.mark.parametrize("w", [30.0, 40.0], ids=["30x12", "40x12"])
def test_narrow_rectangle_pocket_s_equal_r(w):
    """Ek A / K14: dar dikdörtgen cep (15, 10)'dan w × 12, D = 6, s = 3 = r: hata yok ve K14 ölçütü
    (köşe kalanları hariç her erişilebilir nokta bir kesme hareketine ≤ r + 1e-9). Yükseklik 12 = 2D:
    ilk halka (w − 6) × 6'lık dikdörtgen, bir sonraki s = 3 ofseti sıfır kalınlıklı (y = 16 doğrusu)."""
    pts = [(15.0, 10.0), (15.0 + w, 10.0), (15.0 + w, 22.0), (15.0, 22.0)]
    region = Region(Profile.rectangle(15.0, 10.0, w, 12.0))
    tp = pocket(region, make_tool(), make_cut(z_top=0.0, z_bottom=-2.0, a_p=5.0, stepover=r))
    tp.validate()
    ref = RefBolge(("poly", pts))
    P = grid(15.0, 15.0 + w, 10.0, 22.0, 61, 25)
    P = P[reachable(ref, P)]
    assert_covered(tp, P, -2.0)


# ------------------------------------------- K18: kalan malzeme özelliği (rastgele bölgeler)


def random_polygon(seed: int, convex: bool) -> list[tuple[float, float]]:
    """Sabit tohumlu yıldız çokgen (merkez (0, 0), açıya göre sıralı köşeler → basit çokgen).

    Dışbükey: köşeler R = 30 çemberinde (çembere çizilen çokgen dışbükeydir).
    İçbükey: yarıçaplar sırayla U(12, 20) ve U(28, 36) (girintili yıldız); en az bir içbükey köşe
    olması öz denetimle sınanır.
    Ardışık açılar arası ≥ 0,3 rad (çok kısa kenar yok).
    """
    rng = np.random.default_rng(seed)
    n = int(rng.integers(5, 10))
    while True:
        th = np.sort(rng.uniform(0.0, 2 * math.pi, n))
        gaps = np.diff(np.r_[th, th[0] + 2 * math.pi])
        if gaps.min() >= 0.3 and gaps.max() < math.pi - 0.2:
            break
    if convex:
        R = np.full(n, 30.0)
    else:
        R = np.where(np.arange(n) % 2 == 0, rng.uniform(28.0, 36.0, n), rng.uniform(12.0, 20.0, n))
    return [(float(R[i] * math.cos(th[i])), float(R[i] * math.sin(th[i]))) for i in range(n)]


def cross_signs(pts) -> np.ndarray:
    """Köşelerdeki dönüş işaretleri (CCW çokgende dışbükey köşe > 0)."""
    Q = np.asarray(pts)
    a = np.roll(Q, 1, axis=0) - Q
    b = np.roll(Q, -1, axis=0) - Q
    return np.sign(b[:, 0] * a[:, 1] - b[:, 1] * a[:, 0])


RANDOM_POCKETS = {
    **{f"dis_bukey{k}": RefBolge(("poly", random_polygon(k, True))) for k in (1, 2, 3)},
    **{f"ic_bukey{k}": RefBolge(("poly", random_polygon(100 + k, False))) for k in (1, 2, 3, 4)},
    "L": RefBolge(L_SHAPE),
}


def test_random_polygons_self_check():
    """Üretici öz denetimi: dışbükeylerde tüm köşeler aynı yönde, içbükeylerde en az bir içbükey köşe."""
    for name, ref in RANDOM_POCKETS.items():
        if name == "L":
            continue
        sg = cross_signs(ref.outer[1])
        assert shoelace(np.asarray(ref.outer[1])) > 0
        if name.startswith("dis"):
            assert np.all(sg > 0), name
        else:
            assert np.any(sg < 0), name


@pytest.mark.parametrize("name", list(RANDOM_POCKETS))
@pytest.mark.parametrize("k", [0.3, 0.4, 0.5], ids=["0.3D", "0.4D", "0.5D"])
def test_pocket_no_residue_random(name, k):
    """K18: s ∈ {0,3D, 0,4D, 0,5D} için erişilebilir her örnek nokta bir kesme hareketine ≤ r + 1e-9."""
    assert_no_residue(RANDOM_POCKETS[name], k * D, n=40)


# ------------------------------------------- SPEC 03b K5: r < s ≤ D cepte kalan malzeme yok

K5_CASES = [
    ("dikdortgen", RefBolge(RECT), [0.8, 1.0]),
    ("daire", RefBolge(CIRCLE), [0.95]),
    ("L", RefBolge(L_SHAPE), [0.6, 0.7, 1.0]),
    ("dikdortgen_ada", RefBolge(RECT, [ISLAND]), [0.7, 1.0]),
]


@pytest.mark.parametrize("name, k", [(name, k) for name, _, ks in K5_CASES for k in ks], ids=lambda v: str(v))
def test_pocket_no_residue_above_r(name, k):
    """SPEC 03b K5: dikdörtgen (0,8D, D), daire (0,95D), L (0,6D, 0,7D, D), adalı (0,7D, D): erişilebilir
    kümedeki ((Ω ⊖ B_r) ⊕ B_r) her örnek nokta bir kesme hareketine ≤ r + COVER_TOL + 1e-9."""
    ref = {n: g for n, g, _ in K5_CASES}[name]
    assert_no_residue(ref, k * D, tol=TOL_03B)


@pytest.mark.parametrize("name", [n for n in RANDOM_POCKETS if n != "L"])
@pytest.mark.parametrize("k", [0.6, 0.8, 1.0], ids=["0.6D", "0.8D", "D"])
def test_pocket_no_residue_random_above_r(name, k):
    """SPEC 03b K5: rastgele dışbükey / içbükey çokgenler, s ∈ {0,6D, 0,8D, D}: kalan malzeme yok."""
    assert_no_residue(RANDOM_POCKETS[name], k * D, n=40, tol=TOL_03B)


@pytest.mark.parametrize("k", [0.7, 1.0], ids=["0.7D", "D"])
def test_pocket_no_residue_every_pass_above_r(k):
    """SPEC 03b K5: çok pasolu adalı cepte her pasoda aynı ölçüt (Z pasoları XY'yi değiştirmez)."""
    ref = RefBolge(RECT, [ISLAND])
    tp = pocket(to_region(ref), make_tool(), make_cut(z_top=0.0, z_bottom=-5.0, a_p=2.0, stepover=k * D))
    P = grid(0.0, 60.0, 0.0, 40.0, 30, 30)
    P = P[reachable(ref, P)]
    for z in depths(0.0, -5.0, 2.0):
        assert_covered(tp, P, z, TOL_03B)


# ------------------------------------------- K19: merkezden kesmeyen takım


def non_center_tool() -> Tool:
    return Tool(id=1, name="freze6_mk", kind=ToolKind.FLAT, D=D, flute_length=20.0, center_cutting=False)


def test_non_center_cutting_pocket_and_contour_raise():
    """K19: center_cutting=False takım düz dalamaz → pocket ve contour CamError."""
    tool = non_center_tool()
    with pytest.raises(CamError):
        pocket(Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), tool, make_cut(stepover=r))
    for side in ("dis", "ic", "uzerinde"):
        with pytest.raises(CamError):
            contour(Profile.rectangle(0.0, 0.0, 40.0, 20.0), tool, make_cut(), side)


def test_non_center_cutting_face_allowed():
    """K19: face girişleri ham malzemenin dışında (x_min − r − clearance) → kabul; yol center_cutting=True
    takımınkiyle aynı hareketlerden oluşur."""
    cut = make_cut(z_top=0.0, z_bottom=-1.0, a_p=0.6, stepover=FACE_S, clearance=1.0)
    tp = face(FACE_STOCK, non_center_tool(), cut)
    tp.validate()
    ref = face(FACE_STOCK, make_tool(), cut)
    assert [(m.type, m.end) for m in tp.moves] == [(m.type, m.end) for m in ref.moves]


def test_center_cutting_default_true():
    """Ek A2: varsayılan True; mevcut takımlarla davranış değişmez."""
    assert make_tool().center_cutting is True
