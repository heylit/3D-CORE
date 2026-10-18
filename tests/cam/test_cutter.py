"""SPEC 06b — cam/cutter.py testleri (K1, K2, K3; konik ofset K3 arayüz eki sonrası).

Testler sadece SPEC 06b "Takım profili", "Destek (Legendre) fonksiyonu", "Ofset" ve "Arayüz"
bölümlerinden yazıldı; uygulama kodu okunmadı. Beklenen profiller SPEC tablosundaki kapalı
formlardır (tests/cam/ref3d_ek.profil); destek fonksiyonu ve ofset profili kaba kuvvetle
(tests/cam/ref3d_ek.brute_support, minkowski_profile) bağımsız hesaplanır.

Kaynaklar:
- Legendre dönüşümü: f*(m) = max_ρ (mρ − f(ρ)); eğik düzlemde takım ucu ile düzlem arasındaki
  yükseklik farkı (OpenCAMLib MillingCutter::facetDrop, köşe radyüslü takım için "BullCutter").
- Minkowski ofset: Choi & Jerard, Sculptured Surface Machining (1998), 4. bölüm (takım ofset yüzeyi).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.cutter import Cutter
from cam.model import CamError, Tool, ToolKind
from tests.cam.ref3d_ek import brute_support, minkowski_profile, profil

R = 4.0
RC = 1.0
THETA = 30.0  # konik yarı açı [derece]
EPS = 1e-9


def tool(kind: ToolKind, D: float = 2 * R, corner_r: float = 0.0, tip_angle: float | None = None) -> Tool:
    return Tool(id=1, name="t", kind=kind, D=D, flute_length=30.0, corner_r=corner_r, tip_angle=tip_angle)


def rho_grid(Rad: float) -> np.ndarray:
    return np.concatenate([np.linspace(0.0, Rad, 401), [0.0, Rad, 1e-7, Rad - 1e-7]])


# (ad, Cutter üreticisi, referans profil, R)
CUTTERS = [
    pytest.param(lambda: Cutter.flat(R), profil("duz", R), R, id="duz"),
    pytest.param(lambda: Cutter.ball(R), profil("kure", R), R, id="kure"),
    pytest.param(lambda: Cutter.torus(R, RC), profil("torik", R, RC), R, id="torik"),
    pytest.param(lambda: Cutter.torus(5.0, 3.5), profil("torik", 5.0, 3.5), 5.0, id="torik-buyuk-rc"),
    pytest.param(lambda: Cutter.cone(R, THETA), profil("konik", R, theta=THETA), R, id="konik"),
    pytest.param(lambda: Cutter.cone(2.0, 59.0), profil("konik", 2.0, theta=59.0), 2.0, id="konik-118"),
]

# --- K1 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("make, fref, Rad", CUTTERS)
def test_k1_profil_formulleri(make, fref, Rad):
    c = make()
    assert c.R == pytest.approx(Rad, abs=1e-12)
    rho = rho_grid(Rad)
    np.testing.assert_allclose(c.f(rho), fref(rho), atol=EPS, rtol=0)
    assert c.height == pytest.approx(float(fref(Rad)), abs=EPS)
    assert float(c.f(np.array([0.0]))[0]) == pytest.approx(0.0, abs=1e-15)


def test_k1_yukseklikler():
    assert Cutter.flat(R).height == pytest.approx(0.0, abs=EPS)
    assert Cutter.ball(R).height == pytest.approx(R, abs=EPS)
    assert Cutter.torus(R, RC).height == pytest.approx(RC, abs=EPS)
    assert Cutter.cone(R, THETA).height == pytest.approx(R / math.tan(math.radians(THETA)), abs=EPS)


@pytest.mark.parametrize("make, fref, Rad", CUTTERS)
def test_k1_disarisi_sonsuz(make, fref, Rad):
    z = make().f(np.array([Rad + 1e-6, Rad + 1.0, 10 * Rad]))
    assert np.all(np.isinf(z)) and np.all(z > 0)
    assert np.isfinite(make().f(np.array([Rad]))[0])


@pytest.mark.parametrize("make, fref, Rad", CUTTERS)
def test_k1_negatif_rho(make, fref, Rad):
    with pytest.raises(CamError):
        make().f(np.array([0.5, -1e-3]))


def test_k1_torik_uclari():
    """r_c = 0 torik = düz, r_c = R torik = küresel."""
    rho = rho_grid(R)
    np.testing.assert_allclose(Cutter.torus(R, 0.0).f(rho), Cutter.flat(R).f(rho), atol=EPS, rtol=0)
    np.testing.assert_allclose(Cutter.torus(R, R).f(rho), Cutter.ball(R).f(rho), atol=EPS, rtol=0)


def test_k1_profil_azalmayan_ve_disbukey():
    """Dört takımda örneklenen profil azalmayan ve dışbükey (ikinci fark ≥ 0)."""
    rho = np.linspace(0.0, R, 2001)
    for c in (Cutter.flat(R), Cutter.ball(R), Cutter.torus(R, RC), Cutter.cone(R, THETA)):
        z = c.f(rho)
        assert np.all(np.diff(z) >= -1e-12)
        assert np.all(np.diff(z, 2) >= -1e-9)


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda: Cutter.flat(0.0), id="duz-R=0"),
        pytest.param(lambda: Cutter.flat(-1.0), id="duz-R<0"),
        pytest.param(lambda: Cutter.flat(math.nan), id="duz-nan"),
        pytest.param(lambda: Cutter.ball(0.0), id="kure-R=0"),
        pytest.param(lambda: Cutter.ball(math.inf), id="kure-inf"),
        pytest.param(lambda: Cutter.torus(R, -0.1), id="torik-rc<0"),
        pytest.param(lambda: Cutter.torus(R, R + 0.1), id="torik-rc>R"),
        pytest.param(lambda: Cutter.torus(0.0, 0.0), id="torik-R=0"),
        pytest.param(lambda: Cutter.torus(R, math.nan), id="torik-nan"),
        pytest.param(lambda: Cutter.cone(R, 0.0), id="konik-theta=0"),
        pytest.param(lambda: Cutter.cone(R, 90.0), id="konik-theta=90"),
        pytest.param(lambda: Cutter.cone(R, -10.0), id="konik-theta<0"),
        pytest.param(lambda: Cutter.cone(R, 120.0), id="konik-theta>90"),
        pytest.param(lambda: Cutter.cone(0.0, THETA), id="konik-R=0"),
        pytest.param(lambda: Cutter.cone(R, math.nan), id="konik-nan"),
    ],
)
def test_k1_hatali_parametre(make):
    with pytest.raises(CamError):
        make()


@pytest.mark.parametrize(
    "t, fref",
    [
        pytest.param(tool(ToolKind.BALL), profil("kure", R), id="BALL"),
        pytest.param(tool(ToolKind.FLAT), profil("duz", R), id="FLAT"),
        pytest.param(tool(ToolKind.FLAT, corner_r=RC), profil("torik", R, RC), id="FLAT-torik"),
        pytest.param(tool(ToolKind.FLAT, corner_r=R), profil("kure", R), id="FLAT-rc=R"),
        pytest.param(tool(ToolKind.CONE, tip_angle=2 * THETA), profil("konik", R, theta=THETA), id="CONE-60"),
        pytest.param(tool(ToolKind.CONE, tip_angle=90.0), profil("konik", R, theta=45.0), id="CONE-90"),
    ],
)
def test_k1_from_tool(t, fref):
    c = Cutter.from_tool(t)
    assert c.R == pytest.approx(t.D / 2, abs=1e-12)
    rho = rho_grid(R)
    np.testing.assert_allclose(c.f(rho), fref(rho), atol=EPS, rtol=0)


def test_k1_from_tool_matkap():
    with pytest.raises(CamError):
        Cutter.from_tool(tool(ToolKind.DRILL, D=6.0))


# --- K2 ---------------------------------------------------------------------------------------------

M = [0.0, 0.1, math.tan(math.radians(10)), math.tan(math.radians(30)), 1.0, math.tan(math.radians(60)), 5.0]
COT = 1 / math.tan(math.radians(THETA))
M_KONIK = [0.0, 0.5, COT - 1e-3, COT, COT + 1e-3, 2.5, 5.0]


def closed_support(kind: str, m: float, Rad: float = R, rc: float = RC) -> tuple[float, float]:
    """SPEC 06b kapalı formları (β = atan m)."""
    b = math.atan(m)
    if kind == "duz":
        return m * Rad, (Rad if m > 0 else 0.0)
    if kind == "kure":
        return Rad * (1 / math.cos(b) - 1), Rad * math.sin(b)
    if kind == "torik":
        Rt = Rad - rc
        return Rt * math.tan(b) + rc * (1 / math.cos(b) - 1), (Rt + rc * math.sin(b) if m > 0 else 0.0)
    if m <= COT:
        return 0.0, 0.0
    return Rad * (m - COT), Rad


SUPPORT_CASES = [
    pytest.param(lambda: Cutter.flat(R), "duz", profil("duz", R), M, id="duz"),
    pytest.param(lambda: Cutter.ball(R), "kure", profil("kure", R), M, id="kure"),
    pytest.param(lambda: Cutter.torus(R, RC), "torik", profil("torik", R, RC), M, id="torik"),
    pytest.param(
        lambda: Cutter.cone(R, THETA), "konik", profil("konik", R, theta=THETA), M_KONIK, id="konik"
    ),
]


@pytest.mark.parametrize("make, kind, fref, ms", SUPPORT_CASES)
def test_k2_support_kapali_form(make, kind, fref, ms):
    fs, rs = make().support(np.array(ms))
    assert fs.shape == (len(ms),) and rs.shape == (len(ms),)
    for m, a, b in zip(ms, fs, rs, strict=True):
        f_bek, r_bek = closed_support(kind, m)
        assert a == pytest.approx(f_bek, abs=EPS), m
        assert b == pytest.approx(r_bek, abs=EPS), m


@pytest.mark.parametrize("make, kind, fref, ms", SUPPORT_CASES)
def test_k2_support_kaba_kuvvet(make, kind, fref, ms):
    fs, rs = make().support(np.array(ms))
    for m, a, b in zip(ms, fs, rs, strict=True):
        f_ref, r_ref = brute_support(fref, R, m)
        assert a == pytest.approx(f_ref, abs=EPS), m
        assert b == pytest.approx(r_ref, abs=1e-5), m  # argmax örnekleme çözünürlüğü


def test_k2_support_negatif_egim():
    with pytest.raises(CamError):
        Cutter.torus(R, RC).support(np.array([0.3, -0.01]))


# --- K3 ---------------------------------------------------------------------------------------------

DELTA = 0.5


@pytest.mark.parametrize(
    "make, beklenen",
    [
        pytest.param(lambda: Cutter.flat(R), profil("torik", R + DELTA, DELTA), id="duz->torik"),
        pytest.param(lambda: Cutter.ball(R), profil("kure", R + DELTA), id="kure->kure"),
        pytest.param(lambda: Cutter.torus(R, RC), profil("torik", R + DELTA, RC + DELTA), id="torik->torik"),
    ],
)
def test_k3_offset_kapali_form(make, beklenen):
    o = make().offset(DELTA)
    assert o.R == pytest.approx(R + DELTA, abs=1e-12)
    rho = rho_grid(R + DELTA)
    np.testing.assert_allclose(o.f(rho), beklenen(rho), atol=EPS, rtol=0)
    assert np.isinf(o.f(np.array([R + DELTA + 1e-6]))[0])


@pytest.mark.parametrize(
    "make, fref",
    [
        pytest.param(lambda: Cutter.flat(R), profil("duz", R), id="duz"),
        pytest.param(lambda: Cutter.ball(R), profil("kure", R), id="kure"),
        pytest.param(lambda: Cutter.torus(R, RC), profil("torik", R, RC), id="torik"),
    ],
)
def test_k3_offset_minkowski_kaba_kuvvet(make, fref):
    """Ofset profili = takım katısı ⊕ δ küre alt zarfı (meridyen kesitinde kaba kuvvet), 1e-6."""
    rho = np.linspace(0.0, R + DELTA, 61)
    ref = minkowski_profile(fref, R, DELTA, rho)
    np.testing.assert_allclose(make().offset(DELTA).f(rho), ref, atol=1e-6, rtol=0)


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda: Cutter.flat(R), id="duz"),
        pytest.param(lambda: Cutter.ball(R), id="kure"),
        pytest.param(lambda: Cutter.torus(R, RC), id="torik"),
        pytest.param(lambda: Cutter.cone(R, THETA), id="konik"),
    ],
)
def test_k3_offset_sifir(make):
    c = make()
    o = c.offset(0.0)
    assert o.R == pytest.approx(c.R, abs=1e-12)
    rho = rho_grid(c.R)
    np.testing.assert_allclose(o.f(rho), c.f(rho), atol=EPS, rtol=0)


def test_k3_offset_negatif():
    with pytest.raises(CamError):
        Cutter.torus(R, RC).offset(-0.1)


def konik_offset_closed(Rad: float, th_deg: float, delta: float):
    """SPEC 06b konik ofset: uçta δ küre, ona teğet θ koni, kenarda δ yay (merkez eski kenar
    noktası (R, h_c)), dış yarıçap R + δ; ucu 0'a kaydırılmış."""
    th = math.radians(th_deg)
    cot = 1 / math.tan(th)
    h_c = Rad * cot
    r1 = delta * math.cos(th)  # küre–koni teğet noktası
    r2 = Rad + delta * math.cos(th)  # koni–kenar yayı teğet noktası

    def f(rho):
        rho = np.asarray(rho, dtype=float)
        kure = delta - np.sqrt(np.maximum(delta**2 - rho**2, 0.0))
        koni = (delta - delta * math.sin(th)) + (rho - r1) * cot
        yay = delta + h_c - np.sqrt(np.maximum(delta**2 - (rho - Rad) ** 2, 0.0))
        z = np.where(rho <= r1, kure, np.where(rho <= r2, koni, yay))
        return np.where(rho > Rad + delta, np.inf, z)

    return f


