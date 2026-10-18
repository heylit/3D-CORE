"""
SPEC 13 — delikli plaka (Kirsch) benchmark'ı (K5).

Plaka 200 × 100 × 2, merkezde d = 10 delik, uzak alan çekmesi σ = 1 MPa (x yönünde). Simetriden 1/8 model:
[0, 100] × [0, 50] × [0, 1], delik ekseni z, merkezi orijinde; x = 0, y = 0, z = 0 düzlemlerinde simetri.
Analitik (Heywood, sonlu genişlik, brüt kesit): d/W = 0.1 → Kt_g = (2 + (1 − d/W)³) / (1 − d/W) = 3.032.
Sonsuz plakada θ = 0° noktasında σ_yy = −σ (Kirsch).

Kt, delik kenarında x = 0 düzlemindeki düğümlerin (y = 5) düğüm σ_xx ortalamasıdır
(kalınlık boyunca ortalama).
Ağ SPEC 12 `mesh.tet_mesh` ile; gmsh, build123d veya `mesh.tet_mesh` yoksa atlanır.
"""

from __future__ import annotations

import numpy as np
import pytest

from core import post
from core.model import Material
from core.solver import solve

pytestmark = [pytest.mark.slow, pytest.mark.occt]

L, B, T = 100.0, 50.0, 1.0  # 1/8 model boyutları [mm]
R = 5.0  # delik yarıçapı [mm]
SIGMA = 1.0  # uzak alan çekmesi [MPa]
TOL = 1e-6  # düğüm seçimi [mm]


def kt_heywood(d_W: float) -> float:
    return (2.0 + (1.0 - d_W) ** 3) / (1.0 - d_W)


@pytest.fixture(scope="module")
def cozum():
    pytest.importorskip("gmsh")
    import mesh

    if not hasattr(mesh, "tet_mesh"):
        pytest.skip("SPEC 12 (mesh.tet_mesh) henüz main'de değil")
    from build123d import Align, Box, Cylinder, Pos

    from geometry.part import Part

    sekil = Box(L, B, T, align=(Align.MIN, Align.MIN, Align.MIN)) - Pos(0, 0, T / 2) * Cylinder(R, 3 * T)
    m = mesh.tet_mesh(
        Part(sekil, name="kirsch"),
        h=5.0,
        material=Material("celik", 210_000.0, 0.3),
        refine=[mesh.Refine((0.0, 0.0, 0.5), 8.0, 0.25)],
    )
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (1, 0, 0))), dofs=("ux",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 1, 0))), dofs=("uy",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 0, 1))), dofs=("uz",))
    mesh.add_traction(m, mesh.select_triangles(m, mesh.on_plane((L, 0, 0), (1, 0, 0))), (SIGMA, 0.0, 0.0))
    r = solve(m)
    d = post.nodal_stress_tensors(m, r.u)
    X = {n.id: n.xyz for n in m.nodes}
    return m, d, X


def delik_kenari(X: dict[int, np.ndarray], nid: int) -> bool:
    x, y, _ = X[nid]
    return abs(np.hypot(x, y) - R) <= TOL


def test_every_node_has_stress(cozum):
    m, d, _ = cozum
    assert set(d) == {n.id for n in m.nodes}


def test_kt_at_hole_edge(cozum):
    """|Kt / 3.032 − 1| ≤ %3 (ön hesap 3.031)."""
    _, d, X = cozum
    kenar = [n for n in d if abs(X[n][0]) <= TOL and abs(X[n][1] - R) <= TOL]
    assert len(kenar) >= 2, "x = 0, y = 5 kenarında düğüm bulunamadı"
    Kt = np.mean([d[n][0] for n in kenar]) / SIGMA
    assert kt_heywood(0.1) == pytest.approx(3.032, abs=5e-4)
    assert abs(Kt / 3.032 - 1.0) <= 0.03, f"Kt = {Kt:.4f}"


def test_compressive_stress_at_theta_zero(cozum):
    """y = 0 kenarındaki delik düğümlerinde (x = 5) ortalama σ_yy / σ ∈ [−1.10, −0.90] (ön hesap −1.03)."""
    _, d, X = cozum
    kenar = [n for n in d if abs(X[n][1]) <= TOL and abs(X[n][0] - R) <= TOL]
    assert len(kenar) >= 2, "y = 0, x = 5 kenarında düğüm bulunamadı"
    oran = np.mean([d[n][1] for n in kenar]) / SIGMA
    assert -1.10 <= oran <= -0.90, f"σ_yy / σ = {oran:.4f}"


def test_max_von_mises_at_hole_near_x0(cozum):
    """En büyük düğüm von Mises'i delik kenarında ve x = 0 düzlemine 1 mm'den yakın bir düğümde."""
    _, d, X = cozum
    ids = list(d)
    vm = post.von_mises(np.array([d[n] for n in ids]))
    enb = ids[int(np.argmax(vm))]
    assert delik_kenari(X, enb), f"en büyük σ_vM düğümü {enb} delik kenarında değil: {X[enb]}"
    assert X[enb][0] < 1.0, f"en büyük σ_vM düğümü x = 0'a uzak: {X[enb]}"
