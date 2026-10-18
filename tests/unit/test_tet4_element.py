"""
tet4 eleman birim testleri (specs/11-tet4.md, K1–K6 ve K12).

Beklenen değerler SPEC'teki formüllerden el hesabıyla kurulur (C⁻¹, B, D, ke = V·BᵀDB);
uygulama kodu okunmadan yazılmıştır.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from core import post
from core.elements import tet4
from core.model import BC, Element, Load, Material, Model, ModelError, Node
from core.solver import solve
from tests.conftest import STEEL_E, make_bar

REL = 1e-12
NU = 0.3

# Birim köşe tetrahedronu: N1 = 1 − x − y − z, N2 = x, N3 = y, N4 = z
BIRIM = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
# Simetrisiz (genel) bir tetrahedron [mm]
GENEL = [(1.0, 2.0, -0.5), (13.0, 3.5, 1.0), (4.0, 11.0, 2.0), (3.0, 4.0, 9.5)]


def tek_tet(koseler, E: float = STEEL_E, nu: float = NU, dim: int = 3, sira=(1, 2, 3, 4)) -> Model:
    """Tek tet4 elemanlı model; düğüm id'leri 1..4, eleman düğüm sırası `sira`."""
    return Model(
        dim=dim,
        nodes=[Node(i + 1, *x) for i, x in enumerate(koseler)],
        elements=[Element(1, "tet4", list(sira), "celik")],
        materials=[Material("celik", E, nu)],
    )


def lame(E: float, nu: float) -> tuple[float, float]:
    return E * nu / ((1 + nu) * (1 - 2 * nu)), E / (2 * (1 + nu))


def D_el(E: float, nu: float) -> np.ndarray:
    """SPEC'teki D matrisi, elle."""
    lam, G = lame(E, nu)
    return np.array(
        [
            [lam + 2 * G, lam, lam, 0, 0, 0],
            [lam, lam + 2 * G, lam, 0, 0, 0],
            [lam, lam, lam + 2 * G, 0, 0, 0],
            [0, 0, 0, G, 0, 0],
            [0, 0, 0, 0, G, 0],
            [0, 0, 0, 0, 0, G],
        ],
        dtype=float,
    )


def B_birim_el() -> np.ndarray:
    """Birim köşe tetrahedronu için B: β = [−1, 1, 0, 0], γ = [−1, 0, 1, 0], δ = [−1, 0, 0, 1]."""
    beta, gamma, delta = [-1, 1, 0, 0], [-1, 0, 1, 0], [-1, 0, 0, 1]
    B = np.zeros((6, 12))
    for a in range(4):
        b, g, d = beta[a], gamma[a], delta[a]
        B[:, 3 * a : 3 * a + 3] = [[b, 0, 0], [0, g, 0], [0, 0, d], [g, b, 0], [d, 0, b], [0, d, g]]
    return B


def u_alan(model: Model, alan) -> np.ndarray:
    """Global DOF vektörü: her düğümde u = alan(x)."""
    u = np.zeros(model.n_dof)
    for n in model.nodes:
        for d, ad in enumerate(("ux", "uy", "uz")):
            u[model.dof_index(n.id, ad)] = alan(n.xyz)[d]
    return u


def voigt_tensor(s: np.ndarray) -> np.ndarray:
    """[xx, yy, zz, xy, xz, yz] -> 3x3 simetrik tensör (gerilme: kayma bileşenleri olduğu gibi)."""
    return np.array([[s[0], s[3], s[4]], [s[3], s[1], s[5]], [s[4], s[5], s[2]]])


def rastgele_R(tohum: int) -> np.ndarray:
    """Rastgele dönme matrisi (det = +1)."""
    Q, _ = np.linalg.qr(np.random.default_rng(tohum).normal(size=(3, 3)))
    if np.linalg.det(Q) < 0:
        Q[:, 0] = -Q[:, 0]
    return Q


# --- K1: Birim köşe tetrahedronu, el hesabı ------------------------------------


def test_K1_unit_tet_volume():
    m = tek_tet(BIRIM)
    assert tet4.volume(m.elements[0], m) == pytest.approx(1.0 / 6.0, rel=REL)


