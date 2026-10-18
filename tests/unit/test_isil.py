"""
SPEC 56 — kararlı hal ısı iletimi birim testleri (K1, K2, K9, K12 ve arayüz davranışı).

Beklenen değerler SPEC 56 Teori bölümünden el hesabıyla kurulur; uygulama kodu okunmadan yazılmıştır.
Ağ: SPEC 11 K10'daki Kuhn bölümlü kutu ağı (tests/benchmarks/tet_ag.py), OCCT ve gmsh gerekmez.
Birimler: mW, mm, °C; k mW/(mm·K), q mW/mm², h mW/(mm²·K), Q mW/mm³.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

import mesh
from core import isil
from core.elements import tet4
from core.isil import Convection, HeatFlux, Temperature, ThermalResult, solve_thermal
from core.model import BC, Element, Load, Material, Model, ModelError, Node
from tests.benchmarks.tet_ag import kutu_agi
from tests.conftest import make_bar

BIRIM = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
GENEL = [(1.0, 2.0, -0.5), (13.0, 3.5, 1.0), (4.0, 11.0, 2.0), (3.0, 4.0, 9.5)]
CELIK = Material("celik", 210_000.0, 0.3)


def tek_tet(koseler, sira=(1, 2, 3, 4)) -> Model:
    return Model(
        dim=3,
        nodes=[Node(i + 1, *x) for i, x in enumerate(koseler)],
        elements=[Element(1, "tet4", list(sira), "celik")],
        materials=[CELIK],
    )


def kt_el(koseler, k: float) -> np.ndarray:
    """SPEC formülü elle: kt = k V Bᵀ B, B sütunları ∇N_a (C = [1 x y z] satırları, ∇N = C⁻¹[1:, :])."""
    X = np.asarray(koseler, dtype=float)
    C = np.hstack([np.ones((4, 1)), X])
    V = abs(np.linalg.det(C)) / 6.0
    B = np.linalg.inv(C)[1:, :]
    return k * V * B.T @ B


def kutu(L=2.0, b=1.5, h=1.0, n=2, kaydirma=0.0, tohum=0) -> Model:
    return kutu_agi(L, b, h, n, n, n, CELIK, kaydirma=kaydirma, tohum=tohum)


def koordinatlar(model: Model) -> np.ndarray:
    return np.array([n.xyz for n in model.nodes])


def dis_dugumler(model: Model) -> list[int]:
    X = koordinatlar(model)
    lo, hi = X.min(axis=0), X.max(axis=0)
    dis = np.any(np.isclose(X, lo, atol=1e-9) | np.isclose(X, hi, atol=1e-9), axis=1)
    return [n.id for n, d in zip(model.nodes, dis, strict=True) if d]


def yuz(model: Model, eksen: int, deger: float):
    normal = np.zeros(3)
    normal[eksen] = 1.0
    p = np.zeros(3)
    p[eksen] = deger
    return mesh.on_plane(tuple(p), tuple(normal))


def sabit_yuz(model: Model, eksen: int, deger: float, T: float) -> list[Temperature]:
    return [Temperature(n, T) for n in mesh.select_nodes(model, yuz(model, eksen, deger))]


# --- K1: eleman matrisi ------------------------------------------------------------------


def test_kt_unit_tetrahedron():
    """Birim referans tetrahedron, k = 1: kt = (1/6)·[[3,−1,−1,−1],[−1,1,0,0],[−1,0,1,0],[−1,0,0,1]]."""
    m = tek_tet(BIRIM)
    kt = tet4.kt(m.elements[0], m, 1.0)
    beklenen = np.array([[3, -1, -1, -1], [-1, 1, 0, 0], [-1, 0, 1, 0], [-1, 0, 0, 1]]) / 6.0
    assert np.shape(kt) == (4, 4)
    np.testing.assert_allclose(kt, beklenen, rtol=0, atol=1e-14)


def test_kt_general_matches_formula():
    m = tek_tet(GENEL)
    np.testing.assert_allclose(tet4.kt(m.elements[0], m, 3.5), kt_el(GENEL, 3.5), rtol=1e-12)


def test_kt_symmetric_zero_row_sums_psd_rank3():
    """Rastgele tetrahedron: simetrik, satır toplamı 0 (sabit sıcaklık akı üretmez), PSD, rank 3."""
    rng = np.random.default_rng(56)
    for _ in range(10):
        X = rng.uniform(-10, 10, size=(4, 3))
        if abs(np.linalg.det(X[1:] - X[0])) < 1.0:
            continue
        m = tek_tet([tuple(x) for x in X])
        kt = np.asarray(tet4.kt(m.elements[0], m, 12.0))
        olcek = np.linalg.norm(kt)
        np.testing.assert_allclose(kt, kt.T, rtol=0, atol=1e-14 * olcek)
        np.testing.assert_allclose(kt.sum(axis=1), 0.0, rtol=0, atol=1e-12 * olcek)
        w = np.linalg.eigvalsh(kt)
        assert w.min() >= -1e-12 * olcek
        assert np.linalg.matrix_rank(kt, tol=1e-10 * olcek) == 3


def test_kt_rigid_motion_invariant():
    """Rijit öteleme ve döndürme: kt değişmez."""
    rng = np.random.default_rng(3)
    Q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    if np.linalg.det(Q) < 0:
        Q[:, 0] *= -1
    X = np.array(GENEL)
    X2 = X @ Q.T + np.array([100.0, -40.0, 7.0])
    m1, m2 = tek_tet(GENEL), tek_tet([tuple(x) for x in X2])
    kt1 = tet4.kt(m1.elements[0], m1, 2.0)
    kt2 = tet4.kt(m2.elements[0], m2, 2.0)
    np.testing.assert_allclose(kt2, kt1, rtol=0, atol=1e-12 * np.linalg.norm(kt1))


def test_kt_linear_in_k():
    m = tek_tet(GENEL)
    kt1 = np.asarray(tet4.kt(m.elements[0], m, 1.0))
    np.testing.assert_allclose(tet4.kt(m.elements[0], m, 37.5), 37.5 * kt1, rtol=1e-12)


def test_kt_negative_node_order():
    """Negatif sıralı eleman (2. ve 3. düğüm yer değiştirmiş): aynı matris, satır/sütunlar yer değiştirmiş."""
    m1 = tek_tet(GENEL)
    m2 = tek_tet(GENEL, sira=(1, 3, 2, 4))
    kt1 = np.asarray(tet4.kt(m1.elements[0], m1, 5.0))
    kt2 = np.asarray(tet4.kt(m2.elements[0], m2, 5.0))
    p = [0, 2, 1, 3]
    np.testing.assert_allclose(kt2, kt1[np.ix_(p, p)], rtol=1e-12)


def test_conductivity_matrix_assembles_element_matrices():
    """Global Σ ke: seyrek, (n × n), simetrik, satır toplamları 0; tek elemanda kt'nin kendisi."""
    m = tek_tet(GENEL)
    K = isil.conductivity_matrix(m, 4.0)
    assert sp.issparse(K) and K.shape == (4, 4)
    np.testing.assert_allclose(K.toarray(), kt_el(GENEL, 4.0), rtol=1e-12)

    m = kutu(n=2, kaydirma=0.2, tohum=1)
    K = isil.conductivity_matrix(m, 4.0).toarray()
    n = len(m.nodes)
    assert K.shape == (n, n)
    olcek = np.abs(K).max()
    np.testing.assert_allclose(K, K.T, rtol=0, atol=1e-13 * olcek)
    np.testing.assert_allclose(K.sum(axis=1), 0.0, rtol=0, atol=1e-12 * olcek)
    indeks = {nd.id: i for i, nd in enumerate(m.nodes)}
    K_el = np.zeros((n, n))
    for e in m.elements:
        ix = [indeks[i] for i in e.nodes]
        K_el[np.ix_(ix, ix)] += kt_el([m.node(i).xyz for i in e.nodes], 4.0)
    np.testing.assert_allclose(K, K_el, rtol=0, atol=1e-12 * olcek)


