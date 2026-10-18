"""SPEC 03b — cam/rest.py ve cam/offset.offset_union testleri (K1–K4, K7).

Testler sadece SPEC 03b "Teori" ve "Arayüz" bölümlerinden yazıldı; cam/rest.py ve offset_union gövdeleri
okunmadı. Beklenen değerler:
- Seviye koşulu (SPEC 03b): düğüm R, adım σ, X = R ⊖ B_σ, A = R ⊖ B_r, Y = X ⊕ B_(r+ε); koşul A ⊆ Y.
- Köşe eşiği: iç açısı θ olan dışbükey köşede A'nın ve X'in köşeleri açıortay üzerinde (σ − r)/sin(θ/2)
  uzaklıktadır; köşe Y'de ⇔ (σ − r)/sin(θ/2) ≤ r + ε ⇔ σ ≤ r + (r + ε) sin(θ/2). ε = 1e-7 eşiği en fazla
  1e-7 kaydırır; testler eşiğin ±1e-6 yanında karar ister. Dikdörtgen: r(1 + sin 45°), eşkenar üçgen 1,5 r.
- Daire ρ: σ < ρ ise X yarıçapı ρ − σ, Y yarıçapı ρ − σ + r + ε ≥ ρ − r (A) ⇔ σ ≤ 2r + ε; σ ≥ ρ ise X = ∅,
  koşul A = ∅ ⇔ ρ ≤ r.
- Dikdörtgen köşe kalanı (σ > eşik): köşede yerel (u, v) A'nın köşesinden, k = σ − r, ρ' = r + ε;
  kalan = {0 ≤ u, v < k, |(u, v) − (k, k)| > ρ'}, alanı k² − ∫₀ᵏ min(k, √(ρ'² − x²)) dx.
- Uzaklık / içerme: tests/cam/ref2d.py (bağımsız analitik). SPEC 03 ağacı ("denetimsiz" ağaç) referans için
  SPEC 03'ün `offset`'iyle kurulur (her düğümde R ⊖ B_s).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError
from cam.offset import offset, offset_union
from cam.profile import Arc, Line, Profile, Region
from cam.rest import BISECT_N, COVER_TOL, RingNode, covered, residue, ring_tree
from tests.cam.ref2d import Egriler, grid, polygon_contains

SIN45 = math.sqrt(2.0) / 2.0


# ---------------------------------------------------------------- yardımcılar


def rings(regions: list[Region]) -> list[Profile]:
    return [h for g in regions for h in g.loops]


def curves(regions: list[Region]) -> Egriler:
    """Bölge halkalarının doğru + yaylarını bağımsız uzaklık hesabına aktarır."""
    e = Egriler()
    for p in rings(regions):
        for s in p.segments:
            if isinstance(s, Arc):
                th0 = s.a0 if s.ccw else s.a0 - s.sweep  # saat yönündeki yay: eşdeğer CCW başlangıç
                e.arc(s.c, s.R, th0, s.sweep)
            else:
                e.line(s.p0, s.p1)
    return e


def boundary_samples(regions: list[Region], n: int = 9) -> np.ndarray:
    """Her parçanın üzerinde n örnek nokta (uçlar dahil)."""
    pts = [s.point(float(t)) for p in rings(regions) for s in p.segments for t in np.linspace(0.0, 1.0, n)]
    return np.array(pts, dtype=float).reshape(-1, 2)


def ring_polyline(p: Profile, n_arc: int = 256) -> np.ndarray:
    pts = []
    for s in p.segments:
        n = n_arc if isinstance(s, Arc) else 1
        for t in np.linspace(0.0, 1.0, n, endpoint=False):
            pts.append(tuple(s.point(float(t))))
    return np.array(pts)


def union_contains(regions: list[Region], P: np.ndarray) -> np.ndarray:
    """Çift-tek kuralı tüm halkalar üzerinden (ayrık bölgeler, delikler)."""
    acc = np.zeros(len(P), dtype=int)
    for p in rings(regions):
        acc += polygon_contains(P, ring_polyline(p)).astype(int)
    return (acc % 2) == 1


def any_contains(regions: list[Region], P: np.ndarray) -> np.ndarray:
    """cam.profile.Region.contains ile (yaylar kesin): noktalar bölgelerden birinin içinde mi."""
    return np.array([any(g.contains(p) for g in regions) for p in P], dtype=bool)


def areas(regions: list[Region]) -> list[float]:
    return sorted(g.area for g in regions)


def total_area(regions: list[Region]) -> float:
    return sum(g.area for g in regions)


def spec03_tree(region: Region, r: float, s: float) -> list[Region]:
    """SPEC 03 (denetimsiz) halka ağacının tüm düğüm bölgeleri: kökler Ω ⊖ B_r, her düğümde R ⊖ B_s."""
    out: list[Region] = []

    def walk(R: Region) -> None:
        out.append(R)
        for c in offset(R, s):
            walk(c)

    for R0 in offset(region, r):
        walk(R0)
    return out


def iter_nodes(nodes: list[RingNode]):
    for n in nodes:
        yield n
        yield from iter_nodes(n.children)


def random_polygon(seed: int, convex: bool) -> list[tuple[float, float]]:
    """Sabit tohumlu yıldız çokgen (açıya göre sıralı köşeler, basit çokgen); içbükeyde girintili yarıçap."""
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


def triangle_angles(pts) -> list[float]:
    Q = np.asarray(pts, dtype=float)
    out = []
    for i in range(3):
        a = Q[(i - 1) % 3] - Q[i]
        b = Q[(i + 1) % 3] - Q[i]
        out.append(math.acos(float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))))
    return out


def inradius(pts) -> float:
    Q = np.asarray(pts, dtype=float)
    u, v = Q[1] - Q[0], Q[2] - Q[0]
    A = 0.5 * abs(float(u[0] * v[1] - u[1] * v[0]))
    P = sum(float(np.linalg.norm(Q[(i + 1) % 3] - Q[i])) for i in range(3))
    return 2 * A / P


L_POCKET = Region(
    Profile.polygon([(0.0, 0.0), (50.0, 0.0), (50.0, 20.0), (20.0, 20.0), (20.0, 45.0), (0.0, 45.0)])
)
ISLAND_POCKET = Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0), [Profile.circle((30.0, 20.0), 6.0)])
DUMBBELL = Region(
    Profile.polygon(
        [(0.0, 0.0), (20.0, 0.0), (20.0, 8.0), (30.0, 8.0), (30.0, 0.0), (50.0, 0.0),
         (50.0, 20.0), (30.0, 20.0), (30.0, 12.0), (20.0, 12.0), (20.0, 20.0), (0.0, 20.0)]
    )
)  # fmt: skip


# ---------------------------------------------------------------- K1: offset_union


SINGLE_CASES = {
    "dikdortgen_ic": (Region(Profile.rectangle(0.0, 0.0, 40.0, 20.0)), 3.0),
    "dikdortgen_dis": (Region(Profile.rectangle(0.0, 0.0, 40.0, 20.0)), -3.0),
    "daire_ic": (Region(Profile.circle((5.0, -3.0), 10.0)), 2.0),
    "daire_dis": (Region(Profile.circle((5.0, -3.0), 10.0)), -2.0),
    "L_ic": (L_POCKET, 3.0),
    "L_dis": (L_POCKET, -4.0),
    "adali_ic": (ISLAND_POCKET, 3.0),
    "adali_dis": (ISLAND_POCKET, -2.0),
    "halter_ic": (DUMBBELL, 3.0),
}


@pytest.mark.parametrize("name", list(SINGLE_CASES))
def test_offset_union_single_equals_offset(name):
    """K1: tek bölgede offset_union([R], d) = offset(R, d): bölge ve delik sayısı, alanlar, halka boyları."""
    R, d = SINGLE_CASES[name]
    got = offset_union([R], d)
    exp = offset(R, d)
    assert len(got) == len(exp)
    assert areas(got) == pytest.approx(areas(exp), rel=1e-9)
    assert sorted(len(g.holes) for g in got) == sorted(len(g.holes) for g in exp)
    assert sorted(p.length for p in rings(got)) == pytest.approx(
        sorted(p.length for p in rings(exp)), rel=1e-9
    )
    # sonuç sınırı ∂R'ye tam |d| uzaklıkta
    dist = curves([R]).distance(boundary_samples(got))
    assert np.allclose(dist, abs(d), atol=1e-9)


A_SQ = 10.0  # kare kenarı [mm]
G_SQ = 4.0  # aralık [mm]
TWO_SQUARES = [
    Region(Profile.rectangle(0.0, 0.0, A_SQ, A_SQ)),
    Region(Profile.rectangle(A_SQ + G_SQ, 0.0, A_SQ, A_SQ)),
]
SQ_CURVES = Egriler()
SQ_CURVES.polygon([(0.0, 0.0), (A_SQ, 0.0), (A_SQ, A_SQ), (0.0, A_SQ)])
SQ_CURVES.polygon([(A_SQ + G_SQ, 0.0), (2 * A_SQ + G_SQ, 0.0), (2 * A_SQ + G_SQ, A_SQ), (A_SQ + G_SQ, A_SQ)])


def squares_union_ref(P: np.ndarray, d: float) -> tuple[np.ndarray, np.ndarray]:
    """Dış ofset referansı: p ∈ ∪R_i ⊕ B_|d| ⇔ p bir karenin içinde veya dist(p, ∪∂R_i) ≤ |d|.
    İkinci dönüş: sınıra 1e-6'dan yakın (karar dışı) noktalar."""
    dist = SQ_CURVES.distance(P)
    inside = (P[:, 1] > 0.0) & (P[:, 1] < A_SQ)
    inside &= ((P[:, 0] > 0.0) & (P[:, 0] < A_SQ)) | ((P[:, 0] > A_SQ + G_SQ) & (P[:, 0] < 2 * A_SQ + G_SQ))
    return inside | (dist <= abs(d)), np.abs(dist - abs(d)) < 1e-6


