"""
Tet4 ağının sınır yüzeyi ve geometrik seçim (gmsh / OCCT gerektirmez).

Teori: specs/12-gmsh.md
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np

from core.model import Model, ModelError

Tahmin = Callable[[np.ndarray], np.ndarray]  # (n, 3) noktalar -> (n,) bool

# Pozitif yönlü tet (a, b, c, d) için dışa bakan yüzler: (a, c, b), (a, b, d), (a, d, c), (b, c, d)
DIS_YUZLER = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])


def _koordinatlar(model: Model) -> tuple[np.ndarray, np.ndarray]:
    """Düğüm id'leri (n,) ve koordinatları (n, 3), model.nodes sırasında."""
    ids = np.array([n.id for n in model.nodes], dtype=np.int64)
    X = np.array([[n.x, n.y, n.z] for n in model.nodes], dtype=float).reshape(-1, 3)
    return ids, X


def _xyz(model: Model, dugumler: np.ndarray) -> np.ndarray:
    """Düğüm id dizisi (herhangi bir şekil) -> koordinatlar (..., 3). Bilinmeyen düğüm -> ModelError."""
    dugumler = np.asarray(dugumler, dtype=np.int64)
    satir = np.array([model.node_index(int(i)) for i in dugumler.ravel()], dtype=np.int64)
    _, X = _koordinatlar(model)
    return X[satir].reshape(*dugumler.shape, 3)


def _ucgenler(tris) -> np.ndarray:
    T = np.asarray(tris, dtype=np.int64)
    if T.size == 0:
        return T.reshape(0, 3)
    if T.ndim != 2 or T.shape[1] != 3:
        raise ModelError(f"Üçgen dizisi (k, 3) olmalı (şekil {T.shape})")
    return T


def boundary_triangles(model: Model) -> np.ndarray:
    """Sınır üçgenleri (m, 3), düğüm id'leri, dışa bakan sırada."""
    if not model.elements:
        return np.zeros((0, 3), dtype=np.int64)
    E = np.array([e.nodes for e in model.elements], dtype=np.int64)
    if E.ndim != 2 or E.shape[1] != 4:
        raise ModelError("boundary_triangles sadece dört düğümlü (tet4) elemanlarla çalışır")
    P = _xyz(model, E)
    det = np.einsum("ij,ij->i", P[:, 1] - P[:, 0], np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 0]))
    sol = det < 0
    E = E.copy()
    E[sol, 1], E[sol, 2] = E[sol, 2].copy(), E[sol, 1].copy()  # sol el -> sağ el, dış normal korunur

    F = E[:, DIS_YUZLER].reshape(-1, 3)  # eleman ve yüz sırasıyla
    anahtar = np.sort(F, axis=1)
    _, ters, sayi = np.unique(anahtar, axis=0, return_inverse=True, return_counts=True)
    tek = sayi[ters.ravel()] == 1
    return F[tek]


def _birim(v, ad: str) -> np.ndarray:
    v = np.asarray(v, dtype=float).ravel()
    if v.shape != (3,) or not np.all(np.isfinite(v)):
        raise ModelError(f"{ad} üç sonlu bileşenli vektör olmalı ({v})")
    n = np.linalg.norm(v)
    if n == 0.0:
        raise ModelError(f"{ad} sıfır vektör olamaz")
    return v / n


def _nokta(p, ad: str) -> np.ndarray:
    p = np.asarray(p, dtype=float).ravel()
    if p.shape != (3,) or not np.all(np.isfinite(p)):
        raise ModelError(f"{ad} üç sonlu bileşenli nokta olmalı ({p})")
    return p


def _tol(tol) -> float:
    tol = float(tol)
    if not math.isfinite(tol) or tol <= 0:
        raise ModelError(f"tol pozitif ve sonlu olmalı (tol={tol})")
    return tol


def on_plane(point: Sequence[float], normal: Sequence[float], tol: float = 1e-6) -> Tahmin:
    """|(x − point) · n̂| ≤ tol olan noktalar."""
    p0, n, tol = _nokta(point, "Düzlem noktası"), _birim(normal, "Düzlem normali"), _tol(tol)

    def tahmin(X: np.ndarray) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, dtype=float))
        return np.abs((X - p0) @ n) <= tol

    return tahmin


def on_cylinder(point: Sequence[float], axis: Sequence[float], radius: float, tol: float = 1e-6) -> Tahmin:
    """Eksenden uzaklığı radius'a tol içinde eşit olan noktalar."""
    p0, a, tol = _nokta(point, "Eksen noktası"), _birim(axis, "Silindir ekseni"), _tol(tol)
    radius = float(radius)
    if not math.isfinite(radius) or radius <= 0:
        raise ModelError(f"Silindir yarıçapı pozitif ve sonlu olmalı (radius={radius})")

    def tahmin(X: np.ndarray) -> np.ndarray:
        d = np.atleast_2d(np.asarray(X, dtype=float)) - p0
        dik = d - np.outer(d @ a, a)
        return np.abs(np.linalg.norm(dik, axis=1) - radius) <= tol

    return tahmin


def select_nodes(model: Model, pred: Tahmin) -> list[int]:
    """pred doğru olan düğüm id'leri, artan sırada."""
    ids, X = _koordinatlar(model)
    if len(ids) == 0:
        return []
    return sorted(int(i) for i in ids[np.asarray(pred(X), dtype=bool)])


def select_triangles(model: Model, pred: Tahmin) -> np.ndarray:
    """Üç köşesi de pred'i sağlayan sınır üçgenleri (k, 3)."""
    T = boundary_triangles(model)
    if len(T) == 0:
        return T
    ids, X = _koordinatlar(model)
    secili = dict(zip(ids.tolist(), np.asarray(pred(X), dtype=bool).tolist(), strict=True))
    maske = np.array([secili[a] and secili[b] and secili[c] for a, b, c in T.tolist()], dtype=bool)
    return T[maske]


def _capraz(model: Model, tris) -> np.ndarray:
    """(x_j − x_i) × (x_k − x_i), boyu 2A, yönü dış normal (k, 3)."""
    T = _ucgenler(tris)
    if len(T) == 0:
        return np.zeros((0, 3))
    P = _xyz(model, T)
    return np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])


def triangle_areas(model: Model, tris: np.ndarray) -> np.ndarray:
    """Üçgen alanları (k,) [mm²]."""
    return 0.5 * np.linalg.norm(_capraz(model, tris), axis=1)


def triangle_normals(model: Model, tris: np.ndarray) -> np.ndarray:
    """Birim normaller (k, 3), köşe sırasına göre sağ el."""
    c = _capraz(model, tris)
    boy = np.linalg.norm(c, axis=1)
    if np.any(boy == 0.0):
        raise ModelError("Sıfır alanlı üçgenin normali tanımsız")
    return c / boy[:, None]