def test_conductivity_matrix_per_material():
    """k sözlüğü (Material.name → k): her eleman kendi k'sıyla."""
    m = kutu(n=2)
    m.materials.append(Material("al", 70_000.0, 0.33))
    for e in m.elements[::2]:
        e.material = "al"
    K = isil.conductivity_matrix(m, {"celik": 50.0, "al": 200.0}).toarray()
    indeks = {nd.id: i for i, nd in enumerate(m.nodes)}
    K_el = np.zeros_like(K)
    for e in m.elements:
        ix = [indeks[i] for i in e.nodes]
        K_el[np.ix_(ix, ix)] += kt_el(
            [m.node(i).xyz for i in e.nodes], 50.0 if e.material == "celik" else 200.0
        )
    np.testing.assert_allclose(K, K_el, rtol=0, atol=1e-12 * np.abs(K_el).max())


# --- K2: yama testi --------------------------------------------------------------------------

GRAD = np.array([2.0, -3.0, 0.5])


def alan(x: np.ndarray) -> float:
    return float(5.0 + GRAD @ x)


@pytest.mark.parametrize("kaydirma", [0.0, 0.25], ids=["duzgun", "kaydirilmis"])
def test_patch_linear_field(kaydirma):
    """2×2×2 Kuhn kutusu, dış düğümlerde T = 5 + 2x − 3y + 0.5z: iç düğümde aynı alan (abs 1e-10),
    her elemanda q_e = −k (2, −3, 0.5) (göreli 1e-10), düğüm akısı da aynı."""
    k = 7.0
    m = kutu(n=2, kaydirma=kaydirma, tohum=5)
    dis = set(dis_dugumler(m))
    assert len(dis) < len(m.nodes)
    r = solve_thermal(m, k, temperatures=[Temperature(n, alan(m.node(n).xyz)) for n in sorted(dis)])
    assert isinstance(r, ThermalResult)
    np.testing.assert_array_equal(r.node_ids, [n.id for n in m.nodes])
    for n in m.nodes:
        assert r.temperature(n.id) == pytest.approx(alan(n.xyz), abs=1e-10)
    np.testing.assert_allclose(r.T, [alan(n.xyz) for n in m.nodes], rtol=0, atol=1e-10)
    q = isil.heat_flux(m, k, r)
    assert np.shape(q) == (len(m.elements), 3)
    np.testing.assert_allclose(q, np.tile(-k * GRAD, (len(m.elements), 1)), rtol=1e-10)
    qn = isil.nodal_heat_flux(m, k, r)
    assert np.shape(qn) == (len(m.nodes), 3)
    np.testing.assert_allclose(qn, np.tile(-k * GRAD, (len(m.nodes), 1)), rtol=1e-10)
    # tepki yalnız tutulu düğümlerde; iç düğümde 0
    for n, Rn in zip(m.nodes, r.R, strict=True):
        if n.id not in dis:
            assert Rn == 0.0
    # enerji dengesi (dış kaynak yok): Σ R = 0
    assert abs(r.R.sum()) <= 1e-9 * np.abs(r.R).max()
    assert r.Q_gen == 0.0 and r.Q_flux == 0.0 and r.Q_conv == 0.0


