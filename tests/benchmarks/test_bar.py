"""
1D çubuk analitik benchmark'ları (specs/01-bar.md).
Her test bir el hesabı / analitik çözümle karşılaştırır. Tolerans: rel 1e-9
(1D lineer çubukta FEM düğüm değerleri analitik çözümle TAM örtüşür).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.assembly import assemble_F, assemble_K
from core.model import BC, Element, Load, Material, Model, ModelError, Node, Section
from core.solver import solve
from tests.conftest import AL_E, STEEL_E, make_bar

REL = 1e-9


# --- B1: Uçtan çekilen çubuk  δ = F L / (E A) ---------------------------------

@pytest.mark.parametrize("n_elem", [1, 2, 5, 10, 50])
def test_B1_tip_displacement(n_elem):
    L, E, A, F = 1000.0, STEEL_E, 100.0, 10_000.0
    m = make_bar(n_elem=n_elem, L=L, E=E, A=A, tip_load=F)
    r = solve(m)
    assert r.displacement(m, n_elem + 1) == pytest.approx(F * L / (E * A), rel=REL)


def test_B1_linear_displacement_field():
    """Düzgün çubukta u(x) = F x / (E A): tüm düğümlerde doğrusal."""
    L, E, A, F = 1000.0, STEEL_E, 100.0, 10_000.0
    m = make_bar(n_elem=8, L=L, E=E, A=A, tip_load=F)
    r = solve(m)
    for n in m.nodes:
        assert r.displacement(m, n.id) == pytest.approx(F * n.x / (E * A), rel=REL, abs=1e-15)


def test_B1_reaction_and_stress():
    F, A = 10_000.0, 100.0
    m = make_bar(n_elem=4, A=A, tip_load=F)
    r = solve(m)
    assert r.reaction(m, 1) == pytest.approx(-F, rel=REL)
    for e in m.elements:
        assert r.element_forces[e.id] == pytest.approx(F, rel=REL)
        assert r.element_stresses[e.id] == pytest.approx(F / A, rel=REL)  # 100 MPa


# --- B2: Kademeli çubuk (seri yaylar) -----------------------------------------

def test_B2_stepped_bar():
    """Çelik + alüminyum, farklı kesitler: δ = F (L1/(E1 A1) + L2/(E2 A2))."""
    L1, L2, A1, A2, F = 400.0, 600.0, 200.0, 50.0, 5_000.0
    m = Model(
        dim=1,
        nodes=[Node(1, 0.0), Node(2, L1), Node(3, L1 + L2)],
        elements=[
            Element(1, "bar1d", [1, 2], "celik", "kalin"),
            Element(2, "bar1d", [2, 3], "al", "ince"),
        ],
        materials=[Material("celik", STEEL_E), Material("al", AL_E)],
        sections=[Section("kalin", A1), Section("ince", A2)],
        bcs=[BC(1, "ux")],
        loads=[Load(3, "ux", F)],
    )
    r = solve(m)
    d1 = F * L1 / (STEEL_E * A1)
    assert r.displacement(m, 2) == pytest.approx(d1, rel=REL)
    assert r.displacement(m, 3) == pytest.approx(d1 + F * L2 / (AL_E * A2), rel=REL)
    assert r.element_stresses[1] == pytest.approx(F / A1, rel=REL)
    assert r.element_stresses[2] == pytest.approx(F / A2, rel=REL)


# --- B3: İki ucu ankastre, aradan yüklü çubuk (hiperstatik) -------------------

@pytest.mark.parametrize("a_frac", [0.25, 0.5, 0.7])
def test_B3_fixed_fixed_point_load(a_frac):
    """P yükü x=a'da:  u(a) = P a (L-a) / (E A L),  R_sol = -P (L-a)/L,  R_sağ = -P a/L."""
    L, E, A, P, n = 1000.0, STEEL_E, 100.0, 20_000.0, 20
    m = make_bar(n_elem=n, L=L, E=E, A=A, tip_load=None)
    m.bcs.append(BC(n + 1, "ux"))
    k = round(a_frac * n)
    a = L * k / n
    m.loads.append(Load(k + 1, "ux", P))
    r = solve(m)
    assert r.displacement(m, k + 1) == pytest.approx(P * a * (L - a) / (E * A * L), rel=REL)
    assert r.reaction(m, 1) == pytest.approx(-P * (L - a) / L, rel=REL)
    assert r.reaction(m, n + 1) == pytest.approx(-P * a / L, rel=REL)


