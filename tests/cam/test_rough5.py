"""SPEC 50 — 5 eksen kaba (yönelim kümesi, 3+2) testleri (K1, K2, K3, K9'un kaba kısmı).

Testler yalnız SPEC 50 metninden (Teori, Arayüz, Ek A), `cam/model.py`, `cam/dropcutter.py` (`TriMesh`),
`cam/ops3d.py` (`Raster`, `raster_lines`, `rough`), `cam/multiaxis/indexed.py` (`from_normal`, `local_stock`,
`local_mesh`), `cam/sim/simulate5.py` (`simulate5`) ve `geometry/features.py` (`block`) arayüzlerinden
yazıldı; `cam/multiaxis/rough5.py` gövdeleri okunmadı (iskelette NotImplementedError).

Kurallar (SPEC 50 Teori + Ek A):
- Her F_i için 06 kabanın girdileri: stok = local_stock(stock, F_i), raster dikdörtgeni = yerel stoğun XY'si,
  ds = stepover, ds_min = DS_MIN (0.05; koordinatöre önerildi: ds_min = stepover iken 06 kabanın örnekler
  arası doğrusal hareketleri cep kenarını keser), tol = 0.01, z_safe = zmax_yerel + 5, direction = "x",
  z_bottom = max(zmin_yerel_stok, zmin_yerel_ağ). F = +Z ve v_min = 0 iken yol ops3d.rough ile aynıdır.
- Hava kesmesi: o ana kadarki tri-dexel stokta v_min'den (varsayılan 0.01·ae·ap·L, L hareket boyu) az malzeme
  kaldıran G1'ler G0'a çevrilir; v_min = 0 atlamayı kapatır.
- Sonuç: her yol frame = F_i, meta.axis_mode = "3+2", meta.strategy = "kaba"; ikinci dönüş
  son stok (TriDexel).
- max_tilt [°] (varsayılan 30): yönelim ekseninin +Z ile açısı bunu aşarsa CamError.

Beklenen hacimler (düz uç, R = 3): cep tabanı raster sıralarıyla ve örnek noktalarıyla teğet hizalanır
(duvarlar sıra ± (R + ε)), böylece takımın süpürdüğü bölge [x_ilk − R, x_son + R] × [y_ilk − R, y_son + R];
bu bölgede kaldırılan hacim a·b·h ile a·b·h − K arasındadır, ızgara payı %1. K en büyük kalıntı:
dört dik köşe radyüsü 4(1 − π/4)R²h ve sıralara dik iki duvarda ardışık sıra (aralık s) daireleri arasındaki
tarak 2(n_sıra − 1)·A·h, A = s(R − d₀) − 2[F(R) − F(d₀)], d₀ = √(R² − (s/2)²),
F(d) = (d/2)√(R² − d²) + (R²/2)·asin(d/R) (dairenin kapsamadığı alan; dalma / bağlantı hareketleri kısmen
temizleyebilir, o yüzden alt sınır).
Ölçüm: z ışınları boyunca, ışının ölçüm kutusu içindeki tam aralığı ile kalan malzeme aralıklarının
kesişimi (ışın başına tam).
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from cam.dropcutter import TriMesh
from cam.model import CamError, Frame, Move, MoveType, Stock, Tool, ToolKind, Toolpath
from cam.multiaxis.indexed import from_normal, local_mesh, local_stock
from cam.multiaxis.rough5 import RoughCut, rough5
from cam.ops3d import Raster, raster_lines, rough
from cam.sim.simulate5 import simulate5

R = 3.0
EPS = 0.05  # cep duvarının teğet takım konumundan payı (teğet temas drop'ta "değiyor" sayılır)
CELL = 0.5
DS_MIN = 0.05  # Ek A raster'ında uyarlamalı bölmenin en küçük aralığı (önerilen düzeltme)
STOCK = Stock(0.0, 0.0, 0.0, 60.0, 40.0, 30.0)
FEED, PLUNGE, RPM = 1000.0, 300.0, 8000.0
AP, AE = 2.5, 4.0
H_UST, H_EGIK = 5.0, 3.0  # cep derinlikleri


def _flat() -> Tool:
    return Tool(id=1, name="kaba", kind=ToolKind.FLAT, D=2 * R, flute_length=40.0)


def _cut(allowance: float = 0.0) -> RoughCut:
    return RoughCut(a_p=AP, stepover=AE, feed=FEED, plunge_feed=PLUNGE, rpm=RPM, allowance=allowance)


def _F_ust() -> Frame:
    return from_normal((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))


def _F_egik() -> Frame:
    """Pah düzlemi x + z = 70.1 (45°), merkezi (50.05, 20, 20.05); yerel x yokuş yukarı, yerel z dış normal.

    70.1: tri-dexel ışın merkezleri (0.5 adımlı, x + z = 0.5k) pah yüzünün içinde kalmasın (ölçüm tekilliği).
    """
    return from_normal((50.05, 20.0, 20.05), (1.0, 0.0, 1.0), (-1.0, 0.0, 1.0))


def _T(F: Frame) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = np.array(F.R)
    T[:3, 3] = F.origin
    return T


def _kutu(F: Frame | None, lo, hi):
    """F yerel çerçevesinde [lo, hi] kutusu (OCCT parçası)."""
    from geometry.features import block

    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    S = np.eye(4)
    S[:3, 3] = lo
    T = S if F is None else _T(F) @ S
    return block(*(hi - lo)).moved(T)


def _ek_a_raster(st: Stock, cut: RoughCut) -> Raster:
    return Raster(
        xmin=st.xmin, xmax=st.xmax, ymin=st.ymin, ymax=st.ymax, stepover=cut.stepover, ds=cut.stepover,
        tol=0.01, ds_min=DS_MIN, feed=cut.feed, plunge_feed=cut.plunge_feed, rpm=cut.rpm,
        z_safe=st.zmax + 5.0, direction="x", clearance=cut.clearance,
    )  # fmt: skip


def _ornekler(st: Stock, cut: RoughCut) -> tuple[list[float], list[float]]:
    """Ek A raster'ının sıra (y) ve sıra üstü örnek (x) konumları: düz bir ağda 06 kabanın kesme noktaları."""
    r = _ek_a_raster(st, cut)
    z = st.zmin + 0.5 * (st.zmax - st.zmin)
    x0, x1, y0, y1 = st.xmin - 50, st.xmax + 50, st.ymin - 50, st.ymax + 50
    V = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]])
    tp = rough(TriMesh(V=V, T=np.array([[0, 1, 2], [0, 2, 3]])), st, _flat(), r, cut.a_p, z - 1.0)
    xs = sorted(
        {round(m.end[0], 9) for m in tp.moves if m.type is MoveType.LINEAR and abs(m.end[2] - z) < 1e-9}
    )
    return raster_lines(r), xs


