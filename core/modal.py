"""
Modal analiz: K_ff φ = ω² M_ff φ (doğal frekanslar ve mod şekilleri).

Birimler N – mm – t – s: ω² doğrudan 1/s², f = ω / 2π Hz. Kütle sonuçları ton.
Küçük modelde yoğun scipy.linalg.eigh, büyük modelde kaydır-ters çevir Lanczos (eigsh).

Teori: specs/45-modal.md (Bathe, Bölüm 9–11; Cook–Malkus–Plesha, Bölüm 11).
"""

from __future__ import annotations

import numbers
from dataclasses import dataclass

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from core import elements
from core.assembly import assemble_K, assemble_M
from core.model import Model, ModelError

# Serbest DOF sayısı bunun altındaysa yoğun eigh kullanılır
YOGUN_SINIRI = 300

# |λ| ≤ SIFIR_ORANI · λ_ölçek olan negatif özdeğer yuvarlamadır, sıfıra çekilir
SIFIR_ORANI = 1e-9

# Lanczos kaydırması: σ = −KAYDIRMA_ORANI · λ_ölçek (σ < 0 → K − σM pozitif tanımlı)
KAYDIRMA_ORANI = 1e-6


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
        if not 0 <= i < self.modes.shape[1]:
            raise ModelError(f"Mod indeksi {i} geçersiz (0..{self.modes.shape[1] - 1})")
        return float(self.modes[model.dof_index(node_id, dof), i])


def model_mass(model: Model) -> float:
    """Toplam kütle Σ ρV (bar1d: ρAL) [t]. ρ ≤ 0 → ModelError.

    Tek yöndeki öteleme vektörü r için rᵀ M r = Σ ρV (tutarlı ve toplanmış kütlede aynı).
    """
    M = assemble_M(model)
    r = np.zeros(model.n_dof)
    r[0 :: model.dofs_per_node] = 1.0
    return float(r @ (M @ r))


def _serbest_tutulu(model: Model) -> tuple[np.ndarray, np.ndarray]:
    """(f, c) DOF indeksleri. BC value okunmaz; aynı DOF'a farklı değer → ModelError."""
    n = model.n_dof
    deger: dict[int, float] = {}
    for bc in model.bcs:
        i = model.dof_index(bc.node, bc.dof)
        if i in deger and deger[i] != bc.value:
            raise ModelError(f"Düğüm {bc.node} '{bc.dof}' için çelişen sınır koşulları")
        deger[i] = bc.value
    tutulu = np.zeros(n, dtype=bool)
    tutulu[list(deger)] = True
    return np.flatnonzero(~tutulu), np.flatnonzero(tutulu)


def _kutle_kontrol(model: Model) -> None:
    """Her eleman me sağlamalı (ρ kontrolü me içinde)."""
    for e in model.elements:
        if not hasattr(elements.get(e.type), "me"):
            raise ModelError(f"Eleman tipi '{e.type}' kütle matrisi (me) sağlamıyor; modal analiz yapılamaz")


def _coz(K_ff: sp.csr_matrix, M_ff: sp.csr_matrix, k: int, lam_olcek: float) -> tuple[np.ndarray, np.ndarray]:
    """En küçük k özdeğer ve özvektör (artan)."""
    n_f = K_ff.shape[0]
    if n_f <= YOGUN_SINIRI or k > n_f - 2:
        lam, phi = sla.eigh(K_ff.toarray(), M_ff.toarray(), subset_by_index=[0, k - 1])
    else:
        sigma = -KAYDIRMA_ORANI * lam_olcek
        try:
            lam, phi = spla.eigsh(K_ff.tocsc(), k=k, M=M_ff.tocsc(), sigma=sigma, which="LM")
        except (spla.ArpackError, RuntimeError) as hata:
            raise ModelError(f"Özdeğer çözümü yakınsamadı: {hata}") from None
    sira = np.argsort(lam)
    return lam[sira], phi[:, sira]


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
    if isinstance(n_modes, bool) or not isinstance(n_modes, numbers.Integral):
        raise ModelError(f"n_modes tamsayı olmalı (n_modes={n_modes!r})")
    n_modes = int(n_modes)
    model.validate()
    _kutle_kontrol(model)
    f, _ = _serbest_tutulu(model)
    n_f = len(f)
    if n_f == 0:
        raise ModelError("Serbest DOF yok: modal analiz yapılamaz")
    if not 1 <= n_modes <= n_f:
        raise ModelError(f"n_modes 1..{n_f} aralığında olmalı (n_modes={n_modes})")

    K = assemble_K(model)
    M = assemble_M(model, lumped=lumped)
    K_ff = K[f][:, f]
    M_ff = M[f][:, f]
    dM = M_ff.diagonal()
    if np.any(dM <= 0.0):
        raise ModelError("M_ff pozitif tanımlı değil: kütlesi olmayan serbest DOF var")
    lam_olcek = float(np.max(np.abs(K_ff.diagonal()) / dM))
    if lam_olcek == 0.0:
        lam_olcek = 1.0

    lam, phi = _coz(K_ff, M_ff, n_modes, lam_olcek)
    if not (np.all(np.isfinite(lam)) and np.all(np.isfinite(phi))):
        raise ModelError("Özdeğer çözümü sonlu değil")
    if np.any(lam < -SIFIR_ORANI * lam_olcek):
        raise ModelError(f"Negatif özdeğer (λ_min={lam.min()}): K pozitif yarı tanımlı değil")
    lam = np.where(lam < 0.0, 0.0, lam)

    # Kütleye göre birimle ve işaret kuralı
    norm = np.sqrt(np.einsum("ij,ij->j", phi, M_ff @ phi))
    phi = phi / norm
    en_buyuk = np.argmax(np.abs(phi), axis=0)
    isaret = np.sign(phi[en_buyuk, np.arange(phi.shape[1])])
    phi = phi * np.where(isaret == 0, 1.0, isaret)

    modes = np.zeros((model.n_dof, n_modes))
    modes[f] = phi
    omega = np.sqrt(lam)
    return ModalResult(omega2=lam, omega=omega, f=omega / (2.0 * np.pi), modes=modes, lumped=lumped)


def effective_mass(model: Model, result: ModalResult) -> np.ndarray:
    """Etkin kütle Γ² (k, model.dim) [t]; Γᵢ_d = φᵢᵀ M_ff r_d (yalnız serbest bölüm)."""
    f, _ = _serbest_tutulu(model)
    M = assemble_M(model, lumped=result.lumped)
    M_ff = M[f][:, f]
    phi = result.modes[f]
    dpn = model.dofs_per_node
    sutunlar = []
    for d in range(dpn):
        r = np.zeros(model.n_dof)
        r[d::dpn] = 1.0
        gamma = phi.T @ (M_ff @ r[f])
        sutunlar.append(gamma**2)
    return np.column_stack(sutunlar)
