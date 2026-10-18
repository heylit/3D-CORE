"""
SPEC 52 — Helisel diş frezeleme yolu: takım ekseni delik eksenine paralel,
merkezi ρ_h yarıçaplı helis üzerinde (G2/G3 + Z, her turda ΔZ = P).
İç diş ρ_h = r_iç_diş − D/2 + h, dış diş ρ_h = r_dış_diş + D/2 − h.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import Frame, Toolpath


@dataclass
class ThreadMillForm:
    """Tek profilli diş frezesi: çap D, uç açısı eps_deg, burun yarıçapı, kesici boy.

    D > 0, 0 < ε < 180, r ≥ 0; aksi CamError.
    """

    D: float
    eps_deg: float = 60.0
    nose_r: float = 0.0
    flute_length: float = 20.0

    def __post_init__(self) -> None:
        raise NotImplementedError


def thread_mill(
    hole_frame: Frame,
    d: float,
    P: float,
    length: float,
    form: ThreadMillForm,
    side: str = "ic",
    climb: bool = True,
    rpm: float = 3000.0,
    feed: float = 300.0,
) -> Toolpath:
    """Delik ekseni hole_frame'in z'si; d anma çapı, P hatve, length diş boyu; feed mm/dk (G94)."""
    raise NotImplementedError
