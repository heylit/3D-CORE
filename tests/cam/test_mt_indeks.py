"""SPEC 49 K1 — C ekseni indeksleme: özellik ekseninden C açısı, en kısa yol, indeks adımına yuvarlama.

Testler SPEC 49 "Çerçeveler" ve "C indeksleme" bölümlerinden ve iskelet arayüzünden yazıldı;
cam/millturn gövdeleri okunmadı.

Kaynaklar (SPEC 49):
- Parçanın noktası tezgâhta p_t = R_z(C)·p_p. Radyal istasyonda R_z(C)·d = +X → C = −θ (mod 360);
  eksenel istasyonda delik merkezi +X yarıçapına getirilir: C = −θ, X = r.
- En kısa yol: ΔC ∈ (−180°, 180°]; 350° → 10° = +20°.
- continuous = False: açı index_step'e yuvarlanır; konum hatası r·|ΔC_yuv|·π/180 > tol → CamError.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.millturn.indeks import c_for, index_angle, shortest
from cam.millturn.ops import LiveCut, radial_hole
from cam.model import CamError, CAxis
from tests.cam.mtref import ST_RADYAL, STOK, R, aci_farki, freze, profil


def _Rz(c_deg: float) -> np.ndarray:
    c = math.radians(c_deg)
    return np.array([[math.cos(c), -math.sin(c), 0.0], [math.sin(c), math.cos(c), 0.0], [0.0, 0.0, 1.0]])


TETALAR = [0.0, 60.0, 120.0, 180.0, 240.0, 300.0]


@pytest.mark.parametrize("theta", TETALAR)
def test_K1_radyal_c(theta):
    """6 radyal delik: C = −θ (mod 360), [0, 360) içinde; R_z(C)·d = +X."""
    t = math.radians(theta)
    d = (math.cos(t), math.sin(t), 0.0)
    c = c_for(d, "radyal")
    assert 0.0 <= c < 360.0
    assert abs(aci_farki(c, -theta)) <= 1e-12
    assert _Rz(c) @ np.array(d) == pytest.approx([1.0, 0.0, 0.0], abs=1e-12)


@pytest.mark.parametrize("theta", [0.0, 45.0, 135.0, 200.0, 315.0])
def test_K1_eksenel_c(theta):
    """Alında eksenel delik (x, y) = r·(cos θ, sin θ): C = −θ, delik merkezi tezgâhta (r, 0)."""
    r = 12.5
    t = math.radians(theta)
    p = (r * math.cos(t), r * math.sin(t))
    c = c_for(p, "eksenel")
    assert 0.0 <= c < 360.0
    assert abs(aci_farki(c, -theta)) <= 1e-12
    assert _Rz(c) @ np.array([p[0], p[1], 0.0]) == pytest.approx([r, 0.0, 0.0], abs=1e-12)
    # (x, y, z) biçimi de kabul edilir
    assert abs(aci_farki(c_for((p[0], p[1], -3.0), "eksenel"), -theta)) <= 1e-12


@pytest.mark.parametrize(
    "prev, c, beklenen",
    [
        (350.0, 10.0, 370.0),  # SPEC örneği: +20°
        (10.0, 350.0, -10.0),
        (0.0, 180.0, 180.0),  # ΔC = 180 aralığın içinde
        (0.0, -180.0, 180.0),  # −180 dışarıda → +180
        (0.0, 540.0, 180.0),
        (720.0, 10.0, 730.0),
        (90.0, 90.0, 90.0),
        (-30.0, 300.0, -60.0),
    ],
)
def test_K1_en_kisa_yol(prev, c, beklenen):
    got = shortest(prev, c)
    assert got == pytest.approx(beklenen, abs=1e-12)
    dC = got - prev
    assert -180.0 < dC <= 180.0
    assert abs(aci_farki(got, c)) <= 1e-12


def test_K1_c_for_onceki_aciyla_en_kisa_yol():
    """350° → 10°: θ = 350° radyal deliğin C'si 10°; önceki C = 350 iken yazılacak açı 370 (ΔC = +20)."""
    t = math.radians(350.0)
    d = (math.cos(t), math.sin(t), 0.0)
    assert c_for(d, "radyal", prev=350.0) == pytest.approx(370.0, abs=1e-9)


def test_K1_alti_delik_sirasi_en_kisa_yol():
    """Sırayla 6 delik: her adımda ΔC ∈ (−180, 180] ve açı −θ'ya mod 360 eşit."""
    prev = None
    for theta in TETALAR:
        t = math.radians(theta)
        c = c_for((math.cos(t), math.sin(t), 0.0), "radyal", prev=prev)
        assert abs(aci_farki(c, -theta)) <= 1e-12
        if prev is not None:
            assert -180.0 < c - prev <= 180.0
            assert c - prev == pytest.approx(-60.0, abs=1e-9)
        prev = c


def test_K1_bilinmeyen_istasyon_yonu():
    with pytest.raises(CamError):
        c_for((1.0, 0.0, 0.0), "egik")


# ------------------------------------------------------------------ indeks adımı


ADIMLI = CAxis(continuous=False, index_step=5.0)


def test_K1_indeks_adimi_hata():
    """θ = 12° → C = 348°, en yakın adım 350° (ΔC_yuv = 2°): r = 20'de konum hatası 20·2·π/180 ≈ 0.698 mm
    > tol = 1e-3 → CamError."""
    c = c_for((math.cos(math.radians(12.0)), math.sin(math.radians(12.0)), 0.0), "radyal")
    assert 20.0 * 2.0 * math.pi / 180.0 > 1e-3
    with pytest.raises(CamError):
        index_angle(c, ADIMLI, r=20.0)


def test_K1_indeks_adimi_tolerans_icinde_yuvarlanir():
    """Aynı yuvarlama, tol = 1 mm > 0.698 mm: yazılacak açı 350°."""
    assert index_angle(348.0, ADIMLI, r=20.0, tol=1.0) == pytest.approx(350.0, abs=1e-9)


def test_K1_indeks_adimina_tam_oturan_aci():
    assert index_angle(300.0, ADIMLI, r=20.0) == pytest.approx(300.0, abs=1e-12)


def test_K1_surekli_eksen_aciyi_degistirmez():
    assert index_angle(348.123456, CAxis(), r=20.0) == pytest.approx(348.123456, abs=1e-12)


# ------------------------------------------------------------------ işlemde C


@pytest.mark.parametrize("theta", TETALAR)
def test_K1_radyal_delik_hareketleri_c_tasir(theta):
    """radial_hole: hareketler C açısını taşır (Move.c), açı −θ'ya mod 360 eşit."""
    M = profil()
    tp = radial_hole(
        STOK,
        freze(6.0),
        LiveCut(feed=200.0, plunge_feed=100.0, rpm=2000.0),
        theta,
        -20.0,
        5.0,
        station=ST_RADYAL,
        machine=M,
    )
    tp.validate()
    cs = [m.c for m in tp.moves if m.c is not None]
    assert cs
    for c in cs:
        assert abs(aci_farki(c, -theta)) <= 1e-9
    # takım ekseni −X (C ile döndürülmeden önce): delik tabanı x = R − depth, y = 0
    assert min(m.end[0] for m in tp.moves) == pytest.approx(R - 5.0, abs=1e-9)
    assert all(abs(m.end[1]) <= 1e-12 for m in tp.moves)
