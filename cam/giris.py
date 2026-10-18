"""
SPEC 03c — Rampa ve helis giriş.

Cep ve konturda düz dalma yerine helis, zigzag rampa veya kontur boyunca rampa.
Her giriş takım merkezinin geçerli bölgesinde (R₀ = Ω ⊖ B_r) kalır; eğim hiçbir harekette tan α'yı aşmaz.
Giriş sığmazsa CamError: sessizce düz dalmaya dönülmez.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from cam.geom2d import LINK_TOL, TOL, distance_to_region, intersect
from cam.model import CamError, EntryKind, EntryMode, Move, MoveType, Tool
from cam.offset import offset
from cam.profile import Arc, Line, Region, Segment

ANCHOR_N = 40  # çapa noktası (en derin nokta) ikiye bölme sayısı
RAMP_DIRS = 12  # zigzag yön adayı: u_k = (cos kπ/12, sin kπ/12)
HELIX_R_FACTOR = 0.5  # R_h varsayılanı = 0,5·r
RAMP_L_FACTOR = 2.0  # zigzag boyu varsayılanı L = 2D
NONCENTER_MIN = 0.5  # merkezden kesmeyen takımda R_h ≥ 0,5·r
FIT_TIE = 1e-9  # mm: yön seçiminde eşitlik payı (eşitlikte en küçük k)
ANGLE_TOL = 1e-12  # derece: angle ≤ ramp_angle_max karşılaştırması


# ---------------------------------------------------------------- giriş türü


def resolve(tool: Tool, entry: EntryMode | None, op: str) -> EntryMode:
    """Giriş türünü denetler, varsayılan yarıçap / boyu doldurur. op: "cep" veya "kontur"."""
    if op not in ("cep", "kontur"):
        raise CamError(f"Giriş: op 'cep' veya 'kontur' olmalı ({op!r})")
    if entry is None:
        entry = EntryMode()
    if not isinstance(entry, EntryMode):
        raise CamError(f"Giriş: EntryMode veya None olmalı ({type(entry).__name__})")
    nerede = f"Takım '{tool.name}'"
    if entry.kind is EntryKind.PLUNGE:
        if not tool.center_cutting:
            raise CamError(f"{nerede} merkezden kesmiyor; düz dalma yok, rampa veya helis seçin (Ek A2)")
        return entry
    if entry.kind is EntryKind.HELIX and op == "kontur":
        raise CamError("Giriş: helis yalnız cepte; konturda rampa kullanın")
    amax = tool.ramp_angle_max
    if amax is None and not tool.center_cutting:
        raise CamError(f"{nerede} merkezden kesmiyor ve ramp_angle_max yok; giriş açısı denetlenemez")
    if amax is not None and entry.angle > amax + ANGLE_TOL:
        raise CamError(f"Giriş açısı {entry.angle}° takımın en büyük rampa açısını ({amax}°) aşıyor")
    r = tool.D / 2
    if entry.kind is EntryKind.HELIX:
        R_h = HELIX_R_FACTOR * r if entry.radius is None else entry.radius
        if R_h > r + TOL:
            raise CamError(f"Helis yarıçapı R_h = {R_h} > r = {r}: ortada sütun kalır")
        if not tool.center_cutting and R_h < NONCENTER_MIN * r - TOL:
            raise CamError(f"{nerede} merkezden kesmiyor: R_h en az r/2 = {NONCENTER_MIN * r} (R_h = {R_h})")
        return replace(entry, radius=R_h)
    L = RAMP_L_FACTOR * tool.D if entry.length is None else entry.length
    return replace(entry, length=L)


def _check_descent(z0: float, z: float, alpha: float) -> float:
    """tan α; z0 > z ve 0 < α < 90 değilse CamError."""
    if not (math.isfinite(z0) and math.isfinite(z) and z0 > z):
        raise CamError(f"Giriş: z0 > z olmalı (z0={z0}, z={z})")
    if not (math.isfinite(alpha) and 0 < alpha < 90):
        raise CamError(f"Giriş: açı 0..90 derece arasında olmalı (α={alpha})")
    return math.tan(math.radians(alpha))


def _count(H: float, step: float) -> int:
    """max(1, ⌈H/step − 1e-9⌉)."""
    return max(1, math.ceil(H / step - 1e-9))


# ---------------------------------------------------------------- geometri yardımcıları


def deepest_point(region: Region) -> tuple[np.ndarray, float]:
    """Bölgenin en derin noktası c ve iç yarıçap alt sınırı lo (ikiye bölme, ANCHOR_N adım).

    c = offset(region, lo)[0] dış halkasının ilk parçasının başlangıcı; dist(c, ∂region) ≥ lo − KEEP_TOL.
    """
    lo_xy, hi_xy = region.outer.bbox()
    lo, hi = 0.0, 0.5 * float(np.min(hi_xy - lo_xy))
    best = None
    for _ in range(ANCHOR_N):
        t = 0.5 * (lo + hi)
        try:
            res = offset(region, t)
        except CamError:
            res = []  # çökmek üzere olan şerit: bu derinlik güvenle kullanılamaz
        if res:
            lo, best = t, res[0]
        else:
            hi = t
    if best is None:
        raise CamError("Giriş: bölgenin en derin noktası bulunamadı (bölge çok ince)")
    return np.array(best.outer.segments[0].p0, dtype=float), lo


def _on_or_in(p, region: Region) -> bool:
    return region.contains(p) or distance_to_region(p, region) <= LINK_TOL


def segment_inside(p, q, region: Region) -> bool:
    """[p, q] doğru parçası bölgenin içinde mi (sınır dahil)?

    Uçlar bölgede, parça sınırı uçlarından (≤ LINK_TOL) başka yerde kesmiyor, orta noktası bölgede.
    """
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)
    if not (_on_or_in(p, region) and _on_or_in(q, region)):
        return False
    L = float(np.hypot(*(q - p)))
    if L <= LINK_TOL:
        return True
    ln = Line(p, q)
    for loop in region.loops:
        for s in loop.segments:
            for tl, _ in intersect(ln, s):
                if LINK_TOL < tl * L < L - LINK_TOL:
                    return False
    return _on_or_in(0.5 * (p + q), region)


def _ray(c: np.ndarray, u: np.ndarray, region: Region, far: float) -> float:
    """c'den u yönündeki ışının ∂region'ı ilk kestiği noktaya uzaklık."""
    ln = Line(c, c + far * u)
    best = math.inf
    for loop in region.loops:
        for s in loop.segments:
            for tl, _ in intersect(ln, s):
                d = tl * far
                if d > TOL:
                    best = min(best, d)
    return best


def ramp_direction(c, region: Region, L: float) -> tuple[np.ndarray, float]:
    """Zigzag yönü u ve yarı boy ℓ = min(L/2, ℓ_fit); u en büyük ℓ_fit'li aday (eşitlikte en küçük k)."""
    c = np.asarray(c, dtype=float)
    lo_xy, hi_xy = region.outer.bbox()
    far = 2.0 * float(np.hypot(*(hi_xy - lo_xy))) + 1.0
    best_u, best_fit = None, -math.inf
    for k in range(RAMP_DIRS):
        th = k * math.pi / RAMP_DIRS
        u = np.array([math.cos(th), math.sin(th)])
        fit = min(_ray(c, u, region, far), _ray(c, -u, region, far))
        if fit > best_fit + FIT_TIE:
            best_u, best_fit = u, fit
    if not math.isfinite(best_fit):
        raise CamError("Giriş: rampa yönü bulunamadı (ışın bölge sınırını kesmiyor)")
    return best_u, min(0.5 * L, best_fit)


