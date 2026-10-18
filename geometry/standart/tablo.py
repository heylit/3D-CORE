"""
SPEC 35 — ISO ölçü tabloları ve standart parça tanımları (saf Python, OCCT yok).

Kaynak: ISO 4762, ISO 4017, ISO 4032, ISO 7089, ISO 2338, ISO 15, ISO 273. Birimler: mm.
Bu modül geometry'nin OCCT'siz arayüz dosyasıdır: assy/oneri.py buradan okur.
"""

from __future__ import annotations

from geometry.part import GeometryError

# ISO 4762 imbus vida: (d_k, k, s, t, L_min, L_maks)
ISO4762: dict[str, tuple[float, float, float, float, float, float]] = {
    "M3": (5.5, 3.0, 2.5, 1.3, 5.0, 30.0),
    "M4": (7.0, 4.0, 3.0, 2.0, 6.0, 40.0),
    "M5": (8.5, 5.0, 4.0, 2.5, 8.0, 50.0),
    "M6": (10.0, 6.0, 5.0, 3.0, 10.0, 60.0),
    "M8": (13.0, 8.0, 6.0, 4.0, 12.0, 80.0),
    "M10": (16.0, 10.0, 8.0, 5.0, 16.0, 100.0),
    "M12": (18.0, 12.0, 10.0, 6.0, 20.0, 120.0),
    "M14": (21.0, 14.0, 12.0, 7.0, 25.0, 140.0),
    "M16": (24.0, 16.0, 14.0, 8.0, 25.0, 160.0),
    "M20": (30.0, 20.0, 17.0, 10.0, 30.0, 200.0),
    "M24": (36.0, 24.0, 19.0, 12.0, 40.0, 200.0),
}

# ISO 4017 altıgen civata: (s, k, L_min, L_maks)
ISO4017: dict[str, tuple[float, float, float, float]] = {
    "M3": (5.5, 2.0, 6.0, 30.0),
    "M4": (7.0, 2.8, 8.0, 40.0),
    "M5": (8.0, 3.5, 10.0, 50.0),
    "M6": (10.0, 4.0, 12.0, 60.0),
    "M8": (13.0, 5.3, 16.0, 80.0),
    "M10": (16.0, 6.4, 20.0, 100.0),
    "M12": (18.0, 7.5, 25.0, 120.0),
    "M14": (21.0, 8.8, 30.0, 140.0),
    "M16": (24.0, 10.0, 30.0, 200.0),
    "M20": (30.0, 12.5, 40.0, 200.0),
    "M24": (36.0, 15.0, 50.0, 200.0),
}

# ISO 4032 altıgen somun: (s, m)
ISO4032: dict[str, tuple[float, float]] = {
    "M3": (5.5, 2.4),
    "M4": (7.0, 3.2),
    "M5": (8.0, 4.7),
    "M6": (10.0, 5.2),
    "M8": (13.0, 6.8),
    "M10": (16.0, 8.4),
    "M12": (18.0, 10.8),
    "M14": (21.0, 12.8),
    "M16": (24.0, 14.8),
    "M20": (30.0, 18.0),
    "M24": (36.0, 21.5),
}

# ISO 7089 pul, normal seri: (d1, d2, h)
ISO7089: dict[str, tuple[float, float, float]] = {
    "M3": (3.2, 7.0, 0.5),
    "M4": (4.3, 9.0, 0.8),
    "M5": (5.3, 10.0, 1.0),
    "M6": (6.4, 12.0, 1.6),
    "M8": (8.4, 16.0, 1.6),
    "M10": (10.5, 20.0, 2.0),
    "M12": (13.0, 24.0, 2.5),
    "M14": (15.0, 28.0, 2.5),
    "M16": (17.0, 30.0, 3.0),
    "M20": (21.0, 37.0, 3.0),
    "M24": (25.0, 44.0, 4.0),
}

# ISO 273 geçiş delikleri: (ince, orta, kaba)
ISO273: dict[str, tuple[float, float, float]] = {
    "M3": (3.2, 3.4, 3.6),
    "M4": (4.3, 4.5, 4.8),
    "M5": (5.3, 5.5, 5.8),
    "M6": (6.4, 6.6, 7.0),
    "M8": (8.4, 9.0, 10.0),
    "M10": (10.5, 11.0, 12.0),
    "M12": (13.0, 13.5, 14.5),
    "M14": (15.0, 15.5, 16.5),
    "M16": (17.0, 17.5, 18.5),
    "M20": (21.0, 22.0, 24.0),
    "M24": (25.0, 26.0, 28.0),
}

