"""SPEC 05 K18–K22 — tek yönlü (Z) dexel, iki model çapraz kontrolü, kesici boyu, iki bağlama, `initial`.

Testler SPEC 05 "Tek yönlü dexel (Z yönü)" ve "Arayüz" bölümlerinden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 05):
- Aralık farkı: [lo, u] − [a, b] = [lo, min(u, a)] ∪ [max(lo, b), u], boyu > 0 olan parçalar kalır.
- V = Σ Σ (u − lo)·dx·dy; top = max u (aralık yoksa zmin).
- Ters çevirme: hücre j → ny − 1 − j, (lo, u) → (s − u, s − lo), s = zmin + zmax.
- Kaldırma aralığı [e(q), e_üst(q)], e_üst = L_f + max{ z(t) : d(t) ≤ R }; kesicinin üstünde kalan
  malzeme kaldırılmaz.
- Kutu stokta gövde çarpışması olmayan programda dexel her hücrede [zmin, z] tutar, top z-haritasıyla birebir.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, Stock
from cam.sim import DexelMap, ZMap, simulate, sweep_top
from tests.cam import simref as ref
from tests.cam.simref import G1, RANDOM_STOCK, ball, bull, flat, path, random_program

# ------------------------------------------------------------------ K18 aralıklar

D_STOK = Stock(0.0, 0.0, -10.0, 4.0, 3.0, 0.0)  # cell 1 → 4 × 3 hücre


def _aralik_kontrol(iv) -> None:
    for (_, u1), (l2, _) in zip(iv, iv[1:], strict=False):
        assert u1 < l2
    for lo, u in iv:
        assert u - lo > 0


def _fark(iv, a, b):
    """Referans aralık farkı (SPEC 05 formülü)."""
    out = []
    for lo, u in iv:
        if min(u, a) - lo > 0:
            out.append((lo, min(u, a)))
        if u - max(lo, b) > 0:
            out.append((max(lo, b), u))
    return out


def _tum(m: DexelMap):
    return {
        (i, j): [tuple(map(float, p)) for p in m.intervals(i, j)] for i in range(m.nx) for j in range(m.ny)
    }


def test_K18_baslangic():
    m = DexelMap.from_stock(D_STOK, 1.0)
    assert (m.nx, m.ny, m.dx, m.dy, m.x0, m.y0, m.zmin, m.zmax) == (4, 3, 1.0, 1.0, 0.0, 0.0, -10.0, 0.0)
    for iv in _tum(m).values():
        assert iv == [(-10.0, 0.0)]
    assert m.volume() == pytest.approx(D_STOK.volume, rel=1e-12)
    np.testing.assert_array_equal(m.top(), np.zeros((3, 4)))
    X, Y = m.centers()
    assert X.shape == (3, 4) and X[0, 2] == 2.5 and Y[1, 0] == 1.5


def test_K18_subtract_durumlari():
    m = DexelMap.from_stock(D_STOK, 1.0)
    m.subtract(1, 1, -6.0, -4.0)  # ortadan bölme
    assert m.intervals(1, 1) == [(-10.0, -6.0), (-4.0, 0.0)]
    m.subtract(0, 0, -12.0, -7.0)  # alttan kırpma
    assert m.intervals(0, 0) == [(-7.0, 0.0)]
    m.subtract(2, 0, -3.0, 1.0)  # üstten kırpma
    assert m.intervals(2, 0) == [(-10.0, -3.0)]
    m.subtract(3, 0, -11.0, 1.0)  # tamamen silme
    assert m.intervals(3, 0) == []
    m.subtract(0, 1, 1.0, 2.0)  # değmeyen
    assert m.intervals(0, 1) == [(-10.0, 0.0)]
    m.subtract(1, 1, -6.0, -5.0)  # a = u: sınıra değen, değişmez
    assert m.intervals(1, 1) == [(-10.0, -6.0), (-4.0, 0.0)]
    m.subtract(1, 1, -5.0, -4.0)  # b = lo
    assert m.intervals(1, 1) == [(-10.0, -6.0), (-4.0, 0.0)]
    m.subtract(1, 1, -8.0, -2.0)  # iki aralığı birden kırpar
    assert m.intervals(1, 1) == [(-10.0, -8.0), (-2.0, 0.0)]
    m.subtract(1, 2, -6.5, -4.25)
    m.subtract(1, 2, -9.0, -8.5)
    assert m.intervals(1, 2) == [(-10.0, -9.0), (-8.5, -6.5), (-4.25, 0.0)]
    # boşaltılan hücrede top = zmin
    top = m.top()
    assert top[0, 3] == -10.0 and top[0, 2] == -3.0 and top[2, 1] == 0.0
    beklenen = sum(u - lo for iv in _tum(m).values() for lo, u in iv)
    assert m.volume() == pytest.approx(beklenen, rel=1e-12)
    for iv in _tum(m).values():
        _aralik_kontrol(iv)


@pytest.mark.parametrize("a, b", [(-3.0, -3.0), (-2.0, -5.0)])
def test_K18_subtract_gecersiz(a, b):
    m = DexelMap.from_stock(D_STOK, 1.0)
    with pytest.raises(CamError):
        m.subtract(0, 0, a, b)


def test_K18_rastgele_subtract_referansla():
    m = DexelMap.from_stock(D_STOK, 1.0)
    rng = np.random.default_rng(7)
    iv = [(-10.0, 0.0)]
    for _ in range(300):
        a = float(rng.uniform(-11.0, 1.0))
        b = a + float(rng.uniform(1e-3, 0.4))
        m.subtract(2, 1, a, b)
        iv = _fark(iv, a, b)
        sonuc = m.intervals(2, 1)
        assert len(sonuc) == len(iv)
        np.testing.assert_allclose(
            np.array(sonuc).reshape(-1, 2), np.array(iv).reshape(-1, 2), rtol=0, atol=1e-12
        )
        _aralik_kontrol(sonuc)
    assert m.volume() == pytest.approx(11 * 10.0 + sum(u - lo for lo, u in iv), rel=1e-12)
    assert m.top()[1, 2] == (iv[-1][1] if iv else -10.0)


def test_K18_flipped():
    m = DexelMap.from_stock(D_STOK, 1.0)
    m.subtract(1, 0, -6.5, -4.25)
    m.subtract(3, 2, -2.0, 1.0)
    m.subtract(0, 1, -11.0, -7.5)
    f = m.flipped()
    s = m.zmin + m.zmax
    assert (f.nx, f.ny, f.dx, f.dy, f.x0, f.y0, f.zmin, f.zmax) == (
        m.nx,
        m.ny,
        m.dx,
        m.dy,
        m.x0,
        m.y0,
        m.zmin,
        m.zmax,
    )
    for i in range(m.nx):
        for j in range(m.ny):
            beklenen = sorted((s - u, s - lo) for lo, u in m.intervals(i, j))
            assert f.intervals(i, m.ny - 1 - j) == beklenen
    assert f.volume() == pytest.approx(m.volume(), rel=1e-12)
    ff = f.flipped()
    assert _tum(ff) == _tum(m)
    # m değişmedi
    assert m.intervals(1, 0) == [(-10.0, -6.5), (-4.25, 0.0)]


def test_K18_copy_bagimsiz():
    m = DexelMap.from_stock(D_STOK, 1.0)
    c = m.copy()
    c.subtract(0, 0, -5.0, 1.0)
    assert m.intervals(0, 0) == [(-10.0, 0.0)]
    assert c.intervals(0, 0) == [(-10.0, -5.0)]


@pytest.mark.parametrize("cell", [0.0, -1.0, math.nan, math.inf])
def test_K18_from_stock_hatalari(cell):
    with pytest.raises(CamError):
        DexelMap.from_stock(D_STOK, cell)


def test_K18_max_cells():
    with pytest.raises(CamError):
        DexelMap.from_stock(D_STOK, 1.0, max_cells=11)
    DexelMap.from_stock(D_STOK, 1.0, max_cells=12)


# ------------------------------------------------------------------ K19 çapraz kontrol


@pytest.mark.parametrize("takim", ["duz", "kuresel", "koseli"])
def test_K19_iki_model_ayni(takim):
    tool = {
        "duz": flat(D=6.0, Lf=30.0),
        "kuresel": ball(D=6.0, Lf=30.0),
        "koseli": bull(D=6.0, rc=1.5, Lf=30.0),
    }[takim]
    prog = random_program(tool, n=50)
    rz = simulate([prog], RANDOM_STOCK, cell=1.0, model="zmap")
    rd = simulate([prog], RANDOM_STOCK, cell=1.0, model="dexel")
    assert rz.dexel is None
    assert isinstance(rd.dexel, DexelMap)
    d = rd.dexel
    z = rz.zmap.z
    zmin = RANDOM_STOCK.zmin
    bos = 0
    for j in range(d.ny):
        for i in range(d.nx):
            iv = [tuple(map(float, p)) for p in d.intervals(i, j)]
            if z[j, i] > zmin:
                assert iv == [(zmin, float(z[j, i]))], (i, j)
            else:
                assert iv == [], (i, j)
                bos += 1
    assert bos > 0  # program stok tabanını (−6) aşıp −8'e iniyor: malzemesiz hücreler var
    np.testing.assert_array_equal(d.top(), z)
    np.testing.assert_array_equal(rd.zmap.z, z)
    assert d.volume() == pytest.approx(rz.zmap.volume(), rel=1e-12)
    assert rd.removed_volume == pytest.approx(rz.removed_volume, rel=1e-12)
    for ad in ("event_cell", "event_k", "event_z", "offsets"):
        np.testing.assert_array_equal(getattr(rd, ad), getattr(rz, ad))
    assert [(c.kind, c.k, c.op) for c in rd.collisions] == [(c.kind, c.k, c.op) for c in rz.collisions]
    for a, b in zip(rd.collisions, rz.collisions, strict=True):
        assert a.depth == pytest.approx(b.depth, abs=1e-12)
        np.testing.assert_allclose(a.at, b.at, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(rd.cumulative_time(), rz.cumulative_time())
    assert rd.total_time == rz.total_time
    for a, b in zip(rd.steps, rz.steps, strict=True):
        assert a.removed == pytest.approx(b.removed, rel=1e-9, abs=1e-9)


# ------------------------------------------------------------------ K20 kesici boyu

K_STOK = Stock(0.0, 0.0, -20.0, 40.0, 20.0, 0.0)


def _kanal():
    tool = flat(D=6.0, Lf=10.0)
    return path(
        tool, (-10.0, 10.0, 5.0), [G1(-10.0, 10.0, -15.0), G1(50.0, 10.0, -15.0), G1(50.0, 10.0, 5.0)]
    )


def test_K20_kesici_ustunde_malzeme_kalir():
    rd = simulate([_kanal()], K_STOK, cell=1.0, model="dexel")
    rz = simulate([_kanal()], K_STOK, cell=1.0, model="zmap")
    d = rd.dexel
    X, Y = d.centers()
    kanal = np.abs(Y - 10.0) < 3.0
    n_kanal = int(kanal.sum())
    assert n_kanal == 6 * 40
    for j in range(d.ny):
        for i in range(d.nx):
            iv = d.intervals(i, j)
            if kanal[j, i]:
                assert len(iv) == 2
                np.testing.assert_allclose(iv, [(-20.0, -15.0), (-5.0, 0.0)], rtol=0, atol=1e-12)
            else:
                assert [tuple(map(float, p)) for p in iv] == [(-20.0, 0.0)]
    for r in (rd, rz):
        k = [c for c in r.collisions if c.kind == "sap_carpma"]
        assert len(k) == 1 and k[0].k == 2
        assert k[0].depth == pytest.approx(5.0, abs=1e-9)
    assert d.volume() - rz.zmap.volume() == pytest.approx(5.0 * n_kanal * d.dx * d.dy, rel=1e-12)
    # üst yüzey dexel'de değişmedi (kanal kapalı), z-haritasında −15
    np.testing.assert_array_equal(d.top(), np.zeros((d.ny, d.nx)))
    assert np.all(rz.zmap.z[kanal] == -15.0)


EGIK = {
    "rampa": ((8.2, 6.3, -1.0), (30.9, 14.4, -4.5)),
    "yukari": ((30.9, 14.4, -6.0), (8.2, 9.3, -2.0)),
    "dalma": ((17.3, 12.6, 2.0), (17.3, 12.6, -7.5)),
    "uzay": ((3.1, 18.2, 1.0), (21.4, 3.8, -9.0)),
}


@pytest.mark.parametrize("ad", list(EGIK))
def test_K20_sweep_top_kapali_form(ad):
    p0, p1 = EGIK[ad]
    tool = flat(D=6.0, Lf=10.0)
    g = ZMap.from_stock(K_STOK, 0.5)
    X, Y = g.centers()
    e = np.asarray(sweep_top(tool, p0, p1, X, Y), dtype=float)
    beklenen = ref.flat_top_ref(X, Y, p0, p1, 3.0, 10.0)
    m = np.abs(ref.seg_dist(X, Y, p0, p1) - 3.0) > 1e-3
    np.testing.assert_array_equal(np.isfinite(e[m]), np.isfinite(beklenen[m]))
    son = m & np.isfinite(beklenen)
    assert son.sum() > 20
    np.testing.assert_allclose(e[son], beklenen[son], rtol=0, atol=1e-12)
    assert np.all(np.isneginf(e[m & ~np.isfinite(beklenen)]))


@pytest.mark.parametrize("takim", ["kuresel", "koseli"])
def test_K20_sweep_top_egri_uc(takim):
    """e_üst yalnız d(t) ≤ R kümesine ve L_f'ye bağlıdır (profil h'den bağımsız)."""
    tool = {"kuresel": ball(D=6.0, Lf=12.0), "koseli": bull(D=6.0, rc=1.5, Lf=12.0)}[takim]
    p0, p1 = EGIK["rampa"]
    g = ZMap.from_stock(K_STOK, 0.5)
    X, Y = g.centers()
    e = np.asarray(sweep_top(tool, p0, p1, X, Y), dtype=float)
    beklenen = ref.flat_top_ref(X, Y, p0, p1, 3.0, 12.0)
    son = (np.abs(ref.seg_dist(X, Y, p0, p1) - 3.0) > 1e-3) & np.isfinite(beklenen)
    np.testing.assert_allclose(e[son], beklenen[son], rtol=0, atol=1e-12)


# ------------------------------------------------------------------ K21 iki bağlama

B_STOK = Stock(0.0, 0.0, -20.0, 40.0, 30.0, 0.0)
CEP1 = (5.3, 5.2, 20.4, 14.7, 6.0)  # x0, y0, a, b, H (üstten, ilk bağlama)
CEP2 = (15.1, 8.3, 20.2, 13.6, 8.0)  # çevrilmiş koordinatlarda


def _cep(c, tool):
    x0, y0, a, b, H = c
    return ref.rect_pocket(tool, x0, y0, a, b, -H)


def test_K21_iki_baglama():
    tool = flat(D=6.0, Lf=30.0)
    R = 3.0
    r1 = simulate([_cep(CEP1, tool)], B_STOK, cell=0.5, model="dexel")
    ilk = r1.dexel.flipped()
    r2 = simulate([_cep(CEP2, tool)], B_STOK, cell=0.5, model="dexel", initial=ilk)
    d = r2.dexel
    X, Y = d.centers()  # çevrilmiş çerçeve; ızgara simetrik
    # ilk cep çevrilmiş çerçevede: y_orijinal = ymin + ymax − y
    s1 = ref.in_rounded_rect(X, B_STOK.ymin + B_STOK.ymax - Y, *CEP1[:4], R)
    s2 = ref.in_rounded_rect(X, Y, *CEP2[:4], R)
    net = (np.abs(s1) > 1e-9) & (np.abs(s2) > 1e-9)
    ikisi = net & (s1 < 0) & (s2 < 0)
    yalniz1 = net & (s1 < 0) & (s2 > 0)
    yalniz2 = net & (s1 > 0) & (s2 < 0)
    assert ikisi.sum() > 100 and yalniz1.sum() > 100 and yalniz2.sum() > 100
    kalinlik = (B_STOK.zmax - B_STOK.zmin) - CEP1[4] - CEP2[4]
    for j, i in np.argwhere(ikisi):
        iv = d.intervals(i, j)
        assert len(iv) == 1
        assert iv[0][1] - iv[0][0] == pytest.approx(kalinlik, abs=1e-12)
        np.testing.assert_allclose(iv[0], (-20.0 + CEP1[4], -CEP2[4]), rtol=0, atol=1e-12)
    for j, i in np.argwhere(yalniz1):
        np.testing.assert_allclose(d.intervals(i, j), [(-20.0 + CEP1[4], 0.0)], rtol=0, atol=1e-12)
    for j, i in np.argwhere(yalniz2):
        np.testing.assert_allclose(d.intervals(i, j), [(-20.0, -CEP2[4])], rtol=0, atol=1e-12)
    # hacim: stok − V1 − V2 (ızgara toleransı K7'deki gibi)
    V = [(c[2] * c[3] - (4 - math.pi) * R**2) * c[4] for c in (CEP1, CEP2)]
    P = [2 * (c[2] + c[3]) - (8 - 2 * math.pi) * R for c in (CEP1, CEP2)]
    tol = (P[0] * CEP1[4] + P[1] * CEP2[4]) * 0.5
    assert d.volume() == pytest.approx(B_STOK.volume - V[0] - V[1], abs=tol)
    # z-haritası (top) bu sonucu temsil edemez: alttan açılmış ilk cep üst yüzeyde görünmez
    top = d.top()
    assert np.all(top[yalniz1] == 0.0)
    np.testing.assert_allclose(top[ikisi | yalniz2], -CEP2[4], rtol=0, atol=1e-12)
    np.testing.assert_array_equal(r2.zmap.z, top)
    np.testing.assert_array_equal(r2.zmap_at(0), ilk.top())


# ------------------------------------------------------------------ K22 initial

I_STOK = Stock(0.0, 0.0, -10.0, 30.0, 20.0, 0.0)


def _iki_parca():
    tool = flat(D=6.0, Lf=30.0)
    a = path(tool, (-5.0, 5.0, 3.0), [G1(-5.0, 5.0, -2.0), G1(35.0, 7.0, -3.0), G1(20.0, 18.0, -1.0)], "a")
    b = path(tool, (20.0, 18.0, -1.0), [G1(5.0, 2.0, -4.0), G1(28.0, 12.0, -2.5), G1(28.0, 12.0, 3.0)], "b")
    return a, b


def test_K22_initial_zmap_ikiye_bolunmus_program():
    a, b = _iki_parca()
    tek = simulate([a, b], I_STOK, cell=0.5)
    r1 = simulate([a], I_STOK, cell=0.5)
    ilk = r1.zmap
    z_once = ilk.z.copy()
    r2 = simulate([b], I_STOK, cell=0.5, initial=ilk)
    np.testing.assert_array_equal(r2.zmap.z, tek.zmap.z)
    np.testing.assert_array_equal(ilk.z, z_once)  # initial kopyalanır, değişmez
    np.testing.assert_array_equal(r2.zmap_at(0), z_once)
    assert r2.removed_volume == pytest.approx(ilk.volume() - tek.zmap.volume(), rel=1e-9)


def test_K22_initial_dexel():
    a, b = _iki_parca()
    tek = simulate([a, b], I_STOK, cell=0.5, model="dexel")
    r1 = simulate([a], I_STOK, cell=0.5, model="dexel")
    once = _tum(r1.dexel)
    r2 = simulate([b], I_STOK, cell=0.5, model="dexel", initial=r1.dexel)
    assert _tum(r2.dexel) == _tum(tek.dexel)
    assert _tum(r1.dexel) == once


def test_K22_tur_ve_izgara_uyusmazligi():
    a, b = _iki_parca()
    z = ZMap.from_stock(I_STOK, 0.5)
    dx = DexelMap.from_stock(I_STOK, 0.5)
    with pytest.raises(CamError):
        simulate([b], I_STOK, cell=0.5, model="zmap", initial=dx)
    with pytest.raises(CamError):
        simulate([b], I_STOK, cell=0.5, model="dexel", initial=z)
    with pytest.raises(CamError):
        simulate([b], I_STOK, cell=1.0, initial=z)  # farklı hücre
    with pytest.raises(CamError):
        simulate([b], I_STOK, cell=0.5, initial=ZMap.from_stock(Stock(0.0, 0.0, -10.0, 30.0, 20.0, 1.0), 0.5))
    with pytest.raises(CamError):
        simulate([b], I_STOK, cell=0.5, initial=ZMap.from_stock(Stock(1.0, 0.0, -10.0, 31.0, 20.0, 0.0), 0.5))
    with pytest.raises(CamError):
        simulate([b], I_STOK, cell=0.5, model="dexel", initial=DexelMap.from_stock(I_STOK, 1.0))


@pytest.mark.parametrize("model", ["voksel", "", "ZMAP"])
def test_K22_bilinmeyen_model(model):
    a, _ = _iki_parca()
    with pytest.raises(CamError):
        simulate([a], I_STOK, model=model)
