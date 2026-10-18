"""SPEC 05 K13–K15 — parça z-haritası, çakma, kalan malzeme ve OCCT uçtan uca.

Testler SPEC 05 "Parça z-haritası" ve "Çarpışma ve çakma denetimleri" bölümlerinden yazıldı; cam.sim kodu
okunmadı.

Kaynaklar (SPEC 05):
- z_P: hücre merkezinden geçen düşey doğrunun parçayı kestiği en yüksek Z; üçgenin XY izdüşümündeki merkezde
  barisentrik yükseklik, hücre başına en büyük; kenar üstündeki merkezler 1e-12 toleransla dahil;
  düşey üçgenler katkı vermez; değmeyen −∞.
- Çakma: adımda alçalan hücrede z_k < z_P − gouge_tol → kayıt, depth = z_P − z_k.
- Kalan V = Σ max(z − max(z_P, zmin), 0)·dx·dy; çakma V = Σ max(z_P − z, 0)·dx·dy (z_P > zmin).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import Stock
from cam.sim import ZMap, mesh_zmap, simulate
from tests.cam.simref import G1, flat, path

# ------------------------------------------------------------------ ağ kurucular


def _dortgen(V: list, T: list, a, b, c, d) -> None:
    """a-b-c-d dörtgenini iki üçgen (a, b, c), (a, c, d) olarak ekler."""
    n = len(V)
    V += [a, b, c, d]
    T += [(n, n + 1, n + 2), (n, n + 2, n + 3)]


def kutu_agi(x0, y0, z0, x1, y1, z1) -> tuple[np.ndarray, np.ndarray]:
    """12 üçgenli kutu ağı. Üst yüz köşegeni (x0, y0) → (x1, y1), alt yüz diğer köşegen."""
    V: list = []
    T: list = []
    _dortgen(V, T, (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))  # üst
    _dortgen(V, T, (x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0))  # alt
    _dortgen(V, T, (x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))  # y = y0
    _dortgen(V, T, (x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1))  # y = y1
    _dortgen(V, T, (x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1))  # x = x0
    _dortgen(V, T, (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))  # x = x1
    return np.array(V, dtype=float), np.array(T, dtype=np.int64)


def basamak_agi(x0, x1, x2, y0, y1, z0, z1, z2) -> tuple[np.ndarray, np.ndarray]:
    """XZ'de basamaklı profil Y boyunca çekilmiş blok: x ∈ [x0, x1] üst z2, x ∈ [x1, x2] üst z1, taban z0."""
    V: list = []
    T: list = []
    _dortgen(V, T, (x0, y0, z2), (x1, y0, z2), (x1, y1, z2), (x0, y1, z2))  # yüksek üst
    _dortgen(V, T, (x1, y0, z1), (x2, y0, z1), (x2, y1, z1), (x1, y1, z1))  # alçak üst
    _dortgen(V, T, (x2, y0, z0), (x0, y0, z0), (x0, y1, z0), (x2, y1, z0))  # taban
    _dortgen(V, T, (x1, y0, z1), (x1, y1, z1), (x1, y1, z2), (x1, y0, z2))  # basamak alnı
    _dortgen(V, T, (x0, y1, z0), (x0, y0, z0), (x0, y0, z2), (x0, y1, z2))  # x = x0
    _dortgen(V, T, (x2, y0, z0), (x2, y1, z0), (x2, y1, z1), (x2, y0, z1))  # x = x2
    # uç kapakları (y = y0, y = y1): düşey çokgenler, yelpaze üçgenleme
    for y in (y0, y1):
        P = [(x0, y, z0), (x2, y, z0), (x2, y, z1), (x1, y, z1), (x1, y, z2), (x0, y, z2)]
        n = len(V)
        V += P
        T += [(n, n + k, n + k + 1) for k in range(1, 5)]
    return np.array(V, dtype=float), np.array(T, dtype=np.int64)


# ------------------------------------------------------------------ K13

STOK = Stock(0.0, 0.0, -10.0, 10.0, 10.0, 0.0)  # cell 1 → merkezler k + 0.5


