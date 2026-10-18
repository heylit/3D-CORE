"""SPEC 28 — cam.turn_profile, gerçek parçalarla testler (K1–K10, K14, K15). OCCT gerektirir.

Testler sadece SPEC 28 metninden ve sabit arayüzlerden (geometry/part.py, cam/profile.py, cam/model.py,
SPEC 20 cam.lathe / cam.lathe_ops imzaları) yazıldı;
cam/turn_profile.py ve geometry/revolve.py gövdeleri okunmadı.
Parçalar uydurma geometridir; build123d ile (z, x) kesitinin Z ekseni etrafında döndürülmesiyle kurulur
(3B nokta (x, 0, z)). Boolean ve taşıma işlemleri doğrudan build123d ile yapılır (Part.cut / moved SPEC 09'a
bağlı olmasın diye).

Analitik değerler (Pappus–Guldin, V = 2π ∬ x dA):
- K1  mil: V = π(20²·40 + 10²·20), kesit alanı 40·20 + 20·10.
- K2  silindir r=20 (z 0..20) + koni 30° (r 20→16, Δz = 4/tan 30°) + omuz z_s (16→13) + R=3 içbükey radyüs
      (merkez (z_s+3, 13)) + silindir r=10 (10 boy) + yarım küre R=10:
      V = π20²·20 + πh/3(20² + 20·16 + 16²) + π10²·3 + 2π x̄_f A_f + π10²·10 + ⅔π10³,
      radyüs köşesinin eklediği malzeme A_f = 9 − 9π/4, ağırlık merkezi x̄_f = 13 − 0.5/(1 − π/4)
      (kare [z_s, z_s+3]×[10, 13] eksi çeyrek daire; içbükey köşede radyüs malzeme ekler).
- K3  burç: V = π(25² − 15²)·40, kesit alanı 10·40.
- K4  kör delik: uç z_tip = 20 − 5/tan 59°.
- K9  elips uç: V = π20²·40 + ⅔π·20²·30; elips çeyrek yay boyu ∫ √(b² sin²t + a² cos²t) dt.
- ε_V = 1e-6 V + 2π x_max tol L_u, ε_S = 1e-6 S + 2π (x_max + L_u) tol.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.spatial import cKDTree

bd = pytest.importorskip("build123d")

from cam.lathe import is_monotone, orient  # noqa: E402
from cam.lathe_ops import TurnCut, finish, rough  # noqa: E402
from cam.model import CamError, CylinderStock, LatheTool, LatheToolKind, Toolpath  # noqa: E402
from cam.profile import Arc, Line, Profile  # noqa: E402
from cam.turn_profile import TurnProfile, turn_profile  # noqa: E402
from geometry.part import Part  # noqa: E402
from tests.cam.ref_turn import (  # noqa: E402
    assert_lines,
    describe,
    egriler,
    pappus_S,
    pappus_V,
    sample,
)

pytestmark = pytest.mark.occt

TOL = 1e-9
LINK_TOL = 1e-7
T30 = math.tan(math.radians(30.0))
T59 = math.tan(math.radians(59.0))
MIL_OUTER = [(60, 0), (60, 10), (40, 10), (40, 20), (0, 20)]


# ------------------------------------------------------------------ parça kurucuları


def P(z, x) -> bd.Vector:
    """(z, x) kesit noktası → 3B (x, 0, z)."""
    return bd.Vector(x, 0, z)


def ln(a, b):
    return bd.Edge.make_line(P(*a), P(*b))


def arc3(a, m, b):
    return bd.Edge.make_three_point_arc(P(*a), P(*m), P(*b))


def poly(pts) -> list:
    return [ln(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


def rev_shape(edges):
    """(z, x) yarı kesitini Z ekseni etrafında 360° döndürür (build123d katısı)."""
    return bd.revolve(bd.Face(bd.Wire(edges)), bd.Axis.Z, 360)


def rev(edges, name: str = "parca") -> Part:
    return Part(rev_shape(edges), name=name)


MIL_KESIT = [(0, 0), (60, 0), (60, 10), (40, 10), (40, 20), (0, 20)]


def mil() -> Part:
    """K1: Ø40 × 40 (z ∈ [0, 40]) + Ø20 × 20 (z ∈ [40, 60])."""
    return rev(poly(MIL_KESIT), "mil")


Z_S = 20.0 + 4.0 / T30  # koni sonu / omuz
Z_C = Z_S + 13.0  # yarım küre merkezi


def koni_radyus_kure() -> Part:
    """K2: silindir + 30° koni + omuz + R3 içbükey radyüs + Ø20 silindir + R10 yarım küre."""
    s2 = 1 / math.sqrt(2)
    edges = [
        ln((0, 0), (Z_C + 10, 0)),
        arc3((Z_C + 10, 0), (Z_C + 10 * s2, 10 * s2), (Z_C, 10)),
        ln((Z_C, 10), (Z_S + 3, 10)),
        arc3((Z_S + 3, 10), (Z_S + 3 - 3 * s2, 13 - 3 * s2), (Z_S, 13)),
        ln((Z_S, 13), (Z_S, 16)),
        ln((Z_S, 16), (20, 20)),
        ln((20, 20), (0, 20)),
        ln((0, 20), (0, 0)),
    ]
    return rev(edges, "koni_radyus_kure")


def V_k2() -> float:
    h = 4.0 / T30
    A_f = 9 - 9 * math.pi / 4
    x_f = 13 - 0.5 / (1 - math.pi / 4)
    return (
        math.pi * 400 * 20
        + math.pi * h / 3 * (400 + 320 + 256)
        + math.pi * 100 * 3
        + 2 * math.pi * x_f * A_f
        + math.pi * 100 * 10
        + 2 / 3 * math.pi * 1000
    )


def burc() -> Part:
    """K3: Ø50/Ø30 × 40, boydan delik."""
    return rev(poly([(0, 15), (40, 15), (40, 25), (0, 25)]), "burc")


Z_TIP = 20.0 - 5.0 / T59


def kor_delik() -> Part:
    """K4: Ø40 × 50 mil, önden Ø10 × 30 kör delik, 118° matkap ucu konisi."""
    return rev(poly([(0, 0), (Z_TIP, 0), (20, 5), (50, 5), (50, 20), (0, 20)]), "kor_delik")


EA, EB = 20.0, 30.0  # elips yarı eksenleri: radyal a, eksenel b; merkez (z, x) = (40, 0)


def elips_uc() -> Part:
    """K9: Ø40 silindir (z ∈ [0, 40]) + yarı eksenleri a = 20 (radyal), b = 30 (eksenel) yarım sferoid."""
    plane = bd.Plane(origin=(0, 0, 40), x_dir=(0, 0, 1), z_dir=(0, 1, 0))  # yerel x = Z, yerel y = X
    el = bd.Edge.make_ellipse(EB, EA, plane, 0, 90)
    edges = [ln((0, 0), (40 + EB, 0)), el, ln((40, EA), (0, EA)), ln((0, EA), (0, 0))]
    return rev(edges, "elips_uc")


def mil_x() -> Part:
    """K1 mili Y ekseni etrafında +90° döndürülmüş: (x, y, z) → (z, y, −x); Z ekseni X eksenine döner."""
    return Part(bd.Rot(0, 90, 0) * rev_shape(poly(MIL_KESIT)), name="mil_x")


# ------------------------------------------------------------------ yardımcılar


def eps_V(tp: TurnProfile, V: float, tol: float, x_max: float) -> float:
    return 1e-6 * V + 2 * math.pi * x_max * tol * tp.fitted_length


def eps_S(tp: TurnProfile, S: float, tol: float, x_max: float) -> float:
    return 1e-6 * S + 2 * math.pi * (x_max + tp.fitted_length) * tol


def x_max(prof: Profile) -> float:
    return float(sample(prof, 400)[:, 1].max())


def ints(msg: str) -> set[int]:
    return {int(m) for m in re.findall(r"\d+", msg)}


def check_genel(tp: TurnProfile) -> None:
    assert isinstance(tp, TurnProfile)
    assert tp.section.closed and tp.section.area > 0
    assert not tp.outer.closed
    assert np.all(sample(tp.section, 50)[:, 1] >= -TOL)
    for s in tp.section.segments:
        assert isinstance(s, (Line, Arc))


def same_profile(a: Profile | None, b: Profile | None, tol: float) -> None:
    if a is None or b is None:
        assert a is None and b is None
        return
    assert len(a.segments) == len(b.segments), f"{describe(a)}  ≠  {describe(b)}"
    for s, t in zip(a.segments, b.segments, strict=True):
        assert type(s) is type(t)
        np.testing.assert_allclose([s.p0, s.p1], [t.p0, t.p1], atol=tol, rtol=0)
        if isinstance(s, Arc):
            np.testing.assert_allclose(s.c, t.c, atol=tol, rtol=0)
            assert s.ccw == t.ccw


# ------------------------------------------------------------------ K1 basamaklı mil


def test_basamakli_mil():
    part = mil()
    tp = turn_profile(part)
    check_genel(tp)
    assert_lines(tp.outer, MIL_OUTER)
    assert tp.inner is None
    assert len(tp.section.segments) == 6
    assert all(isinstance(s, Line) for s in tp.section.segments)
    assert tp.section.area == pytest.approx(40 * 20 + 20 * 10, rel=1e-9)
    assert tp.fitted_length == 0
    assert pappus_V(tp.section) == pytest.approx(math.pi * (400 * 40 + 100 * 20), rel=1e-9)
    np.testing.assert_allclose(tp.origin, (0, 0, 0), atol=TOL)
    np.testing.assert_allclose(tp.axis, (0, 0, 1), atol=TOL)
    np.testing.assert_allclose(tp.xdir, (1, 0, 0), atol=TOL)


# ------------------------------------------------------------------ K2 koni, radyüs, küre


def test_koni_radyus_kure():
    part = koni_radyus_kure()
    tp = turn_profile(part)
    check_genel(tp)
    assert tp.inner is None
    segs = tp.section.segments
    koni = [
        s
        for s in segs
        if isinstance(s, Line) and abs(s.p0[0] - s.p1[0]) > TOL and abs(s.p0[1] - s.p1[1]) > TOL
    ]
    assert len(koni) == 1, describe(tp.section)
    np.testing.assert_allclose(
        sorted([tuple(koni[0].p0), tuple(koni[0].p1)]), [(20, 20), (Z_S, 16)], atol=TOL
    )
    arcs = [s for s in segs if isinstance(s, Arc)]
    assert len(arcs) == 2, describe(tp.section)
    rad = [a for a in arcs if abs(a.R - 3) < 1e-6]
    kure = [a for a in arcs if abs(a.R - 10) < 1e-6]
    assert len(rad) == 1 and len(kure) == 1
    np.testing.assert_allclose(rad[0].c, (Z_S + 3, 13), atol=TOL)
    assert rad[0].R == pytest.approx(3, abs=TOL)
    assert rad[0].ccw is False  # içbükey
    np.testing.assert_allclose(kure[0].c, (Z_C, 0), atol=TOL)
    assert kure[0].R == pytest.approx(10, abs=TOL)
    assert kure[0].ccw is True
    # ön uç eksende: dış profil yarım küre yayıyla (Z_C + 10, 0)'dan başlar
    np.testing.assert_allclose(tp.outer.start, (Z_C + 10, 0), atol=TOL)
    np.testing.assert_allclose(tp.outer.end, (0, 20), atol=TOL)
    assert tp.fitted_length == 0
    assert pappus_V(tp.section) == pytest.approx(V_k2(), rel=1e-9)
    assert part.volume == pytest.approx(V_k2(), rel=1e-9)


# ------------------------------------------------------------------ K3, K4 delikler


def test_delikli_burc():
    tp = turn_profile(burc())
    check_genel(tp)
    assert_lines(tp.outer, [(40, 15), (40, 25), (0, 25)])
    assert tp.inner is not None
    assert_lines(tp.inner, [(40, 15), (0, 15)])
    assert tp.section.area == pytest.approx(10 * 40, rel=1e-9)
    assert pappus_V(tp.section) == pytest.approx(math.pi * (625 - 225) * 40, rel=1e-9)


def test_kor_delik():
    tp = turn_profile(kor_delik())
    check_genel(tp)
    assert_lines(tp.inner, [(50, 5), (20, 5), (Z_TIP, 0)])
    assert_lines(tp.outer, [(50, 5), (50, 20), (0, 20)])


# ------------------------------------------------------------------ K5, K6 eksen


def test_ters_eksen():
    tp = turn_profile(mil(), axis=(0, 0, -1))
    check_genel(tp)
    assert_lines(tp.outer, [(0, 0), (0, 20), (-40, 20), (-40, 10), (-60, 10)])
    assert tp.inner is None
    np.testing.assert_allclose(tp.axis, (0, 0, -1), atol=TOL)
    np.testing.assert_allclose(tp.xdir, (1, 0, 0), atol=TOL)


def test_eksen_x():
    """Z yerine X ekseninde modellenmiş mil: profil K1 ile aynı; xdir = Y'nin dik bileşeni."""
    ref = turn_profile(mil())
    tp = turn_profile(mil_x(), axis=(1, 0, 0))
    same_profile(tp.outer, ref.outer, TOL)
    same_profile(tp.inner, ref.inner, TOL)
    assert tp.section.area == pytest.approx(ref.section.area, rel=1e-9)
    np.testing.assert_allclose(tp.axis, (1, 0, 0), atol=TOL)
    np.testing.assert_allclose(tp.xdir, (0, 1, 0), atol=TOL)


