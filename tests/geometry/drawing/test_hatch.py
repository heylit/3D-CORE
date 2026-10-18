"""SPEC 16 — K6: tarama (geometry/drawing/hatch.py). OCCT gerektirmez.

Teori: doğrular n·p = (k + ½)·s, n = (−sin θ, cos θ). Eksen-paralel W × H dikdörtgende (θ = 0) doğru sayısı
H/s, toplam boy A/s; genel bölgede s·ΣL → A (orta nokta kuralı). Uygulama gövdeleri okunmadı.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from geometry.drawing.hatch import hatch
from geometry.drawing.types import Line2D
from geometry.part import GeometryError, Region

from ._yardim import bolge_alani, bolge_icinde, bolge_sinirina_uzaklik, boy


def dikdortgen(x0, y0, x1, y1, ccw=True) -> np.ndarray:
    P = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float)
    return P if ccw else P[::-1].copy()


def cember_cokgeni(cx, cy, r, n=200, ccw=True) -> np.ndarray:
    t = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    if not ccw:
        t = -t
    return np.column_stack([cx + r * np.cos(t), cy + r * np.sin(t)])


KARE_DELIKLI = Region(dikdortgen(0, 0, 40, 40), (dikdortgen(10, 10, 30, 30, ccw=False),))
UCGEN = Region(np.array([[0.0, 0.0], [50.0, 0.0], [10.0, 30.0]]))


def _uc(e: Line2D):
    return np.asarray(e.p0, float), np.asarray(e.p1, float)


@pytest.mark.parametrize("W, H, s", [(30.0, 12.0, 3.0), (17.5, 10.0, 2.5), (100.0, 60.0, 0.5)])
def test_dikdortgen_theta0_sayi_ve_boy(W, H, s):
    """θ = 0: v = (k + ½)s doğruları, sayı H/s, her biri W boyunda, toplam A/s."""
    seg = hatch([Region(dikdortgen(0, 0, W, H))], s=s, theta=0.0)
    assert len(seg) == round(H / s)
    assert sum(boy(e) for e in seg) == pytest.approx(W * H / s, rel=1e-9)
    for e in seg:
        p0, p1 = _uc(e)
        assert p0[1] == pytest.approx(p1[1], abs=1e-9)
        assert boy(e) == pytest.approx(W, rel=1e-9)
        k = p0[1] / s - 0.5
        assert k == pytest.approx(round(k), abs=1e-9)


def test_katman_tarama():
    seg = hatch([Region(dikdortgen(0, 0, 10, 10))])
    assert seg
    assert all(isinstance(e, Line2D) and e.layer == "TARAMA" for e in seg)


@pytest.mark.parametrize("region", [KARE_DELIKLI, UCGEN], ids=["delikli_kare", "ucgen"])
def test_theta45_uclar_sinirda_orta_icerde(region):
    seg = hatch([region], s=3.0, theta=45.0)
    assert seg
    th = math.radians(45.0)
    n = np.array([-math.sin(th), math.cos(th)])
    for e in seg:
        p0, p1 = _uc(e)
        assert bolge_sinirina_uzaklik(p0, region) < 1e-9
        assert bolge_sinirina_uzaklik(p1, region) < 1e-9
        assert bolge_icinde(0.5 * (p0 + p1), region)
        # doğru ailesi: n·p = (k + ½)s
        assert n @ p0 == pytest.approx(n @ p1, abs=1e-9)
        k = (n @ p0) / 3.0 - 0.5
        assert k == pytest.approx(round(k), abs=1e-9)


def test_delik_icinde_tarama_yok():
    """Delikli karede hiçbir tarama parçası deliğin içinden geçmez (parça boyunca örneklenir)."""
    seg = hatch([KARE_DELIKLI], s=1.0, theta=45.0)
    delik = Region(dikdortgen(10, 10, 30, 30))
    for e in seg:
        p0, p1 = _uc(e)
        for t in np.linspace(0.02, 0.98, 25):
            q = p0 + t * (p1 - p0)
            assert not bolge_icinde(q, delik) or bolge_sinirina_uzaklik(q, delik) < 1e-9


@pytest.mark.parametrize(
    "region",
    [
        KARE_DELIKLI,
        UCGEN,
        Region(cember_cokgeni(5.0, -3.0, 12.0), (cember_cokgeni(5.0, -3.0, 4.0, ccw=False),)),
    ],
    ids=["delikli_kare", "ucgen", "halka"],
)
@pytest.mark.parametrize("theta", [0.0, 30.0, 45.0])
def test_ince_aralikta_alan(region, theta):
    """s = 0.1: s·ΣL ≈ A (rel 1e-2)."""
    s = 0.1
    seg = hatch([region], s=s, theta=theta)
    assert s * sum(boy(e) for e in seg) == pytest.approx(bolge_alani(region), rel=1e-2)


def test_birden_cok_bolge():
    regs = [Region(dikdortgen(0, 0, 30, 12)), Region(dikdortgen(50, 0, 60, 12))]
    seg = hatch(regs, s=3.0, theta=0.0)
    assert sum(boy(e) for e in seg) == pytest.approx((30 * 12 + 10 * 12) / 3.0, rel=1e-9)


@pytest.mark.parametrize("s", [0.0, -1.0])
def test_gecersiz_aralik_hata(s):
    with pytest.raises(GeometryError):
        hatch([Region(dikdortgen(0, 0, 10, 10))], s=s)


def test_bos_bolge_hata():
    with pytest.raises(GeometryError):
        hatch([], s=3.0)
