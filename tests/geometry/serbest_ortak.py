"""SPEC 65a testlerinin ortak yardımcıları (test dosyası değil; yalnız 65a testleri kullanır).

Testler SPEC 65a metninden (Teori, Arayüz, Kabul kriterleri) ve arayüzden (`geometry/agac.py` Loft / Sweep /
BSplineYuzey, `geometry/serbest.py` imzaları) yazıldı; uygulama gövdeleri okunmadı. Uydurma geometri.

Varsayımlar:
- Hatalar `geometry.part.GeometryError` (SPEC metnindeki ModelError'ın geometri paketindeki karşılığı).
- Nokta ağı `noktalar[i][j] = (x_i, y_j, z)`: i satırı x'i, j sütunu y'yi artırır; bu sırada yüzey normali +z
  tarafına bakar (∂S/∂u × ∂S/∂v ≈ x × y = z). "alt" = normalin tersi = düşük z tarafı.
"""

from __future__ import annotations

import math

import numpy as np

from sketch.model import Plane, SegArc, SegLine, SketchRegion

REL = 1e-6  # K1 / K3 hacim göreli toleransı
TABAN = Plane((0, 0, 0), (0, 0, 1), (1, 0, 0))  # z = 0, uv = dünya xy


def duzlem_z(z: float) -> Plane:
    """z = sabit düzlem, uv = dünya xy."""
    return Plane((0, 0, z), (0, 0, 1), (1, 0, 0))


def daire(r: float, cu: float = 0.0, cv: float = 0.0) -> SketchRegion:
    """Tam daire bölge (start = end), CCW."""
    s = (cu + r, cv)
    return SketchRegion((SegArc((cu, cv), r, s, s, True),))


def kare(a: float, cu: float = 0.0, cv: float = 0.0) -> SketchRegion:
    """Merkezi (cu, cv), kenarı a olan CCW kare."""
    h = a / 2
    p = [(cu - h, cv - h), (cu + h, cv - h), (cu + h, cv + h), (cu - h, cv + h)]
    return SketchRegion(tuple(SegLine(p[i], p[(i + 1) % 4]) for i in range(4)))


def acik_profil(a: float = 10.0) -> SketchRegion:
    """Kapanmayan üç kenar (dördüncü kenar yok)."""
    p = [(0.0, 0.0), (a, 0.0), (a, a), (0.0, a)]
    return SketchRegion(tuple(SegLine(p[i], p[i + 1]) for i in range(3)))


def paraboloid_agi(n: int = 7, yari: float = 30.0, cx: float = 0.0, cy: float = 0.0, z0: float = 0.0):
    """z = z0 + ((x−cx)² + (y−cy)²)/200, x − cx, y − cy ∈ [−yari, yari], n × n nokta (K5)."""
    xs = np.linspace(-yari, yari, n)
    return tuple(
        tuple((float(cx + x), float(cy + y), float(z0 + (x * x + y * y) / 200.0)) for y in xs) for x in xs
    )


def eyer_agi(n: int = 7, yari: float = 30.0):
    """z = (x² − y²)/20: merkezde iki yönde de eğrilik yarıçapı 10 mm (iki taraf da içbükey)."""
    xs = np.linspace(-yari, yari, n)
    return tuple(tuple((float(x), float(y), float((x * x - y * y) / 20.0)) for y in xs) for x in xs)


def rapor(sonuc, kimlik: str):
    for r in sonuc.rapor:
        if r.kimlik == kimlik:
            return r
    raise AssertionError(f"raporda {kimlik} yok")


def yuzler(part, kimlik: str, ad: str) -> list:
    """FaceRef(kimlik, ad)'ın çözüldüğü build123d yüzleri."""
    from geometry.part import FaceRef

    idx = part.find(FaceRef(kimlik, ad))
    hepsi = part.shape.faces()
    return [hepsi[i] for i in idx]


def sessiz_gecmez(ag, agac, kimlik: str) -> None:
    """K8: kurulum GeometryError fırlatır ya da özellik "hata" / "atlandi" olur; sessiz geçemez."""
    from geometry.part import GeometryError

    try:
        s = ag.insa(agac)
    except GeometryError:
        return
    assert rapor(s, kimlik).durum in ("hata", "atlandi"), f"{kimlik} sessizce geçti"
    assert s.basarili is False


def kesik_koni(r1: float, r2: float, h: float) -> float:
    return math.pi * h / 3 * (r1 * r1 + r1 * r2 + r2 * r2)