def test_element_flux_formula_single_element():
    """Tek eleman, rastgele düğüm sıcaklıkları: q_e = −k ∇T, ∇T = B T_e (elle)."""
    m = tek_tet(GENEL)
    T = np.array([10.0, 40.0, -5.0, 22.0])
    r = solve_thermal(m, 3.0, temperatures=[Temperature(i + 1, float(T[i])) for i in range(4)])
    X = np.array(GENEL)
    B = np.linalg.inv(np.hstack([np.ones((4, 1)), X]))[1:, :]
    np.testing.assert_allclose(isil.heat_flux(m, 3.0, r)[0], -3.0 * B @ T, rtol=1e-12)


def test_nodal_flux_volume_weighted():
    """İki eleman ortak yüzde: ortak düğümde (V1 q1 + V2 q2) / (V1 + V2)."""
    X = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 8.0, 0.0), (0.0, 0.0, 6.0), (9.0, 9.0, 14.0)]
    m = Model(
        dim=3,
        nodes=[Node(i + 1, *x) for i, x in enumerate(X)],
        elements=[Element(1, "tet4", [1, 2, 3, 4], "celik"), Element(2, "tet4", [2, 4, 3, 5], "celik")],
        materials=[CELIK],
    )
    T = [0.0, 30.0, 10.0, 25.0, 90.0]
    r = solve_thermal(m, 2.0, temperatures=[Temperature(i + 1, T[i]) for i in range(5)])
    q = isil.heat_flux(m, 2.0, r)
    V = [
        abs(np.linalg.det(np.array([m.node(i).xyz for i in e.nodes[1:]]) - m.node(e.nodes[0]).xyz)) / 6
        for e in m.elements
    ]
    qn = isil.nodal_heat_flux(m, 2.0, r)
    ortak = (V[0] * q[0] + V[1] * q[1]) / (V[0] + V[1])
    for i in (1, 2, 3):  # düğüm 2, 3, 4
        np.testing.assert_allclose(qn[i], ortak, rtol=1e-12)
    np.testing.assert_allclose(qn[0], q[0], rtol=1e-12)
    np.testing.assert_allclose(qn[4], q[1], rtol=1e-12)


