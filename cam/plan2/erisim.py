"""SPEC 57 §2–3 — Aday erişim yönleri, yön başına üstten erişilebilir özellikler, ulaşılabilen yönler."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from cam.features import Features
from cam.model import MachineProfile, Stock
from geometry.part import Part


def candidate_directions(part: Part, ang_tol: float = 0.5) -> tuple[np.ndarray, ...]:
    """±X, ±Y, ±Z ∪ düzlemsel yüz normalleri ∪ delik eksenleri, `ang_tol` derece ile kümelenmiş."""
    raise NotImplementedError("SPEC 57: candidate_directions")


def accessible(part: Part, d, stock: Stock, tol: float = 1e-3, hole_d_max: float = 20.0) -> Features:
    """`d` yönüne bakan yerel çerçevede tanınan, üstten erişilebilir özellikler."""
    raise NotImplementedError("SPEC 57: accessible")


def reachable(c, profile: MachineProfile) -> Callable[[np.ndarray], bool]:
    """Bağlama yüzü `c` iken tezgâhın ulaşabildiği yönler için yüklem R(c)."""
    raise NotImplementedError("SPEC 57: reachable")
