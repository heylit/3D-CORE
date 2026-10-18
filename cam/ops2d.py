"""
SPEC 03 — 2.5D işlemler: yüz alma, kontur, kontur-paralel cep.

Takım yarıçapı telafisi CAM tarafında yapılır: yol takım MERKEZİNİN yoludur (ofsetlenmiş profil).
Kesme yönü: iş mili M3 (saat yönü) varsayılır; tırmanma frezeleme = malzeme ilerleme yönünün SAĞINDA.
Profillerin XY düzleminde olduğu varsayılır (profil u, v → X, Y).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.geom2d import LINK_TOL, TOL, closest, intersect
from cam.model import CamError, Move, MoveType, Stock, Tool, ToolKind, Toolpath
from cam.offset import offset
from cam.profile import Arc, Line, Profile, Region, Segment


@dataclass
class Cut:
    """Kesme parametreleri [mm, mm/dk, dev/dk]."""

    z_top: float
    z_bottom: float
    a_p: float  # en büyük paso derinliği
    feed: float  # XY kesme ilerlemesi
    plunge_feed: float  # Z dalma ilerlemesi
    rpm: float
    z_safe: float  # hızlı hareket yüksekliği
    clearance: float = 1.0  # dalmadan önce son paso üstünde bırakılan mesafe
    stepover: float | None = None  # yan paso s (cep, yüz alma)

    def __post_init__(self) -> None:
        if not self.z_top > self.z_bottom:
            raise CamError(f"z_top > z_bottom olmalı ({self.z_top}, {self.z_bottom})")
        for name in ("a_p", "feed", "plunge_feed", "rpm"):
            if not getattr(self, name) > 0:
                raise CamError(f"Cut.{name} pozitif olmalı ({getattr(self, name)})")
        if not self.z_safe > self.z_top:
            raise CamError(f"z_safe > z_top olmalı ({self.z_safe}, {self.z_top})")
        if self.clearance < 0:
            raise CamError(f"clearance negatif olamaz ({self.clearance})")
        if self.stepover is not None and not self.stepover > 0:
            raise CamError(f"stepover pozitif olmalı ({self.stepover})")


def depths(z_top: float, z_bottom: float, a_p: float) -> list[float]:
    """Eşit paso derinlikleri: n = ⌈H / a_p⌉, z_i = z_top − i·H/n; son derinlik tam z_bottom."""
    H = z_top - z_bottom
    if H <= 0 or a_p <= 0:
        raise CamError(f"depths: H > 0 ve a_p > 0 olmalı (H={H}, a_p={a_p})")
    n = max(1, math.ceil(H / a_p - 1e-9))
    zs = [z_top - i * H / n for i in range(1, n + 1)]
    zs[-1] = float(z_bottom)
    return zs


def _check_tool(tool: Tool) -> float:
    if tool.kind is not ToolKind.FLAT:
        raise CamError(f"SPEC 03 sadece düz parmak freze kabul eder ({tool.kind.value})")
    return tool.D / 2


def _stepover(cut: Cut, tool: Tool) -> float:
    s = cut.stepover
    if s is None:
        raise CamError("Bu işlem için stepover gerekli")
    if s > tool.D + TOL:
        raise CamError(f"stepover takım çapından büyük olamaz (s={s}, D={tool.D})")
    return s


# ---------------------------------------------------------------- hareket kurucu


@dataclass
class _Builder:
    cut: Cut
    moves: list[Move] = field(default_factory=list)
    pos: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def _go(self, mt: MoveType, p, feed=None, center=None) -> None:
        p = np.asarray(p, dtype=float)
        if center is None and np.linalg.norm(p - self.pos) < TOL:
            return
        c = None if center is None else (float(center[0]), float(center[1]))
        self.moves.append(Move(mt, tuple(p), feed, c))
        self.pos = p

    def rapid(self, x, y, z) -> None:
        self._go(MoveType.RAPID, (x, y, z))

    def line(self, x, y, z, feed=None) -> None:
        self._go(MoveType.LINEAR, (x, y, z), feed or self.cut.feed)

    def segment(self, s: Segment, z: float) -> None:
        if isinstance(s, Arc):
            mt = MoveType.ARC_CCW if s.ccw else MoveType.ARC_CW
            self._go(mt, (s.p1[0], s.p1[1], z), self.cut.feed, s.c)
        else:
            self.line(s.p1[0], s.p1[1], z)

    def retract(self) -> None:
        if self.pos[2] < self.cut.z_safe:
            self.rapid(self.pos[0], self.pos[1], self.cut.z_safe)

    def enter(self, p, z: float, z_prev: float) -> None:
        """z_safe'te p üstüne hızlı, z_prev + clearance'a hızlı iniş, z'ye dalma ilerlemesiyle."""
        self.retract()
        self.rapid(p[0], p[1], self.cut.z_safe)
        self.rapid(p[0], p[1], max(z_prev + self.cut.clearance, z))
        self.line(p[0], p[1], z, self.cut.plunge_feed)

    def loop(self, segs: list[Segment], z: float) -> None:
        for s in segs:
            self.segment(s, z)

    def toolpath(self, name: str, tool: Tool, start) -> Toolpath:
        self.retract()
        tp = Toolpath(name=name, tool=tool, start=start, moves=self.moves, rpm=self.cut.rpm)
        tp.validate()
        return tp


