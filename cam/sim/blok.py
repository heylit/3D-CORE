"""
SPEC 53 — Bloklu simülasyon: aynı doğru üzerindeki ardışık G1 hareketlerini birleştirme ve karo planı.

Süpürme kümesi takım ⊕ [p₀, p₂] = (takım ⊕ [p₀, p₁]) ∪ (takım ⊕ [p₁, p₂]); p₁ doğru üzerindeyse birleşmiş
hareketin z-map'i aynıdır. Izgara T × T karolara bölünür; hareket sırası karo içinde korunur.
"""

from __future__ import annotations

from cam.model import Move


def merge_collinear(moves: list[Move], tol: float = 1e-9, start=None) -> list[tuple[int, int]]:
    """Birleştirilebilen ardışık hareket aralıkları [(ilk, son), ...] (son dahil), tüm hareketleri örter.

    Aynı tip G1, aynı F, ara noktaların doğruya uzaklığı ≤ tol olanlar tek aralıktır.
    """
    raise NotImplementedError("SPEC 53")
