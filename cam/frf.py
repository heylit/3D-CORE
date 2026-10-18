"""
Takım ucu FRF'si (frekans tepki fonksiyonu): ölçüm CSV'si ve modal parametre okuma. SPEC 71.

Birimler: frekans Hz, G mm/N. Kod birim dönüştürmez; CSV başlığında '# birim: mm/N' zorunludur.
Modal model:  G(iω) = Σ 1 / (k_r (1 − r² + 2iζ_r r)),  r = ω/ω_n
Ölçüm bandı dışına ekstrapolasyon yapılmaz. Hatalar cam.model.CamError.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FRF:
    f: np.ndarray  # (q,) Hz, artan
    G: np.ndarray  # (q,) karmaşık, mm/N

    def at(self, f: np.ndarray) -> np.ndarray:
        """Ölçüm bandı içinde doğrusal ara değer; bant dışı → CamError."""
        raise NotImplementedError("SPEC 71: FRF.at")


def frf_csv(yol) -> FRF:
    """'f_Hz, Re, Im' sütunlu CSV (mm/N, artan frekans)."""
    raise NotImplementedError("SPEC 71: frf_csv")


def frf_modal(modlar: Sequence[tuple[float, float, float]], f: np.ndarray) -> FRF:
    """Mod başına (f_n [Hz], ζ, k [N/mm]) ile G(iω)."""
    raise NotImplementedError("SPEC 71: frf_modal")


@dataclass(frozen=True)
class TakimFRF:
    xx: FRF
    yy: FRF
    xy: FRF | None = None
    yx: FRF | None = None
