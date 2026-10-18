"""
Takım boyu: Fanuc G43 H ofset tablosu, GRBL G38.2 ölçüm programı ve G43.1 ofsetleri. SPEC 14.

L_n = Tool.gauge_length (iş mili ölçü hattından uca). GRBL'de Z sıfırı referans takımla alınır;
diğer takımlar için ΔL_n = L_n − L_ref (ön ayar) veya ΔL_n = z_n − z_ref (takım boyu ölçerde
G38.2 tetiklenme Z'leri, makine koordinatı). Uzun takımda ΔL pozitif.
Kaynak: GRBL 1.1 wiki "G-code commands" (G38.2, G43.1, G49, G53); LinuxCNC G38, G43.1.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cam.model import ToolLibrary


@dataclass
class ToolSetter:
    """Takım boyu ölçer, makine koordinatında [mm]: ölçerin XY'si, probun başladığı Z, güvenli Z,
    en fazla prob boyu, hızlı / yavaş prob beslemesi [mm/dk] ve geri çekilme."""

    x: float
    y: float
    z_start: float
    z_safe: float
    travel: float
    feed_fast: float = 200.0
    feed_slow: float = 20.0
    backoff: float = 2.0

    def __post_init__(self) -> None:
        raise NotImplementedError


def length_offsets(lib: ToolLibrary, ids: Sequence[int], ref_id: int) -> dict[int, float]:
    """Ön ayardan ΔL_n = L_n − L_ref."""
    raise NotImplementedError


def offsets_from_probe(readings: dict[int, float], ref_id: int) -> dict[int, float]:
    """Prob tetiklenme Z'lerinden ΔL_n = z_n − z_ref."""
    raise NotImplementedError


def verify_offsets(measured: dict[int, float], expected: dict[int, float], tol: float = 0.05) -> None:
    """Ölçülen ve beklenen ofset farkı tol'u aşan takım varsa CamError."""
    raise NotImplementedError


def fanuc_offset_table(lib: ToolLibrary, ids: Sequence[int]) -> dict[int, float]:
    """Fanuc H kayıtları: {n: L_n}."""
    raise NotImplementedError


def probe_program(ids: Sequence[int], setter: ToolSetter, decimals: int = 3) -> str:
    """GRBL takım boyu ölçüm programı (SPEC 14 Ek A)."""
    raise NotImplementedError