def test_eksen_birime_cevrilir():
    tp = turn_profile(mil(), axis=(0, 0, 5))
    np.testing.assert_allclose(tp.axis, (0, 0, 1), atol=TOL)
    assert_lines(tp.outer, MIL_OUTER)


def test_auto_eksen():
    tp = turn_profile(mil_x(), axis="auto")
    np.testing.assert_allclose(tp.axis, (1, 0, 0), atol=1e-9)
    np.testing.assert_allclose(tp.origin, (0, 0, 0), atol=1e-7)
    assert_lines(tp.outer, MIL_OUTER)
    tz = turn_profile(mil(), axis="auto")
    np.testing.assert_allclose(tz.axis, (0, 0, 1), atol=1e-9)
    assert_lines(tz.outer, MIL_OUTER)


def test_auto_eksen_kaydirilmis():
    """Eksen (5, 7) noktasından geçen Z doğrusu: origin = global orijinin eksene izdüşümü (5, 7, 0)."""
    tp = turn_profile(Part(bd.Pos(5, 7, 3) * rev_shape(poly(MIL_KESIT))), axis="auto")
    np.testing.assert_allclose(tp.axis, (0, 0, 1), atol=1e-9)
    np.testing.assert_allclose(tp.origin, (5, 7, 0), atol=1e-7)
    # z parça koordinatında: 3 mm kaymış
    assert_lines(tp.outer, [(z + 3, x) for z, x in MIL_OUTER], tol=1e-7)


