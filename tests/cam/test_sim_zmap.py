"""SPEC 05 K1 — z-haritası ızgarası.

Testler SPEC 05 "Z-haritası" ve "Arayüz" bölümlerinden yazıldı; cam.sim kodu okunmadı.
Kaynak: nx = ⌈(xmax − xmin)/Δ⌉, dx = (xmax − xmin)/nx, merkez x_i = xmin + (i + ½)·dx, z[j, i] şekli (ny, nx);
başlangıçta z = zmax, hacim V = Σ (z − zmin)·dx·dy = Stock.volume.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, Stock
from cam.sim import ZMap

STOK = Stock(-5.0, 2.0, -20.0, 5.3, 9.0, 1.5)  # 10.3 × 7 × 21.5, ızgaraya hizasız x


@pytest.mark.parametrize("cell", [1.0, 0.8, 0.25, 3.0])
def test_izgara_tanimi(cell):
    g = ZMap.from_stock(STOK, cell)
    Lx, Ly = STOK.xmax - STOK.xmin, STOK.ymax - STOK.ymin
    nx, ny = math.ceil(Lx / cell), math.ceil(Ly / cell)
    assert (g.nx, g.ny) == (nx, ny)
    assert g.dx == pytest.approx(Lx / nx, rel=1e-12)
    assert g.dy == pytest.approx(Ly / ny, rel=1e-12)
    assert g.dx <= cell + 1e-12 and g.dy <= cell + 1e-12  # gerçek adım ≤ Δ
    assert (g.x0, g.y0) == (STOK.xmin, STOK.ymin)
    assert (g.zmin, g.zmax) == (STOK.zmin, STOK.zmax)
    assert g.z.shape == (ny, nx)
    assert np.all(g.z == STOK.zmax)


def test_merkezler():
    g = ZMap.from_stock(STOK, 1.0)
    X, Y = g.centers()
    assert X.shape == Y.shape == (g.ny, g.nx)
    i = np.arange(g.nx)
    j = np.arange(g.ny)
    np.testing.assert_allclose(X[3, :], STOK.xmin + (i + 0.5) * g.dx, rtol=0, atol=1e-12)
    np.testing.assert_allclose(Y[:, 4], STOK.ymin + (j + 0.5) * g.dy, rtol=0, atol=1e-12)
    # stok tam örtülür: son merkez + yarım hücre = xmax
    assert X[0, -1] + g.dx / 2 == pytest.approx(STOK.xmax, abs=1e-12)
    assert Y[-1, 0] + g.dy / 2 == pytest.approx(STOK.ymax, abs=1e-12)


@pytest.mark.parametrize("cell", [1.0, 0.33, 0.1])
def test_baslangic_hacmi(cell):
    g = ZMap.from_stock(STOK, cell)
    assert g.volume() == pytest.approx(STOK.volume, rel=1e-12)


def test_hacim_formulu():
    g = ZMap.from_stock(STOK, 1.0)
    rng = np.random.default_rng(1)
    g.z = rng.uniform(STOK.zmin, STOK.zmax, size=g.z.shape)
    beklenen = float(np.sum(g.z - STOK.zmin)) * g.dx * g.dy
    assert g.volume() == pytest.approx(beklenen, rel=1e-12)


def test_copy_bagimsiz():
    g = ZMap.from_stock(STOK, 1.0)
    h = g.copy()
    h.z[0, 0] = -3.0
    assert g.z[0, 0] == STOK.zmax
    assert (h.nx, h.ny, h.dx, h.dy, h.x0, h.y0, h.zmin, h.zmax) == (
        g.nx,
        g.ny,
        g.dx,
        g.dy,
        g.x0,
        g.y0,
        g.zmin,
        g.zmax,
    )


@pytest.mark.parametrize("cell", [0.0, -1.0, math.nan, math.inf, -math.inf])
def test_gecersiz_hucre(cell):
    with pytest.raises(CamError):
        ZMap.from_stock(STOK, cell)


def test_max_cells():
    s = Stock(0, 0, -1, 100, 100, 0)
    with pytest.raises(CamError):
        ZMap.from_stock(s, 1.0, max_cells=9_999)  # 100 · 100 = 10 000 hücre
    g = ZMap.from_stock(s, 1.0, max_cells=10_000)  # sınırda kabul
    assert g.nx * g.ny == 10_000
