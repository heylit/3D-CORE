"""
SPEC 53 — Girişim aday çiftleri için sınır kutusu ağacı (BVH).

Yaprak kutuları orta nokta bölmesiyle (en uzun eksende medyan) ikili ağaca dizilir. İki düğüm aday olur ancak
kutu boşluğu g = |max(0, lo_b − hi_a, lo_a − hi_b)| için g < esik_c veya g ≤ tol_d ise (SPEC 09 ölçütü).
Aday kümesi sort and sweep ile aynıdır; ağaç yalnız aramayı budar.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Bvh:
    lo: np.ndarray  # (n, 3) yaprak kutuları
    hi: np.ndarray

    @classmethod
    def build(cls, boxes) -> Bvh:
        """boxes: [(lo, hi), ...] eksen hizalı kutular."""
        raise NotImplementedError("SPEC 53")

    def pairs(self, esik_c: float, tol_d: float) -> list[tuple[int, int]]:
        """g < esik_c veya g ≤ tol_d olan çiftler (i < j), sıralı."""
        raise NotImplementedError("SPEC 53")
