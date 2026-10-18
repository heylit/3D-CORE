"""
SPEC 41 — iş düzlemi (Frame) kurucuları, Euler açıları ve 3+2 indeksli işleme akışı.

ZXZ: R = Rz(α)·Rx(β)·Rz(γ) (Fanuc G68.2). XYZ sabit eksen: R = Rz(c)·Ry(b)·Rx(a) (Heidenhain PLANE SPATIAL).
`Frame.R` satır satır saklanır; matrisin sütunları yerel x, y, z eksenleridir (p_w = o + R·p_l).
"""

from __future__ import annotations

import itertools
import math

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import (
    ARCS,
    CamError,
    Frame,
    Kinematics,
    Move,
    MoveType,
    Plane,
    Stock,
    Toolpath,
    Wcs,
)
from cam.multiaxis.kinematics import inverse, inverse_axes, rotation

TOL = 1e-9
_EX, _EY, _EZ = np.eye(3)


def _frame(o, R: np.ndarray) -> Frame:
    return Frame(origin=tuple(float(v) for v in o), R=tuple(tuple(float(v) for v in r) for r in R))


def _R(frame: Frame) -> np.ndarray:
    return np.array(frame.R, dtype=float)


# ---------------------------------------------------------------- kurucular ve açılar


def from_normal(o, n, x_hint) -> Frame:
    """z = n/|n|, x = x_hint'in z'ye dik bileşeni (birim), y = z × x."""
    n = np.asarray(n, dtype=float)
    x_hint = np.asarray(x_hint, dtype=float)
    if not (np.all(np.isfinite(n)) and np.all(np.isfinite(x_hint))):
        raise CamError("İş düzlemi: n ve x_hint sonlu olmalı")
    nn = float(np.linalg.norm(n))
    if nn < TOL:
        raise CamError("İş düzlemi: normal sıfır olamaz")
    z = n / nn
    xh = float(np.linalg.norm(x_hint))
    if xh < TOL or np.linalg.norm(np.cross(x_hint, z)) < TOL * xh:
        raise CamError(f"İş düzlemi: x ipucu normale paralel olamaz (x_hint={tuple(x_hint)})")
    x = x_hint - (x_hint @ z) * z
    x /= np.linalg.norm(x)
    return _frame(o, np.column_stack([x, np.cross(z, x), z]))


def from_zxz(o, alpha: float, beta: float, gamma: float) -> Frame:
    """R = Rz(α)·Rx(β)·Rz(γ), açılar derece."""
    return _frame(o, rotation(_EZ, alpha) @ rotation(_EX, beta) @ rotation(_EZ, gamma))


def from_xyz(o, a: float, b: float, c: float) -> Frame:
    """R = Rz(c)·Ry(b)·Rx(a), açılar derece."""
    return _frame(o, rotation(_EZ, c) @ rotation(_EY, b) @ rotation(_EX, a))


def zxz_angles(frame: Frame) -> tuple[float, float, float]:
    """(α, β, γ) [derece], β ∈ [0°, 180°]; tekilde (sin β ≈ 0) γ = 0."""
    R = _R(frame)
    sb = math.hypot(R[0, 2], R[1, 2])
    beta = math.atan2(sb, R[2, 2])
    if sb > TOL:
        alpha = math.atan2(R[0, 2], -R[1, 2])
        gamma = math.atan2(R[2, 0], R[2, 1])
    else:
        alpha, gamma = math.atan2(R[1, 0], R[0, 0]), 0.0
    return math.degrees(alpha), math.degrees(beta), math.degrees(gamma)


def xyz_angles(frame: Frame) -> tuple[float, float, float]:
    """(a, b, c) [derece], b ∈ [−90°, 90°]; tekilde (cos b ≈ 0) c = 0."""
    R = _R(frame)
    cb = math.hypot(R[0, 0], R[1, 0])
    b = math.atan2(-R[2, 0], cb)
    if cb > TOL:
        a = math.atan2(R[2, 1], R[2, 2])
        c = math.atan2(R[1, 0], R[0, 0])
    else:
        a, c = math.atan2(-R[1, 2], R[1, 1]), 0.0
    return math.degrees(a), math.degrees(b), math.degrees(c)


# ---------------------------------------------------------------- yerel stok ve ağ


def local_stock(stock: Stock, frame: Frame) -> Stock:
    """Stok köşelerinin yerel çerçevedeki sınır kutusu (güvenli taraf)."""
    K = np.array(
        list(itertools.product((stock.xmin, stock.xmax), (stock.ymin, stock.ymax), (stock.zmin, stock.zmax)))
    )
    Kl = frame.to_local(K)
    lo, hi = Kl.min(axis=0), Kl.max(axis=0)
    return Stock(*(float(v) for v in lo), *(float(v) for v in hi))


def local_mesh(mesh: TriMesh, frame: Frame) -> TriMesh:
    """Üçgen ağı WCS → yerel."""
    return TriMesh(V=frame.to_local(mesh.V), T=mesh.T.copy())


# ---------------------------------------------------------------- 3+2 akışı


