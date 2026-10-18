"""Pafta yerleşimi, ISO 5456-2 birinci açı ("E" yöntemi) (SPEC 16).

Ön görünüş referanstır. Üst görünüş önün altına, soldan görünüş önün sağına, sağdan görünüş önün soluna
yerleşir; aralarda kağıt üzerinde g boşluk. Ön ve üst aynı u = x'i, ön ve yanlar aynı v = z'yi paylaşır.
Pafta koordinatı = k · görünüş koordinatı + öteleme.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np

from geometry.drawing.types import Entity, Line2D, PlacedView, Sheet, Text2D, View
from geometry.part import GeometryError, Part

ETIKET = 5.0  # mm, kesit çizgisi etiketi yazı boyu
KESIT_TASMA = 5.0  # mm (kağıt), kesit çizgisinin görünüşten taşma payı


def layout(views: list[View], scale: float = 1.0, gap: float = 20.0) -> Sheet:
    """Üst önün altına, sol önün sağına, sağ önün soluna; aralarda g boşluk."""
    if not (math.isfinite(scale) and scale > 0):
        raise GeometryError(f"ölçek > 0 olmalı (scale={scale})")
    if not (math.isfinite(gap) and gap >= 0):
        raise GeometryError(f"boşluk >= 0 olmalı (gap={gap})")
    yonler = [v.direction for v in views]
    if len(set(yonler)) != len(yonler):
        raise GeometryError(f"aynı yönden birden çok görünüş: {yonler}")
    bilinen = {"on", "ust", "sol", "sag"}
    if not set(yonler) <= bilinen:
        raise GeometryError(f"bilinmeyen görünüş yönü: {sorted(set(yonler) - bilinen)}")
    gor = {v.direction: v for v in views}
    if "on" not in gor:
        raise GeometryError("pafta için ön görünüş ('on') gerekli")
    k = scale
    on_lo, on_hi = gor["on"].bbox()
    ofs = {"on": np.zeros(2)}
    if "ust" in gor:
        _, hi = gor["ust"].bbox()
        ofs["ust"] = np.array([0.0, k * on_lo[1] - gap - k * hi[1]])
    if "sol" in gor:
        lo, _ = gor["sol"].bbox()
        ofs["sol"] = np.array([k * on_hi[0] + gap - k * lo[0], 0.0])
    if "sag" in gor:
        _, hi = gor["sag"].bbox()
        ofs["sag"] = np.array([k * on_lo[0] - gap - k * hi[0], 0.0])
    return Sheet(views=tuple(PlacedView(v, ofs[v.direction], k) for v in views))


# kesit yönü -> (kesit çizgisinin çizildiği görünüş, çizginin o görünüşteki ekseni: 0 = u sabit, 1 = v sabit,
#                 kesit konumunu o görünüş koordinatına çeviren işaret)
_KESIT_CIZGISI = {
    "on": [("ust", 1, 1.0)],  # y = y0 → üstte v = y0
    "ust": [("on", 1, 1.0)],  # z = z0 → önde v = z0
    "sol": [("on", 0, 1.0), ("ust", 0, 1.0)],  # x = x0 → önde / üstte u = x0
    "sag": [("on", 0, 1.0), ("ust", 0, 1.0)],
}


def _kesit_cizgisi(sheet: Sheet, direction: str, offset: float, name: str) -> list[Entity]:
    """Kesit düzlemini kesen görünüşe EKSEN katmanında çizgi ve iki uçta etiket (pafta koordinatı)."""
    yerler = {pv.view.direction: pv for pv in sheet.views}
    harf = name.split("-")[0] if "-" in name else name
    for hedef, sabit, isaret in _KESIT_CIZGISI[direction]:
        pv = yerler.get(hedef)
        if pv is None:
            continue
        lo, hi = pv.view.bbox()
        lo, hi = pv.scale * lo + pv.offset, pv.scale * hi + pv.offset
        w = pv.scale * isaret * offset + pv.offset[sabit]
        if sabit == 1:
            p0, p1 = np.array([lo[0] - KESIT_TASMA, w]), np.array([hi[0] + KESIT_TASMA, w])
        else:
            p0, p1 = np.array([w, lo[1] - KESIT_TASMA]), np.array([w, hi[1] + KESIT_TASMA])
        return [
            Line2D(p0, p1, "EKSEN"),
            Text2D(p0 + np.array([-ETIKET, 0.5]), harf, ETIKET, 0.0, "OLCU"),
            Text2D(p1 + np.array([0.5, 0.5]), harf, ETIKET, 0.0, "OLCU"),
        ]
    return []


def make_drawing(
    part: Part,
    views: tuple[str, ...] = ("on", "ust", "sol"),
    section: tuple[str, float] | None = None,
    scale: float = 1.0,
    dims: bool = True,
) -> Sheet:
    """Görünüşler (+ isteğe bağlı kesit ve ölçüler) ile pafta. Kesit, aynı yöndeki görünüşün yerine geçer."""
    from geometry.drawing.dimensions import basic_dimensions
    from geometry.drawing.views import project
    from geometry.drawing.views import section as kesit

    if not (math.isfinite(scale) and scale > 0):
        raise GeometryError(f"ölçek > 0 olmalı (scale={scale})")
    yonler = list(views)
    if section is not None and section[0] not in yonler:
        yonler.append(section[0])
    adlar = "A-A"
    gorunusler: list[View] = []
    for y in yonler:
        if section is not None and y == section[0]:
            gorunusler.append(kesit(part, y, section[1], name=adlar, s=3.0 / scale))
        else:
            gorunusler.append(project(part, y))
    if dims:
        olculer = basic_dimensions(part, gorunusler)
        gorunusler = [dataclasses.replace(v, dims=olculer.get(v.name, ())) for v in gorunusler]
    sheet = layout(gorunusler, scale=scale)
    if section is None:
        return sheet
    ekler = _kesit_cizgisi(sheet, section[0], section[1], adlar)
    pv = next(p for p in sheet.views if p.view.name == adlar)
    lo, hi = pv.view.bbox()
    lo, hi = pv.scale * lo + pv.offset, pv.scale * hi + pv.offset
    alt = 0.5 * (lo[0] + hi[0])
    ekler.append(Text2D(np.array([alt - ETIKET, lo[1] - 2.5 * ETIKET]), adlar, ETIKET, 0.0, "OLCU"))
    return dataclasses.replace(sheet, extras=tuple(ekler))
