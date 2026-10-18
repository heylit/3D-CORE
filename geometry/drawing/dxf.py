"""DXF R12 (AC1009) ASCII yazıcı ve okuyucu (SPEC 16). Saf Python."""

from __future__ import annotations

from pathlib import Path

from geometry.drawing.types import Entity, Sheet


def write_dxf(sheet_or_entities: Sheet | list[Entity], path: str | Path) -> None:
    raise NotImplementedError


def read_dxf(path: str | Path) -> list[Entity]:
    """Sadece LINE, CIRCLE, ARC, TEXT alt kümesi."""
    raise NotImplementedError
