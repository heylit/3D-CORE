"""
SPEC 56 — kararlı hal ısı iletimi, kapalı formüllü benchmark'lar (K3–K6, K8).

Ağ: Kuhn bölümlü kutu (tests/benchmarks/tet_ag.py), `n × n × n` bölme; OCCT ve gmsh gerekmez.
Birimler: mW, mm, °C. El hesapları (Incropera bölüm 3):

K3 düzlem duvar, L = 100, A = 50·50 = 2500, k = 50, T1 = 100, T2 = 20:
    q = k (T1 − T2) / L = 50·80/100 = 40 mW/mm²,  Q = q A = 1.0e5 mW (sıcak yüz +, soğuk yüz −)
K4 duvar + taşınım, T0 = 100, h = 0.025, T∞ = 20:
    q = (T0 − T∞) / (L/k + 1/h) = 80 / (2 + 40) = 1.9047619…,  T(L) = T0 − q L/k = 100 − 2q = 96.190476…
    Q_conv = −q A = −4761.9…  (taşınım yüzünden giren ısı negatif: soğutma)
K5 duvar + akı, T0 = 20, q̄ = 2 (x = L'den giren):
    T(x) = T0 + q̄ x / k → T(L) = 20 + 2·100/50 = 24;  Σ R = −q̄ A = −5000 mW
K6 ısı üreten küp 20³, x = 0 ve x = 20'de T0 = 0, k = 15, Q = 1:
    Σ R = −Q V = −8000 mW;  T_maks = T0 + Q L²/(8k) = 400/120 = 3.3333…
    T(x) = Q x (L − x) / (2k). Doğrusal eleman + tutarlı yükle bu 1B problemde düğüm değerleri tam
    (Kararlar K-1).
K8: her durumda Σ R + Q_gen + Q_flux + Q_conv = 0 (göreli 1e-9, en büyük terime göre).
"""

from __future__ import annotations

import functools

import numpy as np
import pytest

import mesh
from core import isil
from core.isil import Convection, HeatFlux, Temperature, ThermalResult, solve_thermal
from core.model import Material, Model
from tests.benchmarks.tet_ag import kutu_agi

L, B, H = 100.0, 50.0, 50.0
A = B * H
K = 50.0
AGLAR = [1, 3]


def duvar(n: int, L_=L, B_=B, H_=H) -> Model:
    return kutu_agi(L_, B_, H_, n, n, n, Material("celik", 210_000.0, 0.3), name=f"duvar_{n}")


def duzlem(eksen: int, deger: float):
    p = [0.0, 0.0, 0.0]
    nrm = [0.0, 0.0, 0.0]
    p[eksen], nrm[eksen] = deger, 1.0
    return mesh.on_plane(tuple(p), tuple(nrm))


def yuz_sicakligi(m: Model, eksen: int, deger: float, T: float) -> list[Temperature]:
    dugumler = mesh.select_nodes(m, duzlem(eksen, deger))
    assert dugumler
    return [Temperature(n, T) for n in dugumler]


def yuz_ucgenleri(m: Model, eksen: int, deger: float) -> np.ndarray:
    tris = mesh.select_triangles(m, duzlem(eksen, deger))
    assert len(tris) > 0
    return tris


def x_dizisi(m: Model) -> np.ndarray:
    return np.array([n.x for n in m.nodes])


def yuz_toplami(m: Model, r: ThermalResult, eksen: int, deger: float) -> float:
    ids = set(mesh.select_nodes(m, duzlem(eksen, deger)))
    return float(sum(Rn for nid, Rn in zip(r.node_ids, r.R, strict=True) if int(nid) in ids))


def denge(r: ThermalResult) -> None:
    """K8: Σ R + Q_gen + Q_flux + Q_conv = 0 (göreli 1e-9, en büyük terime göre)."""
    terimler = [float(np.sum(r.R)), r.Q_gen, r.Q_flux, r.Q_conv]
    # en büyük terim: tutulu yüzlerden giren / çıkan ısı da sayılır (K3'te Σ R = 0 ama yüz başına 1e5)
    olcek = max([abs(t) for t in terimler] + [float(r.R[r.R > 0].sum()), float(-r.R[r.R < 0].sum())])
    assert olcek > 0
    assert abs(sum(terimler)) <= 1e-9 * olcek, terimler


# --- K3: düzlem duvar ---------------------------------------------------------------------------


@functools.cache
def k3(n: int):
    m = duvar(n)
    temps = yuz_sicakligi(m, 0, 0.0, 100.0) + yuz_sicakligi(m, 0, L, 20.0)
    return m, solve_thermal(m, K, temperatures=temps)


