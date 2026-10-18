"""
Part boolean işlemleri, rijit taşıma ve en küçük uzaklık (SPEC 09).

Arayüz geometry/part.py'dedir (Part.moved, common, cut, fuse, distance); diğer paketler bu dosyayı import
etmez. Bu dosya arayüz PR'ının iskeletidir; gövdeler SPEC 09 PR'ında yazılır. Birimler: mm, mm³.
Boolean sonucu geçersiz şekilse veya OCCT işlemi başarısızsa GeometryError.
"""

from __future__ import annotations

import numpy as np

from geometry.part import Part


def moved(part: Part, T: np.ndarray) -> Part:
    """Rijit T (4x4) ile taşınmış yeni parça; ad aynı, delik kayıtları da taşınır."""
    raise NotImplementedError("SPEC 09: geometry.boolean.moved")


def common(a: Part, b: Part, tol_v: float = 1e-6) -> Part | None:
    """A ∩ B; hacmi ≤ tol_v ise None. Ad: a.name."""
    raise NotImplementedError("SPEC 09: geometry.boolean.common")


def cut(a: Part, b: Part) -> Part:
    """A − B; delik kayıtları korunur, boş sonuç GeometryError. Ad: a.name."""
    raise NotImplementedError("SPEC 09: geometry.boolean.cut")


def fuse(a: Part, b: Part) -> Part:
    """A ∪ B, tek parça; delik kayıtları A, B sırasıyla. Ad: a.name."""
    raise NotImplementedError("SPEC 09: geometry.boolean.fuse")


def distance(a: Part, b: Part) -> tuple[float, np.ndarray, np.ndarray]:
    """Sınırlar arası en küçük uzaklık d ve en yakın noktalar (p ∈ ∂A, q ∈ ∂B)."""
    raise NotImplementedError("SPEC 09: geometry.boolean.distance")
