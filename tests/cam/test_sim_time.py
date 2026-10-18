"""SPEC 05 K9 — işleme süresi tahmini.

Testler SPEC 05 "Süre tahmini" bölümünden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 05; GRBL planlayıcısı, trapez profil):
- Kesme: v = F/60 [mm/s], ayrıca v ≤ min_i(rapid_i/|u_i|)/60; accel yoksa t = L/v (G1: t = 60·L/F).
- G0: v = min_i(rapid_i/|u_i|)/60 (u birim yön).
- Yay: L = √((rΔθ)² + Δz²), v ≤ min(rapid_x, rapid_y)/60 ve accel varsa v ≤ √(a·r).
- accel = a, tam duruş: L ≥ v²/a → t = L/v + v/a; değilse t = 2√(L/a). L = v²/a'da iki dal eşit.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import Move, MoveType, Plane, Stock, Tool, ToolKind
from cam.sim import Machine, move_time, simulate
from tests.cam.simref import G0, G1, path


def _m() -> Machine:
    return Machine(rapid=(6000.0, 6000.0, 1200.0))


XY = Plane.XY


def _t(p0, move, machine: Machine | None = None) -> float:
    machine = _m() if machine is None else machine
    return float(move_time(p0, move.end, move, XY, machine))


# ------------------------------------------------------------------ hızsız ivme (accel = None)


def test_g1_60L_bolu_F():
    p0 = (1.0, 2.0, 3.0)
    m = G1(13.0, -7.0, -2.5, F=750.0)
    L = math.dist(p0, m.end)
    assert _t(p0, m) == pytest.approx(60 * L / 750.0, rel=1e-12)


def test_g1_eksen_hizi_siniri():
    """Çok büyük F ile düşey G1: v ≤ rapid_z/60 = 20 mm/s."""
    p0 = (0.0, 0.0, 0.0)
    m = G1(0.0, 0.0, -30.0, F=50_000.0)
    assert _t(p0, m) == pytest.approx(30.0 / 20.0, rel=1e-12)


def test_g0_xy_kosegen():
    """u = (0.6, 0.8, 0): v = min(6000/0.6, 6000/0.8)/60 = 125 mm/s; L = 50 → 0.4 s."""
    assert _t((0.0, 0.0, 5.0), G0(30.0, 40.0, 5.0)) == pytest.approx(0.4, rel=1e-12)


def test_g0_z_ekseni():
    assert _t((0.0, 0.0, 5.0), G0(0.0, 0.0, -25.0)) == pytest.approx(30.0 / 20.0, rel=1e-12)


def test_g0_uzay_dogrusu():
    p0 = (0.0, 0.0, 0.0)
    m = G0(30.0, 40.0, -20.0)
    L = math.sqrt(30**2 + 40**2 + 20**2)
    u = np.array([30.0, 40.0, -20.0]) / L
    v = min(6000.0 / abs(u[0]), 6000.0 / abs(u[1]), 1200.0 / abs(u[2])) / 60
    assert _t(p0, m) == pytest.approx(L / v, rel=1e-12)
    # Z sınırı burada belirleyici: 1200/(20/L) < 6000/(40/L)
    assert v == pytest.approx(1200.0 * L / 20.0 / 60.0, rel=1e-12)


def test_sifir_boy():
    p0 = (3.0, 4.0, 5.0)
    assert _t(p0, G1(3.0, 4.0, 5.0)) == 0.0
    assert _t(p0, G0(3.0, 4.0, 5.0)) == 0.0
    assert _t(p0, G0(3.0, 4.0, 5.0), Machine(accel=500.0)) == 0.0


def test_yay_suresi():
    """Yarım daire r = 2: L = 2π; F = 3000 → t = 60·L/F."""
    p0 = (2.0, 0.0, 0.0)
    m = Move(MoveType.ARC_CCW, (-2.0, 0.0, 0.0), 3000.0, center=(0.0, 0.0))
    assert _t(p0, m) == pytest.approx(60 * 2 * math.pi / 3000.0, rel=1e-12)


def test_helis_suresi():
    """Tam tur helis r = 5, Δz = −3: L = √((10π)² + 9)."""
    p0 = (5.0, 0.0, 0.0)
    m = Move(MoveType.ARC_CW, (5.0, 0.0, -3.0), 1200.0, center=(0.0, 0.0))
    L = math.hypot(10 * math.pi, 3.0)
    assert _t(p0, m) == pytest.approx(60 * L / 1200.0, rel=1e-12)


def test_yay_eksen_hizi_siniri():
    """Yayda v ≤ min(rapid_x, rapid_y)/60 = 100 mm/s (F = 9000 → 150 mm/s istenir)."""
    p0 = (2.0, 0.0, 0.0)
    m = Move(MoveType.ARC_CCW, (-2.0, 0.0, 0.0), 9000.0, center=(0.0, 0.0))
    assert _t(p0, m) == pytest.approx(2 * math.pi / 100.0, rel=1e-12)


# ------------------------------------------------------------------ ivme (trapez / üçgen)

A_ACC = 500.0


def _ma() -> Machine:
    return Machine(rapid=(6000.0, 6000.0, 1200.0), accel=A_ACC)


def test_trapez():
    """F = 3000 → v = 50 mm/s, v²/a = 5 mm; L = 20 ≥ 5 → t = L/v + v/a = 0.5 s."""
    assert _t((0.0, 0.0, 0.0), G1(20.0, 0.0, 0.0, F=3000.0), _ma()) == pytest.approx(0.5, rel=1e-12)


def test_ucgen():
    """L = 2 < 5 → t = 2√(L/a)."""
    t = _t((0.0, 0.0, 0.0), G1(0.0, 2.0, 0.0, F=3000.0), _ma())
    assert t == pytest.approx(2 * math.sqrt(2.0 / A_ACC), rel=1e-12)


def test_dal_siniri_esit():
    """L = v²/a = 5: trapez 5/50 + 50/500 = 0.2, üçgen 2√(5/500) = 0.2."""
    t = _t((0.0, 0.0, 0.0), G1(3.0, 4.0, 0.0, F=3000.0), _ma())
    assert t == pytest.approx(0.2, rel=1e-12)
    assert 5 / 50 + 50 / 500 == pytest.approx(2 * math.sqrt(5 / 500), rel=1e-12)


def test_g0_trapez():
    """G0 XY köşegen v = 125 mm/s, v²/a = 31.25; L = 50 → t = 50/125 + 125/500 = 0.65."""
    assert _t((0.0, 0.0, 5.0), G0(30.0, 40.0, 5.0), _ma()) == pytest.approx(0.65, rel=1e-12)


def test_yay_merkezcil_siniri():
    """r = 2, F = 6000 → 100 mm/s istenir; √(a·r) = √1000 sınırlar. L = 2π ≥ v²/a = 2 → trapez."""
    p0 = (2.0, 0.0, 0.0)
    m = Move(MoveType.ARC_CCW, (-2.0, 0.0, 0.0), 6000.0, center=(0.0, 0.0))
    v = math.sqrt(A_ACC * 2.0)
    L = 2 * math.pi
    assert _t(p0, m, _ma()) == pytest.approx(L / v + v / A_ACC, rel=1e-12)


# ------------------------------------------------------------------ program süresi, takım değişimi

STOK = Stock(0.0, 0.0, -10.0, 50.0, 50.0, 0.0)


def _takim(id: int) -> Tool:
    return Tool(id, f"T{id}", ToolKind.FLAT, 6.0, 20.0)


def _program():
    """Havada (z = 10, stok üstü 0) üç yol: T1, T2, T2. Yol 0 → 1 arasında bağlantı, 1 → 2 arasında yok."""
    y0 = path(_takim(1), (0.0, 0.0, 10.0), [G1(10.0, 0.0, 10.0, F=600.0), G0(10.0, 10.0, 10.0)], "a")
    y1 = path(_takim(2), (20.0, 10.0, 10.0), [G1(20.0, 20.0, 10.0, F=600.0)], "b")
    y2 = path(_takim(2), (20.0, 20.0, 10.0), [G1(30.0, 20.0, 10.0, F=1200.0)], "c")
    return [y0, y1, y2]


def test_takim_degisimi_ve_kumulatif():
    mak = Machine(tool_change=7.5)
    res = simulate(_program(), STOK, cell=1.0, machine=mak)
    # adımlar: k1 G1 (1 s), k2 G0 (10 mm / (5000/60)), k3 bağlantı G0 (10 mm X), k4 G1 (1 s), k5 G1 (0.5 s)
    assert [s.k for s in res.steps] == [1, 2, 3, 4, 5]
    assert [s.op for s in res.steps] == [0, 0, 1, 1, 2]
    assert [s.link for s in res.steps] == [False, False, True, False, False]
    assert res.steps[2].type is MoveType.RAPID
    d = [1.0, 10 / (5000 / 60), 10 / (5000 / 60), 1.0, 0.5]
    for s, beklenen in zip(res.steps, d, strict=True):
        assert s.duration == pytest.approx(beklenen, rel=1e-12)
    # takım değişimi yol 1'in ilk adımından (bağlantı) önce ve yol 1'e sayılır; yol 2 aynı takım
    assert res.steps[2].t0 == pytest.approx(d[0] + d[1] + 7.5, rel=1e-12)
    assert res.op_times == pytest.approx([d[0] + d[1], 7.5 + d[2] + d[3], d[4]], rel=1e-12)
    assert res.total_time == pytest.approx(sum(d) + 7.5, rel=1e-12)
    ct = res.cumulative_time()
    assert ct.shape == (6,)
    assert ct[0] == 0.0
    beklenen = np.cumsum([0.0, d[0], d[1], 7.5 + d[2], d[3], d[4]])
    np.testing.assert_allclose(ct, beklenen, rtol=1e-12)
    for s in res.steps:
        assert ct[s.k] == pytest.approx(s.t0 + s.duration, rel=1e-12)


def test_ilk_yolda_takim_degisimi_yok():
    res = simulate(_program()[:1], STOK, cell=1.0, machine=Machine(tool_change=7.5))
    assert res.steps[0].t0 == 0.0
    assert res.total_time == pytest.approx(1.0 + 10 / (5000 / 60), rel=1e-12)


def test_adim_suresi_move_time_ile_ayni():
    mak = Machine(rapid=(6000.0, 6000.0, 1200.0), accel=800.0, tool_change=3.0)
    prog = _program()
    res = simulate(prog, STOK, cell=1.0, machine=mak)
    pts = res.points()
    for s in res.steps:
        m = Move(s.type, s.end, s.feed, s.center)
        assert s.duration == pytest.approx(move_time(tuple(pts[s.k - 1]), s.end, m, XY, mak), rel=1e-12)
        np.testing.assert_allclose(pts[s.k], s.end, rtol=0, atol=0)
    ct = res.cumulative_time()
    assert np.all(np.diff(ct) >= 0)
    assert ct[-1] == pytest.approx(res.total_time, rel=1e-12)
    assert sum(res.op_times) == pytest.approx(res.total_time, rel=1e-12)


def test_varsayilan_makine():
    """machine=None → Machine(): rapid (5000, 5000, 3000), accel yok, takım değişimi 0."""
    m = Machine()
    assert m.rapid == (5000.0, 5000.0, 3000.0)
    assert m.accel is None
    assert m.tool_change == 0.0
    res = simulate(_program(), STOK, cell=1.0)
    assert res.total_time == pytest.approx(1.0 + 2 * 10 / (5000 / 60) + 1.0 + 0.5, rel=1e-12)


def test_mrr():
    """MRR_k = ΔV_k / t_k; t_k = 0 ise 0."""
    tool = Tool(1, "T1", ToolKind.FLAT, 6.0, 20.0)
    yol = path(tool, (-10.0, 25.0, -2.0), [G1(60.0, 25.0, -2.0, F=600.0), G1(60.0, 25.0, -2.0, F=600.0)])
    res = simulate([yol], STOK, cell=0.5)
    s1, s2 = res.steps
    assert s1.removed > 0
    assert s1.mrr == pytest.approx(s1.removed / s1.duration, rel=1e-12)
    assert s2.duration == 0.0 and s2.mrr == 0.0