def _ust_cep_kutusu() -> tuple[np.ndarray, np.ndarray]:
    """Üst cep süpürme bölgesi: sıralar 12…28, örnekler 12…28 (F = +Z, raster 0…60 × 0…40, adım 4)."""
    return np.array([9.0, 9.0]), np.array([31.0, 31.0])


_EGIK = None


def _egik_cep() -> tuple[np.ndarray, np.ndarray]:
    """Eğik yüzdeki cebin süpürme bölgesi (yerel x, y): yerel raster örneklerinden 3 × 4 teğet hizalı."""
    global _EGIK
    if _EGIK is None:
        ys, xs = _ornekler(local_stock(STOCK, _F_egik()), _cut())
        ys = [y for y in ys if -10.0 <= y <= 10.0][:4]
        xs = [x for x in xs if -6.0 <= x <= 6.0][:3]
        assert len(ys) == 4 and len(xs) == 3
        _EGIK = (np.array([xs[0] - R, ys[0] - R]), np.array([xs[-1] + R, ys[-1] + R]))
    return _EGIK


def _parca_k1():
    from geometry.features import block

    lo, hi = _ust_cep_kutusu()
    cep = _kutu(None, (lo[0] - EPS, lo[1] - EPS, 20.0), (hi[0] + EPS, hi[1] + EPS, 26.0))
    return block(60.0, 40.0, 25.0).cut(cep)


def _parca_k2():
    from geometry.features import block

    F = _F_egik()
    lo, hi = _ust_cep_kutusu()
    p = block(60.0, 40.0, 30.0)
    p = p.cut(_kutu(F, (-30.0, -30.0, 0.0), (30.0, 30.0, 40.0)))  # pah: x + z ≥ 70.1
    p = p.cut(_kutu(None, (lo[0] - EPS, lo[1] - EPS, 25.0), (hi[0] + EPS, hi[1] + EPS, 31.0)))
    el, eh = _egik_cep()
    return p.cut(_kutu(F, (el[0] - EPS, el[1] - EPS, -H_EGIK), (eh[0] + EPS, eh[1] + EPS, 1.0)))


_AG: dict[str, TriMesh] = {}


def _ag(ad: str) -> TriMesh:
    if ad not in _AG:
        _AG[ad] = TriMesh.from_part(_parca_k1() if ad == "k1" else _parca_k2())
    return _AG[ad]


