"""
SPEC 06 — Küresel uç iz (scallop) yüksekliği: düzlem, dışbükey ve içbükey silindir / küre.

Birimler: mm, açı rad. İskelet: gövdeler henüz yazılmadı.
"""

from __future__ import annotations


def scallop_flat(R: float, s: float) -> float:
    """Düzlemde h = R − √(R² − (s/2)²)."""
    raise NotImplementedError("SPEC 06: scallop_flat")


def stepover_flat(R: float, h: float) -> float:
    """Düzlemde ters formül s = 2√(2Rh − h²)."""
    raise NotImplementedError("SPEC 06: stepover_flat")


def scallop_curved(R: float, rho: float, alpha: float, convex: bool) -> float:
    """Eğrilik yarıçapı rho olan yüzeyde, merkezler arası açı alpha için sırt yüksekliği."""
    raise NotImplementedError("SPEC 06: scallop_curved")