# ------------------------------------------------------------------ K7 otomatik eksen hataları


def test_auto_eksen_hata_kure():
    with pytest.raises(CamError):
        turn_profile(Part(bd.Sphere(10)), axis="auto")


def test_auto_eksen_hata_iki_eksen():
    """Eksen dışı Ø6 eksenel delik (x = 10): iki farklı eksen → CamError, mesajda ikinci eksenin konumu."""
    delik = bd.Pos(10, 0, 20) * bd.Cylinder(3, 60)
    part = Part(rev_shape(poly([(0, 0), (40, 0), (40, 20), (0, 20)])) - delik)
    with pytest.raises(CamError) as e:
        turn_profile(part, axis="auto")
    assert "10" in str(e.value)


# ------------------------------------------------------------------ K8 dönel olmayan parça


def _duzluk() -> Part:
    kutu = bd.Pos(24, 0, 15) * bd.Box(12, 60, 20)  # x ≥ 18, z ∈ [5, 25]: 2 mm düzlük
    return Part(rev_shape(poly(MIL_KESIT)) - kutu)


def _capraz_delik() -> Part:
    delik = bd.Pos(0, 0, 20) * bd.Rot(0, 90, 0) * bd.Cylinder(3, 60)
    return Part(rev_shape(poly(MIL_KESIT)) - delik)


