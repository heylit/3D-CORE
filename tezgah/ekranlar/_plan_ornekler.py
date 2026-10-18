"""
SPEC 47a — Plan ekranının uydurma örnekleri (gizlilik kuralı).

plan_blogu  : SPEC 29 K12 parçası (OCCT), freze, iki bağlama
plan_engelli: elle kurulmuş `Features` (SPEC 29 K6 delikleri + K3 keskin köşeli cep), OCCT'siz
plan_mili   : SPEC 27 K10 profilinden döndürülmüş mil (OCCT, SPEC 28 `turn_profile`), torna
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ORNEKLER: tuple[str, ...] = ("plan_blogu", "plan_engelli", "plan_mili")


@dataclass(frozen=True)
class PlanGirdisi:
    """Planın girdileri. `part` None → `features` ile `plan_mill_features` (OCCT'siz)."""

    ad: str
    tur: str  # "freze" | "torna"
    aciklama: str
    malzeme: str
    stok: Any  # Stock | CylinderStock
    lib: Any  # ToolLibrary
    part: Any = None  # geometry.part.Part | None
    features: Any = None  # cam.features.Features | None (OCCT'siz örnek)
    part_zmin: float | None = None
    secenekler: dict[str, Any] = field(default_factory=dict)  # MillOptions / TurnOptions alanları
    gerektirir: tuple[str, ...] = ()  # "occt"


def plan_blogu() -> PlanGirdisi:
    raise NotImplementedError("SPEC 47a: plan_blogu")


def plan_engelli() -> PlanGirdisi:
    raise NotImplementedError("SPEC 47a: plan_engelli")


def plan_mili() -> PlanGirdisi:
    raise NotImplementedError("SPEC 47a: plan_mili")


KURUCULAR: dict[str, Callable[[], PlanGirdisi]] = {
    "plan_blogu": plan_blogu,
    "plan_engelli": plan_engelli,
    "plan_mili": plan_mili,
}


def ornek(ad: str) -> PlanGirdisi:
    """Adıyla örnek. Bilinmeyen ad → KeyError (uçta 404)."""
    raise NotImplementedError("SPEC 47a: ornek")


def hazir(ad: str) -> str | None:
    """None → örnek bu kurulumda çalışır; metin → neden (ör. "OCCT kurulu değil: pip install -e .[cad]")."""
    raise NotImplementedError("SPEC 47a: hazir")
