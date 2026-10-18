"""SPEC 28 testleri için bağımsız referans hesaplar (cam.turn_profile'a güvenmeden).

Bu modül test değildir (adı test_ ile başlamaz). Sadece numpy, scipy, cam/profile.py (Line, Arc, Profile) ve
tests/cam/ref2d.py kullanır. Koordinatlar (u, v) = (z, x).

Formüller:
- Pappus–Guldin hacmi: V_P = 2π ∬ x dA; CCW halkada Green teoremiyle ∬ x dA = −½ ∮ x² dz.
- Pappus–Guldin yüzey alanı: S_P = 2π Σ ∫ x ds (eksen üzerindeki x = 0 kenarları katkı vermez zaten).
- Kenar integralleri Gauss–Legendre ile (40 nokta): doğruda integrand polinom (tam), yayda trigonometrik
  (40 noktada makine duyarlığı).
"""

from __future__ import annotations

import math

import numpy as np

from cam.profile import Arc, Line, Profile
from tests.cam.ref2d import Egriler, arc_ccw_form

TWO_PI = 2.0 * math.pi
_GL_T, _GL_W = np.polynomial.legendre.leggauss(40)
_GL_T = 0.5 * (_GL_T + 1.0)  # [0, 1]
_GL_W = 0.5 * _GL_W


def arc_form(s: Arc) -> tuple[np.ndarray, float, float, float]:
    """Yay → (merkez, R, θ_başlangıç (p0 açısı), işaretli süpürme); ccw → +, cw → −."""
    c = np.asarray(s.c, dtype=float)
    p0, p1 = np.asarray(s.p0, dtype=float), np.asarray(s.p1, dtype=float)
    R = float(np.hypot(*(p0 - c)))
    t0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    t1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    if np.hypot(*(p0 - p1)) < 1e-12:
        sw = TWO_PI
    else:
        sw = ((t1 - t0) if s.ccw else (t0 - t1)) % TWO_PI
    return c, R, t0, sw if s.ccw else -sw


def seg_points(s, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Parça üzerinde t ∈ [0, 1] noktaları ve dp/dt türevi, (n, 2) ve (n, 2)."""
    t = np.asarray(t, dtype=float)
    if isinstance(s, Line):
        p0, p1 = np.asarray(s.p0, dtype=float), np.asarray(s.p1, dtype=float)
        P = p0[None, :] + t[:, None] * (p1 - p0)[None, :]
        dP = np.repeat((p1 - p0)[None, :], len(t), axis=0)
        return P, dP
    c, R, t0, sw = arc_form(s)
    th = t0 + sw * t
    P = c[None, :] + R * np.stack([np.cos(th), np.sin(th)], axis=1)
    dP = R * sw * np.stack([-np.sin(th), np.cos(th)], axis=1)
    return P, dP


def sample(profile: Profile, n: int = 200) -> np.ndarray:
    """Her parçadan n nokta (uçlar dahil), (m, 2)."""
    t = np.linspace(0.0, 1.0, n)
    return np.vstack([seg_points(s, t)[0] for s in profile.segments])


def int_x2_dz(profile: Profile) -> float:
    """∮ x² dz."""
    tot = 0.0
    for s in profile.segments:
        P, dP = seg_points(s, _GL_T)
        tot += float(np.sum(_GL_W * P[:, 1] ** 2 * dP[:, 0]))
    return tot


def pappus_V(section: Profile) -> float:
    """V_P = 2π · (−½ ∮ x² dz); kesit CCW."""
    return 2.0 * math.pi * (-0.5 * int_x2_dz(section))


def pappus_S(section: Profile) -> float:
    """S_P = 2π Σ ∫ x ds."""
    tot = 0.0
    for s in section.segments:
        P, dP = seg_points(s, _GL_T)
        tot += float(np.sum(_GL_W * P[:, 1] * np.hypot(dP[:, 0], dP[:, 1])))
    return 2.0 * math.pi * tot


def shoelace_area(section: Profile) -> float:
    """Yönlü alan ½ ∮ (z dx − x dz), Gauss–Legendre ile."""
    tot = 0.0
    for s in section.segments:
        P, dP = seg_points(s, _GL_T)
        tot += float(np.sum(_GL_W * (P[:, 0] * dP[:, 1] - P[:, 1] * dP[:, 0])))
    return 0.5 * tot


def egriler(segments) -> Egriler:
    """Parça listesi → ref2d.Egriler (noktadan kesin uzaklık için)."""
    e = Egriler()
    for s in segments:
        if isinstance(s, Line):
            e.line(s.p0, s.p1)
        else:
            R, th0, sw = arc_ccw_form(s.p0, s.p1, s.c, cw=not s.ccw)
            e.arc(s.c, R, th0, sw)
    return e


def chain_points(profile: Profile) -> list[np.ndarray]:
    """Zincirin köşe noktaları: p0'lar + son p1."""
    return [np.asarray(s.p0) for s in profile.segments] + [np.asarray(profile.segments[-1].p1)]


def assert_lines(profile: Profile, pts, tol: float = 1e-9) -> None:
    """Profil tam olarak pts köşeli doğrulardan oluşur (sıra ve yön dahil)."""
    pts = [np.asarray(p, dtype=float) for p in pts]
    segs = profile.segments
    assert len(segs) == len(pts) - 1, f"parça sayısı {len(segs)} ≠ {len(pts) - 1}: {describe(profile)}"
    for i, s in enumerate(segs):
        assert isinstance(s, Line), f"parça {i} doğru değil: {describe(profile)}"
        np.testing.assert_allclose(s.p0, pts[i], atol=tol, rtol=0)
        np.testing.assert_allclose(s.p1, pts[i + 1], atol=tol, rtol=0)


def describe(profile: Profile | None) -> str:
    if profile is None:
        return "None"
    out = []
    for s in profile.segments:
        if isinstance(s, Line):
            out.append(f"L{tuple(np.round(s.p0, 6))}->{tuple(np.round(s.p1, 6))}")
        else:
            c = tuple(np.round(s.c, 6))
            out.append(f"A{tuple(np.round(s.p0, 6))}->{tuple(np.round(s.p1, 6))} c{c} ccw={s.ccw}")
    return " | ".join(out)
