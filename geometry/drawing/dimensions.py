"""Temel ölçüler, ölçü metni ve ölçünün çizgi + metne açılması (SPEC 16, ISO 129-1 esası).

Temel ölçüler (her biri pafta üzerinde bir kez):
- ön görünüş: toplam genişlik (yatay) ve yükseklik (dikey),
- üst görünüş: toplam derinlik (dikey); görünen her tam çember için Ø ve merkez konumu
  (sınır kutusunun sol-alt köşesine göre yatay ve dikey; aynı değer bir kez).
"""

from __future__ import annotations

import math

import numpy as np

from geometry.drawing.types import Arc2D, Dimension, Entity, Line2D, Text2D, View
from geometry.part import GeometryError, Part

ARALIK = 10.0  # mm (görünüş koordinatı): ölçü çizgisinin parçaya / bir önceki ölçüye uzaklığı
YAZI = 3.5  # mm, kağıt üzerinde yazı boyu
OK = 3.0  # mm, kağıt üzerinde ok boyu
OK_ACI = 15.0  # derece, ok kanadı açısı
TASMA = 2.0  # mm, kağıt üzerinde yardımcı çizginin ölçü çizgisini geçme payı
TOL = 1e-6  # mm, aynı ölçü değeri sayılma toleransı


def format_value(value: float, diameter: bool = False) -> str:
    """0.01'e yuvarla, sondaki sıfırları at, ondalık virgül; çapta "Ø" öneki."""
    if not math.isfinite(value):
        raise GeometryError(f"ölçü değeri sonlu olmalı ({value})")
    metin = f"{round(value, 2):.2f}".rstrip("0").rstrip(".")
    if metin in ("-0", ""):
        metin = "0"
    metin = metin.replace(".", ",")
    return ("Ø" if diameter else "") + metin


def _gorunur_kutu(view: View) -> tuple[np.ndarray, np.ndarray]:
    from geometry.drawing.types import entities_bbox

    gorunur = [e for e in view.edges if e.layer == "GORUNUR"]
    if not gorunur:
        raise GeometryError(f"görünüş '{view.name}': görünen kenar yok")
    return entities_bbox(gorunur)


def _yatay(p1, p2, offset: float) -> Dimension:
    p1, p2 = np.asarray(p1, dtype=float), np.asarray(p2, dtype=float)
    v = abs(p2[0] - p1[0])
    return Dimension("yatay", p1, p2, offset, v, format_value(v))


def _dikey(p1, p2, offset: float) -> Dimension:
    p1, p2 = np.asarray(p1, dtype=float), np.asarray(p2, dtype=float)
    v = abs(p2[1] - p1[1])
    return Dimension("dikey", p1, p2, offset, v, format_value(v))


def _tam_cemberler(view: View) -> list[Arc2D]:
    return [
        e for e in view.edges if isinstance(e, Arc2D) and e.layer == "GORUNUR" and e.a1 - e.a0 >= 360.0 - 1e-9
    ]


