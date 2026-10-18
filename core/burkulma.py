"""
Doğrusal (Euler) burkulma: (K + λ Kg) φ = 0.

Referans yük model.loads altında statik çözüm u0, eleman gerilmeleri σ0, geometrik rijitlik Kg(σ0),
sonra en küçük |λ| özdeğerleri. Negatif λ (yük ters yönde burkulma) atılmaz, raporlanır.
Bağımlılık: yalnız numpy, scipy, core.

Teori: specs/68a-burkulma.md (Timoshenko–Gere, Bölüm 2; Cook–Malkus–Plesha–Witt, Bölüm 18).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.model import Model


@dataclass(frozen=True)
class BucklingResult:
    """Burkulma sonucu. modes global DOF sırasında, max |φ| = 1, tutulu DOF'larda 0."""

    lam: np.ndarray  # (k,) yük çarpanları, |λ| artan; negatifler dahil
    modes: np.ndarray  # (n_dof, k)
    u0: np.ndarray  # (n_dof,) referans statik çözüm [mm]


def buckling(model: Model, n_modes: int = 4) -> BucklingResult:
    """
    En küçük |λ| olan n_modes burkulma yük çarpanı ve mod şekli.

    Hatalar ModelError: yük yok, serbest DOF yok, geçersiz n_modes, tekil K (mesnet yok),
    kg sağlamayan eleman tipi, bütün λ sonsuz / tanımsız (gerilmesiz model).
    """
    raise NotImplementedError("specs/68a-burkulma.md uygulanacak")