def test_K1_general_tet_volume():
    """V = |det [x2−x1, x3−x1, x4−x1]| / 6 (det C'nin eşdeğeri)."""
    m = tek_tet(GENEL)
    X = np.array(GENEL)
    beklenen = abs(np.linalg.det(X[1:] - X[0])) / 6.0
    assert tet4.volume(m.elements[0], m) == pytest.approx(beklenen, rel=REL)


def test_K1_unit_tet_B_exact():
    m = tek_tet(BIRIM)
    B = tet4.B(m.elements[0], m)
    assert B.shape == (6, 12)
    np.testing.assert_allclose(B, B_birim_el(), rtol=REL, atol=REL)


def test_K1_unit_tet_ke_exact():
    E = STEEL_E
    m = tek_tet(BIRIM, E=E, nu=NU)
    k = tet4.ke(m.elements[0], m)
    assert k.shape == (12, 12)
    beklenen = (1.0 / 6.0) * B_birim_el().T @ D_el(E, NU) @ B_birim_el()
    np.testing.assert_allclose(k, beklenen, rtol=REL, atol=REL * np.abs(beklenen).max())

    # Birkaç terim tamamen elle: köşe 1'de β = γ = δ = −1
    lam, G = lame(E, NU)
    assert k[0, 0] == pytest.approx((lam + 2 * G + G + G) / 6.0, rel=REL)  # u1-u1
    assert k[0, 1] == pytest.approx((lam + G) / 6.0, rel=REL)  # u1-v1: β1γ1(λ + G)
    assert k[3, 3] == pytest.approx((lam + 2 * G) / 6.0, rel=REL)  # u2-u2: sadece β2 = 1
    assert k[3, 4] == pytest.approx(0.0, abs=REL * k[0, 0])  # u2-v2: β2γ2 = 0
    assert k[3, 7] == pytest.approx(lam / 6.0, rel=REL)  # u2-v3: β2 γ3 λ
    assert k[4, 6] == pytest.approx(G / 6.0, rel=REL)  # v2-u3: β2 γ3 G


@pytest.mark.parametrize("koseler", [BIRIM, GENEL], ids=["birim", "genel"])
def test_K1_ke_symmetric_with_six_rigid_modes(koseler):
    m = tek_tet(koseler)
    k = tet4.ke(m.elements[0], m)
    np.testing.assert_allclose(k, k.T, rtol=0, atol=1e-14 * np.abs(k).max())
    lam = np.linalg.eigvalsh(0.5 * (k + k.T))
    lam_max = lam.max()
    sifir = np.abs(lam) <= 1e-10 * lam_max
    assert sifir.sum() == 6
    assert np.all(lam[~sifir] > 1e-10 * lam_max)


def test_K1_dofs_order():
    """dofs: [ux, uy, uz] her düğüm için, element.nodes sırasında, model.dof_index ile."""
    m = Model(
        dim=3,
        nodes=[Node(i, *x) for i, x in zip((10, 20, 30, 40, 50), [*GENEL, (0.0, 0.0, 0.0)], strict=True)],
        elements=[Element(7, "tet4", [30, 10, 40, 20], "celik")],
        materials=[Material("celik", STEEL_E, NU)],
    )
    beklenen = [m.dof_index(n, d) for n in (30, 10, 40, 20) for d in ("ux", "uy", "uz")]
    assert list(tet4.dofs(m.elements[0], m)) == beklenen


def test_K1_strain_of_linear_field():
    """u = u0 + H x için ε = [H11, H22, H33, H12 + H21, H13 + H31, H23 + H32] (mühendislik kayması)."""
    m = tek_tet(GENEL)
    H = np.array([[1.0, 2.0, -3.0], [0.5, -1.5, 4.0], [-2.5, 3.5, 0.7]]) * 1e-3
    u0 = np.array([0.1, -0.2, 0.3])
    u = u_alan(m, lambda x: u0 + H @ x)
    eps = tet4.strain(m.elements[0], m, u)
    beklenen = [H[0, 0], H[1, 1], H[2, 2], H[0, 1] + H[1, 0], H[0, 2] + H[2, 0], H[1, 2] + H[2, 1]]
    assert eps.shape == (6,)
    np.testing.assert_allclose(eps, beklenen, rtol=1e-12, atol=1e-15)
    sig = tet4.stress(m.elements[0], m, u)
    np.testing.assert_allclose(sig, D_el(STEEL_E, NU) @ np.array(beklenen), rtol=1e-12, atol=1e-9)


# --- K2: Rijit cisim hareketi ---------------------------------------------------


