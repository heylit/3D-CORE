"""
SPEC 53 — Simülasyon ölçüt programları (B1 2.5D kaba, B2 3D ince) ve süre ölçümü.

Kullanım:  python scripts/bench_sim.py [--cell 0.1] [--only B1|B2] [--old]
Süre: simulate(...) çağrısının duvar saati, aynı süreçte ikinci çalıştırma (ısınma hariç).
--old: block=None, merge=False (eski yol, başlangıç çizgisi).
"""

from __future__ import annotations

import argparse
import math
import time

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import Stock, Tool, ToolKind, Toolpath
from cam.ops2d import Cut, face
from cam.ops3d import Raster, finish
from cam.sim import simulate

STOCK = Stock(0.0, 0.0, 0.0, 200.0, 200.0, 40.0)


def b1() -> list[Toolpath]:
    """B1: D = 16 düz takım, zigzag tüm alan, ae = 8, ap = 5, 8 paso."""
    tool = Tool(1, "D16", ToolKind.FLAT, D=16.0, flute_length=45.0)
    cut = Cut(
        z_top=40.0, z_bottom=0.0, a_p=5.0, feed=1200.0, plunge_feed=300.0, rpm=8000.0, z_safe=50.0,
        stepover=8.0,
    )  # fmt: skip
    return [face(STOCK, tool, cut)]


def surface(x, y):
    """B2 yüzeyi z = 30 + 5·sin(2πx/80)·cos(2πy/60)"""
    return 30.0 + 5.0 * np.sin(2 * math.pi * x / 80.0) * np.cos(2 * math.pi * y / 60.0)


def surface_mesh(h: float = 1.0) -> TriMesh:
    """Yüzey ağı; h = 1 mm'de kiriş sapması ≤ κ_max·h²/8 ≈ 0.007 mm (< 0.01)."""
    n = round(200.0 / h)
    t = np.linspace(0.0, 200.0, n + 1)
    X, Y = np.meshgrid(t, t)
    V = np.column_stack([X.ravel(), Y.ravel(), surface(X, Y).ravel()])
    i = np.arange(n)
    a = (i[None, :] + (n + 1) * i[:, None]).ravel()
    b, c, d = a + 1, a + n + 1, a + n + 2
    T = np.vstack([np.column_stack([a, b, d]), np.column_stack([a, d, c])])
    return TriMesh(V=V, T=T)


def b2() -> list[Toolpath]:
    """B2: R = 5 küresel uç, raster yan adım 0.5 mm, uyarlamalı nokta aralığı (tol = 0.005)."""
    tool = Tool(2, "R5", ToolKind.BALL, D=10.0, flute_length=30.0, corner_r=5.0)
    r = Raster(
        xmin=0.0, xmax=200.0, ymin=0.0, ymax=200.0, stepover=0.5, ds=2.0, tol=0.005, ds_min=0.05,
        feed=2000.0, plunge_feed=500.0, rpm=12000.0, z_safe=50.0,
    )  # fmt: skip
    return [finish(surface_mesh(), tool, r)]


def measure(ops, cell: float, old: bool) -> tuple[float, int]:
    kw = {"block": None, "merge": False} if old else {}
    simulate(ops, STOCK, cell=cell, **kw)  # ısınma
    t0 = time.perf_counter()
    simulate(ops, STOCK, cell=cell, **kw)
    return time.perf_counter() - t0, sum(len(op.moves) for op in ops)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--cell", type=float, default=0.1)
    ap.add_argument("--only", choices=("B1", "B2"))
    ap.add_argument("--old", action="store_true")
    a = ap.parse_args()
    for ad, f in (("B1", b1), ("B2", b2)):
        if a.only and a.only != ad:
            continue
        ops = f()
        sure, n = measure(ops, a.cell, a.old)
        print(f"{ad}: {n} hareket, hücre {a.cell} mm, {'eski' if a.old else 'yeni'} yol: {sure:.2f} s")


if __name__ == "__main__":
    main()
