"""
SPEC 52 — Helisel diş frezeleme yolu: takım ekseni delik eksenine paralel,
merkezi ρ_h yarıçaplı helis üzerinde (G2/G3 + Z, her turda ΔZ = P).
İç diş ρ_h = r_iç_diş − D/2 + h, dış diş ρ_h = r_dış_diş + D/2 − h.

Yol delik çerçevesinde (Toolpath.frame = hole_frame) yazılır: delik ekseni yerel z, diş z = 0'dan
z = −length'e. Sağ helis: z, φ (CCW) ile artar. Tırmanma (M3): iç dişte CCW (aşağıdan yukarı), dış dişte
CW (yukarıdan aşağı); geleneksel tersi. Giriş / çıkış yayları helis çemberine teğet; her biri çeyrek tur
kadar (P/4) eksenel ilerler.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.lathe_ops import iso_thread_depth
from cam.model import CamError, FeedMode, Frame, Move, MoveType, PathMeta, Plane, Tool, ToolKind, Toolpath

SAFE = 5.0  # mm, delik ağzının üstünde başlangıç / dönüş yüksekliği (yerel z)


def _sonlu(ad: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise CamError(f"Diş frezesi: {ad} sonlu bir sayı olmalı ({v!r})")
    return float(v)


@dataclass
class ThreadMillForm:
    """Tek profilli diş frezesi: çap D, uç açısı eps_deg, burun yarıçapı, kesici boy.

    D > 0, 0 < ε < 180, r ≥ 0; aksi CamError.
    """

    D: float
    eps_deg: float = 60.0
    nose_r: float = 0.0
    flute_length: float = 20.0

    def __post_init__(self) -> None:
        for ad in ("D", "eps_deg", "nose_r", "flute_length"):
            setattr(self, ad, _sonlu(ad, getattr(self, ad)))
        if self.D <= 0:
            raise CamError(f"Diş frezesi: D pozitif olmalı (D={self.D})")
        if not 0 < self.eps_deg < 180:
            raise CamError(f"Diş frezesi: uç açısı 0 < ε < 180 olmalı ({self.eps_deg})")
        if self.nose_r < 0:
            raise CamError(f"Diş frezesi: burun yarıçapı negatif olamaz ({self.nose_r})")
        if self.nose_r >= self.D / 2:
            raise CamError(f"Diş frezesi: burun yarıçapı D/2'den küçük olmalı ({self.nose_r})")
        if self.flute_length <= 0:
            raise CamError(f"Diş frezesi: kesici boy pozitif olmalı ({self.flute_length})")

    def radius(self, w) -> np.ndarray:
        """Profil düzleminden eksenel w uzaklıkta takım yarıçapı R(w) ≥ 0 (α = ε/2, burun merkezi D/2 − r):
        |w| ≤ r·cos α → (D/2 − r) + √(r² − w²), aksi (D/2 − r) + r·sin α − (|w| − r·cos α)/tan α."""
        w = np.abs(np.asarray(w, dtype=float))
        a = math.radians(self.eps_deg / 2)
        r = self.nose_r
        Rc = self.D / 2 - r
        wt = r * math.cos(a)
        nose = Rc + np.sqrt(np.maximum(r * r - w * w, 0.0))
        flank = Rc + r * math.sin(a) - (w - wt) / math.tan(a)
        return np.maximum(np.where(w <= wt, nose, flank), 0.0)

    def half_width(self) -> float:
        """R(w) > 0 olan en büyük |w|."""
        a = math.radians(self.eps_deg / 2)
        r = self.nose_r
        return r * math.cos(a) + (self.D / 2 - r + r * math.sin(a)) * math.tan(a)


@dataclass
class ThreadMillTool(Tool):
    """Diş frezesi takımı (ToolKind.THREAD_MILL gelene kadar, Karar 1): FLAT türünde, profil form'da."""

    form: ThreadMillForm | None = field(default=None, repr=False)


def _arc(kind: MoveType, end, center, feed: float) -> Move:
    return Move(kind, tuple(float(v) for v in end), feed, (float(center[0]), float(center[1])))


