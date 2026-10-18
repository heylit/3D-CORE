"""SPEC 19 — analitik yardımcılar ve malzeme ızgarası (K1–K3).

Testler yalnızca SPEC 19 "Teori", "Arayüz" ve "Kabul kriterleri" metninden yazıldı; cam/adaptive.py gövdeleri
okunmadı. Beklenen değerler SPEC'teki kapalı formüllerdir:
1. Düz duvar: φ = arccos(1 − a_e/r), a_e = r(1 − cos φ).
2. İçbükey daire: cos φ = (R_p² − ρ² − r²) / (2ρr); Δ(ρ) = ρ + r − √(ρ² + r² + 2ρr·cos φ), ρ → ∞: Δ → r(1 −
cos φ).
3. Trokoid ön noktası: cos φ_max = ((ρ + r)² − d² − r²) / (2dr), d = ρ + p;
   p(ρ, φ_t) = −r·cos φ_t + √((ρ + r)² − r²·sin² φ_t) − ρ.
4. Ek A1: döngü boyunca en büyük temas φ_loop(ρ, r, p) — test tarafında adaptref.loop_phi_ref ile bağımsız
hesaplanır.
Ölçüm adımı: temas açısı tanımında takımın gelişi [a, b] kısa (s = 1e-3 mm) tutulur; tanımdaki
dist(q, [a, b]) ≥ r koşulunun yan bantları ~s/(2r) radyan, toleransın yanında ihmal edilir.
Kaynak: Sandvik Coromant, Metal Cutting Technical Guide (temas açısı); Altintas, Manufacturing Automation,
Bölüm 2.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.adaptive import (
    MaterialGrid,
    ae_to_engagement,
    engagement_to_ae,
    spiral_spacing,
    trochoid_loop_engagement,
    trochoid_loop_pitch,
    trochoid_pitch,
)
from cam.model import CamError
from cam.profile import Profile, Region
from tests.cam.adaptref import loop_phi_ref, tol_phi

D = 10.0
r = D / 2
N_ALPHA = 1440
S = 1e-3  # ölçüm adımının boyu [mm]
RNG_SEED = 20261018


def rect_region(x0: float, y0: float, a: float, b: float, holes=()) -> Region:
    return Region(Profile.rectangle(x0, y0, a, b), [*holes])


def shifts(h: float, k: int = 3) -> list[tuple[float, float]]:
    """Izgara kaymaları: (0, 0) ve k − 1 rastgele (0..h)² kayma (sabit tohum)."""
    rng = np.random.default_rng(RNG_SEED)
    return [(0.0, 0.0)] + [tuple(rng.uniform(0.0, h, 2)) for _ in range(k - 1)]


# ---------------------------------------------------------------- K1 analitik yardımcılar


@pytest.mark.parametrize("ae", [0.01, 0.5, 1.0, 2.5, 5.0, 7.5, 9.9, 10.0])
def test_k1_ae_engagement_roundtrip(ae):
    phi = ae_to_engagement(ae, D)
    assert phi == pytest.approx(math.degrees(math.acos(1.0 - 2.0 * ae / D)), abs=1e-12)
    assert engagement_to_ae(phi, D) == pytest.approx(ae, abs=1e-12)


@pytest.mark.parametrize("phi", [1.0, 15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 150.0, 179.0, 180.0])
def test_k1_engagement_ae_roundtrip(phi):
    ae = engagement_to_ae(phi, D)
    assert ae == pytest.approx(r * (1.0 - math.cos(math.radians(phi))), abs=1e-12)
    assert ae_to_engagement(ae, D) == pytest.approx(phi, abs=1e-9)


def test_k1_special_values():
    assert ae_to_engagement(r, D) == pytest.approx(90.0, abs=1e-12)
    assert ae_to_engagement(D, D) == pytest.approx(180.0, abs=1e-12)
    assert engagement_to_ae(90.0, D) == pytest.approx(r, abs=1e-12)
    assert engagement_to_ae(180.0, D) == pytest.approx(D, abs=1e-12)


@pytest.mark.parametrize("phi", [20.0, 45.0, 60.0, 90.0, 135.0])
def test_k1_spiral_spacing_limit_is_straight_wall(phi):
    """ρ → ∞: Δ → r(1 − cos φ) (düz duvar).

    Not: formül 2'nin açılımı Δ(ρ) = r(1 − cos φ) + r²·sin²φ / (2ρ) + O(ρ⁻²); SPEC K1'deki "ρ = 1e6, göreli
    1e-6"
    bu 1/ρ terimi yüzünden analitik olarak tutmaz (φ = 90°'de göreli fark 2,5e-6). Bu yüzden ρ = 1e6'da fark
    r²/(2ρ) sınırıyla, göreli 1e-6 ise ρ = 1e8'de (1/ρ terimi < 3e-8) sınanır.
    """
    beklenen = r * (1.0 - math.cos(math.radians(phi)))
    assert abs(spiral_spacing(1e6, r, phi) - beklenen) <= r * r / (2 * 1e6)
    assert spiral_spacing(1e8, r, phi) == pytest.approx(beklenen, rel=1e-6)


@pytest.mark.parametrize("rho", [2.0, 5.0, 12.0, 40.0])
@pytest.mark.parametrize("phi", [30.0, 60.0, 90.0])
def test_k1_spiral_spacing_satisfies_formula2(rho, phi):
    """Önceki tur R_p = (ρ − Δ) + r yarıçaplı daireyi boşaltmışsa formül 2 tam olarak φ verir."""
    delta = spiral_spacing(rho, r, phi)
    assert delta > 0
    Rp = rho - delta + r
    cos_phi = (Rp**2 - rho**2 - r**2) / (2.0 * rho * r)
    assert math.degrees(math.acos(cos_phi)) == pytest.approx(phi, abs=1e-9)


@pytest.mark.parametrize("rho", [0.05, 1.0, 2.5, 4.0, 10.0])
@pytest.mark.parametrize("phi_t", [10.0, 45.0, 60.0, 90.0, 120.0, 170.0])
def test_k1_trochoid_pitch_satisfies_formula3(rho, phi_t):
    p = trochoid_pitch(rho, r, phi_t)
    assert p > 0
    d = rho + p
    cos_max = ((rho + r) ** 2 - d**2 - r**2) / (2.0 * d * r)
    assert math.degrees(math.acos(cos_max)) == pytest.approx(phi_t, abs=1e-9)


def test_k1_trochoid_pitch_closed_form():
    rho, phi = 2.5, 60.0
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    beklenen = -r * c + math.sqrt((rho + r) ** 2 - r**2 * s**2) - rho
    assert trochoid_pitch(rho, r, phi) == pytest.approx(beklenen, abs=1e-12)


@pytest.mark.parametrize(
    "call",
    [
        lambda: ae_to_engagement(0.0, D),
        lambda: ae_to_engagement(-1.0, D),
        lambda: ae_to_engagement(D * 1.001, D),
        lambda: engagement_to_ae(0.0, D),
        lambda: engagement_to_ae(-10.0, D),
        lambda: engagement_to_ae(180.5, D),
        lambda: spiral_spacing(0.0, r, 60.0),
        lambda: spiral_spacing(-3.0, r, 60.0),
        lambda: spiral_spacing(10.0, 0.0, 60.0),
        lambda: spiral_spacing(10.0, -r, 60.0),
        lambda: trochoid_pitch(0.0, r, 60.0),
        lambda: trochoid_pitch(-1.0, r, 60.0),
        lambda: trochoid_pitch(2.5, r, 0.0),
        lambda: trochoid_pitch(2.5, r, 180.0),
        lambda: trochoid_pitch(2.5, r, -30.0),
    ],
)
def test_k1_out_of_range_raises(call):
    with pytest.raises(CamError):
        call()


# ---------------------------------------------------------------- K1a (Ek A) döngü temas açısı ve aralığı

EK_A_TABLO = [(2.5, 60.0, 67.9), (2.5, 90.0, 118.2), (5.0, 45.0, 46.7), (1.0, 30.0, 31.6)]


@pytest.mark.parametrize("rho,phi,tablo", EK_A_TABLO)
def test_k1a_loop_engagement_table(rho, phi, tablo):
    got = trochoid_loop_engagement(rho, r, trochoid_pitch(rho, r, phi))
    assert got >= phi - 0.1  # ön nokta (formül 3) alt sınırdır
    assert got == pytest.approx(tablo, abs=0.2)


@pytest.mark.parametrize("rho,p", [(1.5, None), (0.5, None), (4.0, 1.0), (2.5, 0.5)])
def test_k1a_loop_engagement_independent(rho, p):
    """Testin kendi Ek A1 hesabıyla (loop_phi_ref, 0,1° hassasiyet) 0,2° + 0,1° içinde."""
    if p is None:
        p = trochoid_pitch(rho, r, 90.0)
    ref, _ = loop_phi_ref(rho, r, p)
    assert trochoid_loop_engagement(rho, r, p) == pytest.approx(ref, abs=0.3)


def test_k1a_loop_engagement_increases_with_p():
    vals = [trochoid_loop_engagement(2.5, r, p) for p in (0.2, 0.5, 1.0, 1.5)]
    assert all(b > a for a, b in zip(vals, vals[1:], strict=False))


@pytest.mark.parametrize("rho,phi", [(2.5, 60.0), (2.5, 90.0), (5.0, 45.0), (1.0, 30.0), (4.0, 120.0)])
def test_k1a_loop_pitch(rho, phi):
    p_star = trochoid_loop_pitch(rho, r, phi)
    assert 0 < p_star <= trochoid_pitch(rho, r, phi) * (1 + 1e-12)
    assert trochoid_loop_engagement(rho, r, p_star) == pytest.approx(phi, abs=0.2)
    ref, _ = loop_phi_ref(rho, r, p_star)
    assert ref <= phi + 0.3  # bağımsız hesapla da sınırda


@pytest.mark.parametrize(
    "call",
    [
        lambda: trochoid_loop_engagement(0.0, r, 1.0),
        lambda: trochoid_loop_engagement(-1.0, r, 1.0),
        lambda: trochoid_loop_engagement(2.5, 0.0, 1.0),
        lambda: trochoid_loop_engagement(2.5, -r, 1.0),
        lambda: trochoid_loop_engagement(2.5, r, 0.0),
        lambda: trochoid_loop_engagement(2.5, r, -0.5),
        lambda: trochoid_loop_pitch(0.0, r, 60.0),
        lambda: trochoid_loop_pitch(-2.0, r, 60.0),
        lambda: trochoid_loop_pitch(2.5, r, 0.0),
        lambda: trochoid_loop_pitch(2.5, r, 180.0),
        lambda: trochoid_loop_pitch(2.5, r, -10.0),
    ],
)
def test_k1a_out_of_range_raises(call):
    with pytest.raises(CamError):
        call()


# ---------------------------------------------------------------- K2 alanlar


def _circle_region(c, R, holes=()) -> Region:
    return Region(Profile.circle(c, R), [*holes])


AREA_CASES = {
    # ad: (bölge, gerçek alan, çevre)
    "dikdortgen": (lambda: rect_region(3.0, -7.0, 40.0, 30.0), 1200.0, 140.0),
    "daire": (lambda: _circle_region((5.0, 5.0), 20.0), math.pi * 400.0, 2 * math.pi * 20.0),
    "adali": (
        lambda: rect_region(0.0, 0.0, 60.0, 40.0, [Profile.circle((30.0, 20.0), 8.0, ccw=False)]),
        2400.0 - math.pi * 64.0,
        200.0 + 2 * math.pi * 8.0,
    ),
    "kare_adali": (
        lambda: rect_region(0.0, 0.0, 50.0, 50.0, [Profile.rectangle(10.0, 10.0, 15.0, 20.0).reversed()]),
        2500.0 - 300.0,
        200.0 + 70.0,
    ),
}


@pytest.mark.parametrize("ad", list(AREA_CASES))
@pytest.mark.parametrize("h", [0.1, 0.25])
def test_k2_from_region_area(ad, h):
    make, A, cevre = AREA_CASES[ad]
    g = MaterialGrid.from_region(make(), h)
    assert g.h == h
    assert g.m.shape == (g.ny, g.nx)
    assert g.m.dtype == bool
    assert abs(g.area() - A) <= cevre * h
    assert g.area() == pytest.approx(h * h * int(g.m.sum()), rel=1e-12)


def test_k2_from_region_cell_rule():
    """Hücre (i, j) merkezi (x0 + (j + ½)h, y0 + (i + ½)h); merkezi bölgede olan hücre malzemedir."""
    reg = rect_region(0.0, 0.0, 10.0, 6.0, [Profile.circle((5.0, 3.0), 2.0, ccw=False)])
    g = MaterialGrid.from_region(reg, 0.5)
    for i in range(g.ny):
        for j in range(g.nx):
            c = (g.x0 + (j + 0.5) * g.h, g.y0 + (i + 0.5) * g.h)
            assert bool(g.m[i, j]) == reg.contains(c), (i, j, c)
    # sınır kutusu bölgeyi kapsar
    assert g.x0 <= 0.0 + 1e-12 and g.y0 <= 0.0 + 1e-12
    assert g.x0 + g.nx * g.h >= 10.0 - 1e-12 and g.y0 + g.ny * g.h >= 6.0 - 1e-12


def test_k2_from_region_pad():
    reg = rect_region(0.0, 0.0, 10.0, 10.0)
    g0 = MaterialGrid.from_region(reg, 0.5)
    g1 = MaterialGrid.from_region(reg, 0.5, pad=3.0)
    assert g1.x0 <= g0.x0 - 3.0 + 1e-9 and g1.y0 <= g0.y0 - 3.0 + 1e-9
    assert g1.x0 + g1.nx * g1.h >= 13.0 - 1e-9 and g1.y0 + g1.ny * g1.h >= 13.0 - 1e-9
    assert g1.area() == pytest.approx(g0.area(), abs=1e-9)  # pad yalnız boş hücre ekler


@pytest.mark.parametrize("h", [0.0, -0.1])
def test_k2_from_region_bad_h(h):
    with pytest.raises(CamError):
        MaterialGrid.from_region(rect_region(0.0, 0.0, 10.0, 10.0), h)


@pytest.mark.parametrize("h", [0.1, 0.05])
@pytest.mark.parametrize(
    "seg", [((20.0, 20.0), (50.0, 20.0)), ((15.0, 12.0), (45.0, 38.0)), ((30.0, 25.0), (30.0, 25.0))]
)
def test_k2_cut_segment_capsule(h, seg):
    g = MaterialGrid.from_region(rect_region(0.0, 0.0, 60.0, 50.0), h)
    a, b = seg
    L = math.dist(a, b)
    once = g.area()
    removed = g.cut_segment(a, b, r)
    beklenen = 2 * r * L + math.pi * r * r
    assert abs(removed - beklenen) <= (2 * L + 2 * math.pi * r) * h
    assert once - g.area() == pytest.approx(removed, abs=1e-9)
    # ikinci kez aynı kesim hiçbir şey boşaltmaz
    assert g.cut_segment(a, b, r) == pytest.approx(0.0, abs=1e-12)


def test_k2_cut_segment_cells():
    """Merkezi [a, b]'ye uzaklığı ≤ r olan hücreler boşalır, diğerleri kalır."""
    g = MaterialGrid.from_region(rect_region(0.0, 0.0, 30.0, 20.0), 0.2)
    a, b = np.array([8.0, 7.0]), np.array([21.0, 13.0])
    g.cut_segment(a, b, r)
    j = np.arange(g.nx)
    i = np.arange(g.ny)
    X, Y = np.meshgrid(g.x0 + (j + 0.5) * g.h, g.y0 + (i + 0.5) * g.h)
    P = np.stack([X, Y], axis=-1)
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0.0, 1.0)
    d = np.linalg.norm(P - (a + t[..., None] * ab), axis=-1)
    kesin = d <= r - 1e-9
    disari = d > r + 1e-9
    assert not g.m[kesin].any()
    ilk = MaterialGrid.from_region(rect_region(0.0, 0.0, 30.0, 20.0), 0.2)
    assert np.array_equal(g.m[disari], ilk.m[disari])


