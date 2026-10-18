"""SPEC 67b — core/yukler.py: yerçekimi, merkezkaç, ısıl yük vektörleri, add_loads; asılı çubuk (K13, K18).

Testler sadece specs/67-fem-genisletme.md (67b) metninden ve arayüzünden yazıldı; core/yukler.py gövdesi
okunmadı. Beklenen tutarlı düğüm kuvvetleri f_a = ∫ N_a b dV, düz elemanda barisentrik polinomların kapalı
form integraliyle (tests/benchmarks/yuk_ag.py `L_integrali`) elle hesaplanır:
    tet4   N_a = L_a                      ∫ N_a = V/4,   ∫ N_a L_k = V (1 + δ_ak) / 20
    tet10  N_i = L_i (2 L_i − 1), N_ij = 4 L_i L_j    ∫ N_köşe = −V/20, ∫ N_kenar = V/5
Isıl: σ0 = D ε0 = E α ΔT / (1 − 2ν) · [1, 1, 1, 0, 0, 0] (hidrostatik)
      → f_a = ∫ s(x) ∇N_a dV, s = E α ΔT / (1 − 2ν).
tet10 elemanı SPEC 67a'dır; 67a gelene kadar tet10 testleri "uygulanmamış" düşer.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pytest

from core import yukler
from core.model import BC, Load, Material, ModelError
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri
from tests.benchmarks.yuk_ag import (
    KENARLAR,
    L_integrali,
    SahteSicaklik,
    dugum_kuvveti,
    grad_L,
    tek_tet,
    tet10_agi,
    tet_hacmi,
    toplam_kuvvet,
    u_dugum,
    yuk_sozlugu,
)

RHO = 7.85e-9  # t/mm³
G = np.array([0.0, 0.0, -9810.0])  # mm/s²
CELIK = Material("celik", 210_000.0, 0.3, RHO)


def _X(model):
    return np.array([model.node(n).xyz for n in model.elements[0].nodes[:4]])


def _N_us(a: int) -> list[tuple[float, tuple[int, int, int, int]]]:
    """tet10 N_a'nın barisentrik tek terimlileri: [(katsayı, üsler)]."""
    if a < 4:
        e2 = [0, 0, 0, 0]
        e2[a] = 2
        e1 = [0, 0, 0, 0]
        e1[a] = 1
        return [(2.0, tuple(e2)), (-1.0, tuple(e1))]
    i, j = KENARLAR[a - 4]
    e = [0, 0, 0, 0]
    e[i] += 1
    e[j] += 1
    return [(4.0, tuple(e))]


def _carp(us, k: int) -> tuple[int, int, int, int]:
    e = list(us)
    e[k] += 1
    return tuple(e)


# ---------- yerçekimi ----------


def test_gravity_tet4_quarter_per_node():
    m = tek_tet(1)
    V = tet_hacmi(_X(m))
    loads = yukler.gravity_loads(m, G)
    for nid in (1, 2, 3, 4):
        np.testing.assert_allclose(dugum_kuvveti(loads, nid), RHO * G * V / 4, rtol=1e-12, atol=1e-30)


def test_gravity_tet10_corner_and_edge():
    """Köşeler −ρ g V/20, kenarlar ρ g V/5 (toplam ρ g V)."""
    m = tek_tet(2)
    V = tet_hacmi(_X(m))
    loads = yukler.gravity_loads(m, G)
    e = m.elements[0]
    for a, nid in enumerate(e.nodes):
        beklenen = RHO * G * V * (-1 / 20 if a < 4 else 1 / 5)
        np.testing.assert_allclose(dugum_kuvveti(loads, nid), beklenen, rtol=1e-12, atol=1e-30)
    np.testing.assert_allclose(toplam_kuvvet(loads), RHO * G * V, rtol=1e-12)


@pytest.mark.parametrize("order", [1, 2])
def test_gravity_total_on_mesh(order):
    """Kuhn kutusu 20 × 30 × 40 (2 × 2 × 2): toplam ρ g V, V = 24000."""
    m = kutu_agi(20.0, 30.0, 40.0, 2, 2, 2, CELIK)
    if order == 2:
        m = tet10_agi(m)
    np.testing.assert_allclose(toplam_kuvvet(yukler.gravity_loads(m, G)), RHO * G * 24000.0, rtol=1e-12)


def test_gravity_rho_missing_raises():
    m = tek_tet(1, malzeme=Material("rhosuz", 210_000.0, 0.3, 0.0))
    with pytest.raises(ModelError):
        yukler.gravity_loads(m, G)