@pytest.mark.parametrize("n", AGLAR, ids=lambda n: f"n{n}")
def test_k3_linear_temperature(n):
    m, r = k3(n)
    np.testing.assert_allclose(r.T, 100.0 - 80.0 * x_dizisi(m) / L, rtol=0, atol=1e-9)


@pytest.mark.parametrize("n", AGLAR, ids=lambda n: f"n{n}")
def test_k3_element_flux(n):
    m, r = k3(n)
    q = isil.heat_flux(m, K, r)
    np.testing.assert_allclose(q, np.tile([40.0, 0.0, 0.0], (len(m.elements), 1)), rtol=1e-9, atol=1e-9 * 40)
    qn = isil.nodal_heat_flux(m, K, r)
    np.testing.assert_allclose(qn, np.tile([40.0, 0.0, 0.0], (len(m.nodes), 1)), rtol=1e-9, atol=1e-9 * 40)


@pytest.mark.parametrize("n", AGLAR, ids=lambda n: f"n{n}")
def test_k3_face_reactions(n):
    m, r = k3(n)
    assert yuz_toplami(m, r, 0, 0.0) == pytest.approx(1.0e5, rel=1e-9)
    assert yuz_toplami(m, r, 0, L) == pytest.approx(-1.0e5, rel=1e-9)
    assert r.Q_gen == 0.0 and r.Q_flux == 0.0 and r.Q_conv == 0.0
    denge(r)


def test_k3_per_material_k_mapping():
    """Aynı duvar `k` sözlüğüyle (Material.name → k): aynı sonuç."""
    m = duvar(1)
    temps = yuz_sicakligi(m, 0, 0.0, 100.0) + yuz_sicakligi(m, 0, L, 20.0)
    r = solve_thermal(m, {"celik": K}, temperatures=temps)
    np.testing.assert_allclose(r.T, 100.0 - 80.0 * x_dizisi(m) / L, rtol=0, atol=1e-9)
    assert yuz_toplami(m, r, 0, 0.0) == pytest.approx(1.0e5, rel=1e-9)


# --- K4: taşınım --------------------------------------------------------------------------------

H_FILM, T_INF, T0_K4 = 0.025, 20.0, 100.0
Q_K4 = (T0_K4 - T_INF) / (L / K + 1.0 / H_FILM)  # 80/42


@functools.cache
def k4(n: int):
    m = duvar(n)
    r = solve_thermal(
        m,
        K,
        temperatures=yuz_sicakligi(m, 0, 0.0, T0_K4),
        convection=[Convection(yuz_ucgenleri(m, 0, L), H_FILM, T_INF)],
    )
    return m, r


def test_k4_hand_values():
    assert Q_K4 == pytest.approx(80.0 / 42.0, rel=1e-15)
    assert Q_K4 == pytest.approx(1.904762, abs=5e-7)
    assert T0_K4 - Q_K4 * L / K == pytest.approx(96.190476, abs=5e-7)


@pytest.mark.parametrize("n", AGLAR, ids=lambda n: f"n{n}")
def test_k4_end_temperature_and_linear(n):
    m, r = k4(n)
    T_L = T0_K4 - Q_K4 * L / K
    x = x_dizisi(m)
    for nid, xi, Ti in zip(r.node_ids, x, r.T, strict=True):
        if abs(xi - L) <= 1e-9:
            assert Ti == pytest.approx(T_L, abs=1e-9), nid
    np.testing.assert_allclose(r.T, T0_K4 - Q_K4 * x / K, rtol=0, atol=1e-9)


@pytest.mark.parametrize("n", AGLAR, ids=lambda n: f"n{n}")
def test_k4_convection_heat(n):
    m, r = k4(n)
    assert r.Q_conv == pytest.approx(-Q_K4 * A, rel=1e-9)
    assert r.Q_conv == pytest.approx(-4761.9, abs=0.05)
    assert yuz_toplami(m, r, 0, 0.0) == pytest.approx(Q_K4 * A, rel=1e-9)
    assert r.Q_gen == 0.0 and r.Q_flux == 0.0
    denge(r)


def test_k4_convection_only_no_dirichlet():
    """Γ_T boş, yalnız taşınım: sistem tekil değil; iki uçta taşınım, aynı T∞ → her yer T∞, ısı 0."""
    m = duvar(1)
    r = solve_thermal(
        m,
        K,
        convection=[
            Convection(yuz_ucgenleri(m, 0, 0.0), H_FILM, 35.0),
            Convection(yuz_ucgenleri(m, 0, L), 2 * H_FILM, 35.0),
        ],
    )
    np.testing.assert_allclose(r.T, 35.0, rtol=0, atol=1e-9)
    assert np.all(r.R == 0.0)


