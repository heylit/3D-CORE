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

import math
from dataclasses import dataclass

from cam.model import CamError, CuttingData, LatheTool, Tool, _sonlu


@dataclass(frozen=True)
class SpindleFeed:
    """Devir n [dev/dk], ilerleme F [mm/dk], gerçek kesme hızı Vc [m/dk], diş/devir başı ilerleme f."""

    n: int
    F: float
    Vc: float
    f: float


def _pozitif(nerede: str, **degerler) -> None:
    """Her değer sonlu ve > 0 olmalı; aksi CamError."""
    _sonlu(nerede, **degerler)
    for ad, v in degerler.items():
        if v <= 0:
            raise CamError(f"{nerede}: {ad} pozitif olmalı ({ad}={v})")


def spindle_speed(Vc: float, D: float) -> float:
    """n = 1000·Vc / (π·D), yuvarlanmamış [dev/dk]."""
    _pozitif("Devir", Vc=Vc, D=D)
    return 1000 * Vc / (math.pi * D)


def cutting_speed(n: float, D: float) -> float:
    """Vc = π·D·n / 1000 [m/dk]."""
    _pozitif("Kesme hızı", n=n, D=D)
    return math.pi * D * n / 1000


def effective_diameter(tool: Tool, ap: float) -> float:
    """Kesme derinliği ap'deki etkin çap [mm]: D − 2r + 2·sqrt(r² − (r − ap)²), ap ≥ r veya r = 0 → D."""
    _pozitif(f"Takım '{tool.name}' etkin çap", ap=ap)
    r = tool.corner_r
    if r == 0 or ap >= r:
        return tool.D
    return tool.D - 2 * r + 2 * math.sqrt(r * r - (r - ap) ** 2)


def cutting_for(tool: Tool | LatheTool, material: str) -> CuttingData:
    """Takımın `material` için kesme verisi; yoksa CamError."""
    if material not in tool.cutting:
        raise CamError(f"Takım '{tool.name}' (T{tool.id}): '{material}' için kesme verisi yok")
    return tool.cutting[material]


def _devir(Vc: float, D: float, n_max: float | None) -> int:
    """Program devri: floor(n + 0.5), sonra n_max sınırı."""
    n = math.floor(spindle_speed(Vc, D) + 0.5)
    if n_max is not None:
        _pozitif("Devir sınırı", n_max=n_max)
        n = min(n, math.floor(n_max))
    if n < 1:
        raise CamError(f"Devir 1 dev/dk'dan küçük çıktı (Vc={Vc}, D={D}, n_max={n_max})")
    return n


def milling(tool: Tool, material: str, n_max: float | None = None, ap: float | None = None) -> SpindleFeed:
    """Freze devri ve ilerlemesi; ap verilirse etkin çapla."""
    if tool.flutes is None:
        raise CamError(f"Takım '{tool.name}' (T{tool.id}): diş sayısı yok, ilerleme hesaplanamaz")
    c = cutting_for(tool, material)
    D = tool.D if ap is None else effective_diameter(tool, ap)
    n = _devir(c.Vc, D, n_max)
    return SpindleFeed(n=n, F=n * tool.flutes * c.fz, Vc=cutting_speed(n, D), f=c.fz)


def turning(tool: LatheTool, material: str, D: float, n_max: float | None = None) -> SpindleFeed:
    """Torna sabit devir: işlenen çap D'de devir ve ilerleme."""
    c = cutting_for(tool, material)
    n = _devir(c.Vc, D, n_max)
    return SpindleFeed(n=n, F=n * c.fn, Vc=cutting_speed(n, D), f=c.fn)


def css(tool: LatheTool, material: str, n_max: float) -> tuple[float, int]:
    """G96 sabit kesme hızı ve G50 devir üst sınırı: (Vc, n_max)."""
    c = cutting_for(tool, material)
    if n_max is None:
        raise CamError(f"Torna takımı '{tool.name}': G96'da devir üst sınırı (G50) zorunlu")
    _pozitif("G50 devir sınırı", n_max=n_max)
    return c.Vc, math.floor(n_max)


def mrr_milling(ap: float, ae: float, F: float) -> float:
    """Q = ap·ae·F / 1000 [cm³/dk]."""
    _pozitif("Talaş debisi", ap=ap, ae=ae, F=F)
    return ap * ae * F / 1000


def mrr_turning(Vc: float, ap: float, fn: float) -> float:
    """Q = Vc·ap·fn [cm³/dk]."""
    _pozitif("Talaş debisi", Vc=Vc, ap=ap, fn=fn)
    return Vc * ap * fn
