"""SPEC 59 — torna aşınması testleri (K5–K7, K9).

Testler yalnız specs/59-takim-omru.md'deki teori, arayüz ve örneklerden yazıldı; cam/omur.py gövdesi okunmadı.
Torna: r = |x| (yarıçap koordinatı). G97: Vc(r) = 2π r N / 1000, dt = ds / (f N). G96 (Vc₀, N_max):
r ≥ r* = 1000 Vc₀ / (2π N_max) iken Vc = Vc₀, altında n = N_max.
Kapalı formlar SPEC Teori'den; örnek sayılar (0.0075161336, 0.01580293, r* = 11.936621) SPEC'te ve
bu dosyadaki kapalı formla aynı.
"""

from __future__ import annotations

import math

import pytest

from cam.model import CamError
from cam.omur import turn_wear
from malzeme.model import Taylor
from tests.cam.omur_ref import (
    MODEL_HATASI,
    T_taylor,
    g97_alin_D,
    malzeme,
    torna_programi,
    torna_ucu,
)

KARBUR = {5: "karbur"}


def _tek(wear):
    assert len(wear) == 1
    return wear[0]


# ---------- K5 G97 alın tornalama ----------


def test_g97_face_closed_form():
    """N = 500, f = 0.2, R₀ = 50 → 0: kesme süresi 50 / (0.2 · 500) = 0.5 dk;
    D = (2π N / (1000 C))^m R₀^(m+1) / ((m+1) f N) = 0.0075161336 (C = 300, n = 0.25, m = 4)."""
    ops, res, loads = torna_programi([(torna_ucu(), 500.0, None, 0.2, [(50.0, 0.0), (0.0, 0.0)], 1.0)])
    w = _tek(turn_wear(ops, res, loads, malzeme(), KARBUR))
    assert w.tool_id == 5 and w.tool_material == "karbur"
    assert w.t_cut == pytest.approx(0.5, abs=1e-12)
    D = g97_alin_D(500.0, 0.2, 50.0)
    assert D == pytest.approx(0.0075161336, abs=1e-10)
    assert w.D == pytest.approx(D, abs=1e-9)
    # Tam sayı m: Gauss–Legendre kesin (SPEC: ≤ 1e-12 göreli)
    assert w.D == pytest.approx(D, rel=1e-12)
    assert w.Vc_max == pytest.approx(2 * math.pi * 50.0 * 500.0 / 1000.0, rel=1e-12)
    s = next(s for s in w.steps if s.D > 0)
    assert s.Vc_min == pytest.approx(0.0, abs=1e-9)
    assert s.Vc_max == pytest.approx(2 * math.pi * 50.0 * 500.0 / 1000.0, rel=1e-12)
    assert s.t == pytest.approx(0.5, abs=1e-12)


def test_g97_face_direction_and_negative_x():
    """r = |x|: dıştan içe, içten dışa ve x < 0 tarafında aynı D."""
    D = g97_alin_D(500.0, 0.2, 50.0)
    for noktalar in ([(50.0, 0.0), (0.0, 0.0)], [(0.0, 0.0), (50.0, 0.0)], [(-50.0, 0.0), (0.0, 0.0)]):
        ops, res, loads = torna_programi([(torna_ucu(), 500.0, None, 0.2, noktalar, 1.0)])
        assert _tek(turn_wear(ops, res, loads, malzeme(), KARBUR)).D == pytest.approx(D, rel=1e-12)


def test_g97_face_split_in_steps_same_D():
    """Alın yolu 50 → 20 → 0 iki adımda: toplam D aynı (Miner toplamsal)."""
    ops, res, loads = torna_programi(
        [(torna_ucu(), 500.0, None, 0.2, [(50.0, 0.0), (20.0, 0.0), (0.0, 0.0)], 1.0)]
    )
    w = _tek(turn_wear(ops, res, loads, malzeme(), KARBUR))
    assert w.D == pytest.approx(g97_alin_D(500.0, 0.2, 50.0), rel=1e-12)
    assert sum(s.D for s in w.steps) == pytest.approx(w.D, rel=1e-12)


