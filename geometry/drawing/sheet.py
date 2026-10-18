"""Pafta yerleşimi, ISO birinci açı (SPEC 16)."""

from __future__ import annotations

from geometry.drawing.types import Sheet, View
from geometry.part import Part


def layout(views: list[View], scale: float = 1.0, gap: float = 20.0) -> Sheet:
    """Üst önün altına, sol önün sağına, sağ önün soluna; aralarda g boşluk."""
    raise NotImplementedError


def make_drawing(
    part: Part,
    views: tuple[str, ...] = ("on", "ust", "sol"),
    section: tuple[str, float] | None = None,
    scale: float = 1.0,
    dims: bool = True,
) -> Sheet:
    """Görünüşler (+ isteğe bağlı kesit ve ölçüler) ile pafta."""
    raise NotImplementedError