@pytest.mark.parametrize("Rad, th", [pytest.param(R, THETA, id="R4-30"), pytest.param(2.0, 59.0, id="R2-59")])
def test_k3_konik_offset(Rad, th):
    """Konik ofset profili: kapalı form ve takım katısı ⊕ δ küre alt zarfı (kaba kuvvet), 1e-6."""
    o = Cutter.cone(Rad, th).offset(DELTA)
    assert o.R == pytest.approx(Rad + DELTA, abs=1e-12)
    rho = np.linspace(0.0, Rad + DELTA, 61)
    ref = minkowski_profile(profil("konik", Rad, theta=th), Rad, DELTA, rho)
    np.testing.assert_allclose(konik_offset_closed(Rad, th, DELTA)(rho), ref, atol=1e-6, rtol=0)  # oracle
    np.testing.assert_allclose(o.f(rho), ref, atol=1e-6, rtol=0)
    assert np.isinf(o.f(np.array([Rad + DELTA + 1e-6]))[0])


def test_k3_konik_offset_from_tool():
    o = Cutter.from_tool(tool(ToolKind.CONE, tip_angle=2 * THETA)).offset(DELTA)
    rho = rho_grid(R + DELTA)
    np.testing.assert_allclose(o.f(rho), konik_offset_closed(R, THETA, DELTA)(rho), atol=EPS, rtol=0)
