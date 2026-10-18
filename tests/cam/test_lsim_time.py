"""SPEC 22 K10 — torna hareket süresi (G95, G96 + G50, G0, ivme, takım değişimi).

Testler SPEC 22 "Süre tahmini" bölümünden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 22; Fanuc 0i-TF G96/G50; Smid, CNC Programming Handbook):
- G95 sabit devir: v = F·n/60 → t = 60·L/(F·n); ayrıca v ≤ min_i(rapid_i/|u_i|)/60
  (X = rapid[0], Z = rapid[2]).
- G96: n(x) = min(1000·Vc/(2π|x|), rpm), x = 0 → rpm; t = ∫ 60 ds/(F·n(x(s))); sınırsız bölgede integrand
  60·2π|x|/(1000·Vc·F), sınırlı bölgede 60/(F·rpm); geçiş |x| = x* = 1000·Vc/(2π·rpm).
- G0 ve accel: SPEC 05 (v = min_i(rapid_i/|u_i|)/60; L ≥ v²/a → t = L/v + v/a, aksi 2√(L/a)).
  G96'da accel ile eşdeğer sabit hız v_eş = L/t_G96.
- G94 (PER_MIN): SPEC 05 kuralı t = 60·L/F.
- Takım değişimi, cumulative_time, op_times: SPEC 05 ile aynı.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CylinderStock, FeedMode, Move, MoveType
from cam.sim import Machine, lathe_move_time, simulate_lathe
from tests.cam.lsimref import G0, G1, lpath, turn_tool

MAK = Machine(rapid=(6000.0, 100.0, 4000.0))
VC, NMAX = 100.0, 3000.0  # m/dk, dev/dk
XS = 1000.0 * VC / (2 * math.pi * NMAX)  # x* ≈ 5.305 mm
F = 0.2  # mm/dev


def _p(x: float, z: float) -> tuple[float, float, float]:
    return (x, 0.0, z)


def _t(p0, move: Move, css=None, rpm=1000.0, machine: Machine = MAK, feed_mode=FeedMode.PER_REV) -> float:
    path = lpath(turn_tool(), (p0[0], p0[2]), [move], rpm=rpm, css=css, feed_mode=feed_mode)
    return float(lathe_move_time(p0, move.end, move, path, machine))


def _k_sinirsiz() -> float:
    """G96 sınırsız bölge katsayısı: dt = k·|x|·ds, k = 60·2π/(1000·Vc·F)."""
    return 60 * 2 * math.pi / (1000 * VC * F)


def _k_sinirli() -> float:
    """G96 sınırlı bölge (devir = rpm): dt = 60/(F·rpm)·ds."""
    return 60 / (F * NMAX)


# ------------------------------------------------------------------ G95 sabit devir


def test_K10_g95_sabit_devir():
    p0 = _p(20.0, 3.0)
    m = G1(12.0, -18.0, F=0.25)
    L = math.hypot(8.0, 21.0)
    assert _t(p0, m, rpm=1200.0) == pytest.approx(60 * L / (0.25 * 1200.0), rel=1e-12)


def test_K10_g95_eksen_hizi_siniri():
    """F·n = 10·3000 = 30000 mm/dk > rapid_z = 4000: t = L/(4000/60)."""
    p0 = _p(10.0, 0.0)
    m = G1(10.0, -50.0, F=10.0)
    assert _t(p0, m, rpm=3000.0) == pytest.approx(50.0 / (4000.0 / 60), rel=1e-12)


def test_K10_g95_yay():
    """Yarım daire, merkez (x = 8, z = 0), R = 4: L = 4π, t = 60·L/(F·n)."""
    p0 = _p(8.0, 4.0)
    m = Move(MoveType.ARC_CCW, (8.0, 0.0, -4.0), F, center=(8.0, 0.0))
    assert _t(p0, m, rpm=800.0) == pytest.approx(60 * 4 * math.pi / (F * 800.0), rel=1e-12)


def test_K10_g94_dakika_basina():
    p0 = _p(20.0, 0.0)
    m = G1(20.0, -30.0, F=150.0)
    assert _t(p0, m, feed_mode=FeedMode.PER_MIN) == pytest.approx(60 * 30.0 / 150.0, rel=1e-12)


# ------------------------------------------------------------------ G96 sabit kesme hızı


def test_K10_g96_alin_pasosu_x_star_gecisi():
    """x: 30 → 0 (z sabit): ∫ = k·(30² − x*²)/2 + 60/(F·rpm)·x*."""
    p0 = _p(30.0, -2.0)
    m = G1(0.0, -2.0, F=F)
    beklenen = _k_sinirsiz() * (30.0**2 - XS**2) / 2 + _k_sinirli() * XS
    assert _t(p0, m, css=VC, rpm=NMAX) == pytest.approx(beklenen, rel=1e-12)


def test_K10_g96_eksen_gecen_pasa():
    """x: 10 → −4 (eksenin öbür tarafı): |x| > x* yalnız [x*, 10]'da."""
    p0 = _p(10.0, 0.0)
    m = G1(-4.0, 0.0, F=F)
    beklenen = _k_sinirsiz() * (100.0 - XS**2) / 2 + _k_sinirli() * (XS + 4.0)
    assert _t(p0, m, css=VC, rpm=NMAX) == pytest.approx(beklenen, rel=1e-12)


