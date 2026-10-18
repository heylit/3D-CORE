"""SPEC 03 — cam/profile.py ve cam/geom2d.py testleri (K1–K3).

Testler sadece SPEC 03 "Arayüz" bölümündeki imzalardan yazıldı; uygulama kodu okunmadı.
Beklenen değerler el hesabı / kapalı formdur (kaynak her testin yorumunda):
- Yönlü alan (Green teoremi): A = Σ ½(x₀y₁ − x₁y₀) + Σ_yay ±½R²(Δθ − sin Δθ)  (O'Rourke, Bölüm 1).
- Kesişimler: doğru–doğru doğrusal sistem, doğru–daire ikinci derece denklem, daire–daire
  radikal eksen (x = (d² + R₁² − R₂²) / 2d).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.geom2d import LINK_TOL, TOL, distance, distance_to_region, intersect, winding
from cam.model import CamError
from cam.profile import Arc, Line, Profile, Region

A_RECT = 40.0  # dikdörtgen kenarı a [mm]
B_RECT = 20.0  # dikdörtgen kenarı b [mm]
R5 = 5.0  # daire yarıçapı [mm]


def close(p, q, tol: float = 1e-9) -> bool:
    """İki 2D nokta tol içinde aynı mı."""
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol


def bbox4(profile: Profile) -> np.ndarray:
    """bbox() çıktısını [xmin, ymin, xmax, ymax] düzlüğüne getirir ((min, max) çifti veya 4'lü)."""
    return np.asarray(profile.bbox(), dtype=float).ravel()


# ---------------------------------------------------------------- K1: doğrulamalar, yön kuralı


def test_constants():
    # SPEC 03 arayüzündeki sabitler
    assert TOL == 1e-9
    assert LINK_TOL == 1e-7


def test_line_zero_length_raises():
    """Boy < TOL olan doğru geçersiz: boy 0 ve boy 1e-10 < 1e-9."""
    with pytest.raises(CamError):
        Line((1.0, 2.0), (1.0, 2.0))
    with pytest.raises(CamError):
        Line((0.0, 0.0), (1e-10, 0.0))


def test_arc_inconsistent_radius_raises():
    """|p0−c| = 5, |p1−c| = 5,001 → fark 1e-3 > ARC_TOL (1e-6)."""
    with pytest.raises(CamError):
        Arc((5.0, 0.0), (0.0, 5.001), (0.0, 0.0), True)


def test_arc_zero_radius_raises():
    """p0 = p1 = c → R = 0 < R_MIN."""
    with pytest.raises(CamError):
        Arc((1.0, 1.0), (1.0, 1.0), (1.0, 1.0), True)


def test_arc_R_and_sweep():
    """Çeyrek yay (5,0)→(0,5), merkez 0: CCW süpürme π/2, CW süpürme 2π − π/2 = 3π/2; tam daire 2π."""
    q_ccw = Arc((R5, 0.0), (0.0, R5), (0.0, 0.0), True)
    q_cw = Arc((R5, 0.0), (0.0, R5), (0.0, 0.0), False)
    full = Arc((R5, 0.0), (R5, 0.0), (0.0, 0.0), True)
    assert q_ccw.R == pytest.approx(R5, abs=1e-12)
    assert q_ccw.sweep == pytest.approx(math.pi / 2, abs=1e-12)
    assert q_cw.sweep == pytest.approx(3 * math.pi / 2, abs=1e-12)
    assert full.sweep == pytest.approx(2 * math.pi, abs=1e-12)
    # boy s = R·Δθ
    assert q_ccw.length == pytest.approx(R5 * math.pi / 2, rel=1e-12)
    assert q_cw.length == pytest.approx(R5 * 3 * math.pi / 2, rel=1e-12)
    assert full.length == pytest.approx(2 * math.pi * R5, rel=1e-12)


def test_line_point_length_reversed_split():
    """(0,0)→(3,4): boy 5 (3-4-5 üçgeni); point(0.5) = (1.5, 2); split(0.2) boyları 1 ve 4."""
    ln = Line((0.0, 0.0), (3.0, 4.0))
    assert ln.length == pytest.approx(5.0, rel=1e-12)
    assert close(ln.point(0.0), (0.0, 0.0))
    assert close(ln.point(1.0), (3.0, 4.0))
    assert close(ln.point(0.5), (1.5, 2.0))
    rv = ln.reversed()
    assert close(rv.p0, (3.0, 4.0)) and close(rv.p1, (0.0, 0.0))
    s1, s2 = ln.split(0.2)
    assert s1.length == pytest.approx(1.0, rel=1e-12)
    assert s2.length == pytest.approx(4.0, rel=1e-12)
    assert close(s1.p1, (0.6, 0.8)) and close(s2.p0, (0.6, 0.8))


def test_arc_point_reversed_split():
    """Çeyrek CCW yay (5,0)→(0,5): orta nokta 45°'de (5/√2, 5/√2); CW çeyrek (0,5)→(5,0) aynı orta nokta.

    reversed(): uçlar yer değiştirir, yön tersine döner, süpürme aynı kalır.
    split(0.5): iki parça π/4 süpürmeli, birleşim noktası point(0.5).
    """
    s = R5 / math.sqrt(2.0)
    a = Arc((R5, 0.0), (0.0, R5), (0.0, 0.0), True)
    assert close(a.point(0.5), (s, s))
    rv = a.reversed()
    assert close(rv.p0, (0.0, R5)) and close(rv.p1, (R5, 0.0))
    assert rv.ccw is False
    assert rv.sweep == pytest.approx(math.pi / 2, abs=1e-12)
    assert close(rv.point(0.5), (s, s))
    a1, a2 = a.split(0.5)
    assert a1.sweep == pytest.approx(math.pi / 4, abs=1e-12)
    assert a2.sweep == pytest.approx(math.pi / 4, abs=1e-12)
    assert close(a1.p1, (s, s)) and close(a2.p0, (s, s))
    # CW yayın orta noktası: (5,0)'dan saat yönünde 3π/2 → orta nokta açısı −3π/4
    b = Arc((R5, 0.0), (0.0, R5), (0.0, 0.0), False)
    assert close(b.point(0.5), (R5 * math.cos(-3 * math.pi / 4), R5 * math.sin(-3 * math.pi / 4)))


def test_profile_disconnected_raises():
    """İkinci parça birinciden 1e-3 kopuk (> LINK_TOL = 1e-7)."""
    with pytest.raises(CamError):
        Profile([Line((0.0, 0.0), (10.0, 0.0)), Line((10.0, 1e-3), (10.0, 10.0))], closed=False)


def test_profile_gap_within_link_tol_accepted():
    """Kopukluk 1e-8 < LINK_TOL: kabul edilir."""
    p = Profile([Line((0.0, 0.0), (10.0, 0.0)), Line((10.0, 1e-8), (10.0, 10.0))], closed=False)
    assert len(p.segments) == 2


def test_closed_profile_not_closing_raises():
    """Uç uca ama son nokta (10,10) ≠ ilk nokta (0,0): kapalı profil olamaz; açık olarak geçerli."""
    segs = [Line((0.0, 0.0), (10.0, 0.0)), Line((10.0, 0.0), (10.0, 10.0))]
    with pytest.raises(CamError):
        Profile(list(segs), closed=True)
    Profile(list(segs), closed=False)


def test_region_open_ring_raises():
    """Açık halka bölge sınırı olamaz (dış veya delik)."""
    open_p = Profile([Line((0.0, 0.0), (10.0, 0.0)), Line((10.0, 0.0), (10.0, 10.0))], closed=False)
    with pytest.raises(CamError):
        Region(open_p)
    with pytest.raises(CamError):
        Region(Profile.rectangle(-20.0, -20.0, 40.0, 40.0), [open_p])


def test_constructors_orientation():
    """rectangle → CCW (alan > 0); circle(ccw=False) → CW (alan < 0); polygon verilen sırada."""
    assert Profile.rectangle(0.0, 0.0, A_RECT, B_RECT).area > 0
    assert Profile.circle((0.0, 0.0), R5, ccw=True).area > 0
    assert Profile.circle((0.0, 0.0), R5, ccw=False).area < 0
    cw_square = Profile.polygon([(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)])
    assert cw_square.area == pytest.approx(-1.0, rel=1e-12)
    assert len(cw_square.segments) == 4


def test_region_orientation_rule():
    """Yön kuralı: dış halka CCW, delikler CW — kullanıcı ters verse de çevrilir."""
    outer_cw = Profile.rectangle(0.0, 0.0, A_RECT, B_RECT).reversed()
    hole_ccw = Profile.circle((20.0, 10.0), 3.0, ccw=True)
    reg = Region(outer_cw, [hole_ccw])
    assert reg.outer.area > 0
    assert reg.holes[0].area < 0
    reg2 = Region(Profile.rectangle(0.0, 0.0, A_RECT, B_RECT), [Profile.circle((20.0, 10.0), 3.0, ccw=False)])
    assert reg2.outer.area > 0
    assert reg2.holes[0].area < 0


# ---------------------------------------------------------------- K2: alan, boy, contains


def test_rectangle_area_length_bbox():
    """a×b dikdörtgen: alan ab = 800, çevre 2(a+b) = 120, bbox [x0, y0, x0+a, y0+b]."""
    p = Profile.rectangle(5.0, -3.0, A_RECT, B_RECT)
    assert p.area == pytest.approx(A_RECT * B_RECT, rel=1e-9)
    assert p.length == pytest.approx(2 * (A_RECT + B_RECT), rel=1e-9)
    assert np.allclose(bbox4(p), [5.0, -3.0, 5.0 + A_RECT, -3.0 + B_RECT], atol=1e-9)


def test_circle_area_length_bbox():
    """Daire: alan πR², çevre 2πR, bbox [cx−R, cy−R, cx+R, cy+R] (yay uçları değil, eksen uçları)."""
    p = Profile.circle((2.0, 3.0), R5)
    assert p.area == pytest.approx(math.pi * R5**2, rel=1e-9)
    assert p.length == pytest.approx(2 * math.pi * R5, rel=1e-9)
    assert np.allclose(bbox4(p), [2.0 - R5, 3.0 - R5, 2.0 + R5, 3.0 + R5], atol=1e-9)


def test_semicircle_plus_diameter_area():
    """Üst yarım daire (CCW) + çap: A = πR²/2.

    Green: yay için shoelace kirişi ½(R·0 − (−R)·0) = 0 + ½R²(π − sin π) = πR²/2; çap doğrusu
    (−R,0)→(R,0) katkısı 0. CW (ters) profilde işaret ters: −πR²/2. Boy πR + 2R.
    """
    p = Profile([Arc((R5, 0.0), (-R5, 0.0), (0.0, 0.0), True), Line((-R5, 0.0), (R5, 0.0))])
    assert p.area == pytest.approx(math.pi * R5**2 / 2, rel=1e-9)
    assert p.reversed().area == pytest.approx(-math.pi * R5**2 / 2, rel=1e-9)
    assert p.length == pytest.approx(math.pi * R5 + 2 * R5, rel=1e-9)
    assert np.allclose(bbox4(p), [-R5, 0.0, R5, R5], atol=1e-9)


def test_three_quarter_arc_area():
    """Δθ > π yay: (R,0)'dan CCW 3π/2 ile (0,−R)'ye, sonra doğru ile geri.

    Geometri: 3/4 daire dilimi (3πR²/4) + üçgen (0,0),(0,−R),(R,0) (R²/2) → A = R²(3π/4 + 1/2).
    Green kontrolü: yay kirişi ½(R·(−R) − 0) = −R²/2, daire parçası ½R²(3π/2 + 1),
    doğru ½(0·0 − R·(−R)) = R²/2 → toplam R²(3π/4 + 1/2). Aynı.
    """
    p = Profile([Arc((R5, 0.0), (0.0, -R5), (0.0, 0.0), True), Line((0.0, -R5), (R5, 0.0))])
    assert p.area == pytest.approx(R5**2 * (3 * math.pi / 4 + 0.5), rel=1e-9)


def test_cw_rectangle_area_negative():
    """CW profilde yönlü alan işareti ters: −ab."""
    p = Profile.polygon([(0.0, 0.0), (0.0, B_RECT), (A_RECT, B_RECT), (A_RECT, 0.0)])
    assert p.area == pytest.approx(-A_RECT * B_RECT, rel=1e-9)
    assert p.reversed().area == pytest.approx(A_RECT * B_RECT, rel=1e-9)


def test_region_with_hole_area_and_contains():
    """40×20 dikdörtgen − (20,10) merkezli R=3 delik: alan ab − π·3² ; contains: iç / dış / delik içi."""
    reg = Region(Profile.rectangle(0.0, 0.0, A_RECT, B_RECT), [Profile.circle((20.0, 10.0), 3.0)])
    assert reg.area == pytest.approx(A_RECT * B_RECT - math.pi * 9.0, rel=1e-9)
    assert reg.contains((5.0, 5.0))
    assert reg.contains((20.0, 14.0))  # delik dışında, deliğin hemen üstü
    assert not reg.contains((-1.0, 5.0))  # dış sınırın dışı
    assert not reg.contains((50.0, 10.0))
    assert not reg.contains((20.0, 10.0))  # deliğin merkezi
    assert not reg.contains((21.0, 11.0))  # deliğin içi (√2 < 3)


def test_region_contains_with_arcs():
    """Yarım daire bölge: (0,4) içerde (4 < 5), (0,−1) dışarda (çapın altı), (4,4) dışarda (√32 > 5)."""
    reg = Region(Profile([Arc((R5, 0.0), (-R5, 0.0), (0.0, 0.0), True), Line((-R5, 0.0), (R5, 0.0))]))
    assert reg.contains((0.0, 4.0))
    assert not reg.contains((0.0, -1.0))
    assert not reg.contains((4.0, 4.0))


def test_winding_numbers():
    """Sarım sayısı: CCW daire içi +1, CW daire içi −1, dışı 0; dikdörtgen içi +1."""
    ccw = Profile.circle((0.0, 0.0), R5, ccw=True)
    cw = Profile.circle((0.0, 0.0), R5, ccw=False)
    assert winding((1.0, 1.0), ccw) == 1
    assert winding((1.0, 1.0), cw) == -1
    assert winding((6.0, 0.0), ccw) == 0
    assert winding((10.0, 5.0), Profile.rectangle(0.0, 0.0, A_RECT, B_RECT)) == 1
    assert winding((-1.0, 5.0), Profile.rectangle(0.0, 0.0, A_RECT, B_RECT)) == 0


# ---------------------------------------------------------------- K3: kesişimler ve uzaklık


def distinct_points(seg, params, tol: float = 1e-9) -> list[tuple[float, float]]:
    """intersect sonuçlarından seg üzerindeki farklı noktalar (teğette çift kök tek sayılır)."""
    pts: list[tuple[float, float]] = []
    for t in params:
        q = tuple(seg.point(t))
        if not any(close(q, r, tol) for r in pts):
            pts.append(q)
    return pts


def check_hits(a, b, expected: list[tuple[float, float]]) -> None:
    """intersect(a, b) noktaları a.point(t_a) = b.point(t_b) = beklenen; parametreler [0, 1]'de."""
    hits = intersect(a, b)
    for ta, tb in hits:
        assert -1e-12 <= ta <= 1 + 1e-12 and -1e-12 <= tb <= 1 + 1e-12
        assert close(a.point(ta), b.point(tb), 1e-9)
    pts = distinct_points(a, [h[0] for h in hits])
    assert len(pts) == len(expected)
    for e in expected:
        assert any(close(e, q, 1e-9) for q in pts), (e, pts)


def test_line_line_cross():
    """(0,0)→(2,2) ve (0,2)→(2,0): kesişim (1,1), t_a = t_b = 0,5."""
    a = Line((0.0, 0.0), (2.0, 2.0))
    b = Line((0.0, 2.0), (2.0, 0.0))
    hits = intersect(a, b)
    assert len(hits) == 1
    assert hits[0][0] == pytest.approx(0.5, abs=1e-12)
    assert hits[0][1] == pytest.approx(0.5, abs=1e-12)


def test_line_line_none():
    """Paralel doğrular kesişmez; doğruların uzantıları (5,5)'te kesişir ama parçalar dışında."""
    assert intersect(Line((0.0, 0.0), (1.0, 0.0)), Line((0.0, 1.0), (1.0, 1.0))) == []
    assert intersect(Line((0.0, 0.0), (1.0, 1.0)), Line((10.0, 0.0), (9.0, 1.0))) == []


def test_line_circle_two_points():
    """y = 0 doğrusu R=5 tam daireyi (±5, 0)'da keser (x² = R²)."""
    check_hits(
        Line((-10.0, 0.0), (10.0, 0.0)), Arc((R5, 0.0), (R5, 0.0), (0.0, 0.0), True), [(-R5, 0.0), (R5, 0.0)]
    )


def test_line_circle_one_point_segment_end_inside():
    """(0,0)→(10,0) parçası dairenin içinden başlar: tek kesişim (5, 0)."""
    check_hits(Line((0.0, 0.0), (10.0, 0.0)), Arc((0.0, R5), (0.0, R5), (0.0, 0.0), True), [(R5, 0.0)])


def test_line_circle_tangent():
    """y = R doğrusu daireye (0, R)'de teğet: x² = R² − R² = 0 → tek nokta."""
    check_hits(Line((-10.0, R5), (10.0, R5)), Arc((R5, 0.0), (R5, 0.0), (0.0, 0.0), True), [(0.0, R5)])


def test_line_circle_miss():
    """y = 6 > R: x² = 25 − 36 < 0 → kesişim yok."""
    assert intersect(Line((-10.0, 6.0), (10.0, 6.0)), Arc((R5, 0.0), (R5, 0.0), (0.0, 0.0), True)) == []


def test_line_arc_outside_sweep_dropped():
    """Üst yarım yay (CCW (5,0)→(−5,0)) ile x = 0 doğrusu: daire çözümleri (0, ±5); (0,−5) süpürme dışında."""
    upper = Arc((R5, 0.0), (-R5, 0.0), (0.0, 0.0), True)
    check_hits(Line((0.0, -10.0), (0.0, 10.0)), upper, [(0.0, R5)])
    # Ters sırada çağrı aynı noktayı verir (parametreler yer değiştirir)
    check_hits(upper, Line((0.0, -10.0), (0.0, 10.0)), [(0.0, R5)])


def test_arc_arc_two_circles():
    """R=5 daireler, merkezler (0,0) ve (6,0): radikal eksen x = (36 + 25 − 25)/12 = 3,
    y = ±√(25 − 9) = ±4."""
    c1 = Arc((R5, 0.0), (R5, 0.0), (0.0, 0.0), True)
    c2 = Arc((11.0, 0.0), (11.0, 0.0), (6.0, 0.0), True)
    check_hits(c1, c2, [(3.0, 4.0), (3.0, -4.0)])


def test_arc_arc_outside_sweep_dropped():
    """Aynı iki daire, sadece üst yarı yaylar: (3,−4) her iki yayın süpürmesi dışında → sadece (3,4)."""
    u1 = Arc((R5, 0.0), (-R5, 0.0), (0.0, 0.0), True)
    u2 = Arc((11.0, 0.0), (1.0, 0.0), (6.0, 0.0), True)
    check_hits(u1, u2, [(3.0, 4.0)])
    # Alt yarı yay (CW (5,0)→(−5,0)) ile üst yarı yay: sadece (3,−4) alt yayda, (3,4) üstte → kesişim yok
    l1 = Arc((R5, 0.0), (-R5, 0.0), (0.0, 0.0), False)
    assert intersect(l1, u2) == []


def test_arc_arc_disjoint_and_concentric():
    """Merkezler arası 20 > 5 + 5 → yok; eş merkezli farklı yarıçap → yok."""
    c1 = Arc((R5, 0.0), (R5, 0.0), (0.0, 0.0), True)
    assert intersect(c1, Arc((25.0, 0.0), (25.0, 0.0), (20.0, 0.0), True)) == []
    assert intersect(c1, Arc((3.0, 0.0), (3.0, 0.0), (0.0, 0.0), True)) == []


def test_distance_point_line():
    """(0,0)→(2,0) parçası: (1,1) dik uzaklık 1; (3,1) uca uzaklık √2; parça üzerinde 0."""
    ln = Line((0.0, 0.0), (2.0, 0.0))
    assert distance((1.0, 1.0), ln) == pytest.approx(1.0, abs=1e-12)
    assert distance((3.0, 1.0), ln) == pytest.approx(math.sqrt(2.0), abs=1e-12)
    assert distance((0.5, 0.0), ln) == pytest.approx(0.0, abs=1e-12)


def test_distance_point_arc():
    """Üst yarım yay R=5: (0,10) → 10 − 5 = 5; merkez → 5; (0,−3) süpürme dışı → uç (±5,0)'a √(25+9) = √34."""
    upper = Arc((R5, 0.0), (-R5, 0.0), (0.0, 0.0), True)
    assert distance((0.0, 10.0), upper) == pytest.approx(5.0, abs=1e-12)
    assert distance((0.0, 0.0), upper) == pytest.approx(5.0, abs=1e-12)
    assert distance((0.0, -3.0), upper) == pytest.approx(math.sqrt(34.0), abs=1e-12)
    assert distance((3.0, 4.0), upper) == pytest.approx(0.0, abs=1e-12)


def test_distance_to_region():
    """40×20 dikdörtgen + (20,10) merkezli R=3 delik.

    (5,5): en yakın kenar 5 (sol ve alt kenar). (20,15): deliğe 5 − 3 = 2. (20,10): deliğe 3.
    (−3,−4): köşeye 5 (dış nokta da sınıra uzaklığını verir).
    """
    reg = Region(Profile.rectangle(0.0, 0.0, A_RECT, B_RECT), [Profile.circle((20.0, 10.0), 3.0)])
    assert distance_to_region((5.0, 5.0), reg) == pytest.approx(5.0, abs=1e-12)
    assert distance_to_region((20.0, 15.0), reg) == pytest.approx(2.0, abs=1e-12)
    assert distance_to_region((20.0, 10.0), reg) == pytest.approx(3.0, abs=1e-12)
    assert distance_to_region((-3.0, -4.0), reg) == pytest.approx(5.0, abs=1e-12)
