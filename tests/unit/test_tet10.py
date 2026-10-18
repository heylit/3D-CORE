"""
tet10 eleman birim testleri (specs/67-fem-genisletme.md, 67a: K1, K3, K8 kütle, K10, D5 ve
`mesh` tet10 sınır üçgenleri / tri6 yükleri).

Beklenen değerler SPEC'in Teori formüllerinden testin kendi araçlarıyla (tests/benchmarks/tet10_ag.py)
kurulur; core/elements/tet10.py okunmadan yazılmıştır.

Şekil fonksiyonları arayüzde yoktur; K1 gözlenebilir sonuçlarıyla sınanır:
- Σ ∂N/∂x = 0  ⇔  öteleme sıfır şekil değiştirme verir, ke · d_öteleme = 0
- Σ N = 1 ve ∫ N_a dV  ⇔  kütle matrisinin satır toplamı ρ ∫ N_a dV (köşe −ρV/20, kenar ρV/5)
- N_i(x_j) = δ_ij ve düğüm sırası  ⇔  tutarlı kütle ρ ∫ N_a N_b dV kesin değerine eşit, ikinci dereceden
  alanın düğüm değerleri Gauss noktalarında kesin şekil değiştirmeyi verir
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

import mesh
from core import post
from core.elements import tet10
from core.model import BC, Element, Load, Material, Model, ModelError, Node
from core.solver import solve
from tests.benchmarks.tet10_ag import (
    GAUSS_L,
    KENARLAR,
    D_matrisi,
    M_kesin,
    N_integrali,
    dN_dx,
    gauss_konumlari,
    ke_referans,
    koordinatlar,
    kutu_agi10,
)
from tests.benchmarks.tet_ag import kutu_agi

E, NU, RHO = 210_000.0, 0.3, 7.85e-9
REL = 1e-12
DOFS = ("ux", "uy", "uz")

# Birim köşe tetrahedronu ve simetrisiz genel bir tetrahedron (sağ el sırası), köşeler
BIRIM = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
GENEL = np.array([[1.0, 2.0, -0.5], [13.0, 3.5, 1.0], [4.0, 11.0, 2.0], [3.0, 4.0, 9.5]])


def on_dugum(kose: np.ndarray) -> np.ndarray:
    """Köşelerden 10 düğüm: kenar düğümleri kenar ortasında (C3D10 sırası)."""
    return np.vstack([kose] + [0.5 * (kose[i] + kose[j]) for i, j in KENARLAR])


def tek_tet10(X: np.ndarray, nu: float = NU, rho: float = RHO, eid: int = 1, sira=None) -> Model:
    """Tek tet10 elemanlı model; düğüm id'leri 1..10."""
    return Model(
        dim=3,
        nodes=[Node(i + 1, *x) for i, x in enumerate(X)],
        elements=[Element(eid, "tet10", list(sira or range(1, 11)), "celik")],
        materials=[Material("celik", E, nu, rho)],
    )


def u_alan(model: Model, alan) -> np.ndarray:
    u = np.zeros(model.n_dof)
    for n in model.nodes:
        for d, ad in enumerate(DOFS):
            u[model.dof_index(n.id, ad)] = alan(n.xyz)[d]
    return u


def V_kose(kose: np.ndarray) -> float:
    return abs(np.linalg.det(kose[1:] - kose[0])) / 6.0


def rastgele_R(tohum: int) -> np.ndarray:
    Q, _ = np.linalg.qr(np.random.default_rng(tohum).normal(size=(3, 3)))
    if np.linalg.det(Q) < 0:
        Q[:, 0] = -Q[:, 0]
    return Q


# İkinci dereceden genel alan: u_i = Σ_j H_ij x_j + Σ_jk Q_ijk x_j x_k (Q_ijk = Q_ikj)
_rng = np.random.default_rng(67)
H2 = _rng.normal(size=(3, 3)) * 1e-3
Q2 = _rng.normal(size=(3, 3, 3)) * 1e-4
Q2 = 0.5 * (Q2 + Q2.transpose(0, 2, 1))


def u_kare(x: np.ndarray) -> np.ndarray:
    return H2 @ x + np.einsum("ijk,j,k->i", Q2, x, x)


def eps_kare(x: np.ndarray) -> np.ndarray:
    """∂u_i/∂x_j = H_ij + 2 Q_ijk x_k → Voigt (mühendislik kayması)."""
    g = H2 + 2.0 * np.einsum("ijk,k->ij", Q2, x)
    return np.array([g[0, 0], g[1, 1], g[2, 2], g[0, 1] + g[1, 0], g[0, 2] + g[2, 0], g[1, 2] + g[2, 1]])