def test_load_functions_do_not_change_model():
    m = tek_tet(1)
    m.loads.append(Load(1, "ux", 5.0))
    once = m.to_dict()
    yukler.gravity_loads(m, G)
    yukler.centrifugal_loads(m, 1000.0, (0, 0, 0), (0, 0, 1))
    yukler.thermal_loads(m, {n.id: 70.0 for n in m.nodes}, 20.0, 1.2e-5)
    assert m.to_dict() == once


# ---------- merkezkaç ----------

P0 = np.array([2.0, -1.0, 0.0])
A_EKSEN = np.array([1.0, 2.0, 2.0]) / 3.0  # birim
OMEGA = 300.0  # rad/s


def _r_dik(x):
    d = np.asarray(x) - P0
    return d - (d @ A_EKSEN) * A_EKSEN


def test_centrifugal_tet4_exact_per_node():
    """f_a = ρ ω² Σ_k r⊥_k ∫ L_a L_k dV = ρ ω² V/20 (r⊥_a + Σ_k r⊥_k)  (b doğrusal, kural tam)."""
    m = tek_tet(1)
    X = _X(m)
    V = tet_hacmi(X)
    R = np.array([_r_dik(x) for x in X])
    loads = yukler.centrifugal_loads(m, OMEGA, P0, A_EKSEN)
    for a in range(4):
        beklenen = RHO * OMEGA**2 * V / 20 * (R[a] + R.sum(axis=0))
        np.testing.assert_allclose(dugum_kuvveti(loads, a + 1), beklenen, rtol=1e-12)


def test_centrifugal_tet10_exact_per_node():
    """f_a = ρ ω² Σ_k r⊥_k ∫ N_a L_k dV (N_a 2. derece, b doğrusal: 3. derece, Keast tam)."""
    m = tek_tet(2)
    X = _X(m)
    V = tet_hacmi(X)
    R = np.array([_r_dik(x) for x in X])
    loads = yukler.centrifugal_loads(m, OMEGA, P0, A_EKSEN)
    for a, nid in enumerate(m.elements[0].nodes):
        beklenen = np.zeros(3)
        for c, us in _N_us(a):
            for k in range(4):
                beklenen += c * L_integrali(V, _carp(us, k)) * R[k]
        np.testing.assert_allclose(
            dugum_kuvveti(loads, nid), RHO * OMEGA**2 * beklenen, rtol=1e-10, atol=1e-14
        )


@pytest.mark.parametrize("order", [1, 2])
def test_centrifugal_total_on_mesh(order):
    """Toplam = ρ ω² Σ_e V_e r⊥(merkez_e) (göreli 1e-12)."""
    m4 = kutu_agi(20.0, 30.0, 40.0, 2, 2, 2, CELIK)
    beklenen = np.zeros(3)
    for e in m4.elements:
        X = np.array([m4.node(n).xyz for n in e.nodes])
        beklenen += abs(tet_hacmi(X)) * _r_dik(X.mean(axis=0))
    m = m4 if order == 1 else tet10_agi(m4)
    toplam = toplam_kuvvet(yukler.centrifugal_loads(m, OMEGA, P0, A_EKSEN))
    np.testing.assert_allclose(toplam, RHO * OMEGA**2 * beklenen, rtol=1e-12)


def test_centrifugal_zero_on_axis_body():
    """Eksen üzerindeki düğümlerin r⊥'si sıfır; ω = 0 → bütün kuvvetler sıfır."""
    m = tek_tet(1)
    loads = yukler.centrifugal_loads(m, 0.0, P0, A_EKSEN)
    np.testing.assert_allclose(toplam_kuvvet(loads), 0.0, atol=1e-30)


# ---------- ısıl yük ----------

ALFA = 1.2e-5
T_REF = 20.0


def test_thermal_tet4_uniform_hydrostatic():
    """Düzgün ΔT = 50: f_a = V s ∇L_a, s = E α ΔT / (1 − 2ν)."""
    m = tek_tet(1)
    X = _X(m)
    V = tet_hacmi(X)
    s = 210_000.0 * ALFA * 50.0 / (1 - 2 * 0.3)
    loads = yukler.thermal_loads(m, {n.id: T_REF + 50.0 for n in m.nodes}, T_REF, ALFA)
    gL = grad_L(X)
    for a in range(4):
        np.testing.assert_allclose(dugum_kuvveti(loads, a + 1), V * s * gL[a], rtol=1e-10)
    np.testing.assert_allclose(toplam_kuvvet(loads), 0.0, atol=1e-9 * V * s)


