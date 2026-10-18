"""
Montaj STEP'i yazma / okuma (SPEC 07), OCCT XCAF ile (STEPCAFControl_Writer / Reader).

Her parça kimliği ve alt montaj tanımı bir PRODUCT, her ağaç düğümü bir NEXT_ASSEMBLY_USAGE_OCCURRENCE olur.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from assy.model import Node
    from geometry.part import Part


def write_step(path: str | Path, root: Node, parts: Mapping[str, Part]) -> None:
    """Ağacı ürün / oluşum yapısıyla STEP'e yazar."""
    raise NotImplementedError("SPEC 07: write_step")


def read_step(path: str | Path) -> tuple[Node, dict[str, Part]]:
    """STEP'i ağaç ve parça sözlüğü olarak okur."""
    raise NotImplementedError("SPEC 07: read_step")
