"""
SPEC 49 — C ekseni indeksleme: özellik ekseninden C açısı, en kısa yol, indeks adımına yuvarlama.

Radyal istasyonda R_z(C)·d = +X → C = −θ (mod 360); eksenel istasyonda delik merkezi +X yarıçapına: C = −θ.
Birimler: derece, mm.
"""

from __future__ import annotations

from cam.model import CAxis

STATIONS = ("radyal", "eksenel")


def c_for(feature_axis, station: str, prev: float | None = None) -> float:
    """Özelliğin C açısı [derece]. Radyal: feature_axis = d (parça çerçevesinde, d_z = 0); eksenel: delik
    merkezi (x, y) ya da (x, y, z). prev verilirse önceki açıya en kısa yol
    (ΔC ∈ (−180, 180]), yoksa [0, 360)."""
    raise NotImplementedError


def shortest(prev: float, c: float) -> float:
    """c'nin prev'e en yakın eşdeğeri: prev + ΔC, ΔC ∈ (−180, 180]."""
    raise NotImplementedError


def index_angle(c: float, c_axis: CAxis, r: float, tol: float = 1e-3) -> float:
    """Yazılacak açı: continuous ise c; değilse index_step'e yuvarlanır ve konum hatası r·|ΔC|·π/180 > tol
    → CamError."""
    raise NotImplementedError
