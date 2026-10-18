"""SPEC 38 — Bağlama resmi: ham malzeme, bağlama elemanları, iş sıfırı simgesi (SPEC 16 paftası, §5).

Görünüşler iş koordinatındadır (öteleme yok): "on" (u = x, v = z), "ust" (u = x, v = y).
Ham malzeme EKSEN (noktalı-kesikli), bağlama elemanı GORUNUR + TARAMA, iş sıfırı simgesi OLCU.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from cam.model import CamError, CylinderStock, Setup, Stock
from geometry.drawing.hatch import hatch
from geometry.drawing.sheet import layout
from geometry.drawing.types import Arc2D, Entity, Line2D, Sheet, Text2D, View
from geometry.part import Region

if TYPE_CHECKING:
    from geometry.part import Part

OK_BOY = 15.0  # mm, kağıt üzerinde iş sıfırı okunun boyu
KANAT = 3.0  # mm, kağıt üzerinde ok kanadı boyu
KANAT_ACI = 15.0  # derece
YAZI = 3.5  # mm, kağıt üzerinde yazı boyu
KIRIS = 1e-3  # mm, silindirin taranan çokgeninin kiriş toleransı

# görünüş adı → (u eksen indisi, v eksen indisi, v ekseninin harfi)
EKSENLER = {"on": (0, 2, "Z"), "ust": (0, 1, "Y")}


def _pozitif(ad: str, v) -> None:
    if not (isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v > 0):
        raise CamError(f"Bağlama resmi: {ad} pozitif ve sonlu olmalı ({ad}={v})")


def _dikdortgen(u0: float, v0: float, u1: float, v1: float) -> np.ndarray:
    """CCW dikdörtgen köşeleri (4, 2)."""
    return np.array([[u0, v0], [u1, v0], [u1, v1], [u0, v1]], dtype=float)


def _kapali(P: np.ndarray, layer: str) -> list[Line2D]:
    return [Line2D(P[i], P[(i + 1) % len(P)], layer) for i in range(len(P))]


def _cember(r: float) -> np.ndarray:
    """Merkezi (0, 0), kiriş sapması ≤ KIRIS olan CCW çokgen."""
    n = max(8, math.ceil(math.pi / math.acos(1 - min(KIRIS / r, 1.0))))
    a = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    return r * np.column_stack([np.cos(a), np.sin(a)])


def _kutu_uv(b: Stock, name: str) -> tuple[float, float, float, float]:
    lo = (b.xmin, b.ymin, b.zmin)
    hi = (b.xmax, b.ymax, b.zmax)
    iu, iv, _ = EKSENLER[name]
    return lo[iu], lo[iv], hi[iu], hi[iv]


def _eleman(b: Stock | CylinderStock, name: str, s: float) -> tuple[list[Entity], list[Line2D]]:
    """Bağlama elemanı: GORUNUR sınır + TARAMA."""
    if isinstance(b, CylinderStock) and name == "ust":
        r = b.D / 2
        return [Arc2D(np.zeros(2), r, 0.0, 360.0, "GORUNUR")], hatch([Region(_cember(r))], s=s)
    if isinstance(b, CylinderStock):
        P = _dikdortgen(-b.D / 2, b.zmin, b.D / 2, b.zmax)
    else:
        P = _dikdortgen(*_kutu_uv(b, name))
    return _kapali(P, "GORUNUR"), hatch([Region(P)], s=s)


def _ok(yon: np.ndarray, A: float, k: float) -> list[Line2D]:
    """Orijinden `yon` yönünde A boyunda gövde + ucunda iki kanat (kağıt ölçüsü / k)."""
    uc = A * yon
    out = [Line2D(np.zeros(2), uc, "OLCU")]
    for isaret in (1.0, -1.0):
        a = math.radians(KANAT_ACI) * isaret
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        out.append(Line2D(uc, uc - (KANAT / k) * (R @ yon), "OLCU"))
    return out


def _is_sifiri(name: str, code: str, k: float) -> list[Entity]:
    A = OK_BOY / k
    ex, ey = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    _, _, harf_v = EKSENLER[name]
    pay = 1.0 / k
    return [
        *_ok(ex, A, k),
        *_ok(ey, A, k),
        Text2D(A * ex + np.array([pay, -YAZI / 2 / k]), "X", YAZI, 0.0, "OLCU"),
        Text2D(A * ey + np.array([-YAZI / 2 / k, pay]), harf_v, YAZI, 0.0, "OLCU"),
        Text2D(np.array([pay, pay]), code, YAZI, 0.0, "OLCU"),
    ]


def _gorunus(setup: Setup, name: str, part: Part | None, k: float) -> View:
    edges: list[Entity] = []
    if part is not None:
        from geometry.drawing.views import project

        edges += list(project(part, name, axes=False).edges)
    edges += _kapali(_dikdortgen(*_kutu_uv(setup.stock, name)), "EKSEN")
    tarama: list[Line2D] = []
    for b in setup.fixtures:
        sinir, t = _eleman(b, name, 3.0 / k)
        edges += sinir
        tarama += t
    edges += _is_sifiri(name, setup.wcs.code, k)
    return View(name=name, direction=name, edges=tuple(edges), hatch=tuple(tarama))


def setup_drawing(setup: Setup, part: Part | None = None, scale: float = 1.0, gap: float = 20.0) -> Sheet:
    """ "on" ve "ust" görünüşlü bağlama paftası (iş koordinatında)."""
    if not isinstance(setup, Setup):
        raise CamError(f"Bağlama resmi: Setup bekleniyor ({type(setup).__name__})")
    if not isinstance(setup.stock, Stock):
        raise CamError("Bağlama resmi: yalnız kutu ham malzeme (torna föyü kapsam dışı)")
    _pozitif("scale", scale)
    _pozitif("gap", gap)
    gorunusler = [_gorunus(setup, name, part, float(scale)) for name in ("on", "ust")]
    return layout(gorunusler, scale=float(scale), gap=float(gap))
