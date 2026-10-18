"""
SPEC 13 — gerilme sonrası işlem birim testleri (K1–K4): von Mises, asal gerilmeler, düğüm gerilmesi.

Beklenen değerler SPEC 13 Teori bölümündeki formüllerden el hesabıyla kurulur; uygulama kodu okunmadan
yazılmıştır. Voigt düzeni: σ = [σ_xx, σ_yy, σ_zz, τ_xy, τ_xz, τ_yz].
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core import post
from core.model import BC, Element, Material, Model, ModelError, Node
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri, yuzey_cekmesi
from tests.conftest import STEEL_E, make_bar

REL = 1e-12


def voigt(S: np.ndarray) -> np.ndarray:
    """3x3 simetrik tensör → Voigt (6,)."""
    return np.array([S[0, 0], S[1, 1], S[2, 2], S[0, 1], S[0, 2], S[1, 2]])


def tensor(s) -> np.ndarray:
    """Voigt (6,) → 3x3 simetrik tensör."""
    xx, yy, zz, xy, xz, yz = s
    return np.array([[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]], dtype=float)


def vm_el(s) -> float:
    """SPEC'teki von Mises formülü, elle."""
    xx, yy, zz, xy, xz, yz = s
    return math.sqrt(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3 * (xy**2 + xz**2 + yz**2))


def rastgele_R(rng: np.random.Generator) -> np.ndarray:
    """Rastgele dönme matrisi (det = +1)."""
    Q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    if np.linalg.det(Q) < 0:
        Q[:, 0] *= -1
    return Q


def rastgele_sigma(rng: np.random.Generator, n: int | None = None) -> np.ndarray:
    shape = (6,) if n is None else (n, 6)
    return rng.uniform(-300.0, 300.0, size=shape)


# --- K1: von Mises ---------------------------------------------------------------


@pytest.mark.parametrize("s", [150.0, -80.0, 1e-3])
def test_von_mises_uniaxial(s):
    """Tek eksen: σ_vM = |σ| (her eksende)."""
    for i in range(3):
        sigma = np.zeros(6)
        sigma[i] = s
        v = post.von_mises(sigma)
        assert isinstance(v, float)
        assert v == pytest.approx(abs(s), rel=REL)


@pytest.mark.parametrize("i", [3, 4, 5])
@pytest.mark.parametrize("tau", [40.0, -25.0])
def test_von_mises_pure_shear(i, tau):
    """Saf kayma (τ_xy, τ_xz, τ_yz ayrı ayrı): σ_vM = √3 |τ|."""
    sigma = np.zeros(6)
    sigma[i] = tau
    assert post.von_mises(sigma) == pytest.approx(math.sqrt(3.0) * abs(tau), rel=REL)


@pytest.mark.parametrize("p", [100.0, -250.0])
def test_von_mises_hydrostatic_is_zero(p):
    """Hidrostatik gerilme: σ_vM = 0 (≤ 1e-12 |p|)."""
    v = post.von_mises(np.array([p, p, p, 0.0, 0.0, 0.0]))
    assert abs(v) <= 1e-12 * abs(p)


def test_von_mises_biaxial_tension_compression():
    """σ_xx = a, σ_yy = −b: σ_vM = √(a² + ab + b²)."""
    a, b = 120.0, 70.0
    v = post.von_mises(np.array([a, -b, 0.0, 0.0, 0.0, 0.0]))
    assert v == pytest.approx(math.sqrt(a * a + a * b + b * b), rel=REL)


def test_von_mises_general_matches_formula():
    rng = np.random.default_rng(13)
    for _ in range(20):
        s = rastgele_sigma(rng)
        assert post.von_mises(s) == pytest.approx(vm_el(s), rel=REL)


def test_von_mises_rotation_invariant():
    """S' = R S Rᵀ için σ_vM aynı (rel 1e-12)."""
    rng = np.random.default_rng(7)
    for _ in range(20):
        s = rastgele_sigma(rng)
        R = rastgele_R(rng)
        s2 = voigt(R @ tensor(s) @ R.T)
        assert post.von_mises(s2) == pytest.approx(post.von_mises(s), rel=REL)


def test_von_mises_batch_rows():
    """(n, 6) girdi → (n,), satır satır tek tek çağrıyla aynı."""
    rng = np.random.default_rng(3)
    S = rastgele_sigma(rng, 15)
    v = post.von_mises(S)
    assert isinstance(v, np.ndarray) and v.shape == (15,)
    beklenen = np.array([vm_el(s) for s in S])
    np.testing.assert_allclose(v, beklenen, rtol=REL)
    np.testing.assert_allclose(v, [post.von_mises(s) for s in S], rtol=REL)


def test_von_mises_accepts_list():
    assert post.von_mises([100.0, 0, 0, 0, 0, 0]) == pytest.approx(100.0, rel=REL)