def test_thermal_tet4_uses_element_mean_temperature():
    """tet4'te T eleman içinde 4 düğümün ortalaması: (20, 60, 100, 140) ile ortalama 80, ΔT = 60."""
    m = tek_tet(1)
    X = _X(m)
    s = 210_000.0 * ALFA * 60.0 / (1 - 2 * 0.3)
    loads = yukler.thermal_loads(m, {1: 20.0, 2: 60.0, 3: 100.0, 4: 140.0}, T_REF, ALFA)
    gL = grad_L(X)
    for a in range(4):
        np.testing.assert_allclose(dugum_kuvveti(loads, a + 1), tet_hacmi(X) * s * gL[a], rtol=1e-10)


def test_thermal_tet10_linear_temperature_exact():
    """tet10'da T doğrusal (kenarda iki ucun ortalaması): f_a = c Σ_k ΔT_k ∫ L_k ∇N_a dV.

    ∇N_i = (4 L_i − 1) ∇L_i, ∇N_ij = 4 (L_j ∇L_i + L_i ∇L_j); integrand 2. derece (4 noktalı kural tam).
    """
    m = tek_tet(2)
    X = _X(m)
    V = tet_hacmi(X)
    c = 210_000.0 * ALFA / (1 - 2 * 0.3)
    Tk = np.array([20.0, 60.0, 100.0, 140.0])
    e = m.elements[0]
    T = {nid: float(Tk[a]) for a, nid in enumerate(e.nodes[:4])}
    for a, (i, j) in enumerate(KENARLAR):
        T[e.nodes[4 + a]] = (Tk[i] + Tk[j]) / 2
    loads = yukler.thermal_loads(m, T, T_REF, ALFA)
    gL = grad_L(X)
    dT = Tk - T_REF

    def integ(us_list):  # Σ c_m ∫ L^us_m L_k ΔT_k
        return sum(cf * sum(L_integrali(V, _carp(us, k)) * dT[k] for k in range(4)) for cf, us in us_list)

    for a, nid in enumerate(e.nodes):
        if a < 4:
            e1 = [0, 0, 0, 0]
            e1[a] = 1
            beklenen = gL[a] * (4 * integ([(1.0, tuple(e1))]) - integ([(1.0, (0, 0, 0, 0))]))
        else:
            i, j = KENARLAR[a - 4]
            ei, ej = [0, 0, 0, 0], [0, 0, 0, 0]
            ei[i], ej[j] = 1, 1
            beklenen = 4 * (gL[i] * integ([(1.0, tuple(ej))]) + gL[j] * integ([(1.0, tuple(ei))]))
        np.testing.assert_allclose(dugum_kuvveti(loads, nid), c * beklenen, rtol=1e-9, atol=1e-9 * c * V)


def test_thermal_alpha_mapping_and_result_object():
    """α malzeme adıyla eşlem olarak; T SPEC 56 ThermalResult (ördek tipi) olarak: sözlükle aynı yük."""
    m = kutu_agi(10.0, 10.0, 10.0, 2, 1, 1, CELIK)
    T = {n.id: 20.0 + 3.0 * n.x + 0.5 * n.z for n in m.nodes}
    a = yuk_sozlugu(yukler.thermal_loads(m, T, T_REF, ALFA))
    b = yuk_sozlugu(yukler.thermal_loads(m, T, T_REF, {"celik": ALFA}))
    c = yuk_sozlugu(yukler.thermal_loads(m, SahteSicaklik.alandan(m, T), T_REF, ALFA))
    for d in (b, c):
        for k in set(a) | set(d):
            assert d.get(k, 0.0) == pytest.approx(a.get(k, 0.0), rel=1e-12, abs=1e-12)


def test_thermal_missing_node_temperature_raises():
    m = tek_tet(1)
    with pytest.raises(ModelError):
        yukler.thermal_loads(m, {1: 50.0, 2: 50.0, 3: 50.0}, T_REF, ALFA)


def test_thermal_strain_stress_restrained():
    """u = 0 (tam tutulu) ve düzgün ΔT = 50: σ = −D ε0 = −s [1, 1, 1, 0, 0, 0]."""
    m = kutu_agi(10.0, 10.0, 10.0, 1, 1, 1, CELIK)
    s = 210_000.0 * ALFA * 50.0 / (1 - 2 * 0.3)
    sigma = yukler.thermal_strain_stress(m, np.zeros(m.n_dof), {n.id: 70.0 for n in m.nodes}, T_REF, ALFA)
    assert np.shape(sigma) == (len(m.elements), 6)
    np.testing.assert_allclose(sigma, np.tile([-s, -s, -s, 0, 0, 0], (len(m.elements), 1)), atol=1e-9 * s)