def test_K10_g96_egik_dogru():
    """(x, z): (20, 0) → (2, −24); ds = (L/|Δx|)·dx; x* ∈ (2, 20)."""
    p0 = _p(20.0, 0.0)
    m = G1(2.0, -24.0, F=F)
    L = math.hypot(18.0, 24.0)
    olcek = L / 18.0
    beklenen = olcek * (_k_sinirsiz() * (400.0 - XS**2) / 2 + _k_sinirli() * (XS - 2.0))
    assert _t(p0, m, css=VC, rpm=NMAX) == pytest.approx(beklenen, rel=1e-12)


def test_K10_g96_tamamen_sinirsiz_dogru():
    p0 = _p(12.0, 0.0)
    m = G1(18.0, -8.0, F=F)
    L = 10.0
    ort = (12.0 + 18.0) / 2  # ∫|x| ds = L·x̄ (doğrusal x)
    assert _t(p0, m, css=VC, rpm=NMAX) == pytest.approx(_k_sinirsiz() * L * ort, rel=1e-12)


def test_K10_g96_yay_x_star_gecisi():
    """Merkez (0, 0), R = 10: (x=0, z=10) → (x=10, z=0) G3; x = 10·sin θ; sin θ* = x*/10.
    t = 60/(F·rpm)·R·θ* + k·R·∫_{θ*}^{π/2} 10 sin θ dθ = … + k·100·cos θ*."""
    p0 = _p(0.0, 10.0)
    m = Move(MoveType.ARC_CCW, (10.0, 0.0, 0.0), F, center=(0.0, 0.0))
    th = math.asin(XS / 10.0)
    beklenen = _k_sinirli() * 10.0 * th + _k_sinirsiz() * 100.0 * math.cos(th)
    assert _t(p0, m, css=VC, rpm=NMAX) == pytest.approx(beklenen, rel=1e-12)


def test_K10_g96_yay_tepe_noktasi():
    """Merkez (x=8, z=0), R = 4, yarım daire (tepe x = 12 dahil): ∫|x| ds = 4·(8π + 8)."""
    p0 = _p(8.0, 4.0)
    m = Move(MoveType.ARC_CCW, (8.0, 0.0, -4.0), F, center=(8.0, 0.0))
    assert _t(p0, m, css=VC, rpm=NMAX) == pytest.approx(_k_sinirsiz() * 4 * (8 * math.pi + 8), rel=1e-12)


def test_K10_g96_yay_sinirli_bolgede():
    """Merkez (x=2, z=0), R = 2, G3 (x=2, z=2) → (x=2, z=−2) tepe x = 4 < x*: t = 60·2π/(F·rpm)."""
    p0 = _p(2.0, 2.0)
    m = Move(MoveType.ARC_CCW, (2.0, 0.0, -2.0), F, center=(2.0, 0.0))
    assert _t(p0, m, css=VC, rpm=NMAX) == pytest.approx(_k_sinirli() * 2 * math.pi, rel=1e-12)


