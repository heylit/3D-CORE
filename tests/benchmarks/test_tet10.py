"""
tet10 analitik benchmark'ları (specs/67-fem-genisletme.md, 67a: K2, K4–K8, K10 `order`).

Testler yalnız SPEC metninden ve iskeletin imzalarından yazıldı; uygulama kodu okunmadı.
Kuhn ağları tests/benchmarks/tet10_ag.py'den (tet_ag.py'nin ikinci dereceden hali); gmsh ağları
`mesh.tet_mesh(..., order=2)` ile (gmsh + build123d gerekir, `occt` işareti).

Beklenen değerler:
- K4 doğrusal ve saf eğilme alanları (Teori): u_x = κxz, u_y = −νκyz, u_z = −κ(x² + ν(z² − y²))/2,
  σ_xx = Eκz. tet10 tam 2. derece tabanlı olduğu için ikisini de tam üretir.
- K5 Timoshenko konsol δ_T = PL³/(3EI) + PL/(κGA) (SPEC 11 K10 ile aynı kiriş).
- K6 Heywood Kt_g = 3.032, K7 Lamé u_r(a) (SPEC 12/13 testlerinin formülleri).
- K8 ankastre–serbest çubuk f_ax = √(E/ρ)/(4L).
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

import mesh
from core import post
from core.elements import tet10
from core.modal import effective_mass, modal
from core.model import BC, Material, Model, ModelError
from core.solver import solve
from tests.benchmarks.test_tet4 import delta_timoshenko, denge_kontrol
from tests.benchmarks.test_tet4 import konsol as konsol_tet4
from tests.benchmarks.tet10_ag import (
    GAUSS_L,
    KENARLAR,
    D_matrisi,
    dN_dx,
    gauss_konumlari,
    koordinatlar,
    kutu_agi10,
    yuzey_cekmesi10,
)
from tests.benchmarks.tet_ag import yuz_dugumleri

E, NU, RHO = 210_000.0, 0.3, 7.85e-9
DOFS = ("ux", "uy", "uz")


def celik(rho: float = RHO) -> Material:
    return Material("celik", E, NU, rho)


def gmsh_mesh_api():
    """SPEC 12 `mesh.tet_mesh`; gmsh yoksa atlanır."""
    pytest.importorskip("gmsh", reason='gmsh kurulu değil (pip install -e ".[mesh]")')
    pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')
    return mesh


# --- K4: yama testleri (2 × 2 × 2 Kuhn kutusu, tet10) --------------------------------------

PL, PB, PH = 2.0, 1.5, 1.0
PATCH_H = np.array([[1.2, -0.7, 0.4], [0.9, -0.5, 1.6], [-1.1, 0.3, 0.8]]) * 1e-3
PATCH_U0 = np.array([0.01, -0.02, 0.015])
KAPPA = 2e-3  # 1/mm


def u_dogrusal(x: np.ndarray) -> np.ndarray:
    return PATCH_U0 + PATCH_H @ x


def u_egilme(x: np.ndarray) -> np.ndarray:
    """Saf eğilme alanı (Teori): x kiriş ekseni, eğrilik κ."""
    X, Y, Z = x
    return KAPPA * np.array([X * Z, -NU * Y * Z, -(X**2 + NU * (Z**2 - Y**2)) / 2.0])


def _patch_model(alan, kaydirma: float, tohum: int) -> tuple[Model, set[int]]:
    """Sınır yüzlerindeki bütün düğümlere (köşe + kenar) alan yazılı, iç düğümler serbest."""
    m = kutu_agi10(PL, PB, PH, 2, 2, 2, celik(), kaydirma=kaydirma, tohum=tohum)
    sinir: set[int] = set()
    for eksen, deger in ((0, 0.0), (0, PL), (1, 0.0), (1, PB), (2, 0.0), (2, PH)):
        sinir.update(yuz_dugumleri(m, eksen, deger))
    for nid in sorted(sinir):
        u = alan(m.node(nid).xyz)
        m.bcs.extend(BC(nid, d, float(u[i])) for i, d in enumerate(DOFS))
    return m, sinir


PATCH_DURUMLARI = [(0.0, 0), (0.2, 3), (0.2, 8)]
PATCH_IDS = ["duzenli", "kaydirilmis_3", "kaydirilmis_8"]


@pytest.mark.parametrize(("kaydirma", "tohum"), PATCH_DURUMLARI, ids=PATCH_IDS)
def test_patch_linear_interior_nodes(kaydirma, tohum):
    m, sinir = _patch_model(u_dogrusal, kaydirma, tohum)
    ic = [n for n in m.nodes if n.id not in sinir]
    assert len(ic) > 10 and any(n.id in {c for e in m.elements for c in e.nodes[:4]} for n in ic)
    r = solve(m)
    for n in ic:
        bulunan = [r.displacement(m, n.id, d) for d in DOFS]
        np.testing.assert_allclose(bulunan, u_dogrusal(n.xyz), rtol=0, atol=1e-10)
    denge_kontrol(m, r)


@pytest.mark.parametrize(("kaydirma", "tohum"), PATCH_DURUMLARI, ids=PATCH_IDS)
def test_patch_linear_constant_stress_at_gauss_points(kaydirma, tohum):
    m, _ = _patch_model(u_dogrusal, kaydirma, tohum)
    r = solve(m)
    H = PATCH_H
    eps = np.array([H[0, 0], H[1, 1], H[2, 2], H[0, 1] + H[1, 0], H[0, 2] + H[2, 0], H[1, 2] + H[2, 1]])
    s = D_matrisi(E, NU) @ eps
    for e in m.elements:
        sg = tet10.stress_gauss(e, m, r.u)
        np.testing.assert_allclose(sg, np.tile(s, (4, 1)), rtol=0, atol=1e-9 * np.abs(s).max())


@pytest.mark.parametrize(("kaydirma", "tohum"), PATCH_DURUMLARI, ids=PATCH_IDS)
def test_patch_bending_interior_nodes(kaydirma, tohum):
    """Sınıra yazılan 2. derece saf eğilme alanı iç düğümlerde abs 1e-10 tutar."""
    m, sinir = _patch_model(u_egilme, kaydirma, tohum)
    r = solve(m)
    for n in m.nodes:
        if n.id in sinir:
            continue
        bulunan = [r.displacement(m, n.id, d) for d in DOFS]
        np.testing.assert_allclose(bulunan, u_egilme(n.xyz), rtol=0, atol=1e-10)
    denge_kontrol(m, r)


@pytest.mark.parametrize(("kaydirma", "tohum"), PATCH_DURUMLARI, ids=PATCH_IDS)
def test_patch_bending_stress_at_gauss_points(kaydirma, tohum):
    """Her Gauss noktasında σ_xx = Eκz, diğer bileşenler abs 1e-8·Eκ (Gauss sırası serbest: küme olarak)."""
    m, _ = _patch_model(u_egilme, kaydirma, tohum)
    r = solve(m)
    for e in m.elements:
        sg = tet10.stress_gauss(e, m, r.u)
        z = gauss_konumlari(koordinatlar(m, e))[:, 2]
        np.testing.assert_allclose(np.sort(sg[:, 0]), np.sort(E * KAPPA * z), rtol=0, atol=1e-8 * E * KAPPA)
        np.testing.assert_allclose(sg[:, 1:], 0.0, rtol=0, atol=1e-8 * E * KAPPA)


def test_patch_bending_nodal_stress():
    """D5: düğüm gerilmesi (köşeye dış değerleme, kenara ortalama, hacim ağırlıklı) doğrusal σ'yı
    tam verir."""
    m, _ = _patch_model(u_egilme, 0.2, 3)
    r = solve(m)
    d = post.nodal_stress_tensors(m, r.u)
    assert set(d) == {n.id for n in m.nodes}
    for n in m.nodes:
        beklenen = np.array([E * KAPPA * n.z, 0, 0, 0, 0, 0])
        np.testing.assert_allclose(d[n.id], beklenen, rtol=0, atol=1e-8 * E * KAPPA)


# --- K5: konsol yakınsaması ------------------------------------------------------------------

KL, KB, KH, KP = 100.0, 10.0, 10.0, 1000.0


@functools.cache
def konsol10(k: int) -> tuple[float, Model]:
    """(δ_uç / δ_T, model): SPEC 11 K10 kirişi, aynı Kuhn ağı, tet10; δ_uç uç yüzündeki bütün düğümlerin
    (köşe + kenar) −u_z ortalaması; yük tri6 tutarlı (kenar düğümlerine t·A/3)."""
    m = kutu_agi10(KL, KB, KH, 10 * k, k, k, celik(), name=f"konsol10_{k}")
    m.bcs = [BC(n, d) for n in yuz_dugumleri(m, 0, 0.0) for d in DOFS]
    m.loads = yuzey_cekmesi10(m, 0, KL, (0.0, 0.0, -KP / (KB * KH)))
    r = solve(m)
    denge_kontrol(m, r)
    delta = -float(np.mean([r.displacement(m, n, "uz") for n in yuz_dugumleri(m, 0, KL)]))
    return delta / delta_timoshenko(), m


def test_cantilever_tet10_load_total():
    _, m = konsol10(1)
    assert sum(ld.value for ld in m.loads if ld.dof == "uz") == pytest.approx(-KP, rel=1e-12)


def test_cantilever_tet10_k1():
    """k = 1: δ_uç/δ_T ≥ 0.95; hatası tet4'ün k = 4 hatasından küçük."""
    oran, _ = konsol10(1)
    assert oran >= 0.95, f"δ_uç/δ_T = {oran:.4f}"
    oran4 = konsol_tet4(4)[0] / delta_timoshenko()
    assert abs(1 - oran) < 1 - oran4, (oran, oran4)


