"""
SPEC 49 — Canlı takım işlemleri: radyal / eksenel delik, Y eksenli kaçık delik, kama kanalı, alın cebi
ve konturu (polar), silindirik kanal.

Hepsi parça çerçevesinde Toolpath üretir: radyal işlemlerde takım ekseni −X (C ile döndürülmeden önce),
eksenel işlemlerde −Z. Radyal / eksenel delik ve kamada hareketler C açısını taşır (Move.c);
alın işlemleri coord = "polar", silindirik kanal coord = "silindirik". Takım LatheTool, istasyon canlı
değil ya da Y kursu dışında e → CamError.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import CylinderStock, MachineProfile, Tool, Toolpath
from cam.ops2d import Cut
from cam.profile import Profile, Region


@dataclass(frozen=True)
class LiveCut:
    """Canlı takım kesme verisi [mm/dk, dev/dk, mm]."""

    feed: float
    plunge_feed: float
    rpm: float
    clearance: float = 1.0  # stok yüzeyine dalmadan önce bırakılan pay
    safe: float = 5.0  # hızlı hareket mesafesi stok yüzeyinin üstünde (radyalde yarıçap, eksenelde Z)


def radial_hole(
    stock: CylinderStock,
    tool: Tool,
    cut: LiveCut,
    theta: float,
    z: float,
    depth: float,
    e: float = 0.0,
    station: int | None = None,
    machine: MachineProfile | None = None,
) -> Toolpath:
    """Çevreden radyal (e = 0) ya da Y eksenli kaçık (e ≠ 0) düz tabanlı delik; θ derece, giriş
    stok yüzeyinden."""
    raise NotImplementedError


def axial_hole(
    stock: CylinderStock,
    tool: Tool,
    cut: LiveCut,
    r: float,
    theta: float,
    depth: float,
    station: int | None = None,
    machine: MachineProfile | None = None,
) -> Toolpath:
    """Alında (stock.zmax) eksenden r uzakta, θ açısında eksenel düz tabanlı delik."""
    raise NotImplementedError


def keyway(
    stock: CylinderStock,
    tool: Tool,
    cut: LiveCut,
    theta: float,
    z0: float,
    z1: float,
    t: float,
    ap: float,
    station: int | None = None,
    machine: MachineProfile | None = None,
) -> Toolpath:
    """Kama kanalı: C = −θ sabit, takım −X yönünde x = R − t'ye ap pasolarla, Z boyunca z0 → z1
    (uçlar yarım daire)."""
    raise NotImplementedError


def face_pocket(
    region: Region, tool: Tool, cut: Cut, station: int | None = None, machine: MachineProfile | None = None
) -> Toolpath:
    """Alın cebi (SPEC 03 pocket), coord = "polar"; machine verilirse polar_check."""
    raise NotImplementedError


def face_contour(
    profile: Profile,
    tool: Tool,
    cut: Cut,
    side: str,
    station: int | None = None,
    machine: MachineProfile | None = None,
) -> Toolpath:
    """Alın konturu (SPEC 03 contour), coord = "polar"; machine verilirse polar_check."""
    raise NotImplementedError


def cyl_slot(
    path_sz: Profile,
    tool: Tool,
    cut: LiveCut,
    r_ref: float,
    t: float,
    station: int | None = None,
    machine: MachineProfile | None = None,
) -> Toolpath:
    """Açılmış (s, z) düzleminde doğrulardan oluşan açık yol boyunca silindirik kanal, taban yarıçapı
    r_ref − t."""
    raise NotImplementedError
