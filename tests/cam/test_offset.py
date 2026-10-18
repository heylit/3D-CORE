"""SPEC 03 — cam/offset.py testleri (K4–K9).

Testler sadece SPEC 03 "Arayüz" bölümündeki imzalardan yazıldı; uygulama kodu okunmadı.
Ofset tanımı (SPEC 03, Held Bölüm 2–3): d > 0 iç ofset Ω ⊖ B_d = {p ∈ Ω : dist(p, ∂Ω) ≥ d},
d < 0 dış ofset Ω ⊕ B_|d|. Uzaklıklar ve içerde/dışarda kararları tests/cam/ref2d.py'deki
bağımsız analitik hesapla verilir (cam.geom2d kullanılmaz).

Çokgen iç ofset alanı (konu dışı olay yoksa, dA/dd = −P(d) integrali):
    P(t) = P − 2t Σ_dışbükey cot(θ/2) + t Σ_içbükey (θ − π)
    A(d) = A − P d + d² Σ_dışbükey cot(θ/2) − ½ d² Σ_içbükey (θ − π)
(θ iç açı; dışbükey köşede iki kenar t·cot(θ/2) kısalır, içbükey köşede t yarıçaplı θ−π açılı yay eklenir.)
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError
from cam.offset import offset, offset_profile
from cam.profile import Arc, Line, Profile, Region
from tests.cam.ref2d import Egriler, grid, polygon_contains

A_RECT = 40.0  # [mm]
B_RECT = 20.0  # [mm]


def total_area(regions: list[Region]) -> float:
    return sum(r.area for r in regions)


def rings(regions: list[Region]) -> list[Profile]:
    return [h for r in regions for h in [r.outer, *r.holes]]


def segs(regions: list[Region]):
    return [s for p in rings(regions) for s in p.segments]


def close(p, q, tol: float = 1e-9) -> bool:
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol


def ring_polyline(p: Profile, n_arc: int = 128) -> np.ndarray:
    """Halkayı nokta dizisine çevirir (yaylar n_arc noktayla örneklenir) — bağımsız içerme testi için."""
    pts = []
    for s in p.segments:
        n = n_arc if isinstance(s, Arc) else 1
        for t in np.linspace(0.0, 1.0, n, endpoint=False):
            pts.append(tuple(s.point(float(t))))
    return np.array(pts)


def union_contains(regions: list[Region], P: np.ndarray) -> np.ndarray:
    """Çift-tek kuralı tüm halkalar üzerinden: ayrık bölgeler ve delikler doğal olarak çıkar."""
    acc = np.zeros(len(P), dtype=int)
    for p in rings(regions):
        acc += polygon_contains(P, ring_polyline(p)).astype(int)
    return (acc % 2) == 1


# ---------------------------------------------------------------- K4: dikdörtgen iç ofset


def test_offset_zero_raises():
    with pytest.raises(CamError):
        offset(Region(Profile.rectangle(0.0, 0.0, A_RECT, B_RECT)), 0.0)


def test_rectangle_inner_offset_sharp_corners():
    """40×20, r = 3 → (40−6)×(20−6) = 34×14 dikdörtgen, alan 476, çevre 96,
    köşeler (3,3), (37,3), (37,17), (3,17).

    İç ofsette dışbükey köşeler keskin kalır (yay yok): ham ofset doğruları köşede kesişir, 4. adımda budanır.
    """
    r = 3.0
    res = offset(Region(Profile.rectangle(0.0, 0.0, A_RECT, B_RECT)), r)
    assert len(res) == 1
    reg = res[0]
    assert reg.holes == []
    assert reg.area == pytest.approx((A_RECT - 2 * r) * (B_RECT - 2 * r), rel=1e-9)
    assert reg.outer.length == pytest.approx(2 * (A_RECT - 2 * r + B_RECT - 2 * r), rel=1e-9)
    assert all(isinstance(s, Line) for s in reg.outer.segments)
    corners = [(r, r), (A_RECT - r, r), (A_RECT - r, B_RECT - r), (r, B_RECT - r)]
    ends = [s.p0 for s in reg.outer.segments]
    for c in corners:
        assert any(close(c, e) for e in ends), c
    # her uç nokta iç dikdörtgenin sınırında
    ref = Egriler()
    ref.polygon(corners)
    assert np.all(ref.distance(np.array(ends)) <= 1e-9)


def test_rectangle_inner_offset_off_origin():
    """Konumdan bağımsız: (−7, 12) köşeli 25×18, r = 2.5 → 20×13, alan 260."""
    res = offset(Region(Profile.rectangle(-7.0, 12.0, 25.0, 18.0)), 2.5)
    assert len(res) == 1
    assert res[0].area == pytest.approx(20.0 * 13.0, rel=1e-9)
    bb = np.asarray(res[0].outer.bbox(), dtype=float).ravel()
    assert np.allclose(bb, [-4.5, 14.5, 15.5, 27.5], atol=1e-9)


@pytest.mark.parametrize("r", [10.0, 12.0, 30.0])
def test_rectangle_inner_offset_empty(r):
    """2r ≥ min(a, b) = 20 → boş liste."""
    assert offset(Region(Profile.rectangle(0.0, 0.0, A_RECT, B_RECT)), r) == []


def test_rectangle_inner_offset_just_fits():
    """r = 9.999 → 20.002 × 0.002 dikdörtgen (henüz boş değil)."""
    r = 9.999
    res = offset(Region(Profile.rectangle(0.0, 0.0, A_RECT, B_RECT)), r)
    assert len(res) == 1
    assert res[0].area == pytest.approx((A_RECT - 2 * r) * (B_RECT - 2 * r), rel=1e-9)


# ---------------------------------------------------------------- K5: dikdörtgen dış ofset


def test_rectangle_outer_offset():
    """40×20, d = −3: alan ab + 2r(a+b) + πr² = 800 + 360 + 9π, çevre 2(a+b) + 2πr = 120 + 6π.

    4 doğru + 4 çeyrek yay (R = r, süpürme π/2, CCW), yay merkezleri dikdörtgen köşelerinde
    (Minkowski toplamı).
    """
    r = 3.0
    res = offset(Region(Profile.rectangle(0.0, 0.0, A_RECT, B_RECT)), -r)
    assert len(res) == 1
    reg = res[0]
    assert reg.holes == []
    assert reg.area == pytest.approx(A_RECT * B_RECT + 2 * r * (A_RECT + B_RECT) + math.pi * r**2, rel=1e-9)
    assert reg.outer.length == pytest.approx(2 * (A_RECT + B_RECT) + 2 * math.pi * r, rel=1e-9)
    arcs = [s for s in reg.outer.segments if isinstance(s, Arc)]
    lines = [s for s in reg.outer.segments if isinstance(s, Line)]
    assert len(arcs) == 4
    assert len(lines) == 4
    for a in arcs:
        assert a.R == pytest.approx(r, abs=1e-9)
        assert a.sweep == pytest.approx(math.pi / 2, abs=1e-9)
        assert a.ccw is True
    for c in [(0.0, 0.0), (A_RECT, 0.0), (A_RECT, B_RECT), (0.0, B_RECT)]:
        assert sum(close(a.c, c) for a in arcs) == 1, c
    assert np.allclose(
        np.asarray(reg.outer.bbox(), dtype=float).ravel(), [-r, -r, A_RECT + r, B_RECT + r], atol=1e-9
    )


# ---------------------------------------------------------------- K6: daire ofseti


@pytest.mark.parametrize("ccw", [True, False])
@pytest.mark.parametrize("d", [3.0, -3.0, 9.5])
def test_circle_offset_single_arc(d, ccw):
    """R = 10 daire, d ofseti → aynı merkezli R − d yarıçaplı tek tam yay (yaylar korunur), alan π(R−d)²."""
    c, R = (5.0, -2.0), 10.0
    res = offset(Region(Profile.circle(c, R, ccw=ccw)), d)
    assert len(res) == 1
    reg = res[0]
    assert reg.holes == []
    assert len(reg.outer.segments) == 1
    a = reg.outer.segments[0]
    assert isinstance(a, Arc)
    assert close(a.c, c)
    assert a.R == pytest.approx(R - d, abs=1e-9)
    assert a.sweep == pytest.approx(2 * math.pi, abs=1e-9)
    assert reg.outer.area == pytest.approx(math.pi * (R - d) ** 2, rel=1e-9)


@pytest.mark.parametrize("d", [10.0, 12.0])
def test_circle_offset_empty(d):
    """d ≥ R → boş."""
    assert offset(Region(Profile.circle((0.0, 0.0), 10.0)), d) == []


def test_offset_profile_shortcut():
    """offset_profile(p, d) = offset(Region(p), d): R = 10 dairenin d = 4 ofseti alanı π·6²."""
    res = offset_profile(Profile.circle((0.0, 0.0), 10.0), 4.0)
    assert len(res) == 1
    assert res[0].area == pytest.approx(math.pi * 36.0, rel=1e-9)
    res2 = offset_profile(Profile.rectangle(0.0, 0.0, A_RECT, B_RECT), -1.0)
    assert total_area(res2) == pytest.approx(800.0 + 2 * 60.0 + math.pi, rel=1e-9)


# ---------------------------------------------------------------- K7: dar boğaz

W_BRIDGE = 4.0
DUMBBELL = [
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
]  # iki 20×20 kare, x ∈ [20, 30]'da w = 4 genişlikli köprü (y ∈ [8, 12]); CCW
REFLEX = [(20.0, 8.0), (30.0, 8.0), (30.0, 12.0), (20.0, 12.0)]


def test_dumbbell_area_formula_self_check():
    """Formülün kendi kontrolü (uygulamadan bağımsız): d = 1,5 için iki yoldan aynı alan.

    Formül: A = 840, P = 172, 8 dışbükey 90° köşe (cot 45° = 1), 4 içbükey 270° köşe (θ − π = π/2)
    → A(d) = 840 − 172d + 8d² − πd².
    Parça parça: iki 17×17 kare (578) + köprü şeridi 13 × 1 + 4 köşe dolgusu (d² − πd²/4).
    """
    d = 1.5
    formula = 840.0 - 172.0 * d + 8 * d**2 - math.pi * d**2
    pieces = 2 * (20 - 2 * d) ** 2 + (10 + 2 * d) * (W_BRIDGE - 2 * d) + 4 * (d**2 - math.pi * d**2 / 4)
    assert formula == pytest.approx(pieces, rel=1e-12)


def test_dumbbell_narrow_single_region():
    """d = 1,5 < w/2 = 2: tek bölge, alan 840 − 172d + 8d² − πd² (modül yorumu);
    içbükey köşelerde d yarıçaplı, merkezi köşede olan 4 yay (CW: köşede yol sağa döner)."""
    d = 1.5
    res = offset(Region(Profile.polygon(DUMBBELL)), d)
    assert len(res) == 1
    reg = res[0]
    assert reg.holes == []
    assert reg.area == pytest.approx(840.0 - 172.0 * d + 8 * d**2 - math.pi * d**2, rel=1e-9)
    assert reg.contains((25.0, 10.0))  # köprünün ortası
    arcs = [s for s in reg.outer.segments if isinstance(s, Arc)]
    assert len(arcs) == 4
    for a in arcs:
        assert a.R == pytest.approx(d, abs=1e-9)
        assert a.ccw is False
        assert a.sweep == pytest.approx(math.pi / 2, abs=1e-9)
    for v in REFLEX:
        assert sum(close(a.c, v) for a in arcs) == 1, v


def bulge_area(d: float, w: float) -> float:
    """d > w/2: köprü kopunca her karenin köprü tarafında kalan çıkıntı alanı.

    u = 20 − x (karenin sağ kenarından içeri), çıkıntı u ∈ [u₁, d], u₁ = √(d² − (w/2)²);
    y genişliği w − 2√(d² − u²) (iki içbükey köşe çemberinin dışı).
    ∫√(d² − u²) du = ½(u√(d² − u²) + d² asin(u/d)).
    """
    u1 = math.sqrt(d**2 - (w / 2) ** 2)

    def F(u: float) -> float:
        return 0.5 * (u * math.sqrt(max(d**2 - u**2, 0.0)) + d**2 * math.asin(min(u / d, 1.0)))

    return w * (d - u1) - 2 * (F(d) - F(u1))


def test_dumbbell_bulge_self_check():
    """El hesabı: d = 2,5, w = 4 → u₁ = 1,5; ∫ = 4,908739 − 3,510942 = 1,397797 → 4 − 2,795594 = 1,204405."""
    assert bulge_area(2.5, 4.0) == pytest.approx(1.204405, abs=2e-6)


def test_dumbbell_split_two_regions():
    """d = 2,5 > w/2: iki bölge. Her biri (20 − 2d)² + çıkıntı; sol bölge bbox [d, d, 20 − u₁, 20 − d]."""
    d = 2.5
    res = offset(Region(Profile.polygon(DUMBBELL)), d)
    assert len(res) == 2
    expected = (20 - 2 * d) ** 2 + bulge_area(d, W_BRIDGE)
    for reg in res:
        assert reg.holes == []
        assert reg.area == pytest.approx(expected, rel=1e-9)
    left = [r for r in res if r.contains((10.0, 10.0))]
    right = [r for r in res if r.contains((40.0, 10.0))]
    assert len(left) == 1 and len(right) == 1 and left[0] is not right[0]
    assert not any(r.contains((25.0, 10.0)) for r in res)
    u1 = math.sqrt(d**2 - (W_BRIDGE / 2) ** 2)
    assert np.allclose(
        np.asarray(left[0].outer.bbox(), dtype=float).ravel(), [d, d, 20.0 - u1, 20.0 - d], atol=1e-9
    )


# ---------------------------------------------------------------- K8: adalı bölge

SQ = 60.0  # dış kare kenarı
RHO = 5.0  # ada yarıçapı
CEN = (30.0, 30.0)


def island_region() -> Region:
    return Region(Profile.rectangle(0.0, 0.0, SQ, SQ), [Profile.circle(CEN, RHO)])


@pytest.mark.parametrize("d", [4.0, 12.0])
def test_island_grows(d):
    """Halka bölge: dış kare (60 − 2d) kenarlı, ada R + d yarıçaplı tek yay (CW), alan (60 − 2d)² − π(ρ + d)².

    Birleşme d* = (30 − ρ)/2 = 12,5'ten önce topoloji aynı: 1 bölge, 1 delik.
    """
    res = offset(island_region(), d)
    assert len(res) == 1
    reg = res[0]
    assert len(reg.holes) == 1
    h = reg.holes[0]
    assert len(h.segments) == 1
    a = h.segments[0]
    assert isinstance(a, Arc)
    assert a.ccw is False
    assert close(a.c, CEN)
    assert a.R == pytest.approx(RHO + d, abs=1e-9)
    assert h.area == pytest.approx(-math.pi * (RHO + d) ** 2, rel=1e-9)
    assert reg.area == pytest.approx((SQ - 2 * d) ** 2 - math.pi * (RHO + d) ** 2, rel=1e-9)


def test_island_merges_into_four_corners():
    """d = 14 > 12,5: büyüyen ada (R' = 19) küçülen kareye (yarı kenar h = 16) değer; R' < h√2 (22,6)
    olduğu için 4 köşe parçası kalır, delik yok.

    Kare ∩ daire = πR'² − 4 (R'² acos(h/R') − h√(R'² − h²))  (daire parçası alanı, h < R' < h√2).
    Her köşe = (4h² − kare ∩ daire) / 4.
    """
    d = 14.0
    h = SQ / 2 - d
    Rp = RHO + d
    inter = math.pi * Rp**2 - 4 * (Rp**2 * math.acos(h / Rp) - h * math.sqrt(Rp**2 - h**2))
    corner = (4 * h**2 - inter) / 4
    res = offset(island_region(), d)
    assert len(res) == 4
    assert len(rings(res)) == 4
    for reg in res:
        assert reg.holes == []
        assert reg.area == pytest.approx(corner, rel=1e-9)


def test_island_vanishes():
    """d = 16: h√2 = 14√2 = 19,8 < ρ + d = 21 → köşeler de kaybolur, sonuç boş.
    (Köşe kaybolma eşiği (30 − d)√2 = 5 + d → d = (30√2 − 5)/(√2 + 1) ≈ 15,50.)"""
    assert offset(island_region(), 16.0) == []


def test_island_outer_offset_shrinks_hole():
    """Dış ofset d = −2: dış kare 64×64 köşe yaylı, delik 5 − 2 = 3 yarıçaplı.
    Alan = 60² + 2·2·(60+60) + 4π − 9π. d = −6 ≥ ρ: delik kaybolur → 60² + 2·6·120 + 36π."""
    res = offset(island_region(), -2.0)
    assert len(res) == 1 and len(res[0].holes) == 1
    assert res[0].area == pytest.approx(SQ**2 + 2 * 2.0 * 2 * SQ + 4 * math.pi - 9 * math.pi, rel=1e-9)
    res5 = offset(island_region(), -6.0)
    assert len(res5) == 1 and res5[0].holes == []
    assert res5[0].area == pytest.approx(SQ**2 + 2 * 6.0 * 2 * SQ + 36 * math.pi, rel=1e-9)


# ---------------------------------------------------------------- K9: rastgele çokgenler


def convex_polygon(seed: int) -> list[tuple[float, float]]:
    """Yarıçapı 10 olan çember üzerinde rastgele açılı (en az ~0,25 rad aralıklı) 5–8 köşe → dışbükey, CCW."""
    rng = np.random.default_rng(seed)
    n = int(rng.integers(5, 9))
    gaps = rng.uniform(1.0, 3.0, n)
    ang = np.cumsum(gaps / gaps.sum() * 2 * math.pi) + rng.uniform(0, 2 * math.pi)
    return [(10 * math.cos(t), 10 * math.sin(t)) for t in ang]


def star_polygon(seed: int) -> list[tuple[float, float]]:
    """Merkeze göre yıldız biçimli, yarıçapları [5, 10] rastgele 7–10 köşe → genelde içbükey, CCW."""
    rng = np.random.default_rng(1000 + seed)
    n = int(rng.integers(7, 11))
    ang = (np.arange(n) + rng.uniform(-0.25, 0.25, n)) * 2 * math.pi / n
    rad = rng.uniform(5.0, 10.0, n)
    return [(float(r * math.cos(t)), float(r * math.sin(t))) for r, t in zip(rad, ang, strict=True)]


POLYS = [("dis", convex_polygon(s)) for s in range(3)] + [("yildiz", star_polygon(s)) for s in range(4)]
POLY_IDS = [f"{k}{i}" for i, (k, _) in enumerate(POLYS)]


@pytest.mark.parametrize("d", [0.8, 2.0, -0.8, -2.5])
@pytest.mark.parametrize("poly", [p for _, p in POLYS], ids=POLY_IDS)
def test_random_offset_distance_property(poly, d):
    """Her sonuç parçası üzerindeki örnek noktaların ∂Ω'ya uzaklığı |d| (± 1e-9), doğru tarafta;
    halka yönü kuralı (dış CCW, delik CW)."""
    res = offset(Region(Profile.polygon(poly)), d)
    bnd = Egriler()
    bnd.polygon(poly)
    pts = np.array([tuple(s.point(float(t))) for s in segs(res) for t in np.linspace(0.0, 1.0, 9)])
    assert len(pts) > 0
    dist = bnd.distance(pts)
    assert np.max(np.abs(dist - abs(d))) <= 1e-9
    inside = polygon_contains(pts, poly)
    assert np.all(inside) if d > 0 else not np.any(inside)
    for reg in res:
        assert reg.outer.area > 0
        assert all(h.area < 0 for h in reg.holes)


@pytest.mark.parametrize("d", [0.8, 2.0, -0.8, -2.5])
@pytest.mark.parametrize("poly", [p for _, p in POLYS], ids=POLY_IDS)
def test_random_offset_set_membership(poly, d):
    """Küme tanımı (ızgara, 0,05 mm pay): d > 0 → p ∈ sonuç ⇔ p ∈ Ω ve dist ≥ d;
    d < 0 → p ∈ sonuç ⇔ p ∈ Ω veya dist ≤ |d|. Sınıra 0,05'ten yakın noktalar atlanır."""
    res = offset(Region(Profile.polygon(poly)), d)
    bnd = Egriler()
    bnd.polygon(poly)
    P = grid(-13.0, 13.0, -13.0, 13.0, 40, 40)
    dist = bnd.distance(P)
    in_omega = polygon_contains(P, poly)
    if d > 0:
        expected = in_omega & (dist >= d)
    else:
        expected = in_omega | (dist <= -d)
    clear = np.abs(dist - abs(d)) > 0.05
    got = union_contains(res, P) if res else np.zeros(len(P), dtype=bool)
    assert np.array_equal(got[clear], expected[clear])


@pytest.mark.parametrize("d1, d2", [(0.6, 0.9), (1.5, 1.2), (-0.6, -0.9)])
@pytest.mark.parametrize("poly", [p for _, p in POLYS], ids=POLY_IDS)
def test_random_offset_composition(poly, d1, d2):
    """Minkowski birleşme özelliği: (Ω ⊖ B_d₁) ⊖ B_d₂ = Ω ⊖ B_(d₁+d₂) (dış ofsette ⊕ için de geçerli).
    Alan göreli 1e-9; iki adımlı sonucun ∂Ω'ya uzaklığı |d₁ + d₂| (± 1e-9)."""
    region = Region(Profile.polygon(poly))
    two_step = [r2 for r1 in offset(region, d1) for r2 in offset(r1, d2)]
    one_step = offset(region, d1 + d2)
    assert total_area(two_step) == pytest.approx(total_area(one_step), rel=1e-9, abs=1e-12)
    assert len(two_step) == len(one_step)
    if two_step:
        bnd = Egriler()
        bnd.polygon(poly)
        pts = np.array([tuple(s.point(float(t))) for s in segs(two_step) for t in np.linspace(0.0, 1.0, 7)])
        assert np.max(np.abs(bnd.distance(pts) - abs(d1 + d2))) <= 1e-9
