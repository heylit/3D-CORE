"""
Harmonik tepki (frekans tepki fonksiyonu, FRF): M ü + C u̇ + K u = F e^(iωt) altında karmaşık genlik U(ω).

İki yol:
    doğrudan:  (K − ω² M + iω C) U = F,   C = α M + β K (Rayleigh)
    modal:     U = Σ_r φ_r (φ_rᵀ F) / (ω_r² − ω² + 2 i ζ_r ω_r ω)   (+ isteğe bağlı kalıntı esneklik)
Yük model.loads'tan genlik olarak okunur (tek fazlı). Birimler N – mm – t – s; f Hz.

Teori: specs/68c-harmonik-tepki.md (Ewins, Modal Testing, bölüm 2).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from core.model import Model


@dataclass(frozen=True)
class FRF:
    """Frekans tepkisi. U global DOF sırasında karmaşık genlik [mm] (yük modelin Load'larıdır)."""

    f: np.ndarray  # (q,) Hz
    U: np.ndarray  # (q, n_dof) karmaşık

    def nokta(self, model: Model, node_id: int, dof: str) -> np.ndarray:
        """(q,) karmaşık genlik, o düğüm / DOF."""
        raise NotImplementedError("SPEC 68c: FRF.nokta")

    def genlik(self, model: Model, node_id: int, dof: str) -> np.ndarray:
        """|U| (q,) [mm]."""
        raise NotImplementedError("SPEC 68c: FRF.genlik")

    def faz(self, model: Model, node_id: int, dof: str) -> np.ndarray:
        """Faz açısı (q,) [derece], (−180, 180]."""
        raise NotImplementedError("SPEC 68c: FRF.faz")


def harmonic_modal(
    model: Model,
    f: Sequence[float],
    *,
    zeta: float | Sequence[float],
    n_modes: int,
    residual: bool = True,
) -> FRF:
    """Modal süperpozisyon (SPEC 45 modları, φᵀMφ = 1); residual=True ise kalıntı esneklik düzeltmesi.

    zeta: sabit ya da mod başına (n_modes uzunlukta), 0 < ζ < 1; verilmezse ModelError.
    """
    raise NotImplementedError("SPEC 68c: harmonic_modal")


def harmonic_direct(model: Model, f: Sequence[float], *, alpha: float = 0.0, beta: float = 0.0) -> FRF:
    """Doğrudan çözüm (K − ω² M + iω (αM + βK)) U = F; sönümsüz tam rezonans (tekil) → ModelError."""
    raise NotImplementedError("SPEC 68c: harmonic_direct")


def rayleigh_from_zeta(f1: float, f2: float, zeta: float) -> tuple[float, float]:
    """f1 ve f2 [Hz] frekanslarında tam ζ veren Rayleigh katsayıları (α, β): ζ(ω) = α/(2ω) + βω/2."""
    raise NotImplementedError("SPEC 68c: rayleigh_from_zeta")
