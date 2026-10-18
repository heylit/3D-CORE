"""SPEC 39 K10–K16 — işlenmiş parça ikizi: kolon / yüzey ağı, ikili STL, nokta–üçgen uzaklığı, sapma haritası.

Testler SPEC 39 "İşlenmiş parça ağı (ikiz)", "Sapma haritası" ve "Arayüz → cam/sim/ikiz.py" bölümlerinden
yazıldı; cam/sim/ikiz.py gövdesi okunmadı. Beklenen değerler aşağıdaki bağımsız referanslardan gelir
(yalnız numpy; SPEC 05 durumları yalnız genel arayüzleriyle kullanılır).

Kaynaklar:
- Kolon katısı (SPEC 39): hücre (i, j) aralığı [l, u] → [x_i ± dx/2] × [y_j ± dy/2] × [l, u] prizması;
  z-haritasında aralık [zmin, z], z = zmin → prizma yok. Bir nokta katının içinde ⇔ hücresinin bir aralığı
  z'yi içeriyor (düşey ışın paritesi: ışının kestiği aralık sınırı sayısı tekse içeride).
- Kapalılık (SPEC 39): her yönlü kenar (a, b) sayısı = ters (b, a) sayısı.
- Hacim, diverjans teoremi: V = Σ v₀ · (v₁ × v₂) / 6.
- Yüzey ağı (SPEC 39): düğüm yüksekliği komşu hücrelerin z ortalaması; doğrusal z = ax + by + c için
  dört hücre merkezinin ortalaması düğümdeki değerdir (merkezler düğüme göre simetrik). Hacim hatası ≤ P·Δ·H.
- İkili STL (SPEC 39): 80 bayt başlık, '<u4' sayı, üçgen başına '<f4' × 12 + '<u2' = 50 bayt.
- Nokta–üçgen uzaklığı (Ericson 5.1.5): yüz bölgesinde düzleme dik uzaklık; kenar bölgesinde kenara dik
  (düzlem içi s, düzleme dik h) √(s² + h²); köşe bölgesinde köşeye uzaklık. Rastgele noktalarda
  ağırlık merkezli ızgara örneklemesi (ref3d.sample_triangles), örneklem hatası ≤ en uzun kenar / n.
- Sapma (SPEC 39): p = (x_i, y_j, top); s = σ·dist(p, ağ), σ = sign(top − z_P), z_P = −∞ ve top = zmin → 0;
  dz = top − max(z_P, zmin). Kutu parça [5, 15]² × [0, 6]: üstte δ → s = δ; duvar dışı şeritte yatay uzaklık;
  üst yüzden 0.2 derin çakma (yan duvarlardan ≥ 3 uzak) → s = −0.2.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, Stock
from cam.sim import DexelMap, ZMap, mesh_zmap, simulate
from cam.sim.ikiz import (
    Deviation,
    TwinMesh,
    deviation,
    mesh_volume,
    point_mesh_distance,
    point_triangle_distance,
    twin_mesh,
    write_stl,
)
from tests.cam import ref3d
from tests.cam import simref as ref
from tests.cam.simref import G0, G1, flat, path

# ================================================================== bağımsız referanslar


def _vol_ref(V: np.ndarray, T: np.ndarray) -> float:
    """Diverjans teoremi: Σ v₀ · (v₁ × v₂) / 6."""
    v0, v1, v2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def _closed_ref(T: np.ndarray) -> bool:
    """Her yönlü kenar (a, b) sayısı ters yönlü (b, a) sayısına eşit mi."""
    E = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    say: dict[tuple[int, int], int] = {}
    for a, b in E.tolist():
        say[(a, b)] = say.get((a, b), 0) + 1
    return all(say.get((b, a), 0) == k for (a, b), k in say.items())


def _normals(V: np.ndarray, T: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sağ el kuralıyla birim normaller ve üçgen alanları."""
    v0, v1, v2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    L = np.linalg.norm(n, axis=1)
    return n / L[:, None], L / 2.0


def _columns(state) -> list[list[list[tuple[float, float]]]]:
    """Hücre başına aralık listesi [j][i] (z-haritası: z > zmin ise [(zmin, z)])."""
    if isinstance(state, ZMap):
        return [
            [
                [(state.zmin, float(state.z[j, i]))] if state.z[j, i] > state.zmin else []
                for i in range(state.nx)
            ]
            for j in range(state.ny)
        ]
    return [[list(state.intervals(i, j)) for i in range(state.nx)] for j in range(state.ny)]


def _inside(state, P: np.ndarray) -> np.ndarray:
    """Kolon katısına üyelik (düşey ışın paritesi = hücrenin bir aralığının z'yi kesin içermesi)."""
    cols = _columns(state)
    K = max(1, max(len(c) for row in cols for c in row))
    lo = np.full((state.ny, state.nx, K), np.nan)
    hi = np.full((state.ny, state.nx, K), np.nan)
    for j, row in enumerate(cols):
        for i, iv in enumerate(row):
            for k, (lz, u) in enumerate(iv):
                lo[j, i, k], hi[j, i, k] = lz, u
    i = np.floor((P[:, 0] - state.x0) / state.dx).astype(int)
    j = np.floor((P[:, 1] - state.y0) / state.dy).astype(int)
    ok = (i >= 0) & (i < state.nx) & (j >= 0) & (j < state.ny)
    out = np.zeros(len(P), dtype=bool)
    z = P[ok, 2][:, None]
    out[ok] = np.any((lo[j[ok], i[ok]] < z) & (z < hi[j[ok], i[ok]]), axis=1)
    return out