def test_K13_kutu_agi():
    """Kutu [0.5, 6.5]² × [−5, −1]: kenarlar, köşeler ve üst yüz köşegeni hücre merkezlerinden geçer."""
    g = ZMap.from_stock(STOK, 1.0)
    V, T = kutu_agi(0.5, 0.5, -5.0, 6.5, 6.5, -1.0)
    assert len(T) == 12
    zP = np.asarray(mesh_zmap(V, T, g), dtype=float)
    assert zP.shape == (g.ny, g.nx)
    X, Y = g.centers()
    ic = (X >= 0.5) & (X <= 6.5) & (Y >= 0.5) & (Y <= 6.5)  # kenar ve köşe dahil: delik yok
    assert ic.sum() == 49
    np.testing.assert_allclose(zP[ic], -1.0, rtol=0, atol=1e-12)
    assert np.all(np.isneginf(zP[~ic]))


def test_K13_basamakli_blok():
    """Basamak alnı x = 3.5 hücre merkez çizgisinde: orada yüksek üst (en yüksek kesişim) alınır."""
    g = ZMap.from_stock(STOK, 1.0)
    V, T = basamak_agi(1.0, 3.5, 7.2, 2.5, 6.0, -8.0, -4.0, -1.5)
    zP = np.asarray(mesh_zmap(V, T, g), dtype=float)
    X, Y = g.centers()
    y_ic = (Y >= 2.5) & (Y <= 6.0)
    yuksek = y_ic & (X >= 1.0) & (X <= 3.5)
    alcak = y_ic & (X > 3.5) & (X <= 7.2)
    assert yuksek.sum() == 3 * 4 and alcak.sum() == 3 * 4
    np.testing.assert_allclose(zP[yuksek], -1.5, rtol=0, atol=1e-12)
    np.testing.assert_allclose(zP[alcak], -4.0, rtol=0, atol=1e-12)
    assert np.all(np.isneginf(zP[~(yuksek | alcak)]))


def test_K13_egik_ucgen_barisentrik():
    """Eğik tek üçgen: z = düzlem denklemi (barisentrik interpolasyon doğrusal alanı birebir verir)."""
    g = ZMap.from_stock(STOK, 1.0)
    A, B, C = (0.2, 0.3, -6.0), (9.7, 1.1, -2.0), (4.4, 9.6, -3.5)
    V = np.array([A, B, C])
    T = np.array([[0, 1, 2]])
    zP = np.asarray(mesh_zmap(V, T, g), dtype=float)
    X, Y = g.centers()
    n = np.cross(np.subtract(B, A), np.subtract(C, A))
    zplan = A[2] - (n[0] * (X - A[0]) + n[1] * (Y - A[1])) / n[2]

    def yan(P, Q):
        return (Q[0] - P[0]) * (Y - P[1]) - (Q[1] - P[1]) * (X - P[0])

    s1, s2, s3 = yan(A, B), yan(B, C), yan(C, A)
    ic = ((s1 > 1e-9) & (s2 > 1e-9) & (s3 > 1e-9)) | ((s1 < -1e-9) & (s2 < -1e-9) & (s3 < -1e-9))
    dis = ((s1 < -1e-9) | (s2 < -1e-9) | (s3 < -1e-9)) & ((s1 > 1e-9) | (s2 > 1e-9) | (s3 > 1e-9))
    assert ic.sum() > 20
    np.testing.assert_allclose(zP[ic], zplan[ic], rtol=0, atol=1e-12)
    assert np.all(np.isneginf(zP[dis]))


def test_K13_dusey_ucgen_katki_vermez():
    g = ZMap.from_stock(STOK, 1.0)
    V = np.array([(0.5, 0.5, -5.0), (6.5, 6.5, -5.0), (3.5, 3.5, -1.0)])  # x = y düzleminde, düşey
    zP = np.asarray(mesh_zmap(V, np.array([[0, 1, 2]]), g), dtype=float)
    assert np.all(np.isneginf(zP))