@pytest.mark.parametrize("k", [2, pytest.param(4, marks=pytest.mark.slow)])
def test_cantilever_tet10_converged(k):
    """k = 2 ve 4: |1 − δ_uç/δ_T| ≤ 0.015."""
    oran, _ = konsol10(k)
    assert abs(1 - oran) <= 0.015, f"δ_uç/δ_T = {oran:.4f}"


# --- K8: ankastre çubuk eksenel frekansı -------------------------------------------------------


def test_axial_frequency_k2():
    """SPEC 45 konsolu (100 × 10 × 10, x = 0 ankastre), tet10 k = 2: eksenel mod f_ax = √(E/ρ)/(4L)'ye
    %0.5 içinde. Eksenel mod, ilk 8 mod içinde x etkin kütlesi en büyük mod."""
    m = kutu_agi10(KL, KB, KH, 20, 2, 2, celik(), name="modal10_k2")
    m.bcs = [BC(n, d) for n in yuz_dugumleri(m, 0, 0.0) for d in DOFS]
    r = modal(m, 8)
    me = effective_mass(m, r)
    i = int(np.argmax(me[:, 0]))
    f_ax = math.sqrt(E / RHO) / (4 * KL)
    assert abs(r.f[i] / f_ax - 1) <= 0.005, f"f = {r.f[i]:.1f} Hz, f_ax = {f_ax:.1f} Hz"


