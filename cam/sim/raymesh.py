"""
SPEC 43 — Parça dexel'i: kapalı üçgen ağı ile ışın kesişimi (Möller–Trumbore).

Işın o + s·d, üçgen P0 + u·e1 + v·e2 (e1 = P1 − P0, e2 = P2 − P0):
    p = d × e2, det = e1·p, q = (o − P0) × e1, u = (o − P0)·p / det, v = d·q / det, s = e2·q / det
İsabet: u ≥ 0, v ≥ 0, u + v ≤ 1. Kesişimler sıralanır, çiftler halinde parça içi aralıkları verir.
Tek sayıda kesişim ya da kenar / köşe isabeti → ışın 1e-9·Δ kaydırılıp yeniden denenir; yine tekse CamError.
"""

from __future__ import annotations

import math

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import CamError

_KENAR = 1e-13  # barisentrik koordinat bu kadar sıfıra yakınsa kenar / köşe isabeti
_KAYMA_ACI = 0.6180339887  # kaydırma yönü (kenarlarla hizalanmasın diye irrasyonel açı)
_BLOK = 400_000  # ışın × üçgen blok boyu


def _triangles(mesh: TriMesh) -> np.ndarray:
    if not isinstance(mesh, TriMesh):
        raise CamError(f"Parça ağı TriMesh olmalı ({type(mesh).__name__})")
    return np.asarray(mesh.V, dtype=float)[np.asarray(mesh.T)]


def _mt(P: np.ndarray, Ob: np.ndarray, d: np.ndarray):
    """Işınlar (n, 3) × üçgenler (m, 3, 3): (isabet, kenar isabeti, s), her biri (n, m)."""
    e1 = P[:, 1] - P[:, 0]
    e2 = P[:, 2] - P[:, 0]
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    olcek = np.linalg.norm(e1, axis=1) * np.linalg.norm(e2, axis=1) * float(np.linalg.norm(d))
    gecerli = np.abs(det) > 1e-12 * olcek
    inv = np.where(gecerli, 1.0 / np.where(gecerli, det, 1.0), 0.0)
    tv = Ob[:, None, :] - P[None, :, 0]  # (n, m, 3)
    u = np.einsum("nmk,mk->nm", tv, p) * inv
    q = np.cross(tv, e1[None, :, :])
    v = np.einsum("k,nmk->nm", d, q) * inv
    s = np.einsum("mk,nmk->nm", e2, q) * inv
    w = 1.0 - u - v
    lmin = np.minimum(np.minimum(u, v), w)
    isabet = gecerli & (lmin >= -_KENAR)
    kenar = isabet & (lmin <= _KENAR)
    return isabet, kenar, s


def _pairs(isabet: np.ndarray, s: np.ndarray):
    """Satır başına sıralı isabetlerden çiftler: (lo, hi, tek mi)."""
    S = np.sort(np.where(isabet, s, np.inf), axis=1)
    say = isabet.sum(axis=1)
    K = int(say.max()) if say.size else 0
    K += K % 2
    S = S[:, :K] if K else np.zeros((S.shape[0], 0))
    lo, hi = S[:, 0::2], S[:, 1::2]
    bos = ~np.isfinite(hi) | ~(hi > lo)
    return np.where(bos, np.inf, lo), np.where(bos, -np.inf, hi), say % 2 == 1


def _perp(d: np.ndarray) -> np.ndarray:
    """d'ye dik, kenarlarla hizalanmayan birim yön."""
    e = np.eye(3)[int(np.argmin(np.abs(d)))]
    b1 = np.cross(d, e)
    b1 /= np.linalg.norm(b1)
    b2 = np.cross(d / np.linalg.norm(d), b1)
    return math.cos(_KAYMA_ACI) * b1 + math.sin(_KAYMA_ACI) * b2


def _one(P: np.ndarray, o: np.ndarray, d: np.ndarray, kayma: float) -> list[tuple[float, float]]:
    for deneme in range(2):
        oo = o + (kayma * deneme) * _perp(d)
        isabet, kenar, s = _mt(P, oo[None, :], d)
        lo, hi, tek = _pairs(isabet, s)
        if not tek[0] and (deneme == 1 or not kenar.any()):
            return [(float(a), float(b)) for a, b in zip(lo[0], hi[0], strict=True) if b > a]
    raise CamError("Parça ağı kapalı değil: ışın tek sayıda yüzey kesiyor")


def _kayma(P: np.ndarray, cell: float | None) -> float:
    if cell is None:
        cell = float(np.linalg.norm(P.reshape(-1, 3).max(axis=0) - P.reshape(-1, 3).min(axis=0)))
    return 1e-9 * cell


def part_intervals(mesh: TriMesh, origin, direction, cell: float | None = None) -> list[tuple[float, float]]:
    """Işın origin + s·direction üzerinde parça içi aralıklar [(s_giriş, s_çıkış), ...], sıralı.

    cell: kaydırma ölçeği Δ (yoksa ağın sınır kutusu köşegeni).
    """
    P = _triangles(mesh)
    o = np.asarray(origin, dtype=float)
    d = np.asarray(direction, dtype=float)
    if o.shape != (3,) or d.shape != (3,) or not (np.all(np.isfinite(o)) and np.all(np.isfinite(d))):
        raise CamError("part_intervals: origin ve direction 3 bileşenli sonlu vektör olmalı")
    if not np.linalg.norm(d) > 0:
        raise CamError("part_intervals: ışın yönü sıfır olamaz")
    return _one(P, o, d, _kayma(P, cell))


def family_part(mesh: TriMesh, Ob: np.ndarray, d: np.ndarray, cell: float) -> tuple[np.ndarray, np.ndarray]:
    """Işın ailesinin parça aralıkları: Ob (n, 3) başlangıçlar, d ortak yön → (lo, hi) (n, K), boş ±inf."""
    P = _triangles(mesh)
    kayma = _kayma(P, cell)
    n = Ob.shape[0]
    blok = max(1, _BLOK // max(1, len(P)))
    los, his = [], []
    for b in range(0, n, blok):
        isabet, kenar, s = _mt(P, Ob[b : b + blok], d)
        lo, hi, tek = _pairs(isabet, s)
        sorunlu = np.nonzero(tek | kenar.any(axis=1))[0]
        if sorunlu.size:
            satir = [_one(P, Ob[b + i], d, kayma) for i in sorunlu]
            K = max([lo.shape[1]] + [len(r) for r in satir])
            lo = np.pad(lo, ((0, 0), (0, K - lo.shape[1])), constant_values=np.inf)
            hi = np.pad(hi, ((0, 0), (0, K - hi.shape[1])), constant_values=-np.inf)
            for i, r in zip(sorunlu, satir, strict=True):
                lo[i] = np.inf
                hi[i] = -np.inf
                for k, (a_, b_) in enumerate(r):
                    lo[i, k], hi[i, k] = a_, b_
        los.append(lo)
        his.append(hi)
    K = max(1, max(x.shape[1] for x in los))
    lo = np.concatenate([np.pad(x, ((0, 0), (0, K - x.shape[1])), constant_values=np.inf) for x in los])
    hi = np.concatenate([np.pad(x, ((0, 0), (0, K - x.shape[1])), constant_values=-np.inf) for x in his])
    return lo, hi
