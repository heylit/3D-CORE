"""SPEC 52 K6, K7 — helisel diş frezeleme: yol üretimi ve simüle yüzey (dönel takım zarfı).

Testler SPEC 52 "Diş frezeleme (senkronsuz helis)" ve "Arayüz" bölümlerinden yazıldı;
cam.sim ve cam.thread_mill
kodu okunmadı. Zarf referansı: tests/cam/threadref.py `mill_envelope_inner` (yoldaki her kesme hareketi yoğun
örneklenir: yayda 0.05°, sonra en iyi konum çevresinde ince örnekleme).

Kaynaklar (SPEC 52):
- Helis c(φ) = (ρ_h cos φ, ρ_h sin φ, z₀ + P·φ/2π): her turda ΔZ = P; z, φ (CCW) ile artar (sağ helis).
- İç diş ρ_h = r_iç_diş − D/2 + h, r_iç_diş = D₁/2, h = 5/8·H (SPEC 20 iso_thread_depth iç) → ρ_h = d/2 − D/2.
  Dış diş ρ_h = r_dış_diş + D/2 − h, r_dış_diş = d/2, h = 17/24·H.
- Takım: tek profilli, uç açısı 60°,
  D fiziksel uç çapı. K6'da burun yarıçapı r_ε = H/8: ρ_h formülü ucu D/2'ye
  koyar; r_ε = H/8 burunlu V'nin sanal sivri tepesi D/2 + H/8'de, yani ISO temel üçgenin tepesinde olur
  (sivri takımda d₂ 0.2·P kayardı). Helis bozulması (bağımsız zarf hesabı, Δz = 0.002, medyan) d₂'yi D = 10'da
  +0.023·P kaydırır; bu yüzden ISO d₂ toleransı 0.03·P (SPEC'teki 0.01·P D = 10 ile geometrik olarak
  sağlanamaz; koordinatöre bildirildi, karar bekleniyor).
- Tırmanma (M3 iş mili): iç dişte takım delik çevresinde CCW (G3), dış dişte CW (G2); geleneksel tersi.
  Sağ helis korunur: CCW yayda ΔZ > 0, CW yayda ΔZ < 0. İki yön aynı yüzeyi verir.
- Giriş yayı delik duvarına teğet: giriş yayının bitişi helis başlangıcı; iki çember bu noktada teğet
  (merkezler ve nokta doğrudaş).
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from cam.model import CylinderStock, FeedMode, Frame, MoveType, Plane
from cam.sim import PolarMap, simulate_thread, thread_measure
from cam.thread_mill import ThreadMillForm, thread_mill
from tests.cam.threadref import D1_iso, H_iso, d2_iso, mill_envelope_inner

BIRIM = Frame((0.0, 0.0, 0.0), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
ARCS = (MoveType.ARC_CW, MoveType.ARC_CCW)

d, P = 16.0, 1.5
D_K6 = 10.0
UZUNLUK = 10.5  # 7 tur
DZ = 0.05
DTH = 0.1  # Δφ ≤ Δθ/2 = 0.05° (SPEC 52) → yoğun referansla 1e-6


def _form(D: float = D_K6, nose_r: float | None = None) -> ThreadMillForm:
    return ThreadMillForm(D, 60.0, H_iso(P) / 8 if nose_r is None else nose_r)


def _helis_yaylari(tp, rho: float, tol: float = 1e-9):
    """Merkezi delik ekseninde (0, 0) ve yarıçapı ρ_h olan yaylar: [(önceki nokta, hareket)]."""
    out = []
    p0 = np.array(tp.start, dtype=float)
    for m in tp.moves:
        if m.type in ARCS and math.hypot(*m.center) <= tol and abs(math.hypot(p0[0], p0[1]) - rho) <= tol:
            out.append((p0, m))
        p0 = np.array(m.end, dtype=float)
    return out


def _supurme(p0, m) -> float:
    a0 = math.atan2(p0[1] - m.center[1], p0[0] - m.center[0])
    a1 = math.atan2(m.end[1] - m.center[1], m.end[0] - m.center[0])
    if m.type is MoveType.ARC_CCW:
        dd = (a1 - a0) % (2 * math.pi)
        return dd if dd > 1e-12 else 2 * math.pi
    dd = (a0 - a1) % (2 * math.pi)
    return -(dd if dd > 1e-12 else 2 * math.pi)


def _teget(m, c: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Yayın T noktasındaki birim hareket yönü (CCW: (T − c) 90° sola döndürülmüş)."""
    v = T - c
    t = np.array([-v[1], v[0]]) if m.type is MoveType.ARC_CCW else np.array([v[1], -v[0]])
    return t / np.linalg.norm(t)


def _rho_ic(d_: float, D_: float) -> float:
    """ρ_h = D₁/2 − D/2 + 5/8·H."""
    return D1_iso(d_, P) / 2 - D_ / 2 + 5 / 8 * H_iso(P)


def _rho_dis(d_: float, D_: float) -> float:
    """ρ_h = d/2 + D/2 − 17/24·H."""
    return d_ / 2 + D_ / 2 - 17 / 24 * H_iso(P)


# ------------------------------------------------------------------ ThreadMillForm


def test_K7_form_varsayilanlari():
    f = ThreadMillForm(10.0)
    assert (f.D, f.eps_deg, f.nose_r, f.flute_length) == (10.0, 60.0, 0.0, 20.0)


# ------------------------------------------------------------------ K7 yol üretimi