@pytest.mark.parametrize("koseler", [BIRIM, GENEL], ids=["birim", "genel"])
def test_K2_rigid_body_motion_gives_zero(koseler):
    m = tek_tet(koseler)
    e = m.elements[0]
    c = np.array([0.3, -1.2, 0.8])
    omega = np.array([2e-3, -1e-3, 3e-3])
    u = u_alan(m, lambda x: c + np.cross(omega, x))

    eps = tet4.strain(e, m, u)
    sig = tet4.stress(e, m, u)
    np.testing.assert_allclose(eps, 0.0, atol=1e-12 * np.abs(omega).max())
    np.testing.assert_allclose(sig, 0.0, atol=1e-9 * STEEL_E * np.abs(omega).max())

    k = tet4.ke(e, m)
    d = u[tet4.dofs(e, m)]
    np.testing.assert_allclose(k @ d, 0.0, atol=1e-9 * np.linalg.norm(k) * np.linalg.norm(d))


# --- K3: Düğüm sırası bağımsızlığı ---------------------------------------------


def test_K3_all_24_node_orders_agree():
    """24 permütasyon (sol el sıraları dahil): ke DOF bloklarına göre yeniden sıralanınca aynı, σ aynı."""
    m0 = tek_tet(GENEL)
    k0 = tet4.ke(m0.elements[0], m0)
    H = np.array([[1.0, -2.0, 0.5], [3.0, 0.2, -1.0], [0.4, 1.1, -0.6]]) * 1e-3
    u = u_alan(m0, lambda x: H @ x)
    s0 = tet4.stress(m0.elements[0], m0, u)

    sol_el = 0
    for sira in itertools.permutations((1, 2, 3, 4)):
        m = tek_tet(GENEL, sira=sira)
        X = np.array([GENEL[n - 1] for n in sira])
        sol_el += np.linalg.det(X[1:] - X[0]) < 0
        k = tet4.ke(m.elements[0], m)
        idx = [3 * (n - 1) + d for n in sira for d in range(3)]
        np.testing.assert_allclose(k, k0[np.ix_(idx, idx)], rtol=0, atol=REL * np.abs(k0).max())
        s = tet4.stress(m.elements[0], m, u)
        np.testing.assert_allclose(s, s0, rtol=0, atol=REL * np.abs(s0).max())
    assert sol_el == 12  # testin kendisi: iki yönelim de denendi


# --- K4: Döndürme değişmezliği -------------------------------------------------


@pytest.mark.parametrize("tohum", [1, 2, 3])
def test_K4_rotation_invariance(tohum):
    R = rastgele_R(tohum)
    m = tek_tet(GENEL)
    mR = tek_tet([tuple(R @ np.array(x)) for x in GENEL])
    T = np.kron(np.eye(4), R)

    k = tet4.ke(m.elements[0], m)
    kR = tet4.ke(mR.elements[0], mR)
    np.testing.assert_allclose(kR, T @ k @ T.T, rtol=0, atol=1e-12 * np.abs(k).max())

    # Doğrusal alan u(x) = H x; döndürülmüş cisimde u'(x') = R H Rᵀ x'
    H = np.array([[1.0, 2.0, -0.5], [-1.0, 0.3, 0.8], [0.6, -0.2, 1.4]]) * 1e-3
    u = u_alan(m, lambda x: H @ x)
    uR = u_alan(mR, lambda x: R @ H @ R.T @ x)
    S = voigt_tensor(tet4.stress(m.elements[0], m, u))
    SR = voigt_tensor(tet4.stress(mR.elements[0], mR, uR))
    np.testing.assert_allclose(SR, R @ S @ R.T, rtol=0, atol=1e-9 * np.abs(S).max())


# --- K5: D matrisi -------------------------------------------------------------


def test_K5_D_at_zero_poisson():
    E = 1000.0
    np.testing.assert_allclose(
        tet4.D(Material("m", E, 0.0)), np.diag([E, E, E, E / 2, E / 2, E / 2]), rtol=REL, atol=0
    )


def test_K5_D_matches_formula():
    E, nu = STEEL_E, NU
    D = tet4.D(Material("m", E, nu))
    assert D.shape == (6, 6)
    np.testing.assert_allclose(D, D_el(E, nu), rtol=REL, atol=REL * E)


