"""
SPEC 38 — İş föyü veri tipleri ve kurulumu: WCS tarifi, takım tablosu ve boy ofsetleri, SPEC 05 süre modeli,
işe özel doğrulama maddeleri (docs/tezgah-dogrulama.md bölümleri).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cam.gcode import GRBL, Dialect, DrillOp
from cam.model import Setup, Stock, ToolLibrary, Toolpath
from cam.sim import Machine
from geometry.drawing.types import Dimension, Sheet

if TYPE_CHECKING:
    from geometry.part import Part


@dataclass(frozen=True)
class ToolRow:
    T: int
    name: str
    kind: str  # ToolKind değeri
    D: float
    corner_r: float
    flute_length: float
    stickout: float | None
    holder: str | None
    L: float | None  # gauge_length
    offset: float | None  # Fanuc: L; GRBL: ΔL; bilinmiyorsa None
    need: float  # gerekli kesici boy (§3)
    rpm_max: int
    ops: tuple[str, ...]
    time: float  # s


@dataclass(frozen=True)
class OpRow:
    no: int  # bağlama içinde 1'den
    name: str
    T: int
    rpm: int
    F: float  # kesme hareketlerinin en büyük ilerlemesi (DrillOp: feed); kesme yoksa 0
    z_min: float  # kesme hareketlerinin en alçak Z'si (DrillOp: z)
    time: float  # s, §4
    t_end: float  # s, bağlama içinde birikimli


@dataclass(frozen=True)
class SetupSheet:
    index: int  # 1'den
    setup: Setup
    wcs: tuple[str, str, str]  # wcs_text(setup.stock)
    ref_id: int | None  # GRBL referans takımı; Fanuc'ta None
    tools: tuple[ToolRow, ...]
    ops: tuple[OpRow, ...]
    time: float
    tool_changes: int
    drawing: Sheet  # §5


@dataclass(frozen=True)
class InspectionItem:
    no: int  # 1'den
    text: str
    nominal: float
    tol: float  # ±t
    lower: float
    upper: float


@dataclass(frozen=True)
class CheckItem:
    section: int  # docs/tezgah-dogrulama.md bölümü (1..5)
    text: str


@dataclass(frozen=True)
class JobSheet:
    title: str
    material: str
    dialect: Dialect
    program_no: int
    setups: tuple[SetupSheet, ...]
    inspection: tuple[InspectionItem, ...]
    checks: tuple[CheckItem, ...]
    warnings: tuple[str, ...]
    total_time: float
    date: str | None = None


def wcs_text(stock: Stock) -> tuple[str, str, str]:
    """İş sıfırının ham malzemedeki yeri, eksen başına metin (§2)."""
    raise NotImplementedError("SPEC 38: wcs_text")


def build_job_sheet(
    title: str,
    setups: Sequence[Setup],
    ops: Sequence[Sequence[Toolpath | DrillOp]],
    lib: ToolLibrary,
    material: str,
    dialect: Dialect = GRBL,
    machine: Machine | None = None,
    n_max: float | None = None,
    ref_id: int | None = None,
    program_no: int = 1,
    names: Sequence[Sequence[str]] | None = None,
    dims: Sequence[Dimension] = (),
    tol_class: str = "m",
    warnings: Sequence[str] = (),
    part: Part | None = None,
    scale: float = 1.0,
    date: str | None = None,
) -> JobSheet:
    """Bağlamalar ve op'lardan iş föyü (§1–7). Güvensiz programda CamError."""
    raise NotImplementedError("SPEC 38: build_job_sheet")