@pytest.mark.parametrize("h", [0.1, 0.05])
@pytest.mark.parametrize("rho", [7.0, 12.0])
@pytest.mark.parametrize("ccw", [True, False])
def test_k2_cut_arc_full_turn_annulus(h, rho, ccw):
    c = np.array([30.0, 30.0])
    g = MaterialGrid.from_region(rect_region(0.0, 0.0, 60.0, 60.0), h)
    p = c + np.array([rho, 0.0])
    removed = g.cut_arc(p, p, c, ccw, r)
    beklenen = math.pi * ((rho + r) ** 2 - (rho - r) ** 2)
    cevre = 2 * math.pi * (rho + r) + 2 * math.pi * (rho - r)
    assert abs(removed - beklenen) <= cevre * h
    # halkanın içindeki ada (yarıçap ρ − r) kalır
    i = int((c[1] - g.y0) / h)
    j = int((c[0] - g.x0) / h)
    assert g.m[i, j]


def test_k2_cut_arc_half_turn_direction():
    """G3 (ccw) üst yarıyı, G2 (cw) alt yarıyı keser (aynı uçlar, ters yön)."""
    c = np.array([30.0, 30.0])
    rho = 12.0
    p0, p1 = c + [rho, 0.0], c - [rho, 0.0]
    ust = c + [0.0, rho]
    alt = c - [0.0, rho]

    def dolu(g, q) -> bool:
        return bool(g.m[int((q[1] - g.y0) / g.h), int((q[0] - g.x0) / g.h)])

    g1 = MaterialGrid.from_region(rect_region(0.0, 0.0, 60.0, 60.0), 0.2)
    g1.cut_arc(p0, p1, c, True, r)
    assert not dolu(g1, ust) and dolu(g1, alt)
    g2 = MaterialGrid.from_region(rect_region(0.0, 0.0, 60.0, 60.0), 0.2)
    g2.cut_arc(p0, p1, c, False, r)
    assert dolu(g2, ust) and not dolu(g2, alt)