# ---------- add_loads ----------


def test_add_loads_sums_same_node_dof():
    """Aynı (düğüm, dof) toplanır, tek Load kalır; modeldeki mevcut yük de toplama girer (varsayım)."""
    m = tek_tet(1)
    m.loads.append(Load(1, "ux", 1.0))
    yukler.add_loads(m, [Load(1, "ux", 2.0), Load(1, "ux", 3.5), Load(2, "uz", -4.0), Load(1, "uy", 1.0)])
    anahtarlar = [(ld.node, ld.dof) for ld in m.loads]
    assert len(anahtarlar) == len(set(anahtarlar))
    d = yuk_sozlugu(m.loads)
    assert d == pytest.approx({(1, "ux"): 6.5, (2, "uz"): -4.0, (1, "uy"): 1.0})


def test_add_loads_unknown_node_raises():
    m = tek_tet(1)
    with pytest.raises(ModelError):
        yukler.add_loads(m, [Load(99, "ux", 1.0)])


# ---------- K13 kendi ağırlığıyla asılı çubuk ----------

LB, LZ = 20.0, 200.0  # 20 × 20 × 200, üst uç z = L
NU0 = Material("celik_nu0", 210_000.0, 0.0, RHO)
DELTA = RHO * 9810.0 * LZ**2 / (2 * 210_000.0)  # 7.334e-6 mm


def _asili(order: int, k: int):
    m = kutu_agi(LB, LB, LZ, k, k, 5 * k, NU0)
    if order == 2:
        m = tet10_agi(m)
    ust = [n.id for n in m.nodes if abs(n.z - LZ) <= 1e-9]
    m.bcs += [BC(nid, dof) for nid in ust for dof in ("ux", "uy", "uz")]  # ν = 0: tam çözümle uyumlu
    yukler.add_loads(m, yukler.gravity_loads(m, G))
    return m, solve(m)


def test_hanging_bar_delta_value():
    assert DELTA == pytest.approx(7.334e-6, rel=1e-3)


@pytest.mark.parametrize("k", [1, 2])
def test_hanging_bar_tet10_exact(k):
    """tet10: u_z(z) = −ρ g (L² − z²)/(2E) her düğümde (uç δ, göreli 1e-8); eleman σ_zz = ρ g z_merkez."""
    from core import post

    m, r = _asili(2, k)
    for n in m.nodes:
        uz = r.u[m.dof_index(n.id, "uz")]
        assert uz == pytest.approx(
            -RHO * 9810.0 * (LZ**2 - n.z**2) / (2 * 210_000.0), rel=1e-8, abs=1e-8 * DELTA
        )
    alt = yuz_dugumleri(m, 2, 0.0)
    assert u_dugum(m, r.u, alt[0])[2] == pytest.approx(-DELTA, rel=1e-8)
    # Gauss ortalaması doğrusal alanda merkez değeridir
    sig = post.element_stress_tensors(m, r.u)
    for e in m.elements:
        zc = np.mean([m.node(nid).z for nid in e.nodes[:4]])
        assert sig[e.id][2] == pytest.approx(RHO * 9810.0 * zc, rel=1e-8)


def test_hanging_bar_tet4_converges():
    """tet4: uç sehimi hatası k = 1 → 2 → 4 her adımda en az yarıya iner."""
    hatalar = []
    for k in (1, 2, 4):
        m, r = _asili(1, k)
        alt = yuz_dugumleri(m, 2, 0.0)
        uz = np.mean([r.u[m.dof_index(nid, "uz")] for nid in alt])
        hatalar.append(abs(uz + DELTA) / DELTA)
    assert hatalar[1] <= hatalar[0] / 2 and hatalar[2] <= hatalar[1] / 2


@pytest.mark.parametrize("order", [1, 2])
def test_hanging_bar_reactions_sum(order):
    """Tepkiler toplamı −m g, m = ρ V, V = 20·20·200 (göreli 1e-12)."""
    m, r = _asili(order, 1)
    Rz = sum(r.reactions[m.dof_index(bc.node, "uz")] for bc in m.bcs if bc.dof == "uz")
    assert Rz == pytest.approx(-RHO * LB * LB * LZ * G[2], rel=1e-12)


# ---------- K18 ----------