# ISO 2338 silindirik pim: d -> (L_min, L_maks)
ISO2338: dict[float, tuple[float, float]] = {
    2.0: (6.0, 20.0),
    2.5: (6.0, 24.0),
    3.0: (8.0, 30.0),
    4.0: (8.0, 40.0),
    5.0: (10.0, 50.0),
    6.0: (12.0, 60.0),
    8.0: (14.0, 80.0),
    10.0: (18.0, 95.0),
    12.0: (22.0, 140.0),
    16.0: (26.0, 180.0),
    20.0: (35.0, 200.0),
}

# ISO 15 sabit bilyalı rulman: kod -> (d, D, B)
ISO15: dict[str, tuple[float, float, float]] = {
    "6000": (10.0, 26.0, 8.0),
    "6001": (12.0, 28.0, 8.0),
    "6002": (15.0, 32.0, 9.0),
    "6003": (17.0, 35.0, 10.0),
    "6004": (20.0, 42.0, 12.0),
    "6005": (25.0, 47.0, 12.0),
    "6006": (30.0, 55.0, 13.0),
    "6007": (35.0, 62.0, 14.0),
    "6008": (40.0, 68.0, 15.0),
    "6200": (10.0, 30.0, 9.0),
    "6201": (12.0, 32.0, 10.0),
    "6202": (15.0, 35.0, 11.0),
    "6203": (17.0, 40.0, 12.0),
    "6204": (20.0, 47.0, 14.0),
    "6205": (25.0, 52.0, 15.0),
    "6206": (30.0, 62.0, 16.0),
    "6207": (35.0, 72.0, 17.0),
    "6208": (40.0, 80.0, 18.0),
}

# Kaba hatve P [mm]: SPEC 23 THREADS_COARSE ile aynı (geometry.holes OCCT ister; bu OCCT'siz kopya)
P_KABA: dict[str, float] = {
    "M3": 0.5,
    "M4": 0.7,
    "M5": 0.8,
    "M6": 1.0,
    "M8": 1.25,
    "M10": 1.5,
    "M12": 1.75,
    "M14": 2.0,
    "M16": 2.0,
    "M20": 2.5,
    "M24": 3.0,
}

# Vida / civata tercihli boy serisi (ISO 4762 ve 4017 ortak)
L_SERI_VIDA: tuple[float, ...] = (
    5, 6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100,
    110, 120, 130, 140, 150, 160, 180, 200,
)  # fmt: skip

# ISO 2338 pim boy serisi
L_SERI_PIM: tuple[float, ...] = (
    4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 35, 40, 45, 50, 55, 60,
    65, 70, 75, 80, 85, 90, 95, 100, 120, 140, 160, 180, 200,
)  # fmt: skip


def boyut(M: str) -> float:
    """M boyutu: "M8" → 8.0; tabloda yoksa GeometryError."""
    raise NotImplementedError("SPEC 35")


def gecis_olcusu(d: float) -> str | None:
    """ISO 273 ince–kaba aralığına giren M; yoksa None."""
    raise NotImplementedError("SPEC 35")


def vida_boyu(M: str, L_min: float, seri: str = "4762") -> float | None:
    """Seri ∩ aralıkta L ≥ L_min olan en küçük boy (seri "4762" veya "4017"); yoksa None."""
    raise NotImplementedError("SPEC 35")


def ayristir(tanim: str) -> tuple[str, dict]:
    """Kanonik tanım ("ISO 4762 M8x25" ...) → (standart, ölçüler). Bozuk / tablo dışı → GeometryError."""
    raise NotImplementedError("SPEC 35")


def tanim(std: str, **olcu) -> str:
    """ayristir'ın tersi: tanim("4762", M="M8", L=25) → "ISO 4762 M8x25"."""
    raise NotImplementedError("SPEC 35")


__all__ = [
    "GeometryError",
    "ISO15",
    "ISO273",
    "ISO2338",
    "ISO4017",
    "ISO4032",
    "ISO4762",
    "ISO7089",
    "L_SERI_PIM",
    "L_SERI_VIDA",
    "P_KABA",
    "ayristir",
    "boyut",
    "gecis_olcusu",
    "tanim",
    "vida_boyu",
]