def _start_builder(cut: Cut, p) -> tuple[_Builder, tuple[float, float, float]]:
    """Yol z_safe'te, ilk giriş noktasının üstünde başlar."""
    b = _Builder(cut)
    start = (float(p[0]), float(p[1]), float(cut.z_safe))
    b.pos = np.array(start)
    return b, start


# ---------------------------------------------------------------- yüz alma


def face(stock: Stock, tool: Tool, cut: Cut) -> Toolpath:
    """X'e paralel zigzag; m = ⌈Ly/s⌉ + 1 eşit aralıklı sıra, ilk ve son sıra kenarda."""
    r = _check_tool(tool)
    s = _stepover(cut, tool)
    Ly = stock.ymax - stock.ymin
    m = math.ceil(Ly / s - 1e-9) + 1
    ys = [stock.ymin + j * Ly / (m - 1) for j in range(m)]
    xa = stock.xmin - r - cut.clearance
    xb = stock.xmax + r + cut.clearance
    b, start = _start_builder(cut, (xa, ys[0]))
    z_prev = cut.z_top
    for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
        b.enter((xa, ys[0]), z, z_prev)
        x = xa
        for j, y in enumerate(ys):
            if j > 0:
                b.line(x, y, z)
            x = xb if x == xa else xa
            b.line(x, y, z)
        b.retract()
        z_prev = z
    return b.toolpath("yuz_alma", tool, start)


# ---------------------------------------------------------------- kontur


def contour(profile: Profile, tool: Tool, cut: Cut, side: str, climb: bool = True) -> Toolpath:
    """Kontur: side = "dis" (−r ofset), "ic" (+r ofset), "uzerinde" (ofsetsiz).

    Tırmanma: dış kontur CW, iç kontur CCW; climb=False tersi.
    """
    r = _check_tool(tool)
    if not tool.center_cutting:
        raise NotImplementedError("SPEC 03 Ek A2: merkezden kesmeyen takım")
    if side not in ("dis", "ic", "uzerinde"):
        raise CamError(f"contour: side 'dis', 'ic' veya 'uzerinde' olmalı ({side!r})")
    if side == "uzerinde":
        loops = [profile.segments]
    else:
        if not profile.closed:
            raise CamError("contour: açık profilde sadece 'uzerinde' kullanılabilir")
        reg = Region(profile)
        if side == "dis":
            loops = [rg.outer.reversed().segments for rg in offset(reg, -r)]  # CW
        else:
            res = offset(reg, r)
            if not res:
                raise CamError("contour: takım iç kontura sığmıyor")
            loops = [rg.outer.segments for rg in res]  # CCW
        if not climb:
            loops = [Profile(lp).reversed().segments for lp in loops]
    b, start = _start_builder(cut, loops[0][0].p0)
    z_prev = cut.z_top
    for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
        for lp in loops:
            b.enter(lp[0].p0, z, z_prev)
            b.loop(lp, z)
            b.retract()
        z_prev = z
    return b.toolpath(f"kontur_{side}", tool, start)


# ---------------------------------------------------------------- cep


INRADIUS_TOL = 1e-9  # iç yarıçap ikiye bölme hassasiyeti (D'ye göre)


@dataclass
class _Node:
    region: Region
    children: list[_Node] = field(default_factory=list)


def _inradius(region: Region, hi: float, tol: float) -> float:
    """offset(region, t) boşalan en küçük t'nin üst sınırı (ikiye bölme). offset(region, hi) boş olmalı."""
    lo = 0.0
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if offset(region, mid):
            lo = mid
        else:
            hi = mid
    return hi


