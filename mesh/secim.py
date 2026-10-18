"""
Tet4 ağının sınır yüzeyi ve geometrik seçim (gmsh / OCCT gerektirmez).

Teori: specs/12-gmsh.md
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from core.model import Model

Tahmin = Callable[[np.ndarray], np.ndarray]  # (n, 3) noktalar -> (n,) bool


def boundary_triangles(model: Model) -> np.ndarray:
    """Sınır üçgenleri (m, 3), düğüm id'leri, dışa bakan sırada."""
    raise NotImplementedError("SPEC 12: boundary_triangles")


def on_plane(point: Sequence[float], normal: Sequence[float], tol: float = 1e-6) -> Tahmin:
    """|(x − point) · n̂| ≤ tol olan noktalar."""
    raise NotImplementedError("SPEC 12: on_plane")


def on_cylinder(point: Sequence[float], axis: Sequence[float], radius: float, tol: float = 1e-6) -> Tahmin:
    """Eksenden uzaklığı radius'a tol içinde eşit olan noktalar."""
    raise NotImplementedError("SPEC 12: on_cylinder")


def select_nodes(model: Model, pred: Tahmin) -> list[int]:
    """pred doğru olan düğüm id'leri, artan sırada."""
    raise NotImplementedError("SPEC 12: select_nodes")


def select_triangles(model: Model, pred: Tahmin) -> np.ndarray:
    """Üç köşesi de pred'i sağlayan sınır üçgenleri (k, 3)."""
    raise NotImplementedError("SPEC 12: select_triangles")


def triangle_areas(model: Model, tris: np.ndarray) -> np.ndarray:
    """Üçgen alanları (k,) [mm²]."""
    raise NotImplementedError("SPEC 12: triangle_areas")


def triangle_normals(model: Model, tris: np.ndarray) -> np.ndarray:
    """Birim normaller (k, 3), köşe sırasına göre sağ el."""
    raise NotImplementedError("SPEC 12: triangle_normals")
