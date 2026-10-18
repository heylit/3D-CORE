"""
Tolerans yığılımı (SPEC 34).

1B ölçü zinciri  G = c + Σ a_i x_i : en kötü durum, istatistiksel (RSS), Monte Carlo; katkı payları ve
şartname dışı oranı. 3B: montajdaki DISTANCE / ANGLE kısıt değerlerine verilen toleranslar, SPEC 08
Jacobian'ı ve örtük fonksiyon teoremiyle doğrusal zincire çevrilir.

Kaynak: Fortini, Dimensioning for Interchangeable Manufacture (1967); Chase–Parkinson (1991);
Drake, Dimensioning and Tolerancing Handbook, Bölüm 9.

Birimler: mm, açı derece. Tüm hatalar AssyError.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np

from assy.model import Assembly, Ref

if TYPE_CHECKING:
    from assy.model import Tolerance  # arayüz A1


class Method(StrEnum):
    WORST_CASE = "en_kotu"
    RSS = "rss"
    MONTE_CARLO = "monte_carlo"


@dataclass(frozen=True)
class Link:
    """Zincir halkası: tolerans ve hassasiyet katsayısı a (sonlu, sıfırdan farklı)."""

    tol: Tolerance
    a: float = 1.0
    name: str = ""

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 34: Link doğrulaması")


@dataclass(frozen=True)
class Chain:
    """G = c + Σ a_i x_i. Boş zincir → AssyError."""

    links: tuple[Link, ...]
    c: float = 0.0

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 34: Chain doğrulaması")

    @property
    def nominal(self) -> float:
        """G₀ = c + Σ a_i x₀_i"""
        raise NotImplementedError("SPEC 34: Chain.nominal")

    @property
    def mean(self) -> float:
        """μ_G = c + Σ a_i μ_i"""
        raise NotImplementedError("SPEC 34: Chain.mean")


@dataclass(frozen=True)
class StackResult:
    method: Method
    nominal: float
    mean: float
    lower: float
    upper: float
    sigma: float | None  # WORST_CASE: None
    contributions: tuple[float, ...]  # halka sırasıyla, toplam 1 (hepsi T = 0 ise 0)


def worst_case(chain: Chain) -> StackResult:
    """T_wc = Σ |a_i| T_i,  G ∈ [μ_G − T_wc, μ_G + T_wc]."""
    raise NotImplementedError("SPEC 34: worst_case")


def rss(chain: Chain, k: float = 3.0) -> StackResult:
    """σ_G = √(Σ a_i² σ_i²),  G ∈ [μ_G − k σ_G, μ_G + k σ_G]."""
    raise NotImplementedError("SPEC 34: rss")


def samples(chain: Chain, n: int, seed: int = 0) -> np.ndarray:
    """G örnekleri (n,); aynı seed → aynı dizi."""
    raise NotImplementedError("SPEC 34: samples")


def monte_carlo(chain: Chain, n: int = 100_000, seed: int = 0, k: float = 3.0) -> StackResult:
    """Örnek ortalaması, örnek std (ddof=1), sınırlar Φ(−k) ve Φ(k) ampirik yüzdelikleri."""
    raise NotImplementedError("SPEC 34: monte_carlo")


def reject_fraction(
    chain: Chain,
    lsl: float,
    usl: float,
    method: Method = Method.RSS,
    n: int = 100_000,
    seed: int = 0,
) -> float:
    """G < LSL veya G > USL olasılığı (RSS: normal yaklaşım, MONTE_CARLO: örnek oranı)."""
    raise NotImplementedError("SPEC 34: reject_fraction")


def measure(assembly: Assembly, a: Ref, b: Ref) -> float:
    """POINT–PLANE (p − q)·n, PLANE–PLANE (p_b − p_a)·n_a, POINT–POINT |p_b − p_a|."""
    raise NotImplementedError("SPEC 34: measure")


def assembly_chain(
    assembly: Assembly, tolerances: dict[int, Tolerance], a: Ref, b: Ref, tol: float = 1e-10
) -> Chain:
    """Montajdan doğrusal zincir: a_j = ∂m/∂p_j (δq = −J_q⁺ J_p δp), c = m₀ − Σ a_j p₀_j."""
    raise NotImplementedError("SPEC 34: assembly_chain")
