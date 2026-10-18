"""
Parçadan kararlı hal ısıl analizi: Part → mesh.tet_mesh → core.isil (SPEC 56). gmsh + OCCT gerektirir.

Teori: specs/56-isil-analiz.md
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from core.isil import ThermalResult
from core.model import Model

Tahmin = Callable[[np.ndarray], np.ndarray]


def parca_isil(
    part,
    h_ag: float,
    malzeme,
    *,
    sabit: Sequence[tuple[Tahmin, float]] = (),
    aki: Sequence[tuple[Tahmin, float]] = (),
    tasinim: Sequence[tuple[Tahmin, float, float]] = (),
    Q: float = 0.0,
) -> tuple[Model, ThermalResult]:
    """Parçayı ağlar, yüz seçicilerini uygular, ısıl çözümü döndürür. k = malzeme.iste("k")."""
    raise NotImplementedError("SPEC 56: parca_isil")