# ---------------------------------------------------------------- K3 temas açısı


def _straight_wall_grid(h: float, dx: float, dy: float) -> MaterialGrid:
    """Malzeme y < 0 (duvar y = 0), x ∈ [−15, 15]; ızgara (dx, dy) kaydırılmış."""
    return MaterialGrid.from_region(rect_region(-15.0 + dx, -20.0 + dy, 30.0, 20.0 - dy), h)


@pytest.mark.parametrize("h", [D / 100, D / 200])
@pytest.mark.parametrize("ae_D", [0.1, 0.25, 0.5, 0.75])
def test_k3_straight_wall(h, ae_D):
    ae = ae_D * D
    phi = math.degrees(math.acos(1.0 - ae / r))
    yc = r - ae  # takım merkezi; en alt noktası y = −a_e
    for dx, dy in shifts(h):
        g = _straight_wall_grid(h, dx, dy)
        # +x yönünde ilerleme: malzeme sağda (−y), tırmanma
        got = g.engagement((-S, yc), (0.0, yc), r, N_ALPHA)
        assert abs(got - phi) <= tol_phi(phi, h, r, N_ALPHA), (dx, dy, got, phi)


@pytest.mark.parametrize("h", [D / 100, D / 200])
def test_k3_full_slot(h):
    for dx, dy in shifts(h):
        g = MaterialGrid.from_region(rect_region(-20.0 + dx, -20.0 + dy, 40.0, 40.0), h)
        got = g.engagement((0.0, 0.0), (S, 0.0), r, N_ALPHA)
        assert abs(got - 180.0) <= tol_phi(180.0, h, r, N_ALPHA), (dx, dy, got)


