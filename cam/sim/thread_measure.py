"""
SPEC 52 — Simüle diş yüzeyinden ölçüm: hatve (öz-ilişki), büyük çap, böğür çapı (dolu oranı ½),
diş dibi, helis tutarlılığı.

ISO 68-1: H = (√3/2)·P, d₂ = d − (3√3/8)·P, dış d₃ = d − 2·(17/24)·H, iç D₁ = D − 2·(5/8)·H.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.sim.polar import PolarMap


@dataclass
class ThreadMeasure:
    """Ölçülen değerler [mm]: hatve, büyük çap, böğür çapı, diş dibi çapı, helis tutarlılık hatası."""

    P: float
    d: float
    d2: float
    d_root: float
    lead_err: float


def thread_measure(m: PolarMap, side: str, z_range: tuple[float, float]) -> ThreadMeasure:
    """side "dis" (r_out) veya "ic" (r_in); z_range ölçüm bölgesi (z_min, z_max). Hatalı girdi → CamError."""
    raise NotImplementedError