def test_assembled_mass_total():
    """Birleştirilmiş tet10 kütlesi: rᵀ M r = ρ V (öteleme vektörü r, rel 1e-12)."""
    from core.assembly import assemble_M

    m = kutu_agi10(4.0, 3.0, 2.0, 2, 2, 1, celik(), kaydirma=0.0)
    M = assemble_M(m)
    for d in DOFS:
        r = np.zeros(m.n_dof)
        r[[m.dof_index(n.id, d) for n in m.nodes]] = 1.0
        assert r @ (M @ r) == pytest.approx(RHO * 4.0 * 3.0 * 2.0, rel=1e-12)


# --- K2: gmsh ikinci dereceden ağ (birim küp) ------------------------------------------------------


@functools.cache
def _birim_kup10() -> Model:
    api = gmsh_mesh_api()
    import build123d as bd

    from geometry.part import Part

    return api.tet_mesh(Part(bd.Box(1, 1, 1, align=(bd.Align.MIN,) * 3), name="kup"), 0.25, celik(), order=2)


@pytest.fixture
def birim_kup10():
    """Ağ testin gövdesinde kurulur: fikstür kurulumunda düşen NotImplementedError 'uygulanmamış'
    sayılmaz."""
    gmsh_mesh_api()
    return _birim_kup10