# --- Arayüz davranışı ------------------------------------------------------------------------


def test_mechanical_bcs_and_loads_are_ignored():
    """`model.bcs` ve `model.loads` okunmaz: eklemek ısıl sonucu değiştirmez."""
    m = kutu(n=2)
    temps = sabit_yuz(m, 0, 0.0, 100.0) + sabit_yuz(m, 0, 2.0, 20.0)
    r1 = solve_thermal(m, 50.0, temperatures=temps)
    m.bcs = [BC(n.id, "ux", 0.0) for n in m.nodes[:3]]
    m.loads = [Load(m.nodes[-1].id, "uz", 1e6)]
    r2 = solve_thermal(m, 50.0, temperatures=temps)
    np.testing.assert_array_equal(r1.T, r2.T)
    np.testing.assert_array_equal(r1.R, r2.R)


def test_repeated_same_temperature_accepted():
    m = kutu(n=2)
    temps = sabit_yuz(m, 0, 0.0, 100.0) + sabit_yuz(m, 0, 2.0, 20.0)
    r = solve_thermal(m, 50.0, temperatures=temps + temps[:3])
    np.testing.assert_allclose(r.T, [100.0 - 40.0 * n.x for n in m.nodes], rtol=0, atol=1e-9)


def test_generation_per_material_mapping():
    """Q sözlükle (malzeme adı → Q): Q_gen = Σ Q_e V_e."""
    m = kutu(L=2.0, b=1.5, h=1.0, n=2)
    m.materials.append(Material("al", 70_000.0, 0.33))
    alt = [e for e in m.elements if np.mean([m.node(i).x for i in e.nodes]) < 1.0]
    for e in alt:
        e.material = "al"
    temps = sabit_yuz(m, 0, 0.0, 0.0)
    r = solve_thermal(m, {"celik": 10.0, "al": 20.0}, temperatures=temps, Q={"celik": 0.0, "al": 3.0})
    V_al = 1.0 * 1.5 * 1.0
    assert r.Q_gen == pytest.approx(3.0 * V_al, rel=1e-12)
    assert r.R.sum() == pytest.approx(-3.0 * V_al, rel=1e-10)


def test_unknown_node_temperature_raises():
    m = kutu(n=2)
    r = solve_thermal(m, 1.0, temperatures=sabit_yuz(m, 0, 0.0, 1.0))
    with pytest.raises(ModelError):
        r.temperature(99_999)


# --- K9: hatalar -------------------------------------------------------------------------------


def _temps(m: Model) -> list[Temperature]:
    return sabit_yuz(m, 0, 0.0, 10.0)


def _tris(m: Model, eksen=0, deger=2.0) -> np.ndarray:
    return mesh.select_triangles(m, yuz(m, eksen, deger))


def _cozum(m: Model, k=1.0, temps=None, **kw) -> ThermalResult:
    return solve_thermal(m, k, temperatures=_temps(m) if temps is None else temps, **kw)


