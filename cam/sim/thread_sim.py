"""
SPEC 52 — Diş ve helis simülasyonu: senkron helis süpürmesi (torna G32/G95 pasoları, kılavuz G84)
ve diş frezeleme zarfı (senkronsuz helis).

Senkron kesim: θ(z) = θ₀ + 360°·(z − z₀)/P; hücre (θ, z) için
z_c(θ) = z₀ + P·(θ − θ₀)/360° + k·P (en yakın k),
dış diş r_dış ← min(r_dış, r_profil(z − z_c)), iç diş r_iç ← max(r_iç, r_profil(z − z_c)).
"""

from __future__ import annotations

from cam.model import Frame, Toolpath
from cam.sim.polar import PolarMap


def simulate_thread(
    ops: list[Toolpath], initial: PolarMap, frame: Frame | None = None, starts: int = 1
) -> PolarMap:
    """G32/G95 torna pasoları (feed = P), G84 kılavuz, thread_mill helisi.

    Başka yol → CamError ("diş yolu değil").

    initial kopyalanır, değiştirilmez. starts: diş ağız sayısı (≥ 1).
    """
    raise NotImplementedError