# ------------------------------------------------------------------ K14 çakma

C_STOK = Stock(0.0, 0.0, -20.0, 40.0, 30.0, 0.0)


def _blok_zP(g: ZMap, x_ust: float | None = None) -> np.ndarray:
    """Parça üst yüzü z = −3 (x ≤ x_ust olan hücrelerde; None → her yerde); diğer hücreler −∞."""
    zP = np.full((g.ny, g.nx), -3.0)
    if x_ust is not None:
        X, _ = g.centers()
        zP[X > x_ust] = -np.inf
    return zP


def _gecis(z: float):
    """Stok dışında z'ye in, y = 15'te boydan geç, çık. Kesilen hücreler |y − 15| ≤ 3."""
    tool = flat(D=6.0, Lf=10.0)
    return path(tool, (-10.0, 15.0, 5.0), [G1(-10.0, 15.0, z), G1(50.0, 15.0, z), G1(50.0, 15.0, 5.0)])


def test_K14_02mm_cakma():
    g = ZMap.from_stock(C_STOK, 1.0)
    res = simulate([_gecis(-3.2)], C_STOK, cell=1.0, part_z=_blok_zP(g))
    k = [c for c in res.collisions if c.kind == "cakma"]
    assert len(k) == 1
    assert k[0].k == 2 and k[0].op == 0
    assert k[0].depth == pytest.approx(0.2, abs=1e-9)
    assert k[0].at[2] == pytest.approx(-3.2, abs=1e-9)
    assert abs(k[0].at[1] - 15.0) <= 3.0


@pytest.mark.parametrize("z", [-3.0, -3.0005])
def test_K14_teget_ve_tolerans_ici_kayit_yok(z):
    """Tam teğet (z = z_P) veya gouge_tol (1e-3) içinde: kayıt yok."""
    g = ZMap.from_stock(C_STOK, 1.0)
    res = simulate([_gecis(z)], C_STOK, cell=1.0, part_z=_blok_zP(g))
    assert [c for c in res.collisions if c.kind == "cakma"] == []


def test_K14_ilk_cakan_adim():
    """Kayıt hücreyi ilk kez çakan adıma aittir; aynı derinlikte geri geçiş hücreyi alçaltmaz → kayıt yok."""
    tool = flat(D=6.0, Lf=10.0)
    yol = path(tool, (-10.0, 15.0, -3.2), [G1(50.0, 15.0, -3.2), G1(-10.0, 15.0, -3.2)])
    g = ZMap.from_stock(C_STOK, 1.0)
    res = simulate([yol], C_STOK, cell=1.0, part_z=_blok_zP(g))
    k = [c for c in res.collisions if c.kind == "cakma"]
    assert [c.k for c in k] == [1]
    assert k[0].depth == pytest.approx(0.2, abs=1e-9)


def _yuz_alma(z: float):
    """Tüm stoğu z'de yüz alan zigzag (satır aralığı 5 ≤ 2R = 6, x ∈ [−5, 45])."""
    tool = flat(D=6.0, Lf=10.0)
    mv = [G1(-5.0, 0.0, z)]
    for j, y in enumerate(range(0, 31, 5)):
        xa, xb = (-5.0, 45.0) if j % 2 == 0 else (45.0, -5.0)
        if j > 0:
            mv.append(G1(xa, float(y), z))
        mv.append(G1(xb, float(y), z))
    mv.append(G1(mv[-1].end[0], 30.0, 5.0))
    return path(tool, (-5.0, 0.0, 5.0), mv, "yuz")


