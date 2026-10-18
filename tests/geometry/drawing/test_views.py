"""SPEC 16 — K2–K5: HLR görünüşleri (geometry/drawing/views.py). OCCT gerektirir.

Testler SPEC 16 "Görünüş düzlemleri" ve "Analitik görünüş uzunlukları" bölümlerinden yazıldı; uygulama
gövdeleri okunmadı. Uydurma geometri: blok a×b×c = 100×60×30; delik d = 10, eksen (20, 25) (y asimetrik,
böylece sol görünüşteki u = −y işareti sınanır); kör delik t = 12; cep 40×20, merkez (65, 30), t = 8.

Görünüş koordinatları (SPEC 16): on (u, v) = (x, z), ust = (x, y), sol = (−y, z), sag = (y, z).
"""

from __future__ import annotations

import math
from functools import cache

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.drawing.views import project  # noqa: E402
from geometry.features import block, hole, pocket  # noqa: E402
from geometry.part import GeometryError  # noqa: E402

from ._yardim import (  # noqa: E402
    dikey_dogrular,
    en_buyuk_ortusme,
    katmandakiler,
    tam_cemberler,
    toplam_boy,
    yatay_dogrular,
)

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 30.0
D, HX, HY = 10.0, 20.0, 25.0
T_KOR = 12.0
PX, PY, PW, PL, PT = 65.0, 30.0, 40.0, 20.0, 8.0
TASMA = 2.0  # eksen çizgisi taşması [mm]


@cache
def _blok():
    return block(A, B, C)


@cache
def _delikli():
    return hole(block(A, B, C), HX, HY, D)


@cache
def _kor_delikli():
    return hole(block(A, B, C), HX, HY, D, depth=T_KOR)


@cache
def _cepli(r: float):
    return pocket(block(A, B, C), PX, PY, PW, PL, PT, r=r)


def _gorunur_gizli(view):
    return [e for e in view.edges if e.layer in ("GORUNUR", "GIZLI")]


# --- K2: blok --------------------------------------------------------------------------------------

BLOK_LG = {"on": 2 * (A + C), "ust": 2 * (A + B), "sol": 2 * (B + C), "sag": 2 * (B + C)}
BLOK_BBOX = {
    "on": ((0.0, 0.0), (A, C)),
    "ust": ((0.0, 0.0), (A, B)),
    "sol": ((-B, 0.0), (0.0, C)),
    "sag": ((0.0, 0.0), (B, C)),
}


@pytest.mark.parametrize("yon", ["on", "ust", "sol", "sag"])
def test_blok_boylar(yon):
    view = project(_blok(), yon)
    assert view.direction == yon
    assert toplam_boy(view.edges, "GORUNUR") == pytest.approx(BLOK_LG[yon], rel=1e-9)
    assert toplam_boy(view.edges, "GIZLI") == pytest.approx(0.0, abs=1e-9)
    assert en_buyuk_ortusme(_gorunur_gizli(view)) < 1e-6


@pytest.mark.parametrize("yon", ["on", "ust", "sol", "sag"])
def test_blok_sinir_kutusu(yon):
    lo, hi = project(_blok(), yon).bbox()
    assert np.asarray(lo, float) == pytest.approx(np.array(BLOK_BBOX[yon][0]), abs=1e-9)
    assert np.asarray(hi, float) == pytest.approx(np.array(BLOK_BBOX[yon][1]), abs=1e-9)


def test_blokta_eksen_cizgisi_yok():
    for yon in ("on", "ust", "sol"):
        assert katmandakiler(project(_blok(), yon).edges, "EKSEN") == []


@pytest.mark.parametrize("yon", ["arka", "alt", "", "ON"])
def test_gecersiz_yon_hata(yon):
    with pytest.raises(GeometryError):
        project(_blok(), yon)


# --- K3: delikler ----------------------------------------------------------------------------------


def test_boydan_delik_ust_tam_cember():
    view = project(_delikli(), "ust")
    cem = tam_cemberler(view.edges)
    assert len(cem) == 1
    assert np.linalg.norm(np.asarray(cem[0].c, float) - [HX, HY]) < 1e-6
    assert cem[0].r == pytest.approx(D / 2, abs=1e-6)
    assert toplam_boy(view.edges, "GORUNUR") == pytest.approx(2 * (A + B) + math.pi * D, rel=1e-6)
    assert toplam_boy(view.edges, "GIZLI") == pytest.approx(0.0, abs=1e-6)


def test_boydan_delik_on():
    """Ön: L_h = 2c, u = x ± d/2'de iki dikey gizli çizgi (v ∈ [0, c])."""
    view = project(_delikli(), "on")
    assert toplam_boy(view.edges, "GORUNUR") == pytest.approx(2 * (A + C), rel=1e-6)
    assert toplam_boy(view.edges, "GIZLI") == pytest.approx(2 * C, rel=1e-6)
    for u in (HX - D / 2, HX + D / 2):
        cizgiler = dikey_dogrular(view.edges, "GIZLI", u)
        assert sum(abs(e.p1[1] - e.p0[1]) for e in cizgiler) == pytest.approx(C, rel=1e-6)
    assert en_buyuk_ortusme(_gorunur_gizli(view)) < 1e-6