@pytest.mark.occt
def test_K2_every_element_is_tet10(birim_kup10):
    m = birim_kup10()
    assert m.dim == 3 and len(m.elements) > 20
    assert all(e.type == "tet10" and len(e.nodes) == 10 and len(set(e.nodes)) == 10 for e in m.elements)
    kullanilan = {n for e in m.elements for n in e.nodes}
    assert kullanilan == {n.id for n in m.nodes}


@pytest.mark.occt
def test_K2_mid_nodes_at_edge_midpoints(birim_kup10):
    m = birim_kup10()
    """Düz yüzlü küpte her kenar düğümü C3D10 sırasındaki iki köşesinin ortasında (abs 1e-9): gmsh → C3D10."""
    for e in m.elements:
        X = koordinatlar(m, e)
        for a, (i, j) in enumerate(KENARLAR):
            np.testing.assert_allclose(X[4 + a], 0.5 * (X[i] + X[j]), rtol=0, atol=1e-9)


@pytest.mark.occt
def test_K2_positive_jacobian_and_volume(birim_kup10):
    m = birim_kup10()
    """Bütün Gauss noktalarında det J > 0 (testin kendi Jacobian'ı); Σ V = 1 (rel 1e-12)."""
    V_kendi = 0.0
    for e in m.elements:
        X = koordinatlar(m, e)
        for L in GAUSS_L:
            _, d = dN_dx(X, L)
            assert d > 0.0, f"eleman {e.id}: det J = {d}"
            V_kendi += d / 24.0
    assert V_kendi == pytest.approx(1.0, rel=1e-12)
    assert sum(tet10.volume(e, m) for e in m.elements) == pytest.approx(1.0, rel=1e-12)


@pytest.mark.occt
def test_K2_tension_exact_on_gmsh_tet10(birim_kup10):
    """Düzensiz tet10 ağında doğrusal alan (çekme) tam: u = (σx/E, −νσy/E, −νσz/E)."""
    src = birim_kup10()
    m = Model(dim=3, nodes=list(src.nodes), elements=list(src.elements), materials=list(src.materials))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (1, 0, 0))), dofs=("ux",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 1, 0))), dofs=("uy",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 0, 1))), dofs=("uz",))
    sigma = 50.0
    mesh.add_traction(m, mesh.select_triangles(m, mesh.on_plane((1, 0, 0), (1, 0, 0))), (sigma, 0.0, 0.0))
    r = solve(m)
    for n in m.nodes:
        beklenen = sigma / E * n.xyz * np.array([1.0, -NU, -NU])
        bulunan = [r.displacement(m, n.id, d) for d in DOFS]
        np.testing.assert_allclose(bulunan, beklenen, atol=1e-9 * sigma / E)
    denge_kontrol(m, r)


# --- K10: order ----------------------------------------------------------------------------------


@pytest.mark.occt
@pytest.mark.parametrize("order", [0, 3])
def test_K10_invalid_order_raises(order):
    api = gmsh_mesh_api()
    import build123d as bd

    from geometry.part import Part

    with pytest.raises(ModelError):
        api.tet_mesh(Part(bd.Box(1, 1, 1), name="kup"), 0.5, celik(), order=order)


# --- K6: Kirsch (delikli plaka, order = 2) --------------------------------------------------------

KIRSCH_L, KIRSCH_B, KIRSCH_T, KIRSCH_R = 100.0, 50.0, 1.0, 5.0


