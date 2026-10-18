"""
Modal analiz: K_ff φ = ω² M_ff φ (doğal frekanslar ve mod şekilleri).

Birimler N – mm – t – s: ω² doğrudan 1/s², f = ω / 2π Hz. Kütle sonuçları ton.
Küçük modelde yoğun scipy.linalg.eigh, büyük modelde kaydır-ters çevir Lanczos (eigsh).

Teori: specs/45-modal.md (Bathe, Bölüm 9–11; Cook–Malkus–Plesha, Bölüm 11).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.model import Model

# Serbest DOF sayısı bunun altındaysa yoğun eigh kullanılır
YOGUN_SINIRI = 300


@dataclass(frozen=True)
class ModalResult:
    """Modal analiz sonucu. modes global DOF sırasında, tutulu DOF'larda 0, φᵀ M φ = 1."""

    omega2: np.ndarray  # (k,) [1/s²], artan
    omega: np.ndarray  # (k,) [rad/s]
    f: np.ndarray  # (k,) [Hz]
    modes: np.ndarray  # (n_dof, k)
    lumped: bool = False

    def mode(self, model: Model, i: int, node_id: int, dof: str = "ux") -> float:
        """i. modun o düğüm / DOF bileşeni."""
        raise NotImplementedError("SPEC 45: ModalResult.mode")


def model_mass(model: Model) -> float:
    """Toplam kütle Σ ρV (bar1d: ρAL) [t]. ρ ≤ 0 → ModelError."""
    raise NotImplementedError("SPEC 45: model_mass")


def modal(model: Model, n_modes: int, *, lumped: bool = False) -> ModalResult:
    """
    En küçük n_modes doğal frekans ve kütleye göre birimlenmiş mod şekilleri.

    1. model.validate()
    2. K, M birleştir
    3. Serbest / tutulu DOF ayrımı (BC value okunmaz; çelişen BC → ModelError)
    4. n_f ≤ YOGUN_SINIRI veya n_modes > n_f − 2 → yoğun eigh; aksi → eigsh (sigma < 0)
    5. φᵀ M φ = 1; mutlak değeri en büyük bileşen pozitif
    Hatalar ModelError: geçersiz n_modes, serbest DOF yok, ρ ≤ 0, me sağlamayan eleman,
    negatif özdeğer, sonlu olmayan sonuç.
    """
    raise NotImplementedError("SPEC 45: modal")


def effective_mass(model: Model, result: ModalResult) -> np.ndarray:
    """Etkin kütle Γ² (k, model.dim) [t]; Γᵢ_d = φᵢᵀ M_ff r_d (yalnız serbest bölüm)."""
    raise NotImplementedError("SPEC 45: effective_mass")