def thread_mill(
    hole_frame: Frame,
    d: float,
    P: float,
    length: float,
    form: ThreadMillForm,
    side: str = "ic",
    climb: bool = True,
    rpm: float = 3000.0,
    feed: float = 300.0,
) -> Toolpath:
    """Delik ekseni hole_frame'in z'si; d anma çapı, P hatve, length diş boyu; feed mm/dk (G94)."""
    if not isinstance(hole_frame, Frame):
        raise CamError(f"Diş frezesi: hole_frame Frame olmalı ({type(hole_frame).__name__})")
    if not isinstance(form, ThreadMillForm):
        raise CamError(f"Diş frezesi: form ThreadMillForm olmalı ({type(form).__name__})")
    if side not in ("ic", "dis"):
        raise CamError(f"Diş frezesi: taraf 'ic' veya 'dis' olmalı ({side!r})")
    d, P, length = _sonlu("d", d), _sonlu("P", P), _sonlu("length", length)
    rpm, feed = _sonlu("rpm", rpm), _sonlu("feed", feed)
    for ad, v in (("d", d), ("P", P), ("length", length), ("rpm", rpm), ("feed", feed)):
        if v <= 0:
            raise CamError(f"Diş frezesi: {ad} pozitif olmalı ({v})")
    ic = side == "ic"
    h = iso_thread_depth(P, external=not ic)
    D = form.D
    if ic:
        rho = (d - 2 * 5 / 8 * math.sqrt(3) / 2 * P) / 2 - D / 2 + h  # r_iç_diş = D₁/2
        if rho <= 0:
            raise CamError(f"Diş frezesi: takım deliğe göre büyük (ρ_h = {rho} ≤ 0)")
    else:
        rho = d / 2 + D / 2 - h
    ccw = climb if ic else not climb
    up = ccw  # sağ helis: CCW yayda z artar
    n = math.ceil(length / P - 1e-9)  # tam tur sayısı
    z_lo, z_hi = -length, -length + n * P
    z_a, z_b = (z_lo, z_hi) if up else (z_hi, z_lo)
    q = P / 4 if up else -P / 4  # giriş / çıkış yayının eksenel ilerlemesi
    arc = MoveType.ARC_CCW if ccw else MoveType.ARC_CW
    T = np.array([rho, 0.0])
    moves: list[Move] = []
    if ic:
        # Yarım daire: delik ekseninden T'ye, merkez OT'nin ortası; helisle aynı dönüş yönü.
        c_e = T / 2
        bas = (0.0, 0.0)
        giris = arc
    else:
        # Dışarıdan çeyrek daire, merkez OT doğrusu üzerinde dışarıda; dönüş yönü helisin tersi (S giriş).
        re = max(D / 2, 2 * h)
        c_e = np.array([rho + re, 0.0])
        giris = MoveType.ARC_CW if ccw else MoveType.ARC_CCW
        bas = (rho + re, re if giris is MoveType.ARC_CCW else -re)
    moves.append(Move(MoveType.RAPID, (bas[0], bas[1], SAFE)))
    moves.append(Move(MoveType.RAPID, (bas[0], bas[1], z_a - q)))
    moves.append(_arc(giris, (T[0], T[1], z_a), c_e, feed))
    for k in range(1, n + 1):
        moves.append(_arc(arc, (T[0], T[1], z_a + (k * P if up else -k * P)), (0.0, 0.0), feed))
    # Çıkış: giriş çemberinde aynı yönde devam (iç: yarım daireyle eksene, dış: çeyrek daireyle dışarı).
    bit = (0.0, 0.0) if ic else (bas[0], -bas[1])
    moves.append(_arc(giris, (bit[0], bit[1], z_b + q), c_e, feed))
    moves.append(Move(MoveType.RAPID, (bit[0], bit[1], SAFE)))
    tool = ThreadMillTool(0, f"dis_frezesi_D{D:g}", ToolKind.FLAT, D, form.flute_length, form=form)
    tp = Toolpath(
        name=f"dis_frezeleme_{side}",
        tool=tool,
        start=(bas[0], bas[1], SAFE),
        moves=moves[1:],
        rpm=rpm,
        plane=Plane.XY,
        feed_mode=FeedMode.PER_MIN,
        frame=hole_frame,
        meta=PathMeta("dis"),
    )
    tp.validate()
    return tp
