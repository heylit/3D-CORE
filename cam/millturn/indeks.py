"""
SPEC 49 — C ekseni indeksleme: özellik ekseninden C açısı, en kısa yol, indeks adımına yuvarlama.

Radyal istasyonda R_z(C)·d = +X → C = −θ (mod 360); eksenel istasyonda delik merkezi +X yarıçapına: C = −θ.
Birimler: derece, mm.
"""

from __future__ import annotations

import math

from cam.model import CamError, CAxis

STATIONS = ("radyal", "eksenel")


def _mod360(c: float) -> float:
    """[0, 360) aralığına indirger (−0 ve 360'a yuvarlanan küçük negatifler 0 olur)."""
    c = math.fmod(c, 360.0)
    if c < 0:
        c += 360.0
    return 0.0 if c >= 360.0 else c + 0.0


def c_for(feature_axis, station: str, prev: float | None = None) -> float:
    """Özelliğin C açısı [derece]. Radyal: feature_axis = d (parça çerçevesinde, d_z = 0); eksenel: delik
    merkezi (x, y) ya da (x, y, z). prev verilirse önceki açıya en kısa yol
    (ΔC ∈ (−180, 180]), yoksa [0, 360)."""
    if station not in STATIONS:
        raise CamError(f"C açısı: istasyon yönü {', '.join(STATIONS)} olmalı ({station!r})")
    v = [float(a) for a in feature_axis]
    if len(v) not in (2, 3) or not all(math.isfinite(a) for a in v):
        raise CamError(f"C açısı: özellik ekseni / konumu (x, y[, z]) sonlu olmalı ({feature_axis!r})")
    x, y = v[0], v[1]
    if math.hypot(x, y) < 1e-12:
        raise CamError(f"C açısı: {station} özellik eksen üzerinde, açı tanımsız ({feature_axis!r})")
    if station == "radyal" and len(v) == 3 and abs(v[2]) > 1e-9 * math.hypot(x, y):
        raise CamError(f"C açısı: radyal özellik ekseni XY düzleminde olmalı (d_z = {v[2]})")
    c = _mod360(-math.degrees(math.atan2(y, x)))
    return c if prev is None else shortest(prev, c)


def shortest(prev: float, c: float) -> float:
    """c'nin prev'e en yakın eşdeğeri: prev + ΔC, ΔC ∈ (−180, 180]."""
    if not (math.isfinite(prev) and math.isfinite(c)):
        raise CamError(f"C açısı sonlu olmalı (prev={prev}, c={c})")
    dC = _mod360(c - prev)
    if dC > 180.0:
        dC -= 360.0
    return prev + dC


def index_angle(c: float, c_axis: CAxis, r: float, tol: float = 1e-3) -> float:
    """Yazılacak açı: continuous ise c; değilse index_step'e yuvarlanır ve konum hatası r·|ΔC|·π/180 > tol
    → CamError."""
    if not isinstance(c_axis, CAxis):
        raise CamError(f"C ekseni CAxis olmalı ({type(c_axis).__name__})")
    if not (math.isfinite(c) and math.isfinite(r) and r >= 0 and tol > 0):
        raise CamError(f"C indeksi: c, r ≥ 0 sonlu ve tol > 0 olmalı (c={c}, r={r}, tol={tol})")
    if c_axis.continuous:
        return c
    step = c_axis.index_step
    c_yuv = round(c / step) * step
    hata = r * abs(c_yuv - c) * math.pi / 180.0
    if hata > tol:
        raise CamError(
            f"C indeksi: {c}° adım {step}°'ye yuvarlanınca ({c_yuv}°) r = {r} mm'de konum hatası "
            f"{hata:.4g} mm > {tol} mm"
        )
    return c_yuv
