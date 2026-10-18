"""
SPEC 29 — Otomatik işlem planı (freze): SPEC 27 özelliklerinden SPEC 03 / 04 işlemlerine, takım ve kesme
verisi SPEC 14 kütüphanesinden, işlem sırası, bağlama (gerekirse alt yüz için ikinci bağlama), G-code.

Planlanamayan her özellik gerekçe koduyla `Unplanned` olur; hiçbir özellik sessizce atlanmaz.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cam.cutting import SpindleFeed
from cam.features import Features
from cam.gcode import GRBL, Dialect, DrillOp
from cam.model import CylinderStock, Setup, Stock, ToolLibrary, Toolpath, Wcs
from geometry.part import Part

KINDS = ("yuz_alma", "acik_bolge", "cep", "cep_kalan", "delik", "lamba")
UNPLANNED_CODES = (
    "kesme_verisi_yok",
    "takim_yok",
    "takim_sigmiyor",
    "kesici_boy_yetmez",
    "ustten_erisilemez",
    "havsa_takimi_yok",
    "kilavuz_cevrimi_yok",
    "baglama_carpismasi",
    "on_delik_yok",
    "genel_girinti",
)
NOTE_CODES = ("kose_artigi", "yan_paso_kisildi", "delik_tasma_kisildi", "ikinci_baglama")


@dataclass(frozen=True)
class PlannedOp:
    name: str  # f"{sıra:02d}-{kind}-T{tool_id}", sıra 1'den, bağlamalar boyunca sürer
    kind: str
    setup: int  # 0 → setups[0], 1 → setups[1]
    feature: str  # özellik adresi; delik grubunda "holes[i,j,...]"
    tool_id: int
    op: Toolpath | DrillOp
    spindle: SpindleFeed
    a_p: float | None
    stepover: float | None


@dataclass(frozen=True)
class Unplanned:
    feature: str
    code: str
    detail: str


@dataclass(frozen=True)
class PlanNote:
    feature: str
    code: str
    value: float
    detail: str


@dataclass(frozen=True)
class MillOptions:
    n_max: float | None = None
    rest: bool = True
    plunge_ratio: float = 0.3
    clearance: float = 1.0
    open_margin: float = 1.0
    drill_tol: float = 0.01
    breakthrough: float = 1.0
    peck_limit: float = 3.0
    peck_q: float = 1.0
    hole_d_max: float = 20.0
    tol: float = 1e-3
    strict: bool = False


DEFAULT_OPTIONS = MillOptions()  # dondurulmuş: paylaşılan varsayılan güvenli


@dataclass(frozen=True)
class MillPlan:
    material: str
    features: Features
    setups: tuple[Setup, ...]
    ops: tuple[PlannedOp, ...]
    unplanned: tuple[Unplanned, ...]
    notes: tuple[PlanNote, ...]

    def ops_for(self, setup: int) -> list[Toolpath | DrillOp]:
        """Bir bağlamanın işlemleri, plan sırasıyla."""
        raise NotImplementedError

    def tool_changes(self) -> int:
        """Bağlama içinde ardışık farklı takım geçişleri + her bağlamanın ilk takımı."""
        raise NotImplementedError

    def summary(self) -> list[dict]:
        """Op başına {name, kind, setup, feature, tool_id, n, F, a_p, stepover}."""
        raise NotImplementedError

    def gcode(self, lib: ToolLibrary, dialect: Dialect = GRBL, program_no: int = 1) -> list[str]:
        """Bağlama başına bir program (SPEC 04 / 14 `write`)."""
        raise NotImplementedError


def plan_mill_features(
    features: Features,
    part_zmin: float,
    stock: Stock,
    lib: ToolLibrary,
    material: str,
    wcs: Wcs | None = None,
    fixtures: Sequence[Stock | CylinderStock] = (),
    wcs2: Wcs | None = None,
    fixtures2: Sequence[Stock | CylinderStock] | None = None,
    options: MillOptions = DEFAULT_OPTIONS,
) -> MillPlan:
    """OCCT'siz çekirdek: SPEC 29 §2–5."""
    raise NotImplementedError


def plan_mill(part: Part, stock: Stock, lib: ToolLibrary, material: str, **kw) -> MillPlan:
    """recognize(part, stock, tol, hole_d_max) + plan_mill_features(...)."""
    raise NotImplementedError
