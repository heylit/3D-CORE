"""
SPEC 02 — Üçgen ağı (görüntüleme / STL) ve STL okuma.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from geometry.part import Part


def tessellate(part: Part, tol: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    """Köşeler V (n,3) ve dışa bakan üçgenler T (m,3); ağ kapalı."""
    raise NotImplementedError


def mesh_volume(V: np.ndarray, T: np.ndarray) -> float:
    """Diverjans teoremi: V = (1/6) Σ p₁ · (p₂ × p₃)."""
    raise NotImplementedError


def read_stl(path: str | Path, name: str | None = None) -> Part:
    """STL üçgenlerini dikip kapalı katıya çevirir."""
    raise NotImplementedError