# ---------------------------------------------------------------- ölçüm (z ışınları, ışın başına tam)


def _kutu_icinde_malzeme(td, F: Frame | None, lo, hi) -> tuple[float, float]:
    """F yerel kutusu [lo, hi] içinde (kutu hacmi, kalan malzeme hacmi), z ışını ailesiyle."""
    m = td.maps["z"]
    X, Y = np.meshgrid(m.xs(), m.ys())
    M = np.eye(3) if F is None else np.array(F.R)
    o = np.zeros(3) if F is None else np.array(F.origin)
    z_lo = np.full(X.shape, -np.inf)
    z_hi = np.full(X.shape, np.inf)
    for i in range(3):
        e = M[:, i]  # yerel eksen i'nin WCS birim vektörü: yerel koordinat = e·(p − o)
        c = e[0] * (X - o[0]) + e[1] * (Y - o[1]) - e[2] * o[2]
        if abs(e[2]) < 1e-12:
            disarida = (c < lo[i]) | (c > hi[i])
            z_lo[disarida], z_hi[disarida] = np.inf, -np.inf
            continue
        a, b = (lo[i] - c) / e[2], (hi[i] - c) / e[2]
        z_lo, z_hi = np.maximum(z_lo, np.minimum(a, b)), np.minimum(z_hi, np.maximum(a, b))
    L = np.clip(z_hi - z_lo, 0.0, None)
    kesisim = np.minimum(m.hi, z_hi[..., None]) - np.maximum(m.lo, z_lo[..., None])
    ic = np.where(m.hi > m.lo, np.clip(kesisim, 0.0, None), 0.0)
    alan = m.dx * m.dy
    return float(L.sum()) * alan, float(ic.sum()) * alan


def _isin_tepesi(td, x: float, y: float, z_alt: float, z_ust: float) -> tuple[float, float, float]:
    """(x, y)'ye en yakın z ışınında [z_alt, z_ust] ile kesişen malzeme aralıklarının en yüksek ucu

    Işının (x, y) merkezi de döner.
    """
    m = td.maps["z"]
    i = int(np.argmin(np.abs(m.xs() - x)))
    j = int(np.argmin(np.abs(m.ys() - y)))
    ust = [hi for lo, hi in td.intervals("z", i, j) if hi > z_alt and lo < z_ust]
    assert ust, "ışında beklenen aralıkta malzeme yok"
    return max(ust), float(m.xs()[i]), float(m.ys()[j])


def _gouge(td, mesh: TriMesh) -> float:
    """Son stokta parça ∖ malzeme hacmi (simulate5, malzeme kaldırmayan tek G0 ile)."""
    hareket = [Move(MoveType.RAPID, (-50.0, -45.0, 100.0))]
    bos = Toolpath(name="bos", tool=_flat(), start=(-50.0, -50.0, 100.0), moves=hareket, rpm=RPM)
    return simulate5([bos], STOCK, cell=CELL, part=mesh, initial=td).gouge_volume()


def _tarak_alani(s: float = AE) -> float:
    """Komşu iki sıranın (aralık s) R yarıçaplı dairelerinin duvar tarafında kapsamadığı alan A."""

    def F(d: float) -> float:
        return d / 2 * math.sqrt(max(R * R - d * d, 0.0)) + R * R / 2 * math.asin(d / R)

    d0 = math.sqrt(R * R - (s / 2) ** 2)
    return s * (R - d0) - 2 * (F(R) - F(d0))


def _cep_kontrol(kaldirilan: float, V: float, h: float, n_sira: int) -> None:
    """V: ölçüm kutusu hacmi (a·b·h, ışınlarla); kaldırılan ∈ [V − K, V], %1 ızgara payıyla."""
    K = (4 * (1 - math.pi / 4) * R * R + 2 * (n_sira - 1) * _tarak_alani()) * h
    assert V - K - 0.01 * V <= kaldirilan <= V + 0.01 * V, (kaldirilan, V, K)


# ---------------------------------------------------------------- K1


_K1 = None


def _k1():
    global _K1
    if _K1 is None:
        _K1 = rough5(_ag("k1"), STOCK, _flat(), [_F_ust()], _cut(), cell=CELL, v_min=0.0)
    return _K1