def _altigen() -> Part:
    alt = bd.extrude(bd.RegularPolygon(15, 6, major_radius=False), 10)  # SW 30, z ∈ [0, 10]
    return Part(alt + rev_shape(poly([(10, 0), (40, 0), (40, 10), (10, 10)])))


def _beklenen_duzlem(part: Part) -> set[int]:
    return {f.index for f in part.planar_faces() if abs(abs(f.normal[2]) - 1) > 1e-6}


def _beklenen_silindir(part: Part) -> set[int]:
    return {f.index for f in part.cylindrical_faces() if abs(abs(f.axis[2]) - 1) > 1e-6}


@pytest.mark.parametrize(
    "kur, beklenen",
    [(_duzluk, _beklenen_duzlem), (_capraz_delik, _beklenen_silindir), (_altigen, _beklenen_duzlem)],
    ids=["duzluk", "capraz_delik", "altigen"],
)
def test_donel_olmayan(kur, beklenen):
    part = kur()
    idx = beklenen(part)
    assert idx, "kurulumda dönel olmayan yüz bulunamadı"
    with pytest.raises(CamError) as e:
        turn_profile(part)
    assert idx <= ints(str(e.value)), (idx, str(e.value))


# ------------------------------------------------------------------ K9 elips uydurma


def _elips_boyu() -> float:
    f = lambda t: math.hypot(EB * math.sin(t), EA * math.cos(t))  # noqa: E731
    return quad(f, 0.0, math.pi / 2, epsabs=1e-12, epsrel=1e-13)[0]