@pytest.mark.parametrize("d, n_exp", [(-1.5, 2), (-1.999, 2), (-2.001, 1), (-2.5, 1)])
def test_offset_union_two_squares_outer(d, n_exp):
    """K1: iki ayrık 10×10 kare (aralık g = 4) dış ofsette |d| < g/2 → 2 bölge, |d| > g/2 → 1 bölge;
    sınır örnekleri ∪∂R_i'ye tam |d| uzaklıkta; ızgara noktaları için içerme referansla aynı."""
    got = offset_union(TWO_SQUARES, d)
    assert len(got) == n_exp
    assert all(g.holes == [] for g in got)
    dist = SQ_CURVES.distance(boundary_samples(got))
    assert np.allclose(dist, abs(d), atol=1e-9)
    P = grid(-3.0, 2 * A_SQ + G_SQ + 3.0, -3.0, A_SQ + 3.0, 81, 49)
    exp, near = squares_union_ref(P, d)
    assert np.array_equal(union_contains(got, P)[~near], exp[~near])


def test_offset_union_two_squares_outer_area_disjoint():
    """K1: ayrık durumda her bölgenin alanı tek kare dış ofseti a² + 4a|d| + π d²."""
    d = -1.5
    got = offset_union(TWO_SQUARES, d)
    exp = A_SQ**2 + 4 * A_SQ * abs(d) + math.pi * d**2
    assert areas(got) == pytest.approx([exp, exp], rel=1e-9)


