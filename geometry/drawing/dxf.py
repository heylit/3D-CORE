"""DXF R12 (AC1009) ASCII yazıcı ve okuyucu (SPEC 16). Saf Python.

DXF bir grup kodu / değer çifti dizisidir: her çift iki satır ("  10" / "12.5"). Bölümler:
HEADER ($ACADVER = AC1009), TABLES (LTYPE, LAYER, STYLE), ENTITIES (LINE, CIRCLE, ARC, TEXT).
Çoklu çizgi ve tarama LINE dizisi olarak yazılır. Sayılar repr ile (en kısa tam gidiş-dönüş) yazılır.
Kaynak: Autodesk, DXF Reference (R12).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from geometry.drawing.types import Arc2D, Entity, Line2D, Polyline2D, Sheet, Text2D
from geometry.part import GeometryError

SURUM = "AC1009"
# ad -> (açıklama, desen: pozitif çizgi, negatif boşluk, mm)
CIZGI_TIPLERI = {
    "CONTINUOUS": ("Solid line", []),
    "HIDDEN": ("Hidden __ __ __", [3.0, -1.5]),
    "CENTER": ("Center ____ _ ____", [12.0, -3.0, 2.0, -3.0]),
}
# katman -> (renk, çizgi tipi)
KATMANLAR = {
    "GORUNUR": (7, "CONTINUOUS"),
    "GIZLI": (1, "HIDDEN"),
    "EKSEN": (5, "CENTER"),
    "TARAMA": (8, "CONTINUOUS"),
    "OLCU": (3, "CONTINUOUS"),
}
CAP = "Ø"
CAP_DXF = "%%c"  # DXF'te çap işareti kontrol kodu


def _sayi(x: float) -> str:
    x = float(x)
    if not math.isfinite(x):
        raise GeometryError(f"DXF: sonlu olmayan sayı ({x})")
    return repr(x)


def _tablolar() -> list[tuple[int, str]]:
    g: list[tuple[int, str]] = [(0, "SECTION"), (2, "TABLES")]
    g += [(0, "TABLE"), (2, "LTYPE"), (70, str(len(CIZGI_TIPLERI)))]
    for ad, (aciklama, desen) in CIZGI_TIPLERI.items():
        g += [(0, "LTYPE"), (2, ad), (70, "0"), (3, aciklama), (72, "65"), (73, str(len(desen)))]
        g += [(40, _sayi(sum(abs(x) for x in desen)))]
        g += [(49, _sayi(x)) for x in desen]
    g += [(0, "ENDTAB")]
    g += [(0, "TABLE"), (2, "LAYER"), (70, str(len(KATMANLAR) + 1))]
    for ad, (renk, tip) in {"0": (7, "CONTINUOUS"), **KATMANLAR}.items():
        g += [(0, "LAYER"), (2, ad), (70, "0"), (62, str(renk)), (6, tip)]
    g += [(0, "ENDTAB")]
    g += [(0, "TABLE"), (2, "STYLE"), (70, "1")]
    g += [(0, "STYLE"), (2, "STANDARD"), (70, "0"), (40, "0.0"), (41, "1.0"), (50, "0.0"), (71, "0")]
    g += [(42, "2.5"), (3, "txt"), (4, "")]
    g += [(0, "ENDTAB"), (0, "ENDSEC")]
    return g


def _varlik(e: Entity) -> list[tuple[int, str]]:
    if isinstance(e, Line2D):
        return [
            (0, "LINE"), (8, e.layer),
            (10, _sayi(e.p0[0])), (20, _sayi(e.p0[1])), (30, "0.0"),
            (11, _sayi(e.p1[0])), (21, _sayi(e.p1[1])), (31, "0.0"),
        ]  # fmt: skip
    if isinstance(e, Arc2D):
        merkez = [(10, _sayi(e.c[0])), (20, _sayi(e.c[1])), (30, "0.0"), (40, _sayi(e.r))]
        if e.a1 - e.a0 >= 360.0:
            return [(0, "CIRCLE"), (8, e.layer), *merkez]
        return [(0, "ARC"), (8, e.layer), *merkez, (50, _sayi(e.a0 % 360.0)), (51, _sayi(e.a1 % 360.0))]
    if isinstance(e, Polyline2D):
        P = np.asarray(e.P, dtype=float)
        return [g for a, b in zip(P[:-1], P[1:], strict=True) for g in _varlik(Line2D(a, b, e.layer))]
    if isinstance(e, Text2D):
        return [
            (0, "TEXT"), (8, e.layer),
            (10, _sayi(e.p[0])), (20, _sayi(e.p[1])), (30, "0.0"),
            (40, _sayi(e.h)), (1, e.text.replace(CAP, CAP_DXF)), (50, _sayi(e.angle)),
        ]  # fmt: skip
    raise GeometryError(f"DXF: bilinmeyen varlık {type(e).__name__}")


def write_dxf(sheet_or_entities: Sheet | list[Entity], path: str | Path) -> None:
    """Paftayı ya da varlık listesini DXF R12 ASCII olarak yazar."""
    if isinstance(sheet_or_entities, Sheet):
        varliklar = sheet_or_entities.entities()
    else:
        varliklar = list(sheet_or_entities)
    g: list[tuple[int, str]] = [(0, "SECTION"), (2, "HEADER"), (9, "$ACADVER"), (1, SURUM)]
    g += [(9, "$DWGCODEPAGE"), (3, "ANSI_1252"), (0, "ENDSEC")]
    g += _tablolar()
    g += [(0, "SECTION"), (2, "ENTITIES")]
    for e in varliklar:
        g += _varlik(e)
    g += [(0, "ENDSEC"), (0, "EOF")]
    metin = "".join(f"{kod:>3}\n{deger}\n" for kod, deger in g)
    try:
        Path(path).write_text(metin, encoding="cp1252", newline="\r\n")
    except (OSError, UnicodeEncodeError) as e:
        raise GeometryError(f"DXF yazılamadı: {path} ({e})") from e


# ---------- okuyucu ----------


def _ciftler(path: Path) -> list[tuple[int, str]]:
    if not path.is_file():
        raise GeometryError(f"DXF dosyası yok: {path}")
    try:
        satirlar = path.read_text(encoding="cp1252").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise GeometryError(f"DXF okunamadı: {path} ({e})") from e
    if len(satirlar) % 2:
        raise GeometryError("DXF bozuk: tek sayıda satır (grup kodu / değer çifti eksik)")
    out = []
    for i in range(0, len(satirlar), 2):
        try:
            kod = int(satirlar[i].strip())
        except ValueError as e:
            raise GeometryError(f"DXF bozuk: satır {i + 1} grup kodu değil ({satirlar[i]!r})") from e
        out.append((kod, satirlar[i + 1].strip()))
    return out


def _bolumler(ciftler: list[tuple[int, str]]) -> dict[str, list[tuple[int, str]]]:
    bolumler: dict[str, list[tuple[int, str]]] = {}
    i = 0
    while i < len(ciftler):
        if ciftler[i] == (0, "SECTION"):
            if i + 1 >= len(ciftler) or ciftler[i + 1][0] != 2:
                raise GeometryError("DXF bozuk: SECTION adı yok")
            ad, j = ciftler[i + 1][1], i + 2
            while j < len(ciftler) and ciftler[j] != (0, "ENDSEC"):
                j += 1
            if j == len(ciftler):
                raise GeometryError(f"DXF bozuk: {ad} bölümü kapanmıyor (ENDSEC yok)")
            bolumler[ad] = ciftler[i + 2 : j]
            i = j + 1
        elif ciftler[i] == (0, "EOF"):
            break
        else:
            i += 1
    return bolumler


def _f(kodlar: dict[int, str], kod: int, tur: str) -> float:
    if kod not in kodlar:
        raise GeometryError(f"DXF bozuk: {tur} varlığında grup kodu {kod} yok")
    try:
        x = float(kodlar[kod])
    except ValueError as e:
        raise GeometryError(f"DXF bozuk: {tur} grup kodu {kod} sayı değil ({kodlar[kod]!r})") from e
    if not math.isfinite(x):
        raise GeometryError(f"DXF bozuk: {tur} grup kodu {kod} sonlu değil")
    return x


def _oku_varlik(tur: str, kodlar: dict[int, str]) -> Entity:
    katman = kodlar.get(8, "0")
    if tur == "LINE":
        return Line2D(
            np.array([_f(kodlar, 10, tur), _f(kodlar, 20, tur)]),
            np.array([_f(kodlar, 11, tur), _f(kodlar, 21, tur)]),
            katman,  # type: ignore[arg-type]
        )
    if tur in ("CIRCLE", "ARC"):
        c = np.array([_f(kodlar, 10, tur), _f(kodlar, 20, tur)])
        r = _f(kodlar, 40, tur)
        if tur == "CIRCLE":
            return Arc2D(c, r, 0.0, 360.0, katman)  # type: ignore[arg-type]
        a0, a1 = _f(kodlar, 50, tur), _f(kodlar, 51, tur)
        if a1 <= a0:
            a1 += 360.0
        return Arc2D(c, r, a0, a1, katman)  # type: ignore[arg-type]
    if tur == "TEXT":
        return Text2D(
            np.array([_f(kodlar, 10, tur), _f(kodlar, 20, tur)]),
            kodlar.get(1, "").replace(CAP_DXF, CAP).replace(CAP_DXF.upper(), CAP),
            _f(kodlar, 40, tur),
            float(kodlar.get(50, "0")),
            katman,  # type: ignore[arg-type]
        )
    raise GeometryError(f"DXF: desteklenmeyen varlık '{tur}' (LINE, CIRCLE, ARC, TEXT)")


def read_dxf(path: str | Path) -> list[Entity]:
    """Sadece LINE, CIRCLE, ARC, TEXT alt kümesi."""
    bolumler = _bolumler(_ciftler(Path(path)))
    baslik = bolumler.get("HEADER", [])
    for i, (kod, deger) in enumerate(baslik):
        if (kod, deger) == (9, "$ACADVER"):
            surum = baslik[i + 1][1] if i + 1 < len(baslik) else ""
            if surum != SURUM:
                raise GeometryError(f"DXF: desteklenmeyen sürüm {surum!r} (yalnızca {SURUM})")
    if "ENTITIES" not in bolumler:
        raise GeometryError("DXF bozuk: ENTITIES bölümü yok")
    out: list[Entity] = []
    tur: str | None = None
    kodlar: dict[int, str] = {}
    for kod, deger in bolumler["ENTITIES"] + [(0, "")]:
        if kod == 0:
            if tur is not None:
                out.append(_oku_varlik(tur, kodlar))
            tur, kodlar = (deger or None), {}
        else:
            kodlar[kod] = deger
    return out
