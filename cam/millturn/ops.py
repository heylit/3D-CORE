"""
SPEC 49 — Canlı takım işlemleri: radyal / eksenel delik, Y eksenli kaçık delik, kama kanalı, alın cebi
ve konturu (polar), silindirik kanal.

Hepsi parça çerçevesinde Toolpath üretir: radyal işlemlerde takım ekseni −X (C ile döndürülmeden önce),
eksenel işlemlerde −Z. Radyal / eksenel delik ve kamada hareketler C açısını taşır (Move.c);
alın işlemleri coord = "polar", silindirik kanal coord = "silindirik". Takım LatheTool, istasyon canlı
değil ya da Y kursu dışında e → CamError.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from cam.millturn.indeks import c_for
from cam.millturn.istasyon import RADYAL_EKSEN, live_station, live_tool
from cam.millturn.polar import polar_check
from cam.model import CamError, CylinderStock, MachineProfile, Move, MoveType, PathMeta, Tool, Toolpath
from cam.ops2d import Cut, contour, pocket
from cam.profile import Arc, Profile, Region

G0, G1 = MoveType.RAPID, MoveType.LINEAR
STEPOVER = 0.5  # alın cebinde varsayılan yan paso / takım çapı


@dataclass(frozen=True)
class LiveCut:
    """Canlı takım kesme verisi [mm/dk, dev/dk, mm]."""

    feed: float
    plunge_feed: float
    rpm: float
    clearance: float = 1.0  # stok yüzeyine dalmadan önce bırakılan pay
    safe: float = 5.0  # hızlı hareket mesafesi stok yüzeyinin üstünde (radyalde yarıçap, eksenelde Z)

    def __post_init__(self) -> None:
        for ad in ("feed", "plunge_feed", "rpm", "clearance", "safe"):
            v = getattr(self, ad)
            if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
                raise CamError(f"Canlı takım kesme verisi: {ad} sonlu sayı olmalı ({v!r})")
        if min(self.feed, self.plunge_feed, self.rpm) <= 0:
            raise CamError("Canlı takım kesme verisi: feed, plunge_feed ve rpm pozitif olmalı")
        if not 0 <= self.clearance < self.safe:
            raise CamError(
                f"Canlı takım kesme verisi: 0 ≤ clearance < safe olmalı ({self.clearance}, {self.safe})"
            )


def _pozitif(nerede: str, **vals) -> None:
    for ad, v in vals.items():
        if not (isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v > 0):
            raise CamError(f"{nerede}: {ad} pozitif ve sonlu olmalı ({v!r})")


def _sonlu(nerede: str, **vals) -> None:
    for ad, v in vals.items():
        if not (isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)):
            raise CamError(f"{nerede}: {ad} sonlu sayı olmalı ({v!r})")


def _stok(stock: CylinderStock) -> float:
    if not isinstance(stock, CylinderStock):
        raise CamError(f"Torna-freze işlemi CylinderStock ister ({type(stock).__name__})")
    return stock.D / 2


def _radyal_yol(name, tool, cut, c, start, pts, meta, station) -> Toolpath:
    """Radyal istasyon yolu: noktalar (tip, (x, y, z), ilerleme) tezgâh çerçevesinde, C = c sabit."""
    moves = [Move(t, p, feed=f, axis=RADYAL_EKSEN, c=c) for t, p, f in pts]
    tp = Toolpath(name, tool, start, moves, rpm=cut.rpm, station=station, meta=meta)
    tp.validate()
    return tp


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
    tool = live_tool(tool)
    nerede = "Radyal delik"
    R = _stok(stock)
    _sonlu(nerede, theta=theta, z=z, e=e)
    _pozitif(nerede, depth=depth)
    rho = tool.D / 2
    if abs(e) + rho >= R:
        raise CamError(
            f"{nerede}: |e| + takım yarıçapı ({abs(e) + rho}) stok yarıçapından ({R}) küçük olmalı"
        )
    if machine is not None and e != 0.0:
        if machine.y is None:
            raise CamError(f"{nerede}: kaçık delik (e = {e}) için tezgâhta Y ekseni yok")
        if not machine.y.min <= e <= machine.y.max:
            raise CamError(f"{nerede}: e = {e} Y kursu dışında ({machine.y.min}, {machine.y.max})")
    live_station(machine, station, "radyal", cut.rpm)
    x_giris = math.sqrt(R * R - e * e)  # takım merkezinde stok yüzeyi
    x_b = x_giris - depth
    if x_b <= 0:
        raise CamError(f"{nerede}: derinlik ({depth}) yüzeyden eksene ({x_giris}) ulaşıyor")
    x_ust = math.sqrt(R * R - max(0.0, abs(e) - rho) ** 2)  # takım izdüşümünde en yüksek yüzey
    c = c_for((math.cos(math.radians(theta)), math.sin(math.radians(theta)), 0.0), "radyal")
    pts = [
        (G0, (x_ust + cut.clearance, e, z), None),
        (G1, (x_b, e, z), cut.plunge_feed),
        (G0, (x_ust + cut.safe, e, z), None),
    ]
    meta = PathMeta("delik", "c_indeks", ap=depth)
    return _radyal_yol("radyal_delik", tool, cut, c, (x_ust + cut.safe, e, z), pts, meta, station)


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
    tool = live_tool(tool)
    nerede = "Eksenel delik"
    R = _stok(stock)
    _sonlu(nerede, r=r, theta=theta)
    _pozitif(nerede, depth=depth)
    if not 0 <= r < R:
        raise CamError(f"{nerede}: 0 ≤ r < R olmalı (r = {r}, R = {R})")
    live_station(machine, station, "eksenel", cut.rpm)
    t = math.radians(theta)
    # r = 0'da açı tanımsız: C = 0
    c = c_for((r * math.cos(t), r * math.sin(t)), "eksenel") if r > 1e-12 else 0.0
    z0 = stock.zmax
    moves = [
        Move(G0, (r, 0.0, z0 + cut.clearance), c=c),
        Move(G1, (r, 0.0, z0 - depth), feed=cut.plunge_feed, c=c),
        Move(G0, (r, 0.0, z0 + cut.safe), c=c),
    ]
    tp = Toolpath(
        "eksenel_delik",
        tool,
        (r, 0.0, z0 + cut.safe),
        moves,
        rpm=cut.rpm,
        station=station,
        meta=PathMeta("delik", "c_indeks", ap=depth),
    )
    tp.validate()
    return tp


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
    tool = live_tool(tool)
    nerede = "Kama kanalı"
    R = _stok(stock)
    _sonlu(nerede, theta=theta, z0=z0, z1=z1)
    _pozitif(nerede, t=t, ap=ap)
    if tool.D >= 2 * R:
        raise CamError(f"{nerede}: kama genişliği (takım çapı {tool.D}) stok çapından küçük olmalı")
    if t >= R:
        raise CamError(f"{nerede}: derinlik t = {t} stok yarıçapından ({R}) küçük olmalı")
    live_station(machine, station, "radyal", cut.rpm)
    c = c_for((math.cos(math.radians(theta)), math.sin(math.radians(theta)), 0.0), "radyal")
    n = max(1, math.ceil(t / ap - 1e-9))
    pts = [(G0, (R + cut.clearance, 0.0, z0), None)]
    ucta, obur = z0, z1
    for i in range(1, n + 1):
        x = R - (t if i == n else i * ap)
        pts.append((G1, (x, 0.0, ucta), cut.plunge_feed))
        if obur != ucta:
            pts.append((G1, (x, 0.0, obur), cut.feed))
            ucta, obur = obur, ucta
    pts.append((G0, (R + cut.safe, 0.0, ucta), None))
    meta = PathMeta("kanal", "c_indeks", ap=min(ap, t))
    return _radyal_yol("kama", tool, cut, c, (R + cut.safe, 0.0, z0), pts, meta, station)


def _alin(tp: Toolpath, name: str, station, machine) -> Toolpath:
    tp = replace(tp, name=name, coord="polar", station=station, meta=PathMeta("alin", "polar"))
    tp.validate()
    if machine is not None:
        polar_check(tp, machine.c_axis)
    return tp


def face_pocket(
    region: Region, tool: Tool, cut: Cut, station: int | None = None, machine: MachineProfile | None = None
) -> Toolpath:
    """Alın cebi (SPEC 03 pocket), coord = "polar"; machine verilirse polar_check. stepover verilmezse
    takım çapının yarısı (SPEC 03 cebi stepover ister)."""
    tool = live_tool(tool)
    live_station(machine, station, "eksenel", cut.rpm)
    if cut.stepover is None:
        cut = replace(cut, stepover=STEPOVER * tool.D)
    return _alin(pocket(region, tool, cut), "alin_cebi", station, machine)


def face_contour(
    profile: Profile,
    tool: Tool,
    cut: Cut,
    side: str,
    station: int | None = None,
    machine: MachineProfile | None = None,
) -> Toolpath:
    """Alın konturu (SPEC 03 contour), coord = "polar"; machine verilirse polar_check."""
    tool = live_tool(tool)
    live_station(machine, station, "eksenel", cut.rpm)
    return _alin(contour(profile, tool, cut, side), f"alin_konturu_{side}", station, machine)


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
    tool = live_tool(tool)
    nerede = "Silindirik kanal"
    if not isinstance(path_sz, Profile):
        raise CamError(f"{nerede}: yol Profile olmalı ({type(path_sz).__name__})")
    _pozitif(nerede, r_ref=r_ref, t=t)
    if t >= r_ref:
        raise CamError(f"{nerede}: derinlik t = {t} r_ref'ten ({r_ref}) küçük olmalı")
    if any(isinstance(s, Arc) for s in path_sz.segments):
        raise CamError(f"{nerede}: açılmış yolda yay yok (yalnız doğrular)")
    live_station(machine, station, "radyal", cut.rpm)
    if machine is not None and not machine.c_axis.continuous:
        raise CamError(f"{nerede}: sürekli olmayan C ekseninde silindirik enterpolasyon yok")
    segs = path_sz.segments
    s0, zz0 = (float(v) for v in segs[0].p0)
    r = r_ref - t
    moves = [Move(G0, (s0, zz0, r_ref + cut.clearance)), Move(G1, (s0, zz0, r), feed=cut.plunge_feed)]
    for sg in segs:
        moves.append(Move(G1, (float(sg.p1[0]), float(sg.p1[1]), r), feed=cut.feed))
    s1, zz1 = (float(v) for v in segs[-1].p1)
    moves.append(Move(G0, (s1, zz1, r_ref + cut.safe)))
    tp = Toolpath(
        "silindirik_kanal",
        tool,
        (s0, zz0, r_ref + cut.safe),
        moves,
        rpm=cut.rpm,
        coord="silindirik",
        cyl_r=float(r_ref),
        station=station,
        meta=PathMeta("kanal", "silindirik", ap=t),
    )
    tp.validate()
    return tp