def test_offset_union_merge_makes_hole():
    """K1: 3×3 ızgarada ortası boş 8 kare (10×10, aralık 2), d = −1,5 > g/2: hepsi birleşir, ortada bir delik
    kalır. Sınır örnekleri karelere tam 1,5 uzaklıkta; içerme referansla aynı."""
    sq = [(12.0 * i, 12.0 * j) for i in range(3) for j in range(3) if (i, j) != (1, 1)]
    regs = [Region(Profile.rectangle(x, y, 10.0, 10.0)) for x, y in sq]
    ref = Egriler()
    for x, y in sq:
        ref.polygon([(x, y), (x + 10.0, y), (x + 10.0, y + 10.0), (x, y + 10.0)])
    d = -1.5
    got = offset_union(regs, d)
    assert len(got) == 1
    assert len(got[0].holes) == 1
    assert np.allclose(ref.distance(boundary_samples(got)), 1.5, atol=1e-9)
    P = grid(-2.0, 36.0, -2.0, 36.0, 77, 77)
    dist = ref.distance(P)
    inside = np.zeros(len(P), dtype=bool)
    for x, y in sq:
        inside |= (P[:, 0] > x) & (P[:, 0] < x + 10.0) & (P[:, 1] > y) & (P[:, 1] < y + 10.0)
    exp = inside | (dist <= 1.5)
    near = np.abs(dist - 1.5) < 1e-6
    assert np.array_equal(union_contains(got, P)[~near], exp[~near])


