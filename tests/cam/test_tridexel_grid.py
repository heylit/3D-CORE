"""SPEC 43 K1 — tri-dexel ızgarası.

Testler SPEC 43 "Izgara ve ışınlar" ve "Arayüz" bölümlerinden yazıldı; cam.sim.tridexel kodu okunmadı.
Kaynak: SPEC 05 kuralı n = ⌈L/Δ⌉, d = L/n, merkez min + (i + ½)·d; Z ışınları XY, X ışınları YZ, Y ışınları XZ
hücre merkezlerinden; başlangıçta her ışında stok boyunca tek aralık, V_x = V_y = V_z = Stock.volume.
"""

from __future__ import annotations

import math

import pytest

from cam.model import CamError, Stock
from cam.sim import TriDexel
from tests.cam.tridexref import grid3

STOK = Stock(-5.0, 2.0, -20.0, 5.3, 9.0, 1.5)  # 10.3 × 7 × 21.5


@pytest.mark.parametrize("cell", [1.0, 0.8, 3.0])
def test_K1_izgara_tanimi(cell):
    t = TriDexel.from_stock(STOK, cell)
    (nx, dx, _), (ny, dy, _), (nz, dz, _) = grid3(STOK, cell)
    assert (t.nx, t.ny, t.nz) == (nx, ny, nz)
    assert t.dx == pytest.approx(dx, rel=1e-12)
    assert t.dy == pytest.approx(dy, rel=1e-12)
    assert t.dz == pytest.approx(dz, rel=1e-12)
    assert (t.x0, t.y0, t.z0) == (STOK.xmin, STOK.ymin, STOK.zmin)


def test_K1_baslangic_araliklari():
    t = TriDexel.from_stock(STOK, 1.0)
    for i in range(t.nx):
        for j in range(t.ny):
            assert t.intervals("z", i, j) == [(pytest.approx(STOK.zmin), pytest.approx(STOK.zmax))]
    for j in range(t.ny):
        for k in range(t.nz):
            assert t.intervals("x", j, k) == [(pytest.approx(STOK.xmin), pytest.approx(STOK.xmax))]
    for i in range(t.nx):
        for k in range(t.nz):
            assert t.intervals("y", i, k) == [(pytest.approx(STOK.ymin), pytest.approx(STOK.ymax))]


@pytest.mark.parametrize("cell", [1.0, 0.33, 0.25])
def test_K1_baslangic_hacimleri(cell):
    t = TriDexel.from_stock(STOK, cell)
    Vx, Vy, Vz = t.volumes()
    for V in (Vx, Vy, Vz, t.volume()):
        assert V == pytest.approx(STOK.volume, rel=1e-12)


def test_K1_copy_bagimsiz():
    t = TriDexel.from_stock(STOK, 1.0)
    c = t.copy()
    assert (c.nx, c.ny, c.nz, c.dx, c.dy, c.dz, c.x0, c.y0, c.z0) == (
        t.nx,
        t.ny,
        t.nz,
        t.dx,
        t.dy,
        t.dz,
        t.x0,
        t.y0,
        t.z0,
    )
    assert c.volumes() == pytest.approx(t.volumes(), rel=1e-15)


@pytest.mark.parametrize("cell", [0.0, -1.0, math.nan, math.inf, -math.inf])
def test_K1_gecersiz_hucre(cell):
    with pytest.raises(CamError):
        TriDexel.from_stock(STOK, cell)


def test_K1_max_rays():
    s = Stock(0.0, 0.0, 0.0, 10.0, 20.0, 5.0)  # cell 1: 10·20 + 20·5 + 10·5 = 350 ışın
    with pytest.raises(CamError):
        TriDexel.from_stock(s, 1.0, max_rays=349)
    t = TriDexel.from_stock(s, 1.0, max_rays=350)  # sınırda kabul
    assert (t.nx, t.ny, t.nz) == (10, 20, 5)
