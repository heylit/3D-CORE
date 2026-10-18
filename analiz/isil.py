"""
Parçadan kararlı hal ısıl analizi: Part → mesh.tet_mesh → core.isil (SPEC 56). gmsh + OCCT gerektirir.

Teori: specs/56-isil-analiz.md
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

import mesh
from core.isil import Convection, HeatFlux, Temperature, ThermalResult, solve_thermal
from core.model import Model, ModelError

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
    """Parçayı ağlar, yüz seçicilerini uygular, ısıl çözümü döndürür.

    `malzeme` B2 kaydıdır (malzeme.model.Malzeme): ağ `malzeme.fem_malzemesi()` ile kurulur,
    k = `malzeme.iste("k")` (k alanı yoksa B2 ModelError verir). Hiçbir şey bulamayan seçici → ModelError.
    """
    k = malzeme.iste("k")
    m = mesh.tet_mesh(part, h_ag, malzeme.fem_malzemesi())

    sicakliklar = []
    for pred, T in sabit:
        dugumler = mesh.select_nodes(m, pred)
        if not dugumler:
            raise ModelError("sabit sıcaklık seçicisi hiçbir düğüm seçmedi")
        sicakliklar += [Temperature(n, T) for n in dugumler]
    akilar = [HeatFlux(_ucgenler(m, pred, "akı"), q) for pred, q in aki]
    tasinimlar = [Convection(_ucgenler(m, pred, "taşınım"), h, T_inf) for pred, h, T_inf in tasinim]
    r = solve_thermal(m, k, temperatures=sicakliklar, fluxes=akilar, convection=tasinimlar, Q=Q)
    return m, r


def _ucgenler(m: Model, pred: Tahmin, ne: str) -> np.ndarray:
    """Seçicinin sınır üçgenleri (k, 3); boşsa ModelError."""
    T = mesh.select_triangles(m, pred)
    if len(T) == 0:
        raise ModelError(f"{ne} seçicisi hiçbir sınır üçgeni seçmedi")
    return T
