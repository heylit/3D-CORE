"""
Post-process: eleman iç kuvvetleri ve gerilmeleri.

Teori: specs/01-bar.md (çubuk), specs/11-tet4.md (katı eleman gerilme tensörü)
"""

from __future__ import annotations

import numpy as np

from core import elements
from core.model import Model


def element_forces(model: Model, u: np.ndarray) -> dict[int, float]:
    """eleman id -> eksenel kuvvet [N]. Sadece axial_force sağlayan (çubuk tipi) elemanlar."""
    sonuc = {}
    for e in model.elements:
        eleman = elements.get(e.type)
        if hasattr(eleman, "axial_force"):
            sonuc[e.id] = eleman.axial_force(e, model, u)
    return sonuc


def element_stresses(model: Model, u: np.ndarray) -> dict[int, float]:
    """eleman id -> eksenel gerilme sigma = N / A [MPa]. Sadece çubuk tipi elemanlar."""
    N = element_forces(model, u)
    return {e.id: N[e.id] / model.section(e.section).A for e in model.elements if e.id in N}


def element_stress_tensors(model: Model, u: np.ndarray) -> dict[int, np.ndarray]:
    """eleman id -> gerilme tensörü σ (6,) [MPa], Voigt: xx, yy, zz, xy, xz, yz (SPEC 11).

    Sadece stress sağlayan (katı) elemanlar.
    """
    sonuc = {}
    for e in model.elements:
        eleman = elements.get(e.type)
        if hasattr(eleman, "stress"):
            sonuc[e.id] = eleman.stress(e, model, u)
    return sonuc