def _zmap(stock: Stock, cell: float, z) -> ZMap:
    m = ZMap.from_stock(stock, cell)
    m.z = np.array(z, dtype=float)
    assert m.z.shape == (m.ny, m.nx)
    return m


def test_referans_oz_denetim():
    """Referans yardımcıların kendisi: kutu hacmi abc, kapalı; kolon üyeliği tek hücrede."""
    V, T = ref3d.box_mesh(2.0, 3.0, 5.0)
    assert _vol_ref(V, T) == pytest.approx(30.0, rel=1e-14)
    assert _closed_ref(T) and not _closed_ref(T[1:])
    m = _zmap(Stock(0, 0, -5, 2, 1, 0), 1.0, [[-2.0, -5.0]])
    P = np.array([[0.5, 0.5, -1.0], [0.5, 0.5, -3.0], [1.5, 0.5, -3.0], [-0.1, 0.5, -3.0]])
    np.testing.assert_array_equal(_inside(m, P), [False, True, False, False])


# ================================================================== K10 kolon ağı

S_TEK = Stock(0.0, 0.0, -5.0, 1.0, 1.0, 0.0)  # 1 × 1 hücre


def _st_tek_hucre():
    return ZMap.from_stock(S_TEK, 1.0)  # z = zmax = 0


def _st_tek_kolon():
    return _zmap(Stock(0, 0, -5, 3, 2, 0), 1.0, [[-5, -2, -5], [-5, -5, -5]])


def _st_basamakli():
    # nx = ⌈4.4/1⌉ = 5 → dx = 0.88, ny = 3, dy = 1 (dx ≠ dy)
    z = [[0, -1, -2, -3, -1.5], [-0.5, -4, -2, -2, -3.25], [-1, -1, -1, -3.5, 0]]
    return _zmap(Stock(0, 0, -4, 4.4, 3, 0), 1.0, z)


def _st_capraz():
    # yalnız köşeden değen iki kolon (farklı yükseklik): ortak düşey kenar dört üçgende olabilir
    return _zmap(Stock(0, 0, -3, 2, 2, 0), 1.0, [[0, -3], [-3, -1]])


def _st_dama():
    z = np.full((3, 3), -2.0)
    for j in range(3):
        for i in range(3):
            if (i + j) % 2 == 0:
                z[j, i] = 0.25 * (i + 2 * j) - 1.0
    return _zmap(Stock(0, 0, -2, 3, 3, 1), 1.0, z)


def _st_cep():
    z = np.zeros((5, 6))
    z[1:4, 1:5] = -3.0
    z[2, 2] = -5.0  # delik (zmin): katı halka biçiminde
    return _zmap(Stock(0, 0, -5, 6, 5, 0), 1.0, z)


def _st_dexel_iki_aralik():
    d = DexelMap.from_stock(Stock(0, 0, -6, 3, 3, 0), 1.0)
    d.subtract(1, 1, -4.0, -2.0)  # iki aralık
    d.subtract(2, 1, -1.0, 1.0)  # üstten
    d.subtract(0, 2, -7.0, -5.0)  # alttan
    d.subtract(2, 2, -5.0, -4.5)
    d.subtract(2, 2, -3.0, -2.0)  # üç aralık
    d.subtract(0, 0, -7.0, 1.0)  # boş hücre
    assert len(d.intervals(1, 1)) == 2 and len(d.intervals(2, 2)) == 3
    return d


def _st_iki_baglama_elle():
    d = DexelMap.from_stock(Stock(0, 0, -10, 5, 4, 0), 1.0)
    for i in range(1, 4):
        for j in range(1, 3):
            d.subtract(i, j, -4.0, 1.0)  # ilk bağlama: üstten cep
    f = d.flipped()  # SPEC 05 K21: ikinci bağlama ters çevrilmiş stokta
    for i in range(2, 5):
        for j in range(0, 3):
            f.subtract(i, j, -3.0, 1.0)  # ikinci bağlama: (orijinalin) alttan cep
    return f


def _st_iki_baglama_sim():
    # SPEC 05 K21 kurgusu (test_sim_dexel.py), hücre 1.0
    stock = Stock(0.0, 0.0, -20.0, 40.0, 30.0, 0.0)
    tool = flat(D=6.0, Lf=30.0)
    r1 = simulate([ref.rect_pocket(tool, 5.3, 5.2, 20.4, 14.7, -6.0)], stock, cell=1.0, model="dexel")
    r2 = simulate(
        [ref.rect_pocket(tool, 15.1, 8.3, 20.2, 13.6, -8.0)],
        stock,
        cell=1.0,
        model="dexel",
        initial=r1.dexel.flipped(),
    )
    return r2.dexel


K10_DURUMLAR = {
    "tek_hucre": _st_tek_hucre,
    "tek_kolon": _st_tek_kolon,
    "basamakli": _st_basamakli,
    "capraz": _st_capraz,
    "dama": _st_dama,
    "cep": _st_cep,
    "dexel_iki_aralik": _st_dexel_iki_aralik,
    "iki_baglama_elle": _st_iki_baglama_elle,
    "iki_baglama_sim": _st_iki_baglama_sim,
}