def satir_eslestir(bulunan: np.ndarray, beklenen: np.ndarray, atol: float) -> None:
    """Gauss noktalarının sırası SPEC'te sabit değil: satırlar bire bir eşleşmeli (bir permütasyon)."""
    assert bulunan.shape == beklenen.shape
    kalan = list(range(len(beklenen)))
    for satir in bulunan:
        fark = [np.abs(satir - beklenen[j]).max() for j in kalan]
        j = int(np.argmin(fark))
        assert fark[j] <= atol, f"eşleşmeyen satır {satir}, en yakın fark {fark[j]:.3e} > {atol:.3e}"
        kalan.pop(j)


# --- K1: şekil fonksiyonları (gözlenebilir sonuçlar) ---------------------------------------


@pytest.mark.parametrize("kose", [BIRIM, GENEL], ids=["birim", "genel"])
def test_K1_volume(kose):
    m = tek_tet10(on_dugum(kose))
    assert tet10.volume(m.elements[0], m) == pytest.approx(V_kose(kose), rel=REL)


@pytest.mark.parametrize("kose", [BIRIM, GENEL], ids=["birim", "genel"])
def test_K1_translation_gives_zero_strain(kose):
    """Σ ∂N/∂x = 0: öteleme her Gauss noktasında sıfır gerilme ve ke · d = 0 verir."""
    m = tek_tet10(on_dugum(kose))
    e = m.elements[0]
    c = np.array([0.3, -1.2, 0.8])
    u = u_alan(m, lambda x: c)
    s = tet10.stress_gauss(e, m, u)
    assert s.shape == (4, 6)
    np.testing.assert_allclose(s, 0.0, atol=1e-14 * E)
    k = tet10.ke(e, m)
    d = u[tet10.dofs(e, m)]
    np.testing.assert_allclose(k @ d, 0.0, atol=1e-12 * np.abs(k).max() * np.abs(d).max())


def test_K1_reference_tet_N_integrals():
    """Referans tetrahedronda ∫ N_köşe dV = −V/20, ∫ N_kenar dV = V/5 (abs 1e-14): M satır toplamı / ρ."""
    m = tek_tet10(on_dugum(BIRIM), rho=1.0)
    M = tet10.me(m.elements[0], m)
    V = 1.0 / 6.0
    satir = M[0::3, 0::3].sum(axis=1)  # x yönü, ΣN_b = 1 olduğundan Σ_b M_ab = ρ ∫ N_a dV
    beklenen = np.array([-V / 20] * 4 + [V / 5] * 6)
    np.testing.assert_allclose(N_integrali(V), beklenen, rtol=0, atol=1e-15)  # testin kendi aritmetiği
    np.testing.assert_allclose(satir, beklenen, rtol=0, atol=1e-14)


@pytest.mark.parametrize("kose", [BIRIM, GENEL], ids=["birim", "genel"])
def test_K1_quadratic_field_exact_at_gauss_points(kose):
    """N_i(x_j) = δ_ij ve tam 2. derece taban: düğümlere yazılan 2. derece alan Gauss noktalarında
    kesin ε verir."""
    X = on_dugum(kose)
    m = tek_tet10(X)
    e = m.elements[0]
    u = u_alan(m, u_kare)
    D = D_matrisi(E, NU)
    beklenen = np.array([D @ eps_kare(x) for x in gauss_konumlari(X)])
    s = tet10.stress_gauss(e, m, u)
    satir_eslestir(s, beklenen, atol=1e-9 * np.abs(beklenen).max())
    np.testing.assert_allclose(tet10.stress(e, m, u), s.mean(axis=0), rtol=0, atol=1e-12 * np.abs(s).max())


# --- K3: eleman matrisi ---------------------------------------------------------------------


@pytest.mark.parametrize("kose", [BIRIM, GENEL], ids=["birim", "genel"])
def test_K3_ke_matches_own_gauss_integration(kose):
    X = on_dugum(kose)
    m = tek_tet10(X)
    k = tet10.ke(m.elements[0], m)
    assert k.shape == (30, 30)
    beklenen = ke_referans(X, E, NU)
    np.testing.assert_allclose(k, beklenen, rtol=0, atol=REL * np.abs(beklenen).max())