HATALAR = {
    "sicaklik-ve-tasinim-yok": lambda m: solve_thermal(m, 1.0, fluxes=[HeatFlux(_tris(m), 1.0)]),
    "hicbir-kosul-yok": lambda m: solve_thermal(m, 1.0),
    "k=0": lambda m: solve_thermal(m, 0.0, temperatures=_temps(m)),
    "k=-1": lambda m: solve_thermal(m, -1.0, temperatures=_temps(m)),
    "k=nan": lambda m: solve_thermal(m, float("nan"), temperatures=_temps(m)),
    "k-sozluk-sifir": lambda m: solve_thermal(m, {"celik": 0.0}, temperatures=_temps(m)),
    "h=0": lambda m: solve_thermal(
        m, 1.0, temperatures=_temps(m), convection=[Convection(_tris(m), 0.0, 20.0)]
    ),
    "h=-1": lambda m: solve_thermal(
        m, 1.0, temperatures=_temps(m), convection=[Convection(_tris(m), -1.0, 20.0)]
    ),
    "T_inf=inf": lambda m: solve_thermal(
        m, 1.0, temperatures=_temps(m), convection=[Convection(_tris(m), 1.0, float("inf"))]
    ),
    "Q=nan": lambda m: solve_thermal(m, 1.0, temperatures=_temps(m), Q=float("nan")),
    "q=inf": lambda m: solve_thermal(
        m, 1.0, temperatures=_temps(m), fluxes=[HeatFlux(_tris(m), float("inf"))]
    ),
    "T=nan": lambda m: solve_thermal(m, 1.0, temperatures=[Temperature(1, float("nan"))]),
    "bilinmeyen-dugum": lambda m: solve_thermal(m, 1.0, temperatures=[*_temps(m), Temperature(99_999, 5.0)]),
    "bilinmeyen-ucgen-dugumu": lambda m: solve_thermal(
        m, 1.0, temperatures=_temps(m), fluxes=[HeatFlux(np.array([[1, 2, 99_999]]), 1.0)]
    ),
    "ayni-dugume-10-ve-20": lambda m: solve_thermal(
        m, 1.0, temperatures=[Temperature(1, 10.0), Temperature(1, 20.0)]
    ),
    "eksik-malzeme-adi": lambda m: solve_thermal(m, {"baska": 1.0}, temperatures=_temps(m)),
    "Q-sozlugunde-eksik-ad": lambda m: solve_thermal(m, 1.0, temperatures=_temps(m), Q={"baska": 1.0}),
}


@pytest.mark.parametrize("ad", list(HATALAR))
def test_errors_raise_model_error(ad):
    m = kutu(n=2)
    with pytest.raises(ModelError):
        HATALAR[ad](m)


def test_validate_is_called():
    m = kutu(n=2)
    m.elements[0].nodes = [1, 2, 3, 99_999]
    with pytest.raises(ModelError):
        solve_thermal(m, 1.0, temperatures=_temps(kutu(n=2)))


def test_bar_model_raises():
    """tet4 dışı eleman (bar1d modeli)."""
    m = make_bar(n_elem=3)
    with pytest.raises(ModelError):
        solve_thermal(m, 1.0, temperatures=[Temperature(1, 10.0)])


def test_dim_1_raises():
    m = kutu(n=2)
    m.dim = 1
    with pytest.raises(ModelError):
        solve_thermal(m, 1.0, temperatures=_temps(kutu(n=2)))


def test_mixed_element_types_raise():
    m = kutu(n=2)
    m.sections = []
    m.elements.append(Element(9999, "bar1d", [1, 2], "celik"))
    with pytest.raises(ModelError):
        solve_thermal(m, 1.0, temperatures=_temps(m))


# --- K12: bağımlılık ----------------------------------------------------------------------------


def test_core_isil_imports_only_numpy_scipy_core():
    """core/isil.py yalnız numpy, scipy, core ve standart kütüphane kullanır (metin taraması)."""
    import sys

    kaynak = Path(isil.__file__).read_text(encoding="utf-8")
    izinli = {"numpy", "scipy", "core", "__future__"} | set(sys.stdlib_module_names)
    for dugum in ast.walk(ast.parse(kaynak)):
        if isinstance(dugum, ast.Import):
            adlar = [a.name for a in dugum.names]
        elif isinstance(dugum, ast.ImportFrom):
            assert dugum.level == 0, "core/isil.py göreli import kullanmamalı"
            adlar = [dugum.module or ""]
        else:
            continue
        for ad in adlar:
            assert ad.split(".")[0] in izinli, f"core/isil.py izin dışı modül import ediyor: {ad}"


def test_kuhn_mesh_has_both_orders():
    """Testin kendi güvencesi: kutu ağı iki düğüm sırasını da içerir (negatif hacimli sıra dahil)."""
    m = kutu(n=2)
    isaretler = set()
    for e in m.elements:
        X = np.array([m.node(i).xyz for i in e.nodes])
        isaretler.add(np.sign(np.linalg.det(X[1:] - X[0])))
    assert isaretler == {-1.0, 1.0}
    assert len(m.elements) == 48
