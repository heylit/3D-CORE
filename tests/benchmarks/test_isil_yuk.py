"""SPEC 67b — ısıl yük benchmark'ları (K15). OCCT'siz: Kuhn kutu ağı (tet_ag.py) ve düz tet10.

Testler sadece specs/67-fem-genisletme.md (67b) Teori / Isıl yük'ten yazıldı; core/yukler.py gövdesi okunmadı.
    ε0 = α (T − T_ref) [1, 1, 1, 0, 0, 0],  f_e = ∫ Bᵀ D ε0 dV,  σ = D (B u − ε0)
Kapalı formlar:
    serbest genleşme (3-2-1 mesnet)   u = α ΔT (x − x0), σ = 0
    eksenel tutulu çubuk               σ_xx = −E α ΔT = −126 MPa (E = 210000, α = 1.2e-5, ΔT = 50)
                                       σ_yy = σ_zz = 0; yanal gerinme (1 + ν) α ΔT → u_y = (1 + ν) α ΔT y
    doğrusal T, serbest gövde          gerilmesiz (tet10 tam; tet4'te eleman sabiti ε0
                                       uyumsuz, inceldikçe azalır)
SPEC 56 düzlem duvarı: T(x) = T1 + (T2 − T1) x / L, T1 = 100, T2 = 20.
"""

from __future__ import annotations

import numpy as np
import pytest

from core import post, yukler
from core.model import BC, Material
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi
from tests.benchmarks.yuk_ag import SahteSicaklik, dugum_bul, mesnet_321, tet10_agi, u_dugum

E, NU, ALFA = 210_000.0, 0.3, 1.2e-5
CELIK = Material("celik", E, NU, 7.85e-9)
LX, LY, LZ = 40.0, 10.0, 20.0
T_REF = 20.0


def _ag(order: int, k: int = 1):
    m = kutu_agi(LX, LY, LZ, 2 * k, k, k, CELIK)
    return m if order == 1 else tet10_agi(m)


def _coz(m, T):
    yukler.add_loads(m, yukler.thermal_loads(m, T, T_REF, ALFA))
    r = solve(m)
    return r.u, yukler.thermal_strain_stress(m, r.u, T, T_REF, ALFA)


def _serbest(m):
    mesnet_321(m, dugum_bul(m, (0, 0, 0)), dugum_bul(m, (LX, 0, 0)), dugum_bul(m, (0, LY, 0)))


@pytest.mark.parametrize("order", [1, 2])
def test_free_expansion(order):
    """ΔT = 50, 3-2-1 mesnet (x0 = orijin): u = α ΔT x (göreli 1e-9), σ_vM ≤ 1e-9 E α ΔT."""
    dT = 50.0
    m = _ag(order)
    _serbest(m)
    u, sigma = _coz(m, {n.id: T_REF + dT for n in m.nodes})
    for n in m.nodes:
        np.testing.assert_allclose(
            u_dugum(m, u, n.id), ALFA * dT * n.xyz, rtol=1e-9, atol=1e-9 * ALFA * dT * LX
        )
    assert np.max(post.von_mises(sigma)) <= 1e-9 * E * ALFA * dT


@pytest.mark.parametrize("order", [1, 2])
def test_axially_restrained_bar(order):
    """x = 0 ve x = L yüzleri u_x = 0, yanal serbest: her elemanda σ_xx = −126 MPa, diğerleri ≈ 0.

    Yanal rijit gövde hareketi tam çözümle uyumlu noktalardan tutulur: (0,0,0) u_y = u_z = 0, (0,b,0) u_z = 0,
    (0,0,h) u_y = 0 (tam çözümde u_y = (1 + ν) α ΔT y, u_z = (1 + ν) α ΔT z).
    """
    dT = 50.0
    m = _ag(order)
    for n in m.nodes:
        if abs(n.x) <= 1e-9 or abs(n.x - LX) <= 1e-9:
            m.bcs.append(BC(n.id, "ux"))
    o = dugum_bul(m, (0, 0, 0))
    m.bcs += [
        BC(o, "uy"),
        BC(o, "uz"),
        BC(dugum_bul(m, (0, LY, 0)), "uz"),
        BC(dugum_bul(m, (0, 0, LZ)), "uy"),
    ]
    _, sigma = _coz(m, {n.id: T_REF + dT for n in m.nodes})
    assert -E * ALFA * dT == pytest.approx(-126.0)
    np.testing.assert_allclose(sigma[:, 0], -126.0, rtol=1e-9)
    np.testing.assert_allclose(sigma[:, 1:], 0.0, atol=1e-9 * 126.0)


def _duvar(m):
    return {n.id: 100.0 + (20.0 - 100.0) * n.x / LX for n in m.nodes}


def test_linear_field_free_body_tet10_stress_free():
    """SPEC 56 duvarının doğrusal alanı serbest gövdede: tet10'da σ_vM ≤ 1e-8 E α ΔT, ΔT = 80."""
    m = _ag(2)
    _serbest(m)
    _, sigma = _coz(m, _duvar(m))
    assert np.max(post.von_mises(sigma)) <= 1e-8 * E * ALFA * 80.0


def test_linear_field_free_body_tet4_decreases():
    """Aynı durumda tet4'te max σ_vM k = 1 → 2 → 4 boyunca azalır (sıfır değil: eleman sabiti ε0 uyumsuz)."""
    maks = []
    for k in (1, 2, 4):
        m = _ag(1, k)
        _serbest(m)
        _, sigma = _coz(m, _duvar(m))
        maks.append(float(np.max(post.von_mises(sigma))))
    assert maks[0] > 0.0
    assert maks[0] > maks[1] > maks[2]


@pytest.mark.parametrize("order", [1, 2])
def test_thermal_result_same_as_dict(order):
    """ThermalResult (ördek tipi: node_ids, T) düğüm sözlüğüyle aynı çözümü verir."""
    m1, m2 = _ag(order), _ag(order)
    _serbest(m1)
    _serbest(m2)
    u1, s1 = _coz(m1, _duvar(m1))
    u2, s2 = _coz(m2, SahteSicaklik.alandan(m2, _duvar(m2)))
    np.testing.assert_allclose(u2, u1, rtol=1e-12, atol=1e-15)
    np.testing.assert_allclose(s2, s1, rtol=1e-12, atol=1e-9)


def test_real_thermal_result_accepted():
    """SPEC 56'nın gerçek ThermalResult'ı doğrudan verilebilir (56 main'e girene kadar "uygulanmamış")."""
    try:
        from core.isil import ThermalResult
    except ImportError:
        raise NotImplementedError("SPEC 56: core.isil.ThermalResult henüz yok") from None
    m1, m2 = _ag(1), _ag(1)
    _serbest(m1)
    _serbest(m2)
    T = _duvar(m1)
    ids = np.array([n.id for n in m2.nodes])
    tr = ThermalResult(
        node_ids=ids, T=np.array([T[i] for i in ids]), R=np.zeros(len(ids)), Q_gen=0.0, Q_flux=0.0, Q_conv=0.0
    )
    u1, _ = _coz(m1, T)
    u2, _ = _coz(m2, tr)
    np.testing.assert_allclose(u2, u1, rtol=1e-12, atol=1e-15)
