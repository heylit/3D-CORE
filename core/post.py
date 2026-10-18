"""
Post-process: eleman iç kuvvetleri ve gerilmeleri.

Teori: specs/01-bar.md
"""

from __future__ import annotations

import numpy as np

from core import elements
from core.model import Model


def element_forces(model: Model, u: np.ndarray) -> dict[int, float]:
    """eleman id -> eksenel kuvvet [N]"""
    return {e.id: elements.get(e.type).axial_force(e, model, u) for e in model.elements}


def element_stresses(model: Model, u: np.ndarray) -> dict[int, float]:
    """eleman id -> eksenel gerilme sigma = N / A [MPa]"""
    N = element_forces(model, u)
    return {e.id: N[e.id] / model.section(e.section).A for e in model.elements}
