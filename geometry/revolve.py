"""
Eksenden geçen yarı düzlem kesiti, yüz sınıflama ve otomatik eksen (SPEC 28).

Arayüz geometry/part.py'dedir (Part.axial_section, SectionEdge, SectionFace, AxialSection); diğer paketler
bu dosyayı import etmez. Bu dosya arayüz PR'ının iskeletidir; gövde SPEC 28 PR'ında yazılır. Birimler: mm.
"""

from __future__ import annotations

from geometry.part import AxialSection, Part


def axial_section(
    part: Part, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), tol: float = 1e-3
) -> AxialSection:
    """Eksenden geçen x ≥ 0 yarı düzlem kesiti; axis="auto" → dönel yüzlerden eksen bulunur."""
    raise NotImplementedError("SPEC 28: geometry.revolve.axial_section")