def test_g97_longitudinal_constant_radius():
    """G97 boy tornalama r = 30 sabit: Vc = 2π 30 · 500 / 1000, t = 40 / (0.2 · 500) = 0.4 dk,
    D = t / T(Vc)."""
    ops, res, loads = torna_programi([(torna_ucu(), 500.0, None, 0.2, [(30.0, 0.0), (30.0, -40.0)], 1.0)])
    w = _tek(turn_wear(ops, res, loads, malzeme(), KARBUR))
    Vc = 2 * math.pi * 30.0 * 500.0 / 1000.0
    assert w.t_cut == pytest.approx(0.4, rel=1e-12)
    assert w.D == pytest.approx(0.4 / T_taylor(Vc), rel=1e-12)


# ---------- K6 G96 + devir sınırı ----------


def _g96_alin_D(Vc0: float, N_max: float, f: float, R0: float) -> tuple[float, float]:
    """SPEC Teori: D₁ (r* … R₀, Vc = Vc₀) + D₂ (0 … r*, n = N_max). Döner: (r*, D)."""
    r_ = 1000.0 * Vc0 / (2 * math.pi * N_max)
    D1 = (2 * math.pi * (R0**2 - r_**2) / (2 * 1000.0 * Vc0 * f)) / T_taylor(Vc0)
    D2 = g97_alin_D(N_max, f, r_)
    return r_, D1 + D2


def test_g96_face_with_speed_limit():
    """Vc₀ = 150, N_max = 2000, f = 0.2, R₀ = 50 → 0: r* = 11.936621, D = 0.01580293."""
    r_, D = _g96_alin_D(150.0, 2000.0, 0.2, 50.0)
    assert r_ == pytest.approx(11.936621, abs=1e-6)
    assert D == pytest.approx(0.01580293, abs=1e-8)
    ops, res, loads = torna_programi([(torna_ucu(), 2000.0, 150.0, 0.2, [(50.0, 0.0), (0.0, 0.0)], 1.0)])
    w = _tek(turn_wear(ops, res, loads, malzeme(), KARBUR))
    assert w.D == pytest.approx(D, abs=1e-9)
    assert w.Vc_max == pytest.approx(150.0, rel=1e-12)
    t = 2 * math.pi * (50.0**2 - r_**2) / (2 * 1000.0 * 150.0 * 0.2) + r_ / (0.2 * 2000.0)
    assert w.t_cut == pytest.approx(t, rel=1e-9)


def test_g96_face_above_r_star_only():
    """G96 alın 50 → 20 (tamamı r* üstünde): Vc = Vc₀ sabit → D = t / T(Vc₀),
    t = 2π (R₀² − r₁²) / (2·1000 Vc₀ f)."""
    ops, res, loads = torna_programi([(torna_ucu(), 2000.0, 150.0, 0.2, [(50.0, 0.0), (20.0, 0.0)], 1.0)])
    w = _tek(turn_wear(ops, res, loads, malzeme(), KARBUR))
    t = 2 * math.pi * (50.0**2 - 20.0**2) / (2 * 1000.0 * 150.0 * 0.2)
    assert w.D == pytest.approx(t / 16.0, rel=1e-9)
    s = next(s for s in w.steps if s.D > 0)
    assert s.Vc_min == pytest.approx(150.0, rel=1e-9) and s.Vc_max == pytest.approx(150.0, rel=1e-9)


