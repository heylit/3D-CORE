"""SPEC 52 K1 — silindirik yükseklik haritası (PolarMap): ızgara, hacim, RadialMap'ten başlangıç.

Testler SPEC 52 "Silindirik yükseklik haritası" ve "Arayüz" bölümlerinden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 52):
- Izgara n_θ × n_z, Δθ = 360/n_θ, θ_j = (j + ½)·Δθ, z_i = z0 + (i + ½)·dz;
  dz stok boyunu tam böler (⌈L/dz⌉ hücre).
- Hücrede radyal aralık [r_iç, r_dış]; dolu milde r_iç = 0, delikte r_iç = d/2; r_in, r_out (n_θ, n_z).
- Hacim V = Σ ½(r_dış² − r_iç²)·Δθ[rad]·Δz; from_stock hacmi CylinderStock.volume'a rel ≤ (Δθ[rad])²/6.
- from_radial: dönel simetrik RadialMap, her θ aynı; aynı ızgarada hacim rel 1e-9.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CylinderStock
from cam.sim import PolarMap, RadialMap

DOLU = CylinderStock(D=40.0, zmin=-25.0, zmax=0.0)
BORU = CylinderStock(D=40.0, zmin=-25.0, zmax=0.0, d=10.0)


@pytest.mark.parametrize("stok, r_ic", [(DOLU, 0.0), (BORU, 5.0)])
def test_K1_from_stock_izgara(stok, r_ic):
    """dz = 0.07 → n_z = ⌈25/0.07⌉ = 358, dz = 25/358; Δθ = 2° → n_θ = 180."""
    m = PolarMap.from_stock(stok, dtheta_deg=2.0, dz=0.07)
    assert m.n_theta == 180
    assert m.n_z == 358
    assert m.dz == pytest.approx(25.0 / 358, rel=1e-12)
    assert m.z0 == pytest.approx(-25.0, abs=1e-12)
    np.testing.assert_allclose(m.thetas(), (np.arange(180) + 0.5) * 2.0, rtol=0, atol=1e-12)
    np.testing.assert_allclose(m.centers(), -25.0 + (np.arange(358) + 0.5) * 25.0 / 358, rtol=0, atol=1e-9)
    assert np.asarray(m.r_in).shape == (180, 358) and np.asarray(m.r_out).shape == (180, 358)
    np.testing.assert_allclose(m.r_in, r_ic, rtol=0, atol=1e-12)
    np.testing.assert_allclose(m.r_out, 20.0, rtol=0, atol=1e-12)


@pytest.mark.parametrize("stok", [DOLU, BORU])
@pytest.mark.parametrize("dth", [1.0, 5.0])
def test_K1_from_stock_hacim(stok, dth):
    m = PolarMap.from_stock(stok, dtheta_deg=dth, dz=0.05)
    assert m.volume() == pytest.approx(stok.volume, rel=math.radians(dth) ** 2 / 6)


def test_K1_copy_bagimsiz():
    m = PolarMap.from_stock(DOLU, dtheta_deg=5.0, dz=0.5)
    k = m.copy()
    k.r_out[0, 0] = 1.0
    k.r_in[1, 1] = 3.0
    assert m.r_out[0, 0] == 20.0 and m.r_in[1, 1] == 0.0
    assert k.volume() < m.volume()


def _basamakli_rmap() -> RadialMap:
    """D40 z[−30, 0], hücre 0.1: z > −10'da dış çap 30 (r ∈ [15, 20] kaldırılır), z > −20'de Ø12 delik."""
    g = RadialMap.from_stock(CylinderStock(D=40.0, zmin=-30.0, zmax=0.0), 0.1)
    for i, z in enumerate(g.centers()):
        if z > -10.0:
            g.subtract(i, 15.0, 20.0)
        if z > -20.0:
            g.subtract(i, 0.0, 6.0)
    return g


def test_K1_from_radial_her_teta_ayni():
    g = _basamakli_rmap()
    m = PolarMap.from_radial(g, dtheta_deg=2.0)
    assert m.n_z == g.nz and m.n_theta == 180
    assert m.dz == pytest.approx(g.dz, rel=1e-12)
    assert m.z0 == pytest.approx(g.z0, abs=1e-12)
    np.testing.assert_allclose(m.centers(), g.centers(), rtol=0, atol=1e-9)
    beklenen_dis = np.array([g.intervals(i)[-1][1] for i in range(g.nz)])
    beklenen_ic = np.array([g.intervals(i)[0][0] for i in range(g.nz)])
    np.testing.assert_allclose(m.r_out, np.broadcast_to(beklenen_dis, (180, g.nz)), rtol=0, atol=1e-12)
    np.testing.assert_allclose(m.r_in, np.broadcast_to(beklenen_ic, (180, g.nz)), rtol=0, atol=1e-12)


@pytest.mark.parametrize("dth", [1.0, 3.0])
def test_K1_from_radial_hacim(dth):
    g = _basamakli_rmap()
    m = PolarMap.from_radial(g, dtheta_deg=dth)
    assert m.volume() == pytest.approx(g.volume(), rel=1e-9)
