"""
SPEC 50 — eksen düzgünleştirme: yönelim dizisine simetrik pencereli ortalama, çakmazlık korunarak.

Ölçüt J = Σ_k |∠(a_k, a_{k+1}) − ∠(a_{k−1}, a_k)|; düzgünleştirme J'yi artıramaz.

Birimler: mm, derece.
"""

from __future__ import annotations

from cam.dropcutter import TriMesh
from cam.model import Kinematics, Tool, Toolpath
from cam.multiaxis.toolpath5 import Avoid


def smooth_axes(
    tp: Toolpath,
    mesh: TriMesh,
    tool: Tool,
    w: int = 5,
    avoid: Avoid | None = None,
    kin: Kinematics | None = None,
) -> tuple[Toolpath, float, float]:
    """Düzgünleştirilmiş yol, J_eski, J_yeni.

    Pencere yalnız kesintisiz G1 kesme dizisinin içinde; dizi uçlarında kırpılır, ağırlık eşit.
    """
    raise NotImplementedError("SPEC 50: smooth_axes")