@pytest.mark.parametrize("ad", list(K10_DURUMLAR))
def test_K10_kolon_agi(ad):
    state = K10_DURUMLAR[ad]()
    tm = twin_mesh(state)
    assert isinstance(tm, TwinMesh)
    V, T, fc = np.asarray(tm.V, dtype=float), np.asarray(tm.T), np.asarray(tm.face_cell)
    m = len(T)
    assert V.ndim == 2 and V.shape[1] == 3 and T.shape == (m, 3) and fc.shape == (m,)
    assert np.issubdtype(T.dtype, np.integer) and np.issubdtype(fc.dtype, np.integer)
    assert T.min() >= 0 and T.max() < len(V)
    # kaynaklanmış: aynı koordinatlı köşe tek kez
    assert len(np.unique(V, axis=0)) == len(V)
    # kapalı (kendi yönlü kenar sayımımız ve uygulamanınki)
    assert _closed_ref(T)
    assert tm.is_closed() is True
    # hacim: durumun hacmi = kendi diverjans toplamımız = volume() = mesh_volume()
    Vs = state.volume()
    assert _vol_ref(V, T) == pytest.approx(Vs, rel=1e-12)
    assert tm.volume() == pytest.approx(Vs, rel=1e-12)
    assert mesh_volume(V, T) == pytest.approx(Vs, rel=1e-12)
    # dışa yönlü: merkez + 1e-6·n dışarıda, merkez − 1e-6·n içeride
    n, A = _normals(V, T)
    assert np.all(A > 0)
    c = V[T].mean(axis=1)
    assert not np.any(_inside(state, c + 1e-6 * n))
    assert np.all(_inside(state, c - 1e-6 * n))
    # eksenlere paralel yüzler: üst (+Z), alt (−Z) ya da dik duvar
    ust = n[:, 2] > 1 - 1e-9
    alt = n[:, 2] < -1 + 1e-9
    duvar = np.abs(n[:, 2]) < 1e-9
    assert np.all(ust | alt | duvar)
    # face_cell: üst yüzde merkezin altındaki hücre c = j·nx + i, duvar ve altta −1
    i = np.floor((c[:, 0] - state.x0) / state.dx).astype(int)
    j = np.floor((c[:, 1] - state.y0) / state.dy).astype(int)
    np.testing.assert_array_equal(fc[ust], j[ust] * state.nx + i[ust])
    assert np.all(fc[~ust] == -1)
    # her aralığın üst yüzü hücreyi tam örter: hücre başına üst alan = dx·dy·(aralık sayısı)
    cols = _columns(state)
    alan = np.bincount(fc[ust], weights=A[ust], minlength=state.nx * state.ny)
    beklenen = np.array([len(cols[jj][ii]) for jj in range(state.ny) for ii in range(state.nx)], dtype=float)
    np.testing.assert_allclose(alan, beklenen * state.dx * state.dy, rtol=1e-12, atol=1e-12)
    # üst yüz yüksekliği hücrenin bir aralığının u'su
    for k in np.flatnonzero(ust):
        us = [u for _, u in cols[j[k]][i[k]]]
        assert min(abs(c[k, 2] - u) for u in us) < 1e-12


def test_K10_tek_hucre_kesin():
    """Tek hücrelik stok: kutu, 6 yüz × 2 = 12 üçgen, 8 köşe, hacim 1·1·5."""
    tm = twin_mesh(_st_tek_hucre())
    assert len(tm.T) == 12 and len(tm.V) == 8
    assert tm.volume() == pytest.approx(5.0, rel=1e-12)
    np.testing.assert_array_equal(np.sort(np.asarray(tm.face_cell)), [-1] * 10 + [0, 0])


def test_K10_twin_mesh_metotlari_elle():
    """TwinMesh.volume / is_closed elle kurulmuş ağda: kutu, eksik üçgen, kenardan değen iki kutu."""
    V, T = ref3d.box_mesh(2.0, 3.0, 5.0)
    tm = TwinMesh(V, T, np.full(len(T), -1))
    assert tm.is_closed() is True and tm.volume() == pytest.approx(30.0, rel=1e-12)
    assert TwinMesh(V, T[1:], np.full(len(T) - 1, -1)).is_closed() is False
    assert mesh_volume(V, T[:, ::-1]) == pytest.approx(-30.0, rel=1e-12)  # ters yön: işaretli hacim
    # yalnız (1, 1, z) kenarından değen iki birim kutu, köşeler kaynaklı: kenar dört üçgende
    Va, Ta = ref3d.box_mesh(1.0, 1.0, 1.0)
    W = np.vstack([Va, Va + [1.0, 1.0, 0.0]])
    U, inv = np.unique(W, axis=0, return_inverse=True)
    T2 = inv.reshape(-1)[np.vstack([Ta, Ta + 8])]
    assert len(U) == 14 and _closed_ref(T2)
    tm2 = TwinMesh(U, T2, np.full(len(T2), -1))
    assert tm2.is_closed() is True and tm2.volume() == pytest.approx(2.0, rel=1e-12)


def test_K10_hatalar():
    bos = _zmap(Stock(0, 0, -5, 3, 2, 0), 1.0, np.full((2, 3), -5.0))
    with pytest.raises(CamError):
        twin_mesh(bos)
    d = DexelMap.from_stock(Stock(0, 0, -5, 2, 2, 0), 1.0)
    for i in range(2):
        for j in range(2):
            d.subtract(i, j, -6.0, 1.0)
    with pytest.raises(CamError):
        twin_mesh(d)
    with pytest.raises(CamError):
        twin_mesh(_st_basamakli(), mode="kolonn")


