"""
SPEC 18 — Desen ve ayna dönüşümleri, delik kaydının dönüştürülmesi.

`Donusum` 4 × 4 homojen matristir (numpy). Doğrusal: p_ij = p + i·s₁·e₁ + j·s₂·e₂. Dairesel: eksen etrafında
φ_k = k · aci / n (aci = 360°), aci < 360° ise φ_k = k · aci / (n − 1). Ayna (nokta q, birim normal m):
p' = p − 2((p − q)·m) m. Listelerin ilk elemanı birim dönüşümdür (asıl). Birimler: mm, derece.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from geometry.part import Hole

Donusum = np.ndarray  # (4, 4)


def dogrusal(
    n1: int,
    s1: float,
    e1: Sequence[float],
    n2: int = 1,
    s2: float = 0.0,
    e2: Sequence[float] | None = None,
) -> list[Donusum]:
    """n1 × n2 öteleme; sıra: j dış, i iç (önce e₁ boyunca bir satır, sonra e₂ yönünde sonraki satır).

    n < 1, sıfır yön, n > 1 iken sıfır adım → `GeometryError`.
    """
    raise NotImplementedError("SPEC 18: dogrusal")


def dairesel(eksen_p: Sequence[float], eksen_y: Sequence[float], n: int, aci: float = 360.0) -> list[Donusum]:
    """Eksen etrafında n dönme (sağ el, eksen_y yönünde). Hatalar: n < 1, sıfır eksen, aci ∉ (0, 360]."""
    raise NotImplementedError("SPEC 18: dairesel")


def ayna(q: Sequence[float], m: Sequence[float]) -> Donusum:
    """q noktasından geçen, normali m olan düzleme göre yansıma. |m| = 0 → `GeometryError`."""
    raise NotImplementedError("SPEC 18: ayna")


def donustur_hole(hole: Hole, T: Donusum) -> Hole:
    """origin' = T(origin), axis' = R(axis) (R: T'nin dönme / yansıma kısmı); diğer alanlar aynı."""
    raise NotImplementedError("SPEC 18: donustur_hole")
