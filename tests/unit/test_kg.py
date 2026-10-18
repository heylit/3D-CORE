"""
SPEC 68a geometrik rijitlik testleri, tet4 aşaması (specs/68a-burkulma.md, K1, K2, assemble_Kg hataları).

Testler yalnız SPEC metninden ve arayüzden yazıldı; kg / assemble_Kg / buckling gövdeleri okunmadı.

Teori: Kg_e = V Gᵀ Ŝ G, Ŝ = diag(S, S, S), G (9 × 12) yer değiştirme gradyanı ∂u_i/∂x_j.
Bileşen biçimi: Kg_e[3a+i, 3b+k] = δ_ik · V · ∇N_aᵀ S ∇N_b.
"""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from core.assembly import assemble_Kg
from core.elements import tet4
from core.model import Element, Material, Model, ModelError, Node, Section
from tests.benchmarks.tet_ag import kutu_agi

E, NU = 210_000.0, 0.3

GENEL_TET = np.array([[0.3, -0.2, 0.1], [2.1, 0.4, -0.3], [0.5, 1.7, 0.2], [0.2, 0.6, 1.9]])
SIGMA_A = np.array([120.0, -35.0, 60.0, 14.0, -22.0, 9.0])
SIGMA_B = np.array([-40.0, 80.0, 5.0, -30.0, 11.0, 47.0])


def tet(X: np.ndarray = GENEL_TET, sira: tuple[int, int, int, int] = (1, 2, 3, 4)) -> Model:
    return Model(
        dim=3,
        nodes=[Node(i + 1, *X[i]) for i in range(4)],
        elements=[Element(1, "tet4", list(sira), "m")],
        materials=[Material("m", E, NU)],
    )


def gradyanlar(model: Model) -> tuple[float, np.ndarray]:
    """Testin kendi (V, ∇N) hesabı: ∇N (4 × 3), element.nodes sırasında, C = [1 x y z]."""
    e = model.elements[0]
    X = np.array([model.node(n).xyz for n in e.nodes])
    C = np.hstack([np.ones((4, 1)), X])
    V = abs(np.linalg.det(C)) / 6.0
    return V, np.linalg.inv(C)[1:, :].T


def G_matrisi(dN: np.ndarray) -> np.ndarray:
    """G (9 × 12): satır 3i + j = ∂u_i/∂x_j, sütun 3a + i (DOF sırası [u1, v1, w1, ...])."""
    G = np.zeros((9, 12))
    for a in range(4):
        for i in range(3):
            for j in range(3):
                G[3 * i + j, 3 * a + i] = dN[a, j]
    return G


def tensor(s: np.ndarray) -> np.ndarray:
    """Voigt [xx, yy, zz, xy, xz, yz] → 3 × 3 (kayma bileşenleri tensör bileşenidir)."""
    return np.array([[s[0], s[3], s[4]], [s[3], s[1], s[5]], [s[4], s[5], s[2]]])


def kg_beklenen(model: Model, s: np.ndarray) -> np.ndarray:
    V, dN = gradyanlar(model)
    G = G_matrisi(dN)
    S_hat = np.kron(np.eye(3), tensor(s))
    return V * G.T @ S_hat @ G


def kg(model: Model, s: np.ndarray) -> np.ndarray:
    return tet4.kg(model.elements[0], model, np.asarray(s, dtype=float))


# --- K1 ---------------------------------------------------------------------------------


def test_kg_boyut():
    assert kg(tet(), SIGMA_A).shape == (12, 12)


@pytest.mark.parametrize("s", [SIGMA_A, SIGMA_B])
def test_kg_simetrik(s):
    K = kg(tet(), s)
    np.testing.assert_allclose(K, K.T, rtol=0, atol=1e-13 * np.abs(K).max())


def test_kg_sigma_ile_dogrusal():
    m = tet()
    a, b = 2.5, -0.7
    sol = kg(m, a * SIGMA_A + b * SIGMA_B)
    sag = a * kg(m, SIGMA_A) + b * kg(m, SIGMA_B)
    np.testing.assert_allclose(sol, sag, rtol=0, atol=1e-12 * np.abs(sag).max())
    np.testing.assert_array_equal(kg(m, np.zeros(6)), np.zeros((12, 12)))


