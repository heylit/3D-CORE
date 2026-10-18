"""
SPEC 45 parça → ağ → analiz zinciri (specs/45-modal.md, K15).

Testler yalnız SPEC metninden yazıldı; analiz/ uygulama kodu okunmadı. gmsh + build123d gerekir
(`occt` işareti; gmsh yoksa pytest.importorskip ile atlanır).

Referans: 100 × 10 × 10 çelik konsol, x = 0 yüzü sabit.
    f₁,EB = (β₁L)² / (2πL²) · √(EI/(ρA)), β₁L = 1.875104   (≈ 835.52 Hz)
    δ_T = PL³/(3EI) + PL/(κGA), κ = 5/6
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

import mesh
from analiz import Sehim, parca_modal, parca_sehimi
from core.modal import ModalResult
from core.model import Material, Model, ModelError

pytestmark = pytest.mark.occt

E, NU, RHO = 210_000.0, 0.3, 7.85e-9
L, B, H = 100.0, 10.0, 10.0
I_KESIT = B * H**3 / 12.0
A_KESIT = B * H
G = E / (2 * (1 + NU))
F1_EB = 1.875104**2 / (2 * math.pi * L**2) * math.sqrt(E * I_KESIT / (RHO * A_KESIT))
P = 400.0
DELTA_T = P * L**3 / (3 * E * I_KESIT) + P * L / (5 / 6 * G * A_KESIT)
H_AG = 2.5


@pytest.fixture
def gmsh():
    return pytest.importorskip("gmsh", reason='gmsh kurulu değil (pip install -e ".[mesh]")')


def celik() -> Material:
    return Material("St", E, NU, RHO)


def kutu():
    import build123d as bd

    from geometry.part import Part

    return Part(bd.Box(L, B, H, align=(bd.Align.MIN,) * 3), name="konsol")


def sabit():
    return [mesh.on_plane((0, 0, 0), (1, 0, 0))]


@functools.cache
def modal_sonucu() -> tuple[Model, ModalResult]:
    return parca_modal(kutu(), H_AG, celik(), sabit(), n_modes=6)


@functools.cache
def sehim_sonucu() -> tuple[Model, Sehim]:
    return parca_sehimi(kutu(), H_AG, celik(), sabit(), nokta=(L, B / 2, H / 2), F=(0, 0, -P), yaricap=3.0)


def x0_dugumleri(m: Model) -> set[int]:
    return {n.id for n in m.nodes if abs(n.x) <= 1e-6}


def test_parca_modal_birinci_frekans(gmsh):
    m, r = modal_sonucu()
    assert len(r.f) == 6
    assert np.all(np.diff(r.f) >= 0)
    assert 0.99 <= r.f[0] / F1_EB <= 1.35


def test_parca_modal_sabit_yuz_tutulu(gmsh):
    """x = 0 yüzündeki her düğümün üç DOF'u tutulu; mod şekilleri orada sıfır."""
    m, r = modal_sonucu()
    assert all(e.type == "tet4" for e in m.elements)
    tutulu = {(bc.node, bc.dof) for bc in m.bcs}
    x0 = x0_dugumleri(m)
    assert x0
    assert {(n, d) for n in x0 for d in ("ux", "uy", "uz")} == tutulu
    for n in x0:
        for d in ("ux", "uy", "uz"):
            assert np.all(r.modes[m.dof_index(n, d)] == 0.0)


def test_parca_sehimi_uc_yuz_merkezi(gmsh):
    m, s = sehim_sonucu()
    assert 0.6 <= s.delta / DELTA_T < 1.0
    assert s.k == pytest.approx(P / s.delta, rel=1e-12)
    assert s.dugumler


def test_parca_sehimi_mesnet(gmsh):
    m, _ = sehim_sonucu()
    tutulu = {(bc.node, bc.dof) for bc in m.bcs}
    assert {(n, d) for n in x0_dugumleri(m) for d in ("ux", "uy", "uz")} == tutulu


def test_parca_sabit_hic_dugum_secmiyor(gmsh):
    bos = [mesh.on_plane((-50.0, 0, 0), (1, 0, 0))]
    with pytest.raises(ModelError):
        parca_modal(kutu(), 5.0, celik(), bos, n_modes=3)
    with pytest.raises(ModelError):
        parca_sehimi(kutu(), 5.0, celik(), bos, nokta=(L, B / 2, H / 2), F=(0, 0, -P), yaricap=3.0)
