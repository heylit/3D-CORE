"""
SPEC 22 — Torna hareket süresi.

G0 ve G94: SPEC 05 kuralı (X = rapid[0], Z = rapid[2]; Y kullanılmaz).
G95 sabit devir: v = F·n/60 [mm/s] → t = 60·L/(F·n), eksen hız sınırıyla.
G96 (css = Vc, rpm = devir sınırı): n(x) = min(1000·Vc/(2π|x|), rpm) → dt/ds = 60/(F·n) = max(k|x|, c),
    k = 60·2π/(1000·Vc·F), c = 60/(F·rpm), geçiş |x| = x* = 1000·Vc/(2π·rpm).
    Doğruda ∫ max(k|x|, c) dx kapalı form (G(y) = ∫₀^y, tek fonksiyon); yayda x = c_x + R·sin θ,
    |x| = x* ve x = 0 açılarında bölünür. accel ile eşdeğer sabit hız v_eş = L/t_G96.
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import ARCS, CamError, FeedMode, Move, MoveType, Toolpath
from cam.sim.timing import Machine, _axis_limit


def zx_arc(p0, p1, center, cw: bool) -> tuple[float, float, float, float, float]:
    """G18 yayı (u, v) = (z, x): (R, |Δθ|, θ0, c_u, c_v). Başlangıç = bitiş ise tam daire."""
    cu, cv = float(center[1]), float(center[0])
    du0, dv0 = p0[2] - cu, p0[0] - cv
    du1, dv1 = p1[2] - cu, p1[0] - cv
    R = math.hypot(du0, dv0)
    th0 = math.atan2(dv0, du0)
    dth = math.atan2(dv1, du1) - th0
    if cw:
        dth = -dth
    dth %= 2 * math.pi
    if dth < 1e-12:
        dth = 2 * math.pi
    return R, dth, th0, cu, cv


def _G(y: float, k: float, c: float, xs: float) -> float:
    """∫₀^y max(k·x, c) dx, y ≥ 0."""
    if y <= xs:
        return c * y
    return c * xs + k * (y * y - xs * xs) / 2


def _F(x: float, k: float, c: float, xs: float) -> float:
    """∫₀^x max(k|t|, c) dt (tek fonksiyon)."""
    return math.copysign(_G(abs(x), k, c, xs), x)


def _css_line(x0: float, x1: float, L: float, k: float, c: float, xs: float) -> float:
    if x0 == x1:
        return L * max(k * abs(x0), c)
    lo, hi = min(x0, x1), max(x0, x1)
    return L / (hi - lo) * (_F(hi, k, c, xs) - _F(lo, k, c, xs))


def _css_arc(R: float, ta: float, tb: float, cv: float, k: float, c: float, xs: float) -> float:
    """∫_{ta}^{tb} max(k|c_v + R sin θ|, c)·R dθ, parça parça kapalı form."""
    kes = {ta, tb}
    for val in (-xs, 0.0, xs):
        q = (val - cv) / R
        if -1.0 <= q <= 1.0:
            base = math.asin(q)
            for th in (base, math.pi - base):
                n0 = math.ceil((ta - th) / (2 * math.pi))
                n1 = math.floor((tb - th) / (2 * math.pi))
                for n in range(n0, n1 + 1):
                    t = th + 2 * math.pi * n
                    if ta < t < tb:
                        kes.add(t)
    pts = sorted(kes)
    t = 0.0
    for a, b in zip(pts[:-1], pts[1:], strict=True):
        m = cv + R * math.sin(0.5 * (a + b))
        if abs(m) <= xs:
            t += c * R * (b - a)
        else:
            sg = 1.0 if m > 0 else -1.0
            t += sg * k * R * (cv * (b - a) - R * (math.cos(b) - math.cos(a)))
    return t


def _accel(L: float, v: float, a: float | None) -> float:
    if a is None:
        return L / v
    if L >= v * v / a:
        return L / v + v / a
    return 2 * math.sqrt(L / a)


def lathe_move_time(p0, p1, move: Move, path: Toolpath, machine: Machine) -> float:
    """Tek hareketin süresi [s] (path.feed_mode, css, rpm buradan)."""
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    arc = None
    if move.type in ARCS:
        arc = zx_arc(p0, p1, move.center, move.type is MoveType.ARC_CW)
        R, dth = arc[0], arc[1]
        L = math.hypot(R * dth, p1[1] - p0[1])
    else:
        L = float(np.linalg.norm(p1 - p0))
    if L == 0:
        return 0.0
    if move.type is MoveType.RAPID:
        return _accel(L, _axis_limit((p1 - p0) / L, machine.rapid) / 60, machine.accel)
    F = move.feed
    if F is None or not F > 0:
        raise CamError(f"Hareket ({move.type.value}): ilerleme pozitif olmalı (feed={F})")
    if path.feed_mode is FeedMode.PER_REV:
        if not path.rpm > 0:
            raise CamError(f"Yol '{path.name}': G95'te devir (rpm) pozitif olmalı")
        if path.css is not None:
            Vc = float(path.css)
            k = 60 * 2 * math.pi / (1000 * Vc * F)
            c = 60 / (F * path.rpm)
            xs = 1000 * Vc / (2 * math.pi * path.rpm)
            if arc is None:
                t = _css_line(float(p0[0]), float(p1[0]), L, k, c, xs)
            else:
                R, dth, th0, _, cv = arc
                ta, tb = (th0 - dth, th0) if move.type is MoveType.ARC_CW else (th0, th0 + dth)
                t = _css_arc(R, ta, tb, cv, k, c, xs) * L / (R * dth)
            if machine.accel is None:
                return t
            return _accel(L, L / t, machine.accel)
        v = F * path.rpm / 60
    else:
        v = F / 60
    if arc is None:
        v = min(v, _axis_limit((p1 - p0) / L, machine.rapid) / 60)
    else:
        v = min(v, min(machine.rapid[0], machine.rapid[2]) / 60)
        if machine.accel is not None:
            v = min(v, math.sqrt(machine.accel * arc[0]))
    return _accel(L, v, machine.accel)