@pytest.mark.parametrize("nu", [0.0, 0.3, 0.49, -0.5])
def test_K5_uniaxial_stress_inverse(nu):
    E, sigma = STEEL_E, 150.0
    D = tet4.D(Material("m", E, nu))
    eps = np.linalg.solve(D, np.array([sigma, 0, 0, 0, 0, 0]))
    beklenen = [sigma / E, -nu * sigma / E, -nu * sigma / E, 0, 0, 0]
    np.testing.assert_allclose(eps, beklenen, rtol=1e-10, atol=1e-12 * sigma / E)


# --- K6: Hatalar ModelError ----------------------------------------------------


def _ke(m: Model):
    return tet4.ke(m.elements[0], m)


def test_K6_dim_not_3():
    m = tek_tet(BIRIM, dim=2)
    with pytest.raises(ModelError):
        _ke(m)


@pytest.mark.parametrize("dugumler", [[1, 2, 3], [1, 2, 3, 4, 5]], ids=["3_dugum", "5_dugum"])
def test_K6_wrong_node_count(dugumler):
    m = tek_tet([*BIRIM, (1.0, 1.0, 1.0)])
    m.elements = [Element(1, "tet4", dugumler, "celik")]
    with pytest.raises(ModelError):
        _ke(m)


def test_K6_repeated_node():
    m = tek_tet(BIRIM, sira=(1, 2, 3, 3))
    with pytest.raises(ModelError):
        _ke(m)


@pytest.mark.parametrize(
    "koseler",
    [
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)],  # tam düzlemsel
        [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0), (3.0, 3.0, 1e-12)],  # V << 1e-12 ℓ³
    ],
    ids=["duzlemsel", "neredeyse_duzlemsel"],
)
def test_K6_flat_element(koseler):
    m = tek_tet(koseler)
    with pytest.raises(ModelError):
        tet4.volume(m.elements[0], m)
    with pytest.raises(ModelError):
        _ke(m)


@pytest.mark.parametrize("nu", [0.5, 0.7, -1.0, -1.5])
def test_K6_invalid_poisson(nu):
    with pytest.raises(ModelError):
        tet4.D(Material("m", STEEL_E, nu))
    with pytest.raises(ModelError):
        _ke(tek_tet(BIRIM, nu=nu))


# --- K12: post.element_stress_tensors ve solve() ------------------------------


def _iki_tet_model() -> Model:
    """İki tetrahedronlu, rijit cisim modları tutulmuş küçük model (uç düğüm çekiliyor)."""
    koseler = [*BIRIM, (1.0, 1.0, 1.0)]
    return Model(
        dim=3,
        nodes=[Node(i + 1, *x) for i, x in enumerate(koseler)],
        elements=[Element(1, "tet4", [1, 2, 3, 4], "celik"), Element(2, "tet4", [2, 3, 4, 5], "celik")],
        materials=[Material("celik", STEEL_E, NU)],
        bcs=[
            BC(1, "ux"),
            BC(1, "uy"),
            BC(1, "uz"),
            BC(2, "uy"),
            BC(2, "uz"),
            BC(3, "uz"),
        ],
        loads=[Load(5, "ux", 100.0), Load(5, "uz", -50.0)],
    )


def test_K12_stress_tensors_per_tet4():
    m = _iki_tet_model()
    r = solve(m)
    sig = post.element_stress_tensors(m, r.u)
    assert set(sig) == {1, 2}
    for e in m.elements:
        assert np.asarray(sig[e.id]).shape == (6,)
        np.testing.assert_allclose(sig[e.id], tet4.stress(e, m, r.u), rtol=1e-12, atol=1e-12)


def test_K12_solve_tet4_has_no_axial_results():
    m = _iki_tet_model()
    r = solve(m)
    assert r.element_forces == {}
    assert r.element_stresses == {}
    assert np.all(np.isfinite(r.u))


def test_K12_bar1d_unchanged():
    """bar1d sonuçları aynı; bar1d gerilme tensörü sağlamaz -> element_stress_tensors boş."""
    F, A = 10_000.0, 100.0
    m = make_bar(n_elem=3, A=A, tip_load=F)
    r = solve(m)
    for e in m.elements:
        assert r.element_forces[e.id] == pytest.approx(F, rel=1e-9)
        assert r.element_stresses[e.id] == pytest.approx(F / A, rel=1e-9)
    assert post.element_stress_tensors(m, r.u) == {}
