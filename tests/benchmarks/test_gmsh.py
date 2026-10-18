"""
SPEC 12 analitik benchmark'ları: parça → gmsh tet4 ağı → mesnet + yük → solve (K11, K12).

Testler sadece specs/12-gmsh.md'den yazıldı; mesh/ uygulama kodu okunmadı.
gmsh ve build123d gerekir (`gmsh` fikstürü: pytest.importorskip, `occt` işareti).

K11: düzgün çekme, tet4 doğrusal alanı tam ürettiği için ağdan bağımsız tam sonuç.
K12: kalın cidarlı silindir (Lamé, Timoshenko–Goodier §33), düzlem şekil değiştirme (iki uçta uz = 0):
    u_r(r) = (1+ν) a² p / (E (b² − a²)) · ((1 − 2ν) r + b²/r)
    σ_θ(r) = p a² / (b² − a²) · (1 + b²/r²)
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

import mesh
from core import post
from core.model import Material, Model
from core.solver import solve
from tests.benchmarks.test_tet4 import denge_kontrol, dugum_dizileri

E, NU = 210_000.0, 0.3

pytestmark = pytest.mark.occt


@pytest.fixture
def gmsh():
    return pytest.importorskip("gmsh", reason='gmsh kurulu değil (pip install -e ".[mesh]")')


def celik() -> Material:
    return Material("celik", E, NU)


# --- K11: düzgün çekme ---------------------------------------------------------------

LX, LY, LZ = 100.0, 20.0, 10.0
SIGMA = 100.0  # MPa


@functools.cache
def cekme():
    import build123d as bd

    from geometry.part import Part

    parca = Part(bd.Box(LX, LY, LZ, align=(bd.Align.MIN,) * 3), name="blok")
    m = mesh.tet_mesh(parca, 5.0, celik())
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (1, 0, 0))), dofs=("ux",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 1, 0))), dofs=("uy",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 0, 1))), dofs=("uz",))
    uc = mesh.select_triangles(m, mesh.on_plane((LX, 0, 0), (1, 0, 0)))
    mesh.add_traction(m, uc, (SIGMA, 0.0, 0.0))
    return m, solve(m)


def test_cekme_ag_duzensiz(gmsh):
    """Ağ gerçekten gmsh'ten: tet4, düzensiz (yapılandırılmış ızgara değil), uç yükü tam σ · A."""
    m, _ = cekme()
    assert all(e.type == "tet4" for e in m.elements)
    assert len(m.elements) > 100
    F = sum(ld.value for ld in m.loads if ld.dof == "ux")
    assert F == pytest.approx(SIGMA * LY * LZ, rel=1e-12)


def test_cekme_gerilme_her_elemanda(gmsh):
    """Her elemanda σ = (100, 0, 0, 0, 0, 0) MPa (abs 1e-9 · 100)."""
    m, r = cekme()
    S = post.element_stress_tensors(m, r.u)
    assert set(S) == {e.id for e in m.elements}
    sigma = np.array([S[e.id] for e in m.elements])
    np.testing.assert_allclose(sigma, np.tile([SIGMA, 0, 0, 0, 0, 0], (len(sigma), 1)), atol=1e-9 * SIGMA)


def test_cekme_yer_degistirme_her_dugumde(gmsh):
    """u = (σ x / E, −ν σ y / E, −ν σ z / E) (abs 1e-9 · σ L / E)."""
    m, r = cekme()
    X = np.array([n.xyz for n in m.nodes])
    U = dugum_dizileri(m, r.u)
    beklenen = SIGMA / E * X * np.array([1.0, -NU, -NU])
    np.testing.assert_allclose(U, beklenen, atol=1e-9 * SIGMA * LX / E)


def test_cekme_denge(gmsh):
    m, r = cekme()
    denge_kontrol(m, r)


# --- K12: kalın cidarlı silindir (Lamé) -------------------------------------------------

a, b, BOY, P = 10.0, 20.0, 5.0, 100.0


def u_r(r: np.ndarray | float) -> np.ndarray | float:
    return (1 + NU) * a**2 * P / (E * (b**2 - a**2)) * ((1 - 2 * NU) * r + b**2 / r)


def sigma_theta(r: np.ndarray | float) -> np.ndarray | float:
    return P * a**2 / (b**2 - a**2) * (1 + b**2 / r**2)


