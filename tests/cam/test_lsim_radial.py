"""SPEC 22 K1, K2 — radyal dexel ızgarası ve aralık işlemleri.

Testler SPEC 22 "Radyal dexel" bölümünden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 22):
- n_s = ⌈(zmax − zmin)/Δ⌉, dz = (zmax − zmin)/n_s; bağlama elemanları için n_alt = ⌈(zmin − zf_min)/dz⌉⁺,
  n_üst = ⌈(zf_max − zmax)/dz⌉⁺, z0 = zmin − n_alt·dz, nz = n_alt + n_s + n_üst, z_i = z0 + (i + ½)·dz.
- Başlangıç: stok hücrelerinde [d/2, D/2], diğerleri boş; r_max = max(D/2, bağlama D/2).
- V = Σ π·(u² − l²)·dz (Pappus); başlangıçta CylinderStock.volume (rel 1e-12).
- [l, u] − [a, b] → [l, min(u, a)], [max(l, b), u] (boyu > 0 ise); outer = max u, inner = min l (boşsa 0).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, CylinderStock
from cam.sim import RadialMap
from tests.cam.lsimref import iv_is_valid, iv_subtract

STOK = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0)
BORU = CylinderStock(D=40.0, zmin=-30.0, zmax=5.0, d=12.0)


def _bos(cell: float = 0.5) -> RadialMap:
    return RadialMap.empty_like(RadialMap.from_stock(STOK, cell))


# ------------------------------------------------------------------ K1 ızgara


def test_K1_izgara_tam_bolunur():
    """L = 50, Δ = 0.7 → n_s = ⌈71.43⌉ = 72, dz = 50/72; stok sınırları hücre sınırı."""
    g = RadialMap.from_stock(STOK, 0.7)
    assert g.nz == 72
    assert g.dz == pytest.approx(50.0 / 72, rel=1e-12)
    assert g.z0 == pytest.approx(-50.0, abs=1e-12)
    assert g.z0 + g.nz * g.dz == pytest.approx(0.0, abs=1e-9)
    assert g.r_max == pytest.approx(20.0)
    np.testing.assert_allclose(g.centers(), -50.0 + (np.arange(72) + 0.5) * 50.0 / 72, rtol=0, atol=1e-12)


def test_K1_baslangic_dolu_ve_boru():
    g = RadialMap.from_stock(STOK, 0.5)
    assert g.nz == 100
    for i in range(g.nz):
        assert g.intervals(i) == [pytest.approx((0.0, 20.0))]
    b = RadialMap.from_stock(BORU, 0.5)
    assert b.nz == 70
    for i in range(b.nz):
        assert b.intervals(i) == [pytest.approx((6.0, 20.0))]
    np.testing.assert_allclose(b.outer(), 20.0)
    np.testing.assert_allclose(b.inner(), 6.0)


@pytest.mark.parametrize("stok", [STOK, BORU], ids=["dolu", "boru"])
@pytest.mark.parametrize("cell", [1.0, 0.7, 0.3])
def test_K1_baslangic_hacmi(stok, cell):
    g = RadialMap.from_stock(stok, cell)
    assert g.volume() == pytest.approx(stok.volume, rel=1e-12)


def test_K1_baglama_alttan_tasar():
    """Ayna çenesi z ∈ [−70, −40]: n_alt = ⌈20/(50/72)⌉ = ⌈28.8⌉ = 29, n_üst = 0; r_max = 30."""
    cene = CylinderStock(D=60.0, zmin=-70.0, zmax=-40.0, d=40.0)
    g = RadialMap.from_stock(STOK, 0.7, fixtures=[cene])
    dz = 50.0 / 72
    assert g.dz == pytest.approx(dz, rel=1e-12)
    assert g.nz == 29 + 72
    assert g.z0 == pytest.approx(-50.0 - 29 * dz, abs=1e-9)
    assert g.r_max == pytest.approx(30.0)
    for i in range(29):
        assert g.intervals(i) == []  # bağlama elemanı malzeme değildir
    for i in range(29, 29 + 72):
        assert g.intervals(i) == [pytest.approx((0.0, 20.0))]
    assert g.volume() == pytest.approx(STOK.volume, rel=1e-12)


def test_K1_baglama_iki_taraftan():
    """Alt: z ∈ [−56.2, −40] → n_alt = ⌈6.2/0.5⌉ = 13; üst (punta): zmax = 7.3 → n_üst = ⌈14.6⌉ = 15."""
    alt = CylinderStock(D=60.0, zmin=-56.2, zmax=-40.0, d=40.0)
    ust = CylinderStock(D=10.0, zmin=-2.0, zmax=7.3)
    g = RadialMap.from_stock(STOK, 0.5, fixtures=[alt, ust])
    assert g.nz == 13 + 100 + 15
    assert g.z0 == pytest.approx(-50.0 - 13 * 0.5, abs=1e-12)
    assert g.r_max == pytest.approx(30.0)
    assert all(g.intervals(i) == [] for i in range(13))
    assert all(g.intervals(i) == [] for i in range(113, 128))
    assert g.volume() == pytest.approx(STOK.volume, rel=1e-12)


def test_K1_baglama_stok_icinde_ek_hucre_yok():
    ic = CylinderStock(D=50.0, zmin=-45.0, zmax=-30.0, d=40.0)
    g = RadialMap.from_stock(STOK, 0.5, fixtures=[ic])
    assert g.nz == 100
    assert g.z0 == pytest.approx(-50.0)
    assert g.r_max == pytest.approx(25.0)


@pytest.mark.parametrize("cell", [0.0, -1.0, math.inf, math.nan])
def test_K1_hatali_hucre(cell):
    with pytest.raises(CamError):
        RadialMap.from_stock(STOK, cell)


def test_K1_max_cells():
    assert RadialMap.from_stock(STOK, 0.5, max_cells=100).nz == 100
    with pytest.raises(CamError):
        RadialMap.from_stock(STOK, 0.5, max_cells=99)


def test_K1_empty_like_ve_copy():
    g = RadialMap.from_stock(STOK, 0.5)
    e = RadialMap.empty_like(g)
    assert (e.z0, e.dz, e.nz) == (g.z0, g.dz, g.nz)
    assert all(e.intervals(i) == [] for i in range(e.nz))
    assert e.volume() == 0.0
    c = g.copy()
    c.subtract(3, 5.0, 10.0)
    assert g.intervals(3) == [pytest.approx((0.0, 20.0))]
    assert c.intervals(3) == [pytest.approx((0.0, 5.0)), pytest.approx((10.0, 20.0))]


# ------------------------------------------------------------------ K2 aralıklar


@pytest.mark.parametrize(
    ("a", "b", "beklenen"),
    [
        (12.0, 15.0, [(10.0, 12.0), (15.0, 20.0)]),  # ortadan bölme
        (5.0, 12.0, [(12.0, 20.0)]),  # iç kırpma
        (15.0, 25.0, [(10.0, 15.0)]),  # dış kırpma
        (5.0, 25.0, []),  # tamamen silme
        (10.0, 20.0, []),  # tam aynı aralık
        (1.0, 3.0, [(10.0, 20.0)]),  # değmeyen (içte)
        (22.0, 30.0, [(10.0, 20.0)]),  # değmeyen (dışta)
        (0.0, 10.0, [(10.0, 20.0)]),  # alt sınıra değen
        (20.0, 30.0, [(10.0, 20.0)]),  # üst sınıra değen
    ],
)
def test_K2_subtract(a, b, beklenen):
    g = _bos()
    g.add(7, 10.0, 20.0)
    g.subtract(7, a, b)
    assert g.intervals(7) == [pytest.approx(p) for p in beklenen]
    assert iv_is_valid(g.intervals(7))
    assert g.intervals(6) == [] and g.intervals(8) == []


def test_K2_subtract_coklu_aralik():
    g = _bos()
    for lo, hi in ((1.0, 3.0), (5.0, 8.0), (10.0, 14.0)):
        g.add(0, lo, hi)
    g.subtract(0, 2.0, 11.0)
    assert g.intervals(0) == [pytest.approx((1.0, 2.0)), pytest.approx((11.0, 14.0))]


@pytest.mark.parametrize(("a", "b"), [(5.0, 5.0), (6.0, 5.0)])
def test_K2_subtract_hatali(a, b):
    g = RadialMap.from_stock(STOK, 0.5)
    with pytest.raises(CamError):
        g.subtract(0, a, b)


def test_K2_add_birlestirme():
    g = _bos()
    g.add(4, 1.0, 2.0)
    g.add(4, 5.0, 6.0)
    assert g.intervals(4) == [pytest.approx((1.0, 2.0)), pytest.approx((5.0, 6.0))]
    g.add(4, 1.5, 3.0)  # çakışan
    assert g.intervals(4) == [pytest.approx((1.0, 3.0)), pytest.approx((5.0, 6.0))]
    g.add(4, 3.0, 4.0)  # değen
    assert g.intervals(4) == [pytest.approx((1.0, 4.0)), pytest.approx((5.0, 6.0))]
    g.add(4, 0.5, 7.0)  # hepsini örten
    assert g.intervals(4) == [pytest.approx((0.5, 7.0))]


def test_K2_outer_inner_volume():
    g = _bos()
    g.add(0, 2.0, 5.0)
    g.add(0, 7.0, 9.0)
    g.add(3, 0.0, 4.0)
    o, i = g.outer(), g.inner()
    assert o.shape == (g.nz,) and i.shape == (g.nz,)
    assert o[0] == pytest.approx(9.0) and i[0] == pytest.approx(2.0)
    assert o[3] == pytest.approx(4.0) and i[3] == 0.0
    assert o[1] == 0.0 and i[1] == 0.0
    V = math.pi * 0.5 * ((25 - 4) + (81 - 49) + 16)
    assert g.volume() == pytest.approx(V, rel=1e-12)


def test_K2_rastgele_dizi_referansla():
    """Sabit tohumlu 300 rastgele ekle / çıkar işlemi; bağımsız aralık referansıyla birebir."""
    rng = np.random.default_rng(22)
    g = _bos()
    ref: list[list[tuple[float, float]]] = [[] for _ in range(g.nz)]
    for _ in range(300):
        i = int(rng.integers(0, 4))
        a, b = sorted(rng.uniform(0.0, 20.0, 2))
        if b - a < 1e-9:
            continue
        if rng.random() < 0.5:
            g.add(i, a, b)
            # referans birleşim: ekle ve sırala-birleştir
            ivs = sorted([*ref[i], (a, b)])
            merged: list[tuple[float, float]] = []
            for lo, hi in ivs:
                if merged and lo <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
                else:
                    merged.append((lo, hi))
            ref[i] = merged
        else:
            g.subtract(i, a, b)
            ref[i] = iv_subtract(ref[i], a, b)
        assert iv_is_valid(g.intervals(i))
        assert g.intervals(i) == [pytest.approx(p, abs=1e-12) for p in ref[i]]
    V = sum(math.pi * (u * u - lo * lo) * g.dz for iv in ref for lo, u in iv)
    assert g.volume() == pytest.approx(V, rel=1e-12, abs=1e-12)