ISLAND_POCKET_SHIFTED = Region(Profile.rectangle(0.0, 30.0, 60.0, 40.0), [Profile.circle((30.0, 50.0), 6.0)])


def test_offset_union_inner_is_union_of_offsets():
    """K1: iç ofsette sonuç her bölgenin offset'lerinin birleşimi (bölgeler ayrık kalır; boş olan düşer)."""
    regs = [*TWO_SQUARES, Region(Profile.rectangle(40.0, 0.0, 3.0, 3.0)), ISLAND_POCKET_SHIFTED]
    d = 2.0
    got = offset_union(regs, d)
    exp = [g for R in regs for g in offset(R, d)]
    assert len(got) == len(exp) == 3  # 3×3 kare 2d = 4 > 3: boş
    assert areas(got) == pytest.approx(areas(exp), rel=1e-9)
    assert sorted(len(g.holes) for g in got) == sorted(len(g.holes) for g in exp)
    assert areas(got)[:2] == pytest.approx([36.0, 36.0], rel=1e-9)


@pytest.mark.parametrize("d", [2.0, -2.0])
def test_offset_union_empty_list(d):
    """K1: regions == [] → []."""
    assert offset_union([], d) == []


def test_offset_union_zero_raises():
    """K1: d = 0 → CamError."""
    with pytest.raises(CamError):
        offset_union(TWO_SQUARES, 0.0)


# ---------------------------------------------------------------- K2: covered analitik eşikleri


RECTS = {
    "60x40_r5": (Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), 5.0),
    "30x20_r4": (Region(Profile.rectangle(-7.0, 12.0, 30.0, 20.0)), 4.0),
    "50x30_r3": (Region(Profile.rectangle(5.0, 5.0, 50.0, 30.0)), 3.0),
}


@pytest.mark.parametrize("name", list(RECTS))
def test_covered_rectangle_threshold(name):
    """K2: a×b dikdörtgen (X boş değil): eşik r(1 + sin 45°) = 1,7071 r; −1e-6 → True, +1e-6 → False."""
    R, r = RECTS[name]
    thr = r * (1.0 + SIN45)
    assert covered(R, thr - 1e-6, r) is True
    assert covered(R, thr + 1e-6, r) is False


@pytest.mark.parametrize("name", list(RECTS))
@pytest.mark.parametrize("k", [1.2, 1.5, 1.9, 2.0])
def test_covered_rectangle_far_from_threshold(name, k):
    """K2: σ = k·r; k < 1,7071 → True, k > 1,7071 → False (σ ≤ 2r; X boş değil)."""
    R, r = RECTS[name]
    assert covered(R, k * r, r) is (k < 1.0 + SIN45)


TRIANGLES = {
    "eskenar": [(0.0, 0.0), (40.0, 0.0), (20.0, 20.0 * math.sqrt(3.0))],
    "dik_ikizkenar": [(0.0, 0.0), (40.0, 0.0), (0.0, 40.0)],
    "cesitkenar": [(0.0, 0.0), (50.0, 0.0), (12.0, 36.0)],
}


def test_triangle_self_check():
    """Öz denetim: eşkenar θ_min = 60°, dik ikizkenar 45°; eşikler 1,5 r ve 1,3827 r."""
    assert min(triangle_angles(TRIANGLES["eskenar"])) == pytest.approx(math.pi / 3, abs=1e-12)
    assert min(triangle_angles(TRIANGLES["dik_ikizkenar"])) == pytest.approx(math.pi / 4, abs=1e-12)
    assert 1.0 + math.sin(math.pi / 6) == pytest.approx(1.5, abs=1e-15)
    assert 1.0 + math.sin(math.pi / 8) == pytest.approx(1.3827, abs=1e-4)


