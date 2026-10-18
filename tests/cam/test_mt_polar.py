"""SPEC 49 K2–K3 — polar ve silindirik enterpolasyon: dönüşümler, merkez tekilliği denetimi, kirişler.

Testler SPEC 49 "Polar enterpolasyon" ve "Silindirik enterpolasyon" bölümlerinden ve iskelet arayüzünden
yazıldı; cam/millturn gövdeleri okunmadı.

Kaynaklar (SPEC 49):
- Polar: r = √(x² + y²), C = atan2(y, x); C ∈ (−180, 180] derece.
- Eksenden h uzaklıkta geçen doğruda teğet ilerleme F iken ω = F·h / r², en çok r = h'de ω_max = F / h
  [rad/dk]; dev/dk'ya: ω / (2π). ω_max > 2π·rpm_max → CamError; merkezden geçiş (h < 1e-9) → CamError.
- Merkezi eksende olan yayda r sabit: ω = F / r (teğet hız / yarıçap).
- Silindirik: açılmış (s, z, r) → C = s / r_ref [rad], nokta (r cos C, r sin C, z); kanal tabanı r_ref − t.
  Kiriş hatası (sehim) r·(1 − cos(Δφ/2)) ≤ arc_tol.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.millturn.ops import LiveCut, cyl_slot, face_contour, face_pocket
from cam.millturn.polar import H_MIN, cyl_chords, from_cyl, from_polar, polar_check, to_cartesian, to_polar
from cam.model import CamError, CAxis, Move, MoveType, Toolpath
from cam.ops2d import Cut
from cam.profile import Profile, Region
from tests.cam.mtref import C_RPM_MAX, ST_EKSENEL, ST_RADYAL, freze, profil

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
C_AXIS = CAxis(rpm_max=C_RPM_MAX)


def _polar_yol(start, moves) -> Toolpath:
    return Toolpath("polar", freze(6.0), start, moves, rpm=3000.0, coord="polar", station=ST_EKSENEL)


def _dogru(h: float, x0: float = -40.0, x1: float = 40.0, F: float = 1000.0) -> Toolpath:
    """y = h doğrusu boyunca G1, z = −1."""
    return _polar_yol((x0, h, -1.0), [Move(G1, (x1, h, -1.0), feed=F)])


# ------------------------------------------------------------------ K2 dönüşüm


def test_K2_to_polar_geri_donus():
    rng = np.random.default_rng(49)
    P = rng.uniform(-50.0, 50.0, size=(1000, 2))
    for x, y in P:
        r, c = to_polar((x, y))
        assert r == pytest.approx(math.hypot(x, y), abs=1e-12)
        assert -180.0 < c <= 180.0
        assert from_polar(r, c) == pytest.approx([x, y], abs=1e-12)


def test_K2_to_polar_ozel_noktalar():
    r, c = to_polar((0.0, 5.0))
    assert (r, c) == (pytest.approx(5.0, abs=1e-12), pytest.approx(90.0, abs=1e-12))
    r, c = to_polar((-3.0, 0.0))
    assert (r, c) == (pytest.approx(3.0, abs=1e-12), pytest.approx(180.0, abs=1e-12))  # −180 değil
    r, c = to_polar((4.0, -4.0, -7.0))  # (x, y, z) biçimi
    assert (r, c) == (pytest.approx(4.0 * math.sqrt(2.0), abs=1e-12), pytest.approx(-45.0, abs=1e-12))


# ------------------------------------------------------------------ K2 merkez tekilliği


@pytest.mark.parametrize("h", [5.0, 2.0, -3.0])
def test_K2_polar_check_omega_max(h):
    """y = h boyunca F = 1000, doğru x = 0'dan geçer: ω_max = F / |h| rad/dk = F / (2π|h|) dev/dk."""
    F = 1000.0
    beklenen = F / abs(h) / (2 * math.pi)
    assert beklenen < C_RPM_MAX
    assert polar_check(_dogru(h, F=F), C_AXIS) == pytest.approx(beklenen, rel=1e-9)


def test_K2_polar_check_dikme_ayagi_disinda():
    """Doğru parçası x ∈ [10, 40], y = 4: en küçük r = √(10² + 4²) → ω = F·h / r²."""
    F, h = 1000.0, 4.0
    beklenen = F * h / (10.0**2 + h**2) / (2 * math.pi)
    assert polar_check(_dogru(h, x0=10.0, x1=40.0, F=F), C_AXIS) == pytest.approx(beklenen, rel=1e-9)


def test_K2_polar_check_eksen_merkezli_yay():
    """Merkez (0, 0), r = 10 yarım yay, F = 1000: ω = F / r. Yay kirişlerle denetlenirse sehim ≤ arc_tol
    (göreli fark ≤ 1e-3 / 10), bu yüzden rel 1e-3."""
    F, r = 1000.0, 10.0
    tp = _polar_yol((r, 0.0, -1.0), [Move(G3, (-r, 0.0, -1.0), feed=F, center=(0.0, 0.0))])
    assert polar_check(tp, C_AXIS) == pytest.approx(F / r / (2 * math.pi), rel=1e-3)