@pytest.mark.parametrize("kose", [BIRIM, GENEL], ids=["birim", "genel"])
def test_K3_ke_symmetric_with_six_rigid_modes(kose):
    m = tek_tet10(on_dugum(kose))
    k = tet10.ke(m.elements[0], m)
    np.testing.assert_allclose(k, k.T, rtol=0, atol=1e-14 * np.abs(k).max())
    lam = np.linalg.eigvalsh(0.5 * (k + k.T))
    sifir = np.abs(lam) <= 1e-10 * lam.max()
    assert sifir.sum() == 6
    assert np.all(lam[~sifir] > 0.0)


def test_K3_rigid_rotation_in_kernel():
    m = tek_tet10(on_dugum(GENEL))
    e = m.elements[0]
    omega = np.array([2e-3, -1e-3, 3e-3])
    u = u_alan(m, lambda x: np.cross(omega, x))
    k = tet10.ke(e, m)
    d = u[tet10.dofs(e, m)]
    np.testing.assert_allclose(k @ d, 0.0, atol=1e-10 * np.linalg.norm(k) * np.linalg.norm(d))
    np.testing.assert_allclose(tet10.stress_gauss(e, m, u), 0.0, atol=1e-9 * E * np.abs(omega).max())


def test_K3_translation_invariance():
    X = on_dugum(GENEL)
    m, mt = tek_tet10(X), tek_tet10(X + np.array([150.0, -40.0, 75.0]))
    k, kt = tet10.ke(m.elements[0], m), tet10.ke(mt.elements[0], mt)
    np.testing.assert_allclose(kt, k, rtol=0, atol=1e-11 * np.abs(k).max())


@pytest.mark.parametrize("tohum", [1, 2, 3])
def test_K3_rotation_invariance(tohum):
    R = rastgele_R(tohum)
    X = on_dugum(GENEL)
    m, mR = tek_tet10(X), tek_tet10(X @ R.T)
    T = np.kron(np.eye(10), R)
    k, kR = tet10.ke(m.elements[0], m), tet10.ke(mR.elements[0], mR)
    np.testing.assert_allclose(kR, T @ k @ T.T, rtol=0, atol=1e-11 * np.abs(k).max())


def test_K3_dofs_order():
    """dofs: [ux, uy, uz] her düğüm için, element.nodes sırasında, model.dof_index ile."""
    X = on_dugum(GENEL)
    ids = [10 * (i + 1) for i in range(10)]
    m = Model(
        dim=3,
        nodes=[Node(ids[i], *X[i]) for i in range(10)][::-1],  # düğüm listesi eleman sırasının tersi
        elements=[Element(3, "tet10", ids, "celik")],
        materials=[Material("celik", E, NU, RHO)],
    )
    beklenen = [m.dof_index(n, d) for n in ids for d in DOFS]
    assert list(tet10.dofs(m.elements[0], m)) == beklenen


# --- D5: düğüm gerilmeleri ----------------------------------------------------------------


def test_D5_stress_nodes_exact_for_linear_stress():
    """2. derece alan → doğrusal σ: köşelere doğrusal dış değerleme ve kenar ortalaması her düğümde kesin."""
    X = on_dugum(GENEL)
    m = tek_tet10(X)
    u = u_alan(m, u_kare)
    D = D_matrisi(E, NU)
    beklenen = np.array([D @ eps_kare(x) for x in X])
    s = tet10.stress_nodes(m.elements[0], m, u)
    assert s.shape == (10, 6)
    np.testing.assert_allclose(s, beklenen, rtol=0, atol=1e-9 * np.abs(beklenen).max())


def test_D5_stress_nodes_corner_extrapolation_and_edge_mean():
    """Genel (doğrusal olmayan σ) alanda: kenar düğümü iki köşesinin ortalaması; Gauss değerleri köşelerin
    doğrusal alanından geri okunur (dış değerleme Gauss değerlerini tam geçirir)."""
    X = on_dugum(GENEL)
    m = tek_tet10(X)
    e = m.elements[0]
    u = np.random.default_rng(5).normal(size=m.n_dof) * 1e-3
    sn = tet10.stress_nodes(e, m, u)
    for a, (i, j) in enumerate(KENARLAR):
        np.testing.assert_allclose(sn[4 + a], 0.5 * (sn[i] + sn[j]), rtol=0, atol=1e-10 * np.abs(sn).max())
    # Köşe değerlerinden doğrusal (L) enterpolasyon Gauss noktalarında Gauss değerlerini vermeli
    sg = tet10.stress_gauss(e, m, u)
    geri = GAUSS_L @ sn[:4]
    satir_eslestir(geri, sg, atol=1e-9 * np.abs(sg).max())


