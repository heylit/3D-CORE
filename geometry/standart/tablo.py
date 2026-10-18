"""
SPEC 35 — ISO ölçü tabloları ve standart parça tanımları (saf Python, OCCT yok).

Kaynak: ISO 4762, ISO 4017, ISO 4032, ISO 7089, ISO 2338, ISO 15, ISO 273. Birimler: mm.
Bu modül geometry'nin OCCT'siz arayüz dosyasıdır: assy/oneri.py buradan okur.
"""

from __future__ import annotations

import math
import re

from geometry.part import GeometryError

TOL_GECIS = 1e-6  # mm: ISO 273 aralık uçlarında tolerans
TOL_BOY = 1e-9  # mm: L ≥ L_min − TOL_BOY

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
    if M not in ISO4762:
        raise GeometryError(f"Bilinmeyen vida ölçüsü: {M!r}")
    return float(M[1:])


def gecis_olcusu(d: float) -> str | None:
    """ISO 273 ince–kaba aralığına giren M; yoksa None."""
    for M, (ince, _, kaba) in ISO273.items():
        if ince - TOL_GECIS <= d <= kaba + TOL_GECIS:
            return M
    return None


def _vida_tablosu(seri: str) -> dict[str, tuple[float, float]]:
    """Seriye göre M → (L_min, L_maks)."""
    if seri == "4762":
        return {M: (r[4], r[5]) for M, r in ISO4762.items()}
    if seri == "4017":
        return {M: (r[2], r[3]) for M, r in ISO4017.items()}
    raise GeometryError(f"Bilinmeyen vida serisi: {seri!r} (4762 veya 4017)")


def vida_boyu(M: str, L_min: float, seri: str = "4762") -> float | None:
    """Seri ∩ aralıkta L ≥ L_min olan en küçük boy (seri "4762" veya "4017"); yoksa None."""
    tablo = _vida_tablosu(seri)
    if M not in tablo:
        raise GeometryError(f"Bilinmeyen vida ölçüsü: {M!r}")
    alt, ust = tablo[M]
    for L in L_SERI_VIDA:
        if alt <= L <= ust and L >= L_min - TOL_BOY:
            return float(L)
    return None


_SAYI = r"(\d+(?:\.\d+)?)"
_DESEN = {
    "vida": re.compile(rf"ISO (4762|4017) (M\d+)x{_SAYI}"),
    "somun_pul": re.compile(r"ISO (4032|7089) (M\d+)"),
    "pim": re.compile(rf"ISO 2338 {_SAYI}x{_SAYI}"),
    "rulman": re.compile(r"ISO 15 (\d{4})"),
}


def _seride(L: float, seri: tuple[float, ...]) -> bool:
    return any(abs(L - v) <= TOL_BOY for v in seri)


def ayristir(tanim: str) -> tuple[str, dict]:
    """Kanonik tanım ("ISO 4762 M8x25" ...) → (standart, ölçüler). Bozuk / tablo dışı → GeometryError."""
    if not isinstance(tanim, str):
        raise GeometryError(f"Tanım metin olmalı ({tanim!r})")
    if m := _DESEN["vida"].fullmatch(tanim):
        std, M, L = m.group(1), m.group(2), float(m.group(3))
        alt, ust = _vida_tablosu(std).get(M, (math.inf, -math.inf))
        if M not in ISO4762:
            raise GeometryError(f"{tanim}: bilinmeyen ölçü {M}")
        if not (_seride(L, L_SERI_VIDA) and alt <= L <= ust):
            raise GeometryError(f"{tanim}: L={L:g} seride veya {alt:g}–{ust:g} aralığında değil")
        return std, {"M": M, "L": L}
    if m := _DESEN["somun_pul"].fullmatch(tanim):
        std, M = m.group(1), m.group(2)
        if M not in (ISO4032 if std == "4032" else ISO7089):
            raise GeometryError(f"{tanim}: bilinmeyen ölçü {M}")
        return std, {"M": M}
    if m := _DESEN["pim"].fullmatch(tanim):
        d, L = float(m.group(1)), float(m.group(2))
        if d not in ISO2338:
            raise GeometryError(f"{tanim}: bilinmeyen pim çapı {d:g}")
        alt, ust = ISO2338[d]
        if not (_seride(L, L_SERI_PIM) and alt <= L <= ust):
            raise GeometryError(f"{tanim}: L={L:g} pim serisinde veya {alt:g}–{ust:g} aralığında değil")
        return "2338", {"d": d, "L": L}
    if m := _DESEN["rulman"].fullmatch(tanim):
        kod = m.group(1)
        if kod not in ISO15:
            raise GeometryError(f"{tanim}: bilinmeyen rulman kodu {kod}")
        return "15", {"kod": kod}
    raise GeometryError(f"Tanınmayan standart parça tanımı: {tanim!r}")


def _yaz(x: float) -> str:
    """Sayı yazımı: tamsayı değerliyse ondalıksız (25.0 → "25", 2.5 → "2.5")."""
    return f"{float(x):g}"


def tanim(std: str, **olcu) -> str:
    """ayristir'ın tersi: tanim("4762", M="M8", L=25) → "ISO 4762 M8x25". Geçersiz → GeometryError."""
    try:
        if std in ("4762", "4017"):
            metin = f"ISO {std} {olcu['M']}x{_yaz(olcu['L'])}"
        elif std in ("4032", "7089"):
            metin = f"ISO {std} {olcu['M']}"
        elif std == "2338":
            metin = f"ISO 2338 {_yaz(olcu['d'])}x{_yaz(olcu['L'])}"
        elif std == "15":
            metin = f"ISO 15 {olcu['kod']}"
        else:
            raise GeometryError(f"Bilinmeyen standart: {std!r}")
    except KeyError as e:
        raise GeometryError(f"ISO {std}: eksik ölçü {e}") from e
    ayristir(metin)  # tablo / seri denetimi
    return metin


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
