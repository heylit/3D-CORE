"""
Takım ömrü: Taylor, birikimli aşınma (Palmgren–Miner) ve planlı takım değişimi. SPEC 59.

Taylor: Vc · T^n = C → T(Vc) = (C / Vc)^(1/n) [dk], m = 1/n.
Miner: D = Σ ∫ dt / T(Vc(t)); yalnız SPEC 32 `Load.kind == "kesme"` adımları sayılır.
Freze: Vc = π · D_eff · n / 1000, D_eff = effective_diameter(tool, ap) (SPEC 14).
Torna: r = |x|; G97 Vc = 2π r N / 1000, dt = ds / (f N); G96 r* = 1000 Vc₀ / (2π N_max) ayrımı (SPEC 22).
Öneri: k = floor(D_lim / D_parça); k = 0 → program içi değişim (at_op).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cam.kuvvet import Load
from cam.model import ToolLibrary
from cam.sim.simulate import SimResult
from malzeme.model import Malzeme, Taylor

D_LIM = 0.8  # varsayılan değiştirme sınırı (güvenlik payı)
DEGISIM_TURLERI = ("kenar", "kardes", "gerek_yok")


def tool_life(taylor: Taylor, Vc: float) -> float:
    """T(Vc) [dk]; Taylor.omur'un ince sarmalayıcısı. Vc ≤ 0 veya sonsuz → ModelError."""
    raise NotImplementedError


@dataclass(frozen=True)
class StepWear:
    """Adım başına kesme süresi t [dk], adımdaki hız aralığı [m/dk] ve aşınma katkısı D."""

    k: int
    op: int
    tool_id: int
    t: float
    Vc_min: float
    Vc_max: float
    D: float

    def to_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d: dict) -> StepWear:
        raise NotImplementedError


@dataclass(frozen=True)
class ToolWear:
    """Takım başına toplam: kesme süresi t_cut [dk], aşınma D, en yüksek Vc [m/dk], adımlar."""

    tool_id: int
    tool_material: str
    t_cut: float
    D: float
    Vc_max: float
    steps: tuple[StepWear, ...]

    def to_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d: dict) -> ToolWear:
        raise NotImplementedError


@dataclass(frozen=True)
class ChangeAdvice:
    """Takım değişimi önerisi. kind ∈ {"kenar", "kardes", "gerek_yok"};
    parts_per_edge None iken program içi değişim (at_op dolu)."""

    tool_id: int
    kind: str
    parts_per_edge: int | None
    at_op: int | None
    sister_id: int | None
    D_part: float

    def to_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d: dict) -> ChangeAdvice:
        raise NotImplementedError


def mill_wear(
    ops,
    result: SimResult,
    loads: list[Load],
    material: Malzeme,
    tool_materials: Mapping[int, str],
) -> list[ToolWear]:
    """Freze: adım başına sabit Vc ile D_i = duration_i / T(Vc_i).
    len(loads) ≠ len(result.steps) → CamError."""
    raise NotImplementedError


def turn_wear(
    ops,
    result,
    loads: list[Load],
    material: Malzeme,
    tool_materials: Mapping[int, str],
    rtol: float = 1e-6,
) -> list[ToolWear]:
    """Torna: çapla değişen Vc; adımlar r = r* ve x = 0'da bölünür, 8 noktalı Gauss–Legendre.
    G96 / G97 ayrımı Toolpath.css ve rpm'den."""
    raise NotImplementedError


def advise(
    wear: list[ToolWear], lib: ToolLibrary, parts: int = 1, D_lim: float = D_LIM
) -> list[ChangeAdvice]:
    """Planlı takım değişimi önerisi; 0 < D_lim ≤ 1, parts ≥ 1 tam sayı, aksi CamError."""
    raise NotImplementedError