@pytest.mark.parametrize("side, climb", [("ic", True), ("ic", False), ("dis", True), ("dis", False)])
def test_K7_helis_yaricapi_ve_tur_basina_P(side, climb):
    D_ = 10.0
    tp = thread_mill(BIRIM, d, P, UZUNLUK, _form(D_, 0.0), side=side, climb=climb)
    tp.validate()
    assert tp.plane is Plane.XY and tp.feed_mode is FeedMode.PER_MIN and tp.rpm == 3000.0
    assert all(m.feed == 300.0 for m in tp.moves if m.type is not MoveType.RAPID)
    rho = _rho_ic(d, D_) if side == "ic" else _rho_dis(d, D_)
    if side == "ic":
        assert rho == pytest.approx(d / 2 - D_ / 2, abs=1e-12)
    yaylar = _helis_yaylari(tp, rho, tol=1e-12)
    assert yaylar, "ρ_h yarıçaplı helis yayı yok"
    toplam = 0.0
    for p0, m in yaylar:
        assert math.hypot(m.end[0], m.end[1]) == pytest.approx(rho, abs=1e-12)
        phi = _supurme(p0, m)
        assert m.end[2] - p0[2] == pytest.approx(
            P * phi / (2 * math.pi), abs=1e-12
        )  # sağ helis, tur başına P
        toplam += abs(phi)
    assert toplam / (2 * math.pi) * P >= UZUNLUK - 1e-9
    beklenen_ccw = climb if side == "ic" else not climb
    assert all((m.type is MoveType.ARC_CCW) == beklenen_ccw for _p, m in yaylar)


@pytest.mark.parametrize("side", ["ic", "dis"])
def test_K7_giris_yayi_teget(side):
    D_ = 10.0
    tp = thread_mill(BIRIM, d, P, UZUNLUK, _form(D_, 0.0), side=side)
    rho = _rho_ic(d, D_) if side == "ic" else _rho_dis(d, D_)
    yaylar = _helis_yaylari(tp, rho, tol=1e-12)
    ilk = tp.moves.index(yaylar[0][1])
    assert ilk >= 1
    g = tp.moves[ilk - 1]
    assert g.type in ARCS, "helisten önce giriş yayı yok"
    T = np.array(g.end[:2])  # giriş yayının sonu = helis başı
    assert math.hypot(*T) == pytest.approx(rho, abs=1e-12)
    c = np.array(g.center, dtype=float)
    capraz = c[0] * T[1] - c[1] * T[0]  # O, c, T doğrudaş → çemberler T'de teğet
    assert capraz == pytest.approx(0.0, abs=1e-12)
    t_giris = _teget(g, c, T)
    t_helis = _teget(yaylar[0][1], np.zeros(2), T)
    assert float(t_giris @ t_helis) == pytest.approx(1.0, abs=1e-9)  # hareket T'den aynı yönde sürer


# ------------------------------------------------------------------ K6 simüle yüzey


def _harita(tp) -> PolarMap:
    """Yolun bütün z'sini kapsayan Ø40 blokta D₁ ön delik."""
    z = tp.points()[:, 2]
    stok = CylinderStock(
        D=40.0, zmin=math.floor(z.min()) - 2.0, zmax=math.ceil(z.max()) + 2.0, d=D1_iso(d, P)
    )
    return PolarMap.from_stock(stok, dtheta_deg=DTH, dz=DZ)


@functools.cache
def _k6(climb: bool):
    # fixture değil: simülasyon test gövdesinde çağrılsın (uygulanmamış kod "uygulanmamış" sayılsın)
    tp = thread_mill(BIRIM, d, P, UZUNLUK, _form(), side="ic", climb=climb)
    return tp, simulate_thread([tp], _harita(tp), frame=BIRIM)


def _pencere(tp, m: PolarMap) -> np.ndarray:
    """Helis yaylarının z aralığının iki ucundan 2P içerideki hücreler (giriş / çıkış etkisi dışında)."""
    zs = [p0[2] for p0, _m in _helis_yaylari(tp, _rho_ic(d, D_K6))]
    zs += [m_.end[2] for _p, m_ in _helis_yaylari(tp, _rho_ic(d, D_K6))]
    a, b = min(zs) + 2 * P, max(zs) - 2 * P
    assert b - a >= 2 * P
    z = m.centers()
    return (z > a) & (z < b)


@pytest.mark.slow
def test_K6_zarf_referansi():
    tp, m = _k6(True)
    w = _pencere(tp, m)
    js = np.arange(0, m.n_theta, 150)  # 24 açı
    ref = mill_envelope_inner(tp, m.thetas()[js], m.centers()[w], D_K6, 60.0, H_iso(P) / 8, D1_iso(d, P) / 2)
    np.testing.assert_allclose(np.asarray(m.r_in)[np.ix_(js, np.where(w)[0])], ref, rtol=0, atol=1e-6)


@pytest.mark.slow
def test_K6_bogur_capi_iso():
    tp, m = _k6(True)
    w = _pencere(tp, m)
    z = m.centers()[w]
    s = thread_measure(m, "ic", (float(z.min()), float(z.max())))
    assert s.d2 == pytest.approx(d2_iso(d, P), abs=0.03 * P)
    assert s.d_root == pytest.approx(D1_iso(d, P), abs=DZ)


@pytest.mark.slow
def test_K6_tirmanma_geleneksel_ayni_yuzey():
    tp, a = _k6(True)
    _tp2, b = _k6(False)
    w = _pencere(tp, a)
    np.testing.assert_allclose(np.asarray(b.r_in)[:, w], np.asarray(a.r_in)[:, w], rtol=0, atol=2e-6)