@pytest.mark.parametrize("name", list(TRIANGLES))
@pytest.mark.parametrize("r", [3.0, 4.0])
def test_covered_triangle_threshold(name, r):
    """K2: üçgende eşik r(1 + sin(θ_min/2)) (iç yarıçap > σ: X benzer üçgen, kenar kaybolmaz)."""
    pts = TRIANGLES[name]
    R = Region(Profile.polygon(pts))
    thr = r * (1.0 + math.sin(min(triangle_angles(pts)) / 2))
    assert inradius(pts) > thr + 1.0
    assert covered(R, thr - 1e-6, r) is True
    assert covered(R, thr + 1e-6, r) is False


@pytest.mark.parametrize("rho, sigma", [(10.0, 3.5), (10.0, 5.0), (10.0, 6.0), (7.0, 5.9), (20.0, 5.5)])
def test_covered_circle_sigma_below_rho(rho, sigma):
    """K2: ρ yarıçaplı daire, σ < ρ ve σ ≤ 2r (r = 3) → her zaman True."""
    R = Region(Profile.circle((5.0, -3.0), rho))
    assert covered(R, sigma, 3.0) is True


@pytest.mark.parametrize(
    "rho, sigma, exp",
    [(2.5, 5.0, True), (2.9, 3.5, True), (4.0, 5.0, False), (5.0, 5.5, False), (5.9, 6.0, False)],
)
def test_covered_circle_leaf(rho, sigma, exp):
    """K2: σ ≥ ρ (X = ∅, yaprak) → True ⇔ ρ ≤ r (r = 3; A = R ⊖ B_r boş)."""
    R = Region(Profile.circle((5.0, -3.0), rho))
    assert covered(R, sigma, 3.0) is exp


SIGMA_LE_R_REGIONS = {
    **{f"dis_bukey{k}": Region(Profile.polygon(random_polygon(k, True))) for k in (1, 2, 3)},
    **{f"ic_bukey{k}": Region(Profile.polygon(random_polygon(100 + k, False))) for k in (1, 2, 3, 4)},
    "L": L_POCKET,
    "adali": ISLAND_POCKET,
    "halter": DUMBBELL,
}


@pytest.mark.parametrize("name", list(SIGMA_LE_R_REGIONS))
@pytest.mark.parametrize("f", [0.3, 0.7, 1.0])
def test_covered_sigma_le_r_always_true(name, f):
    """K2 / Önerme 1: σ ≤ r → her bölgede True (r = 3)."""
    assert covered(SIGMA_LE_R_REGIONS[name], f * 3.0, 3.0) is True


# ---------------------------------------------------------------- K3: residue


CONSISTENCY_CASES = [
    (RECTS["60x40_r5"][0], 8.0, 5.0),
    (RECTS["60x40_r5"][0], 9.0, 5.0),
    (RECTS["30x20_r4"][0], 4.0 * (1.0 + SIN45) + 1e-6, 4.0),
    (RECTS["30x20_r4"][0], 4.0 * (1.0 + SIN45) - 1e-6, 4.0),
    (Region(Profile.polygon(TRIANGLES["eskenar"])), 4.4, 3.0),
    (Region(Profile.polygon(TRIANGLES["eskenar"])), 4.6, 3.0),
    (Region(Profile.circle((0.0, 0.0), 10.0)), 5.0, 3.0),
    (Region(Profile.circle((0.0, 0.0), 4.0)), 5.0, 3.0),
    (L_POCKET, 3.0, 3.0),
    (ISLAND_POCKET, 5.5, 3.0),
]


@pytest.mark.parametrize("k", range(len(CONSISTENCY_CASES)))
def test_residue_consistent_with_covered(k):
    """K3: residue(...) == [] ⇔ covered(...); boş değilse bölgelerin alanı pozitif."""
    R, sigma, r = CONSISTENCY_CASES[k]
    res = residue(R, sigma, r)
    assert (res == []) is covered(R, sigma, r)
    assert all(g.area > 0 for g in res)