def test_K14_kalan_ve_cakma_hacmi():
    g = ZMap.from_stock(C_STOK, 1.0)
    alan = 40.0 * 30.0
    # işlenmemiş stok: kalan = (0 − (−3)) · alan, çakma 0
    res0 = simulate([_gecis(5.0)], C_STOK, cell=1.0, part_z=_blok_zP(g))
    assert res0.rest_volume() == pytest.approx(3.0 * alan, rel=1e-9)
    assert res0.gouge_volume() == 0.0
    # parça yalnız x ≤ 20'de: diğer yarıda z_P = −∞ → max(z_P, zmin) = zmin, sütun tümüyle kalan
    res1 = simulate([_gecis(5.0)], C_STOK, cell=1.0, part_z=_blok_zP(g, x_ust=20.0))
    assert res1.rest_volume() == pytest.approx(3.0 * alan / 2 + 20.0 * alan / 2, rel=1e-9)
    # doğru ince işleme: tüm üst z = −3 → kalan 0, çakma 0
    res2 = simulate([_yuz_alma(-3.0)], C_STOK, cell=1.0, part_z=_blok_zP(g))
    assert np.all(res2.zmap.z == -3.0)
    assert res2.rest_volume() == pytest.approx(0.0, abs=1e-9)
    assert res2.gouge_volume() == pytest.approx(0.0, abs=1e-9)
    assert [c for c in res2.collisions if c.kind == "cakma"] == []
    # 0.2 mm fazla: çakma hacmi 0.2 · alan, kalan 0
    res3 = simulate([_yuz_alma(-3.2)], C_STOK, cell=1.0, part_z=_blok_zP(g))
    assert res3.gouge_volume() == pytest.approx(0.2 * alan, rel=1e-9)
    assert res3.rest_volume() == pytest.approx(0.0, abs=1e-9)
    assert all(c.kind == "cakma" for c in res3.collisions) and res3.collisions


def test_K14_parca_yoksa_hacim_hatasi():
    from cam.model import CamError

    res = simulate([_gecis(-3.0)], C_STOK, cell=1.0)
    assert res.part_z is None
    with pytest.raises(CamError):
        res.rest_volume()
    with pytest.raises(CamError):
        res.gouge_volume()


# ------------------------------------------------------------------ K15 OCCT uçtan uca


@pytest.mark.occt
def test_K15_cepli_blok_uctan_uca():
    """SPEC 02 cepli blok + SPEC 03 pocket(): çakma yok, son hacim Part.volume ile P·Δ·H toleransında.

    Cep merkez (30, 20), 30 × 20, derinlik 5, köşe yarıçapı 3 = R (düz takım D = 6). Hücre 0.5'te merkezler
    k + 0.25/0.75: köşe yayı merkezlerine uzaklıklar √(a² + b²)/4 (a, b tek) hiçbir zaman 3 ± 0.02 içinde
    değil → üçgenleme kiriş payında (tol 0.01) hücre merkezi yok, z_P kararlı.
    """
    from cam.ops2d import Cut, pocket
    from cam.profile import Profile, Region
    from cam.sim import part_zmap
    from geometry.features import block
    from geometry.features import pocket as cep

    parca = cep(block(60.0, 40.0, 20.0), 30.0, 20.0, 30.0, 20.0, 5.0, r=3.0)
    stok = Stock(0.0, 0.0, 0.0, 60.0, 40.0, 20.0)
    cell = 0.5
    g = ZMap.from_stock(stok, cell)
    zP = np.asarray(part_zmap(parca, g, tol=0.01), dtype=float)
    assert zP.shape == (g.ny, g.nx)
    tool = flat(D=6.0, Lf=15.0)
    cut = Cut(
        z_top=20.0,
        z_bottom=15.0,
        a_p=5.0,
        feed=600.0,
        plunge_feed=200.0,
        rpm=8000.0,
        z_safe=25.0,
        stepover=3.0,
    )
    yol = pocket(Region(Profile.rectangle(15.0, 10.0, 30.0, 20.0)), tool, cut)
    res = simulate([yol], stok, cell=cell, part_z=zP)
    assert [c for c in res.collisions if c.kind == "cakma"] == []
    P = 2 * (30.0 + 20.0) - (8 - 2 * math.pi) * 3.0
    assert res.zmap.volume() == pytest.approx(parca.volume, abs=P * cell * 5.0)
    assert res.gouge_volume() == pytest.approx(0.0, abs=1e-9)
