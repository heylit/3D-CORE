"""
SPEC 10 — Bağlama elemanlarının OCCT katısı: ilkel listesinden (kutu, Z eksenli silindir) birleşim.

`cam`'i import etmez: ilkelleri `cam.baglama.Primitive.to_dict()` biçiminde düz sözlük olarak alır.
Hatalar `geometry.part.GeometryError`.
"""

from __future__ import annotations

from collections.abc import Sequence

from geometry.part import Part


def primitives_part(prims: Sequence[dict], name: str) -> Part:
    """İlkellerin birleşimi; Part.name = name.

    Her ilkel {"shape": {"type": "kutu" | "silindir", ...}, "frame": {"origin", "R"}}.
    """
    raise NotImplementedError("SPEC 10: primitives_part")