def basic_dimensions(part: Part, views: list[View]) -> dict[str, tuple[Dimension, ...]]:
    """Görünüş adı -> temel ölçüler; her ölçü pafta üzerinde bir kez."""
    if part is None:
        raise GeometryError("basic_dimensions: parça yok")
    sonuc: dict[str, tuple[Dimension, ...]] = {v.name: () for v in views}
    on = next((v for v in views if v.direction == "on"), None)
    ust = next((v for v in views if v.direction == "ust"), None)
    if on is not None:
        lo, hi = _gorunur_kutu(on)
        sonuc[on.name] = (
            _yatay((lo[0], hi[1]), (hi[0], hi[1]), ARALIK),  # genişlik, üstte
            _dikey((lo[0], lo[1]), (lo[0], hi[1]), -ARALIK),  # yükseklik, solda
        )
    if ust is not None:
        lo, hi = _gorunur_kutu(ust)
        olculer = [_dikey((lo[0], lo[1]), (lo[0], hi[1]), -ARALIK)]  # derinlik, solda
        xler: list[float] = []
        yler: list[float] = []
        for e in sorted(_tam_cemberler(ust), key=lambda e: (e.c[0], e.c[1])):
            c = np.asarray(e.c, dtype=float)
            q = c + e.r * np.array([math.cos(math.pi / 4), math.sin(math.pi / 4)])
            olculer.append(Dimension("cap", c, q, 0.0, 2.0 * e.r, format_value(2.0 * e.r, diameter=True)))
            x, y = c[0] - lo[0], c[1] - lo[1]
            if x > TOL and all(abs(x - u) > TOL for u in xler):
                xler.append(x)
                olculer.append(_yatay((lo[0], lo[1]), (c[0], lo[1]), -ARALIK * len(xler)))  # altta
            if y > TOL and all(abs(y - u) > TOL for u in yler):
                yler.append(y)
                olculer.append(_dikey((hi[0], lo[1]), (hi[0], c[1]), ARALIK * len(yler)))  # sağda
        sonuc[ust.name] = tuple(olculer)
    return sonuc


# ---------- ölçünün çizime açılması (pafta koordinatı) ----------


def _ok(uc: np.ndarray, yon: np.ndarray) -> list[Line2D]:
    """Ucu `uc`'ta, `yon`e (birim) bakan açık ok: iki kısa çizgi."""
    out = []
    for isaret in (1.0, -1.0):
        a = math.radians(OK_ACI) * isaret
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        out.append(Line2D(uc, uc - OK * (R @ yon), "OLCU"))
    return out


def render_dimension(dim: Dimension, k: float, t: np.ndarray) -> list[Entity]:
    """Ölçüyü pafta koordinatında çizgi + ok + metne açar (p' = k·p + t)."""
    t = np.asarray(t, dtype=float)
    p1, p2 = k * np.asarray(dim.p1, dtype=float) + t, k * np.asarray(dim.p2, dtype=float) + t
    off = k * dim.offset
    if dim.kind == "cap":
        r = float(np.linalg.norm(p2 - p1))
        yon = (p2 - p1) / r
        dis = p2 + 2.0 * OK * yon
        return [
            Line2D(p1 - r * yon, dis, "OLCU"),
            *_ok(p2, yon),
            *_ok(p1 - r * yon, -yon),
            Text2D(dis + np.array([0.5, 0.5]), dim.text, YAZI, 0.0, "OLCU"),
        ]
    if dim.kind == "yatay":
        e = np.array([0.0, 1.0])  # ölçü çizgisini öteleme yönü
        a, b = np.array([p1[0], p1[1] + off]), np.array([p2[0], p1[1] + off])
        aci = 0.0
    elif dim.kind == "dikey":
        e = np.array([1.0, 0.0])
        a, b = np.array([p1[0] + off, p1[1]]), np.array([p1[0] + off, p2[1]])
        aci = 90.0
    else:
        raise GeometryError(f"bilinmeyen ölçü türü: {dim.kind}")
    isaret = 1.0 if off >= 0 else -1.0
    out: list[Entity] = [
        Line2D(p1, a + isaret * TASMA * e, "OLCU"),
        Line2D(p2, b + isaret * TASMA * e, "OLCU"),
        Line2D(a, b, "OLCU"),
    ]
    L = float(np.linalg.norm(b - a))
    if L > 0:
        yon = (b - a) / L
        out += _ok(b, yon) + _ok(a, -yon)
    orta = 0.5 * (a + b)
    if dim.kind == "yatay":
        yazi_p = orta + np.array([-0.3 * YAZI * len(dim.text) / 2, 1.0])
    else:
        yazi_p = orta + np.array([-1.0, -0.3 * YAZI * len(dim.text) / 2])
    out.append(Text2D(yazi_p, dim.text, YAZI, aci, "OLCU"))
    return out
