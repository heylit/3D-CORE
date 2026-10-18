"""
SPEC 05 — CAD parçasının z-haritası: her hücre merkezinden geçen düşey doğrunun parçayı kestiği en yüksek Z.

Üçgen ağı (Part.mesh) hücre merkezlerinde barisentrik koordinatla örneklenir: merkez q üçgenin XY
izdüşümündeyse z = λ1·z1 + λ2·z2 + λ3·z3, hücre başına en büyük alınır. Düşey üçgenler (izdüşüm alanı 0) katkı
vermez; doğru parçaya değmiyorsa −∞.
"""

from __future__ import annotations

import numpy as np

from cam.model import CamError
from cam.sim.zmap import ZMap

_BARY_TOL = 1e-12  # ortak kenar / köşe üstündeki merkezler iki üçgende de kapsansın


def mesh_zmap(V: np.ndarray, T: np.ndarray, grid: ZMap) -> np.ndarray:
    """Üçgen ağından (köşeler V (n, 3), üçgenler T (m, 3)) parça z-haritası (ny, nx); değmeyen hücre −inf."""
    V = np.asarray(V, dtype=float)
    T = np.asarray(T)
    if V.ndim != 2 or V.shape[1] != 3 or T.ndim != 2 or T.shape[1] != 3:
        raise CamError(f"Parça ağı: V (n, 3) ve T (m, 3) olmalı ({V.shape}, {T.shape})")
    if not np.all(np.isfinite(V)):
        raise CamError("Parça ağı: köşeler sonlu olmalı")
    if T.size and (T.min() < 0 or T.max() >= len(V)):
        raise CamError("Parça ağı: üçgen indeksi köşe sayısını aşıyor")
    zP = np.full((grid.ny, grid.nx), -np.inf)
    xs = grid.xs()
    ys = grid.ys()
    for tri in T:
        A, B, C = V[tri[0]], V[tri[1]], V[tri[2]]
        det = (B[0] - A[0]) * (C[1] - A[1]) - (C[0] - A[0]) * (B[1] - A[1])
        if abs(det) < 1e-15:
            continue  # düşey üçgen
        lo = np.minimum(np.minimum(A, B), C)
        hi = np.maximum(np.maximum(A, B), C)
        w = grid.window(lo[0], hi[0], lo[1], hi[1])
        if w is None:
            continue
        js, is_ = w
        X, Y = np.meshgrid(xs[is_], ys[js])
        l2 = ((X - A[0]) * (C[1] - A[1]) - (C[0] - A[0]) * (Y - A[1])) / det
        l3 = ((B[0] - A[0]) * (Y - A[1]) - (X - A[0]) * (B[1] - A[1])) / det
        l1 = 1.0 - l2 - l3
        inside = (l1 >= -_BARY_TOL) & (l2 >= -_BARY_TOL) & (l3 >= -_BARY_TOL)
        z = l1 * A[2] + l2 * B[2] + l3 * C[2]
        sub = zP[js, is_]
        zP[js, is_] = np.where(inside, np.maximum(sub, z), sub)
    return zP


def part_zmap(part, grid: ZMap, tol: float = 0.01) -> np.ndarray:
    """geometry.part.Part için: part.mesh(tol) ağından mesh_zmap."""
    V, T = part.mesh(tol)
    return mesh_zmap(V, T, grid)
