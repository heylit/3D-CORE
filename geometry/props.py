"""
SPEC 02 — Kütle özellikleri: hacim, kütle, ağırlık merkezi, atalet tensörü.

Birimler: ρ [t/mm³], m [t], I [t·mm²] (N – mm – MPa ile tutarlı).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from geometry.part import GeometryError, Part

try:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
except ImportError:  # pragma: no cover - build123d kurulu değilse Part zaten hata verir
    BRepGProp = GProp_GProps = None


@dataclass(frozen=True)
class MassProps:
    """V [mm³], m [t], com (3,) [mm], I (3,3) ağırlık merkezine göre, global eksenlerde [t·mm²]."""

    V: float
    m: float
    com: np.ndarray
    I: np.ndarray  # noqa: E741 - formüldeki sembol


def mass_props(part: Part, rho: float) -> MassProps:
    """m = ρ V, I = ∫ ρ (|r|² 𝟙 − r rᵀ) dV, r = x − x̄.

    Hacim integralleri OCCT BRepGProp ile birim yoğunlukta alınır (GProp_GProps: Mass = V,
    MatrixOfInertia = ∫ (|r|² 𝟙 − r rᵀ) dV, ağırlık merkezine göre, global eksenlerde); sonra ρ ile çarpılır.
    """
    if not (np.isfinite(rho) and rho > 0):
        raise GeometryError(f"yoğunluk rho > 0 olmalı (rho={rho})")
    g = GProp_GProps()
    try:
        BRepGProp.VolumeProperties_s(part.shape.wrapped, g)
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"kütle özellikleri hesaplanamadı: {e}") from e
    V = float(g.Mass())
    if not (np.isfinite(V) and V > 0):
        raise GeometryError(f"hacim pozitif olmalı (V={V})")
    c = g.CentreOfMass()
    com = np.array([c.X(), c.Y(), c.Z()])
    M = g.MatrixOfInertia()
    I_birim = np.array([[M.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)])
    I = rho * 0.5 * (I_birim + I_birim.T)  # noqa: E741 - sayısal simetri garantisi
    if not (np.all(np.isfinite(com)) and np.all(np.isfinite(I))):
        raise GeometryError("kütle özellikleri sonlu değil")
    return MassProps(V=V, m=rho * V, com=com, I=I)


def principal_moments(mp: MassProps) -> tuple[np.ndarray, np.ndarray]:
    """Artan sıralı asal momentler (3,) ve sütunları asal eksen olan (3,3) matris.

    I simetrik olduğundan özdeğer problemi I q = λ q; numpy.linalg.eigh özdeğerleri artan sırada,
    ortonormal özvektörleri sütun olarak verir: Qᵀ I Q = diag(λ).
    """
    I = np.asarray(mp.I, dtype=float)  # noqa: E741
    if I.shape != (3, 3) or not np.all(np.isfinite(I)):
        raise GeometryError("atalet tensörü (3,3) ve sonlu olmalı")
    lam, Q = np.linalg.eigh(I)
    return lam, Q
