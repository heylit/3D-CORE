"""SPEC 38 — Bağlama resmi: ham malzeme, bağlama elemanları, iş sıfırı simgesi (SPEC 16 paftası, §5)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cam.model import Setup
from geometry.drawing.types import Sheet

if TYPE_CHECKING:
    from geometry.part import Part


def setup_drawing(setup: Setup, part: Part | None = None, scale: float = 1.0, gap: float = 20.0) -> Sheet:
    """ "on" ve "ust" görünüşlü bağlama paftası (iş koordinatında)."""
    raise NotImplementedError("SPEC 38: setup_drawing")