# ================================================================== K11 yüzey ağı


def test_K11_sabit_yukseklik_hacim_kesin():
    m = _zmap(Stock(0, 0, -5, 7.0, 5.0, 0), 0.6, np.full((9, 12), -2.5))
    tm = twin_mesh(m, mode="yuzey")
    V, T = np.asarray(tm.V, dtype=float), np.asarray(tm.T)
    assert _closed_ref(T) and tm.is_closed() is True
    # kaynak: sabit yükseklikte yüzey ağı kutudur, hacim Lx·Ly·(z − zmin) = state.volume()
    assert tm.volume() == pytest.approx(m.volume(), rel=1e-12)
    assert _vol_ref(V, T) == pytest.approx(7.0 * 5.0 * 2.5, rel=1e-12)


def test_K11_egik_duzlem_ic_dugumler():
    a, b, c0 = 0.3, -0.2, 1.0
    m = ZMap.from_stock(Stock(0, 0, -10, 7.0, 5.0, 5.0), 0.6)  # 12 × 9, dx ≠ dy
    X, Y = m.centers()
    m.z = a * X + b * Y + c0
    assert m.z.min() > m.zmin and m.z.max() < m.zmax
    tm = twin_mesh(m, mode="yuzey")
    V, T = np.asarray(tm.V, dtype=float), np.asarray(tm.T)
    assert _closed_ref(T) and tm.is_closed() is True
    assert tm.volume() > 0  # dışa yönlü
    # iç düğüm (k, ll): 1 ≤ k ≤ nx−1, 1 ≤ ll ≤ ny−1; yüksekliği dört hücre ortalaması = düzlem (doğrusal)
    for k in range(1, m.nx):
        for ll in range(1, m.ny):
            xn, yn = m.x0 + k * m.dx, m.y0 + ll * m.dy
            sec = (np.abs(V[:, 0] - xn) < 1e-9) & (np.abs(V[:, 1] - yn) < 1e-9)
            assert np.any(sec)
            assert V[sec, 2].max() == pytest.approx(a * xn + b * yn + c0, abs=1e-12)


def test_K11_simule_cep_hacim_siniri():
    stock = Stock(0.0, 0.0, -10.0, 40.0, 30.0, 0.0)
    res = simulate([ref.rect_pocket(flat(D=6.0), 8.0, 6.0, 20.0, 15.0, -4.0)], stock, cell=0.5)
    m = res.zmap
    tm = twin_mesh(m, mode="yuzey")
    assert _closed_ref(np.asarray(tm.T)) and tm.is_closed() is True
    # P: yüksekliği değişen komşu hücre sınırlarının toplam boyu; H: en büyük yükseklik farkı; Δ = max(dx, dy)
    fx = m.z[:, 1:] != m.z[:, :-1]  # x komşuları, ortak kenar boyu dy
    fy = m.z[1:, :] != m.z[:-1, :]  # y komşuları, ortak kenar boyu dx
    P = fx.sum() * m.dy + fy.sum() * m.dx
    H = max(np.abs(np.diff(m.z, axis=1)).max(), np.abs(np.diff(m.z, axis=0)).max())
    assert P > 0 and H == pytest.approx(4.0, abs=1e-9)
    assert abs(tm.volume() - m.volume()) <= P * max(m.dx, m.dy) * H


def test_K11_dexel_hata():
    d = DexelMap.from_stock(Stock(0, 0, -5, 3, 2, 0), 1.0)
    with pytest.raises(CamError):
        twin_mesh(d, mode="yuzey")


# ================================================================== K12 STL

STL_DT = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("attr", "<u2")])


def _read_stl(p) -> tuple[bytes, int, np.ndarray]:
    data = open(p, "rb").read()
    assert STL_DT.itemsize == 50
    head = data[:80]
    m = int(np.frombuffer(data[80:84], dtype="<u4")[0])
    rec = np.frombuffer(data[84:], dtype=STL_DT)
    return head, m, rec


def _stl_kontrol(p, V, T, name):
    import os

    m = len(T)
    assert os.path.getsize(p) == 84 + 50 * m
    head, mm, rec = _read_stl(p)
    assert mm == m and len(rec) == m
    # başlık: ad (ASCII) + boşluk dolgusu, "solid" ile başlamaz
    nb = name.encode("ascii")
    assert head[: len(nb)] == nb and head[len(nb) :] == b" " * (80 - len(nb))
    assert not head.startswith(b"solid")
    # köşeler float32 yuvarlamasıyla birebir, normal = birim sağ el normali (float32 toleransı)
    np.testing.assert_array_equal(rec["v"], V[T].astype(np.float32))
    n, _ = _normals(V, T)
    np.testing.assert_allclose(rec["n"], n.astype(np.float32), rtol=0, atol=1e-6)
    assert np.all(rec["attr"] == 0)
    # okunan ağın hacmi (float32 köşelerle) ≈ mesh_volume
    W = rec["v"].astype(float)
    vol = float(np.einsum("ij,ij->i", W[:, 0], np.cross(W[:, 1], W[:, 2])).sum() / 6.0)
    assert vol == pytest.approx(mesh_volume(V, T), rel=1e-6)