def test_D5_post_nodal_stress_tensors_volume_weighted():
    """post.nodal_stress_tensors tet10'da stress_nodes değerlerinin hacim ağırlıklı ortalaması."""
    m = kutu_agi10(4.0, 2.0, 2.0, 2, 1, 1, Material("celik", E, NU, RHO), kaydirma=0.0)
    u = np.random.default_rng(11).normal(size=m.n_dof) * 1e-3
    pay: dict[int, np.ndarray] = {}
    payda: dict[int, float] = {}
    for e in m.elements:
        V = tet10.volume(e, m)
        for n, s in zip(e.nodes, tet10.stress_nodes(e, m, u), strict=True):
            pay[n] = pay.get(n, np.zeros(6)) + V * s
            payda[n] = payda.get(n, 0.0) + V
    d = post.nodal_stress_tensors(m, u)
    assert set(d) == {n.id for n in m.nodes}
    olcek = max(np.abs(v).max() for v in pay.values()) / min(payda.values())
    for n in d:
        np.testing.assert_allclose(d[n], pay[n] / payda[n], rtol=0, atol=1e-10 * olcek)


def test_D5_post_element_stress_tensors_is_gauss_mean():
    m = kutu_agi10(4.0, 2.0, 2.0, 2, 1, 1, Material("celik", E, NU, RHO))
    u = np.random.default_rng(12).normal(size=m.n_dof) * 1e-3
    S = post.element_stress_tensors(m, u)
    assert set(S) == {e.id for e in m.elements}
    for e in m.elements:
        np.testing.assert_allclose(S[e.id], tet10.stress_gauss(e, m, u).mean(axis=0), rtol=1e-12, atol=1e-9)


# --- K8: kütle matrisi ------------------------------------------------------------------


@pytest.mark.parametrize("kose", [BIRIM, GENEL], ids=["birim", "genel"])
def test_K8_mass_total_is_rho_V(kose):
    """Σ_ab M_ab (tek yön) = ρ V (rel 1e-12); diğer yönlerle bağlaşım yok."""
    m = tek_tet10(on_dugum(kose))
    M = tet10.me(m.elements[0], m)
    assert M.shape == (30, 30)
    rhoV = RHO * V_kose(kose)
    for d in range(3):
        assert M[d::3, d::3].sum() == pytest.approx(rhoV, rel=REL)
    assert np.abs(M[0::3, 1::3]).max() <= 1e-14 * np.abs(M).max()


@pytest.mark.parametrize("kose", [BIRIM, GENEL], ids=["birim", "genel"])
def test_K8_consistent_mass_exact(kose):
    """M = ρ ∫ N_a N_b dV ⊗ I₃, kesin polinom integrali ile (düz kenarlı eleman; rel 1e-12)."""
    m = tek_tet10(on_dugum(kose))
    M = tet10.me(m.elements[0], m)
    beklenen = M_kesin(V_kose(kose), RHO)
    np.testing.assert_allclose(M, beklenen, rtol=0, atol=REL * np.abs(beklenen).max())
    np.testing.assert_allclose(M, M.T, rtol=0, atol=1e-15 * np.abs(M).max())


def test_K8_lumped_mass_rejected():
    m = tek_tet10(on_dugum(BIRIM))
    with pytest.raises(ModelError):
        tet10.me(m.elements[0], m, lumped=True)


# --- K10: hatalar -----------------------------------------------------------------------


def sol_el(kose: np.ndarray) -> np.ndarray:
    """Köşe 2 ↔ 3 değişmiş (sol el) ama kenar düğümleri C3D10 kuralına uygun yeniden eşlenmiş eleman."""
    return on_dugum(kose[[0, 2, 1, 3]])


def test_K10_inverted_element_raises_with_element_id():
    X = sol_el(GENEL)
    assert np.linalg.det(X[1:4] - X[0]) < 0  # testin kendisi: gerçekten sol el
    m = tek_tet10(X, eid=4711)
    with pytest.raises(ModelError, match="4711"):
        tet10.ke(m.elements[0], m)
    with pytest.raises(ModelError):
        tet10.volume(m.elements[0], m)


