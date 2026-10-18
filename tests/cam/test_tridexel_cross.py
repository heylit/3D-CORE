"""SPEC 43 K7 — SPEC 05 dexel'iyle çapraz kontrol (takım ekseni +Z).

Testler SPEC 43 "05 ile çapraz kontrol" bölümünden yazıldı; cam.sim.tridexel / simulate5 kodu okunmadı.
Kaynak: ekseni +Z olan programda Z ailesi SPEC 05 dexel'iyle aynı ızgarada aynı (aralık uçları 1e-6, hacim
rel 1e-9); X ve Y aileleri aynı katıyı başka yönden örnekler, hacimleri O(Δ) ile aynı değere yakınsar.
Rastgele program SPEC 05 K16/K19'daki ile aynı (tests/cam/simref.py, sabit tohum).

Not: küresel uçta iki modülün zarfı da 1e-6 hatayla hesaplanabilir (SPEC 05 K5, SPEC 43 K5); bu yüzden
küresel uçta aralık toleransı 2e-6 ve hacim toleransı hücre sayısı · 2e-6 · dx·dy.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.sim import simulate, simulate5
from tests.cam.simref import RANDOM_STOCK, ball, flat, random_program, rect_pocket

CELL = 1.0


@pytest.mark.parametrize("ad", ["duz", "kuresel"])
def test_K7_z_ailesi_05_dexel_ile_ayni(ad):
    tool = {"duz": flat(D=6.0, Lf=30.0), "kuresel": ball(D=6.0, Lf=30.0)}[ad]
    tol = 1e-6 if ad == "duz" else 2e-6
    prog = random_program(tool, n=50)
    r05 = simulate([prog], RANDOM_STOCK, cell=CELL, model="dexel")
    r43 = simulate5([prog], RANDOM_STOCK, cell=CELL)
    d = r05.dexel
    td = r43.tridexel
    assert (td.nx, td.ny) == (d.nx, d.ny)
    for i in range(d.nx):
        for j in range(d.ny):
            a = np.array(d.intervals(i, j), dtype=float).reshape(-1, 2)
            b = np.array(td.intervals("z", i, j), dtype=float).reshape(-1, 2)
            assert a.shape == b.shape, (i, j, a, b)
            np.testing.assert_allclose(b, a, rtol=0, atol=tol)
    Vz = td.volumes()[2]
    if ad == "duz":
        assert Vz == pytest.approx(d.volume(), rel=1e-9)
    else:
        assert Vz == pytest.approx(d.volume(), abs=d.nx * d.ny * tol * d.dx * d.dy)


def test_K7_x_y_aileleri_ayni_hacme_yakin():
    """Rastgele programda X ve Y hacimleri Z'ninkinden kaldırılan hacmin %1'inden az sapar
    (bağımsız kaba referansta aileler arası fark %0.1 mertebesinde)."""
    prog = random_program(flat(D=6.0, Lf=30.0), n=50)
    r43 = simulate5([prog], RANDOM_STOCK, cell=CELL)
    Vx, Vy, Vz = r43.tridexel.volumes()
    kaldirilan = RANDOM_STOCK.volume - Vz
    assert kaldirilan > 1000.0
    assert abs(Vx - Vz) <= 0.01 * kaldirilan
    assert abs(Vy - Vz) <= 0.01 * kaldirilan
    assert r43.removed_volume == pytest.approx(RANDOM_STOCK.volume - r43.tridexel.volume(), rel=1e-9)


@pytest.mark.parametrize("cell", [1.0, 0.5])
def test_K7_dikdortgen_cep_uc_aile(cell):
    """SPEC 05 K7 cebi: her aile kaldırılan hacmi (ab − (4 − π)R²)·H'yi P·Δ·H toleransında verir."""
    from cam.model import Stock

    stok = Stock(0.0, 0.0, -20.0, 60.3, 40.7, 0.0)
    x0, y0, a, b, H, R = 7.3, 5.6, 31.7, 22.9, 5.0, 3.0
    res = simulate5([rect_pocket(flat(D=6.0), x0, y0, a, b, -H)], stok, cell=cell)
    V = (a * b - (4 - math.pi) * R**2) * H
    P = 2 * (a + b) - (8 - 2 * math.pi) * R
    for Vi in res.tridexel.volumes():
        assert stok.volume - Vi == pytest.approx(V, abs=P * cell * H)


def test_K7_sure_05_ile_ayni():
    """Süre 05 kuralıyla uç yolu boyundan: aynı programda adım süreleri ve toplam aynı."""
    prog = random_program(flat(D=6.0, Lf=30.0), n=50)
    r05 = simulate([prog], RANDOM_STOCK, cell=CELL)
    r43 = simulate5([prog], RANDOM_STOCK, cell=CELL)
    assert r43.total_time == pytest.approx(r05.total_time, rel=1e-12)
    assert len(r43.steps) == len(r05.steps)
    for a, b in zip(r43.steps, r05.steps, strict=True):
        assert (a.k, a.op, a.type, a.link) == (b.k, b.op, b.type, b.link)
        assert a.duration == pytest.approx(b.duration, rel=1e-12)