def kirsch_modeli(h: float, refine: tuple = ()) -> Model:
    """SPEC 13 K5'in 1/8 modeli (200 × 100 × 2 plaka, d = 10), order = 2, x = L yüzünde σ = 1 MPa."""
    api = gmsh_mesh_api()
    from build123d import Align, Box, Cylinder, Pos

    from geometry.part import Part

    T = KIRSCH_T
    sekil = Box(KIRSCH_L, KIRSCH_B, T, align=(Align.MIN,) * 3) - Pos(0, 0, T / 2) * Cylinder(KIRSCH_R, 3 * T)
    m = api.tet_mesh(Part(sekil, name="kirsch"), h=h, material=celik(), order=2, refine=list(refine))
    api.fix(m, api.select_nodes(m, api.on_plane((0, 0, 0), (1, 0, 0))), dofs=("ux",))
    api.fix(m, api.select_nodes(m, api.on_plane((0, 0, 0), (0, 1, 0))), dofs=("uy",))
    api.fix(m, api.select_nodes(m, api.on_plane((0, 0, 0), (0, 0, 1))), dofs=("uz",))
    api.add_traction(m, api.select_triangles(m, api.on_plane((KIRSCH_L, 0, 0), (1, 0, 0))), (1.0, 0.0, 0.0))
    return m


@pytest.mark.occt
@pytest.mark.slow
def test_K6_kirsch_tet10():
    """Kalınlık ortalamalı Kt_g (x = 0, y = 5 delik kenarı düğümlerinde σ_xx ortalaması), h = 5 ve
    Refine(r = 8, h = 0.5): 3.032'ye %2 içinde."""
    m = kirsch_modeli(5.0, (mesh.Refine((0.0, 0.0, 0.5), 8.0, 0.5),))
    assert all(e.type == "tet10" for e in m.elements)
    r = solve(m)
    d = post.nodal_stress_tensors(m, r.u)
    X = {n.id: n.xyz for n in m.nodes}
    kenar = [n for n in d if abs(X[n][0]) <= 1e-6 and abs(X[n][1] - KIRSCH_R) <= 1e-6]
    assert len(kenar) >= 3, "x = 0, y = 5 kenarında düğüm bulunamadı"
    Kt = float(np.mean([d[n][0] for n in kenar]))
    assert abs(Kt / 3.032 - 1.0) <= 0.02, f"Kt = {Kt:.4f}"
    denge_kontrol(m, r)


# --- K7: Lamé kalın silindir (order = 2) ------------------------------------------------------------


@pytest.mark.occt
def test_K7_lame_tet10():
    """SPEC 12 çeyrek halkası, h = 4, order = 2: iç yarıçapta ortalama u_r hatası ≤ %1."""
    gmsh_mesh_api()
    from tests.benchmarks.test_gmsh import BOY, P, a, ceyrek_halka, u_r

    m = mesh.tet_mesh(ceyrek_halka(), 4.0, celik(), order=2)
    assert all(e.type == "tet10" for e in m.elements)
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (1, 0, 0))), dofs=("ux",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 1, 0))), dofs=("uy",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 0, 1))), dofs=("uz",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, BOY), (0, 0, 1))), dofs=("uz",))
    ic = mesh.on_cylinder((0, 0, 0), (0, 0, 1), a)
    T = np.asarray(mesh.select_triangles(m, ic))
    assert T.ndim == 2 and T.shape[1] == 6
    mesh.add_pressure(m, T, P)
    r = solve(m)
    ur = []
    for nid in mesh.select_nodes(m, ic):
        x, y, _ = m.node(nid).xyz
        ux, uy = r.u[m.dof_index(nid, "ux")], r.u[m.dof_index(nid, "uy")]
        ur.append((ux * x + uy * y) / math.hypot(x, y))
    assert len(ur) > 10
    e = 1.0 - float(np.mean(ur)) / u_r(a)
    assert abs(e) <= 0.01, f"e = {e:.4f}"
    denge_kontrol(m, r)