def test_K10_distorted_mid_node_negative_jacobian_raises():
    """Hacmi pozitif ama bir kenar düğümü öyle kaymış ki bazı Gauss noktalarında det J ≤ 0."""
    X = on_dugum(BIRIM)
    X[4] = [0.5, 0.0, 0.7]  # 1–2 kenar düğümü kenar ortasından çok yukarı
    detler = [dN_dx(X, L)[1] for L in GAUSS_L]
    assert min(detler) <= 0.0 < sum(detler)  # testin kendisi: Σ w det J > 0 ama bir noktada det J < 0
    m = tek_tet10(X, eid=12)
    with pytest.raises(ModelError, match="12"):
        tet10.ke(m.elements[0], m)


def test_K10_nine_node_tet10_raises():
    m = tek_tet10(on_dugum(BIRIM))
    m.elements = [Element(1, "tet10", list(range(1, 10)), "celik")]
    with pytest.raises(ModelError):
        tet10.ke(m.elements[0], m)


def test_K10_mixed_tet4_tet10_boundary_triangles_raises():
    m4 = kutu_agi(2.0, 1.0, 1.0, 2, 1, 1, Material("celik", E, NU))
    m10 = kutu_agi10(2.0, 1.0, 1.0, 2, 1, 1, Material("celik", E, NU))
    karisik = Model(
        dim=3,
        nodes=m10.nodes,
        elements=[m10.elements[0], Element(999, "tet4", m4.elements[-1].nodes, "celik")],
        materials=m10.materials,
    )
    with pytest.raises(ModelError):
        mesh.boundary_triangles(karisik)


# --- mesh: tet10 sınır üçgenleri ve tri6 yükleri ------------------------------------------

KUTU = (4.0, 3.0, 2.0, 2, 2, 1)  # L, b, h, nx, ny, nz


def kutu10() -> Model:
    L, b, h, nx, ny, nz = KUTU
    return kutu_agi10(L, b, h, nx, ny, nz, Material("celik", E, NU, RHO))


def test_boundary_triangles_tet10_shape_and_mid_nodes():
    """(m, 6): 3 köşe, sonra 1–2, 2–3, 3–1 kenar düğümleri; kenar düğümü köşelerin ortasında; dışa bakar."""
    L, b, h, nx, ny, nz = KUTU
    m = kutu10()
    T = np.asarray(mesh.boundary_triangles(m))
    assert T.shape == (4 * (nx * ny + ny * nz + nz * nx), 6)
    X = {n.id: n.xyz for n in m.nodes}
    merkez = np.array([L, b, h]) / 2
    for t in T.tolist():
        P = np.array([X[n] for n in t])
        for a, (i, j) in enumerate(((0, 1), (1, 2), (2, 0))):
            np.testing.assert_allclose(P[3 + a], 0.5 * (P[i] + P[j]), atol=1e-12)
        n = np.cross(P[1] - P[0], P[2] - P[0])
        assert np.dot(n, P[:3].mean(axis=0) - merkez) > 0.0


def test_boundary_triangles_tet10_corners_match_tet4():
    """tet10 sınır üçgenlerinin köşeleri, aynı ağın tet4 sınır üçgenleriyle aynı küme."""
    L, b, h, nx, ny, nz = KUTU
    m4 = kutu_agi(L, b, h, nx, ny, nz, Material("celik", E, NU))
    m10 = kutu10()
    T4 = {frozenset(t) for t in np.asarray(mesh.boundary_triangles(m4)).tolist()}
    T10 = {frozenset(t[:3]) for t in np.asarray(mesh.boundary_triangles(m10)).tolist()}
    assert T10 == T4


def test_select_triangles_tet10_decides_by_corners():
    L, b, h, nx, ny, nz = KUTU
    m = kutu10()
    T = np.asarray(mesh.select_triangles(m, mesh.on_plane((L, 0, 0), (1, 0, 0))))
    assert T.shape == (2 * ny * nz, 6)
    X = {n.id: n.xyz for n in m.nodes}
    assert all(abs(X[n][0] - L) <= 1e-12 for n in T.ravel().tolist())


def _dugum_kuvvetleri(m: Model) -> dict[int, np.ndarray]:
    F: dict[int, np.ndarray] = {}
    for ld in m.loads:
        F.setdefault(ld.node, np.zeros(3))[DOFS.index(ld.dof)] += ld.value
    return F


