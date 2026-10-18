"""
SPEC 62 — ISO 286-1 / 286-2 sınır sapmaları (sabit tablo). Girdi ve dönüş mm; tablo µm.

Çap aralığı "üstü … dahil" (Ø10 → 6–10, Ø10.001 → 10–18). İlk sürüm 1–500 mm; alanlar H6–H11, h6–h11, g6, f7,
js6, k6, m6, n6, p6. Tablo dışı alan, d ≤ 0, d > 500 → KomutError.
"""

from __future__ import annotations


def sapma(alan: str, d: float) -> tuple[float, float]:
    """(üst, alt) sapma, mm. Delikte (ES, EI), milde (es, ei)."""
    raise NotImplementedError("SPEC 62: sapma")


def hedef_cap(alan: str, d: float) -> float:
    """İşleme hedef çapı d + (üst + alt) / 2."""
    raise NotImplementedError("SPEC 62: hedef_cap")
