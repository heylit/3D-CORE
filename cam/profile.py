"""
SPEC 03 — 2D profiller: doğru ve yay parçaları, kapalı/açık zincirler, adalı bölgeler.

Profiller düzlemden bağımsızdır (u, v koordinatları): frezede XY, ileride tornada XZ olarak kullanılır.
Yön kuralı (Region): bölgenin içi her halkanın solundadır → dış halka CCW, iç halkalar (ada/delik) CW.

Birimler: mm, açı radyan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.geom2d import AREA_TOL, LINK_TOL, TOL, TWO_PI, winding
from cam.model import ARC_TOL, R_MIN, CamError


def _pt(p) -> np.ndarray:
    a = np.asarray(p, dtype=float).reshape(-1)
    if a.shape != (2,) or not np.all(np.isfinite(a)):
        raise CamError(f"2D nokta bekleniyor: {p}")
    return a


def _same(p, q, tol: float = LINK_TOL) -> bool:
    return float(np.hypot(*(np.asarray(p) - np.asarray(q)))) <= tol


@dataclass(frozen=True, eq=False)
class Line:
    """Doğru parçası p0 → p1."""

    p0: np.ndarray
    p1: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "p0", _pt(self.p0))
        object.__setattr__(self, "p1", _pt(self.p1))
        if self.length < TOL:
            raise CamError(f"Doğru parçası sıfır boylu: {self.p0} → {self.p1}")

    @property
    def length(self) -> float:
        return float(np.hypot(*(self.p1 - self.p0)))

    def point(self, t: float) -> np.ndarray:
        return self.p0 + t * (self.p1 - self.p0)

    def tangent(self, t: float) -> np.ndarray:
        """Birim teğet (ilerleme yönü)."""
        return (self.p1 - self.p0) / self.length

    def reversed(self) -> Line:
        return Line(self.p1, self.p0)

    def split(self, t: float) -> tuple[Line, Line]:
        m = self.point(t)
        return Line(self.p0, m), Line(m, self.p1)

    def sub(self, t0: float, t1: float) -> Line:
        return Line(self.point(t0), self.point(t1))


@dataclass(frozen=True, eq=False)
class Arc:
    """Merkezi c olan yay p0 → p1; ccw=True saat yönü tersi. p0 = p1 ise tam daire."""

    p0: np.ndarray
    p1: np.ndarray
    c: np.ndarray
    ccw: bool = True

    def __post_init__(self) -> None:
        for k in ("p0", "p1", "c"):
            object.__setattr__(self, k, _pt(getattr(self, k)))
        object.__setattr__(self, "ccw", bool(self.ccw))
        R0 = float(np.hypot(*(self.p0 - self.c)))
        R1 = float(np.hypot(*(self.p1 - self.c)))
        if R0 < R_MIN:
            raise CamError(f"Yay yarıçapı sıfır (merkez {self.c})")
        if abs(R0 - R1) > ARC_TOL:
            raise CamError(f"Yay yarıçapları tutmuyor (R0={R0}, R1={R1})")
        full = _same(self.p0, self.p1, TOL)
        a0 = math.atan2(self.p0[1] - self.c[1], self.p0[0] - self.c[0])
        a1 = math.atan2(self.p1[1] - self.c[1], self.p1[0] - self.c[0])
        sweep = TWO_PI if full else ((a1 - a0) if self.ccw else (a0 - a1)) % TWO_PI
        if sweep * R0 < TOL:
            raise CamError("Yay sıfır boylu")
        object.__setattr__(self, "R", R0)
        object.__setattr__(self, "a0", a0)
        object.__setattr__(self, "sweep", sweep)
        object.__setattr__(self, "full", full)

    @property
    def length(self) -> float:
        return self.R * self.sweep

    def _angle(self, t: float) -> float:
        return self.a0 + (1 if self.ccw else -1) * t * self.sweep

    def point(self, t: float) -> np.ndarray:
        if t >= 1.0:
            return self.p1.copy()
        if t <= 0.0:
            return self.p0.copy()
        a = self._angle(t)
        return self.c + self.R * np.array([math.cos(a), math.sin(a)])

    def tangent(self, t: float) -> np.ndarray:
        a = self._angle(t)
        tv = np.array([-math.sin(a), math.cos(a)])
        return tv if self.ccw else -tv

    def reversed(self) -> Arc:
        return Arc(self.p1, self.p0, self.c, not self.ccw)

    def split(self, t: float) -> tuple[Arc, Arc]:
        m = self.point(t)
        return Arc(self.p0, m, self.c, self.ccw), Arc(m, self.p1, self.c, self.ccw)

    def sub(self, t0: float, t1: float) -> Arc:
        return Arc(self.point(t0), self.point(t1), self.c, self.ccw)


Segment = Line | Arc


def segment_area(s: Segment) -> float:
    """Green teoremi katkısı: ½(x₀y₁ − x₁y₀) + yayda ±½R²(Δθ − sin Δθ)."""
    a = 0.5 * (s.p0[0] * s.p1[1] - s.p1[0] * s.p0[1])
    if isinstance(s, Arc):
        a += (1 if s.ccw else -1) * 0.5 * s.R**2 * (s.sweep - math.sin(s.sweep))
    return float(a)


@dataclass
class Profile:
    """Uç uca bağlı doğru + yay zinciri. closed=True ise son parça ilkine bağlanır."""

    segments: list[Segment]
    closed: bool = True

    def __post_init__(self) -> None:
        self.segments = list(self.segments)
        if not self.segments:
            raise CamError("Profil boş")
        for i in range(len(self.segments) - 1):
            if not _same(self.segments[i].p1, self.segments[i + 1].p0):
                raise CamError(f"Profil kopuk: parça {i} bitişi ≠ parça {i + 1} başlangıcı")
        if self.closed and not _same(self.segments[-1].p1, self.segments[0].p0):
            raise CamError("Kapalı profil kapanmıyor (son nokta ≠ ilk nokta)")

    # ---------------------------------------------------------- kurucular
    @classmethod
    def polygon(cls, points, closed: bool = True) -> Profile:
        pts = [_pt(p) for p in points]
        if closed and _same(pts[0], pts[-1]):
            pts = pts[:-1]
        n = len(pts)
        if n < (3 if closed else 2):
            raise CamError("Çokgen için yeterli nokta yok")
        idx = range(n) if closed else range(n - 1)
        return cls([Line(pts[i], pts[(i + 1) % n]) for i in idx], closed)

    @classmethod
    def rectangle(cls, x0: float, y0: float, a: float, b: float) -> Profile:
        """Sol alt köşesi (x0, y0), kenarları a × b olan CCW dikdörtgen."""
        if a <= 0 or b <= 0:
            raise CamError(f"Dikdörtgen kenarları pozitif olmalı (a={a}, b={b})")
        return cls.polygon([(x0, y0), (x0 + a, y0), (x0 + a, y0 + b), (x0, y0 + b)])

    @classmethod
    def circle(cls, c, R: float, ccw: bool = True) -> Profile:
        """Tek tam-daire yaydan profil; başlangıç noktası (cx + R, cy)."""
        c = _pt(c)
        p = c + np.array([R, 0.0])
        return cls([Arc(p, p, c, ccw)])

    # ---------------------------------------------------------- özellikler
    @property
    def area(self) -> float:
        """Yönlü alan [mm²] (CCW > 0)."""
        if not self.closed:
            raise CamError("Açık profilin alanı yok")
        return sum(segment_area(s) for s in self.segments)

    @property
    def length(self) -> float:
        return sum(s.length for s in self.segments)

    @property
    def start(self) -> np.ndarray:
        return self.segments[0].p0

    @property
    def end(self) -> np.ndarray:
        return self.segments[-1].p1

    def reversed(self) -> Profile:
        return Profile([s.reversed() for s in reversed(self.segments)], self.closed)

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        pts = [s.p0 for s in self.segments] + [self.segments[-1].p1]
        for s in self.segments:
            if isinstance(s, Arc):
                for k in range(4):
                    phi = k * math.pi / 2
                    d = ((phi - s.a0) if s.ccw else (s.a0 - phi)) % TWO_PI
                    if d <= s.sweep:
                        pts.append(s.c + s.R * np.array([math.cos(phi), math.sin(phi)]))
        a = np.array(pts)
        return a.min(axis=0), a.max(axis=0)


@dataclass
class Region:
    """Dış halka + adalar. Kurulurken yön kuralına çevrilir: dış CCW, adalar CW."""

    outer: Profile
    holes: list[Profile] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.holes = list(self.holes)
        for p in [self.outer, *self.holes]:
            if not p.closed:
                raise CamError("Bölge halkaları kapalı olmalı")
            if abs(p.area) <= AREA_TOL:
                raise CamError("Bölge halkasının alanı sıfır")
        if self.outer.area < 0:
            self.outer = self.outer.reversed()
        self.holes = [h.reversed() if h.area > 0 else h for h in self.holes]

    @property
    def loops(self) -> list[Profile]:
        return [self.outer, *self.holes]

    @property
    def area(self) -> float:
        return self.outer.area + sum(h.area for h in self.holes)

    def contains(self, p) -> bool:
        """p bölgenin içinde mi (dış halkanın içinde ve hiçbir adanın içinde değil)."""
        p = _pt(p)
        return winding(p, self.outer) != 0 and all(winding(p, h) == 0 for h in self.holes)