# ---------------------------------------------------------------- giriş hareketleri


def helix_moves(
    c, R_h: float, u, z0: float, z: float, alpha: float, climb: bool, ramp_feed: float, feed: float
) -> list[Move]:
    """h = c + R_h·u'dan n helis turu + z'de düz tam daire.

    n = max(1, ⌈Δz / (2π R_h tan α) − 1e-9⌉); her tur Δz/n iner. climb → G3, değilse G2.
    """
    if not (math.isfinite(R_h) and R_h > 0):
        raise CamError(f"Helis: yarıçap pozitif olmalı (R_h={R_h})")
    tan_a = _check_descent(z0, z, alpha)
    c = np.asarray(c, dtype=float)
    u = np.asarray(u, dtype=float)
    nu = float(np.hypot(*u))
    u = u / nu if nu > TOL else np.array([1.0, 0.0])
    h = c + R_h * u
    dz = z0 - z
    n = _count(dz, 2 * math.pi * R_h * tan_a)
    mt = MoveType.ARC_CCW if climb else MoveType.ARC_CW
    cc = (float(c[0]), float(c[1]))
    moves = []
    for k in range(1, n + 1):
        zk = z if k == n else z0 - dz * k / n
        moves.append(Move(mt, (float(h[0]), float(h[1]), zk), ramp_feed, cc))
    moves.append(Move(mt, (float(h[0]), float(h[1]), z), feed, cc))
    return moves