def test_K10_x_star_sinirinda_iki_dal_esit():
    """|x| = x*'da 60·2π·x*/(1000·Vc·F) = 60/(F·rpm): x = x* boyunca z hareketi her iki formülle aynı."""
    assert _k_sinirsiz() * XS == pytest.approx(_k_sinirli(), rel=1e-14)
    p0 = _p(XS, 0.0)
    m = G1(XS, -10.0, F=F)
    assert _t(p0, m, css=VC, rpm=NMAX) == pytest.approx(10.0 * _k_sinirli(), rel=1e-12)
    ust = _t(_p(XS * (1 + 1e-9), 0.0), G1(XS * (1 + 1e-9), -10.0, F=F), css=VC, rpm=NMAX)
    alt = _t(_p(XS * (1 - 1e-9), 0.0), G1(XS * (1 - 1e-9), -10.0, F=F), css=VC, rpm=NMAX)
    assert ust == pytest.approx(alt, rel=1e-8)


def test_K10_g96_eksende_devir_siniri():
    """x = 0 boyunca z hareketi: n = rpm."""
    m = G1(0.0, -6.0, F=F)
    assert _t(_p(0.0, 0.0), m, css=VC, rpm=NMAX) == pytest.approx(6.0 * _k_sinirli(), rel=1e-12)


# ------------------------------------------------------------------ G0 ve ivme


def test_K10_g0_eksen_hizlari():
    """u = (0.6, ·, 0.8): v = min(6000/0.6, 4000/0.8)/60 = 5000/60 mm/s; L = 50 → 0.6 s.
    Y hızı kullanılmaz."""
    m = G0(40.0, 45.0)
    assert _t(_p(10.0, 5.0), m) == pytest.approx(0.6, rel=1e-12)


def test_K10_g0_ivme_trapez_ve_ucgen():
    a = 500.0
    mak = Machine(rapid=(6000.0, 100.0, 4000.0), accel=a)
    v = 5000.0 / 60
    assert _t(_p(10.0, 5.0), G0(40.0, 45.0), machine=mak) == pytest.approx(50.0 / v + v / a, rel=1e-12)
    # kısa hareket: L = 5 < v²/a → üçgen
    assert _t(_p(10.0, 5.0), G0(13.0, 9.0), machine=mak) == pytest.approx(2 * math.sqrt(5.0 / a), rel=1e-12)


def test_K10_g95_ivme():
    a = 50.0
    mak = Machine(rapid=(6000.0, 100.0, 4000.0), accel=a)
    v = F * 1000.0 / 60  # 3.333 mm/s, v²/a = 0.222 mm
    assert _t(_p(20.0, 0.0), G1(20.0, -30.0), machine=mak) == pytest.approx(30.0 / v + v / a, rel=1e-12)
    assert _t(_p(20.0, 0.0), G1(20.0, -0.1), machine=mak) == pytest.approx(2 * math.sqrt(0.1 / a), rel=1e-12)


def test_K10_g96_ivme_esdeger_hiz():
    a = 50.0
    mak = Machine(rapid=(6000.0, 100.0, 4000.0), accel=a)
    p0, m = _p(30.0, -2.0), G1(0.0, -2.0, F=F)
    t96 = _k_sinirsiz() * (30.0**2 - XS**2) / 2 + _k_sinirli() * XS
    v_es = 30.0 / t96
    assert 30.0 >= v_es**2 / a
    assert _t(p0, m, css=VC, rpm=NMAX, machine=mak) == pytest.approx(t96 + v_es / a, rel=1e-12)


def test_K10_sifir_boy():
    assert _t(_p(5.0, 1.0), G1(5.0, 1.0)) == 0.0
    assert _t(_p(5.0, 1.0), G0(5.0, 1.0)) == 0.0
    assert _t(_p(5.0, 1.0), G1(5.0, 1.0), css=VC, rpm=NMAX) == 0.0


# ------------------------------------------------------------------ program süresi


