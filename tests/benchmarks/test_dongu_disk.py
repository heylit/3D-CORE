"""SPEC 67b — dönen ince disk benchmark'ı (K14). gmsh + OCCT gerektirir.

Testler sadece specs/67-fem-genisletme.md (67b) Teori / Hacim kuvvetleri'nden yazıldı; core/yukler.py gövdesi
okunmadı. Disk: yarıçap b = 100, kalınlık t = 5, delik yok, çelik (ν = 0.3, ρ = 7.85e-9), ω = 1000 rad/s,
eksen z.
Düzlem gerilme kapalı formu (Timoshenko–Goodier § 32):
    σ_r = (3 + ν)/8 · ρ ω² (b² − r²),   σ_θ = ρ ω²/8 · [(3 + ν) b² − (1 + 3ν) r²]
    ρ ω² b² = 78.5 MPa → merkezde σ_r = σ_θ = 32.38 MPa, kenarda σ_θ = 13.74 MPa
Gerilme çözümü simetriden 1/8 modelle (x ≥ 0, y ≥ 0, 0 ≤ z ≤ t/2; x = 0, y = 0, z = 0 düzlemlerinde simetri
mesnedi; z = 0 orta düzlemdir). Tam çözüm bu mesnetleri sağlar (u_x ∝ x/r, u_z ∝ z). Merkezkaç yükü toplamı
tam disk ağında da denetlenir. tet10 ağı (order = 2) SPEC 67a'dır; 67a gelene kadar "uygulanmamış".
"""

from __future__ import annotations

import numpy as np
import pytest

from core import post, yukler
from core.model import Material
from core.solver import solve
from tests.benchmarks.yuk_ag import tet10_hacim_merkez, tet_hacmi, toplam_kuvvet

pytestmark = pytest.mark.occt

B_R, T_K, NU, RHO, OMEGA = 100.0, 5.0, 0.3, 7.85e-9, 1000.0
CELIK = Material("celik", 210_000.0, NU, RHO)
S0 = RHO * OMEGA**2 * B_R**2  # 78.5 MPa
TOL = 1e-6


def _mesh():
    pytest.importorskip("gmsh")
    import mesh

    return mesh


def _ag(sekizde_bir: bool, order: int):
    mesh = _mesh()
    from build123d import Cylinder

    from geometry.part import Part

    if sekizde_bir:
        sekil = Cylinder(B_R, T_K / 2, arc_size=90, align=None)  # x, y ≥ 0, z ∈ [0, t/2]
    else:
        sekil = Cylinder(B_R, T_K)
    kw = {"order": order} if order != 1 else {}
    return mesh.tet_mesh(Part(sekil, name="disk"), 5.0, CELIK, **kw)


def test_closed_form_values():
    assert S0 == pytest.approx(78.5, rel=1e-12)
    assert (3 + NU) / 8 * S0 == pytest.approx(32.38, abs=5e-3)
    assert S0 / 8 * ((3 + NU) - (1 + 3 * NU)) == pytest.approx(13.74, abs=5e-3)


def _beklenen_toplam(m) -> np.ndarray:
    """ρ ω² Σ_e V_e r⊥(merkez_e), eksen z orijinden: r⊥ = (x, y, 0)."""
    F = np.zeros(3)
    for e in m.elements:
        X = np.array([m.node(n).xyz for n in e.nodes])
        if len(e.nodes) == 4:
            V, c = abs(tet_hacmi(X)), X.mean(axis=0)
        else:
            V, c = tet10_hacim_merkez(X)
        F += V * np.array([c[0], c[1], 0.0])
    return RHO * OMEGA**2 * F


@pytest.mark.slow
@pytest.mark.parametrize("order", [1, 2])
def test_centrifugal_total_full_disk(order):
    """Toplam = ρ ω² Σ_e V_e r⊥(merkez_e) (göreli 1e-12) ve |toplam| ≤ 1e-3 ρ ω² b V (ağ simetriye yakın)."""
    m = _ag(False, order)
    loads = yukler.centrifugal_loads(m, OMEGA, (0, 0, 0), (0, 0, 1))
    F = toplam_kuvvet(loads)
    beklenen = _beklenen_toplam(m)
    V = np.pi * B_R**2 * T_K
    np.testing.assert_allclose(F, beklenen, rtol=1e-12, atol=1e-12 * RHO * OMEGA**2 * B_R * V)
    assert np.linalg.norm(F) <= 1e-3 * RHO * OMEGA**2 * B_R * V


@pytest.mark.slow
def test_centrifugal_total_octant():
    """1/8 modelde toplam yine ρ ω² Σ_e V_e r⊥(merkez_e) (tet10, eğri kenar elemanları dahil)."""
    m = _ag(True, 2)
    F = toplam_kuvvet(yukler.centrifugal_loads(m, OMEGA, (0, 0, 0), (0, 0, 1)))
    np.testing.assert_allclose(F, _beklenen_toplam(m), rtol=1e-12)


_COZUM: dict = {}


def disk_cozumu():
    """1/8 disk (tet10) çözümü, modülde bir kez (fixture değil: 67a yokken "uygulanmamış" düşer)."""
    if _COZUM:
        return _COZUM["m"], _COZUM["d"]
    mesh = _mesh()
    m = _ag(True, 2)
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (1, 0, 0))), dofs=("ux",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 1, 0))), dofs=("uy",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 0, 1))), dofs=("uz",))
    yukler.add_loads(m, yukler.centrifugal_loads(m, OMEGA, (0, 0, 0), (0, 0, 1)))
    r = solve(m)
    _COZUM.update(m=m, d=post.nodal_stress_tensors(m, r.u))
    return _COZUM["m"], _COZUM["d"]


def _kutupsal(m, d, sec):
    """Seçilen düğümlerde (σ_r, σ_θ): n = (x, y, 0)/r, t = (−y, x, 0)/r."""
    sr, st = [], []
    for n in m.nodes:
        x, y, z = n.xyz
        r = float(np.hypot(x, y))
        if r < TOL or not sec(r, z):
            continue
        s = d[n.id]
        S = np.array([[s[0], s[3], s[4]], [s[3], s[1], s[5]], [s[4], s[5], s[2]]])
        nr, nt = np.array([x, y, 0.0]) / r, np.array([-y, x, 0.0]) / r
        sr.append(nr @ S @ nr)
        st.append(nt @ S @ nt)
    assert sr, "seçimde düğüm yok"
    return np.mean(sr), np.mean(st)


@pytest.mark.slow
def test_rotating_disk_center():
    """Orta düzlemde r < 10: σ_r ve σ_θ ortalamaları 32.38 MPa'ya %3 içinde."""
    m, d = disk_cozumu()
    sr, st = _kutupsal(m, d, lambda r, z: r < 10.0 and abs(z) <= TOL)
    hedef = (3 + NU) / 8 * S0
    assert sr == pytest.approx(hedef, rel=0.03)
    assert st == pytest.approx(hedef, rel=0.03)


@pytest.mark.slow
def test_rotating_disk_rim_hoop():
    """Kenarda (r = b, orta düzlem) σ_θ ortalaması 13.74 MPa'ya %3 içinde."""
    m, d = disk_cozumu()
    _, st = _kutupsal(m, d, lambda r, z: abs(r - B_R) <= 1e-3 and abs(z) <= TOL)
    assert st == pytest.approx(S0 / 8 * ((3 + NU) - (1 + 3 * NU)), rel=0.03)
