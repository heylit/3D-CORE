"""
SPEC 69 — Mekanizma dinamiği: ters dinamik, eklem kuvvetleri ve motor torku.

Sürücü eklemlerin hareketi q(t) verilir; her anda sürücü torku/kuvveti ve eklem tepkileri bulunur.
Birimler: t, mm, s → kuvvet N, moment N·mm, atalet t·mm², güç N·mm/s (mW).

Konum: SPEC 33 `drive` ile her t'de çözülür. Hız: Φ_q q̇ = −Φ_t. İvme: hız çözümünün t etrafında
merkezi farkı (h = 1e-4·T_periyot, O(h²)).
Newton–Euler (her hareketli cisim i, dünya çerçevesinde):
    m_i a_c,i = F_dış,i + m_i g + Σ F_eklem
    J_i ω̇_i + ω_i × J_i ω_i = M_dış,i + Σ (r × F_eklem + M_eklem)
Tepkiler Lagrange çarpanlarıyla:  Φ_qᵀ λ = Q_dış + Q_g − M q̈ − Q_v ; sürücü kısıtının çarpanı = tork.
Kaynak: Shabana, Computational Dynamics, 3. baskı, Bölüm 6–7; Nikravesh, Computer-Aided Analysis of
Mechanical Systems, Bölüm 11.

Bu modül OCCT import etmez; parça köprüsü (kutleler_parcadan) geometry/malzeme'yi geç import eder.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from assy.model import Assembly

if TYPE_CHECKING:
    from geometry.part import Part

# Dünya yerçekimi, mm/s²
G_DUNYA = 9810.0


@dataclass(frozen=True)
class Kutle:
    """Bileşenin kütle özellikleri, bileşenin yerel çerçevesinde."""

    m: float  # t
    c: np.ndarray  # (3,) mm, kütle merkezi
    J: np.ndarray  # (3, 3) t·mm², c etrafında


@dataclass(frozen=True)
class Surucu:
    """Sürücü eklem: q(t) derece (döner) ya da mm (kayar)."""

    joint: str
    q: Callable[[float], float]

    @staticmethod
    def sabit_hiz(joint: str, q0: float, hiz: float) -> Surucu:
        """q(t) = q0 + hiz·t  (derece/s ya da mm/s)."""
        raise NotImplementedError

    @staticmethod
    def tablo(joint: str, t: Sequence[float], q: Sequence[float]) -> Surucu:
        """Tablodan kübik spline (scipy.interpolate.CubicSpline)."""
        raise NotImplementedError


@dataclass(frozen=True)
class DinamikSonuc:
    t: np.ndarray  # (s,)
    q: Mapping[str, np.ndarray]  # eklem → (s,)
    tork: Mapping[str, np.ndarray]  # sürücü → (s,) N·mm ya da N
    eklem_kuvveti: Mapping[str, np.ndarray]  # eklem → (s, 3) N, eklemin a çerçevesinde
    eklem_momenti: Mapping[str, np.ndarray]  # eklem → (s, 3) N·mm
    guc: np.ndarray  # (s,) N·mm/s (mW)
    belirsiz: bool  # fazla kısıtlı → tepkiler en küçük kareler

    def en_kotu(self, ad: str) -> tuple[float, float]:
        """(t, |değer| maks): ad bir sürücü ise tork, eklem ise kuvvet büyüklüğü."""
        raise NotImplementedError


def ters_dinamik(
    assembly: Assembly,
    kutleler: Mapping[str, Kutle],
    suruculer: Sequence[Surucu],
    t: Sequence[float],
    *,
    g=(0.0, 0.0, -G_DUNYA),
    dis_kuvvetler: Mapping[str, Callable[[float], tuple[np.ndarray, np.ndarray]]] | None = None,
) -> DinamikSonuc:
    """Ters dinamik: her t için sürücü torku ve eklem tepkileri. Girdiyi değiştirmez."""
    raise NotImplementedError


def kutleler_parcadan(assembly: Assembly, parts: Mapping[str, Part], kutuphane) -> dict[str, Kutle]:
    """66 köprüsü: Component.material → rho, geometry.props.mass_props ile Kutle (OCCT, geç import)."""
    raise NotImplementedError
