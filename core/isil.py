"""
Kararlı hal ısı iletimi, tet4 ağı üzerinde (SPEC 56).

−∇·(k ∇T) = Q; sabit sıcaklık (Dirichlet), ısı akısı (Neumann), taşınım (Robin) ve hacimsel üretim.
Birimler: N – mm – s; güç mW, k mW/(mm·K), q mW/mm², h mW/(mm²·K), Q mW/mm³.
`model.bcs` ve `model.loads` okunmaz: ısıl koşullar bu dosyadaki kayıtlardır.

Teori: specs/56-isil-analiz.md (Incropera bölüm 3; Zienkiewicz–Taylor cilt 1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp

from core.model import Model


@dataclass(frozen=True)
class Temperature:
    """Sabit sıcaklık: düğüm id, T [°C]."""

    node: int
    T: float


@dataclass(frozen=True)
class HeatFlux:
    """Γ_q: üçgenler (k, 3) düğüm id'leri, q [mW/mm²], parçaya giren pozitif."""

    tris: np.ndarray
    q: float


@dataclass(frozen=True)
class Convection:
    """Γ_h: üçgenler (k, 3), film katsayısı h [mW/(mm²·K)] > 0, ortam sıcaklığı T_inf [°C]."""

    tris: np.ndarray
    h: float
    T_inf: float


@dataclass(frozen=True)
class ThermalResult:
    node_ids: np.ndarray  # (n,) model.nodes sırası
    T: np.ndarray  # (n,) °C
    R: np.ndarray  # (n,) mW, tepki ısısı; sabit sıcaklıklı olmayan düğümde 0
    Q_gen: float  # mW, toplam üretim
    Q_flux: float  # mW, Γ_q'dan giren toplam
    Q_conv: float  # mW, Γ_h'den giren toplam (soğutmada negatif)

    def temperature(self, node_id: int) -> float:
        """Düğüm sıcaklığı [°C]. Bilinmeyen düğüm → ModelError."""
        raise NotImplementedError("SPEC 56: ThermalResult.temperature")


def conductivity_matrix(model: Model, k: float | Mapping[str, float]) -> sp.csr_matrix:
    """Global iletkenlik matrisi Σ ke (taşınım hariç), (n x n)."""
    raise NotImplementedError("SPEC 56: conductivity_matrix")


def solve_thermal(
    model: Model,
    k: float | Mapping[str, float],
    *,
    temperatures: Sequence[Temperature] = (),
    fluxes: Sequence[HeatFlux] = (),
    convection: Sequence[Convection] = (),
    Q: float | Mapping[str, float] = 0.0,
) -> ThermalResult:
    """K T = F'yi çözer. `model.bcs` ve `model.loads` okunmaz. Hatalar → ModelError."""
    raise NotImplementedError("SPEC 56: solve_thermal")


def heat_flux(model: Model, k: float | Mapping[str, float], result: ThermalResult) -> np.ndarray:
    """Eleman ısı akısı q_e = −k B T_e, (m, 3) mW/mm², eleman sırası."""
    raise NotImplementedError("SPEC 56: heat_flux")


def nodal_heat_flux(model: Model, k: float | Mapping[str, float], result: ThermalResult) -> np.ndarray:
    """Düğüm ısı akısı, (n, 3) mW/mm², hacim ağırlıklı ortalama."""
    raise NotImplementedError("SPEC 56: nodal_heat_flux")