@pytest.mark.parametrize("h", [D / 100, D / 200])
@pytest.mark.parametrize("rho,Rp", [(20.0, 23.0), (10.0, 13.0), (30.0, 32.0), (10.0, 11.0)])
def test_k3_concave_circle(h, rho, Rp):
    """Formül 2: merkez ρ çemberinde, R_p dairesi boş (disk kesimi), dışı malzeme; teğet (CCW) yönde
    ilerleme."""
    cos_phi = (Rp**2 - rho**2 - r**2) / (2 * rho * r)
    phi = math.degrees(math.acos(cos_phi))
    m = r + 2.0
    for dx, dy in shifts(h):
        # takımın çevresini kapsayan dolu kare; R_p dairesi bir disk kesimiyle boşaltılır
        g = MaterialGrid.from_region(rect_region(rho - m + dx, -m + dy, 2 * m, 2 * m), h)
        g.cut_segment((0.0, 0.0), (0.0, 0.0), Rp)
        b = np.array([rho, 0.0])
        da = S / rho
        a = rho * np.array([math.cos(-da), math.sin(-da)])
        got = g.engagement(a, b, r, N_ALPHA)
        assert abs(got - phi) <= tol_phi(phi, h, r, N_ALPHA), (dx, dy, got, phi)


@pytest.mark.parametrize("h", [D / 100, D / 200])
@pytest.mark.parametrize("rho,p", [(2.5, 1.0), (4.0, 2.0), (1.0, 0.5), (2.5, 1.1237)])
def test_k3_trochoid_front_point(h, rho, p):
    """Formül 3: önceki döngü c_(k−1) = 0 merkezli ρ + r dairesini boşaltmış; takım c_k = (p, 0) döngüsünün
    ön noktası b = (p + ρ, 0)'da, döngü yönünde (+y) ilerliyor."""
    d = rho + p
    phi = math.degrees(math.acos(((rho + r) ** 2 - d**2 - r**2) / (2 * d * r)))
    m = r + 2.0
    for dx, dy in shifts(h):
        g = MaterialGrid.from_region(rect_region(d - m + dx, -m + dy, 2 * m, 2 * m), h)
        g.cut_segment((0.0, 0.0), (0.0, 0.0), rho + r)
        got = g.engagement((d, -S), (d, 0.0), r, N_ALPHA)
        assert abs(got - phi) <= tol_phi(phi, h, r, N_ALPHA), (dx, dy, got, phi)


