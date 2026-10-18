"""
Post-process: eleman iç kuvvetleri ve gerilmeleri.

Uygulanacak: specs/01-bar.md
"""

from __future__ import annotations

import numpy as np

from core.model import Model


def element_forces(model: Model, u: np.ndarray) -> dict[int, float]:
    """eleman id -> eksenel kuvvet [N]"""
    raise NotImplementedError("specs/01-bar.md uygulanacak")


def element_stresses(model: Model, u: np.ndarray) -> dict[int, float]:
    """eleman id -> eksenel gerilme sigma = N / A [MPa]"""
    raise NotImplementedError("specs/01-bar.md uygulanacak")
