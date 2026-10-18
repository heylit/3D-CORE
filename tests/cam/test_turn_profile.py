"""SPEC 28 — cam.turn_profile, OCCT'siz testler (K10 OCCT'siz kısmı, K11, K12, K13 ve uydurma).

Testler sadece SPEC 28 metninden ve sabit arayüzlerden (geometry/part.py kesit kayıtları, cam/profile.py,
cam/model.py) yazıldı; cam/turn_profile.py gövdesi okunmadı. Kesitler elle kurulan AxialSection'dır.
Koordinatlar (z, x); halka CCW (iç solda): eksen boyunca +z, dış kontur ön→arka (−z).

Beklenen değerler (el ile):
- P_ön: en büyük z, eşitlikte en küçük x; P_arka: en küçük z, eşitlikte en büyük x.
- outer: CCW halkada P_ön → P_arka alt zinciri (arka yüz hariç).
- inner: CCW halkada P_arka → P_ön alt zinciri; baştaki z = z_min doğruları ve eksen üzerindeki son
  kenara kadar her şey atılır, kalan ters çevrilir; boşsa None.
- Pappus: torus kesiti (merkez (0, 10), r = 3) V = 2π · 10 · π 3²; burç halkası V = π (8² − 5²) · 10;
  yarım küre V = ⅔ π 10³; sinüs eğrisi V = π ∫ x(z)² dz (scipy.quad).
"""

from __future__ import annotations

import math
import re

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.spatial import cKDTree

from cam.model import CamError
from cam.profile import Arc, Line, Profile
from cam.turn_profile import TurnProfile, profile_from_section, turn_profile
from geometry.part import AxialSection, SectionEdge, SectionFace
from tests.cam.ref_turn import (
    assert_lines,
    chain_points,
    describe,
    egriler,
    pappus_S,
    pappus_V,
    sample,
    shoelace_area,
)

TOL = 1e-9
LINK_TOL = 1e-7
T59 = math.tan(math.radians(59.0))


# ------------------------------------------------------------------ kesit kurucuları


def L(p0, p1) -> SectionEdge:
    return SectionEdge("line", np.array([p0, p1], dtype=float))


def A(p0, p1, c, ccw: bool = True) -> SectionEdge:
    return SectionEdge("arc", np.array([p0, p1], dtype=float), np.array(c, dtype=float), ccw)


def C(pts) -> SectionEdge:
    return SectionEdge("curve", np.asarray(pts, dtype=float))


