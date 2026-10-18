"""
İlerleme optimizasyonu: talaş incelmesi ve iş mili güç / tork sınırına göre F ayarı. SPEC 32.

Geometri değişmez; yalnız Move.feed değerleri yeniden hesaplanır. Yeni program yeniden simüle edilip
yükleri doğrulanır.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.gcode import DrillOp
from cam.kuvvet import KienzleMaterial, Load, Overload, SpindleLimits
from cam.model import CylinderStock, Stock, Toolpath
from cam.sim import Machine


def split_moves(
    ops: list[Toolpath | DrillOp], seg: float | None = None
) -> tuple[list[Toolpath | DrillOp], list[tuple[int, int | None]]]:
    """Kesme hareketlerini boyu ≤ seg bölütlere ayırır; her yeni (op, hareket) için özgün hareket indeksi."""
    raise NotImplementedError("SPEC 32")


@dataclass
class FeedChange:
    """reason ∈ {"inceltme", "guc", "tork", "en_cok", "ilerleme_siniri", "en_az", "hava", "degismedi"}."""

    op: int
    move: int
    F_old: float
    F_new: float
    reason: str


@dataclass
class FeedPlan:
    ops: list[Toolpath | DrillOp]
    changes: list[FeedChange]
    loads_before: list[Load]
    loads_after: list[Load]
    overloads_before: list[Overload]
    overloads_after: list[Overload]
    skipped: list[int]
    t_before: float
    t_after: float


def optimize_feed(
    ops: list[Toolpath | DrillOp],
    stock: Stock | CylinderStock,
    material: KienzleMaterial,
    limits: SpindleLimits,
    *,
    feed_max: float | None = None,
    seg: float | None = None,
    split: bool = False,
    air_feed: float | None = None,
    max_factor: float = 2.0,
    min_factor: float = 0.1,
    target_hex: float | None = None,
    resolution: float = 0.1,
    K: float = 1.0,
    cell: float | None = None,
    machine: Machine | None = None,
) -> FeedPlan:
    """Freze (simulate) veya torna (simulate_lathe) programının ilerlemesini ayarlar; girdi değişmez."""
    raise NotImplementedError("SPEC 32")
