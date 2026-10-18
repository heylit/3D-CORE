"""
Sınır koşulları ve tutarlı düğüm yükleri: mesnet, yüzey çekmesi, basınç.

Teori: specs/12-gmsh.md
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from core.model import Model


def fix(
    model: Model,
    node_ids: Iterable[int],
    dofs: Sequence[str] = ("ux", "uy", "uz"),
    value: float = 0.0,
) -> None:
    """Her (düğüm, dof) için BC ekler; aynı değerle tutuluysa atlar, farklı değer -> ModelError."""
    raise NotImplementedError("SPEC 12: fix")


def add_traction(model: Model, tris: np.ndarray, t: Sequence[float]) -> None:
    """Yüzey çekmesi t (3,) [MPa]: her köşeye t A / 3, (düğüm, dof) başına tek Load."""
    raise NotImplementedError("SPEC 12: add_traction")


def add_pressure(model: Model, tris: np.ndarray, p: float) -> None:
    """Basınç p [MPa] (pozitif: cisme bastırır): her köşeye −p n A / 3, (düğüm, dof) başına tek Load."""
    raise NotImplementedError("SPEC 12: add_pressure")
