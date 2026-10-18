"""
3D-CORE katı parça arayüzü (OCCT, build123d üzerinden).

build123d / OpenCascade SADECE bu katmanda import edilir. cam/ ve assy/ bir parçaya ihtiyaç duyduğunda
bu sınıfı kullanır, build123d'yi doğrudan değil.

Birimler: mm, mm², mm³.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import build123d as bd
except ImportError:  # pragma: no cover - kurulum yoksa anlamlı hata ver
    bd = None


class GeometryError(ValueError):
    """Geçersiz veya okunamayan geometri."""


def _require_occt() -> None:
    if bd is None:
        raise GeometryError('build123d kurulu değil: pip install -e ".[cad]"')


class Part:
    """Tek bir katı parça: build123d Shape (Solid / Compound) + ad."""

    def __init__(self, shape, name: str = "parca") -> None:
        _require_occt()
        if shape is None or not shape.is_valid:
            raise GeometryError(f"Parça '{name}': geçersiz şekil")
        if shape.volume <= 0:
            raise GeometryError(f"Parça '{name}': hacim pozitif olmalı (V={shape.volume})")
        self.shape = shape
        self.name = name

    @property
    def volume(self) -> float:
        return float(self.shape.volume)

    @property
    def area(self) -> float:
        return float(self.shape.area)

    @property
    def center_of_mass(self) -> np.ndarray:
        c = self.shape.center(bd.CenterOf.MASS)
        return np.array([c.X, c.Y, c.Z])

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        b = self.shape.bounding_box()
        return np.array([b.min.X, b.min.Y, b.min.Z]), np.array([b.max.X, b.max.Y, b.max.Z])

    def to_step(self, path: str | Path) -> None:
        if not bd.export_step(self.shape, str(path)):
            raise GeometryError(f"STEP yazılamadı: {path}")

    @classmethod
    def from_step(cls, path: str | Path, name: str | None = None) -> Part:
        _require_occt()
        path = Path(path)
        if not path.is_file():
            raise GeometryError(f"STEP dosyası yok: {path}")
        return cls(bd.import_step(str(path)), name=name or path.stem)

    def to_stl(self, path: str | Path, tolerance: float = 0.01) -> None:
        if not bd.export_stl(self.shape, str(path), tolerance=tolerance):
            raise GeometryError(f"STL yazılamadı: {path}")