def test_K12_write_stl_kutu(tmp_path):
    V, T = ref3d.box_mesh(10.3, 7.7, 3.1)
    V = V + [1.234567, -2.5, 0.1]
    p = tmp_path / "kutu.stl"
    write_stl(p, V, T, "kutu")
    _stl_kontrol(p, V, T, "kutu")
    # ad tam 80 bayt: kabul, dolgu yok; yol str de olabilir
    q = tmp_path / "uzun.stl"
    write_stl(str(q), V, T, "a" * 80)
    assert _read_stl(q)[0] == b"a" * 80


def test_K12_to_stl_ikiz(tmp_path):
    tm = twin_mesh(_st_basamakli())
    V, T = np.asarray(tm.V, dtype=float), np.asarray(tm.T)
    p = tmp_path / "ikiz.stl"
    tm.to_stl(p)  # varsayılan ad "ikiz"
    _stl_kontrol(p, V, T, "ikiz")
    tm.to_stl(tmp_path / "b.stl", name="basamak")
    _stl_kontrol(tmp_path / "b.stl", V, T, "basamak")


def test_K12_hatalar(tmp_path):
    V, T = ref3d.box_mesh(1.0, 2.0, 3.0)
    p = tmp_path / "x.stl"
    with pytest.raises(CamError):
        write_stl(p, V, T, "çapak")  # ASCII değil
    with pytest.raises(CamError):
        write_stl(p, V, T, "a" * 81)  # 80 bayttan uzun
    for k in (-1, len(V)):
        Tb = T.copy()
        Tb[3, 1] = k
        with pytest.raises(CamError):
            write_stl(p, V, Tb)
    for bad in (np.nan, np.inf):
        Vb = V.copy()
        Vb[2, 0] = bad
        with pytest.raises(CamError):
            write_stl(p, Vb, T)


# ================================================================== K13 nokta–üçgen uzaklığı

TA = np.array([0.3, -0.2, 1.1])
TB = np.array([4.1, 0.7, 0.4])
TC = np.array([1.2, 3.6, 2.5])


def _unit(v):
    return v / np.linalg.norm(v)


def _kapali_form_noktalari() -> tuple[np.ndarray, np.ndarray]:
    """Yüz, üç kenar ve üç köşe bölgesinde noktalar ve kapalı form uzaklıkları."""
    n = _unit(np.cross(TB - TA, TC - TA))
    P, d = [], []
    # yüz: ağırlık merkezli iç nokta + h·n → |h|
    for w, h in (((1 / 3, 1 / 3, 1 / 3), 0.7), ((0.6, 0.3, 0.1), -1.3), ((0.2, 0.2, 0.6), 0.0)):
        q = w[0] * TA + w[1] * TB + w[2] * TC
        P.append(q + h * n)
        d.append(abs(h))
    # kenar (P0, Q0), karşı köşe Oc: q = P0 + t(Q0 − P0), düzlem içi dik m (Oc'den uzağa) → √(s² + h²)
    for P0, Q0, Oc in ((TA, TB, TC), (TB, TC, TA), (TC, TA, TB)):
        e = _unit(Q0 - P0)
        mm = _unit(np.cross(e, n))
        if np.dot(Oc - P0, mm) > 0:
            mm = -mm
        for t, s, h in ((0.4, 0.8, 0.5), (0.85, 1.7, -0.3)):
            P.append(P0 + t * (Q0 - P0) + s * mm + h * n)
            d.append(math.hypot(s, h))
    # köşe P0 (diğerleri Q0, Oc): u = −(ê_Q + ê_Oc); (p − P0)·(Q0 − P0) < 0, (p − P0)·(Oc − P0) < 0 → |p − P0|
    for P0, Q0, Oc in ((TA, TB, TC), (TB, TC, TA), (TC, TA, TB)):
        u = _unit(-(_unit(Q0 - P0) + _unit(Oc - P0)))
        for s, h in ((0.9, 0.4), (2.0, -1.1)):
            p = P0 + s * u + h * n
            assert np.dot(p - P0, Q0 - P0) < 0 and np.dot(p - P0, Oc - P0) < 0
            P.append(p)
            d.append(math.hypot(s, h))
    return np.array(P), np.array(d)


def test_K13_bolgeler_kapali_form():
    P, d = _kapali_form_noktalari()
    out = np.asarray(point_triangle_distance(P, TA, TB, TC))
    assert out.shape == (len(P),)
    np.testing.assert_allclose(out, d, rtol=0, atol=1e-12)
    # köşenin kendisi ve kenar ortası: 0
    out0 = np.asarray(point_triangle_distance(np.array([TA, (TB + TC) / 2]), TA, TB, TC))
    np.testing.assert_allclose(out0, [0.0, 0.0], rtol=0, atol=1e-12)


def test_K13_rastgele_yogun_ornekleme():
    rng = np.random.default_rng(39)
    lo = np.minimum.reduce([TA, TB, TC]) - 2.0
    hi = np.maximum.reduce([TA, TB, TC]) + 2.0
    P = rng.uniform(lo, hi, size=(60, 3))
    n_s = 500  # (n+1)(n+2)/2 = 125751 ≥ 10⁵ örnek
    S = ref3d.sample_triangles(np.array([TA, TB, TC]), np.array([[0, 1, 2]]), n_s)
    assert len(S) >= 100_000
    h = max(np.linalg.norm(TB - TA), np.linalg.norm(TC - TB), np.linalg.norm(TA - TC)) / n_s
    d = np.asarray(point_triangle_distance(P, TA, TB, TC))
    for k, p in enumerate(P):
        ds = float(np.sqrt(np.min(np.sum((S - p) ** 2, axis=1))))
        # örnekler üçgen üstünde: d ≤ d_örnek; her üçgen noktası bir örneğe ≤ h → d_örnek − d ≤ h
        assert d[k] <= ds + 1e-12
        assert ds - d[k] <= h