def test_boydan_delik_sol():
    """Sol: L_h = 2c, u = −y ± d/2'de."""
    view = project(_delikli(), "sol")
    assert toplam_boy(view.edges, "GORUNUR") == pytest.approx(2 * (B + C), rel=1e-6)
    assert toplam_boy(view.edges, "GIZLI") == pytest.approx(2 * C, rel=1e-6)
    for u in (-HY - D / 2, -HY + D / 2):
        cizgiler = dikey_dogrular(view.edges, "GIZLI", u)
        assert sum(abs(e.p1[1] - e.p0[1]) for e in cizgiler) == pytest.approx(C, rel=1e-6)


def test_boydan_delik_sag():
    """Sağ: u = y ± d/2'de gizli çizgiler."""
    view = project(_delikli(), "sag")
    assert toplam_boy(view.edges, "GIZLI") == pytest.approx(2 * C, rel=1e-6)
    for u in (HY - D / 2, HY + D / 2):
        assert dikey_dogrular(view.edges, "GIZLI", u)


def test_kor_delik_on():
    """Kör delik: L_h = 2t + d; dip çizgisi v = c − t'de, boyu d."""
    view = project(_kor_delikli(), "on")
    assert toplam_boy(view.edges, "GORUNUR") == pytest.approx(2 * (A + C), rel=1e-6)
    assert toplam_boy(view.edges, "GIZLI") == pytest.approx(2 * T_KOR + D, rel=1e-6)
    dip = yatay_dogrular(view.edges, "GIZLI", C - T_KOR)
    assert sum(abs(e.p1[0] - e.p0[0]) for e in dip) == pytest.approx(D, rel=1e-6)
    assert en_buyuk_ortusme(_gorunur_gizli(view)) < 1e-6


# --- K4: cep ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("r", [0.0, 5.0])
def test_cep_on(r):
    view = project(_cepli(r), "on")
    assert toplam_boy(view.edges, "GORUNUR") == pytest.approx(2 * (A + C), rel=1e-6)
    assert toplam_boy(view.edges, "GIZLI") == pytest.approx(2 * PT + PW, rel=1e-6)
    assert en_buyuk_ortusme(_gorunur_gizli(view)) < 1e-6


@pytest.mark.parametrize("r", [0.0, 5.0])
def test_cep_sol(r):
    view = project(_cepli(r), "sol")
    assert toplam_boy(view.edges, "GIZLI") == pytest.approx(2 * PT + PL, rel=1e-6)


@pytest.mark.parametrize("r", [0.0, 5.0])
def test_cep_ust(r):
    """Üst: L_g = 2(a + b) + P, P = 2(w + l) − (8 − 2π) r; ağız ve dip tek sayılır."""
    P = 2 * (PW + PL) - (8 - 2 * math.pi) * r
    view = project(_cepli(r), "ust")
    assert toplam_boy(view.edges, "GORUNUR") == pytest.approx(2 * (A + B) + P, rel=1e-6)
    assert toplam_boy(view.edges, "GIZLI") == pytest.approx(0.0, abs=1e-6)


def test_cep_teget_kenar_cizilmiyor():
    """r > 0: köşe silindiri ile düz duvarın teğet geçişi (ön görünüşte u = x ± (w/2 − r)) çizilmez."""
    r = 5.0
    view = project(_cepli(r), "on")
    for u in (PX - PW / 2 + r, PX + PW / 2 - r):
        for layer in ("GORUNUR", "GIZLI"):
            assert dikey_dogrular(view.edges, layer, u) == []


# --- K5: eksen çizgileri ---------------------------------------------------------------------------


def test_ust_eksen_cizgileri():
    """Üst görünüşte merkezden geçen yatay ve dikey EKSEN çizgisi, çemberden 2 mm taşar."""
    view = project(_delikli(), "ust")
    R = D / 2
    yatay = yatay_dogrular(view.edges, "EKSEN", HY)
    dikey = dikey_dogrular(view.edges, "EKSEN", HX)
    assert len(yatay) == 1 and len(dikey) == 1
    us = sorted([yatay[0].p0[0], yatay[0].p1[0]])
    vs = sorted([dikey[0].p0[1], dikey[0].p1[1]])
    assert us == pytest.approx([HX - R - TASMA, HX + R + TASMA], abs=1e-6)
    assert vs == pytest.approx([HY - R - TASMA, HY + R + TASMA], abs=1e-6)


def test_on_eksen_cizgisi():
    """Ön görünüşte delik ekseni u = x'te, delik boyunca (v ∈ [0, c]) 2 mm taşar."""
    view = project(_delikli(), "on")
    eks = dikey_dogrular(view.edges, "EKSEN", HX)
    assert len(eks) == 1
    vs = sorted([eks[0].p0[1], eks[0].p1[1]])
    assert vs == pytest.approx([-TASMA, C + TASMA], abs=1e-6)


def test_axes_false_eksen_yok():
    for yon in ("on", "ust"):
        view = project(_delikli(), yon, axes=False)
        assert katmandakiler(view.edges, "EKSEN") == []
