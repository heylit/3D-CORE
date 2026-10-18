"""
Post-process: eleman iç kuvvetleri ve gerilmeleri.

Teori: specs/01-bar.md (çubuk), specs/11-tet4.md (katı eleman gerilme tensörü)
"""

from __future__ import annotations

import numpy as np

from core import elements
from core.model import Model, ModelError


def element_forces(model: Model, u: np.ndarray) -> dict[int, float]:
    """eleman id -> eksenel kuvvet [N]. Sadece axial_force sağlayan (çubuk tipi) elemanlar."""
    sonuc = {}
    for e in model.elements:
        eleman = elements.get(e.type)
        if hasattr(eleman, "axial_force"):
            sonuc[e.id] = eleman.axial_force(e, model, u)
    return sonuc


def element_stresses(model: Model, u: np.ndarray) -> dict[int, float]:
    """eleman id -> eksenel gerilme sigma = N / A [MPa]. Sadece çubuk tipi elemanlar."""
    N = element_forces(model, u)
    return {e.id: N[e.id] / model.section(e.section).A for e in model.elements if e.id in N}


def element_stress_tensors(model: Model, u: np.ndarray) -> dict[int, np.ndarray]:
    """eleman id -> gerilme tensörü σ (6,) [MPa], Voigt: xx, yy, zz, xy, xz, yz (SPEC 11).

    Sadece stress sağlayan (katı) elemanlar.
    """
    sonuc = {}
    for e in model.elements:
        eleman = elements.get(e.type)
        if hasattr(eleman, "stress"):
            sonuc[e.id] = eleman.stress(e, model, u)
    return sonuc


def _tensor_dizisi(sigma) -> np.ndarray:
    """Voigt gerilme dizisini (6,) veya (n, 6) olarak doğrular. Biçim hatası, nan / inf → ModelError."""
    s = np.asarray(sigma, dtype=float)
    if s.ndim not in (1, 2) or s.shape[-1] != 6:
        raise ModelError(f"Gerilme dizisi (6,) veya (n, 6) olmalı (şekil {s.shape})")
    if not np.all(np.isfinite(s)):
        raise ModelError("Gerilme dizisinde sonlu olmayan değer var")
    return s


def von_mises(sigma) -> float | np.ndarray:
    """Von Mises eşdeğer gerilmesi [MPa] (SPEC 13). (6,) → float, (n, 6) → (n,).

    σ_vM = √( ½[(σxx − σyy)² + (σyy − σzz)² + (σzz − σxx)²] + 3(τxy² + τxz² + τyz²) )
    """
    s = _tensor_dizisi(sigma)
    xx, yy, zz, xy, xz, yz = np.moveaxis(s, -1, 0)
    vm = np.sqrt(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3.0 * (xy**2 + xz**2 + yz**2))
    return float(vm) if s.ndim == 1 else vm


def principal_stresses(sigma) -> np.ndarray:
    """Asal gerilmeler σ1 ≥ σ2 ≥ σ3 [MPa] (SPEC 13): S tensörünün özdeğerleri.

    (6,) → (3,), (n, 6) → (n, 3).
    """
    s = _tensor_dizisi(sigma)
    xx, yy, zz, xy, xz, yz = np.moveaxis(s, -1, 0)
    S = np.stack(
        [np.stack([xx, xy, xz], -1), np.stack([xy, yy, yz], -1), np.stack([xz, yz, zz], -1)],
        axis=-2,
    )
    return np.linalg.eigvalsh(S)[..., ::-1]  # eigvalsh artan sırada verir


def nodal_stress_tensors(model: Model, u: np.ndarray) -> dict[int, np.ndarray]:
    """düğüm id -> σ (6,) [MPa], düğümü içeren katı elemanların hacim ağırlıklı ortalaması (SPEC 13).

    σ_düğüm(i) = Σ_e∋i V_e σ_e / Σ_e∋i V_e. Katı elemana ait olmayan düğüm sözlükte yer almaz.
    """
    toplam: dict[int, np.ndarray] = {}
    hacim: dict[int, float] = {}
    for e in model.elements:
        eleman = elements.get(e.type)
        if not hasattr(eleman, "stress"):
            continue
        V = eleman.volume(e, model)
        Vsigma = V * eleman.stress(e, model, u)
        for nid in e.nodes:
            toplam[nid] = toplam.get(nid, 0.0) + Vsigma
            hacim[nid] = hacim.get(nid, 0.0) + V
    return {nid: toplam[nid] / hacim[nid] for nid in toplam}
