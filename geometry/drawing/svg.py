"""SVG 1.1 yazıcı (SPEC 16). Saf Python."""

from __future__ import annotations

from pathlib import Path

from geometry.drawing.types import Sheet


def write_svg(sheet: Sheet, path: str | Path, margin: float = 10.0) -> None:
    raise NotImplementedError