def _yay_noktalari(p0: np.ndarray, m: Move, arc_tol: float) -> list[np.ndarray]:
    """XY yayını kirişlere böler (SPEC 05 kuralı): n = ⌈|Δθ| / (2·acos(1 − ε/r))⌉; bitiş noktaları."""
    p1 = np.array(m.end, dtype=float)
    c = np.array(m.center, dtype=float)
    v0, v1 = p0[:2] - c, p1[:2] - c
    r = float(np.hypot(*v0))
    cw = m.type is MoveType.ARC_CW
    dth = math.atan2(v1[1], v1[0]) - math.atan2(v0[1], v0[0])
    if cw:
        dth = -dth
    dth %= 2 * math.pi
    if dth < 1e-12:
        dth = 2 * math.pi
    adim = 2 * math.acos(1 - arc_tol / r) if arc_tol < r else math.pi / 2
    n = max(1, math.ceil(dth / adim))
    th0 = math.atan2(v0[1], v0[0])
    isaret = -1.0 if cw else 1.0
    pts = []
    for k in range(1, n + 1):
        if k == n:
            pts.append(p1)
            continue
        t = k / n
        th = th0 + isaret * dth * t
        pts.append(np.array([c[0] + r * math.cos(th), c[1] + r * math.sin(th), p0[2] + t * (p1[2] - p0[2])]))
    return pts


def _cerceve(tp: Toolpath) -> Frame:
    if tp.plane is not Plane.XY:
        raise CamError(f"Takım yolu '{tp.name}': çok eksen akışı yalnız XY (G17) düzleminde")
    return tp.frame if tp.frame is not None else _frame((0.0, 0.0, 0.0), np.eye(3))


def _eksen(fr: Frame, m: Move) -> tuple[float, float, float]:
    a = (0.0, 0.0, 1.0) if m.axis is None else m.axis
    return tuple(float(v) for v in fr.to_world_vec(a))


def to_world(tp: Toolpath, arc_tol: float = 1e-3) -> Toolpath:
    """Yerel çerçeveli yol → WCS (frame = None, her Move.axis dolu, yaylar kirişlere bölünür)."""
    if not (math.isfinite(arc_tol) and arc_tol > 0):
        raise CamError(f"to_world: arc_tol pozitif olmalı ({arc_tol})")
    tp.validate()
    fr = _cerceve(tp)
    moves = []
    p0 = np.array(tp.start, dtype=float)
    for m in tp.moves:
        a = _eksen(fr, m)
        if m.type in ARCS:
            for q in _yay_noktalari(p0, m, arc_tol):
                moves.append(Move(MoveType.LINEAR, tuple(fr.to_world(q)), feed=m.feed, axis=a))
        else:
            moves.append(Move(m.type, tuple(fr.to_world(m.end)), feed=m.feed, axis=a))
        p0 = np.array(m.end, dtype=float)
    return Toolpath(
        name=tp.name,
        tool=tp.tool,
        start=tuple(fr.to_world(tp.start)),
        moves=moves,
        rpm=tp.rpm,
        plane=Plane.XY,
        feed_mode=tp.feed_mode,
        css=tp.css,
        frame=None,
    )


def to_machine(
    tp: Toolpath, kin: Kinematics, wcs: Wcs, L: float, prev: tuple[float, ...] | None = None
) -> np.ndarray:
    """Her nokta için eklem değerleri, (n+1, 3 + k); başlangıç ilk hareketin ekseniyle."""
    fr = _cerceve(tp)
    P = fr.to_world(tp.points())
    A = [_eksen(fr, m) for m in tp.moves]
    A = [A[0] if A else _eksen(fr, Move(MoveType.RAPID, tp.start))] + A
    Q = []
    for p, a in zip(P, A, strict=True):
        q = inverse(kin, p, a, L, wcs, prev)
        prev = tuple(float(v) for v in q[3:])
        Q.append(q)
    return np.array(Q)


def machine_toolpath(
    tp: Toolpath, kin: Kinematics, wcs: Wcs, L: float, prev: tuple[float, ...] | None = None
) -> tuple[Toolpath, tuple[float, ...]]:
    """Sabit yönlü 3+2 yolu makine koordinatında (G17) ve sabit açılar.

    Noktalar eklem XYZ değerleridir: X = W(p_w + o_wcs) − H_rot(tip₀). Masa döndürmesi yerel z'yi
    iş miline taşıyan katı hareket olduğundan yaylar yay kalır, merkez aynı dönüşümle taşınır.
    Kafada döner eksen varken yaylı yol → CamError.
    """
    tp.validate()
    fr = _cerceve(tp)
    eksenler = {_eksen(fr, m) for m in tp.moves} or {_eksen(fr, Move(MoveType.RAPID, tp.start))}
    a0 = np.array(next(iter(eksenler)))
    if any(np.max(np.abs(np.array(a) - a0)) > TOL for a in eksenler):
        raise CamError(f"Takım yolu '{tp.name}': 3+2 makine yolunda takım ekseni sabit olmalı")
    yayli = any(m.type in ARCS for m in tp.moves)
    if yayli and any(e.carrier == "kafa" for e in kin.rotary):
        raise CamError(f"Takım yolu '{tp.name}': kafada döner eksen varken yaylar makine XY'sinde kalmaz")
    acilar = tuple(inverse_axes(kin, a0, prev))

    def makine(p_l) -> np.ndarray:
        return inverse(kin, fr.to_world(p_l), a0, L, wcs, acilar)[:3]

    moves = []
    for m in tp.moves:
        center = None
        if m.center is not None:
            c = makine((m.center[0], m.center[1], m.end[2]))
            center = (float(c[0]), float(c[1]))
        moves.append(Move(m.type, tuple(float(v) for v in makine(m.end)), feed=m.feed, center=center))
    mt = Toolpath(
        name=tp.name,
        tool=tp.tool,
        start=tuple(float(v) for v in makine(tp.start)),
        moves=moves,
        rpm=tp.rpm,
        plane=Plane.XY,
        feed_mode=tp.feed_mode,
        css=tp.css,
        frame=None,
    )
    return mt, acilar