# --- K2: asal gerilmeler ------------------------------------------------------------


def test_principal_diagonal_sorted():
    """Köşegen tensör: asal gerilmeler köşegenin azalan sıralısı."""
    p = post.principal_stresses(np.array([3.0, -1.0, 7.0, 0.0, 0.0, 0.0]))
    assert np.shape(p) == (3,)
    np.testing.assert_allclose(p, [7.0, 3.0, -1.0], rtol=REL)


def test_principal_random_matches_eigvalsh():
    """Rastgele simetrik tensör: numpy.linalg.eigvalsh ile aynı, azalan; Σ σ_i = iz(S)."""
    rng = np.random.default_rng(11)
    for _ in range(30):
        s = rastgele_sigma(rng)
        p = np.asarray(post.principal_stresses(s))
        beklenen = np.sort(np.linalg.eigvalsh(tensor(s)))[::-1]
        olcek = np.max(np.abs(beklenen))
        np.testing.assert_allclose(p, beklenen, rtol=REL, atol=REL * olcek)
        assert p[0] >= p[1] >= p[2]
        assert p.sum() == pytest.approx(s[0] + s[1] + s[2], abs=REL * 10 * np.abs(s[:3]).sum())


def test_principal_von_mises_consistent():
    """Asal gerilmelerden von Mises = von_mises (rel 1e-12)."""
    rng = np.random.default_rng(5)
    for _ in range(30):
        s = rastgele_sigma(rng)
        s1, s2, s3 = post.principal_stresses(s)
        vm = math.sqrt(0.5 * ((s1 - s2) ** 2 + (s2 - s3) ** 2 + (s3 - s1) ** 2))
        assert vm == pytest.approx(post.von_mises(s), rel=1e-11 if vm < 1.0 else REL)


def test_principal_rotation_invariant():
    rng = np.random.default_rng(17)
    s = rastgele_sigma(rng)
    R = rastgele_R(rng)
    p1 = np.asarray(post.principal_stresses(s))
    p2 = np.asarray(post.principal_stresses(voigt(R @ tensor(s) @ R.T)))
    np.testing.assert_allclose(p2, p1, rtol=REL, atol=REL * np.max(np.abs(p1)))


def test_principal_batch_rows():
    """(n, 6) → (n, 3), her satır azalan ve tek çağrıyla aynı."""
    rng = np.random.default_rng(23)
    S = rastgele_sigma(rng, 12)
    P = post.principal_stresses(S)
    assert isinstance(P, np.ndarray) and P.shape == (12, 3)
    for s, p in zip(S, P, strict=True):
        tek = np.asarray(post.principal_stresses(s))
        np.testing.assert_allclose(p, tek, rtol=REL, atol=REL * np.max(np.abs(tek)))
        assert p[0] >= p[1] >= p[2]


def test_principal_hydrostatic_and_shear():
    """Hidrostatik p: üçü de p. Saf kayma τ_xy: (τ, 0, −τ)."""
    np.testing.assert_allclose(post.principal_stresses([50.0, 50.0, 50.0, 0, 0, 0]), [50.0] * 3, rtol=REL)
    p = np.asarray(post.principal_stresses([0, 0, 0, 30.0, 0, 0]))
    np.testing.assert_allclose(p, [30.0, 0.0, -30.0], rtol=REL, atol=REL * 30.0)


# --- K3: hatalar ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "sigma",
    [
        np.zeros(5),
        np.zeros((2, 3, 6)),
        np.zeros((4, 5)),
        np.array(1.0),
        np.array([1.0, np.nan, 0.0, 0.0, 0.0, 0.0]),
        np.array([[1.0, 0.0, 0.0, 0.0, 0.0, 0.0], [0.0, 0.0, np.inf, 0.0, 0.0, 0.0]]),
    ],
    ids=["(5,)", "(2,3,6)", "(4,5)", "skaler", "nan", "inf"],
)
@pytest.mark.parametrize("fonk", [post.von_mises, post.principal_stresses], ids=["vm", "asal"])
def test_bad_input_raises(fonk, sigma):
    with pytest.raises(ModelError):
        fonk(sigma)


# --- K4: düğüm gerilmesi ---------------------------------------------------------------

GENEL = [(1.0, 2.0, -0.5), (13.0, 3.5, 1.0), (4.0, 11.0, 2.0), (3.0, 4.0, 9.5)]
NU = 0.3


def hacim(model: Model, e: Element) -> float:
    """V = |det [x2 − x1, x3 − x1, x4 − x1]| / 6 (elle)."""
    X = np.array([model.node(n).xyz for n in e.nodes])
    return abs(np.linalg.det(X[1:] - X[0])) / 6.0