def zigzag_moves(
    c, u, ell: float, z0: float, z: float, alpha: float, ramp_feed: float, feed: float
) -> list[Move]:
    """A = c − ℓu'dan m ayak + z'de düz geçiş + c'ye.

    m = max(1, ⌈H/(2ℓ) − 1e-9⌉), H = Δz / tan α; ayaklar A → B → A …, her biri Δz/m iner.
    """
    if not (math.isfinite(ell) and ell > 0):
        raise CamError(f"Zigzag: yarı boy pozitif olmalı (ℓ={ell})")
    tan_a = _check_descent(z0, z, alpha)
    c = np.asarray(c, dtype=float)
    u = np.asarray(u, dtype=float)
    A, B = c - ell * u, c + ell * u
    dz = z0 - z
    m = _count(dz / tan_a, 2 * ell)
    moves = []
    for k in range(1, m + 1):
        p = B if k % 2 == 1 else A
        zk = z if k == m else z0 - dz * k / m
        moves.append(Move(MoveType.LINEAR, (float(p[0]), float(p[1]), zk), ramp_feed))
    other = A if m % 2 == 1 else B
    moves.append(Move(MoveType.LINEAR, (float(other[0]), float(other[1]), z), feed))
    moves.append(Move(MoveType.LINEAR, (float(c[0]), float(c[1]), z), feed))
    return moves


def _seg_move(s: Segment, z: float, feed: float) -> Move:
    end = (float(s.p1[0]), float(s.p1[1]), z)
    if isinstance(s, Arc):
        mt = MoveType.ARC_CCW if s.ccw else MoveType.ARC_CW
        return Move(mt, end, feed, (float(s.c[0]), float(s.c[1])))
    return Move(MoveType.LINEAR, end, feed)


def loop_ramp_moves(
    segs: list[Segment], closed: bool, z0: float, z: float, alpha: float, ramp_feed: float
) -> tuple[list[Move], list[Segment]]:
    """Kontur boyunca rampa; ikinci değer z'de kesilecek halka.

    Kapalı: yay boyu σ ∈ [0, H] boyunca z(σ) = z₀ − σ tan α, e'de biter (köşeye ≤ LINK_TOL yakınsa oturur);
    halka e'den döndürülür. Açık: m = max(1, ⌈H/(2P) − 1e-9⌉) gidiş-dönüş, p₀'da z'de biter.
    """
    if not segs:
        raise CamError("Rampa: boş halka")
    tan_a = _check_descent(z0, z, alpha)
    dz = z0 - z
    H = dz / tan_a
    P = sum(s.length for s in segs)
    if P <= LINK_TOL:
        raise CamError(f"Rampa: halka boyu sıfır (P={P})")
    moves: list[Move] = []
    if not closed:
        m = _count(H, 2 * P)
        trip = segs + [s.reversed() for s in reversed(segs)]
        slope = dz / (2 * m * P)
        sigma = 0.0
        for k in range(m):
            for j, s in enumerate(trip):
                sigma += s.length
                last = k == m - 1 and j == len(trip) - 1
                moves.append(_seg_move(s, z if last else z0 - sigma * slope, ramp_feed))
        return moves, list(segs)
    rem, sigma, i, N = H, 0.0, 0, len(segs)
    while True:
        s = segs[i]
        Ls = s.length
        if rem <= Ls + LINK_TOL:
            if rem >= Ls - LINK_TOL:  # e köşede (parçanın sonunda)
                moves.append(_seg_move(s, z, ramp_feed))
                j = (i + 1) % N
                return moves, segs[j:] + segs[:j]
            a, b = s.split(rem / Ls)
            moves.append(_seg_move(a, z, ramp_feed))
            return moves, [b] + segs[i + 1 :] + segs[:i] + [a]
        sigma += Ls
        rem -= Ls
        moves.append(_seg_move(s, z0 - sigma * tan_a, ramp_feed))
        i = (i + 1) % N
