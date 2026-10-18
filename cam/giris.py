"""
SPEC 03c — Rampa ve helis giriş.

Cep ve konturda düz dalma yerine helis, zigzag rampa veya kontur boyunca rampa.
Her giriş takım merkezinin geçerli bölgesinde (R₀ = Ω ⊖ B_r) kalır; eğim hiçbir harekette tan α'yı aşmaz.
Giriş sığmazsa CamError: sessizce düz dalmaya dönülmez.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from cam.model import Move, Tool
from cam.profile import Region, Segment

if TYPE_CHECKING:
    from cam.model import EntryMode

ANCHOR_N = 40  # çapa noktası (en derin nokta) ikiye bölme sayısı
RAMP_DIRS = 12  # zigzag yön adayı: u_k = (cos kπ/12, sin kπ/12)
HELIX_R_FACTOR = 0.5  # R_h varsayılanı = 0,5·r
RAMP_L_FACTOR = 2.0  # zigzag boyu varsayılanı L = 2D
NONCENTER_MIN = 0.5  # merkezden kesmeyen takımda R_h ≥ 0,5·r


def resolve(tool: Tool, entry: EntryMode | None, op: str) -> EntryMode:
    """Giriş türünü denetler, varsayılan yarıçap / boyu doldurur. op: "cep" veya "kontur"."""
    raise NotImplementedError("SPEC 03c: resolve")


def deepest_point(region: Region) -> tuple[np.ndarray, float]:
    """Bölgenin en derin noktası c ve iç yarıçap alt sınırı lo (ikiye bölme, ANCHOR_N adım)."""
    raise NotImplementedError("SPEC 03c: deepest_point")


def segment_inside(p, q, region: Region) -> bool:
    """[p, q] doğru parçası bölgenin içinde mi (sınır dahil)?"""
    raise NotImplementedError("SPEC 03c: segment_inside")


def ramp_direction(c, region: Region, L: float) -> tuple[np.ndarray, float]:
    """Zigzag yönü u ve yarı boy ℓ = min(L/2, ℓ_fit)."""
    raise NotImplementedError("SPEC 03c: ramp_direction")


def helix_moves(
    c, R_h: float, u, z0: float, z: float, alpha: float, climb: bool, ramp_feed: float, feed: float
) -> list[Move]:
    """h = c + R_h·u'dan n helis turu + z'de düz tam daire."""
    raise NotImplementedError("SPEC 03c: helix_moves")


def zigzag_moves(
    c, u, ell: float, z0: float, z: float, alpha: float, ramp_feed: float, feed: float
) -> list[Move]:
    """A = c − ℓu'dan m ayak + z'de düz geçiş + c'ye."""
    raise NotImplementedError("SPEC 03c: zigzag_moves")


def loop_ramp_moves(
    segs: list[Segment], closed: bool, z0: float, z: float, alpha: float, ramp_feed: float
) -> tuple[list[Move], list[Segment]]:
    """Kontur boyunca rampa; ikinci değer z'de kesilecek halka."""
    raise NotImplementedError("SPEC 03c: loop_ramp_moves")
