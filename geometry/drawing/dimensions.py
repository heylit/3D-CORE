"""Temel ölçüler ve ölçü metni (SPEC 16)."""

from __future__ import annotations

from geometry.drawing.types import Dimension, View
from geometry.part import Part


def format_value(value: float, diameter: bool = False) -> str:
    """0.01'e yuvarla, sondaki sıfırları at, ondalık virgül; çapta "Ø" öneki."""
    raise NotImplementedError


def basic_dimensions(part: Part, views: list[View]) -> dict[str, tuple[Dimension, ...]]:
    """Görünüş adı -> temel ölçüler; her ölçü pafta üzerinde bir kez."""
    raise NotImplementedError