def corner_residue_area(k: float, rho: float) -> float:
    """Kenarı k kare ile köşesinden ρ yarıçaplı dairenin dışında kalan alan (k ≤ ρ ≤ k√2)."""
    x0 = math.sqrt(rho**2 - k**2)

    def F(x: float) -> float:  # ∫ √(ρ² − x²) dx
        return 0.5 * (x * math.sqrt(rho**2 - x**2) + rho**2 * math.asin(x / rho))

    inside = k * x0 + F(k) - F(x0)
    return k * k - inside


def test_residue_rectangle_four_corners():
    """K3: 60×40, r = 5, σ = 9 > 8,536: 4 köşe bölgesi; her birinin alanı analitik köşe kalanı
    (k = σ − r = 4, ρ' = r + ε); ızgara noktalarında içerme referansla aynı."""
    R, r = RECTS["60x40_r5"]
    sigma = 9.0
    res = residue(R, sigma, r)
    assert len(res) == 4
    k, rho = sigma - r, r + COVER_TOL
    a_exp = corner_residue_area(k, rho)
    assert a_exp == pytest.approx(0.4525, abs=1e-3)  # öz denetim: 16 − 12 − 12,5(asin 0,8 − asin 0,6)
    assert areas(res) == pytest.approx([a_exp] * 4, abs=1e-6)
    # her bölge farklı bir köşede: A'nın köşesi (r, r)'den X'in köşesi (σ, σ)'ye uzanan kare içinde
    corners = [(0.0, 0.0, 1, 1), (60.0, 0.0, -1, 1), (60.0, 40.0, -1, -1), (0.0, 40.0, 1, -1)]
    P = np.vstack([grid(0.0, 12.0, 0.0, 12.0, 49, 49) * [sx, sy] + [x0, y0] for x0, y0, sx, sy in corners])
    exp = np.zeros(len(P), dtype=bool)
    near = np.zeros(len(P), dtype=bool)
    for x0, y0, sx, sy in corners:
        u = (P[:, 0] - x0) * sx - r
        v = (P[:, 1] - y0) * sy - r
        q = np.hypot(u - k, v - k)
        box = (u >= 0) & (v >= 0) & (u < k) & (v < k)
        exp |= box & (q > rho)
        near |= (np.abs(u) < 1e-6) | (np.abs(v) < 1e-6) | (box & (np.abs(q - rho) < 1e-6))
    assert np.array_equal(any_contains(res, P)[~near], exp[~near])
    # her köşede tam bir bölge: sınır kutusu A'nın köşesinden X'in köşesine uzanan k × k karede
    for x0, y0, sx, sy in corners:
        box = sorted([x0 + sx * r, x0 + sx * sigma]), sorted([y0 + sy * r, y0 + sy * sigma])
        mine = []
        for g in res:
            lo, hi = g.outer.bbox()
            if (
                box[0][0] - 1e-9 <= lo[0]
                and hi[0] <= box[0][1] + 1e-9
                and box[1][0] - 1e-9 <= lo[1] <= hi[1] <= box[1][1] + 1e-9
            ):
                mine.append(g)
        assert len(mine) == 1, (x0, y0)


L_R, L_S = 3.0, 0.6 * 6.0  # D = 6, s = 0,6D


def test_residue_l_pocket_broken_level():
    """K3: L cep (50×45, kollar 20, D = 6, s = 0,6D): SPEC 03 ağacında koşulu bozan seviye var; o seviyenin
    residue alanı > 0, residue içindeki örnek noktalar ∂R'ye > r ve ∂X'e > r uzak (Önerme 3) ve aralarında
    SPEC 03 ağacının hiçbir halkasına r + 1e-6'dan yakın olmayan (kesilmeyen) noktalar var."""
    nodes = spec03_tree(L_POCKET, L_R, L_S)
    broken = [R for R in nodes if not covered(R, L_S, L_R)]
    assert broken
    tree_curves = curves(nodes)
    P = grid(0.0, 50.0, 0.0, 45.0, 201, 181)
    uncut_found = False
    for R in broken:
        res = residue(R, L_S, L_R)
        assert total_area(res) > 0.0
        Q = P[any_contains(res, P)]
        assert len(Q) > 0
        assert np.all(curves([R]).distance(Q) >= L_R - 1e-9)
        X = offset(R, L_S)
        if X:
            assert np.all(curves(X).distance(Q) >= L_R + COVER_TOL - 1e-9)
            assert not np.any(any_contains(X, Q))
        uncut_found |= bool(np.any(tree_curves.distance(Q) > L_R + 1e-6))
    assert uncut_found


