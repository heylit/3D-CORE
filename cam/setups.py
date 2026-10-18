"""
Kurulum: ham malzeme, iş sıfırı (WCS), güvenli yükseklik ve bağlama denetimi. SPEC 14.

Bağlama denetimi takım ucu noktasıyla, takım yarıçapı kadar şişirilmiş engelle yapılır (temkinli):
ρ = R + h/2 (freze R = D/2, torna R = nose_r), h örnekleme adımı.
Tutucu çarpışması ve talaş kaldırma SPEC 05'tir.
"""

from __future__ import annotations

from collections.abc import Sequence

from cam.model import CylinderStock, Setup, Stock, Toolpath, Wcs

CLEARANCE = 5.0  # mm, freze güvenli Z payı
CLEARANCE_R = 2.0  # mm, torna güvenli yarıçap payı
SAMPLE_STEP = 0.25  # mm, bağlama denetimi örnekleme adımı h


def stock_from_bbox(bmin, bmax, margin=(0.0, 0.0, 0.0)) -> Stock:
    """Sınır kutusundan eksen başına pay ile kutu ham malzeme."""
    raise NotImplementedError


def bar_stock_from_bbox(
    bmin, bmax, margin_r: float = 0.0, margin_z: float = 0.0, standard: Sequence[float] | None = None
) -> CylinderStock:
    """Z eksenli dönel parça için çubuk; standart çaplar verilirse en küçük uygun olanı."""
    raise NotImplementedError


def wcs_from_touch(code: str, machine_point, work_point) -> Wcs:
    """Dokunulan noktanın makine ve iş koordinatından iş sıfırı: origin = m − w."""
    raise NotImplementedError


def edge_position(machine_coord: float, probe_d: float, direction: int) -> float:
    """Kenar bulucu (çap d) `direction` (±1) yönünde dokunduğunda yüzeyin makine koordinatı: m + yön·d/2."""
    raise NotImplementedError


def clearance_height(setup: Setup, clearance: float = CLEARANCE) -> float:
    """Ham malzeme ve bağlama elemanlarının en üst Z'si + pay."""
    raise NotImplementedError


def safe_radius(setup: Setup, clearance: float = CLEARANCE_R) -> float:
    """Ham malzeme ve bağlama elemanlarının en büyük yarıçapı + pay (torna)."""
    raise NotImplementedError


def check_setup(setup: Setup, ops: list[Toolpath]) -> None:
    """Bağlamaya çarpma, ham malzeme altına inme, kesici boydan derin kesim → CamError."""
    raise NotImplementedError
