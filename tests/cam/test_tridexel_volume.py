"""SPEC 43 K3–K4 — eğik delik ve yan delik hacimleri.

Testler SPEC 43 "Izgara ve ışınlar" ve "Takım katısı" bölümlerinden yazıldı; cam.sim kodu okunmadı.

Kaynaklar:
- K3: eksen boyunca hareket eden düz takımın süpürmesi eksenli bir silindirdir; H kalınlıklı yatay dilimle
  kesişiminin yatay kesiti πR²/cos θ alanlı elips → V = πR²H / cos θ (Cavalieri).
- K4: +X eksenli küresel takım x = xmax yüzünden d derine: silindir πR²(d − R) + yarım küre ⅔πR³.
  X ışını (y, z) için q = |(y, z) − (y_c, z_c)| < R: kalan [xmin, x_c − √(R² − q²)], x_c = xmax − d + R.
- Izgara hatası: yalnız yüzeyi kesen ışınlar hatalı; her aile için |V_i − V| ≤ A·Δ/10 (A boşluğun yan yüzey
  alanı, SPEC'in P·Δ·L'si: P kesit çevresi, L boy; yüzeyi kesen ışınların hataları büyük ölçüde sönümlenir).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import Stock
from cam.sim import simulate5
from tests.cam import tridexref as tr
from tests.cam.simref import ball, flat

# ------------------------------------------------------------------ K3

D_STOK = Stock(0.0, 0.0, 0.0, 60.0, 30.0, 10.0)
H = 10.0
R = 5.0
C = np.array([30.0, 15.0, 5.0])  # delik ekseninin dilim ortasındaki noktası


def _egik_delik(theta: float, cell: float):
    a = np.array(tr.axis_xz(theta))
    tool = flat(D=2 * R, Lf=60.0)
    yol = tr.tilted_path(tool, a, [C + 20.0 * a, C - 20.0 * a])
    return simulate5([yol], D_STOK, cell=cell), a


@pytest.mark.parametrize("theta", [0.0, 20.0, 40.0])
def test_K3_egik_delik_hacmi(theta):
    V = math.pi * R**2 * H / math.cos(math.radians(theta))
    A_yan = 2 * math.pi * R * H / math.cos(math.radians(theta))
    hata = {}
    for cell in (1.0, 0.5, 0.25):
        res, _ = _egik_delik(theta, cell)
        Vx, Vy, Vz = res.tridexel.volumes()
        for Vi in (Vx, Vy, Vz):
            assert D_STOK.volume - Vi == pytest.approx(V, abs=A_yan * cell / 10)
        V_ort = res.tridexel.volume()
        assert V_ort == pytest.approx((Vx + Vy + Vz) / 3, rel=1e-12)
        assert res.removed_volume == pytest.approx(D_STOK.volume - V_ort, rel=1e-9)
        hata[cell] = abs(D_STOK.volume - V_ort - V)
    assert hata[0.25] <= A_yan * 0.25 / 10
    assert hata[0.25] < hata[1.0]


@pytest.mark.parametrize("theta", [20.0, 40.0])
def test_K3_egik_delik_isin_araliklari(theta):
    """Süpürme sonlu silindir (uç yolu ⊕ kesen kısım): ışın aralıkları kapalı formla 1e-6."""
    res, a = _egik_delik(theta, 1.0)
    tool = flat(D=2 * R, Lf=60.0)
    p1 = C - 20.0 * a

    def ref(o, u):
        r = tr.ray_cylinder(o, u, p1[None, :], a, R, 0.0, 40.0 + tool.flute_length)
        return None if r[0][0] > r[1][0] else (float(r[0][0]), float(r[1][0]))

    tr_n = 0
    for aile in ("x", "y", "z"):
        for i, j, o, u, (lo, hi) in tr.rays(D_STOK, 1.0, aile):
            r = ref(np.array(o), np.array(u))
            if r is None or r[1] - r[0] < 1e-3 or r[1] <= lo or r[0] >= hi:
                continue
            beklenen = tr.fark([(lo, hi)], *r)
            got = res.tridexel.intervals(aile, i, j)
            assert len(got) == len(beklenen), (aile, i, j)
            if beklenen:
                np.testing.assert_allclose(np.array(got, dtype=float), np.array(beklenen), rtol=0, atol=1e-6)
            tr_n += 1
    assert tr_n > 50


# ------------------------------------------------------------------ K4

Y_STOK = Stock(0.0, 0.0, 0.0, 40.0, 30.0, 20.0)
YC, ZC = 15.3, 10.4
DERIN = 12.0


def _yan_delik(cell: float):
    tool = ball(D=2 * R, Lf=30.0)
    dis = (50.0, YC, ZC)
    dip = (Y_STOK.xmax - DERIN, YC, ZC)
    yol = tr.tilted_path(tool, (1.0, 0.0, 0.0), [dis, dip, dis])
    return simulate5([yol], Y_STOK, cell=cell)


@pytest.mark.parametrize("cell", [1.0, 0.5])
def test_K4_yan_delik_hacmi(cell):
    res = _yan_delik(cell)
    V = math.pi * R**2 * (DERIN - R) + 2 / 3 * math.pi * R**3
    A_yan = 2 * math.pi * R * (DERIN - R) + 2 * math.pi * R**2
    for Vi in res.tridexel.volumes():
        assert Y_STOK.volume - Vi == pytest.approx(V, abs=A_yan * cell / 10)
    assert Y_STOK.volume - res.tridexel.volume() == pytest.approx(V, abs=A_yan * cell / 10)


def test_K4_z_ust_yuzey_degismiyor_x_araliklari_kesin():
    res = _yan_delik(1.0)
    td = res.tridexel
    # Z ailesi: üst yüzey (en üst aralığın ucu) her ışında zmax → z-haritası bu boşluğu göremez
    bolunen = 0
    for i, j, *_ in tr.rays(Y_STOK, 1.0, "z"):
        iv = td.intervals("z", i, j)
        assert iv[-1][1] == pytest.approx(Y_STOK.zmax, abs=1e-12)
        bolunen += len(iv) == 2
    assert bolunen > 20  # deliğin altından ve üstünden malzeme: iki aralık
    # X ailesi: kesin aralıklar
    xc = Y_STOK.xmax - DERIN + R
    ic = 0
    for j, k, o, _u, (lo, hi) in tr.rays(Y_STOK, 1.0, "x"):
        q = math.hypot(o[1] - YC, o[2] - ZC)
        iv = np.array(td.intervals("x", j, k), dtype=float)
        if q < R - 1e-6:
            np.testing.assert_allclose(iv, [(lo, xc - math.sqrt(R * R - q * q))], rtol=0, atol=1e-6)
            ic += 1
        elif q > R + 1e-6:
            np.testing.assert_allclose(iv, [(lo, hi)], rtol=0, atol=1e-12)
    assert ic > 50