@pytest.mark.parametrize("s", [SIGMA_A, SIGMA_B])
def test_kg_rijit_oteleme_cekirdekte(s):
    K = kg(tet(), s)
    for d in range(3):
        t = np.zeros(12)
        t[d::3] = 1.0
        np.testing.assert_allclose(K @ t, 0.0, atol=1e-12 * np.linalg.norm(K))


@pytest.mark.parametrize("p", [75.0, -40.0])
def test_kg_hidrostatik(p):
    """σ0 = p I → Kg_e = p V Gᵀ G (göreli 1e-12)."""
    m = tet()
    V, dN = gradyanlar(m)
    G = G_matrisi(dN)
    beklenen = p * V * G.T @ G
    olcek = np.abs(beklenen).max()
    np.testing.assert_allclose(kg(m, [p, p, p, 0, 0, 0]), beklenen, rtol=1e-12, atol=1e-12 * olcek)


@pytest.mark.parametrize("s", [SIGMA_A, SIGMA_B])
def test_kg_genel_gerilme_formulu(s):
    """Kg_e = V Gᵀ diag(S, S, S) G, Voigt kayma bileşenleri tensör bileşeni (γ değil)."""
    m = tet()
    beklenen = kg_beklenen(m, s)
    np.testing.assert_allclose(kg(m, s), beklenen, rtol=1e-12, atol=1e-12 * np.abs(beklenen).max())


def test_kg_kayma_tensor_bileseni():
    """Yalnız σ_xy = τ: Kg[3a, 3b] = V τ (∂N_a/∂x ∂N_b/∂y + ∂N_a/∂y ∂N_b/∂x)."""
    m = tet()
    V, dN = gradyanlar(m)
    tau = 10.0
    K = kg(m, [0, 0, 0, tau, 0, 0])
    beklenen = V * tau * (np.outer(dN[:, 0], dN[:, 1]) + np.outer(dN[:, 1], dN[:, 0]))
    for i in range(3):
        np.testing.assert_allclose(K[i::3, i::3], beklenen, rtol=1e-12, atol=1e-12 * np.abs(beklenen).max())
    np.testing.assert_allclose(K[0::3, 1::3], 0.0, atol=1e-12 * np.abs(beklenen).max())


def test_kg_dugum_sirasi_sol_el():
    """Sol el düğüm sırası: aynı fiziksel matris, DOF'lar düğüm sırasıyla yer değiştirir."""
    sag = tet(sira=(1, 2, 3, 4))
    sol = tet(sira=(1, 3, 2, 4))
    K_sag = kg(sag, SIGMA_A)
    K_sol = kg(sol, SIGMA_A)
    p = np.array([0, 2, 1, 3])  # sol eleman düğüm a ↔ sağ eleman düğüm p[a]
    idx = np.array([3 * p[a] + i for a in range(4) for i in range(3)])
    np.testing.assert_allclose(K_sol, K_sag[np.ix_(idx, idx)], rtol=1e-12, atol=1e-12 * np.abs(K_sag).max())


def test_kg_tek_eleman_cubuk_esdegeri():
    """Yalnız σ_zz = σ: Kg = σ V (∂N/∂z ⊗ ∂N/∂z) ⊗ I₃ (çubuk Kg'sinin 3B karşılığı)."""
    m = tet()
    V, dN = gradyanlar(m)
    sigma = 50.0
    K = kg(m, [0, 0, sigma, 0, 0, 0])
    beklenen = np.kron(sigma * V * np.outer(dN[:, 2], dN[:, 2]), np.eye(3))
    np.testing.assert_allclose(K, beklenen, rtol=1e-12, atol=1e-12 * np.abs(K).max())


def test_kg_yassi_eleman_hatasi():
    X = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0.3, 0.3, 0.0]])
    with pytest.raises(ModelError):
        kg(tet(X), SIGMA_A)


# --- assemble_Kg -------------------------------------------------------------------------------


