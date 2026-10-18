"""
SPEC 62 — ISO 286-1 / 286-2 sınır sapmaları (sabit tablo). Girdi ve dönüş mm; tablo µm.

Çap aralığı "üstü … dahil" (Ø10 → 6–10, Ø10.001 → 10–18). İlk sürüm 1–500 mm; alanlar H6–H11, h6–h11, g6, f7,
js6, k6, m6, n6, p6. Tablo dışı alan, d ≤ 0, d > 500 → KomutError.

Delik H: EI = 0, ES = IT. Mil h: es = 0, ei = −IT. g, f: es temel sapma, ei = es − IT. k, m, n, p: ei temel
sapma, es = ei + IT. js: ± IT/2. Kaynak: ISO 286-1:2010 Tablo 1 (IT), Tablo 2 ve 3 (temel sapmalar).
"""

from __future__ import annotations

import math
import re

# Aralıkların üst sınırları [mm]: (0, 3], (3, 6], … (400, 500]
ARALIK = (3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500)

# Temel tolerans IT [µm], ISO 286-1 Tablo 1
IT = {
    6: (6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40),
    7: (10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63),
    8: (14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97),
    9: (25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155),
    10: (40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250),
    11: (60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400),
}

# Mil temel sapmaları [µm]: üst (es) — g, f; alt (ei) — k (IT4–IT7), m, n, p. ISO 286-1 Tablo 2
ES_MIL = {
    "g": (-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20),
    "f": (-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68),
}
EI_MIL = {
    "k": (0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5),
    "m": (2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23),
    "n": (4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40),
    "p": (6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68),
}

ALANLAR = frozenset(
    [f"H{i}" for i in range(6, 12)]
    + [f"h{i}" for i in range(6, 12)]
    + ["g6", "f7", "js6", "k6", "m6", "n6", "p6"]
)
_ALAN = re.compile(r"([A-Za-z]+)(\d+)")


def _hata(mesaj: str):
    from tezgah.komut import KomutError

    return KomutError(mesaj)


def _aralik(d: float) -> int:
    if isinstance(d, bool) or not isinstance(d, int | float) or not math.isfinite(d):
        raise _hata(f"Tolerans çapı sonlu bir sayı olmalı ({d!r})")
    if d <= 0:
        raise _hata(f"Tolerans çapı pozitif olmalı (Ø{d})")
    if d > ARALIK[-1]:
        raise _hata(f"ISO 286 tablosu 500 mm'ye kadar (Ø{d})")
    return next(i for i, ust in enumerate(ARALIK) if d <= ust)


def _sapma_um(alan: str, d: float) -> tuple[int, int]:
    if alan not in ALANLAR:
        raise _hata(f"Tolerans alanı tabloda yok: {alan!r} (bilinenler: {', '.join(sorted(ALANLAR))})")
    i = _aralik(d)
    harf, derece = _ALAN.fullmatch(alan).groups()
    it = IT[int(derece)][i]
    if harf == "H":
        return it, 0
    if harf == "h":
        return 0, -it
    if harf == "js":
        return it / 2, -it / 2
    if harf in ES_MIL:
        es = ES_MIL[harf][i]
        return es, es - it
    ei = EI_MIL[harf][i]
    return ei + it, ei


def sapma(alan: str, d: float) -> tuple[float, float]:
    """(üst, alt) sapma, mm. Delikte (ES, EI), milde (es, ei)."""
    ust, alt = _sapma_um(alan, d)
    return ust / 1000, alt / 1000


def hedef_cap(alan: str, d: float) -> float:
    """İşleme hedef çapı d + (üst + alt) / 2."""
    ust, alt = _sapma_um(alan, d)
    return d + (ust + alt) / 2000
