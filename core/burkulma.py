"""
Doğrusal (Euler) burkulma: (K + λ Kg) φ = 0.

Referans yük model.loads altında statik çözüm u0, eleman gerilmeleri σ0, geometrik rijitlik Kg(σ0),
sonra en küçük |λ| özdeğerleri. Negatif λ (yük ters yönde burkulma) atılmaz, raporlanır.
Bağımlılık: yalnız numpy, scipy, core.

Çözüm yolu: K_ff pozitif tanımlı, Kg_ff belirsiz işaretli. ν = 1/λ ile
    (−Kg_ff) φ = ν K_ff φ
simetrik-tanımlı genel özdeğer problemidir (SPEC 45'teki gibi M yerine K). En küçük |λ| en büyük |ν|'dür:
küçük modelde yoğun scipy.linalg.eigh (bütün ν), büyükte eigsh(−Kg, M=K, which="LM").

Teori: specs/68a-burkulma.md (Timoshenko–Gere, Bölüm 2; Cook–Malkus–Plesha–Witt, Bölüm 18).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.linalg as sla
import scipy.sparse.linalg as spla

from core import elements
from core.assembly import assemble_K, assemble_Kg
from core.model import Model, ModelError
from core.solver import solve

# Serbest DOF sayısı bunun altındaysa yoğun eigh kullanılır
YOGUN_SINIRI = 300

# |ν| ≤ SIFIR_ORANI · max|ν| olan ν sıfır sayılır (λ = ∞, o yönde burkulma yok)
SIFIR_ORANI = 1e-10

# max|ν| bunun altındaysa model gerilmesiz sayılır (λ > 1e14: anlamsız)
NU_ALT_SINIR = 1e-14


@dataclass(frozen=True)
class BucklingResult:
    """Burkulma sonucu. modes global DOF sırasında, max |φ| = 1, tutulu DOF'larda 0."""

    lam: np.ndarray  # (k,) yük çarpanları, |λ| artan; negatifler dahil
    modes: np.ndarray  # (n_dof, k)
    u0: np.ndarray  # (n_dof,) referans statik çözüm [mm]


def _serbest_tutulu(model: Model) -> tuple[np.ndarray, np.ndarray]:
    """(f, c) DOF indeksleri (solve aynı DOF'a çelişen BC'yi zaten reddeder)."""
    tutulu = np.zeros(model.n_dof, dtype=bool)
    for bc in model.bcs:
        tutulu[model.dof_index(bc.node, bc.dof)] = True
    return np.flatnonzero(~tutulu), np.flatnonzero(tutulu)


def _gerilmeler(model: Model, u0: np.ndarray) -> dict[int, np.ndarray]:
    """σ0: eleman id → eleman gerilmesi (eleman tipinin stress düzeninde)."""
    return {e.id: elements.get(e.type).stress(e, model, u0) for e in model.elements}


def _coz(K_ff, Kg_ff, k: int) -> tuple[np.ndarray, np.ndarray]:
    """(−Kg) φ = ν K φ'nin en büyük |ν| olan k çözümü, |ν| azalan."""
    n_f = K_ff.shape[0]
    if n_f <= YOGUN_SINIRI or k > n_f - 2:
        nu, phi = sla.eigh(-Kg_ff.toarray(), K_ff.toarray())
    else:
        try:
            nu, phi = spla.eigsh(-Kg_ff.tocsc(), k=k, M=K_ff.tocsc(), which="LM")
        except (spla.ArpackError, RuntimeError) as hata:
            raise ModelError(f"Burkulma özdeğer çözümü yakınsamadı: {hata}") from None
    sira = np.argsort(-np.abs(nu), kind="stable")[:k]
    return nu[sira], phi[:, sira]


def buckling(model: Model, n_modes: int = 4) -> BucklingResult:
    """
    En küçük |λ| olan n_modes burkulma yük çarpanı ve mod şekli.

    1. n_modes, yük ve eleman (kg) kontrolü; model.validate()
    2. K u0 = F (core.solver.solve; tekil K → ModelError), σ0 = eleman gerilmeleri
    3. Kg(σ0), serbest bölüm, (−Kg_ff) φ = ν K_ff φ, λ = 1/ν
    4. φ: max |φ| = 1, mutlak değeri en büyük bileşen pozitif
    Hatalar ModelError: yük yok, serbest DOF yok, geçersiz n_modes, tekil K (mesnet yok),
    kg sağlamayan eleman tipi, bütün λ sonsuz / tanımsız (gerilmesiz model).
    """
    if isinstance(n_modes, bool) or not isinstance(n_modes, (int, np.integer)):
        raise ModelError(f"n_modes tamsayı olmalı (n_modes={n_modes!r})")
    n_modes = int(n_modes)
    if n_modes < 1:
        raise ModelError(f"n_modes en az 1 olmalı (n_modes={n_modes})")
    model.validate()
    if not model.loads:
        raise ModelError("Burkulma için referans yük (model.loads) gerekli")
    for e in model.elements:
        if not hasattr(elements.get(e.type), "kg"):
            raise ModelError(f"Eleman tipi '{e.type}' geometrik rijitlik (kg) sağlamıyor; burkulma yapılamaz")
    f, _ = _serbest_tutulu(model)
    n_f = len(f)
    if n_f == 0:
        raise ModelError("Serbest DOF yok: burkulma analizi yapılamaz")
    if n_modes > n_f:
        raise ModelError(f"n_modes 1..{n_f} aralığında olmalı (n_modes={n_modes})")

    u0 = solve(model).u
    K = assemble_K(model)
    Kg = assemble_Kg(model, _gerilmeler(model, u0))
    K_ff = K[f][:, f]
    Kg_ff = Kg[f][:, f]

    nu, phi = _coz(K_ff, Kg_ff, n_modes)
    if not (np.all(np.isfinite(nu)) and np.all(np.isfinite(phi))):
        raise ModelError("Burkulma özdeğer çözümü sonlu değil")
    nu_max = float(np.max(np.abs(nu)))
    if nu_max <= NU_ALT_SINIR:
        raise ModelError("Bütün burkulma yük çarpanları sonsuz: referans yük gerilme üretmiyor")
    sifir = np.abs(nu) <= SIFIR_ORANI * nu_max
    lam = np.where(sifir, np.inf, 1.0 / np.where(sifir, 1.0, nu))

    # max |φ| = 1, en büyük bileşen pozitif
    en_buyuk = np.argmax(np.abs(phi), axis=0)
    tepe = phi[en_buyuk, np.arange(phi.shape[1])]
    phi = phi / tepe

    modes = np.zeros((model.n_dof, n_modes))
    modes[f] = phi
    return BucklingResult(lam=lam, modes=modes, u0=u0)