def test_residue_l_pocket_matches_reference_points():
    """K3: L cebin bozuk seviyesinde residue içermesi, ızgarada A \\ Y referansıyla aynı
    (p ∈ R, δ_R(p) ≥ r, p ∉ X, dist(p, ∂X) > r + ε; sınırlara 1e-6'dan yakın noktalar hariç)."""
    nodes = spec03_tree(L_POCKET, L_R, L_S)
    broken = [R for R in nodes if not covered(R, L_S, L_R)]
    assert broken
    P = grid(0.0, 50.0, 0.0, 45.0, 101, 91)
    for R in broken:
        X = offset(R, L_S)
        dR = curves([R]).distance(P)
        dX = curves(X).distance(P) if X else np.full(len(P), np.inf)
        inR = any_contains([R], P)
        inX = any_contains(X, P) if X else np.zeros(len(P), dtype=bool)
        exp = inR & (dR >= L_R) & ~inX & (dX > L_R + COVER_TOL)
        near = (np.abs(dR - L_R) < 1e-6) | (np.abs(dX - L_R - COVER_TOL) < 1e-6)
        got = any_contains(residue(R, L_S, L_R), P)
        assert np.array_equal(got[~near], exp[~near])
        assert exp.any()


# ---------------------------------------------------------------- K4: ring_tree adımları


def assert_spec03_tree(nodes: list[RingNode], expected: list[Region], s: float) -> None:
    """Düğümler SPEC 03 ağacıyla aynı: aynı bölgeler (alan, delik sayısı); offset(R, s) boş değilse
    çocukların adımı s ve bölgeleri offset(R, s); boşsa (yaprak) yalnız SPEC 03 ek halkaları (adım < s)."""
    assert len(nodes) == len(expected)
    assert areas([n.region for n in nodes]) == pytest.approx(areas(expected), rel=1e-9)
    for n in nodes:
        X = offset(n.region, s)
        if X:
            assert all(c.step == pytest.approx(s, abs=1e-9) for c in n.children)
            assert_spec03_tree(n.children, X, s)
        else:
            assert all(c.step < s for c in n.children)


S_LE_R_TREES = {"dikdortgen": Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), "L": L_POCKET,
                "adali": ISLAND_POCKET, "halter": DUMBBELL}  # fmt: skip


@pytest.mark.parametrize("name", list(S_LE_R_TREES))
@pytest.mark.parametrize("s", [1.8, 2.5, 3.0])
def test_ring_tree_s_le_r_is_spec03_tree(name, s):
    """K4: s ≤ r (r = 3) iken her adım s, ağaç SPEC 03 Ek A ile aynı; kök adımı r, kökler Ω ⊖ B_r."""
    r = 3.0
    region = S_LE_R_TREES[name]
    roots = ring_tree(region, r, s)
    assert all(isinstance(n, RingNode) for n in iter_nodes(roots))
    assert all(n.step == pytest.approx(r, abs=1e-12) for n in roots)
    assert_spec03_tree(roots, offset(region, r), s)


def test_ring_tree_dumbbell_two_roots():
    """K4: halter (köprü 4 < D = 6): iki ayrı kök."""
    assert len(ring_tree(DUMBBELL, 3.0, 3.0)) == 2


RECT_6040 = Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0))


def test_ring_tree_rectangle_08D_no_reduction():
    """K4: 60×40, D = 10, s = 0,8D = 8 < 8,536: kök 50×30, çocuğu adım 8 ile 34×14 (küçültme yok);
    34×14'te X = ∅ (yaprak): yalnız SPEC 03 ek halkaları (adım < s)."""
    r, s = 5.0, 8.0
    roots = ring_tree(RECT_6040, r, s)
    assert len(roots) == 1
    root = roots[0]
    assert root.step == pytest.approx(r, abs=1e-12)
    assert root.region.area == pytest.approx(50.0 * 30.0, rel=1e-9)
    assert len(root.children) == 1
    c = root.children[0]
    assert c.step == pytest.approx(s, abs=1e-12)
    assert c.region.area == pytest.approx(34.0 * 14.0, rel=1e-9)
    assert all(g.step < s for g in c.children)
    for n in iter_nodes(roots):
        if n.children:
            assert covered(n.region, n.children[0].step, r)


