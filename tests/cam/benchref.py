"""SPEC 53 ölçüt programları B1 ve B2 (testte üretilir; uydurma geometri, SPEC 53 "Ölçüt programları").

- B1 — 2.5D kaba: stok 200 × 200 × 40, D = 16 düz takım, tüm alanda zigzag (SPEC 03 yüz alma), ae = 8, ap =
  5, 8 paso.
- B2 — 3D ince: z = 30 + 5·sin(2πx/80)·cos(2πy/60) yüzeyi (SPEC 06 ağı), R = 5 küresel uç, SPEC 06 raster,
  yan adım 0.5, uyarlamalı nokta aralığı (tol = 0.005).
Ağ aralığı h: kiriş hatası h²·κ/8 ≤ 0.01 mm, κ_max ≈ 5·((2π/80)² + (2π/60)²) ≈ 0.086 → h ≤ 0.96; h = 0.8
alınır.
"""

from __future__ import annotations

import functools
import math

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import Stock, Toolpath
from cam.ops2d import Cut, face
from cam.ops3d import Raster, finish
from tests.cam.ref3d import grid_mesh
from tests.cam.simref import ball, flat

STOK = Stock(0.0, 0.0, 0.0, 200.0, 200.0, 40.0)


def yuzey(x, y):
    return 30.0 + 5.0 * np.sin(2 * math.pi * x / 80.0) * np.cos(2 * math.pi * y / 60.0)


@functools.cache
def b1() -> Toolpath:
    cut = Cut(
        z_top=40.0,
        z_bottom=0.0,
        a_p=5.0,
        feed=1200.0,
        plunge_feed=300.0,
        rpm=8000.0,
        z_safe=45.0,
        stepover=8.0,
    )
    return face(STOK, flat(D=16.0, Lf=50.0), cut)


@functools.cache
def b2(stepover: float = 0.5) -> Toolpath:
    xs = np.linspace(-10.0, 210.0, 276)  # h = 0.8
    V, T = grid_mesh(yuzey, xs, xs)
    r = Raster(
        xmin=0.0,
        xmax=200.0,
        ymin=0.0,
        ymax=200.0,
        stepover=stepover,
        ds=2.0,
        tol=0.005,
        ds_min=0.05,
        feed=2000.0,
        plunge_feed=500.0,
        rpm=12000.0,
        z_safe=45.0,
    )
    return finish(TriMesh(V, T), ball(D=10.0, Lf=40.0), r)
