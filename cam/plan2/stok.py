"""SPEC 57 §1 — Stok kataloğu ve stok seçimi. Birimler: mm."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike

import numpy as np

from cam.model import CylinderStock, Stock


@dataclass(frozen=True)
class StockSize:
    """Katalog satırı: blok (a × b × c) ya da çubuk (Ø a, boy ≤ max_len)."""

    kind: str  # "blok" | "cubuk"
    a: float
    b: float = 0.0
    c: float = 0.0
    max_len: float | None = None
    name: str = ""


def load_catalog(path: str | PathLike) -> tuple[StockSize, ...]:
    """JSON stok kataloğunu okur."""
    raise NotImplementedError("SPEC 57: load_catalog")


def select_stock(
    bbox, catalog, m: float = 1.0, g: float = 5.0, saw: float = 3.0
) -> tuple[Stock | CylinderStock, np.ndarray]:
    """En küçük hacimli uyan stok ve parçanın stok içindeki dönüşümü (4×4); uyan yoksa CamError(stok_yok)."""
    raise NotImplementedError("SPEC 57: select_stock")
