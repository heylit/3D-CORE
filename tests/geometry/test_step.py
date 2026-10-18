"""SPEC 02 — işlenmiş parçanın STEP gidiş-dönüşü (K9). OCCT gerektirir.

Testler SPEC 02 teorisinden yazıldı; uygulama gövdeleri okunmadı.
Parça: blok 100×60×30 → boydan delik d=10 (20, 30) → cep 40×20 r=5 t=8 merkez (65, 30) → üst pah d=3.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from geometry.features import block, chamfer_top, cylinder, hole, pocket
from geometry.part import Part
from geometry.props import mass_props

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 30.0


def machined_part() -> Part:
    p = hole(block(A, B, C), 20.0, 30.0, 10.0)
    p = pocket(p, 65.0, 30.0, 40.0, 20.0, 8.0, r=5.0)
    return chamfer_top(p, 3.0)


def assert_same_geometry(p: Part, q: Part) -> None:
    """V, S rel 1e-6; ağırlık merkezi ve sınır kutusu rel 1e-6 (parça boyu ölçeğinde mutlak)."""
    assert q.volume == pytest.approx(p.volume, rel=1e-6)
    assert q.area == pytest.approx(p.area, rel=1e-6)
    L = max(A, B, C)
    np.testing.assert_allclose(q.center_of_mass, p.center_of_mass, rtol=1e-6, atol=1e-6 * L)
    for a, b in zip(p.bbox, q.bbox, strict=True):
        np.testing.assert_allclose(b, a, rtol=1e-6, atol=1e-6 * L)


def test_step_roundtrip_machined_part(tmp_path):
    """K9: delik + cep + pah işlenmiş parça to_step → from_step: V, S, x̄, sınır kutusu korunur.
    Analitik hacim (test_features K5 el hesabı): V = abc − π·10²·30/4 − A_c·8 − ΣΔV_pah,
    A_c = 800 − (4−π)·25, ΣΔV_pah = 1404 + 54π + (360 + 54π). Sınır kutusu [0,0,0]–[100,60,30]."""
    p = machined_part()
    dV_ch = 1404.0 + 54 * math.pi + (4.5 * 80 + 54 * math.pi)
    V = A * B * C - math.pi * 100 * C / 4 - (800 - (4 - math.pi) * 25) * 8 - dV_ch
    assert p.volume == pytest.approx(V, rel=1e-6)

    path = tmp_path / "islenmis.step"
    p.to_step(path)
    assert path.is_file() and path.stat().st_size > 0
    q = Part.from_step(path, name="geri")
    assert q.name == "geri"
    assert_same_geometry(p, q)
    assert q.volume == pytest.approx(V, rel=1e-6)
    lo, hi = q.bbox
    np.testing.assert_allclose(lo, [0.0, 0.0, 0.0], atol=1e-4)
    np.testing.assert_allclose(hi, [A, B, C], atol=1e-4)


def test_step_roundtrip_cylinder_with_hole(tmp_path):
    """K9 (eğri yüzler): silindir r=20 h=50 + eksende kör delik d=10 t=15.
    Gidiş-dönüşte V, S, x̄, sınır kutusu korunur.
    V = π r² h − π d² t/4 = 20000π − 375π = 19625π."""
    p = hole(cylinder(20.0, 50.0), 0.0, 0.0, 10.0, depth=15.0)
    path = tmp_path / "silindir.step"
    p.to_step(path)
    q = Part.from_step(path)
    assert q.volume == pytest.approx(19625 * math.pi, rel=1e-6)
    assert_same_geometry(p, q)


def test_step_roundtrip_preserves_mass_props(tmp_path):
    """K9 + K6: STEP sonrası kütle özellikleri (m, x̄, I) aynı (rel 1e-6)."""
    rho = 7.85e-9
    p = machined_part()
    path = tmp_path / "kp.step"
    p.to_step(path)
    mp0 = mass_props(p, rho)
    mp1 = mass_props(Part.from_step(path), rho)
    assert mp1.m == pytest.approx(mp0.m, rel=1e-6)
    np.testing.assert_allclose(mp1.com, mp0.com, atol=1e-6 * max(A, B, C))
    np.testing.assert_allclose(mp1.I, mp0.I, rtol=1e-6, atol=1e-6 * np.max(np.abs(mp0.I)))