@pytest.mark.occt
@pytest.mark.slow
def test_k1_tek_yonelim_06_ile_ayni_yol():
    yollar, _ = _k1()
    assert len(yollar) == 1
    tp = yollar[0]
    z_bottom = max(STOCK.zmin, float(_ag("k1").bbox()[0][2]))
    ref = rough(_ag("k1"), STOCK, _flat(), _ek_a_raster(STOCK, _cut()), AP, z_bottom, 0.0)
    np.testing.assert_allclose(tp.start, ref.start, atol=1e-9)
    assert len(tp.moves) == len(ref.moves)
    for m, mr in zip(tp.moves, ref.moves, strict=True):
        assert m.type is mr.type
        np.testing.assert_allclose(m.end, mr.end, atol=1e-9)
        if mr.type is not MoveType.RAPID:
            assert m.feed == pytest.approx(mr.feed)
    assert tp.meta is not None
    assert tp.meta.strategy == "kaba"
    assert tp.meta.axis_mode == "3+2"
    F = _F_ust()
    assert tp.frame is not None
    np.testing.assert_allclose(np.array(tp.frame.R), np.array(F.R), atol=1e-12)
    np.testing.assert_allclose(tp.frame.origin, F.origin, atol=1e-12)


@pytest.mark.occt
@pytest.mark.slow
def test_k1_kaldirilan_hacim_43_ile():
    """Son stok = 43 ile aynı yolun simülasyonu; üst katman tamamen, cep analitik kadar boşalır; çakma yok."""
    yollar, td = _k1()
    sim = simulate5(yollar, STOCK, cell=CELL)
    assert td.volume() == pytest.approx(sim.tridexel.volume(), rel=1e-6)
    _, ust = _kutu_icinde_malzeme(td, None, (0.0, 0.0, 25.0), (60.0, 40.0, 30.0))
    assert ust == pytest.approx(0.0, abs=1e-6)
    lo, hi = _ust_cep_kutusu()
    V, kalan = _kutu_icinde_malzeme(td, None, (*lo, 20.0), (*hi, 25.0))
    assert V == pytest.approx((hi[0] - lo[0]) * (hi[1] - lo[1]) * 5.0, rel=1e-9)
    _cep_kontrol(V - kalan, V, 5.0, n_sira=5)
    assert _gouge(td, _ag("k1")) <= 1e-6


# ---------------------------------------------------------------- K2


_K2: dict = {}


def _k2(allowance: float = 0.0, v_min: float | None = None):
    k = (allowance, v_min)
    if k not in _K2:
        _K2[k] = rough5(
            _ag("k2"), STOCK, _flat(), [_F_ust(), _F_egik()], _cut(allowance), cell=CELL, v_min=v_min,
            max_tilt=50.0,
        )  # fmt: skip
    return _K2[k]


@pytest.mark.occt
@pytest.mark.slow
def test_k2_iki_yonelim_yollar():
    yollar, _ = _k2()
    assert len(yollar) == 2
    for tp, F in zip(yollar, (_F_ust(), _F_egik()), strict=True):
        assert tp.frame is not None
        np.testing.assert_allclose(np.array(tp.frame.R), np.array(F.R), atol=1e-12)
        np.testing.assert_allclose(tp.frame.origin, F.origin, atol=1e-12)
        assert tp.meta.strategy == "kaba"
        assert tp.meta.axis_mode == "3+2"


@pytest.mark.occt
@pytest.mark.slow
def test_k2_iki_cep_analitik_hacim():
    _, td = _k2()
    lo, hi = _ust_cep_kutusu()
    V, kalan = _kutu_icinde_malzeme(td, None, (*lo, 25.0), (*hi, 30.0))
    assert V == pytest.approx((hi[0] - lo[0]) * (hi[1] - lo[1]) * H_UST, rel=1e-9)
    _cep_kontrol(V - kalan, V, H_UST, n_sira=5)
    el, eh = _egik_cep()
    V, kalan = _kutu_icinde_malzeme(td, _F_egik(), (*el, -H_EGIK), (*eh, 0.0))
    a, b = eh - el
    assert V == pytest.approx(a * b * H_EGIK, rel=0.01)  # ışın örneklemesi kutuyu doğru ölçüyor
    _cep_kontrol(V - kalan, V, H_EGIK, n_sira=4)
    assert _gouge(td, _ag("k2")) <= 1e-6


