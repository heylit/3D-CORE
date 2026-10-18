"""SPEC 51 K2–K3 — döndürülmüş iş düzlemi: açılar ve 3+2 gidiş-dönüş.

Testler yalnız SPEC 51 metninden ve iskelet imzalarından yazıldı (bkz. `post5_ortak`).
- Sinumerik `CYCLE800` ve Heidenhain `PLANE SPATIAL`: eksenel açılar, R = Rz(c)·Ry(b)·Rx(a) (41 `xyz_angles`).
- Fanuc `G68.2`: ZXZ Euler, R = Rz(α)·Rx(β)·Rz(γ) (41 `zxz_angles`).
Beklenen açılar testin kendi matrisinden elle hesaplanır.
Varsayım: `swivel_angles` tam üç açı döndürür.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import Frame
from cam.multiaxis.indexed import from_xyz, from_zxz
from cam.post import post5, read_program5, swivel_angles
from tests.cam.post5_ortak import (
    DILLER,
    KINEMATIKLER,
    KURULUM,
    TAKIMLAR,
    TOL_ACI,
    TOL_P,
    ac_masa,
    egik_cep,
    kesmeler,
    makine,
    tek_yol,
)

TOL = 1e-9


def Rx(t: float) -> np.ndarray:
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def Ry(t: float) -> np.ndarray:
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def Rz(t: float) -> np.ndarray:
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def cerceve(R: np.ndarray, o=(5.0, -3.0, -10.0)) -> Frame:
    return Frame(origin=tuple(o), R=tuple(tuple(float(v) for v in r) for r in R))


def xyz_elle(R: np.ndarray) -> tuple[float, float, float]:
    """R = Rz(c)·Ry(b)·Rx(a): R20 = −sin b, R21/R22 = tan a, R10/R00 = tan c (cos b > 0)."""
    b = math.degrees(math.asin(-R[2, 0]))
    a = math.degrees(math.atan2(R[2, 1], R[2, 2]))
    c = math.degrees(math.atan2(R[1, 0], R[0, 0]))
    return a, b, c


R_ZXZ = Rz(30.0) @ Rx(45.0) @ Rz(60.0)

# (ad, R, eksenel (a, b, c), ZXZ (α, β, γ)); tekil durumda (+Z) ZXZ'de γ = 0 kuralı (41)
DURUMLAR = [
    ("arti_z", np.eye(3), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    ("x_30", Rx(30.0), (30.0, 0.0, 0.0), (0.0, 30.0, 0.0)),
    ("zxz_30_45_60", R_ZXZ, xyz_elle(R_ZXZ), (30.0, 45.0, 60.0)),
]
EKSENEL = {"sinumerik", "heidenhain"}


def test_el_hesabi_tutarli():
    """xyz_elle kendi kurucusunu geri veriyor; ZXZ durumunun eksenel açıları tekil değil."""
    a, b, c = 12.0, -34.0, 56.0
    np.testing.assert_allclose(xyz_elle(Rz(c) @ Ry(b) @ Rx(a)), (a, b, c), atol=1e-12)
    a, b, c = xyz_elle(R_ZXZ)
    np.testing.assert_allclose(Rz(c) @ Ry(b) @ Rx(a), R_ZXZ, atol=1e-12)
    assert abs(b) < 89.0


# ---------------------------------------------------------------- K2


@pytest.mark.parametrize("dil", DILLER)
@pytest.mark.parametrize("ad, R, xyz, zxz", DURUMLAR, ids=[d[0] for d in DURUMLAR])
def test_k2_bilinen_cercevelerin_acilari(dil, ad, R, xyz, zxz):
    m = makine(dil, ac_masa())
    acilar = swivel_angles(cerceve(R), m)
    assert len(acilar) == 3
    beklenen = xyz if dil in EKSENEL else zxz
    np.testing.assert_allclose(acilar, beklenen, atol=TOL)


@pytest.mark.parametrize("dil", DILLER)
@pytest.mark.parametrize(
    "R",
    [np.eye(3), Rx(30.0), R_ZXZ, Ry(-25.0) @ Rz(110.0), Rz(-75.0) @ Rx(60.0) @ Rz(15.0)],
    ids=["arti_z", "x_30", "zxz", "yz", "zxz_2"],
)
def test_k2_aci_kurucu_gidis_donus(dil, R):
    """swivel_angles → from_xyz / from_zxz → aynı çerçeve, 1e-12."""
    fr = cerceve(R)
    a = swivel_angles(fr, makine(dil, ac_masa()))
    geri = from_xyz(fr.origin, *a) if dil in EKSENEL else from_zxz(fr.origin, *a)
    np.testing.assert_allclose(np.array(geri.R), np.array(fr.R), atol=1e-12)


# ---------------------------------------------------------------- K3


def _r_tol() -> float:
    """Üç açının yuvarlama hatası toplamı [rad]: R elemanları en çok bu kadar sapar."""
    return 3.0 * math.radians(TOL_ACI) + 1e-12


@pytest.mark.parametrize("kin_ad", list(KINEMATIKLER))
@pytest.mark.parametrize("dil", DILLER)
def test_k3_egik_cep_gidis_donus(dil, kin_ad):
    """Eğik yüzde cep üç dilde yazılıp okununca frame ve yerel kesme hareketleri aynı; yaylar yay."""
    fr = from_xyz((10.0, -5.0, -8.0), 20.0, -15.0, 30.0)
    tp = egik_cep(fr)
    m = makine(dil, KINEMATIKLER[kin_ad]())
    okunan = tek_yol(read_program5(post5([tp], m, KURULUM, TAKIMLAR), m, TAKIMLAR))
    assert okunan.frame is not None
    np.testing.assert_allclose(np.array(okunan.frame.R), np.array(fr.R), atol=_r_tol())
    np.testing.assert_allclose(okunan.frame.origin, fr.origin, atol=TOL_P)
    a, b = kesmeler(tp), kesmeler(okunan)
    assert [x.type for x in b] == [x.type for x in a]  # yaylar yay olarak kalıyor
    for i, (ma, mb) in enumerate(zip(a, b, strict=True)):
        assert np.linalg.norm(np.subtract(mb.end, ma.end)) <= TOL_P, f"hareket {i}"
        if ma.center is not None:
            assert np.linalg.norm(np.subtract(mb.center, ma.center)) <= TOL_P, f"hareket {i} merkez"