def test_add_traction_tri6_flat_face():
    """Düz tri6, düzgün t: köşeler 0, kenar düğümleri t·A/3 (her üçgenden), toplam t·A_yüz (rel 1e-12)."""
    L, b, h, *_ = KUTU
    m = kutu10()
    T = mesh.select_triangles(m, mesh.on_plane((L, 0, 0), (1, 0, 0)))
    t = np.array([2.0, -0.5, 1.5])
    mesh.add_traction(m, T, t)
    F = _dugum_kuvvetleri(m)
    toplam = sum(F.values())
    np.testing.assert_allclose(toplam, t * b * h, rtol=1e-12, atol=1e-12 * b * h)
    kose = {n for tri in np.asarray(T).tolist() for n in tri[:3]}
    beklenen: dict[int, np.ndarray] = {}
    X = {n.id: n.xyz for n in m.nodes}
    for tri in np.asarray(T).tolist():
        A = 0.5 * np.linalg.norm(np.cross(X[tri[1]] - X[tri[0]], X[tri[2]] - X[tri[0]]))
        for n in tri[3:]:
            beklenen[n] = beklenen.get(n, np.zeros(3)) + t * A / 3.0
    for n in kose:
        np.testing.assert_allclose(F.get(n, np.zeros(3)), 0.0, atol=1e-12 * np.abs(t).max() * b * h)
    for n, f in beklenen.items():
        np.testing.assert_allclose(F[n], f, rtol=1e-12, atol=1e-14)


def test_add_pressure_tri6_flat_face():
    """Basınç p dışa normal n'e karşı: t = −p n; toplam −p A n, kenar düğümleri −p n A/3, köşeler 0."""
    L, b, h, *_ = KUTU
    m = kutu10()
    T = mesh.select_triangles(m, mesh.on_plane((0, 0, h), (0, 0, 1)))  # üst yüz, n = +z
    p = 2.0
    mesh.add_pressure(m, T, p)
    F = _dugum_kuvvetleri(m)
    np.testing.assert_allclose(sum(F.values()), [0.0, 0.0, -p * L * b], rtol=1e-12, atol=1e-12 * p * L * b)
    kose = {n for tri in np.asarray(T).tolist() for n in tri[:3]}
    for n in kose:
        np.testing.assert_allclose(F.get(n, np.zeros(3)), 0.0, atol=1e-12 * p * L * b)


def test_tri6_traction_solves_tension_exactly():
    """Uçtan çekilen tet10 prizma (simetri mesnetleri, tri6 tutarlı yük): u = (σx/E, −νσy/E, −νσz/E)."""
    L, b, h, *_ = KUTU
    m = kutu10()
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (1, 0, 0))), dofs=("ux",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 1, 0))), dofs=("uy",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 0, 1))), dofs=("uz",))
    sigma = 80.0
    mesh.add_traction(m, mesh.select_triangles(m, mesh.on_plane((L, 0, 0), (1, 0, 0))), (sigma, 0.0, 0.0))
    r = solve(m)
    for n in m.nodes:
        beklenen = sigma / E * n.xyz * np.array([1.0, -NU, -NU])
        bulunan = [r.displacement(m, n.id, d) for d in DOFS]
        np.testing.assert_allclose(bulunan, beklenen, rtol=0, atol=1e-9 * sigma * L / E)


def test_solve_tet10_model_reports():
    """solve() tet10 modelinde: eksenel sonuç sözlükleri boş, gerilme tensörü her elemanda (6,)."""
    m = kutu10()
    m.bcs = [BC(n.id, d) for n in m.nodes if abs(n.x) <= 1e-12 for d in DOFS]
    uc = max(m.nodes, key=lambda n: (n.x, n.y, n.z)).id
    m.loads = [Load(uc, "uz", -100.0)]
    r = solve(m)
    assert r.element_forces == {} and r.element_stresses == {}
    S = post.element_stress_tensors(m, r.u)
    assert all(np.asarray(S[e.id]).shape == (6,) for e in m.elements)


def test_kuhn_tet10_helper_is_right_handed():
    """Testin kendi ağ üreticisi: her elemanda ve her Gauss noktasında det J > 0, hacim toplamı L·b·h."""
    L, b, h, *_ = KUTU
    m = kutu10()
    V = 0.0
    for e in m.elements:
        X = koordinatlar(m, e)
        for Lg in GAUSS_L:
            _, d = dN_dx(X, Lg)
            assert d > 0.0
            V += d / 24.0
    assert V == pytest.approx(L * b * h, rel=1e-12)
    assert all(len(set(e.nodes)) == 10 for e in m.elements)
    assert len(list(itertools.chain.from_iterable(e.nodes for e in m.elements))) == 10 * len(m.elements)