def test_yukler_imports_only_numpy_scipy_core():
    """K18: core/yukler.py yalnız numpy, scipy, core (ve standart kütüphane) import eder."""
    yol = Path(__file__).resolve().parents[2] / "core" / "yukler.py"
    if not yol.exists():
        raise NotImplementedError("SPEC 67b: core/yukler.py henüz yok")
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    izinli = {"numpy", "scipy", "core"} | set(sys.stdlib_module_names)
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            adlar = [a.name for a in dugum.names]
        elif isinstance(dugum, ast.ImportFrom):
            if dugum.level:
                continue
            adlar = [dugum.module or ""]
        else:
            continue
        for ad in adlar:
            assert ad.split(".")[0] in izinli, f"core/yukler.py izin verilmeyen import: {ad}"


# ---------- biçim kuralları ve hatalar (core/yukler.py modül docstring'i) ----------

SIRA = {"ux": 0, "uy": 1, "uz": 2}


@pytest.mark.parametrize("hangi", ["gravity", "centrifugal", "thermal"])
def test_load_list_sorted_unique_nonzero(hangi):
    """Liste düğüm id ve dof sırasıyla; her (düğüm, dof) en çok bir kez; tam sıfır bileşen yazılmaz."""
    m = kutu_agi(20.0, 30.0, 40.0, 2, 1, 1, CELIK)
    if hangi == "gravity":
        loads = yukler.gravity_loads(m, (0.0, 0.0, -9810.0))
    elif hangi == "centrifugal":
        loads = yukler.centrifugal_loads(m, OMEGA, P0, A_EKSEN)
    else:
        loads = yukler.thermal_loads(m, {n.id: 20.0 + n.x for n in m.nodes}, T_REF, ALFA)
    anahtar = [(ld.node, SIRA[ld.dof]) for ld in loads]
    assert anahtar == sorted(set(anahtar))
    assert all(ld.value != 0.0 for ld in loads)
    if hangi == "gravity":
        assert {ld.dof for ld in loads} == {"uz"}


def test_centrifugal_axis_need_not_be_unit():
    m = tek_tet(1)
    a = yuk_sozlugu(yukler.centrifugal_loads(m, OMEGA, P0, A_EKSEN))
    b = yuk_sozlugu(yukler.centrifugal_loads(m, OMEGA, P0, 7.5 * A_EKSEN))
    assert set(a) == set(b)
    for k in a:
        assert b[k] == pytest.approx(a[k], rel=1e-12)


@pytest.mark.parametrize(
    "omega, point, axis",
    [(OMEGA, P0, (0.0, 0.0, 0.0)), (OMEGA, (np.nan, 0.0, 0.0), A_EKSEN), (np.inf, P0, A_EKSEN)],
    ids=["sifir-eksen", "nan-nokta", "inf-omega"],
)
def test_centrifugal_bad_input_raises(omega, point, axis):
    with pytest.raises(ModelError):
        yukler.centrifugal_loads(tek_tet(1), omega, point, axis)


def test_non_solid_model_raises():
    """Eleman tipi tet4 / tet10 değil (bar1d, dim = 1) → ModelError."""
    from core.model import Element, Model, Node, Section

    m = Model(
        dim=1,
        nodes=[Node(1, 0.0), Node(2, 100.0)],
        elements=[Element(1, "bar1d", [1, 2], "celik", "kesit")],
        materials=[CELIK],
        sections=[Section("kesit", 10.0)],
    )
    with pytest.raises(ModelError):
        yukler.gravity_loads(m, G)


def test_thermal_alpha_mapping_missing_material_raises():
    m = tek_tet(1)
    with pytest.raises(ModelError):
        yukler.thermal_loads(m, {n.id: 70.0 for n in m.nodes}, T_REF, {"baska": ALFA})


def test_thermal_tet10_edge_temperature_defaults_to_mean():
    """tet10 kenar düğümünün sıcaklığı verilmezse iki ucun ortalamasıdır."""
    m = tek_tet(2)
    e = m.elements[0]
    Tk = [20.0, 60.0, 100.0, 140.0]
    kose = {nid: Tk[a] for a, nid in enumerate(e.nodes[:4])}
    tam = dict(kose)
    for a, (i, j) in enumerate(KENARLAR):
        tam[e.nodes[4 + a]] = (Tk[i] + Tk[j]) / 2
    a = yuk_sozlugu(yukler.thermal_loads(m, kose, T_REF, ALFA))
    b = yuk_sozlugu(yukler.thermal_loads(m, tam, T_REF, ALFA))
    assert set(a) == set(b)
    for k in a:
        assert a[k] == pytest.approx(b[k], rel=1e-12)
