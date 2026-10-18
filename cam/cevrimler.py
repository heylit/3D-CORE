"""
Punta, havşa (pah) ve kılavuz çevrimleri (SPEC 04b): G82 ve G84.

Delik kaydından (`geometry.part.Hole`, SPEC 23) op üretir; derinlik, ilerleme ve devir analitik formüllerden:
    punta   h_s = (d_s / 2) · cot(σ / 2)
    havşa   h_c = (D_h − d_t) / 2 · cot(α / 2)
    kılavuz h_t = t_d + lead · P,   F = S · P  (S = round(rpm); F yuvarlanmadan yazılabilmeli)
Kanonik açılım (SPEC 04 tanımlarıyla):
    G82: G0 (x, y, z_akım) -> G0 (x, y, r) -> G1 (x, y, z) F -> [bekle w] -> G0 (x, y, z_dön)
    G84: G0 (x, y, z_akım) -> G0 (x, y, r) -> G1 (x, y, z) F -> G1 (x, y, r) F -> G0 (x, y, z_dön)
Kaynak: Smid, CNC Programming Handbook, Bölüm 22; Fanuc 0i-MF Operator's Manual (B-64604EN), "Rigid tapping";
ISO 8830 (kılavuz giriş pahı); Machinery's Handbook, "Tapping", "Countersinks".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cam.gcode.dialect import GRBL, Dialect
from cam.model import Tool, Toolpath

if TYPE_CHECKING:
    from geometry.part import Hole

R_CLEAR = 2.0  # mm, R düzleminin delik üst yüzünden yüksekliği (varsayılan)
DWELL = 0.2  # s, punta ve havşada dipte bekleme (varsayılan)


# ---------------------------------------------------------------- hesap


def spot_depth(tool: Tool, d_s: float) -> float:
    """Punta derinliği h_s = (d_s / 2) · cot(σ / 2); σ = tool.tip_angle."""
    raise NotImplementedError("SPEC 04b: spot_depth")


def chamfer_depth(tool: Tool, csk_d: float, csk_angle: float, d: float) -> float:
    """Havşa derinliği h_c = (csk_d − tip_d) / 2 · cot(α / 2); takım açısı havşa açısına eşit olmalı."""
    raise NotImplementedError("SPEC 04b: chamfer_depth")


def tap_depth(tool: Tool, thread_depth: float) -> float:
    """Kılavuz ucu derinliği h_t = t_d + lead · pitch."""
    raise NotImplementedError("SPEC 04b: tap_depth")


def tap_feed(rpm: float, pitch: float, feed_decimals: int = 1) -> float:
    """Kılavuz ilerlemesi F = S · P (S = round(rpm)); feed_decimals basamakla tam yazılamıyorsa CamError."""
    raise NotImplementedError("SPEC 04b: tap_feed")


def tap_rpm(n: float, pitch: float, feed_decimals: int = 1) -> int:
    """n'yi aşmayan ve S · P · 10^fd tam sayı olan en büyük S (S ≥ 1 yoksa CamError)."""
    raise NotImplementedError("SPEC 04b: tap_rpm")


# ---------------------------------------------------------------- op'lar


@dataclass
class DwellDrillOp:
    """G82: dipte beklemeli delme (punta, havşa). dwell saniye, 1 ms'nin katı."""

    name: str
    tool: Tool
    rpm: float
    start: tuple[float, float, float]
    holes: list[tuple[float, float]]
    z: float
    r: float
    feed: float
    dwell: float
    retract: str = "G98"
    kind: str = "G82"

    def validate(self) -> None:
        raise NotImplementedError("SPEC 04b: DwellDrillOp.validate")

    def to_toolpath(self, dialect: Dialect = GRBL) -> Toolpath:
        """Kanonik açılım (G81'inkiyle aynı hareketler; bekleme yolda temsil edilmez)."""
        raise NotImplementedError("SPEC 04b: DwellDrillOp.to_toolpath")


@dataclass
class TapOp:
    """G84: rijit kılavuz. İlerleme takımın hatvesinden türetilir: F = S · P."""

    name: str
    tool: Tool
    rpm: float
    start: tuple[float, float, float]
    holes: list[tuple[float, float]]
    z: float
    r: float
    retract: str = "G98"
    feed_decimals: int = 1
    kind: str = "G84"

    @property
    def feed(self) -> float:
        raise NotImplementedError("SPEC 04b: TapOp.feed")

    def validate(self) -> None:
        raise NotImplementedError("SPEC 04b: TapOp.validate")

    def to_toolpath(self, dialect: Dialect = GRBL) -> Toolpath:
        """G84 kanonik açılımı: aşağı G1, yukarı G1 (aynı F), sonra G0 dönüş."""
        raise NotImplementedError("SPEC 04b: TapOp.to_toolpath")


# ---------------------------------------------------------------- delik kaydından


def spot_ops(
    holes: list[Hole],
    tool: Tool,
    rpm: float,
    feed: float,
    start: tuple[float, float, float],
    d_s: float | None = None,
    dwell: float = DWELL,
    name: str = "punta",
    r_clear: float = R_CLEAR,
    retract: str = "G98",
) -> list[DwellDrillOp]:
    """Punta op'ları; d_s=None → her delik için Hole.d. (z_top, h) ile gruplanır, sıra korunur."""
    raise NotImplementedError("SPEC 04b: spot_ops")


def chamfer_ops(
    holes: list[Hole],
    tool: Tool,
    rpm: float,
    feed: float,
    start: tuple[float, float, float],
    dwell: float = DWELL,
    name: str = "havsa",
    r_clear: float = R_CLEAR,
    retract: str = "G98",
) -> list[DwellDrillOp]:
    """Havşa op'ları; havşasız delik → CamError."""
    raise NotImplementedError("SPEC 04b: chamfer_ops")


def tap_ops(
    holes: list[Hole],
    tool: Tool,
    rpm: float,
    start: tuple[float, float, float],
    feed_decimals: int = 1,
    name: str = "kilavuz",
    r_clear: float = R_CLEAR,
    retract: str = "G98",
) -> list[TapOp]:
    """Kılavuz op'ları; dişsiz delik, çap / hatve uyuşmazlığı, kör delikte h_t > depth → CamError."""
    raise NotImplementedError("SPEC 04b: tap_ops")
