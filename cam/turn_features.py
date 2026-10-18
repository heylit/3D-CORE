"""
SPEC 27 — Torna profilinden işleme özellikleri: alın, G71 tip I kaba zarf, kanal, genel girinti.

Girdi SPEC 20 kuralındaki yarı kesit profilidir ((u, v) = (z, x), açık); katı parçadan gelen profil SPEC 28
`TurnProfile.outer` (side="dis") veya `.inner` (side="ic"). Hesap dış çerçevede yapılır,
iç tarafta x → −x aynası.
Birimler: mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.lathe import check_side, mirror, mirror_segments, orient
from cam.model import CamError, CylinderStock
from cam.profile import Line, Profile, Segment

ANG = 1e-6  # yön toleransı (birim teğet bileşeni)
_EPS = 1e-9  # mm: bölme noktası parça ucuna bundan yakınsa bölme yapılmaz


@dataclass(frozen=True)
class Groove:
    """Dikdörtgen kanal; parametreler doğrudan SPEC 20 groove()'a gider."""

    z_left: float  # arka duvar
    z_right: float  # ön duvar
    x_top: float
    x_bottom: float


@dataclass(frozen=True)
class Recess:
    """Genel girinti: köprünün altında kalan alt profil (ön→arka, açık)."""

    profile: Profile
    z_left: float
    z_right: float
    x_top: float


@dataclass(frozen=True)
class TurnFeatures:
    side: str
    z_face: float | None
    face_depth: float | None
    rough: Profile  # monoton kaba zarf (açık)
    finish: Profile  # girdi profili, ön→arka
    grooves: tuple[Groove, ...]  # ön→arka
    recesses: tuple[Recess, ...]  # ön→arka


# ---------------------------------------------------------------- yardımcılar


