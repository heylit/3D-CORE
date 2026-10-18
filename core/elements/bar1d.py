"""
1D çubuk elemanı (2 düğüm, düğüm başına 1 DOF: ux).

Uygulanacak: specs/01-bar.md
"""

from __future__ import annotations

import numpy as np

from core.model import Element, Model


def length(element: Element, model: Model) -> float:
    """Eleman boyu L = |x2 - x1| [mm]. L <= 0 ise ModelError."""
    raise NotImplementedError("specs/01-bar.md uygulanacak")


def ke(element: Element, model: Model) -> np.ndarray:
    """k = (E*A/L) * [[1, -1], [-1, 1]]"""
    raise NotImplementedError("specs/01-bar.md uygulanacak")


def dofs(element: Element, model: Model) -> list[int]:
    raise NotImplementedError("specs/01-bar.md uygulanacak")


def axial_force(element: Element, model: Model, u: np.ndarray) -> float:
    """N = (E*A/L) * (u2 - u1)  [N], pozitif = çekme"""
    raise NotImplementedError("specs/01-bar.md uygulanacak")