def ring(pts) -> list[SectionEdge]:
    """Kapalı çokgen halkası (son nokta ilkine bağlanır)."""
    return [L(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


def sec(
    edges, holes=(), off=(), unknown=(), origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), xdir=(1.0, 0.0, 0.0)
):
    face = SectionFace(tuple(edges), tuple(tuple(h) for h in holes))
    return AxialSection(
        origin=np.array(origin, dtype=float),
        axis=np.array(axis, dtype=float),
        xdir=np.array(xdir, dtype=float),
        faces=(face,),
        off_axis_faces=tuple(off),
        unknown_faces=tuple(unknown),
    )


# K1 basamaklı mil: Ø40 × 40 (z ∈ [0, 40]) + Ø20 × 20 (z ∈ [40, 60])
MIL = [(0, 0), (60, 0), (60, 10), (40, 10), (40, 20), (0, 20)]
MIL_OUTER = [(60, 0), (60, 10), (40, 10), (40, 20), (0, 20)]
# K3 burç Ø50/Ø30 × 40
BURC = [(0, 15), (40, 15), (40, 25), (0, 25)]
# K4 kör delik: Ø40 × 50, önden Ø10, 30 derin, 118° uç
Z_TIP = 20.0 - 5.0 / T59
KOR = [(0, 0), (Z_TIP, 0), (20, 5), (50, 5), (50, 20), (0, 20)]


def check_section(tp: TurnProfile) -> None:
    """Genel değişmezler: kapalı CCW kesit, her noktada x ≥ 0, açık outer/inner, uç uca zincirler."""
    assert isinstance(tp, TurnProfile)
    assert tp.section.closed
    assert tp.section.area > 0
    for s in tp.section.segments:
        assert isinstance(s, (Line, Arc))
    P = sample(tp.section, 50)
    assert np.all(P[:, 1] >= -TOL), "kesit eksenin altına iniyor"
    assert not tp.outer.closed
    if tp.inner is not None:
        assert not tp.inner.closed
    for prof in (tp.section, tp.outer) + ((tp.inner,) if tp.inner is not None else ()):
        segs = prof.segments
        for i in range(len(segs) - 1):
            assert np.hypot(*(segs[i].p1 - segs[i + 1].p0)) <= LINK_TOL


# ------------------------------------------------------------------ K10 Pappus (OCCT'siz)


def test_pappus_burc_halkasi():
    """Eksene değmeyen dikdörtgen kesit: V_P = π(R² − r²)·h, alan, fitted_length = 0."""
    tp = profile_from_section(sec(ring([(0, 5), (10, 5), (10, 8), (0, 8)])))
    check_section(tp)
    assert tp.section.area == pytest.approx(30.0, rel=1e-12)
    assert pappus_V(tp.section) == pytest.approx(math.pi * (64 - 25) * 10, rel=1e-12)
    S = 2 * math.pi * (8 * 10 + 5 * 10) + math.pi * (64 - 25) * 2
    assert pappus_S(tp.section) == pytest.approx(S, rel=1e-12)
    assert tp.fitted_length == 0


def test_pappus_torus():
    """İki yarım yaydan daire kesiti (merkez (0, 10), r = 3): V = 2π²·10·9, S = 4π²·10·3."""
    edges = [A((3, 10), (-3, 10), (0, 10), True), A((-3, 10), (3, 10), (0, 10), True)]
    tp = profile_from_section(sec(edges))
    check_section(tp)
    assert tp.section.area == pytest.approx(9 * math.pi, rel=1e-12)
    assert pappus_V(tp.section) == pytest.approx(2 * math.pi**2 * 10 * 9, rel=1e-12)
    assert pappus_S(tp.section) == pytest.approx(4 * math.pi**2 * 10 * 3, rel=1e-12)
    # P_ön = (3, 10), P_arka = (−3, 10): outer üst yarım daire (ccw), inner alt yarım ters çevrilmiş (cw)
    assert len(tp.outer.segments) == 1 and isinstance(tp.outer.segments[0], Arc)
    o = tp.outer.segments[0]
    np.testing.assert_allclose([o.p0, o.p1, o.c], [(3, 10), (-3, 10), (0, 10)], atol=TOL)
    assert o.ccw is True
    assert tp.inner is not None and len(tp.inner.segments) == 1
    i = tp.inner.segments[0]
    np.testing.assert_allclose([i.p0, i.p1, i.c], [(3, 10), (-3, 10), (0, 10)], atol=TOL)
    assert i.ccw is False


def test_pappus_cerceve_aktarimi():
    """origin / axis / xdir kesitten aynen TurnProfile'a geçer."""
    o, ax, xd = (1.0, 2.0, 3.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    tp = profile_from_section(sec(ring(MIL), origin=o, axis=ax, xdir=xd))
    np.testing.assert_allclose(tp.origin, o, atol=TOL)
    np.testing.assert_allclose(tp.axis, ax, atol=TOL)
    np.testing.assert_allclose(tp.xdir, xd, atol=TOL)


# ------------------------------------------------------------------ K11 birleştirme ve bağlama


def test_birlestirme_dogru():
    """Aynı doğru üzerinde üç parçalı silindir kenarı → tek Line (halka başı ortadan başlasa da)."""
    edges = [
        L((47, 10), (40, 10)),
        L((40, 10), (40, 20)),
        L((40, 20), (0, 20)),
        L((0, 20), (0, 0)),
        L((0, 0), (60, 0)),
        L((60, 0), (60, 10)),
        L((60, 10), (52, 10)),
        L((52, 10), (47, 10)),
    ]
    tp = profile_from_section(sec(edges))
    check_section(tp)
    assert len(tp.section.segments) == 6, describe(tp.section)
    assert all(isinstance(s, Line) for s in tp.section.segments)
    assert tp.section.area == pytest.approx(40 * 20 + 20 * 10, rel=1e-12)
    assert_lines(tp.outer, MIL_OUTER)
    assert tp.inner is None
    assert tp.fitted_length == 0


def test_birlestirme_eksen_ve_alin():
    """Eksen kenarı iki parça, ön alın iki parça → her biri tek Line."""
    edges = [
        L((0, 0), (25, 0)),
        L((25, 0), (60, 0)),
        L((60, 0), (60, 4)),
        L((60, 4), (60, 10)),
        L((60, 10), (40, 10)),
        L((40, 10), (40, 20)),
        L((40, 20), (0, 20)),
        L((0, 20), (0, 0)),
    ]
    tp = profile_from_section(sec(edges))
    assert len(tp.section.segments) == 6, describe(tp.section)
    assert_lines(tp.outer, MIL_OUTER)


def test_birlestirme_yay():
    """Aynı merkezli, aynı yarıçaplı, aynı yönlü iki yay → tek Arc (kubbe)."""
    m = (10 * math.cos(math.pi / 4), 10 * math.sin(math.pi / 4))
    edges = [L((0, 0), (10, 0)), A((10, 0), m, (0, 0), True), A(m, (0, 10), (0, 0), True), L((0, 10), (0, 0))]
    tp = profile_from_section(sec(edges))
    check_section(tp)
    arcs = [s for s in tp.section.segments if isinstance(s, Arc)]
    assert len(tp.section.segments) == 3, describe(tp.section)
    assert len(arcs) == 1
    a = arcs[0]
    np.testing.assert_allclose([a.p0, a.p1, a.c], [(10, 0), (0, 10), (0, 0)], atol=TOL)
    assert a.ccw is True
    assert pappus_V(tp.section) == pytest.approx(2 / 3 * math.pi * 1000, rel=1e-12)


def test_birlestirme_yapmaz():
    """Kırık doğrular (açı farkı 1e-4 rad ≫ a_tol) ve farklı merkezli yaylar birleşmez."""
    dz = 20 * math.tan(1e-4)
    edges = [
        L((0, 0), (60, 0)),
        L((60, 0), (60, 10)),
        L((60, 10), (40, 10)),
        L((40, 10), (20, 10 + dz)),
        L((20, 10 + dz), (0, 10 + dz)),
        L((0, 10 + dz), (0, 0)),
    ]
    tp = profile_from_section(sec(edges))
    assert len(tp.section.segments) == 6, describe(tp.section)
    # art arda iki çeyrek yay, merkezleri farklı: (5, 0) ve (0, 5)
    edges = [
        L((0, 0), (10, 0)),
        A((10, 0), (5, 5), (5, 0), True),
        A((5, 5), (0, 10), (0, 5), True),
        L((0, 10), (0, 0)),
    ]
    tp = profile_from_section(sec(edges))
    assert sum(isinstance(s, Arc) for s in tp.section.segments) == 2, describe(tp.section)


def test_baglama():
    """5e-8 mm kayık uçlar tek koordinatta birleşir; |x| ≤ LINK_TOL uçlar x = 0'a çekilir."""
    e = 5e-8
    edges = [
        L((0, 3e-8), (60, -3e-8)),
        L((60 + e, 0), (60, 10 + e)),
        L((60, 10), (40 + e, 10)),
        L((40, 10 - e), (40, 20)),
        L((40, 20 + e), (e, 20)),
        L((0, 20), (0, 0)),
    ]
    tp = profile_from_section(sec(edges))
    check_section(tp)
    segs = tp.section.segments
    assert len(segs) == 6, describe(tp.section)
    n = len(segs)
    for i in range(n):
        # ortak köşe tek koordinat: bitiş ve sonraki başlangıç bit bit aynı
        assert np.array_equal(segs[i].p1, segs[(i + 1) % n].p0), describe(tp.section)
    pts = chain_points(tp.section)
    for p in pts:
        nominal = min(MIL, key=lambda q: np.hypot(*(np.asarray(q) - p)))
        assert np.hypot(*(np.asarray(nominal) - p)) <= LINK_TOL
    eksen = [p for p in pts if abs(p[1]) <= LINK_TOL]
    assert len(eksen) >= 2
    for p in eksen:
        assert p[1] == 0.0
    assert_lines(tp.outer, MIL_OUTER, tol=LINK_TOL)


def test_baglama_cw_halka():
    """CW verilmiş halka CCW'ye çevrilir: alan > 0 ve aynı dış profil."""
    pts = list(reversed(MIL))
    tp = profile_from_section(sec(ring(pts)))
    check_section(tp)
    assert tp.section.area == pytest.approx(1000.0, rel=1e-12)
    assert_lines(tp.outer, MIL_OUTER)
    assert tp.inner is None


# ------------------------------------------------------------------ K12 bölme kuralları


def test_bolme_mil():
    """Ön yüz eksenden başlar, arka yüz dış profile girmez, delik yok."""
    tp = profile_from_section(sec(ring(MIL)))
    check_section(tp)
    assert_lines(tp.outer, MIL_OUTER)
    assert tp.inner is None
    assert len(tp.section.segments) == 6
    assert tp.fitted_length == 0


def test_bolme_burc():
    """P_ön eşitliği: ön yüz deliğe kadar (40, 15)'ten başlar; P_arka (0, 25), arka yüz hariç."""
    tp = profile_from_section(sec(ring(BURC)))
    check_section(tp)
    assert_lines(tp.outer, [(40, 15), (40, 25), (0, 25)])
    assert tp.inner is not None
    assert_lines(tp.inner, [(40, 15), (0, 15)])


def test_bolme_kor_delik():
    """Kör delik: inner = duvar + koni dip, eksende biter; outer ön yüzle (50, 5)'ten başlar."""
    tp = profile_from_section(sec(ring(KOR)))
    check_section(tp)
    assert_lines(tp.outer, [(50, 5), (50, 20), (0, 20)])
    assert_lines(tp.inner, [(50, 5), (20, 5), (Z_TIP, 0)])


def test_bolme_kubbe():
    """Ön ucu eksende biten kubbe: inner None, outer x = 0'dan başlar (yarım küre yayı)."""
    edges = [
        L((0, 0), (30, 0)),
        A((30, 0), (20, 10), (20, 0), True),
        L((20, 10), (0, 10)),
        L((0, 10), (0, 0)),
    ]
    tp = profile_from_section(sec(edges))
    check_section(tp)
    assert tp.inner is None
    s0 = tp.outer.segments[0]
    assert isinstance(s0, Arc)
    np.testing.assert_allclose([s0.p0, s0.p1, s0.c], [(30, 0), (20, 10), (20, 0)], atol=TOL)
    assert s0.p0[1] == pytest.approx(0.0, abs=TOL)
    assert len(tp.outer.segments) == 2
    assert_lines(Profile(tp.outer.segments[1:], closed=False), [(20, 10), (0, 10)])


def test_bolme_arkadan_delik():
    """Arkadan açılmış delik iç profile girmez: inner None; outer ön yüz + dış kontur."""
    pts = [(20, 0), (50, 0), (50, 20), (0, 20), (0, 5), (20, 5)]
    tp = profile_from_section(sec(ring(pts)))
    check_section(tp)
    assert_lines(tp.outer, [(50, 0), (50, 20), (0, 20)])
    assert tp.inner is None


def test_bolme_on_ve_arka_delik():
    """Önden kör delik + arkadan delik: inner yalnız ön delik (arka delik ve eksen kenarı atılır)."""
    pts = [(10, 0), (30, 0), (30, 5), (50, 5), (50, 20), (0, 20), (0, 8), (10, 8)]
    tp = profile_from_section(sec(ring(pts)))
    check_section(tp)
    assert_lines(tp.outer, [(50, 5), (50, 20), (0, 20)])
    assert_lines(tp.inner, [(50, 5), (30, 5), (30, 0)])


def test_bolme_halka_baslangici_bagimsiz():
    """Kenar sırası halkanın neresinden başlarsa başlasın sonuç aynı."""
    for k in range(len(KOR)):
        pts = KOR[k:] + KOR[:k]
        tp = profile_from_section(sec(ring(pts)))
        assert_lines(tp.outer, [(50, 5), (50, 20), (0, 20)])
        assert_lines(tp.inner, [(50, 5), (20, 5), (Z_TIP, 0)])


# ------------------------------------------------------------------ serbest eğri uydurma (OCCT'siz)


def _yay_noktalari(c, R, th0, th1, n):
    th = np.linspace(th0, th1, n)
    return np.stack([c[0] + R * np.cos(th), c[1] + R * np.sin(th)], axis=1)


def test_uydurma_daire_noktalari():
    """Tam daire üzerindeki çokgen (sapma ≤ tol/4) → tek Arc, merkez (0, 0), R = 10; L_u = 5π."""
    q = _yay_noktalari((0.0, 0.0), 10.0, 0.0, math.pi / 2, 201)
    q[0], q[-1] = (10.0, 0.0), (0.0, 10.0)
    tp = profile_from_section(sec([L((0, 0), (10, 0)), C(q), L((0, 10), (0, 0))]), tol=1e-3)
    check_section(tp)
    assert len(tp.section.segments) == 3, describe(tp.section)
    arcs = [s for s in tp.section.segments if isinstance(s, Arc)]
    assert len(arcs) == 1
    a = arcs[0]
    np.testing.assert_allclose(a.c, (0, 0), atol=1e-6)
    np.testing.assert_allclose([a.p0, a.p1], [(10, 0), (0, 10)], atol=TOL)
    assert a.ccw is True
    assert tp.fitted_length == pytest.approx(5 * math.pi, rel=1e-9)


def test_uydurma_dogrusal_noktalar():
    """Doğrusal 'curve' kenarı → tek Line; L_u = 20 (serbest eğriden gelen kenar boyu)."""
    q = np.stack([np.linspace(60, 40, 21), np.full(21, 10.0)], axis=1)
    edges = [
        L((0, 0), (60, 0)),
        L((60, 0), (60, 10)),
        C(q),
        L((40, 10), (40, 20)),
        L((40, 20), (0, 20)),
        L((0, 20), (0, 0)),
    ]
    tp = profile_from_section(sec(edges), tol=1e-3)
    assert len(tp.section.segments) == 6, describe(tp.section)
    assert_lines(tp.outer, MIL_OUTER)
    assert tp.fitted_length == pytest.approx(20.0, rel=1e-9)


def _x_sin(z):
    return 5.0 + 3.0 * np.sin(np.asarray(z) / 4.0)


@pytest.mark.parametrize("tol", [1e-2, 1e-3])
def test_uydurma_sinus(tol):
    """x = 5 + 3 sin(z/4), z ∈ [0, 20]: yalnız Line/Arc, iki yönlü Hausdorff ≤ tol, uçlar tam, L_u ≈ boy."""
    z = np.linspace(20.0, 0.0, 1001)  # Δs ≤ 0.025 → kiriş sapması ≤ κ Δs²/8 ≈ 1.5e-5 ≤ tol/4
    q = np.stack([z, _x_sin(z)], axis=1)
    x20 = float(_x_sin(20.0))
    edges = [L((0, 0), (20, 0)), L((20, 0), (20, x20)), C(q), L((0, 5), (0, 0))]
    tp = profile_from_section(sec(edges), tol=tol)
    check_section(tp)
    assert_lines(Profile(tp.outer.segments[:1], closed=False), [(20, 0), (20, x20)])
    fit = tp.outer.segments[1:]
    assert all(isinstance(s, (Line, Arc)) for s in fit)
    np.testing.assert_allclose(fit[0].p0, (20, x20), atol=TOL)
    np.testing.assert_allclose(fit[-1].p1, (0, 5), atol=TOL)
    # profil → eğri: yoğun gerçek eğri noktaları (aralık 1e-5) en yakın komşu ile (fazla tahmin ≤ 5e-6)
    zz = np.linspace(0.0, 20.0, 2_000_001)
    tree = cKDTree(np.stack([zz, _x_sin(zz)], axis=1))
    P = sample(Profile(fit, closed=False), 200)
    d, _ = tree.query(P)
    assert d.max() <= tol, d.max()
    # eğri → profil: kesin uzaklık
    zq = np.linspace(0.0, 20.0, 20001)
    dq = egriler(fit).distance(np.stack([zq, _x_sin(zq)], axis=1))
    assert dq.max() <= tol, dq.max()
    boy, _ = quad(lambda t: math.hypot(1.0, 0.75 * math.cos(t / 4.0)), 0.0, 20.0, epsabs=1e-12, epsrel=1e-13)
    assert tp.fitted_length == pytest.approx(boy, rel=1e-3)
    V, _ = quad(lambda t: math.pi * float(_x_sin(t)) ** 2, 0.0, 20.0, epsabs=1e-10, epsrel=1e-13)
    eps_V = 1e-6 * V + 2 * math.pi * 8.0 * tol * tp.fitted_length
    assert abs(pappus_V(tp.section) - V) <= eps_V
    assert shoelace_area(tp.section) == pytest.approx(tp.section.area, rel=1e-9)


# ------------------------------------------------------------------ K13 geçersiz kesit ve girdiler


def _ints(msg: str) -> set[int]:
    return {int(m) for m in re.findall(r"\d+", msg)}


def test_gecersiz_iki_yuz():
    s = sec(ring(MIL))
    iki = AxialSection(
        s.origin, s.axis, s.xdir, s.faces + (SectionFace(tuple(ring([(70, 0), (80, 0), (80, 5)]))),), (), ()
    )
    with pytest.raises(CamError):
        profile_from_section(iki)


def test_gecersiz_ic_halka():
    delik = ring([(10, 5), (10, 8), (20, 8), (20, 5)])  # CW iç halka (kapalı toroidal boşluk)
    with pytest.raises(CamError):
        profile_from_section(sec(ring(MIL), holes=[delik]))


def test_gecersiz_bos():
    s = sec(ring(MIL))
    with pytest.raises(CamError):
        profile_from_section(AxialSection(s.origin, s.axis, s.xdir, (), (), ()))


def test_gecersiz_eksen_disi_yuzler():
    with pytest.raises(CamError) as e:
        profile_from_section(sec(ring(MIL), off=(3, 17)))
    assert {3, 17} <= _ints(str(e.value))


def test_bilinmeyen_yuzler_hata_degil():
    """unknown_faces dolu olması tek başına hata değildir (karar Pappus denetimine kalır)."""
    tp = profile_from_section(sec(ring(MIL), unknown=(2,)))
    assert_lines(tp.outer, MIL_OUTER)


@pytest.mark.parametrize("tol", [0.0, -1e-3, math.nan, math.inf])
def test_gecersiz_tol(tol):
    with pytest.raises(CamError):
        profile_from_section(sec(ring(MIL)), tol=tol)


@pytest.mark.parametrize("girdi", [None, "parca", 42, sec(ring(MIL))])
def test_gecersiz_part_degil(girdi):
    with pytest.raises(CamError):
        turn_profile(girdi)