def _build_tree(region: Region, r: float, s: float, D: float) -> _Node:
    node = _Node(region)
    for child in offset(region, s):
        node.children.append(_build_tree(child, r, s, D))
    if not node.children:
        # yaprak: ortada r'den geniş kesilmemiş alan kalmasın
        t_star = _inradius(region, s, INRADIUS_TOL * D)
        t_extra = t_star - r + LINK_TOL  # ikiye bölmenin erken "boş" demesine karşı pay
        if t_extra > TOL:
            node.children = [_Node(c) for c in offset(region, t_extra)]
    return node


def _rotate(segs: list[Segment], i: int, t: float) -> list[Segment]:
    """Halkayı i. parçanın t noktasından başlayacak şekilde döndürür."""
    s = segs[i]
    L = s.length
    head, tail = [], []
    if t * L > LINK_TOL and (1 - t) * L > LINK_TOL:
        a, b = s.split(t)
        head, tail = [b], [a]
    elif t * L <= LINK_TOL:
        head = [s]
    else:
        tail = [s]
    rest = segs[i + 1 :] + segs[:i]
    return head + rest + tail


def _nearest_on(segs: list[Segment], q) -> tuple[int, float, np.ndarray]:
    best = None
    for i, s in enumerate(segs):
        t, d = closest(q, s)
        if best is None or d < best[0] - TOL:
            best = (d, i, t)
    _, i, t = best
    return i, t, segs[i].point(t)


def _link_ok(q, p, region: Region) -> bool:
    """q → p düz çizgisi bölgenin geçerli merkez kümesinin içinde mi (halkaları sadece p'de keser)."""
    if np.hypot(*(p - q)) <= LINK_TOL:
        return True
    ln = Line(q, p)
    for loop in region.loops:
        for s in loop.segments:
            for tl, _ in intersect(ln, s):
                if LINK_TOL < tl * ln.length < ln.length - LINK_TOL:
                    return False
    return region.contains(ln.point(0.5))


def pocket(region: Region, tool: Tool, cut: Cut, climb: bool = True) -> Toolpath:
    """Kontur-paralel cep: halkalar d_k = r + k·s, içten dışa; halkalar arası mümkünse inmeden geçiş."""
    r = _check_tool(tool)
    s = _stepover(cut, tool)
    if not tool.center_cutting:
        raise NotImplementedError("SPEC 03 Ek A2: merkezden kesmeyen takım")
    if s > r + TOL:
        raise NotImplementedError("SPEC 03 Ek A1: cepte yan paso en fazla D/2")
    first = offset(region, r)
    if not first:
        raise CamError("pocket: takım cebe sığmıyor")
    roots = [_build_tree(rg, r, s, tool.D) for rg in first]

    def loops_of(node: _Node) -> list[list[Segment]]:
        lps = [h.segments for h in node.region.holes] + [node.region.outer.segments]
        if not climb:
            lps = [Profile(lp).reversed().segments for lp in lps]
        return lps

    def leaf_start(node: _Node):
        while node.children:
            node = node.children[0]
        return loops_of(node)[0][0].p0

    b, start = _start_builder(cut, leaf_start(roots[0]))
    state = {"z": 0.0, "z_prev": 0.0, "down": False}

    def cut_loop(lp: list[Segment], link_region: Region | None) -> None:
        z = state["z"]
        if state["down"] and link_region is not None:
            q = b.pos[:2]
            i, t, p = _nearest_on(lp, q)
            if _link_ok(q, p, link_region):
                lp = _rotate(lp, i, t)
                b.line(lp[0].p0[0], lp[0].p0[1], z)
                b.loop(lp, z)
                return
        b.enter(lp[0].p0, z, state["z_prev"])
        state["down"] = True
        b.loop(lp, z)

    def cut_node(node: _Node) -> None:
        for k, child in enumerate(node.children):
            if k > 0:
                b.retract()
                state["down"] = False
            cut_node(child)
        for lp in loops_of(node):
            cut_loop(lp, node.region)

    z_prev = cut.z_top
    for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
        state.update(z=z, z_prev=z_prev, down=False)
        for root in roots:
            b.retract()
            state["down"] = False
            cut_node(root)
        b.retract()
        z_prev = z
    return b.toolpath("cep", tool, start)
