"""
bar1d eleman matrisi özellik testleri (specs/01-bar.md, bölüm 'Kabul kriterleri / Eleman').
Doğrulayıcı ajan tarafından SPEC'ten yazıldı; uygulama koduna bakılmadan.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.elements import bar1d
from core.model import ModelError
from tests.conftest import make_bar


def test_length():
    m = make_bar(n_elem=4, L=1000.0)
    assert bar1d.length(m.elements[0], m) == pytest.approx(250.0)


def test_ke_exact_values():
    m = make_bar(n_elem=1, L=1000.0, E=210_000.0, A=100.0)
    k = bar1d.ke(m.elements[0], m)
    k0 = 210_000.0 * 100.0 / 1000.0
    np.testing.assert_allclose(k, k0 * np.array([[1.0, -1.0], [-1.0, 1.0]]), rtol=1e-12)


def test_ke_symmetric():
    m = make_bar(n_elem=3)
    for e in m.elements:
        k = bar1d.ke(e, m)
        np.testing.assert_allclose(k, k.T, rtol=0, atol=1e-9)


def test_ke_rigid_body_mode_has_zero_energy():
    """Tüm çubuğun ötelenmesi iç kuvvet üretmemeli: k @ [1, 1] = 0."""
    m = make_bar()
    k = bar1d.ke(m.elements[0], m)
    np.testing.assert_allclose(k @ np.ones(2), 0.0, atol=1e-9)


def test_ke_eigenvalues():
    """Bir sıfır özdeğer (rijit hareket), bir pozitif özdeğer = 2EA/L."""
    m = make_bar(n_elem=1, L=500.0, E=70_000.0, A=20.0)
    w = np.sort(np.linalg.eigvalsh(bar1d.ke(m.elements[0], m)))
    assert w[0] == pytest.approx(0.0, abs=1e-6)
    assert w[1] == pytest.approx(2 * 70_000.0 * 20.0 / 500.0, rel=1e-12)


def test_ke_independent_of_node_order():
    """Düğümler ters sırada verilse de boy pozitif, matris aynı olmalı."""
    m = make_bar(n_elem=1)
    k1 = bar1d.ke(m.elements[0], m)
    m.elements[0].nodes = list(reversed(m.elements[0].nodes))
    k2 = bar1d.ke(m.elements[0], m)
    np.testing.assert_allclose(k1, k2, rtol=1e-12)


def test_zero_length_rejected():
    m = make_bar(n_elem=1)
    m.nodes[1].x = m.nodes[0].x
    with pytest.raises(ModelError):
        bar1d.ke(m.elements[0], m)


def test_dofs():
    m = make_bar(n_elem=3)
    assert bar1d.dofs(m.elements[1], m) == [1, 2]


def test_axial_force_tension_positive():
    m = make_bar(n_elem=1, L=1000.0, E=210_000.0, A=100.0)
    u = np.array([0.0, 0.1])  # 0.1 mm uzama
    assert bar1d.axial_force(m.elements[0], m, u) == pytest.approx(210_000.0 * 100.0 / 1000.0 * 0.1)


def test_axial_force_compression_negative():
    m = make_bar(n_elem=1)
    assert bar1d.axial_force(m.elements[0], m, np.array([0.0, -0.05])) < 0