def test_K13_point_mesh_distance_kaba_kuvvet():
    V, T = ref3d.sphere_cap_mesh(2.0, 1.2, 4, 10)
    V = V + [0.5, -0.3, 1.0]
    rng = np.random.default_rng(3939)
    P = rng.uniform([-3.0, -3.5, -1.5], [4.0, 3.0, 4.5], size=(40, 3))
    d = np.asarray(point_mesh_distance(P, V, T))
    assert d.shape == (len(P),)
    kaba = np.min([np.asarray(point_triangle_distance(P, V[a], V[b], V[c])) for a, b, c in T], axis=0)
    np.testing.assert_allclose(d, kaba, rtol=0, atol=1e-12)
    ref_d = np.array([ref3d.point_mesh_distance(p, V, T) for p in P])
    np.testing.assert_allclose(d, ref_d, rtol=0, atol=1e-12)


# ================================================================== K14 sapma, analitik

K_STOK = Stock(0.0, 0.0, 0.0, 20.0, 20.0, 10.0)  # hücre 0.5 → 40 × 40, merkezler 0.25 + 0.5k
K_V, K_T = ref3d.box_mesh(10.0, 10.0, 6.0)
K_V = K_V + [5.0, 5.0, 0.0]  # parça [5, 15] × [5, 15] × [0, 6]; tabanı stok tabanında


def _k_grid():
    m = ZMap.from_stock(K_STOK, 0.5)
    X, Y = m.centers()
    ic = (X > 5) & (X < 15) & (Y > 5) & (Y < 15)  # parça izdüşümü (merkezler kenarlarda değil)
    return m, X, Y, ic


def _k_partz(ic):
    zP = np.full(ic.shape, -np.inf)
    zP[ic] = 6.0  # kaynak: kutunun üst yüzü
    return zP


def _k_dexel(top: np.ndarray) -> DexelMap:
    """Aynı üst yüzeyli dexel: her hücreden [top, zmax] kaldırılır."""
    d = DexelMap.from_stock(K_STOK, 0.5)
    for j, i in np.argwhere(top < K_STOK.zmax):
        a = float(top[j, i]) if top[j, i] > K_STOK.zmin else K_STOK.zmin - 1.0
        d.subtract(int(i), int(j), a, K_STOK.zmax + 1.0)
    return d


def _layer(delta: float) -> ZMap:
    m, X, Y, ic = _k_grid()
    m.z = np.where(ic, 6.0 + delta, K_STOK.zmin)
    return m