def _elips(t: np.ndarray) -> np.ndarray:
    return np.stack([40 + EB * np.cos(t), EA * np.sin(t)], axis=1)


@pytest.mark.parametrize("tol", [1e-2, 1e-3])
def test_elips_uydurma(tol):
    part = elips_uc()
    tp = turn_profile(part, tol=tol)
    check_genel(tp)
    assert tp.inner is None
    np.testing.assert_allclose(tp.outer.start, (40 + EB, 0), atol=TOL)
    # elips uçları profilde köşe olarak tam yer alır
    kose = [s.p1 for s in tp.outer.segments[:-1]]
    assert min(np.hypot(*(np.asarray(p) - (40, EA))) for p in kose) <= TOL
    fit = [s for s in tp.outer.segments if min(s.p0[0], s.p1[0]) >= 40 - TOL]
    assert fit, describe(tp.outer)
    assert all(isinstance(s, (Line, Arc)) for s in fit)
    for i in range(len(fit) - 1):
        assert np.hypot(*(fit[i].p1 - fit[i + 1].p0)) <= LINK_TOL
    np.testing.assert_allclose(fit[0].p0, (40 + EB, 0), atol=TOL)
    np.testing.assert_allclose(fit[-1].p1, (40, EA), atol=TOL)
    # parça → elips: yoğun elips noktaları (yay aralığı ≈ 2e-5, fazla tahmin ≤ 1e-5)
    tree = cKDTree(_elips(np.linspace(0, math.pi / 2, 2_000_001)))
    for s in fit:
        d, _ = tree.query(sample(Profile([s], closed=False), 200))
        assert d.max() <= tol, (d.max(), describe(Profile([s], closed=False)))
    # elips → profil: kesin uzaklık
    dq = egriler(fit).distance(_elips(np.linspace(0, math.pi / 2, 20001)))
    assert dq.max() <= tol, dq.max()
    assert tp.fitted_length == pytest.approx(_elips_boyu(), rel=1e-3)
    V = part.volume
    assert V == pytest.approx(math.pi * 400 * 40 + 2 / 3 * math.pi * 400 * 30, rel=1e-9)
    assert abs(pappus_V(tp.section) - V) <= eps_V(tp, V, tol, EA)