def test_ring_tree_rectangle_D_reduced_step():
    """K4: 60×40, D = 10, s = D: kök adımı σ ∈ [1,7071 r − (s − r)/256, 1,7071 r] (ikiye bölme, BISECT_N = 8),
    çocuk (50 − 2σ)×(30 − 2σ) dikdörtgen; covered(kök, σ) True; σ + (s − r)/256 + 1e-6 > σ_max → False."""
    r, s = 5.0, 10.0
    assert BISECT_N == 8
    thr = r * (1.0 + SIN45)
    roots = ring_tree(RECT_6040, r, s)
    assert len(roots) == 1
    root = roots[0]
    assert len(root.children) == 1
    sigma = root.children[0].step
    tol = (s - r) / 2**BISECT_N
    assert thr - tol - 1e-9 <= sigma <= thr + 1e-6
    child = root.children[0].region
    assert child.area == pytest.approx((50.0 - 2 * sigma) * (30.0 - 2 * sigma), rel=1e-9)
    lo, hi = child.outer.bbox()
    assert np.allclose([*lo, *hi], [5.0 + sigma, 5.0 + sigma, 55.0 - sigma, 35.0 - sigma], atol=1e-9)
    assert all(isinstance(seg, Line) for seg in child.outer.segments)
    assert covered(root.region, sigma, r)
    assert not covered(root.region, sigma + tol + 1e-6, r)


@pytest.mark.parametrize("s", [3.6, 4.2, 6.0])
def test_ring_tree_every_level_covered(s):
    """K4: r < s ≤ D'de (L cep, D = 6) çocuklu her düğüm, çocuklarının adımıyla covered (yaprak ek halkaları
    dahil: adımları < r, Önerme 1); adım ≤ s; bir düğümün çocukları aynı adımla, bölgeleri R ⊖ B_σ."""
    r = 3.0
    roots = ring_tree(L_POCKET, r, s)
    assert roots
    for n in iter_nodes(roots):
        if not n.children:
            continue
        steps = {round(c.step, 12) for c in n.children}
        assert len(steps) == 1
        sigma = n.children[0].step
        assert 0.0 < sigma <= s + 1e-12
        assert covered(n.region, sigma, r)
        assert areas([c.region for c in n.children]) == pytest.approx(
            areas(offset(n.region, sigma)), rel=1e-9
        )


# ---------------------------------------------------------------- K7: hatalı girdiler


@pytest.mark.parametrize("sigma, r", [(0.0, 3.0), (-1.0, 3.0), (3.0, 0.0), (3.0, -1.0)])
def test_covered_bad_input_raises(sigma, r):
    """K7: covered σ ≤ 0 veya r ≤ 0 → CamError."""
    with pytest.raises(CamError):
        covered(RECT_6040, sigma, r)


@pytest.mark.parametrize("s", [0.0, -1.0, 6.0 + 1e-6, 9.0])
def test_ring_tree_bad_stepover_raises(s):
    """K7: ring_tree 0 < s ≤ 2r değilse → CamError (r = 3)."""
    with pytest.raises(CamError):
        ring_tree(RECT_6040, 3.0, s)


def test_ring_tree_s_equal_2r_allowed():
    """K7 sınırı: s = 2r kabul edilir."""
    assert ring_tree(RECT_6040, 3.0, 6.0)


def test_ring_tree_tool_does_not_fit():
    """Takım sığmıyorsa [] (5×5 kare, r = 3: 2r > 5)."""
    assert ring_tree(Region(Profile.rectangle(0.0, 0.0, 5.0, 5.0)), 3.0, 3.0) == []


def test_constants():
    """Arayüz sabitleri: COVER_TOL = 1e-7 mm, BISECT_N = 8."""
    assert COVER_TOL == 1e-7
    assert BISECT_N == 8
