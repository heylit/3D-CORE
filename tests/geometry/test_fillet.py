"""SPEC 23 — geometry/fillet.py testleri (K1–K4). OCCT gerektirir.

Testler SPEC 23'ün "Teori", "Arayüz" ve "Kabul kriterleri" bölümlerinden ve geometry/part.py arayüzünden
yazıldı; fillet uygulaması okunmadı. Uydurma geometri: blok a×b×c = 100×60×20 (SPEC ön denemesiyle aynı).
Koordinat kuralı (SPEC 02): blok min köşesi orijinde; üst yüz z = c.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.features import block, cylinder, hole, pocket  # noqa: E402
from geometry.fillet import fillet_all, fillet_top, fillet_vertical  # noqa: E402
from geometry.part import GeometryError, Hole, Part  # noqa: E402

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 20.0  # blok kenarları [mm]
V0 = A * B * C  # 120000 mm³
S0 = 2 * (A * B + B * C + C * A)  # 2(6000 + 1200 + 2000) = 18400 mm²
REL = 1e-6


# --- El hesabı (SPEC 23 "Teori / Yuvarlatma") ---------------------------------------------------


def A_f(r: float) -> float:
    """Dik kenar yuvarlatılınca kalkan kesit: r × r kare − çeyrek daire = (1 − π/4) r²."""
    return (1 - math.pi / 4) * r**2


def x_bar(r: float) -> float:
    """Kalkan kesitin ağırlık merkezinin duvara uzaklığı: x̄ = r (10 − 3π) / (3 (4 − π)).

    Kontrol: kare (alan r², merkez r/2) − çeyrek daire (alan πr²/4, merkez r − 4r/(3π)) momenti
    r³/2 − (πr²/4)(r − 4r/(3π)) = r³ (1/2 − π/4 + 1/3) = r³ (10 − 3π)/12; alana bölünce x̄.
    """
    return r * (10 - 3 * math.pi) / (3 * (4 - math.pi))


def dV_vertical(r: float, c: float) -> float:
    """4 dikey kenar: ΔV = (4 − π) r² c."""
    return (4 - math.pi) * r**2 * c


def dS_vertical(r: float, c: float) -> float:
    """4 dikey kenar: ΔS = −[(8 − 2π) r c + 2 (4 − π) r²] (yan yüzler 2r kaybeder, πr/2 yay kazanır)."""
    return -((8 - 2 * math.pi) * r * c + 2 * (4 - math.pi) * r**2)


def dV_top_block(a: float, b: float, r: float) -> float:
    """Üst 4 kenar: ΔV = A_f · 2(a + b) − 4 r³ (5/3 − π/2) (köşede iki kenarın örtüşmesi)."""
    return A_f(r) * 2 * (a + b) - 4 * r**3 * (5 / 3 - math.pi / 2)


def dV_ring(rho: float, r: float) -> float:
    """Dairesel kenar, Pappus: ΔV = 2π ρ A_f."""
    return 2 * math.pi * rho * A_f(r)


def V_all(a: float, b: float, c: float, r: float) -> float:
    """12 kenar yuvarlatılmış blok: V = a'b'c' + 2r(a'b' + b'c' + c'a') + π r² (a' + b' + c') + (4/3) π r³."""
    a_, b_, c_ = a - 2 * r, b - 2 * r, c - 2 * r
    return (
        a_ * b_ * c_
        + 2 * r * (a_ * b_ + b_ * c_ + c_ * a_)
        + math.pi * r**2 * (a_ + b_ + c_)
        + 4 / 3 * math.pi * r**3
    )


def S_all(a: float, b: float, c: float, r: float) -> float:
    """12 kenar yuvarlatılmış blok: S = 2(a'b' + b'c' + c'a') + 2π r (a' + b' + c') + 4π r²."""
    a_, b_, c_ = a - 2 * r, b - 2 * r, c - 2 * r
    return 2 * (a_ * b_ + b_ * c_ + c_ * a_) + 2 * math.pi * r * (a_ + b_ + c_) + 4 * math.pi * r**2


def test_el_hesabi_spec_on_denemesi():
    """Formül kendi içinde tutarlı: SPEC'teki OCCT ön denemesi (a=100, b=60, r=4 → 1074.21860 mm³)."""
    assert dV_top_block(100.0, 60.0, 4.0) == pytest.approx(1074.21860, rel=1e-8)
    # r → 0 sınırında tüm-kenar formülleri bloğa döner
    assert V_all(A, B, C, 0.0) == pytest.approx(V0)
    assert S_all(A, B, C, 0.0) == pytest.approx(S0)


# --- K1 fillet_vertical -------------------------------------------------------------------------


@pytest.mark.parametrize("r", [2.0, 4.0, 10.0])
def test_k1_fillet_vertical_blok_hacim_alan(r):
    p0 = block(A, B, C)
    p = fillet_vertical(p0, r)
    assert isinstance(p, Part)
    assert V0 - p.volume == pytest.approx(dV_vertical(r, C), rel=REL)
    assert p.area - S0 == pytest.approx(dS_vertical(r, C), rel=REL)


def test_k1_fillet_vertical_sinir_kutusu_degismez():
    p = fillet_vertical(block(A, B, C), 4.0)
    lo, hi = p.bbox
    np.testing.assert_allclose(lo, [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [A, B, C], rtol=1e-6)


def test_k1_fillet_vertical_icbukey_ve_dikis_kenarlarini_secmez():
    """Keskin köşeli cebin dikey kenarları içbükey, deliğin dikiş kenarı silindirik yüzün: ikisi de seçilmez.

    Bu yüzden kaldırılan hacim sadece bloğun 4 dış dikey kenarınınki kadardır.
    """
    p0 = block(A, B, C)
    p0 = hole(p0, 20.0, 30.0, 10.0)  # boydan boya delik, dikiş kenarı dikey doğru
    p0 = pocket(p0, 65.0, 30.0, 30.0, 20.0, 8.0, r=0.0)  # keskin köşeli cep: 4 içbükey dikey kenar
    r = 3.0
    p = fillet_vertical(p0, r)
    assert p0.volume - p.volume == pytest.approx(dV_vertical(r, C), rel=REL)


def test_k1_fillet_vertical_silindirde_kenar_yok_hata():
    """Silindirin tek dikey doğrusal kenarı dikiştir (seam): seçilecek kenar yok → GeometryError."""
    with pytest.raises(GeometryError):
        fillet_vertical(cylinder(20.0, 30.0), 2.0)


# --- K2 fillet_top ------------------------------------------------------------------------------


@pytest.mark.parametrize("r", [2.0, 4.0])
def test_k2_fillet_top_blok(r):
    p = fillet_top(block(A, B, C), r)
    assert V0 - p.volume == pytest.approx(dV_top_block(A, B, r), rel=REL)
    # sınır kutusu: üst kenarlar yuvarlansa da yan yüzler ve üst yüz düzlemleri kalır
    lo, hi = p.bbox
    np.testing.assert_allclose(lo, [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [A, B, C], rtol=1e-6)


def test_k2_fillet_top_silindir_pappus():
    """Silindir (R = 20, h = 30) üst kenarı: ρ = R − x̄, ΔV = 2π ρ A_f."""
    R, h, r = 20.0, 30.0, 3.0
    p0 = cylinder(R, h)
    p = fillet_top(p0, r)
    assert p0.volume - p.volume == pytest.approx(dV_ring(R - x_bar(r), r), rel=REL)


def test_k2_fillet_top_delik_agzi_pappus():
    """Boydan boya delik (r_h = 6) ağzı da üst yüz kenarıdır: ρ = r_h + x̄ halkası + blok üst kenarları."""
    d_h, r = 12.0, 2.0
    p0 = hole(block(A, B, C), 50.0, 30.0, d_h)
    p = fillet_top(p0, r)
    beklenen = dV_top_block(A, B, r) + dV_ring(d_h / 2 + x_bar(r), r)
    assert p0.volume - p.volume == pytest.approx(beklenen, rel=REL)


# --- K3 fillet_all ------------------------------------------------------------------------------


@pytest.mark.parametrize("r", [2.0, 5.0])
def test_k3_fillet_all_blok_hacim_alan_agirlik_merkezi(r):
    p = fillet_all(block(A, B, C), r)
    assert p.volume == pytest.approx(V_all(A, B, C, r), rel=REL)
    assert p.area == pytest.approx(S_all(A, B, C, r), rel=REL)
    np.testing.assert_allclose(p.center_of_mass, [A / 2, B / 2, C / 2], atol=1e-6)


# --- K4 hatalar ve değişmezlik ------------------------------------------------------------------

FILLETLER = [fillet_vertical, fillet_top, fillet_all]


@pytest.mark.parametrize("islem", FILLETLER)
@pytest.mark.parametrize("r", [0.0, -1.0, math.nan])
def test_k4_gecersiz_yaricap_hata(islem, r):
    with pytest.raises(GeometryError):
        islem(block(A, B, C), r)


@pytest.mark.parametrize(
    "islem, r",
    [
        (fillet_vertical, 35.0),  # 2r = 70 > b = 60: yan yüz genişliği yetmez
        (fillet_top, 25.0),  # r = 25 > c = 20: dikey kenar boyundan büyük
        (fillet_all, 12.0),  # 2r = 24 > c = 20: dikey kenar boyundan büyük
    ],
)
def test_k4_kenar_boyundan_buyuk_r_hata(islem, r):
    with pytest.raises(GeometryError):
        islem(block(A, B, C), r)


def _kayit() -> Hole:
    return Hole(
        origin=np.array([20.0, 30.0, C]), axis=np.array([0.0, 0.0, -1.0]), d=10.0, depth=C, through=True
    )


@pytest.mark.parametrize("islem", FILLETLER)
def test_k4_girdi_parca_degismez_kayitlar_korunur(islem):
    """Fillet yeni Part döndürür; girdinin hacmi ve kayıtları aynı kalır, kayıtlar yeni parçaya taşınır."""
    p_blok = hole(block(A, B, C), 20.0, 30.0, 10.0)
    h = _kayit()
    p0 = Part(p_blok.shape, name="kayitli", holes=(h,))
    V_once = p0.volume
    p = islem(p0, 1.0)
    assert p is not p0
    assert p0.volume == pytest.approx(V_once, rel=1e-12)
    assert len(p0.holes) == 1 and p0.holes[0] is h
    assert len(p.holes) == 1
    k = p.holes[0]
    np.testing.assert_allclose(k.origin, h.origin)
    np.testing.assert_allclose(k.axis, h.axis)
    assert (k.d, k.depth, k.through) == (h.d, h.depth, h.through)
    assert p.volume < V_once