def ceyrek_halka():
    """Birinci çeyrekte halka: a ≤ r ≤ b, x, y ≥ 0, 0 ≤ z ≤ BOY."""
    import build123d as bd

    from geometry.part import Part

    hiza = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    halka = bd.Cylinder(b, BOY, align=hiza) - bd.Cylinder(a, BOY, align=hiza)
    ceyrek = halka & bd.Box(b, b, BOY, align=(bd.Align.MIN,) * 3)
    return Part(ceyrek, name="ceyrek_halka")


@functools.cache
def lame(h: float) -> tuple[Model, object, list[int]]:
    m = mesh.tet_mesh(ceyrek_halka(), h, celik())
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (1, 0, 0))), dofs=("ux",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 1, 0))), dofs=("uy",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 0, 1))), dofs=("uz",))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, BOY), (0, 0, 1))), dofs=("uz",))
    ic = mesh.on_cylinder((0, 0, 0), (0, 0, 1), a)
    mesh.add_pressure(m, mesh.select_triangles(m, ic), P)
    return m, solve(m), mesh.select_nodes(m, ic)


def ic_yuzey_hatasi(h: float) -> float:
    """e_h = 1 − ū_r / u_r(a); ū_r iç yüzey düğümlerinin ortalama radyal yer değiştirmesi."""
    m, r, ic = lame(h)
    ur = []
    for nid in ic:
        x, y, _ = m.node(nid).xyz
        ux, uy = r.u[m.dof_index(nid, "ux")], r.u[m.dof_index(nid, "uy")]
        ur.append((ux * x + uy * y) / math.hypot(x, y))
    return 1.0 - float(np.mean(ur)) / u_r(a)


def sigma_theta_rms(h: float) -> float:
    """Eleman ağırlık merkezinde σ_θ = t·σ·t (t = (−y, x, 0)/r) ile σ_θ(r_c) arasındaki göreli RMS hata."""
    m, r, _ = lame(h)
    S = post.element_stress_tensors(m, r.u)
    hatalar = []
    for e in m.elements:
        c = np.mean([m.node(n).xyz for n in e.nodes], axis=0)
        rc = math.hypot(c[0], c[1])
        tx, ty = -c[1] / rc, c[0] / rc
        sxx, syy, _, sxy, _, _ = S[e.id]
        st = sxx * tx**2 + syy * ty**2 + 2 * sxy * tx * ty
        hatalar.append(st / sigma_theta(rc) - 1.0)
    return float(np.sqrt(np.mean(np.square(hatalar))))


def test_lame_parca_ve_secim(gmsh):
    """Çeyrek halka hacmi π/4 (b² − a²) BOY (rel 1e-2, yay kiriş hatası); iç yüzeyde düğüm var."""
    m, _, ic = lame(2.0)
    X = {n.id: n.xyz for n in m.nodes}
    V = sum(abs(np.linalg.det(np.array([X[n] for n in e.nodes[1:]]) - X[e.nodes[0]])) / 6 for e in m.elements)
    assert V == pytest.approx(math.pi / 4 * (b**2 - a**2) * BOY, rel=1e-2)
    assert len(ic) > 10


def test_lame_ic_yuzey_yer_degistirme(gmsh):
    """
    e_h = 1 − ū_r/u_r(a): h = 4, 2, 1'de azalır, e_2 ≤ %3, e_1 ≤ %1.5, hepsi > 0 (uyumlu eleman: alttan).
    Ön hesap: %6.1, %1.9, %0.64.
    """
    e = [ic_yuzey_hatasi(h) for h in (4.0, 2.0, 1.0)]
    assert all(x > 0 for x in e), e
    assert e[0] > e[1] > e[2], e
    assert e[1] <= 0.03, e
    assert e[2] <= 0.015, e


def test_lame_teget_gerilme(gmsh):
    """σ_θ göreli RMS hatası: h = 1'de ≤ %8 ve ≤ 0.7 × (h = 2 değeri). Ön hesap: %9.6 → %5.3."""
    e2, e1 = sigma_theta_rms(2.0), sigma_theta_rms(1.0)
    assert e1 <= 0.08, (e2, e1)
    assert e1 <= 0.7 * e2, (e2, e1)


@pytest.mark.parametrize("h", [4.0, 2.0])
def test_lame_denge(gmsh, h):
    m, r, _ = lame(h)
    denge_kontrol(m, r)
