"""SPEC 16 — K7: düzlemsel kesit (geometry/drawing/views.section). OCCT gerektirir.

Teori: boydan boya delikli blokta delik ekseninden (y₀ = y) `on` kesiti → iki bölge
[0, x − d/2] × [0, c] ve [x + d/2, a] × [0, c], A = c(a − d), L_g = 2a + 4c, gizli çizgi yok.
Uygulama gövdeleri okunmadı. Uydurma geometri: blok 100×60×30, delik d = 10, eksen (20, 25).
"""

from __future__ import annotations

from functools import cache

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.drawing.views import section  # noqa: E402
from geometry.features import block, hole  # noqa: E402
from geometry.part import GeometryError  # noqa: E402

from ._yardim import bolge_alani, bolge_icinde, bolge_sinirina_uzaklik, toplam_boy  # noqa: E402

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 30.0
D, HX, HY = 10.0, 20.0, 25.0


@cache
def _delikli():
    return hole(block(A, B, C), HX, HY, D)


@cache
def _kesit():
    return section(_delikli(), "on", HY)


def test_kesit_adi_ve_yonu():
    view = _kesit()
    assert view.name == "A-A"
    assert view.direction == "on"


def test_iki_bolge_ve_alan():
    regions = _kesit().regions
    assert len(regions) == 2
    alan = sum(bolge_alani(r) for r in regions)
    assert alan == pytest.approx(C * (A - D), rel=1e-6)
    kutular = sorted(
        (tuple(np.asarray(r.outer, float).min(axis=0)), tuple(np.asarray(r.outer, float).max(axis=0)))
        for r in regions
    )
    beklenen = [((0.0, 0.0), (HX - D / 2, C)), ((HX + D / 2, 0.0), (A, C))]
    for (lo, hi), (blo, bhi) in zip(kutular, beklenen, strict=True):
        assert np.array(lo) == pytest.approx(np.array(blo), abs=1e-6)
        assert np.array(hi) == pytest.approx(np.array(bhi), abs=1e-6)


def test_bolgeler_ccw():
    for r in _kesit().regions:
        P = np.asarray(r.outer, float)
        x, y = P[:, 0], P[:, 1]
        assert 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) > 0


def test_gorunen_boy_ve_gizli_yok():
    view = _kesit()
    assert toplam_boy(view.edges, "GORUNUR") == pytest.approx(2 * A + 4 * C, rel=1e-6)
    assert [e for e in view.edges if e.layer == "GIZLI"] == []


def test_tarama_bolgelerin_icinde():
    view = _kesit()
    assert view.hatch
    for e in view.hatch:
        assert e.layer == "TARAMA"
        p0, p1 = np.asarray(e.p0, float), np.asarray(e.p1, float)
        for t in np.linspace(0.05, 0.95, 7):
            q = p0 + t * (p1 - p0)
            assert any(bolge_icinde(q, r) or bolge_sinirina_uzaklik(q, r) < 1e-6 for r in view.regions)
        mid = 0.5 * (p0 + p1)
        assert any(bolge_icinde(mid, r) for r in view.regions)


@pytest.mark.parametrize("yon, offset", [("on", -5.0), ("on", B + 5.0), ("ust", C + 1.0), ("sol", -1.0)])
def test_kesmeyen_duzlem_hata(yon, offset):
    with pytest.raises(GeometryError):
        section(_delikli(), yon, offset)


def test_gecersiz_yon_hata():
    with pytest.raises(GeometryError):
        section(_delikli(), "arka", HY)
