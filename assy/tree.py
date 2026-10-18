"""
Montaj ağacı: gezinme, doğrulama, düz montaja dönüşüm ve geri dönüş (SPEC 07).

Düğüm tipi `assy.model.Node`'dur (ayrı arayüz PR'ı). Saf Python + numpy; OCCT gerektirmez.

Dünya dönüşümü:  T_dünya(n_k) = T(n₀) · T(n₁) · … · T(n_k)   (Craig, Bölüm 2.3)
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from assy.model import Assembly, Node


def validate(root: Node) -> None:
    """Ağaç bütünlüğü: kardeş adları, boş alt montaj, paylaşılan tanımların tutarlılığı."""
    raise NotImplementedError("SPEC 07: validate")


def walk(root: Node) -> Iterator[tuple[str, Node, np.ndarray]]:
    """Derinlik öncelikli (yol, düğüm, T_dünya). Kökün yolu ""."""
    raise NotImplementedError("SPEC 07: walk")


def world(root: Node, path: str) -> np.ndarray:
    """Yoldaki düğümün dünya dönüşümü."""
    raise NotImplementedError("SPEC 07: world")


def flatten(root: Node, fixed: Iterable[str] = ()) -> Assembly:
    """Her yaprak bir Component(name=yol, part=parça kimliği, T=T_dünya)."""
    raise NotImplementedError("SPEC 07: flatten")


def apply(root: Node, assy: Assembly) -> Node:
    """Yaprakların dünya dönüşümü assy'deki bileşenlerle aynı olacak şekilde yeni ağaç."""
    raise NotImplementedError("SPEC 07: apply")