def test_k3_inside_cleared_is_zero():
    g = MaterialGrid.from_region(rect_region(-40.0, -40.0, 80.0, 80.0), D / 100)
    g.cut_segment((0.0, 0.0), (0.0, 0.0), 20.0)
    assert g.engagement((0.0, 0.0), (1.0, 0.0), r, N_ALPHA) == 0.0
    assert g.engagement((3.0, 2.0), (3.0, 2.5), r, N_ALPHA) == 0.0


def test_k3_resting_in_material_is_360():
    g = MaterialGrid.from_region(rect_region(-20.0, -20.0, 40.0, 40.0), D / 100)
    assert g.engagement((1.0, 2.0), (1.0, 2.0), r, N_ALPHA) == pytest.approx(360.0, abs=1e-9)


def test_k3_outside_grid_is_not_material():
    """Çevre noktası ızgara dışında kalırsa malzeme değildir: takım ızgaranın köşesinde."""
    g = MaterialGrid.from_region(rect_region(0.0, 0.0, 20.0, 20.0), D / 100)
    # a = b, merkez köşede: çevrenin yalnız ¼'ü ızgaranın (malzemenin) içinde
    got = g.engagement((0.0, 0.0), (0.0, 0.0), r, N_ALPHA)
    assert got == pytest.approx(90.0, abs=tol_phi(90.0, D / 100, r, N_ALPHA))


def test_k3_engagement_does_not_modify_grid():
    g = MaterialGrid.from_region(rect_region(-20.0, -20.0, 40.0, 40.0), D / 100)
    g.cut_segment((-10.0, 0.0), (0.0, 0.0), r)
    once = g.m.copy()
    g.engagement((0.0, 0.0), (0.5, 0.0), r, N_ALPHA)
    g.engagement((3.0, 3.0), (3.0, 3.0), r, N_ALPHA)
    assert np.array_equal(g.m, once)


def test_k3_default_samples():
    g = MaterialGrid.from_region(rect_region(-20.0, -20.0, 40.0, 40.0), D / 100)
    assert g.engagement((0.0, 0.0), (S, 0.0), r) == pytest.approx(
        g.engagement((0.0, 0.0), (S, 0.0), r, 1440), abs=1e-12
    )
