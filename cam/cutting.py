"""
Kesme verisinden devir ve ilerleme (freze, torna). SPEC 14.

Freze: n = 1000·Vc / (π·D) [dev/dk], önce tam sayıya yuvarlanır (floor(x + 0.5)), sonra n_max sınırı;
F = n·z·fz [mm/dk] yuvarlanmış devirden. Gerçek kesme hızı Vc = π·D·n / 1000.
Etkin çap (köşe radyüsü r, kesme derinliği ap < r): D_eff = D − 2r + 2·sqrt(r² − (r − ap)²).
Torna: n = round(1000·Vc / (π·D)), F = n·fn; G96'da devir üst sınırı (G50) zorunlu.
Talaş debisi: freze Q = ap·ae·F / 1000, torna Q = Vc·ap·fn [cm³/dk].
Kaynak: Sandvik Coromant, Metal cutting technical guide; Smid, CNC Programming Handbook, Bölüm 9.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import CuttingData, LatheTool, Tool


@dataclass(frozen=True)
class SpindleFeed:
    """Devir n [dev/dk], ilerleme F [mm/dk], gerçek kesme hızı Vc [m/dk], diş/devir başı ilerleme f."""

    n: int
    F: float
    Vc: float
    f: float


def spindle_speed(Vc: float, D: float) -> float:
    """n = 1000·Vc / (π·D), yuvarlanmamış [dev/dk]."""
    raise NotImplementedError


def cutting_speed(n: float, D: float) -> float:
    """Vc = π·D·n / 1000 [m/dk]."""
    raise NotImplementedError


def effective_diameter(tool: Tool, ap: float) -> float:
    """Kesme derinliği ap'deki etkin çap [mm]."""
    raise NotImplementedError


def cutting_for(tool: Tool | LatheTool, material: str) -> CuttingData:
    """Takımın `material` için kesme verisi; yoksa CamError."""
    raise NotImplementedError


def milling(tool: Tool, material: str, n_max: float | None = None, ap: float | None = None) -> SpindleFeed:
    """Freze devri ve ilerlemesi; ap verilirse etkin çapla."""
    raise NotImplementedError


def turning(tool: LatheTool, material: str, D: float, n_max: float | None = None) -> SpindleFeed:
    """Torna sabit devir: işlenen çap D'de devir ve ilerleme."""
    raise NotImplementedError


def css(tool: LatheTool, material: str, n_max: float) -> tuple[float, int]:
    """G96 sabit kesme hızı ve G50 devir üst sınırı: (Vc, n_max)."""
    raise NotImplementedError


def mrr_milling(ap: float, ae: float, F: float) -> float:
    """Q = ap·ae·F / 1000 [cm³/dk]."""
    raise NotImplementedError


def mrr_turning(Vc: float, ap: float, fn: float) -> float:
    """Q = Vc·ap·fn [cm³/dk]."""
    raise NotImplementedError