@pytest.mark.parametrize("delta", [0.1, 0.3])
def test_K14a_duzgun_tabaka(delta):
    m, X, Y, ic = _k_grid()
    m = _layer(delta)
    dev = deviation(m, K_V, K_T)
    assert isinstance(dev, Deviation)
    assert dev.s.shape == dev.dz.shape == dev.measured.shape == (m.ny, m.nx)
    # kenarlardan δ'dan uzak izdüşüm hücreleri: p = (x, y, 6 + δ), en yakın nokta üst yüzde → s = δ
    kenar = np.minimum.reduce([X - 5, 15 - X, Y - 5, 15 - Y])
    uzak = ic & (kenar > delta)
    assert uzak.sum() > 100
    np.testing.assert_allclose(dev.s[uzak], delta, rtol=0, atol=1e-12)
    np.testing.assert_allclose(dev.dz[ic], delta, rtol=0, atol=1e-12)  # top − z_P
    # (d) malzemesiz ve parçasız hücre: s = 0, ölçülmez
    assert np.all(dev.s[~ic] == 0.0)
    np.testing.assert_array_equal(dev.measured, ic)
    # açık part_z (elle) aynı sonucu verir
    dev2 = deviation(m, K_V, K_T, part_z=_k_partz(ic))
    np.testing.assert_allclose(dev2.s, dev.s, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(dev2.measured, dev.measured)


def test_K14b_duvar_disi_serit():
    m, X, Y, ic = _k_grid()
    w = 2.0
    serit = (X > 15) & (X < 15 + w) & (Y > 5) & (Y < 15)
    top = np.where(ic | serit, 6.0, K_STOK.zmin)
    m.z = top
    for state in (m, _k_dexel(top)):
        for pz in (None, _k_partz(ic)):
            dev = deviation(state, K_V, K_T, part_z=pz)
            # şeritte p = (x, y, 6): en yakın nokta duvar x = 15 üstünde (15, y, 6) → s = x − 15
            np.testing.assert_allclose(dev.s[serit], X[serit] - 15.0, rtol=0, atol=1e-12)
            # dz = top − max(z_P = −∞, zmin) = 6 − 0 = duvar yüksekliği
            np.testing.assert_allclose(dev.dz[serit], 6.0, rtol=0, atol=1e-12)
            # izdüşümde top = z_P → s = 0, dz = 0
            np.testing.assert_allclose(dev.s[ic], 0.0, rtol=0, atol=1e-12)
            np.testing.assert_allclose(dev.dz[ic], 0.0, rtol=0, atol=1e-12)
            np.testing.assert_array_equal(dev.measured, ic | serit)
            assert dev.max_excess == pytest.approx(X[serit].max() - 15.0, abs=1e-12)
            assert dev.max_gouge == pytest.approx(0.0, abs=1e-12)


def test_K14c_cakma_cebi():
    m, X, Y, ic = _k_grid()
    cep = (X > 8) & (X < 12) & (Y > 8) & (Y < 12)
    m.z = np.where(ic, 6.0, K_STOK.zmin)
    m.z[cep] = 5.8
    dev = deviation(m, K_V, K_T)
    # p = (x, y, 5.8) kutunun içinde; üst yüze 0.2, yan duvarlara ≥ 3, tabana 5.8 → s = −0.2
    np.testing.assert_allclose(dev.s[cep], -0.2, rtol=0, atol=1e-12)
    np.testing.assert_allclose(dev.dz[cep], -0.2, rtol=0, atol=1e-12)
    assert dev.max_gouge == pytest.approx(0.2, abs=1e-12)
    assert dev.max_excess == pytest.approx(0.0, abs=1e-12)
    # (d)
    assert np.all(dev.s[~ic] == 0.0) and not np.any(dev.measured[~ic])


def test_K14_hatalar():
    m = _layer(0.1)
    with pytest.raises(CamError):
        deviation(m, np.zeros((0, 3)), np.zeros((0, 3), dtype=int))  # boş ağ
    Tb = K_T.copy()
    Tb[0, 0] = len(K_V)
    with pytest.raises(CamError):
        deviation(m, K_V, Tb)  # aralık dışı indeks
    Tb[0, 0] = -1
    with pytest.raises(CamError):
        deviation(m, K_V, Tb)
    with pytest.raises(CamError):
        deviation(m, K_V, K_T, part_z=np.zeros((m.ny + 1, m.nx)))  # şekil uyuşmazlığı


# ================================================================== K15 sapma özeti


def _k15_durum():
    """Karma durum ve analitik s: tabaka 0.125, top = 6 şerit, iki çakma (0.2, 0.5), duvar dışı şerit."""
    m, X, Y, ic = _k_grid()
    z = np.where(ic, 6.125, K_STOK.zmin)
    s = np.where(ic, 0.125, 0.0)  # 6.125 − 6 kesin
    tam = ic & (X < 7)
    z[tam], s[tam] = 6.0, 0.0  # top = z_P → σ = 0
    ca = (X > 8) & (X < 10) & (Y > 8) & (Y < 12)
    cb = (X > 10) & (X < 12) & (Y > 8) & (Y < 12)
    z[ca], s[ca] = 5.8, -(6.0 - 5.8)  # üst yüze uzaklık, yan duvarlar ≥ 3
    z[cb], s[cb] = 5.5, -0.5
    serit = (X > 15) & (X < 17) & (Y > 5) & (Y < 15)
    z[serit], s[serit] = 6.0, X[serit] - 15.0  # 0.25, 0.75, 1.25, 1.75
    m.z = z
    return m, s, ic | serit


def test_K15_ozet_ve_bantlar():
    m, s_ref, olc = _k15_durum()
    dev = deviation(m, K_V, K_T)
    np.testing.assert_array_equal(dev.measured, olc)
    np.testing.assert_allclose(dev.s, s_ref, rtol=0, atol=1e-12)
    sm = s_ref[olc]
    assert dev.max_excess == pytest.approx(max(sm.max(), 0.0), abs=1e-12)  # 1.75
    assert dev.max_gouge == pytest.approx(max((-sm).max(), 0.0), abs=1e-12)  # 0.5
    assert dev.rms == pytest.approx(math.sqrt(np.mean(sm**2)), rel=1e-12)
    # bantlar: < b0, [b_i, b_{i+1}), ≥ b_m; kenara eşit değer sağ aralıkta (0 ve 0.125 kesin)
    b = [-0.25, -0.1, 0.0, 0.125, 0.5, 1.0, 1.5]
    say = np.asarray(dev.bands(b))
    assert say.shape == (len(b) + 1,)
    beklenen = [int((sm < b[0]).sum())]
    beklenen += [int(((sm >= b[k]) & (sm < b[k + 1])).sum()) for k in range(len(b) - 1)]
    beklenen += [int((sm >= b[-1]).sum())]
    np.testing.assert_array_equal(say, beklenen)
    assert say.sum() == olc.sum()
    assert say[0] == (s_ref == -0.5).sum() > 0  # −0.5 < b0
    assert say[3] == ((s_ref == 0.0) & olc).sum() > 0  # s = 0 → [0, 0.125)
    assert say[4] == (s_ref == 0.125).sum() + (s_ref == 0.25).sum()  # 0.125 → [0.125, 0.5)
    assert say[-1] == (np.abs(s_ref - 1.75) < 1e-12).sum() > 0  # ≥ 1.5
    # within: tüm ölçülen hücrelerde −lo ≤ s ≤ hi
    assert dev.within(0.5 + 1e-9, 1.75 + 1e-9) is True
    assert dev.within(0.4, 2.0) is False
    assert dev.within(1.0, 1.7) is False


@pytest.mark.parametrize("delta,beklenen", [(0.0625, True), (0.1, True), (0.125, False), (0.3, False)])
def test_K15_within_tabaka(delta, beklenen):
    dev = deviation(_layer(delta), K_V, K_T)
    # K14(a): her ölçülen hücrede s = δ (≥ 0) → within(0, 0.1) ⇔ δ ≤ 0.1
    assert dev.within(0.0, 0.1) is beklenen
    assert dev.max_excess == pytest.approx(delta, abs=1e-12)
    assert dev.max_gouge == pytest.approx(0.0, abs=1e-12)
    assert dev.rms == pytest.approx(delta, abs=1e-12)


def test_K15_hatalar():
    dev = deviation(_layer(0.1), K_V, K_T)
    for b in ([0.0, 0.0, 1.0], [1.0, 0.0], [0.0, 0.5, 0.2]):
        with pytest.raises(CamError):
            dev.bands(b)
    for lo, hi in ((-0.1, 0.1), (0.0, -0.1)):
        with pytest.raises(CamError):
            dev.within(lo, hi)


# ================================================================== K16 uçtan uca

E_STOK = Stock(0.0, 0.0, -10.0, 40.0, 30.0, 0.0)
E_Y1, E_Y2, E_H = 9.0, 21.0, 4.0  # parça: X boyunca açık kanal y ∈ [9, 21], taban z = −4
E_W = 0.8  # duvar payı: işlenen kanal y ∈ [9.8, 20.2]


def _kanal_parca() -> tuple[np.ndarray, np.ndarray]:
    """Kanallı blok, elle kapalı ağ: (y, z) kesit çokgeni (CCW) X boyunca [0, 40] çekilir."""
    y1, y2, H = E_Y1, E_Y2, E_H
    # eşdoğrusal (0, −H) ve (30, −H) köşeleri uç kapak üçgenlemesinde T-birleşimi olmasın diye
    poly = [(0, -10), (30, -10), (30, -H), (30, 0), (y2, 0), (y2, -H), (y1, -H), (y1, 0), (0, 0), (0, -H)]
    kapak = [(0, 1, 2), (0, 2, 5), (0, 5, 6), (0, 6, 9), (9, 6, 7), (9, 7, 8), (5, 2, 3), (5, 3, 4)]
    k = len(poly)
    x0, x1 = 0.0, 40.0
    V = np.array([[x, y, z] for x in (x0, x1) for (y, z) in poly], dtype=float)
    T = [(k + a, k + b, k + c) for a, b, c in kapak]  # x = 40: CCW → normal +x
    T += [(c, b, a) for a, b, c in kapak]  # x = 0: ters
    for p in range(k):
        q = (p + 1) % k
        T += [(p, q, k + q), (p, k + q, k + p)]  # kenar p → q, dış normal (dz, −dy)
    T = np.array(T, dtype=int)
    # öz denetim: kapalı, hacim = 40·(30·10 − (y2 − y1)·H), dışa yönlü
    assert _closed_ref(T)
    assert _vol_ref(V, T) == pytest.approx(40.0 * (300.0 - (y2 - y1) * H), rel=1e-12)
    return V, T


def _kanal_yolu():
    """Düz Ø6 takım: kanal zigzagı + iki duvar konturu; merkez satırları y ∈ [9.8 + R, 20.2 − R]."""
    tool = flat(D=6.0)
    R = 3.0
    ya, yb = E_Y1 + E_W + R, E_Y2 - E_W - R
    ym = (ya + yb) / 2
    z = -E_H
    mv = [G0(-5.0, ym, 5.0), G1(-5.0, ym, z), G1(45.0, ym, z)]  # stok dışından yatay giriş
    mv += [G1(45.0, ya, z), G1(-5.0, ya, z)]  # kontur: alt duvar
    mv += [G1(-5.0, yb, z), G1(45.0, yb, z), G1(45.0, yb, 5.0)]  # kontur: üst duvar
    return path(tool, (-5.0, ym, 5.0), mv, "kanal")


def test_K16_uctan_uca():
    V, T = _kanal_parca()
    res = simulate([_kanal_yolu()], E_STOK, cell=0.5, gouge_tol=1e-3)
    m = res.zmap
    tm = twin_mesh(m)
    assert tm.is_closed() is True
    assert tm.volume() == pytest.approx(m.volume(), rel=1e-12)
    dev = deviation(m, V, T)
    # çakma yok: işlenen kanal parça kanalının içinde
    assert dev.max_gouge <= 1e-3
    # fazlalık: duvar payı şeridinde p = (x, y, 0), duvara yatay uzaklık ≤ w; ızgara toleransı Δ
    D = max(m.dx, m.dy)
    assert abs(dev.max_excess - E_W) <= D
    assert dev.max_excess <= E_W + 1e-12
    # kanal tabanı ve blok üstü: s = 0 (top = z_P)
    X, Y = m.centers()
    taban = (Y > E_Y1 + E_W + 1e-6) & (Y < E_Y2 - E_W - 1e-6)
    np.testing.assert_allclose(dev.s[taban], 0.0, rtol=0, atol=1e-9)
    disari = (Y < E_Y1) | (Y > E_Y2)
    np.testing.assert_allclose(dev.s[disari], 0.0, rtol=0, atol=1e-9)
    assert np.all(dev.measured)
    # parça z-haritası tutarlılığı (SPEC 05 mesh_zmap)
    zP = mesh_zmap(V, T, m)
    np.testing.assert_allclose(zP[taban], -E_H, rtol=0, atol=1e-12)