def test_K2_hizli_hareket_denetlenmez():
    """Yalnız kesme hareketleri: merkezden geçen G0 hata değil."""
    F, h = 1000.0, 5.0
    tp = _polar_yol(
        (-40.0, h, 5.0),
        [Move(G1, (40.0, h, 5.0), feed=F), Move(G0, (-40.0, 0.0, 5.0)), Move(G0, (40.0, 0.0, 5.0))],
    )
    assert polar_check(tp, C_AXIS) == pytest.approx(F / h / (2 * math.pi), rel=1e-9)


@pytest.mark.parametrize("h", [0.0, 1e-12, 0.5 * H_MIN])
def test_K2_merkezden_gecis_hata(h):
    with pytest.raises(CamError):
        polar_check(_dogru(h), C_AXIS)


def test_K2_omega_max_asimi_hata():
    """h = 0.5, F = 1000: F / (2π·0.5) ≈ 318 dev/dk > rpm_max = 200 → CamError."""
    assert 1000.0 / (2 * math.pi * 0.5) > C_RPM_MAX
    with pytest.raises(CamError):
        polar_check(_dogru(0.5), C_AXIS)


def test_K2_surekli_olmayan_c_ekseni_hata():
    with pytest.raises(CamError):
        polar_check(_dogru(5.0), CAxis(continuous=False, index_step=1.0, rpm_max=C_RPM_MAX))


# ------------------------------------------------------------------ alın işlemleri polar yoldur

CEP_KESME = Cut(z_top=0.0, z_bottom=-2.0, a_p=1.0, feed=500.0, plunge_feed=200.0, rpm=3000.0, z_safe=5.0)
# Eksenden uzak, y = x doğrusuna simetrik olmayan cep: kesme doğruları merkezden geçmez
CEP = Region(Profile.polygon([(6.0, 2.0), (16.0, 2.0), (16.0, 12.0), (6.0, 12.0)]))


def test_K2_alin_cebi_polar():
    M = profil()
    tp = face_pocket(CEP, freze(6.0), CEP_KESME, station=ST_EKSENEL, machine=M)
    tp.validate()
    assert tp.coord == "polar"
    assert 0.0 < polar_check(tp, M.c_axis) <= C_RPM_MAX
    z = tp.points()[:, 2]
    assert z.min() == pytest.approx(-2.0, abs=1e-9)


def test_K2_alin_konturu_polar():
    M = profil()
    prof = Profile.polygon([(6.0, 2.0), (16.0, 2.0), (16.0, 12.0), (6.0, 12.0)])
    tp = face_contour(prof, freze(6.0), CEP_KESME, "dis", station=ST_EKSENEL, machine=M)
    tp.validate()
    assert tp.coord == "polar"
    assert polar_check(tp, M.c_axis) <= C_RPM_MAX


def test_K2_merkezden_gecen_alin_konturu_hata():
    """machine verilirse polar_check: x ekseni üstünde merkezden geçen açık kontur → CamError."""
    prof = Profile.polygon([(-10.0, 0.0), (10.0, 0.0)], closed=False)
    with pytest.raises(CamError):
        face_contour(prof, freze(6.0), CEP_KESME, "uzerinde", station=ST_EKSENEL, machine=profil())


# ------------------------------------------------------------------ K3 silindirik


@pytest.mark.parametrize("r_ref", [10.0, 20.0, 37.5])
def test_K3_from_cyl(r_ref):
    """s = π·r_ref → C = 180°; s = π·r_ref/2 → 90°; s = 0 → 0°."""
    z = -10.0
    p = from_cyl(math.pi * r_ref, z, r_ref, r_ref)
    assert p.shape == (3,)
    assert p == pytest.approx([-r_ref, 0.0, z], abs=1e-12)
    assert abs(to_polar(p)[1]) == pytest.approx(180.0, abs=1e-9)
    assert from_cyl(math.pi * r_ref / 2, z, r_ref, r_ref) == pytest.approx([0.0, r_ref, z], abs=1e-12)
    assert from_cyl(0.0, z, r_ref - 2.0, r_ref) == pytest.approx([r_ref - 2.0, 0.0, z], abs=1e-12)


def test_K3_from_cyl_aci_r_ref_ile():
    """C = s / r_ref, yarıçap r'den bağımsız: s = r_ref·π/3, r = 15, r_ref = 20 → 60°."""
    p = from_cyl(20.0 * math.pi / 3, 4.0, 15.0, 20.0)
    assert p == pytest.approx([15.0 * 0.5, 15.0 * math.sqrt(3) / 2, 4.0], abs=1e-12)


R_REF, T_KANAL, Z_KANAL = 20.0, 2.0, -20.0


