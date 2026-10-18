"""
SPEC 17 — eskiz çözücü: Gauss–Newton (en küçük normlu adım), serbestlik, çelişki teşhisi, sürükleme.

Yöntem: specs/17-kroki.md "Çözüm", "Serbestlik derecesi", "Çelişki teşhisi", "Sürükleme".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sketch.model import Sketch


@dataclass
class SolveResult:
    """Çözüm. points: tüm noktalar (sabitler dahil) → (2,); radii: daireler → r; sides: TANGENT dalları."""

    points: dict[str, np.ndarray]
    radii: dict[str, float]
    sides: dict[int, int]
    iterations: int
    residual: float  # son ölçekli max|r|, mm
    dof: int
    freedom: dict[str, int] = field(default_factory=dict)  # nokta / öğe kimliği → kalan serbestlik
    directions: dict[str, np.ndarray] = field(default_factory=dict)  # tek serbestlikli nokta → birim yön
    redundant: tuple[int, ...] = ()  # tutarlı ama gereksiz kısıtların sıraları

    def apply(self, sketch: Sketch) -> None:
        """Konumları, yarıçapları ve side değerlerini eskize yazar."""
        raise NotImplementedError("SPEC 17: SolveResult.apply")


def solve(sketch: Sketch, tol: float = 1e-10, max_iter: int = 50) -> SolveResult:
    """Eskizi çözer; girdiyi değiştirmez. Çelişki → SketchError (constraints = çelişki kümesi)."""
    raise NotImplementedError("SPEC 17: solve")


def drag(sketch: Sketch, point: str, target, tol: float = 1e-10, max_iter: int = 50) -> SolveResult:
    """point'i kısıtları bozmadan target'a (uv, mm) yerel olarak en yakın konuma taşır; girdiyi değiştirmez.

    Sabit nokta → SketchError.
    """
    raise NotImplementedError("SPEC 17: drag")


def dof(sketch: Sketch) -> int:
    """Mevcut konumda kalan serbestlik derecesi (çözmez)."""
    raise NotImplementedError("SPEC 17: dof")
