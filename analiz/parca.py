"""
Parçadan modal analiz ve kesme sehimi: Part → mesh.tet_mesh → core (SPEC 45). gmsh + OCCT gerektirir.

Teori: specs/45-modal.md
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

import mesh
from analiz.sehim import Sehim, kesme_sehimi
from core.modal import ModalResult, modal
from core.model import Material, Model, ModelError

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
    m = _agla_ve_sabitle(part, h, material, sabit)
    return m, modal(m, n_modes, lumped=lumped)


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
    m = _agla_ve_sabitle(part, h, material, sabit)
    return m, kesme_sehimi(m, nokta, F, yaricap)


def _agla_ve_sabitle(part, h: float, material: Material, sabit: Sequence[Tahmin]) -> Model:
    """mesh.tet_mesh ile ağlar; sabit tahminlerinin seçtiği düğümlerin üç DOF'unu tutar."""
    m = mesh.tet_mesh(part, h, material)
    secilen: set[int] = set()
    for pred in sabit:
        secilen.update(mesh.select_nodes(m, pred))
    if not secilen:
        raise ModelError("sabit tahminleri hiçbir düğüm seçmedi (mesnetsiz parça: core.modal.modal kullanın)")
    mesh.fix(m, sorted(secilen))
    return m
