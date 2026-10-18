"""
Parçadan modal analiz ve kesme sehimi: Part → mesh.tet_mesh → core (SPEC 45). gmsh + OCCT gerektirir.

Teori: specs/45-modal.md
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from analiz.sehim import Sehim
from core.modal import ModalResult
from core.model import Material, Model

Tahmin = Callable[[np.ndarray], np.ndarray]


def parca_modal(
    part,
    h: float,
    material: Material,
    sabit: Sequence[Tahmin],
    n_modes: int,
    *,
    lumped: bool = False,
) -> tuple[Model, ModalResult]:
    """Parçayı ağlar, sabit tahminlerinin seçtiği düğümleri tutar, modal analizi çözer."""
    raise NotImplementedError("SPEC 45: parca_modal")


def parca_sehimi(
    part,
    h: float,
    material: Material,
    sabit: Sequence[Tahmin],
    nokta: Sequence[float],
    F: Sequence[float],
    yaricap: float,
) -> tuple[Model, Sehim]:
    """Parçayı ağlar, sabit yüzleri tutar, temas noktasında kesme sehimini hesaplar."""
    raise NotImplementedError("SPEC 45: parca_sehimi")