def _sonlu_pozitif(ad: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise CamError(f"{ad} sonlu ve pozitif olmalı ({v!r})")
    return float(v)


def _quarter_split(s: Segment) -> list[Segment]:
    """Yayı eksen yönlü uç noktalarında (açı k·π/2) böler: her parçada t_z ve t_x işaret değiştirmez."""
    if isinstance(s, Line):
        return [s]
    ts = []
    for k in range(-4, 9):
        phi = k * math.pi / 2
        d = ((phi - s.a0) if s.ccw else (s.a0 - phi)) % (2 * math.pi)
        t = d / s.sweep
        if _EPS < t * s.length and (1 - t) * s.length > _EPS:
            ts.append(t)
    ts = sorted(set(round(t, 15) for t in ts))
    parts, t_prev = [], 0.0
    for t in [*ts, 1.0]:
        parts.append(s.sub(t_prev, t) if (t_prev, t) != (0.0, 1.0) else s)
        t_prev = t
    return parts


def _x_cross(s: Segment, M: float) -> float:
    """x-monoton parçada x = M'nin parametresi t ∈ [0, 1]."""
    if isinstance(s, Line):
        x0, x1 = s.p0[1], s.p1[1]
        return min(max((M - x0) / (x1 - x0), 0.0), 1.0)
    k = (M - s.c[1]) / s.R
    k = min(max(k, -1.0), 1.0)
    a1 = math.asin(k)
    best = None
    for a in (a1, math.pi - a1):
        d = ((a - s.a0) if s.ccw else (s.a0 - a)) % (2 * math.pi)
        t = d / s.sweep
        if t > 1 and (2 * math.pi - d) * s.R < 1e-9:
            t = 0.0
        if -1e-12 <= t <= 1 + 1e-12 and (best is None or abs(s.point(t)[1] - M) < abs(s.point(best)[1] - M)):
            best = t
    if best is None:
        raise CamError("Köprü yayla kesişmiyor")  # x-monoton parçada olmamalı
    return min(max(best, 0.0), 1.0)


def _merge_lines(segs: list[Segment]) -> list[Segment]:
    """Aynı doğrultudaki ardışık doğruları birleştirir."""
    out: list[Segment] = []
    for s in segs:
        if out and isinstance(s, Line) and isinstance(out[-1], Line):
            u, v = out[-1].tangent(0), s.tangent(0)
            if abs(u[0] * v[1] - u[1] * v[0]) <= ANG and u @ v > 0:
                out[-1] = Line(out[-1].p0, s.p1)
                continue
        out.append(s)
    return out


def _yon(s: Segment, t: tuple[float, float]) -> bool:
    return isinstance(s, Line) and bool(np.all(np.abs(s.tangent(0) - np.array(t)) <= ANG))


# ---------------------------------------------------------------- ana işlev


def turn_features(
    profile: Profile, stock: CylinderStock | None = None, side: str = "dis", tol: float = 1e-3
) -> TurnFeatures:
    """Profilden alın, kaba zarf, kanal ve girintileri çıkarır (SPEC 27 §9)."""
    if not isinstance(profile, Profile):
        raise CamError(f"Torna profili Profile olmalı ({type(profile).__name__})")
    if not isinstance(side, str):
        raise CamError(f"Taraf 'dis' veya 'ic' olmalı ({side!r})")
    sgn = check_side(side)
    tol = _sonlu_pozitif("tol", tol)
    if stock is not None and not isinstance(stock, CylinderStock):
        raise CamError("stock CylinderStock olmalı")

    finish = orient(profile)  # ön→arka, aynalanmamış
    lo, hi = finish.bbox()
    if stock is not None:
        if sgn > 0 and hi[1] > stock.D / 2 + tol:
            raise CamError(f"Profil ham malzemeden taşıyor (max x = {hi[1]} > D/2 = {stock.D / 2})")
        if sgn < 0 and lo[1] < stock.d / 2 - tol:
            raise CamError(f"Profil iç çaptan taşıyor (min x = {lo[1]} < d/2 = {stock.d / 2})")
    frame = finish if sgn > 0 else mirror(finish)

    # 1–2. bölme ve arka kesim denetimi
    parts = [q for s in frame.segments for q in _quarter_split(s)]
    for q in parts:
        if max(q.tangent(0)[0], q.tangent(0.5)[0], q.tangent(1)[0]) > ANG:
            raise CamError("Profil öne dönüyor (arka kesim, t_z > 0): kapsam dışı")

    # 3. zarf ve köprüler
    rough: list[Segment] = []
    recesses: list[tuple[list[Segment], float]] = []  # (alt profil, M)
    M = float(parts[0].p0[1])
    bridge_start: np.ndarray | None = None
    sub: list[Segment] = []
    for q in parts:
        x0, x1 = float(q.p0[1]), float(q.p1[1])
        if bridge_start is None:
            if x1 < x0 - tol:
                bridge_start, sub = q.p0.copy(), [q]
            else:
                rough.append(q)
                M = max(M, x1)
            continue
        if x1 < M - tol:
            sub.append(q)
            continue
        t = _x_cross(q, M)
        if t * q.length <= _EPS:
            rest: Segment | None = q
            q_end = q.p0
        elif (1 - t) * q.length <= _EPS:
            sub.append(q)
            rest, q_end = None, q.p1
        else:
            a, rest = q.split(t)
            sub.append(a)
            q_end = a.p1
        end = np.array([q_end[0], M])
        if np.hypot(*(end - bridge_start)) > _EPS:
            rough.append(Line(bridge_start, end))
        if rest is not None:
            if isinstance(rest, Line):
                rest = Line(end, rest.p1)
            rough.append(rest)
        recesses.append((sub, M))
        bridge_start, sub = None, []
        if rest is not None:
            M = max(M, float(rest.p1[1]))
    if bridge_start is not None:
        z_end = float(parts[-1].p1[0])
        rough.append(Line(bridge_start, (z_end, M)))
        recesses.append((sub, M))

    # 4. girinti sınıflama
    grooves: list[Groove] = []
    recs: list[Recess] = []
    for segs, Mk in recesses:
        segs = _merge_lines(segs)
        if len(segs) == 3 and _yon(segs[0], (0, -1)) and _yon(segs[1], (-1, 0)) and _yon(segs[2], (0, 1)):
            grooves.append(
                Groove(
                    z_left=float(segs[2].p0[0]),
                    z_right=float(segs[0].p0[0]),
                    x_top=sgn * Mk,
                    x_bottom=sgn * float(segs[1].p0[1]),
                )
            )
        else:
            back = segs if sgn > 0 else mirror_segments(segs)
            recs.append(
                Recess(
                    profile=Profile(back, closed=False),
                    z_left=float(segs[-1].p1[0]),
                    z_right=float(segs[0].p0[0]),
                    x_top=sgn * Mk,
                )
            )

    # 5. alın
    z_face = face_depth = None
    s0 = finish.segments[0]
    if sgn > 0 and _yon(s0, (0, 1)) and abs(s0.p0[1]) <= tol:
        z_face = float(s0.p0[0])
        if stock is not None and stock.zmax - z_face > tol:
            face_depth = float(stock.zmax - z_face)

    rough_p = Profile(rough if sgn > 0 else mirror_segments(rough), closed=False)
    return TurnFeatures(side, z_face, face_depth, rough_p, finish, tuple(grooves), tuple(recs))
