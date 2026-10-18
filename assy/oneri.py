"""
SPEC 35 — Delik kayıtlarından otomatik bağlantı (vida / civata) önerisi.

Saf Python + numpy. SPEC 23 Hole kayıtlarından eş eksenli delik dizilerini bulur, ISO tablolarından
vida / civata boyunu seçer, önerilen standart parçaları SPEC 08 kısıtlarıyla (CONCENTRIC + COINCIDENT
PLANE) yerleştirir. Birimler: mm.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from assy.model import Assembly, Component, Mate


@dataclass(frozen=True)
class DelikRef:
    component: str
    index: int  # Part.holes içindeki sıra


@dataclass
class Oneri:
    kind: str  # "vida" | "civata_somun"
    M: str  # "M8"
    L: float  # mm, seçilen standart boy
    grip: float  # mm, sıkıştırma boyu g
    stack: tuple[DelikRef, ...]  # dizi yönünde sıralı
    components: list[Component]  # eklenecekler; part = kanonik tanım
    mates: list[Mate]


@dataclass
class Eslesmeme:
    stack: tuple[DelikRef, ...]
    neden: str


def eksen_gruplari(
    assembly: Assembly, parts: Mapping[str, object], tol: float = 1e-3, tol_aci: float = 1e-6
) -> list[tuple[DelikRef, ...]]:
    """En az iki farklı bileşenden delik içeren eş eksen grupları, dizi yönünde sıralı."""
    raise NotImplementedError("SPEC 35")


def oner(
    assembly: Assembly,
    parts: Mapping[str, object],
    kappa: float = 1.0,
    tol: float = 1e-3,
    tol_aci: float = 1e-6,
) -> tuple[list[Oneri], list[Eslesmeme]]:
    """Her eş eksen grubu için bir Oneri ya da bir Eslesmeme."""
    raise NotImplementedError("SPEC 35")


def uygula(assembly: Assembly, oneriler: list[Oneri]) -> Assembly:
    """Önerilerin bileşen ve kısıtlarını eklenmiş yeni montaj; girdi değişmez."""
    raise NotImplementedError("SPEC 35")
