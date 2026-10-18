"""Kenar sınıflama, birleştirme, görünen/gizli önceliği (SPEC 16). Saf numpy."""

from __future__ import annotations

import numpy as np

from geometry.drawing.types import Arc2D, Entity, Line2D, Polyline2D


def classify(P: np.ndarray, tol_s: float = 1e-6) -> Line2D | Arc2D | Polyline2D:
    """Örnek noktalardan (k, 2) doğru / yay / çoklu çizgi sınıflaması."""
    raise NotImplementedError


def clean_edges(visible: list[Entity], hidden: list[Entity], tol_s: float = 1e-6) -> list[Entity]:
    """Ham kenarları birleştirir, gizliden görüneni çıkarır (GORUNUR / GIZLI katmanlı çıktı)."""
    raise NotImplementedError


def total_length(edges: list[Entity], layer: str) -> float:
    """Katmandaki toplam boy (yay boyu r·Δθ)."""
    raise NotImplementedError