def test_k4_convection_both_ends_series_resistance():
    """İki uçta taşınım (T∞1 = 100, h1; T∞2 = 0, h2): q = ΔT / (1/h1 + L/k + 1/h2)."""
    m = duvar(3)
    h1, h2 = 0.05, 0.02
    r = solve_thermal(
        m,
        K,
        convection=[
            Convection(yuz_ucgenleri(m, 0, 0.0), h1, 100.0),
            Convection(yuz_ucgenleri(m, 0, L), h2, 0.0),
        ],
    )
    q = 100.0 / (1 / h1 + L / K + 1 / h2)
    T_sol = 100.0 - q / h1
    np.testing.assert_allclose(r.T, T_sol - q * x_dizisi(m) / K, rtol=0, atol=1e-9)
    assert abs(r.Q_conv) <= 1e-9 * q * A  # giren = çıkan
    denge_terimleri = abs(r.Q_conv + float(np.sum(r.R)))
    assert denge_terimleri <= 1e-9 * q * A


# --- K5: akı ------------------------------------------------------------------------------------


@functools.cache
def k5(n: int):
    m = duvar(n)
    r = solve_thermal(
        m,
        K,
        temperatures=yuz_sicakligi(m, 0, 0.0, 20.0),
        fluxes=[HeatFlux(yuz_ucgenleri(m, 0, L), 2.0)],
    )
    return m, r


@pytest.mark.parametrize("n", AGLAR, ids=lambda n: f"n{n}")
def test_k5_temperature(n):
    m, r = k5(n)
    x = x_dizisi(m)
    np.testing.assert_allclose(r.T, 20.0 + 2.0 * x / K, rtol=0, atol=1e-9)
    assert r.T[np.argmax(x)] == pytest.approx(24.0, abs=1e-9)


@pytest.mark.parametrize("n", AGLAR, ids=lambda n: f"n{n}")
def test_k5_reactions_and_balance(n):
    _, r = k5(n)
    assert r.Q_flux == pytest.approx(2.0 * A, rel=1e-12)
    assert float(np.sum(r.R)) == pytest.approx(-5000.0, rel=1e-9)
    assert r.Q_gen == 0.0 and r.Q_conv == 0.0
    denge(r)


# --- K6: ısı üreten küp -------------------------------------------------------------------------

L6, K6_k, Q6 = 20.0, 15.0, 1.0
T_MAKS = Q6 * L6**2 / (8 * K6_k)


@functools.cache
def k6(n: int):
    m = duvar(n, L6, L6, L6)
    temps = yuz_sicakligi(m, 0, 0.0, 0.0) + yuz_sicakligi(m, 0, L6, 0.0)
    return n, m, solve_thermal(m, K6_k, temperatures=temps, Q=Q6)


@pytest.mark.parametrize("n", [2, 4], ids=lambda n: f"n{n}")
def test_k6_total_reaction(n):
    _, _, r = k6(n)
    assert T_MAKS == pytest.approx(400.0 / 120.0, rel=1e-15)
    assert r.Q_gen == pytest.approx(Q6 * L6**3, rel=1e-12)
    assert float(np.sum(r.R)) == pytest.approx(-8000.0, rel=1e-10)
    assert r.Q_flux == 0.0 and r.Q_conv == 0.0
    denge(r)


@pytest.mark.parametrize("n", [2, 4], ids=lambda n: f"n{n}")
def test_k6_mid_plane_temperature(n):
    """x = 10 düğüm ortalaması: n = 2'de %3, n = 4'te %1; her iki ağda göreli 1e-9 (Kararlar K-1)."""
    n, m, r = k6(n)
    x = x_dizisi(m)
    orta = np.abs(x - L6 / 2) <= 1e-9
    assert orta.any()
    T_ort = float(np.mean(r.T[orta]))
    assert abs(T_ort / T_MAKS - 1) <= (0.03 if n == 2 else 0.01)
    assert T_ort == pytest.approx(T_MAKS, rel=1e-9)


@pytest.mark.parametrize("n", [2, 4], ids=lambda n: f"n{n}")
def test_k6_nodal_values_exact(n):
    """1B problem, doğrusal eleman + tutarlı yük: her düğümde T = Q x (L − x) / (2k)."""
    _, m, r = k6(n)
    x = x_dizisi(m)
    np.testing.assert_allclose(r.T, Q6 * x * (L6 - x) / (2 * K6_k), rtol=0, atol=1e-9 * T_MAKS)


@pytest.mark.parametrize("n", [2, 4], ids=lambda n: f"n{n}")
def test_k6_faces_share_heat_equally(n):
    _, m, r = k6(n)
    assert yuz_toplami(m, r, 0, 0.0) == pytest.approx(-4000.0, rel=1e-9)
    assert yuz_toplami(m, r, 0, L6) == pytest.approx(-4000.0, rel=1e-9)
