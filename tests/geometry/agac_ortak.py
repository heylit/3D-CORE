"""SPEC 18 testlerinin ortak yardımcıları (test dosyası değil; yalnız SPEC 18 testleri kullanır).

Testler SPEC 18 metninden, A2 arayüz önerisinden (`FaceRef`, `Part.names`, `Part.find`, `Part.face_refs`)
ve `sketch/model.py` arayüzünden yazıldı; uygulama kodu okunmadı. Uydurma geometri.

Arayüz bekleyen iki parça:
- `FaceRef` (A2) `geometry/part.py`'ye girene kadar `ref()` NotImplementedError fırlatır
  (yerelde "uygulanmamış").
- `SegLine.src` / `SegArc.src` (SPEC 18 S2) girene kadar `cizgi()` / `yay()` NotImplementedError fırlatır.
Böylece toplama aşaması düşmez; arayüzler birleşince testler değişmeden çalışır.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from sketch.model import Plane, SegArc, SegLine, SketchRegion

try:
    from geometry.part import FaceRef
except ImportError:  # A2 henüz birleşmedi
    FaceRef = None

REL = 1e-6  # hacim / alan göreli toleransı (SPEC 18)
KONUM = 1e-9  # konum toleransı, mm

# Dünya XY'si ile çakışan uv'li düzlemler: (u, v) = (x, y)
UST_20 = Plane((0, 0, 20), (0, 0, 1), (1, 0, 0))  # 100 × 60 × 20 bloğun üst yüz düzlemi
TABAN = Plane((0, 0, 0), (0, 0, 1), (1, 0, 0))  # z = 0


def ref(s: str):
    """ "cep:son" → FaceRef("cep", "son") (ilk ':'ten böler)."""
    if FaceRef is None:
        raise NotImplementedError("A2: geometry.part.FaceRef henüz yok")
    feature, name = s.split(":", 1)
    return FaceRef(feature, name)


def _src_var(cls) -> bool:
    return "src" in {f.name for f in dataclasses.fields(cls)}


def cizgi(p0, p1, src: str) -> SegLine:
    if not _src_var(SegLine):
        raise NotImplementedError("SPEC 18 S2: SegLine.src alanı henüz yok")
    return SegLine(p0, p1, src=src)


def yay(center, r: float, start, end, ccw: bool, src: str) -> SegArc:
    if not _src_var(SegArc):
        raise NotImplementedError("SPEC 18 S2: SegArc.src alanı henüz yok")
    return SegArc(center, r, start, end, ccw, src=src)


def dikdortgen(u0: float, v0: float, u1: float, v1: float) -> SketchRegion:
    """CCW dikdörtgen bölge; kenar kaynakları alt (v = v0), sag (u = u1), ust (v = v1), sol (u = u0)."""
    return SketchRegion(
        (
            cizgi((u0, v0), (u1, v0), "alt"),
            cizgi((u1, v0), (u1, v1), "sag"),
            cizgi((u1, v1), (u0, v1), "ust"),
            cizgi((u0, v1), (u0, v0), "sol"),
        )
    )


# --- Yüz sorguları (A2: index'ler PlanarFace.index / CylindricalFace.index ile aynı OCCT sırası) ---


def duzlemsel(part, i: int):
    """index'i i olan düzlemsel yüz; düzlemsel değilse AssertionError."""
    for f in part.planar_faces():
        if f.index == i:
            return f
    raise AssertionError(f"yüz {i} düzlemsel değil")


def silindirik(part, i: int):
    for f in part.cylindrical_faces():
        if f.index == i:
            return f
    raise AssertionError(f"yüz {i} silindirik değil")


def yuz_imzasi(part, i: int) -> tuple[float, float, float, float]:
    """Herhangi bir yüzün geometrik imzası: (alan, ağırlık merkezi x, y, z), yuvarlanmış."""
    import build123d as bd

    yuz = part.shape.faces()[i]
    c = yuz.center(bd.CenterOf.MASS)
    return (round(float(yuz.area), 6), round(c.X, 6), round(c.Y, 6), round(c.Z, 6))


def ad_imzalari(part) -> dict:
    """Her ad → çözüldüğü yüzlerin sıralı imzaları (index'ten bağımsız karşılaştırma için)."""
    return {r: tuple(sorted(yuz_imzasi(part, i) for i in idx)) for r, idx in part.names.items()}


def yerel_adlar(part) -> dict[str, tuple[int, ...]]:
    """Takım gövdesindeki yerel ad → index'ler (özellik kimliğine bakılmaz)."""
    return {r.name: idx for r, idx in part.names.items()}


def rapor(sonuc, kimlik: str):
    for r in sonuc.rapor:
        if r.kimlik == kimlik:
            return r
    raise AssertionError(f"raporda {kimlik} yok")


def yakin(a, b, tol: float = KONUM) -> bool:
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=0, atol=tol))