def test_single_element_nodes_equal_element_stress():
    """Tek eleman: dört düğüm = eleman gerilmesi; elemana ait olmayan düğüm sözlükte yok."""
    nodes = [Node(i + 1, *x) for i, x in enumerate(GENEL)] + [Node(9, 50.0, 50.0, 50.0)]
    m = Model(
        dim=3,
        nodes=nodes,
        elements=[Element(1, "tet4", [1, 2, 3, 4], "celik")],
        materials=[Material("celik", STEEL_E, NU)],
    )
    u = np.random.default_rng(1).uniform(-0.01, 0.01, m.n_dof)
    sigma_e = post.element_stress_tensors(m, u)[1]
    d = post.nodal_stress_tensors(m, u)
    assert set(d) == {1, 2, 3, 4}
    for nid in (1, 2, 3, 4):
        assert np.shape(d[nid]) == (6,)
        np.testing.assert_allclose(d[nid], sigma_e, rtol=REL, atol=REL * np.max(np.abs(sigma_e)))


@pytest.mark.parametrize("ters", [False, True], ids=["pozitif-sira", "negatif-sira"])
def test_two_elements_volume_weighted(ters):
    """Düğüm paylaşan iki eleman: ortak düğümde (V1σ1 + V2σ2)/(V1 + V2), diğerlerinde kendi σ'sı.
    Negatif sıralı elemanın ağırlığı da pozitif hacimdir (V = |det C| / 6)."""
    X = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 8.0, 0.0), (0.0, 0.0, 6.0), (9.0, 9.0, 14.0)]
    ikinci = [2, 4, 3, 5] if ters else [2, 3, 4, 5]
    m = Model(
        dim=3,
        nodes=[Node(10 * (i + 1), *x) for i, x in enumerate(X)],
        elements=[
            Element(7, "tet4", [10, 20, 30, 40], "celik"),
            Element(3, "tet4", [10 * k for k in ikinci], "al"),
        ],
        materials=[Material("celik", STEEL_E, NU), Material("al", 70_000.0, 0.33)],
    )
    u = np.random.default_rng(2).uniform(-0.02, 0.02, m.n_dof)
    s = post.element_stress_tensors(m, u)
    V1, V2 = hacim(m, m.elements[0]), hacim(m, m.elements[1])
    assert V1 != pytest.approx(V2)
    ortak = (V1 * s[7] + V2 * s[3]) / (V1 + V2)
    d = post.nodal_stress_tensors(m, u)
    assert set(d) == {10, 20, 30, 40, 50}
    olcek = max(np.max(np.abs(s[7])), np.max(np.abs(s[3])))
    for nid in (20, 30, 40):
        np.testing.assert_allclose(d[nid], ortak, rtol=REL, atol=REL * olcek)
    np.testing.assert_allclose(d[10], s[7], rtol=REL, atol=REL * olcek)
    np.testing.assert_allclose(d[50], s[3], rtol=REL, atol=REL * olcek)


@pytest.mark.parametrize("kaydirma", [0.0, 0.2])
def test_uniform_tension_every_node(kaydirma):
    """Düzgün çekme (SPEC 11 yapılandırılmış ağ): her düğümde σ = (σ, 0, 0, 0, 0, 0) (rel 1e-9)."""
    L, b, h, sigma = 30.0, 12.0, 9.0, 80.0
    m = kutu_agi(L, b, h, 5, 3, 3, Material("celik", STEEL_E, NU), kaydirma=kaydirma, tohum=4)
    for eksen, ad in ((0, "ux"), (1, "uy"), (2, "uz")):
        m.bcs.extend(BC(n, ad, 0.0) for n in yuz_dugumleri(m, eksen, 0.0))
    m.loads = yuzey_cekmesi(m, 0, L, (sigma, 0.0, 0.0))
    r = solve(m)
    d = post.nodal_stress_tensors(m, r.u)
    assert set(d) == {n.id for n in m.nodes}
    beklenen = np.array([sigma, 0.0, 0.0, 0.0, 0.0, 0.0])
    for nid in d:
        np.testing.assert_allclose(d[nid], beklenen, rtol=1e-9, atol=1e-9 * sigma)


def test_bar_model_gives_empty_dict():
    """Çubuk (bar1d) modelinde katı eleman yok: boş sözlük."""
    m = make_bar(n_elem=3)
    r = solve(m)
    assert post.nodal_stress_tensors(m, r.u) == {}


def test_existing_post_functions_unchanged():
    """K9: mevcut post fonksiyonları ve Result aynı kalır."""
    m = make_bar(n_elem=2, tip_load=10_000.0, A=100.0)
    r = solve(m)
    assert post.element_stresses(m, r.u) == pytest.approx({1: 100.0, 2: 100.0}, rel=REL)
    assert r.element_stresses == pytest.approx({1: 100.0, 2: 100.0}, rel=REL)
    assert post.element_stress_tensors(m, r.u) == {}