# ------------------------------------------------------------------ K10 Pappus denetimi


@pytest.mark.parametrize(
    "kur", [mil, koni_radyus_kure, burc, kor_delik, elips_uc], ids=["mil", "koni", "burc", "kor", "elips"]
)
def test_pappus_parca(kur):
    tol = 1e-3
    part = kur()
    tp = turn_profile(part, tol=tol)
    xm = x_max(tp.section)
    V, S = part.volume, part.area
    assert abs(pappus_V(tp.section) - V) <= eps_V(tp, V, tol, xm)
    assert abs(pappus_S(tp.section) - S) <= eps_S(tp, S, tol, xm)


# ------------------------------------------------------------------ K13 geçersiz girdiler (Part ile)


@pytest.mark.parametrize(
    "kw",
    [
        {"axis": (0, 0, 0)},
        {"axis": (0, math.nan, 1)},
        {"axis": (0, math.inf, 1)},
        {"axis": "z"},
        {"axis": "oto"},
        {"origin": (0, math.nan, 0)},
        {"origin": (math.inf, 0, 0)},
        {"tol": 0.0},
        {"tol": -1e-3},
        {"tol": math.nan},
    ],
)
def test_gecersiz_girdi(kw):
    with pytest.raises(CamError):
        turn_profile(mil(), **kw)


def test_eksen_parcayi_kesmiyor():
    """Eksen parçanın dışından geçer → CamError (GeometryError da CamError'a çevrilir)."""
    with pytest.raises(CamError):
        turn_profile(mil(), origin=(100, 100, 0))


# ------------------------------------------------------------------ K14 SPEC 20 uyumu


def _ttool(kind=LatheToolKind.TURN, tip: int = 3, r: float = 0.8) -> LatheTool:
    return LatheTool(id=1, name="T", kind=kind, nose_r=r, tip=tip, kappa_r=93.0, eps_r=55.0)


def test_spec20_uyum():
    k1 = turn_profile(mil())
    k2 = turn_profile(koni_radyus_kure())
    same_profile(orient(k1.outer), k1.outer, 0.0)
    same_profile(orient(k2.outer), k2.outer, 0.0)
    assert is_monotone(k1.outer) is True
    stock = CylinderStock(D=40.0, zmin=-5.0, zmax=60.0)
    tp_r = rough(k1.outer, stock, _ttool(), TurnCut(feed=0.2, rpm=2000.0, css=180.0, a_p=2.0), allowance=0.3)
    tp_f = finish(k1.outer, stock, _ttool(), TurnCut(feed=0.1, rpm=2000.0, css=200.0))
    assert isinstance(tp_r, Toolpath) and isinstance(tp_f, Toolpath)
    k3 = turn_profile(burc())
    boru = CylinderStock(D=52.0, zmin=-5.0, zmax=40.0, d=26.0)
    ic = _ttool(kind=LatheToolKind.BORE, tip=2, r=0.4)
    tp_i = finish(k3.inner, boru, ic, TurnCut(feed=0.1, rpm=2000.0, css=200.0), side="ic")
    assert isinstance(tp_i, Toolpath)


# ------------------------------------------------------------------ K15 STEP gidiş-dönüş


def test_step(tmp_path):
    part = koni_radyus_kure()
    yol = tmp_path / "k2.step"
    part.to_step(yol)
    geri = Part.from_step(yol)
    a, b = turn_profile(part), turn_profile(geri)
    # kesit halkasının başlangıç noktası tanımlı değil: alan ve hacimle; outer / inner parça parça
    assert b.section.area == pytest.approx(a.section.area, abs=1e-6)
    assert pappus_V(b.section) == pytest.approx(pappus_V(a.section), rel=1e-9)
    same_profile(a.outer, b.outer, 1e-6)
    same_profile(a.inner, b.inner, 1e-6)
