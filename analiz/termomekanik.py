"""
Tek yönlü termo-mekanik zincir: sıcaklık geçmişi → ısıl yük (67b) → statik çözüm (SPEC 68b).

Mekanik sonuç ısıyı etkilemez. Isıl ve mekanik ağ aynı düğümlerde olmalı
(aynı tet4 ağı ya da tet10'un köşe düğümleri).

Teori: specs/68b-gecici-isil-termomekanik.md
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from core import elements
from core.isil import ThermalResult
from core.isil_gecici import TransientResult
from core.model import Model, ModelError
from core.post import von_mises
from core.solver import solve

# tet10 kenar ortası düğümleri (C3D10 sırası, 0 tabanlı köşe çiftleri)
_TET10_KENAR = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))


@dataclass(frozen=True)
class TermoMekanik:
    t: np.ndarray  # (s,)
    sigma_vM_maks: np.ndarray  # (s,) her zamanda en büyük düğüm σ_vM [MPa]
    u_maks: np.ndarray  # (s,) mm
    en_kotu_an: float  # s
    alanlar: Mapping[float, tuple[np.ndarray, np.ndarray]]  # istenen zamanlar: (u, düğüm σ_vM)


def _kose_dugumleri(model: Model) -> set[int]:
    kose = set()
    for e in model.elements:
        if e.type not in ("tet4", "tet10"):
            raise ModelError(f"Eleman {e.id}: termo-mekanik zincir tet4/tet10 destekler ('{e.type}')")
        kose.update(e.nodes[:4])
    return kose


def _alpha_denetle(model: Model, alpha) -> None:
    if isinstance(alpha, Mapping):
        for e in model.elements:
            if e.material not in alpha:
                raise ModelError(f"alpha: '{e.material}' malzemesi için değer yok")
            a = float(alpha[e.material])
            if not np.isfinite(a):
                raise ModelError(f"alpha sonlu olmalı ('{e.material}': {a})")
    elif not np.isfinite(float(alpha)):
        raise ModelError(f"alpha sonlu olmalı (alpha={alpha})")


def _dugum_sicakliklari(model: Model, node_ids: np.ndarray, T: np.ndarray) -> dict[int, float]:
    """Köşe sıcaklıkları + tet10 kenar ortası düğümlerinde iki köşenin ortalaması (doğrusal alan)."""
    Td = {int(i): float(v) for i, v in zip(node_ids, T, strict=True)}
    for e in model.elements:
        if e.type == "tet10":
            for m, (a, b) in enumerate(_TET10_KENAR):
                Td.setdefault(e.nodes[4 + m], 0.5 * (Td[e.nodes[a]] + Td[e.nodes[b]]))
    return Td


def _dugum_vm(model: Model, sigma_e: np.ndarray) -> np.ndarray:
    """Eleman gerilmelerinin hacim ağırlıklı düğüm ortalaması (SPEC 13), sonra σ_vM; model.nodes sırası."""
    n = len(model.nodes)
    toplam = np.zeros((n, 6))
    hacim = np.zeros(n)
    for e, s in zip(model.elements, sigma_e, strict=True):
        V = elements.get(e.type).volume(e, model)
        for nid in e.nodes:
            i = model.node_index(nid)
            toplam[i] += V * s
            hacim[i] += V
    if np.any(hacim == 0.0):
        raise ModelError("Hiçbir elemana ait olmayan düğüm var (düğüm gerilmesi tanımsız)")
    return np.asarray(von_mises(toplam / hacim[:, None]))


def zincir(
    model_mek: Model,
    sicaklik: TransientResult | ThermalResult,
    T_ref: float,
    alpha,
    zamanlar: Sequence[float] | None = None,
) -> TermoMekanik:
    """Sıcaklık geçmişini statik çözüme zincirler; `model_mek` değişmez (mesnetleri ondan alınır).

    Her zamanda: T(t) → 67b ısıl yükü → K u = F → σ = D(B u − ε0) → düğüm σ_vM.
    Kararlı `ThermalResult` tek zaman 0.0 sayılır. zamanlar=None → bütün kayıtlı zamanlar.
    Ağ uyuşmazlığı, eksik alpha, aralık dışı zaman → ModelError.
    """
    model_mek.validate()
    if model_mek.dim != 3:
        raise ModelError(f"Termo-mekanik zincir 3B model ister (dim={model_mek.dim})")
    kose = _kose_dugumleri(model_mek)
    node_ids = np.asarray(sicaklik.node_ids)
    if set(int(i) for i in node_ids) != kose:
        raise ModelError("Isıl ve mekanik ağ uyuşmuyor: sıcaklık düğümleri mekanik köşe düğümleri olmalı")
    _alpha_denetle(model_mek, alpha)
    T_ref = float(T_ref)
    if not np.isfinite(T_ref):
        raise ModelError(f"T_ref sonlu olmalı (T_ref={T_ref})")

    if isinstance(sicaklik, ThermalResult):
        kayit_t = np.array([0.0])

        def alan(t: float) -> np.ndarray:
            if t != 0.0:
                raise ModelError(f"Kararlı sıcaklık sonucu yalnız t = 0.0'da tanımlı (istenen {t})")
            return np.asarray(sicaklik.T, dtype=float)

    else:
        kayit_t = np.asarray(sicaklik.t, dtype=float)
        alan = sicaklik.at
    t = kayit_t if zamanlar is None else np.array([float(x) for x in zamanlar])
    for x in t:
        alan(float(x))  # aralık dışı → ModelError, ağır çözümden önce

    from core import yukler  # SPEC 67b

    sv, um = np.zeros(len(t)), np.zeros(len(t))
    alanlar: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for j, x in enumerate(t):
        Td = _dugum_sicakliklari(model_mek, node_ids, alan(float(x)))
        m = copy.deepcopy(model_mek)
        yukler.add_loads(m, yukler.thermal_loads(m, Td, T_ref, alpha))
        u = solve(m).u
        vm = _dugum_vm(m, yukler.thermal_strain_stress(m, u, Td, T_ref, alpha))
        sv[j] = vm.max()
        um[j] = np.linalg.norm(u.reshape(-1, 3), axis=1).max()
        alanlar[float(x)] = (u, vm)
    return TermoMekanik(
        t=t,
        sigma_vM_maks=sv,
        u_maks=um,
        en_kotu_an=float(t[int(np.argmax(sv))]),
        alanlar=alanlar,
    )