# --- B4: Kendi ağırlığı / yayılı yük (tutarlı düğüm yükleri) ------------------

def test_B4_uniform_distributed_load():
    """q [N/mm] yayılı yük, sol ankastre: u(x) = q (L x - x²/2) / (E A).
    Her eleman q*Le/2 kadar yükü iki düğümüne paylaştırır."""
    L, E, A, q, n = 2000.0, STEEL_E, 80.0, 3.0, 10
    m = make_bar(n_elem=n, L=L, E=E, A=A, tip_load=None)
    Le = L / n
    for e in m.elements:
        for nid in e.nodes:
            m.loads.append(Load(nid, "ux", q * Le / 2))   # aynı DOF'a gelen yükler toplanmalı
    r = solve(m)
    for nd in m.nodes:
        x = nd.x
        assert r.displacement(m, nd.id) == pytest.approx(q * (L * x - x**2 / 2) / (E * A), rel=REL, abs=1e-15)
    assert r.reaction(m, 1) == pytest.approx(-q * L, rel=REL)


# --- B5: Zorlanmış yer değiştirme ---------------------------------------------

def test_B5_prescribed_displacement():
    """Sol ankastre, sağ uç d kadar çekiliyor: R_sağ = E A d / L."""
    L, E, A, d = 1000.0, STEEL_E, 100.0, 0.2
    m = make_bar(n_elem=5, L=L, E=E, A=A, tip_load=None)
    m.bcs.append(BC(6, "ux", d))
    r = solve(m)
    assert r.displacement(m, 6) == pytest.approx(d, rel=REL)
    assert r.reaction(m, 6) == pytest.approx(E * A * d / L, rel=REL)
    assert r.reaction(m, 1) == pytest.approx(-E * A * d / L, rel=REL)


# --- Genel kontroller ----------------------------------------------------------

def test_global_equilibrium():
    """Tepkiler + dış yükler = 0."""
    m = make_bar(n_elem=6, tip_load=None)
    m.bcs.append(BC(7, "ux"))
    m.loads += [Load(3, "ux", 1_000.0), Load(5, "ux", -4_000.0)]
    r = solve(m)
    total_load = sum(ld.value for ld in m.loads)
    assert r.reactions.sum() + total_load == pytest.approx(0.0, abs=1e-6)


def test_K_global_properties():
    m = make_bar(n_elem=5)
    K = assemble_K(m).toarray()
    assert K.shape == (6, 6)
    np.testing.assert_allclose(K, K.T, atol=1e-9)
    np.testing.assert_allclose(K @ np.ones(6), 0.0, atol=1e-6)        # mesnetsiz: rijit mod
    assert np.sum(np.abs(np.linalg.eigvalsh(K)) < 1e-6) == 1          # tam bir sıfır özdeğer


def test_F_accumulates_loads_on_same_dof():
    m = make_bar(n_elem=2, tip_load=100.0)
    m.loads.append(Load(3, "ux", 50.0))
    F = assemble_F(m)
    np.testing.assert_allclose(F, [0.0, 0.0, 150.0])


def test_mechanism_raises():
    """Mesnet yok -> tekil sistem -> ModelError (sessizce yanlış sonuç değil!)."""
    m = make_bar(n_elem=3, fix_left=False)
    with pytest.raises(ModelError):
        solve(m)


def test_node_order_independence():
    """Düğümler listede karışık sırada verilse de sonuç aynı."""
    m = make_bar(n_elem=4)
    expected = solve(m).displacement(m, 5)
    m.nodes = [m.nodes[i] for i in (3, 0, 4, 2, 1)]
    r = solve(m)
    assert r.displacement(m, 5) == pytest.approx(expected, rel=REL)


def test_example_json():
    m = Model.from_json("examples/01_cubuk.json")
    r = solve(m)
    # örnek: L=1000 mm, A=100 mm², çelik, uçta 10 kN -> 0.47619 mm
    assert r.displacement(m, 5) == pytest.approx(10_000 * 1000 / (STEEL_E * 100), rel=REL)