@pytest.mark.parametrize("r", [30.0, 15.0])
def test_g96_longitudinal(r):
    """Boy tornalama (r sabit ≥ r*): Vc = Vc₀, n = 1000 Vc₀ / (2π r), t = L / (f n), D = t / T(Vc₀)."""
    L = 40.0
    ops, res, loads = torna_programi([(torna_ucu(), 2000.0, 150.0, 0.2, [(r, 0.0), (r, -L)], 1.0)])
    w = _tek(turn_wear(ops, res, loads, malzeme(), KARBUR))
    n = 1000.0 * 150.0 / (2 * math.pi * r)
    t = L / (0.2 * n)
    assert w.t_cut == pytest.approx(t, rel=1e-9)
    assert w.D == pytest.approx(t / T_taylor(150.0), rel=1e-9)


def test_g96_longitudinal_below_r_star():
    """r = 5 < r* (11.94): n = N_max, Vc = 2π 5 · 2000 / 1000 < Vc₀; t = L / (f N_max)."""
    ops, res, loads = torna_programi([(torna_ucu(), 2000.0, 150.0, 0.2, [(5.0, 0.0), (5.0, -40.0)], 1.0)])
    w = _tek(turn_wear(ops, res, loads, malzeme(), KARBUR))
    Vc = 2 * math.pi * 5.0 * 2000.0 / 1000.0
    t = 40.0 / (0.2 * 2000.0)
    assert w.D == pytest.approx(t / T_taylor(Vc), rel=1e-9)
    assert w.Vc_max == pytest.approx(Vc, rel=1e-9)


# ---------- K7 Tam sayı olmayan üs ----------


@pytest.mark.parametrize("rtol", [1e-6, 1e-8])
def test_non_integer_exponent(rtol):
    """n = 0.3 (m = 3.33…): G97 alın tornalama sayısal sonuç kapalı formla rtol içinde."""
    mal = malzeme({"karbur": Taylor(300.0, 0.3)})
    ops, res, loads = torna_programi([(torna_ucu(), 500.0, None, 0.2, [(50.0, 0.0), (0.0, 0.0)], 1.0)])
    w = _tek(turn_wear(ops, res, loads, mal, KARBUR, rtol=rtol))
    assert w.D == pytest.approx(g97_alin_D(500.0, 0.2, 50.0, n=0.3), rel=rtol)


def test_non_integer_exponent_default_rtol():
    mal = malzeme({"karbur": Taylor(300.0, 0.3)})
    ops, res, loads = torna_programi([(torna_ucu(), 500.0, None, 0.2, [(50.0, 0.0), (0.0, 0.0)], 1.0)])
    w = _tek(turn_wear(ops, res, loads, mal, KARBUR))
    assert w.D == pytest.approx(g97_alin_D(500.0, 0.2, 50.0, n=0.3), rel=1e-6)


# ---------- K9 Hatalar (torna) ----------


def _program(rpm=500.0, css=None):
    return torna_programi([(torna_ucu(), rpm, css, 0.2, [(50.0, 0.0), (0.0, 0.0)], 1.0)])


def test_error_tool_material_missing():
    ops, res, loads = _program()
    with pytest.raises(MODEL_HATASI, match="T5"):
        turn_wear(ops, res, loads, malzeme(), {})


def test_error_tool_material_unknown():
    ops, res, loads = _program()
    with pytest.raises(MODEL_HATASI):
        turn_wear(ops, res, loads, malzeme(), {5: "elmas"})


def test_error_no_taylor_for_tool_material():
    ops, res, loads = _program()
    with pytest.raises(MODEL_HATASI) as e:
        turn_wear(ops, res, loads, malzeme(), {5: "CBN"})
    assert "C45" in str(e.value) and "CBN" in str(e.value)


def test_error_loads_length():
    ops, res, loads = _program()
    with pytest.raises(CamError):
        turn_wear(ops, res, loads[:-1], malzeme(), KARBUR)


def test_error_no_spindle_speed():
    """css yok ve rpm = 0: kesme adımında Vc hesaplanamaz → CamError."""
    ops, res, loads = torna_programi([(torna_ucu(), 0.0, None, 0.2, [(30.0, 0.0), (30.0, -40.0)], 1.0)])
    with pytest.raises(CamError):
        turn_wear(ops, res, loads, malzeme(), KARBUR)