def _yay_kirisleri(P: np.ndarray, r: float, tol: float) -> np.ndarray:
    """z = Z_KANAL ve yarıçapı r olan kiriş noktaları; açı sırasıyla."""
    sec = P[(np.abs(P[:, 2] - Z_KANAL) <= 1e-9) & (np.abs(np.hypot(P[:, 0], P[:, 1]) - r) <= 1e-9)]
    if len(sec) > 1:  # ardışık yinelenen noktalar (hareket sınırı) tek sayılır
        sec = sec[np.r_[True, np.linalg.norm(np.diff(sec, axis=0), axis=1) > 1e-12]]
    assert len(sec) >= 2
    phi = np.unwrap(np.arctan2(sec[:, 1], sec[:, 0]))
    return phi


def _kiris_denetimi(P: np.ndarray, arc_tol: float) -> None:
    r = R_REF - T_KANAL
    phi = _yay_kirisleri(P, r, arc_tol)
    assert phi[0] == pytest.approx(0.0, abs=1e-9)
    assert phi[-1] == pytest.approx(math.pi, abs=1e-9)
    dphi = np.diff(phi)
    assert np.all(dphi > 0)  # sıralı, geri dönüş yok
    sehim = r * (1 - np.cos(dphi / 2))
    assert sehim.max() <= arc_tol * (1 + 1e-9)


def _kanal_yolu() -> Toolpath:
    """Açılmış yol: (s, z, r) = (0, Z, r_ref + 5) → dalış r_ref − t → s = π·r_ref boyunca → geri çekme."""
    r = R_REF - T_KANAL
    s1 = math.pi * R_REF
    return Toolpath(
        "kanal",
        freze(4.0),
        (0.0, Z_KANAL, R_REF + 5.0),
        [
            Move(G0, (0.0, Z_KANAL, R_REF + 1.0)),
            Move(G1, (0.0, Z_KANAL, r), feed=100.0),
            Move(G1, (s1, Z_KANAL, r), feed=300.0),
            Move(G0, (s1, Z_KANAL, R_REF + 5.0)),
        ],
        rpm=3000.0,
        coord="silindirik",
        cyl_r=R_REF,
        station=ST_RADYAL,
    )


@pytest.mark.parametrize("arc_tol", [1e-2, 1e-3])
def test_K3_cevresel_kanal_kirisleri(arc_tol):
    """Çevresel düz kanal (z sabit, s: 0 → π·r_ref): kirişler r_ref − t yayının üstünde, 0° → 180°,
    sehim ≤ arc_tol."""
    tp = _kanal_yolu()
    tp.validate()
    P = cyl_chords(tp, arc_tol=arc_tol)
    assert P.ndim == 2 and P.shape[1] == 3
    _kiris_denetimi(P, arc_tol)
    assert np.hypot(P[:, 0], P[:, 1]).min() == pytest.approx(R_REF - T_KANAL, abs=1e-9)


def test_K3_to_cartesian_silindirik():
    tp = _kanal_yolu()
    kart = to_cartesian(tp, arc_tol=1e-3)
    kart.validate()
    assert kart.coord == "kartezyen"
    assert kart.cyl_r is None
    _kiris_denetimi(kart.points(), 1e-3)


def test_K3_cyl_slot_islemi():
    """cyl_slot: coord = "silindirik", cyl_r = r_ref; açılınca taban yarıçapı r_ref − t."""
    s1 = math.pi * R_REF
    path = Profile.polygon([(0.0, Z_KANAL), (s1, Z_KANAL)], closed=False)
    tp = cyl_slot(
        path,
        freze(4.0),
        LiveCut(feed=300.0, plunge_feed=100.0, rpm=3000.0),
        R_REF,
        T_KANAL,
        station=ST_RADYAL,
        machine=profil(),
    )
    tp.validate()
    assert tp.coord == "silindirik"
    assert tp.cyl_r == pytest.approx(R_REF, abs=1e-12)
    assert tp.points()[:, 2].min() == pytest.approx(R_REF - T_KANAL, abs=1e-9)
    _kiris_denetimi(cyl_chords(tp, arc_tol=1e-3), 1e-3)


def test_to_cartesian_kartezyen_aynen():
    tp = Toolpath("k", freze(6.0), (0.0, 0.0, 5.0), [Move(G1, (10.0, 3.0, -1.0), feed=300.0)], rpm=3000.0)
    out = to_cartesian(tp)
    assert out.coord == "kartezyen"
    assert np.array_equal(out.points(), tp.points())


def test_to_cartesian_polar_parca_cercevesinde():
    """Polar yol zaten parça çerçevesinde (x, y, z): açılmış yol aynı doğru parçaları üzerinde."""
    tp = _dogru(5.0)
    out = to_cartesian(tp)
    out.validate()
    assert out.coord == "kartezyen"
    P = out.points()
    assert P[0] == pytest.approx([-40.0, 5.0, -1.0], abs=1e-12)
    assert P[-1] == pytest.approx([40.0, 5.0, -1.0], abs=1e-12)
    assert np.abs(P[:, 1] - 5.0).max() <= 1e-12
    assert np.abs(P[:, 2] + 1.0).max() <= 1e-12
