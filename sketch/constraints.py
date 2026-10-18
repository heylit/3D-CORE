"""
SPEC 17 — eskiz kısıtlarının artıkları ve analitik Jacobian'ları.

Tablo, işaret / dal kuralları ve satır ölçeği (yön satırları · L): specs/17-kroki.md "Kısıt artıkları".
"""

from __future__ import annotations

import numpy as np

from sketch.model import Sketch


def residual(sketch: Sketch, k: int, x_map: dict[str, np.ndarray | float]) -> np.ndarray:
    """k. kısıtın artığı (satır sayısı türe göre 1 ya da 2; ölçek dahil, mm).

    x_map: güncel değerler; nokta kimliği → (2,) konum, daire kimliği → yarıçap r. Haritada olmayan
    noktalar / daireler eskizdeki değerleriyle alınır. Desteklenmeyen tür / referans çifti → SketchError.
    """
    raise NotImplementedError("SPEC 17: residual")


def jacobian(sketch: Sketch, k: int, unknowns: list[str]) -> np.ndarray:
    """k. kısıtın Jacobian'ı, (satır, sütun) — eskizdeki güncel değerlerde.

    Sütun düzeni: unknowns sırasıyla; nokta kimliği → 2 sütun (x, y), daire kimliği → 1 sütun (r).
    Listede olmayan (sabit) noktaların sütunu yok.
    """
    raise NotImplementedError("SPEC 17: jacobian")
