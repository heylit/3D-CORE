"""
Geçici ısı iletimi, tet4 ağı üzerinde (SPEC 68b).

C Ṫ + K T = F(t), θ-yöntemi (sabit Δt):
    (C/Δt + θ K) T_{n+1} = (C/Δt − (1 − θ) K) T_n + θ F_{n+1} + (1 − θ) F_n
Sınır koşulları SPEC 56'nın kayıtlarıdır (core.isil); her birine isteğe bağlı bir zaman çarpanı f(t) eklenir.
Birimler: ρ t/mm³, cp mJ/(t·K), k mW/(mm·K), zaman s, enerji mJ.

Teori: specs/68b-gecici-isil-termomekanik.md (Incropera bölüm 5; Zienkiewicz–Taylor cilt 1).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from core.isil import Convection, HeatFlux, Temperature
from core.model import Model


@dataclass(frozen=True)
class TransientResult:
    t: np.ndarray  # (s,) s, t[0] = 0
    T: np.ndarray  # (s, n) °C, model.nodes sırası
    node_ids: np.ndarray  # (n,)
    E_in: np.ndarray  # (s,) mJ, birikimli net giriş (enerji dengesi için)

    def at(self, t: float) -> np.ndarray:
        """t anındaki sıcaklık alanı (n,), kayıtlı zamanlar arası doğrusal. Aralık dışı → ModelError."""
        raise NotImplementedError("SPEC 68b: TransientResult.at")


def solve_transient(
    model: Model,
    k: float | Mapping[str, float],
    rho_cp: float | Mapping[str, float],
    *,
    T0: float | Mapping[int, float],
    t_end: float,
    dt: float,
    theta: float = 1.0,
    lumped: bool = False,
    temperatures: Sequence[Temperature] = (),
    fluxes: Sequence[HeatFlux] = (),
    convection: Sequence[Convection] = (),
    Q: float | Mapping[str, float] = 0.0,
    zaman: Mapping[int, Callable[[float], float]] | None = None,
    kaydet: Sequence[float] | None = None,
) -> TransientResult:
    """
    Geçici ısıl çözüm. `zaman`: sınır kaydı sırası (temperatures + fluxes + convection, bu sırayla)
    → çarpan f(t). rho_cp: ρ·cp, malzeme adına göre de verilebilir.
    θ ∉ [0.5, 1], dt ≤ 0, t_end < dt → ModelError.
    """
    raise NotImplementedError("SPEC 68b: solve_transient")
