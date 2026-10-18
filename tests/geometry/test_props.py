"""SPEC 02 — geometry/props.py testleri (K6). OCCT gerektirir.

Testler SPEC 02 teorisinden yazıldı; uygulama gövdeleri okunmadı.
Atalet: I = ∫ ρ (|r|² 𝟙 − r rᵀ) dV, r = x − x̄ (Beer & Johnston, Statics, Ek B).
Birimler: ρ [t/mm³] (çelik 7.85e-9), m [t], I [t·mm²].
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from geometry.features import block, cylinder, hole
from geometry.part import GeometryError, Part
from geometry.props import MassProps, mass_props, principal_moments

pytestmark = pytest.mark.occt

RHO = 7.85e-9  # çelik [t/mm³]
A, B, C = 100.0, 60.0, 30.0  # blok [mm]


def block_I(m: float, a: float, b: float, c: float) -> np.ndarray:
    """Dikdörtgen prizma, ağırlık merkezine göre: Ixx = m(b²+c²)/12, Iyy = m(a²+c²)/12, Izz = m(a²+b²)/12."""
    return np.diag([m * (b**2 + c**2) / 12, m * (a**2 + c**2) / 12, m * (a**2 + b**2) / 12])


def cylinder_I(m: float, r: float, h: float) -> np.ndarray:
    """Dolu silindir (eksen Z), ağırlık merkezine göre: Izz = m r²/2, Ixx = Iyy = m(3r² + h²)/12."""
    Ixx = m * (3 * r**2 + h**2) / 12
    return np.diag([Ixx, Ixx, m * r**2 / 2])


def shift(I_c: np.ndarray, m: float, d: np.ndarray) -> np.ndarray:
    """Paralel eksen teoremi (tensör biçimi): I_P = I_c + m(|d|² 𝟙 − d dᵀ), d = x̄ − P."""
    d = np.asarray(d, dtype=float)
    return I_c + m * (d @ d * np.eye(3) - np.outer(d, d))


def assert_tensor_close(I: np.ndarray, I_ref: np.ndarray, rel: float = 1e-6) -> None:  # noqa: E741
    """Tensör karşılaştırması: bileşen hatası ‖I_ref‖ ölçeğine göre rel (çarpım terimleri 0 olabilir)."""
    scale = np.max(np.abs(I_ref))
    np.testing.assert_allclose(I, I_ref, rtol=rel, atol=rel * scale)


def test_mass_props_block():
    """K6: blok 100×60×30, ρ = 7.85e-9.
    V = 180000 mm³, m = ρV = 1.413e-3 t, x̄ = (50, 30, 15);
    Ixx = m(60² + 30²)/12 = m·375, Iyy = m(100² + 30²)/12 = m·908.33, Izz = m(100² + 60²)/12 = m·1133.33;
    çarpım terimleri 0."""
    mp = mass_props(block(A, B, C), RHO)
    assert isinstance(mp, MassProps)
    V = A * B * C
    m = RHO * V
    assert mp.V == pytest.approx(V, rel=1e-6)
    assert mp.m == pytest.approx(m, rel=1e-6)
    assert np.shape(mp.com) == (3,)
    np.testing.assert_allclose(mp.com, [A / 2, B / 2, C / 2], rtol=1e-6, atol=1e-6)
    assert np.shape(mp.I) == (3, 3)
    assert_tensor_close(mp.I, block_I(m, A, B, C))
    np.testing.assert_allclose(mp.I, mp.I.T, rtol=0, atol=1e-12 * np.max(np.abs(mp.I)))


def test_mass_props_cylinder():
    """K6: silindir r=20, h=50 (taban merkezi orijinde, eksen +Z).
    V = π r² h = 20000π, m = ρV, x̄ = (0, 0, 25); Izz = m r²/2 = 200m, Ixx = Iyy = m(3·400 + 2500)/12."""
    r, h = 20.0, 50.0
    mp = mass_props(cylinder(r, h), RHO)
    V = math.pi * r**2 * h
    m = RHO * V
    assert mp.V == pytest.approx(V, rel=1e-6)
    assert mp.m == pytest.approx(m, rel=1e-6)
    np.testing.assert_allclose(mp.com, [0.0, 0.0, h / 2], atol=1e-6)
    assert_tensor_close(mp.I, cylinder_I(m, r, h))


def test_mass_props_holed_block_parallel_axis():
    """K6: blok 100×60×30, boydan boya delik d=10 eksen (20, 30). El hesabı (paralel eksen teoremi):
      m_b = ρ abc,  x̄_b = (50, 30, 15);  m_h = ρ π R² c (R=5),  x̄_h = (20, 30, 15)
      m = m_b − m_h,  x̄ = (m_b x̄_b − m_h x̄_h)/m
      I = [I_b + m_b(|d_b|²𝟙 − d_b d_bᵀ)] − [I_h + m_h(|d_h|²𝟙 − d_h d_hᵀ)],  d_i = x̄_i − x̄
    Kaldırılan silindir negatif kütle gibi çıkarılır (SPEC: ΣVᵢ x̄ᵢ, eksi işaret)."""
    d, R = 10.0, 5.0
    hx, hy = 20.0, 30.0
    mp = mass_props(hole(block(A, B, C), hx, hy, d), RHO)

    m_b = RHO * A * B * C
    m_h = RHO * math.pi * R**2 * C
    c_b = np.array([A / 2, B / 2, C / 2])
    c_h = np.array([hx, hy, C / 2])
    m = m_b - m_h
    com = (m_b * c_b - m_h * c_h) / m
    I_ref = shift(block_I(m_b, A, B, C), m_b, c_b - com) - shift(cylinder_I(m_h, R, C), m_h, c_h - com)

    assert mp.V == pytest.approx(A * B * C - math.pi * R**2 * C, rel=1e-6)
    assert mp.m == pytest.approx(m, rel=1e-6)
    np.testing.assert_allclose(mp.com, com, atol=1e-6)
    assert_tensor_close(mp.I, I_ref)


def test_mass_props_scales_with_rho():
    """m = ρV ve I ∝ ρ: ρ iki katına çıkınca m ve I iki katı, V ve x̄ aynı."""
    p = block(A, B, C)
    mp1 = mass_props(p, RHO)
    mp2 = mass_props(p, 2 * RHO)
    assert mp2.V == pytest.approx(mp1.V, rel=1e-12)
    assert mp2.m == pytest.approx(2 * mp1.m, rel=1e-9)
    np.testing.assert_allclose(mp2.com, mp1.com, atol=1e-9)
    assert_tensor_close(mp2.I, 2 * mp1.I, rel=1e-9)


@pytest.mark.parametrize("rho", [0.0, -7.85e-9])
def test_mass_props_invalid_rho(rho):
    """K6: rho <= 0 → GeometryError."""
    with pytest.raises(GeometryError):
        mass_props(block(A, B, C), rho)


def test_principal_moments_block():
    """K6: eksen hizalı blokta asal momentler = sıralı {Ixx, Iyy, Izz} (artan):
    m·375 < m·908.33 < m·1133.33 → asal eksenler sırasıyla ±X, ±Y, ±Z."""
    mp = mass_props(block(A, B, C), RHO)
    lam, Q = principal_moments(mp)
    m = RHO * A * B * C
    ref = np.sort(np.diag(block_I(m, A, B, C)))
    assert np.shape(lam) == (3,)
    assert np.shape(Q) == (3, 3)
    np.testing.assert_allclose(lam, ref, rtol=1e-6)
    assert np.all(np.diff(lam) >= 0)
    np.testing.assert_allclose(np.abs(Q), np.eye(3), atol=1e-6)


def test_principal_moments_rotated_block_invariant():
    """K6: Z etrafında 30° döndürülmüş blok. Global tensör I' = R I Rᵀ (çarpım terimleri artık ≠ 0),
    ama asal momentler (özdeğerler) dönmeden bağımsız: sıralı {Ixx, Iyy, Izz}.
    En küçük momentin ekseni (blokta X) dönmüş X: ±(cos30°, sin30°, 0).
    Blok build123d ile kurulur (Box orijinde ortalanır), sonra Part(...)."""
    from build123d import Box, Rot

    th = math.radians(30.0)
    p = Part(Rot(0, 0, 30) * Box(A, B, C), name="donuk_blok")
    mp = mass_props(p, RHO)
    m = RHO * A * B * C
    I0 = block_I(m, A, B, C)
    Rz = np.array([[math.cos(th), -math.sin(th), 0.0], [math.sin(th), math.cos(th), 0.0], [0.0, 0.0, 1.0]])
    np.testing.assert_allclose(mp.com, [0.0, 0.0, 0.0], atol=1e-6)
    assert_tensor_close(mp.I, Rz @ I0 @ Rz.T)

    lam, Q = principal_moments(mp)
    np.testing.assert_allclose(lam, np.sort(np.diag(I0)), rtol=1e-6)
    # Q dik (ortonormal) ve I'yi köşegenleştirir: Qᵀ I Q = diag(λ)
    np.testing.assert_allclose(Q.T @ Q, np.eye(3), atol=1e-9)
    assert_tensor_close(Q.T @ mp.I @ Q, np.diag(lam))
    e1 = Q[:, 0]
    assert abs(e1 @ np.array([math.cos(th), math.sin(th), 0.0])) == pytest.approx(1.0, abs=1e-6)

    # Eksen hizalı blokla aynı asal momentler
    lam0, _ = principal_moments(mass_props(block(A, B, C), RHO))
    np.testing.assert_allclose(lam, lam0, rtol=1e-6)
