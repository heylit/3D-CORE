"""
SPEC 18 — Desen ve ayna dönüşümleri, delik kaydının dönüştürülmesi.

`Donusum` 4 × 4 homojen matristir (numpy). Doğrusal: p_ij = p + i·s₁·e₁ + j·s₂·e₂. Dairesel: eksen etrafında
φ_k = k · aci / n (aci = 360°), aci < 360° ise φ_k = k · aci / (n − 1). Ayna (nokta q, birim normal m):
p' = p − 2((p − q)·m) m. Listelerin ilk elemanı birim dönüşümdür (asıl). Birimler: mm, derece.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence

import numpy as np

from geometry.part import GeometryError, Hole

Donusum = np.ndarray  # (4, 4)


def _birim(v: Sequence[float], ad: str) -> np.ndarray:
    """Sonlu, sıfır olmayan (3,) vektörün birim hali; değilse GeometryError."""
    v = np.asarray(v, dtype=float)
    if v.shape != (3,) or not np.all(np.isfinite(v)):
        raise GeometryError(f"{ad}: sonlu (3,) vektör olmalı ({v})")
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        raise GeometryError(f"{ad}: sıfır vektör")
    return v / n


def _sayi(n: int, ad: str) -> int:
    if isinstance(n, bool) or int(n) != n or n < 1:
        raise GeometryError(f"{ad} ≥ 1 tam sayı olmalı ({n})")
    return int(n)


def _oteleme(t: np.ndarray) -> Donusum:
    T = np.eye(4)
    T[:3, 3] = t
    return T


def dogrusal(
    n1: int,
    s1: float,
    e1: Sequence[float],
    n2: int = 1,
    s2: float = 0.0,
    e2: Sequence[float] | None = None,
) -> list[Donusum]:
    """n1 × n2 öteleme; sıra: j dış, i iç (önce e₁ boyunca bir satır, sonra e₂ yönünde sonraki satır).

    n < 1, sıfır yön, n > 1 iken sıfır adım → `GeometryError`.
    """
    n1 = _sayi(n1, "n1")
    n2 = _sayi(n2, "n2")
    e1 = _birim(e1, "e1")
    if n1 > 1 and not (math.isfinite(s1) and s1 != 0):
        raise GeometryError(f"s1 sıfırdan farklı ve sonlu olmalı ({s1})")
    if n2 > 1:
        if e2 is None:
            raise GeometryError("n2 > 1 iken e2 gerekli")
        e2 = _birim(e2, "e2")
        if not (math.isfinite(s2) and s2 != 0):
            raise GeometryError(f"s2 sıfırdan farklı ve sonlu olmalı ({s2})")
    else:
        e2 = np.zeros(3)
    return [_oteleme(i * s1 * e1 + j * s2 * e2) for j in range(n2) for i in range(n1)]


def dairesel(eksen_p: Sequence[float], eksen_y: Sequence[float], n: int, aci: float = 360.0) -> list[Donusum]:
    """Eksen etrafında n dönme (sağ el, eksen_y yönünde). Hatalar: n < 1, sıfır eksen, aci ∉ (0, 360]."""
    n = _sayi(n, "n")
    a = _birim(eksen_y, "eksen_y")
    p = np.asarray(eksen_p, dtype=float)
    if p.shape != (3,) or not np.all(np.isfinite(p)):
        raise GeometryError(f"eksen_p: sonlu (3,) olmalı ({p})")
    if not (math.isfinite(aci) and 0 < aci <= 360):
        raise GeometryError(f"aci ∈ (0, 360] olmalı ({aci})")
    adim = aci / n if aci == 360 or n == 1 else aci / (n - 1)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    sonuc = []
    for k in range(n):
        phi = math.radians(k * adim)
        R = np.eye(3) + math.sin(phi) * K + (1 - math.cos(phi)) * (K @ K)  # Rodrigues
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = p - R @ p
        sonuc.append(T)
    return sonuc


def ayna(q: Sequence[float], m: Sequence[float]) -> Donusum:
    """q noktasından geçen, normali m olan düzleme göre yansıma. |m| = 0 → `GeometryError`."""
    m = _birim(m, "m")
    q = np.asarray(q, dtype=float)
    if q.shape != (3,) or not np.all(np.isfinite(q)):
        raise GeometryError(f"q: sonlu (3,) olmalı ({q})")
    R = np.eye(3) - 2 * np.outer(m, m)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = 2 * (q @ m) * m
    return T


def donustur_hole(hole: Hole, T: Donusum) -> Hole:
    """origin' = T(origin), axis' = R(axis) (R: T'nin dönme / yansıma kısmı); diğer alanlar aynı."""
    T = np.asarray(T, dtype=float)
    o = T[:3, :3] @ hole.origin + T[:3, 3]
    a = T[:3, :3] @ hole.axis
    return dataclasses.replace(hole, origin=o, axis=a / np.linalg.norm(a))
