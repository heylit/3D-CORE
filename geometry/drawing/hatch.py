"""Tarama (SPEC 16): paralel doğruların bölgeyle kesişimi. Saf numpy.

Doğru ailesi: n·p = (k + ½)·s, n = (−sin θ, cos θ), k tam sayı. Her doğru için bölgenin tüm kenarlarıyla
kesişim parametreleri (doğru yönü d = (cos θ, sin θ) boyunca) sıralanır ve çift-tek kuralıyla içteki
aralıklar alınır (tarama satırı; Foley vd., Computer Graphics, 3.6). Köşelerde çift sayımı önlemek için
kenar [h_a, h_b) yarı açık kabul edilir.
"""

from __future__ import annotations

import math

import numpy as np

from geometry.drawing.types import Line2D
from geometry.part import GeometryError, Region


def _kenarlar(regions: list[Region]) -> tuple[np.ndarray, np.ndarray]:
    """Tüm kapalı sınırların kenarları: başlangıç A (m, 2), bitiş B (m, 2)."""
    A, B = [], []
    for reg in regions:
        for P in (reg.outer, *reg.holes):
            P = np.asarray(P, dtype=float)
            if P.ndim != 2 or P.shape[1] != 2 or len(P) < 3 or not np.isfinite(P).all():
                raise GeometryError("tarama: her sınır en az üç sonlu (x, y) noktası olmalı")
            A.append(P)
            B.append(np.roll(P, -1, axis=0))
    return np.vstack(A), np.vstack(B)


def hatch(regions: list[Region], s: float = 3.0, theta: float = 45.0) -> list[Line2D]:
    """n·p = (k + ½)·s doğrularının bölgelerle kesişimi, TARAMA katmanı."""
    if not (math.isfinite(s) and s > 0):
        raise GeometryError(f"tarama aralığı s > 0 olmalı (s={s})")
    if not math.isfinite(theta):
        raise GeometryError(f"tarama açısı sonlu olmalı (theta={theta})")
    if not regions:
        raise GeometryError("tarama: bölge yok")
    A, B = _kenarlar(regions)
    th = math.radians(theta)
    d = np.array([math.cos(th), math.sin(th)])
    n = np.array([-math.sin(th), math.cos(th)])
    hA, hB = A @ n, B @ n
    tA, tB = A @ d, B @ d
    hmin, hmax = float(min(hA.min(), hB.min())), float(max(hA.max(), hB.max()))
    k0 = math.ceil(hmin / s - 0.5)
    k1 = math.floor(hmax / s - 0.5)
    out: list[Line2D] = []
    for k in range(k0, k1 + 1):
        h = (k + 0.5) * s
        kes = ((hA <= h) & (h < hB)) | ((hB <= h) & (h < hA))
        if not kes.any():
            continue
        w = (h - hA[kes]) / (hB[kes] - hA[kes])
        t = np.sort(tA[kes] + w * (tB[kes] - tA[kes]))
        for t0, t1 in zip(t[0::2], t[1::2], strict=False):
            if t1 - t0 > 1e-12:
                out.append(Line2D(h * n + t0 * d, h * n + t1 * d, "TARAMA"))
    return out
