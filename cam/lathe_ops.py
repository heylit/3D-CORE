"""
SPEC 20 — Torna işlemleri: alın, boy, kaba çevrim (G71 tip I), ince profil, kanal, diş.

Yol takımın hayali uç noktasının (P = C + q_T) yoludur; burun yarıçapı telafisi burada yapılır.
Noktalar (x, 0, z), yaylar G18 (ZX), merkez (x, z); ilerleme mm/dev (G95).

İskelet: gövdeler SPEC 20 kodu yazılınca doldurulacak.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import CylinderStock, LatheTool, Toolpath
from cam.profile import Profile


@dataclass
class TurnCut:
    """Torna kesme parametreleri [mm/dev, dev/dk, m/dk, mm]."""

    feed: float  # mm/dev (G95)
    rpm: float  # dev/dk; css verilirse devir sınırı (G50)
    css: float | None = None  # m/dk, sabit kesme hızı (G96)
    a_p: float | None = None  # radyal (alında eksenel) paso derinliği
    clearance: float = 1.0  # yaklaşma payı
    retract: float = 0.5  # kaba pasoda 45° geri çekilme

    def __post_init__(self) -> None:
        raise NotImplementedError


def face(stock: CylinderStock, tool: LatheTool, cut: TurnCut, z_face: float, name: str = "alin") -> Toolpath:
    """Alın tornalama: n = ⌈H/a_p⌉ eşit paso, burun −Z ucu z_i'de, −X yönünde merkeze (borude d/2 − cl'ye)."""
    raise NotImplementedError


def turn(
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    x_final: float,
    z_end: float,
    side: str = "dis",
    name: str = "boy",
) -> Toolpath:
    """Boy tornalama: (zmax, X_f) → (z_end, X_f) → (z_end, X_s) profilinin δ = 0 kaba çevrimi."""
    raise NotImplementedError


def rough(
    profile: Profile,
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    allowance: float = 0.0,
    side: str = "dis",
    name: str = "kaba",
) -> Toolpath:
    """Boyuna kaba çevrim (G71 tip I): n − 1 boyuna paso + δ talaş paylı kontur pasosu."""
    raise NotImplementedError


def finish(
    profile: Profile,
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    side: str = "dis",
    name: str = "ince",
) -> Toolpath:
    """Burun yarıçapı telafili ince profil (sıkı mod: erişilemeyen profil → CamError)."""
    raise NotImplementedError


def groove(
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    z_left: float,
    z_right: float,
    x_top: float,
    x_bottom: float,
    side: str = "dis",
    name: str = "kanal",
) -> Toolpath:
    """Dalarak radyal kanal: m = ⌈(W − w)/(w − 2r)⌉ + 1 dalış, kenarlar eşit aralıklı."""
    raise NotImplementedError


def iso_thread_depth(pitch: float, external: bool = True) -> float:
    """ISO 68-1: H = (√3/2)·P; dış diş h = 17/24·H, iç diş h = 5/8·H."""
    raise NotImplementedError


def thread_depths(h: float, first: float, minimum: float = 0.0, spring: int = 0) -> list[float]:
    """Fanuc G76 kümülatif derinlikler: h_i = Δd·√i, artış ≥ Δd_min, son paso tam h; + spring boş paso."""
    raise NotImplementedError


def thread(
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    z_start: float,
    z_end: float,
    x0: float,
    pitch: float,
    depth: float,
    first: float,
    minimum: float = 0.0,
    spring: int = 1,
    infeed: str = "radyal",
    side: str = "dis",
    name: str = "dis",
) -> Toolpath:
    """Diş çekme: her paso G1, feed = hatve (mm/dev); radyal veya yanak (Δz = s·h_i·tan(εr/2)) dalma."""
    raise NotImplementedError