STOK = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0)


def _iki_yol(id2: int):
    """Havada (malzemeye değmeden) iki yol; bağlantı G0 (25, 5) → (30, 8)."""
    y1 = lpath(turn_tool(id=1), (25.0, 5.0), [G0(25.0, 2.0), G1(22.0, 2.0), G1(22.0, -10.0), G0(25.0, 5.0)])
    y2 = lpath(turn_tool(id=id2), (30.0, 8.0), [G1(30.0, -20.0), G0(30.0, 8.0)])
    return y1, y2


def _g0(x0, z0, x1, z1) -> float:
    dx, dz = abs(x1 - x0), abs(z1 - z0)
    L = math.hypot(dx, dz)
    return L / (min(6000.0 / (dx / L) if dx else math.inf, 4000.0 / (dz / L) if dz else math.inf) / 60)


def _g1(L: float) -> float:
    return 60 * L / (F * 1000.0)


def test_K10_takim_degisimi_ve_kumulatif():
    y1, y2 = _iki_yol(id2=2)
    mak = Machine(rapid=(6000.0, 100.0, 4000.0), tool_change=7.0)
    sonuc = simulate_lathe([y1, y2], STOK, cell=0.5, machine=mak)
    t1 = _g0(25, 5, 25, 2) + _g1(3.0) + _g1(12.0) + _g0(22, -10, 25, 5)
    bag = _g0(25, 5, 30, 8)
    t2 = 7.0 + bag + _g1(28.0) + _g0(30, -20, 30, 8)
    assert len(sonuc.steps) == 7
    s = sonuc.steps
    assert [st.link for st in s] == [False] * 4 + [True, False, False]
    assert [st.op for st in s] == [0, 0, 0, 0, 1, 1, 1]
    assert [st.k for st in s] == list(range(1, 8))
    assert s[4].t0 == pytest.approx(t1 + 7.0, rel=1e-12)  # takım değişimi bağlantıdan önce
    assert s[4].duration == pytest.approx(bag, rel=1e-12)
    assert sonuc.op_times == [pytest.approx(t1, rel=1e-12), pytest.approx(t2, rel=1e-12)]
    assert sonuc.total_time == pytest.approx(t1 + t2, rel=1e-12)
    ct = sonuc.cumulative_time()
    assert ct.shape == (8,) and ct[0] == 0.0
    assert np.all(np.diff(ct) >= 0)
    assert ct[-1] == pytest.approx(sonuc.total_time, rel=1e-12)
    assert sum(sonuc.op_times) == pytest.approx(sonuc.total_time, rel=1e-12)
    np.testing.assert_allclose(sonuc.points()[0], (25.0, 0.0, 5.0))


def test_K10_ayni_takimda_degisim_yok():
    y1, y2 = _iki_yol(id2=1)
    mak = Machine(rapid=(6000.0, 100.0, 4000.0), tool_change=7.0)
    sonuc = simulate_lathe([y1, y2], STOK, cell=0.5, machine=mak)
    t1 = _g0(25, 5, 25, 2) + _g1(3.0) + _g1(12.0) + _g0(22, -10, 25, 5)
    t2 = _g0(25, 5, 30, 8) + _g1(28.0) + _g0(30, -20, 30, 8)
    assert sonuc.total_time == pytest.approx(t1 + t2, rel=1e-12)


def test_K10_adim_sureleri_lathe_move_time_ile():
    """Program içinde G96 adımları lathe_move_time ile aynı; MRR = ΔV/t."""
    y = lpath(turn_tool(), (30.0, -2.0), [G1(0.0, -2.0), G0(30.0, 5.0)], rpm=NMAX, css=VC)
    sonuc = simulate_lathe([y], STOK, cell=0.5, machine=MAK)
    t0 = _k_sinirsiz() * (30.0**2 - XS**2) / 2 + _k_sinirli() * XS
    assert sonuc.steps[0].duration == pytest.approx(t0, rel=1e-12)
    for st in sonuc.steps:
        if st.duration > 0:
            assert st.mrr == pytest.approx(st.removed / st.duration, rel=1e-12)
