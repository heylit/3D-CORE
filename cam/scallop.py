"""
SPEC 06 — Küresel uç iz (scallop) yüksekliği: düzlem, dışbükey ve içbükey silindir / küre.

Düzlemde komşu iki pasonun merkezleri s uzakta; eğri yüzeyde merkezler eğrilik merkezinden
c = ρ ± R uzakta ve aralarındaki açı α. Sırt, iki takım dairesinin açıortaydaki kesişimidir:
kosinüs teoremi t² − 2tc·cos(α/2) + c² − R² = 0.

Birimler: mm, açı rad.
"""

from __future__ import annotations

import math

from cam.model import CamError


def _sonlu(nerede: str, **degerler: float) -> None:
    for ad, v in degerler.items():
        if not math.isfinite(v):
            raise CamError(f"{nerede}: {ad} sonlu olmalı ({ad}={v})")


def scallop_flat(R: float, s: float) -> float:
    """Düzlemde h = R − √(R² − (s/2)²); küçük s için h ≈ s²/(8R)."""
    _sonlu("scallop_flat", R=R, s=s)
    if R <= 0:
        raise CamError(f"scallop_flat: R pozitif olmalı (R={R})")
    if not 0 <= s <= 2 * R:
        raise CamError(f"scallop_flat: 0 ≤ s ≤ 2R olmalı (s={s}, R={R})")
    return R - math.sqrt(R * R - (s / 2) ** 2)


def stepover_flat(R: float, h: float) -> float:
    """Düzlemde ters formül s = 2√(2Rh − h²)."""
    _sonlu("stepover_flat", R=R, h=h)
    if R <= 0:
        raise CamError(f"stepover_flat: R pozitif olmalı (R={R})")
    if not 0 < h <= R:
        raise CamError(f"stepover_flat: 0 < h ≤ R olmalı (h={h}, R={R})")
    return 2 * math.sqrt(2 * R * h - h * h)


def scallop_curved(R: float, rho: float, alpha: float, convex: bool) -> float:
    """Eğrilik yarıçapı rho olan yüzeyde, merkezler arası açı alpha için sırt yüksekliği.

    Dışbükey: c = ρ + R, h = c·cos(α/2) − √(R² − c²·sin²(α/2)) − ρ (yakın kesişim).
    İçbükey:  c = ρ − R, h = ρ − c·cos(α/2) − √(R² − c²·sin²(α/2)) (uzak kesişim).
    """
    _sonlu("scallop_curved", R=R, rho=rho, alpha=alpha)
    if R <= 0:
        raise CamError(f"scallop_curved: R pozitif olmalı (R={R})")
    if rho <= 0:
        raise CamError(f"scallop_curved: rho pozitif olmalı (rho={rho})")
    if alpha < 0:
        raise CamError(f"scallop_curved: alpha negatif olamaz (alpha={alpha})")
    if not convex and rho <= R:
        raise CamError(f"scallop_curved: içbükey yüzeyde rho > R olmalı (rho={rho}, R={R})")
    c = rho + R if convex else rho - R
    q2 = R * R - (c * math.sin(alpha / 2)) ** 2
    if q2 < 0:
        raise CamError(f"scallop_curved: komşu takım küreleri kesişmiyor (c·sin(α/2) > R, α={alpha})")
    q = math.sqrt(q2)
    if convex:
        return c * math.cos(alpha / 2) - q - rho
    return rho - c * math.cos(alpha / 2) - q


def scallop_torus(R: float, r_c: float, s: float) -> float:
    """SPEC 06b — torik uç, yatay düzlem: s ≤ 2(R − r_c) → 0; değilse r_c − √(r_c² − (s/2 − R + r_c)²)."""
    raise NotImplementedError("SPEC 06b: scallop_torus")


def scallop_cone(R: float, theta: float, s: float) -> float:
    """SPEC 06b — konik uç, yatay düzlem: h = (s/2)·cot θ; theta yarı açı [derece]."""
    raise NotImplementedError("SPEC 06b: scallop_cone")
