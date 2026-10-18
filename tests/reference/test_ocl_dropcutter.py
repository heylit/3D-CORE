"""SPEC 06 K18 — drop-cutter ↔ OpenCAMLib BatchDropCutter (isteğe bağlı çapraz kontrol).

OpenCAMLib (`ocl`, pip paketi `opencamlib`) kurulu değilse atlanır; proje bağımlılığı değildir
(karar: CAM algoritmaları bizim, OpenCAMLib yalnızca test referansı). Aynı ağ ve takımda iki
uygulamanın CL yüksekliği 1e-6 mm içinde aynı olmalı. OpenCAMLib'de CL de takım ucudur.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from cam.dropcutter import TriMesh, drop
from cam.model import Tool, ToolKind
from tests.cam.ref3d import grid_mesh


def _ocl():
    """`ocl` modülü (eski dağıtım) veya `opencamlib` paketi; ikisi de yoksa test atlanır."""
    if importlib.util.find_spec("ocl") is not None:
        import ocl

        return ocl
    mod = pytest.importorskip("opencamlib")
    return getattr(mod, "ocl", mod)


def _ocl_drop(ocl, V, T, cutter, xy, z_min):
    s = ocl.STLSurf()
    for a, b, c in T:
        s.addTriangle(ocl.Triangle(ocl.Point(*V[a]), ocl.Point(*V[b]), ocl.Point(*V[c])))
    bdc = ocl.BatchDropCutter()
    bdc.setSTL(s)
    bdc.setCutter(cutter)
    for x, y in xy:
        bdc.appendPoint(ocl.CLPoint(float(x), float(y), z_min))
    bdc.run()
    return np.array([p.z for p in bdc.getCLPoints()])


@pytest.mark.parametrize("kind", [ToolKind.BALL, ToolKind.FLAT], ids=["kuresel", "duz"])
def test_k18_ocl_batchdropcutter(kind):
    ocl = _ocl()
    xs = np.arange(-10.0, 10.25, 0.5)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Z = 2.0 * np.sin(X / 4) * np.cos(Y / 4) + 0.05 * np.random.default_rng(9).standard_normal(X.shape)
    V, T = grid_mesh(Z, xs, xs)
    D = 6.0
    tool = Tool(id=1, name="t", kind=kind, D=D, flute_length=30.0)
    cutter = ocl.BallCutter(D, 30.0) if kind is ToolKind.BALL else ocl.CylCutter(D, 30.0)
    xy = np.random.default_rng(10).uniform(-5, 5, (60, 2))
    z_ref = _ocl_drop(ocl, V, T, cutter, xy, float(Z.min()) - 50.0)
    z = drop(TriMesh(V=V, T=T), tool, xy)
    np.testing.assert_allclose(z, z_ref, atol=1e-6, rtol=0)


def test_k19_ocl_bullcutter_torik():
    """SPEC 06b K19: torik uç ↔ OpenCAMLib BullCutter (köşe radyüslü), 1e-6 mm."""
    ocl = _ocl()
    xs = np.arange(-10.0, 10.25, 0.5)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Z = 2.0 * np.sin(X / 4) * np.cos(Y / 4) + 0.05 * np.random.default_rng(19).standard_normal(X.shape)
    V, T = grid_mesh(Z, xs, xs)
    D, r_c = 8.0, 1.5
    tool = Tool(id=1, name="t", kind=ToolKind.FLAT, D=D, flute_length=30.0, corner_r=r_c)
    xy = np.random.default_rng(20).uniform(-5, 5, (60, 2))
    z_ref = _ocl_drop(ocl, V, T, ocl.BullCutter(D, r_c, 30.0), xy, float(Z.min()) - 50.0)
    z = drop(TriMesh(V=V, T=T), tool, xy)
    np.testing.assert_allclose(z, z_ref, atol=1e-6, rtol=0)