def kutu() -> Model:
    return kutu_agi(4.0, 2.0, 3.0, 2, 2, 2, Material("celik", E, NU), kaydirma=0.15, tohum=5)


def rastgele_sigma(m: Model, tohum: int = 0) -> dict[int, np.ndarray]:
    rng = np.random.default_rng(tohum)
    return {e.id: rng.normal(scale=50.0, size=6) for e in m.elements}


def test_assemble_Kg_eleman_toplami():
    m = kutu()
    s = rastgele_sigma(m)
    Kg = assemble_Kg(m, s)
    assert sp.issparse(Kg)
    assert Kg.shape == (m.n_dof, m.n_dof)
    beklenen = np.zeros((m.n_dof, m.n_dof))
    for e in m.elements:
        d = np.array([m.dof_index(n, a) for n in e.nodes for a in ("ux", "uy", "uz")])
        tek = Model(
            dim=3,
            nodes=[m.node(n) for n in e.nodes],
            elements=[Element(1, "tet4", list(e.nodes), e.material)],
            materials=m.materials,
        )
        beklenen[np.ix_(d, d)] += kg_beklenen(tek, s[e.id])
    np.testing.assert_allclose(Kg.toarray(), beklenen, rtol=0, atol=1e-11 * np.abs(beklenen).max())


def test_assemble_Kg_simetrik_ve_oteleme():
    m = kutu()
    Kg = assemble_Kg(m, rastgele_sigma(m, 3)).toarray()
    olcek = np.abs(Kg).max()
    np.testing.assert_allclose(Kg, Kg.T, atol=1e-13 * olcek)
    for d in range(3):
        t = np.zeros(m.n_dof)
        t[d::3] = 1.0
        np.testing.assert_allclose(Kg @ t, 0.0, atol=1e-12 * np.linalg.norm(Kg))


def test_assemble_Kg_eksik_eleman_gerilmesi():
    m = kutu()
    s = rastgele_sigma(m)
    del s[m.elements[3].id]
    with pytest.raises(ModelError):
        assemble_Kg(m, s)


def test_assemble_Kg_kg_saglamayan_eleman():
    """bar1d kg sağlamaz → ModelError."""
    m = Model(
        dim=1,
        nodes=[Node(1, 0.0), Node(2, 10.0)],
        elements=[Element(1, "bar1d", [1, 2], "m", "s")],
        materials=[Material("m", E, NU)],
        sections=[Section("s", 1.0)],
    )
    with pytest.raises(ModelError):
        assemble_Kg(m, {1: np.zeros(6)})


# --- K2: çubukla çapraz kontrol (Rayleigh oranı) ---------------------------------------------

B_KESIT, L_CUBUK, P_CEKME = 2.0, 40.0, 500.0


@pytest.mark.parametrize("w", ["sinus", "parabol"])
def test_kg_cubuk_rayleigh_orani(w):
    """
    2 × 2 × 20 Kuhn ağı (eksen z), düzgün çekme σ_zz = P/A. Enine alan u_x = w(z) için
    φᵀ Kg φ / (P ∫ (w')² dz) → 1 (göreli %1); çubuk elemanın Kg = P/L [[1, −1], [−1, 1]] karşılığı.
    """
    m = kutu_agi(B_KESIT, B_KESIT, L_CUBUK, 2, 2, 20, Material("celik", E, NU))
    sigma = P_CEKME / B_KESIT**2
    Kg = assemble_Kg(m, {e.id: np.array([0, 0, sigma, 0, 0, 0.0]) for e in m.elements})
    if w == "sinus":
        f = lambda z: np.sin(np.pi * z / L_CUBUK)  # noqa: E731
        integral = (np.pi / L_CUBUK) ** 2 * L_CUBUK / 2
    else:
        f = lambda z: (z / L_CUBUK) ** 2  # noqa: E731
        integral = 4 / (3 * L_CUBUK)
    phi = np.zeros(m.n_dof)
    for n in m.nodes:
        phi[m.dof_index(n.id, "ux")] = f(n.z)
    oran = phi @ (Kg @ phi) / (P_CEKME * integral)
    assert oran == pytest.approx(1.0, rel=1e-2)
