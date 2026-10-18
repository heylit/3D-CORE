"""
SPEC 44 — Tezgâh gövdeleri arası çarpışma, en az boşluk ve eksen sınırı denetimi, hareket boyunca.

Uzaklıklar (kapsül çiftlerinde işaretli: girişimde negatif):
- kapsül–kapsül: doğru parçaları arası en kısa uzaklık − r_a − r_b,
- kapsül–kutu: min_t uzaklık(x(t), kutu) − r (kutu içindeki nokta için uzaklık 0),
- kutu–kutu: ayırıcı eksen teoremi (15 eksen); kesişimde 0, ayrıksa en büyük eksen boşluğu (alt sınır).
Olay: uzaklık < clearance (kutu–kutuda kutular clearance/2 büyütülerek kesişim).

Örnekleme: n = ⌈(|ΔX, ΔY, ΔZ| + Σ |Δθ_i|·ρ_i) / σ⌉ (Δθ radyan), ilk temas ikiye bölmeyle 1e-6 mm.
Adım indeksi k SPEC 05 kuralıyla: nokta 0 ilk yolun başlangıcı, her hareket bir adım, yollar arasında
uçlar farklıysa bağlantı adımı; yay kirişleri hareketin k'sini taşır.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import Setup, Toolpath
from cam.multiaxis.machine import Box, Capsule, MachineModel

EVENT_KINDS = ("tezgah_carpma", "eksen_siniri")


def dist_capsule_capsule(a: Capsule, b: Capsule) -> float:
    """İki kapsül arası işaretli uzaklık [mm]."""
    raise NotImplementedError("SPEC 44: dist_capsule_capsule")


def dist_capsule_box(c: Capsule, b: Box) -> float:
    """Kapsül–kutu işaretli uzaklık [mm]."""
    raise NotImplementedError("SPEC 44: dist_capsule_box")


def boxes_overlap(a: Box, b: Box, margin: float = 0.0) -> bool:
    """Kutular (her biri margin/2 büyütülmüş) kesişiyor mu (SAT, 15 eksen)."""
    raise NotImplementedError("SPEC 44: boxes_overlap")


@dataclass
class MachineEvent:
    """kind: "tezgah_carpma" (a, b gövde adları) veya "eksen_siniri" (a eksen adı, b = "")."""

    kind: str
    k: int
    t: float
    a: str
    b: str
    distance: float
    detail: str


def check(
    model: MachineModel,
    setup: Setup,
    ops: list[Toolpath],
    L: float | None = None,
    tcp: bool = True,
    sigma: float = 1.0,
    clearance: float = 0.0,
    prev: tuple[float, ...] | None = None,
) -> list[MachineEvent]:
    """Program boyunca tezgâh çarpışması ve eksen sınırı olayları; (kind, k, a, b) başına ilk t."""
    raise NotImplementedError("SPEC 44: check")