@pytest.mark.occt
@pytest.mark.slow
def test_k2_kalan_pay():
    """allowance = 0.5: cep tabanlarında kalan malzeme tam pay kadar (ışın boyunca tam)."""
    d = 0.5
    _, td = _k2(allowance=d)
    lo, hi = _ust_cep_kutusu()
    tepe, _, _ = _isin_tepesi(td, (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 24.0, 30.0)
    assert tepe == pytest.approx(25.0 + d, abs=1e-6)
    # eğik cep tabanı: yerel z = −h + δ düzlemi;
    # dik ışın bu düzlemi z = (−h + δ − e·((x, y, 0) − o))/e_z'de keser
    F = _F_egik()
    el, eh = _egik_cep()
    c = np.array(F.origin) + np.array(F.R) @ np.array([(el[0] + eh[0]) / 2, (el[1] + eh[1]) / 2, -H_EGIK])
    e = np.array(F.R)[:, 2]
    tepe, x, y = _isin_tepesi(td, c[0], c[1], c[2] - 1.0, c[2] + 1.0)
    z_bek = (-H_EGIK + d - e[0] * (x - F.origin[0]) - e[1] * (y - F.origin[1])) / e[2] + F.origin[2]
    assert tepe == pytest.approx(z_bek, abs=1e-6)
    assert _gouge(td, _ag("k2")) <= 1e-6


# ---------------------------------------------------------------- K3


@pytest.mark.occt
@pytest.mark.slow
def test_k3_ikinci_yonelimde_her_g1_malzeme_kaldirir():
    """İlk yönelimden sonraki stokla ikinci yolun her G1'i ≥ v_min (= 0.01·ae·ap·L) kaldırır.

    Tri-dexel ayrıklaştırması için alt sınır v_min/2; temizlenmiş bölgede G1 olsaydı kaldırma 0 olurdu.
    """
    yollar, _ = _k2()
    ilk = simulate5([yollar[0]], STOCK, cell=CELL)
    ikinci = simulate5([yollar[1]], STOCK, cell=CELL, initial=ilk.tridexel)
    g1 = [s for s in ikinci.steps if s.type is MoveType.LINEAR and not s.link]
    assert g1
    for s in g1:
        L = float(np.linalg.norm(np.subtract(s.end, s.start)))
        assert s.removed >= 0.5 * 0.01 * AE * AP * L, f"adım {s.k}: {s.removed} mm³, L = {L}"


@pytest.mark.occt
@pytest.mark.slow
def test_k3_atlama_kapaliyken_yol_06_ile_ayni():
    """v_min = 0: ikinci yönelimin yolu yerel ağ / yerel stokta ops3d.rough ile aynı.

    Atlama açıkken daha az G1.
    """
    yollar0, _ = _k2(v_min=0.0)
    F = _F_egik()
    ls, lm = local_stock(STOCK, F), local_mesh(_ag("k2"), F)
    z_bottom = max(ls.zmin, float(lm.bbox()[0][2]))
    ref = rough(lm, ls, _flat(), _ek_a_raster(ls, _cut()), AP, z_bottom, 0.0)
    tp = yollar0[1]
    assert len(tp.moves) == len(ref.moves)
    for m, mr in zip(tp.moves, ref.moves, strict=True):
        assert m.type is mr.type
        np.testing.assert_allclose(m.end, mr.end, atol=1e-9)
    yollar, _ = _k2()
    say = sum(1 for m in yollar[1].moves if m.type is MoveType.LINEAR)
    say0 = sum(1 for m in tp.moves if m.type is MoveType.LINEAR)
    assert say < say0


# ---------------------------------------------------------------- K9 (kaba)


def _basit_ag() -> TriMesh:
    V = np.array([[0.0, 0.0, 10.0], [60.0, 0.0, 10.0], [60.0, 40.0, 10.0], [0.0, 40.0, 10.0]])
    return TriMesh(V=V, T=np.array([[0, 1, 2], [0, 2, 3]]))


def test_k9_bos_yonelim_listesi():
    with pytest.raises(CamError):
        rough5(_basit_ag(), STOCK, _flat(), [], _cut())


def test_k9_desteklenmeyen_takim():
    matkap = Tool(id=3, name="matkap", kind=ToolKind.DRILL, D=6.0, flute_length=40.0)
    with pytest.raises(CamError):
        rough5(_basit_ag(), STOCK, matkap, [_F_ust()], _cut())


def test_k9_max_tilt_asimi():
    """45° eğik yönelim, varsayılan max_tilt = 30° → CamError.

    K2 aynı yönelimi max_tilt = 50 ile kullanır.
    """
    with pytest.raises(CamError):
        rough5(_basit_ag(), STOCK, _flat(), [_F_ust(), _F_egik()], _cut())


@pytest.mark.parametrize("alan", ["a_p", "stepover", "feed"])
def test_k9_roughcut_pozitif_olmali(alan):
    kw = dict(a_p=AP, stepover=AE, feed=FEED, plunge_feed=PLUNGE, rpm=RPM)
    kw[alan] = 0.0
    with pytest.raises(CamError):
        RoughCut(**kw)


def test_k9_roughcut_negatif_pay():
    with pytest.raises(CamError):
        dataclasses.replace(_cut(), allowance=-0.1)
