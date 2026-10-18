"""SVG 1.1 yazıcı (SPEC 16). Saf Python.

viewBox paftanın sınır kutusu + kenar payıdır. SVG'de y aşağı baktığı için y_svg = y_maks − y
(pafta y_maks → SVG 0). Her katman bir <g id="KATMAN">; çizgi tipi ve kalınlığı ISO 128-20'den.
"""

from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from geometry.drawing.types import Arc2D, Entity, Line2D, Polyline2D, Sheet, Text2D
from geometry.part import GeometryError

# katman -> (kalınlık mm, stroke-dasharray veya None)
STILLER = {
    "GORUNUR": (0.5, None),
    "GIZLI": (0.25, "3 1.5"),
    "EKSEN": (0.25, "12 3 2 3"),
    "TARAMA": (0.18, None),
    "OLCU": (0.18, None),
}


def _s(x: float) -> str:
    return repr(float(x))


def _eleman(e: Entity, ymax: float) -> str:
    def Y(y: float) -> float:
        return ymax - float(y)

    if isinstance(e, Line2D):
        return f'<line x1="{_s(e.p0[0])}" y1="{_s(Y(e.p0[1]))}" x2="{_s(e.p1[0])}" y2="{_s(Y(e.p1[1]))}"/>'
    if isinstance(e, Arc2D):
        if e.a1 - e.a0 >= 360.0:
            return f'<circle cx="{_s(e.c[0])}" cy="{_s(Y(e.c[1]))}" r="{_s(e.r)}"/>'
        t0, t1 = math.radians(e.a0), math.radians(e.a1)
        x0, y0 = e.c[0] + e.r * math.cos(t0), e.c[1] + e.r * math.sin(t0)
        x1, y1 = e.c[0] + e.r * math.cos(t1), e.c[1] + e.r * math.sin(t1)
        buyuk = 1 if e.a1 - e.a0 > 180.0 else 0
        # y çevrildiği için matematiksel CCW, SVG'de negatif açı yönüdür: sweep-flag = 0
        d = f"M {_s(x0)} {_s(Y(y0))} A {_s(e.r)} {_s(e.r)} 0 {buyuk} 0 {_s(x1)} {_s(Y(y1))}"
        return f'<path d="{d}"/>'
    if isinstance(e, Polyline2D):
        P = np.asarray(e.P, dtype=float)
        noktalar = " ".join(f"{_s(x)},{_s(Y(y))}" for x, y in P)
        return f'<polyline points="{noktalar}"/>'
    if isinstance(e, Text2D):
        x, y = float(e.p[0]), Y(e.p[1])
        don = f' transform="rotate({_s(-e.angle)} {_s(x)} {_s(y)})"' if e.angle else ""
        return f'<text x="{_s(x)}" y="{_s(y)}" font-size="{_s(e.h)}"{don}>{escape(e.text)}</text>'
    raise GeometryError(f"SVG: bilinmeyen varlık {type(e).__name__}")


def write_svg(sheet: Sheet, path: str | Path, margin: float = 10.0) -> None:
    """Paftayı SVG 1.1 olarak yazar (birim mm)."""
    if not (math.isfinite(margin) and margin >= 0):
        raise GeometryError(f"kenar payı >= 0 olmalı (margin={margin})")
    varliklar = sheet.entities()
    bilinmeyen = {e.layer for e in varliklar} - set(STILLER)
    if bilinmeyen:
        raise GeometryError(f"SVG: bilinmeyen katman {sorted(bilinmeyen)}")
    lo, hi = sheet.bbox()
    w, h = float(hi[0] - lo[0]) + 2 * margin, float(hi[1] - lo[1]) + 2 * margin
    ymax = float(hi[1])
    satirlar = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{_s(w)}mm" height="{_s(h)}mm" '
        f'viewBox="{_s(lo[0] - margin)} {_s(-margin)} {_s(w)} {_s(h)}">',
    ]
    for katman, (kalinlik, kesik) in STILLER.items():
        if katman == "OLCU":
            stil = f'stroke="black" stroke-width="{_s(kalinlik)}" fill="none" font-family="sans-serif"'
        else:
            stil = f'stroke="black" stroke-width="{_s(kalinlik)}" fill="none"'
        if kesik:
            stil += f" stroke-dasharray={quoteattr(kesik)}"
        satirlar.append(f'<g id="{katman}" {stil}>')
        for e in varliklar:
            if e.layer == katman:
                eleman = _eleman(e, ymax)
                if isinstance(e, Text2D):
                    eleman = eleman.replace("<text ", '<text stroke="none" fill="black" ', 1)
                satirlar.append(eleman)
        satirlar.append("</g>")
    satirlar.append("</svg>")
    try:
        Path(path).write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    except OSError as e:
        raise GeometryError(f"SVG yazılamadı: {path} ({e})") from e
