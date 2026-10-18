"""
SPEC 19 — Adaptif (sabit temas açılı) kaba işleme ve trokoidal kanal.

Temas açısı φ (derece) bir malzeme ızgarasında ölçülür; hiçbir kesme adımı hedef φ_t'yi aşmaz.
φ_t tutulamayan bölge kesilmez, AdaptiveResult.uncut_area ile raporlanır.
Tırmanma frezeleme (M3): malzeme ilerleme yönünün SAĞINDA.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from cam.geom2d import TOL
from cam.model import CamError, Move, MoveType, Tool, ToolKind, Toolpath
from cam.offset import offset
from cam.ops2d import Cut, depths
from cam.profile import Arc, Region

TWO_PI = 2 * math.pi
DIST_REL = 1e-12  # dist(q, [a, b]) ≥ r(1 − DIST_REL): adımın kendi süpürdüğü çevre noktası sayılmaz
SCAN = math.radians(10.0)  # yön taramasının adımı
BISECT = 7  # yön ikiye bölme sayısı (10° / 2⁷ ≈ 0,08°)
SCREEN_N = 90  # yeni geçiş başlangıcı ararken çevre örnek sayısı
CORNER_STEPS = 6  # köşe açıortayında en çok adım


def _num(nerede: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise CamError(f"{nerede} sonlu bir sayı olmalı ({v!r})")
    return float(v)


def _xy(p) -> np.ndarray:
    a = np.asarray(p, dtype=float).ravel()
    if a.size < 2 or not np.all(np.isfinite(a[:2])):
        raise CamError(f"Nokta en az iki sonlu bileşenli olmalı ({p!r})")
    return a[:2].copy()


# ---------------------------------------------------------------- analitik yardımcılar


def ae_to_engagement(ae: float, D: float) -> float:
    """Düz duvar: φ = arccos(1 − 2·a_e/D) [derece]."""
    ae, D = _num("a_e", ae), _num("D", D)
    if D <= 0 or not 0 < ae <= D:
        raise CamError(f"0 < a_e ≤ D olmalı (a_e={ae}, D={D})")
    return math.degrees(math.acos(max(-1.0, 1 - 2 * ae / D)))


def engagement_to_ae(phi: float, D: float) -> float:
    """Düz duvar: a_e = (D/2)(1 − cos φ) [mm]."""
    phi, D = _num("φ", phi), _num("D", D)
    if D <= 0 or not 0 < phi <= 180:
        raise CamError(f"0 < φ ≤ 180 ve D > 0 olmalı (φ={phi}, D={D})")
    return D / 2 * (1 - math.cos(math.radians(phi)))


def _check_rpf(rho, r, phi, phi_max: float, rho_zero: bool) -> tuple[float, float, float]:
    rho, r, phi = _num("ρ", rho), _num("r", r), _num("φ", phi)
    if r <= 0 or not (rho >= 0 if rho_zero else rho > 0):
        raise CamError(f"ρ > 0 ve r > 0 olmalı (ρ={rho}, r={r})")
    if not 0 < phi < phi_max or (phi_max == 180 and phi >= 180):
        raise CamError(f"0 < φ < {phi_max:g} olmalı (φ={phi})")
    return rho, r, math.radians(phi)


def spiral_spacing(rho: float, r: float, phi: float) -> float:
    """İçbükey daire: Δ(ρ) = ρ + r − √(ρ² + r² + 2ρr·cos φ) [mm]."""
    rho, r, f = _check_rpf(rho, r, phi, 180.0 + 1e-12, False)
    s = rho * rho + r * r + 2 * rho * r * math.cos(f)
    # sayısal sönüm olmasın diye (ρ + r)² − s = 2ρr(1 − cos φ) ile yazılır
    return 2 * rho * r * (1 - math.cos(f)) / (rho + r + math.sqrt(s))


def trochoid_pitch(rho: float, r: float, phi: float) -> float:
    """Trokoid: p(ρ, φ) = −r·cos φ + √((ρ + r)² − r²·sin² φ) − ρ [mm]."""
    rho, r, f = _check_rpf(rho, r, phi, 180.0, False)
    return -r * math.cos(f) + math.sqrt((rho + r) ** 2 - (r * math.sin(f)) ** 2) - rho


def _trochoid_phi(rho: float, r: float, p: float) -> float:
    """Formül 3: döngü ön noktasında φ_max [derece]."""
    d = rho + p
    c = ((rho + r) ** 2 - d * d - r * r) / (2 * d * r)
    return math.degrees(math.acos(min(1.0, max(-1.0, c))))


LOOP_N = 7200  # Ek A1: takım çevresindeki nokta sayısı
LOOP_M = 720  # Ek A1: α taramasının adım sayısı


def _loop_phi_at(rho: float, r: float, p: float, th: np.ndarray) -> np.ndarray:
    """Ek A1 φ(α) [derece], α = th [rad] ∈ (π, 3π] (vektör).

    Malzeme: önceki döngünün ρ + r dairesinin dışı ve bu döngüde π'den α'ya süpürülen yaya uzaklığı > r.
    Yaya uzaklık analitik: q'nun kutup açısı süpürülen aralıktaysa ||q| − ρ|, değilse uç noktalara uzaklığın
    küçüğü. Yay takımın bulunduğu noktadan 1e-9 rad önce biter (takımın kendi çevresi sınırda kalır).
    """
    u = TWO_PI * np.arange(LOOP_N) / LOOP_N
    th = np.asarray(th, dtype=float)[:, None]
    bx, by = rho * np.cos(th), rho * np.sin(th)
    qx, qy = bx + r * np.cos(u), by + r * np.sin(u)
    mat = np.hypot(qx + p, qy) > rho + r
    sw = th - math.pi - 1e-9
    rel = np.mod(np.arctan2(qy, qx) - math.pi, TWO_PI)
    ex, ey = rho * np.cos(math.pi + sw), rho * np.sin(math.pi + sw)
    d_end = np.minimum(np.hypot(qx + rho, qy), np.hypot(qx - ex, qy - ey))
    d = np.where(rel <= sw, np.abs(np.hypot(qx, qy) - rho), d_end)
    mat &= d > r
    return 360.0 * mat.mean(axis=1)


def _loop_grid() -> np.ndarray:
    return math.pi + TWO_PI * np.arange(1, LOOP_M + 1) / LOOP_M


def _loop_scan(rho: float, r: float, p: float, th: np.ndarray) -> np.ndarray:
    return np.concatenate([_loop_phi_at(rho, r, p, th[i : i + 60]) for i in range(0, len(th), 60)])


def _loop_max(rho: float, r: float, p: float, th: np.ndarray) -> float:
    """th üzerinde tarama + en büyüğün çevresinde 41 noktalı inceltme."""
    v = _loop_scan(rho, r, p, th)
    i = int(np.argmax(v))
    d = TWO_PI / LOOP_M
    ince = np.linspace(th[i] - d, min(th[i] + d, 3 * math.pi), 41)
    return float(max(v[i], _loop_phi_at(rho, r, p, ince).max()))


@lru_cache(maxsize=256)
def _loop_phi(rho: float, r: float, p: float) -> float:
    return _loop_max(rho, r, p, _loop_grid())


def trochoid_loop_engagement(rho: float, r: float, p: float) -> float:
    """Ek A1: trokoid döngüsü boyunca en büyük temas açısı φ_loop(ρ, r, p) [derece]."""
    rho, r, p = _num("ρ", rho), _num("r", r), _num("p", p)
    if rho <= 0 or r <= 0 or p <= 0:
        raise CamError(f"ρ > 0, r > 0 ve p > 0 olmalı (ρ={rho}, r={r}, p={p})")
    return _loop_phi(rho, r, p)


@lru_cache(maxsize=256)
def trochoid_loop_pitch(rho: float, r: float, phi: float) -> float:
    """Ek A2: φ_loop(ρ, r, p) ≤ φ olan en büyük p ≤ p(ρ, φ) (ikiye bölme) [mm].

    φ(α) her α için p'de artandır (önceki döngü geride kaldıkça malzeme artar); bu yüzden p(ρ, φ)'de φ'yi
    aşmayan α'lar daha küçük p'de de aşmaz ve ikiye bölme yalnız aşan α'ları (ve komşularını) tarar.
    """
    hi = trochoid_pitch(rho, r, phi)
    th = _loop_grid()
    v = _loop_scan(rho, r, hi, th)
    if _loop_phi(rho, r, hi) <= phi:
        return hi
    asan = np.flatnonzero(v > phi)
    asan = np.unique(np.clip(np.concatenate([asan - 1, asan, asan + 1]), 0, LOOP_M - 1))
    aday = th[asan]
    lo = 0.0
    while hi - lo > 1e-9 * hi:
        m = 0.5 * (lo + hi)
        if _loop_max(rho, r, m, aday) <= phi:
            lo = m
        else:
            hi = m
    return lo


# ---------------------------------------------------------------- sınır uzaklığı (vektörel)


class _Boundary:
    """Bölge sınırına (doğru + yay) kesin uzaklık, çok nokta için vektörel."""

    def __init__(self, region: Region) -> None:
        L0, L1, C, R, A0, SW = [], [], [], [], [], []
        for loop in region.loops:
            for s in loop.segments:
                if isinstance(s, Arc):
                    C.append(s.c)
                    R.append(s.R)
                    # yönü CCW'ye çevir: başlangıç açısı ve süpürme
                    A0.append(s.a0 if s.ccw else s.a0 - s.sweep)
                    SW.append(s.sweep)
                    L0.append(s.p0)  # uç noktalar (yay dışı açılar için)
                    L1.append(s.p1)
                else:
                    L0.append(s.p0)
                    L1.append(s.p1)
        self.p0 = np.array(L0, dtype=float).reshape(-1, 2)
        self.p1 = np.array(L1, dtype=float).reshape(-1, 2)
        self.is_line = np.ones(len(L0), dtype=bool)
        k = 0
        idx = []
        for loop in region.loops:
            for s in loop.segments:
                if isinstance(s, Arc):
                    idx.append(k)
                k += 1
        self.is_line[idx] = False
        self.arc_idx = np.array(idx, dtype=int)
        self.c = np.array(C, dtype=float).reshape(-1, 2)
        self.R = np.array(R, dtype=float)
        self.a0 = np.array(A0, dtype=float)
        self.sw = np.array(SW, dtype=float)
        self._lines: list | None = None
        self._arcs: list = []

    def dist(self, P: np.ndarray) -> np.ndarray:
        """P (N, 2) → sınıra uzaklık (N,)."""
        P = np.asarray(P, dtype=float).reshape(-1, 2)
        out = np.full(len(P), np.inf)
        ln = self.is_line
        if ln.any():
            a, b = self.p0[ln], self.p1[ln]
            ab = b - a
            L2 = np.einsum("ij,ij->i", ab, ab)
            ap = P[:, None, :] - a[None, :, :]
            t = np.clip(np.einsum("nij,ij->ni", ap, ab) / L2, 0.0, 1.0)
            q = a[None] + t[..., None] * ab[None]
            out = np.minimum(out, np.min(np.hypot(*(P[:, None, :] - q).transpose(2, 0, 1)), axis=1))
        if len(self.R):
            v = P[:, None, :] - self.c[None]
            rad = np.hypot(v[..., 0], v[..., 1])
            ang = np.arctan2(v[..., 1], v[..., 0])
            ic = ((ang - self.a0[None]) % TWO_PI) <= self.sw[None] + 1e-15
            d_in = np.abs(rad - self.R[None])
            e0, e1 = self.p0[self.arc_idx], self.p1[self.arc_idx]
            d0 = np.hypot(*(P[:, None, :] - e0[None]).transpose(2, 0, 1))
            d1 = np.hypot(*(P[:, None, :] - e1[None]).transpose(2, 0, 1))
            d = np.where(ic, d_in, np.minimum(d0, d1))
            out = np.minimum(out, np.min(d, axis=1))
        return out

    def dist1(self, x: float, y: float) -> float:
        """Tek nokta için dist (saf Python; az parçalı sınırda numpy çağrısından hızlı)."""
        if self._lines is None:
            ln = self.is_line
            self._lines = [
                (a[0], a[1], b[0] - a[0], b[1] - a[1], (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
                for a, b in zip(self.p0[ln].tolist(), self.p1[ln].tolist(), strict=True)
            ]
            self._arcs = list(
                zip(
                    self.c.tolist(),
                    self.R.tolist(),
                    self.a0.tolist(),
                    self.sw.tolist(),
                    self.p0[self.arc_idx].tolist(),
                    self.p1[self.arc_idx].tolist(),
                    strict=True,
                )
            )
        best = math.inf
        for ax, ay, bx, by, L2 in self._lines:
            t = min(1.0, max(0.0, ((x - ax) * bx + (y - ay) * by) / L2))
            best = min(best, math.hypot(x - (ax + t * bx), y - (ay + t * by)))
        for (cx, cy), R, a0, sw, e0, e1 in self._arcs:
            vx, vy = x - cx, y - cy
            if (math.atan2(vy, vx) - a0) % TWO_PI <= sw + 1e-15:
                d = abs(math.hypot(vx, vy) - R)
            else:
                d = min(math.hypot(x - e0[0], y - e0[1]), math.hypot(x - e1[0], y - e1[1]))
            best = min(best, d)
        return best

    def dist_chunked(self, P: np.ndarray, chunk: int = 20000) -> np.ndarray:
        return np.concatenate([self.dist(P[i : i + chunk]) for i in range(0, len(P), chunk)] or [np.zeros(0)])


def _inside(region: Region, X: np.ndarray, Y: np.ndarray, h: float) -> np.ndarray:
    """Hücre merkezleri (X satırları, Y sütunu ızgarası) bölgede mi: tarama çizgisi + çift-tek kuralı.
    Yaylar sapması ≤ h·1e-3 olan kirişlerle örneklenir (sınıra bu kadar yakın hücre belirsizdir)."""
    xs = X[0]
    ys = Y[:, 0]
    E0, E1 = [], []
    for loop in region.loops:
        for s in loop.segments:
            if isinstance(s, Arc):
                tol = max(h * 1e-3, 1e-9)
                step = 2 * math.acos(max(-1.0, 1 - tol / s.R)) if tol < s.R else math.pi / 2
                n = max(1, math.ceil(s.sweep / step))
                pts = [s.point(i / n) for i in range(n + 1)]
            else:
                pts = [s.p0, s.p1]
            E0 += pts[:-1]
            E1 += pts[1:]
    E0, E1 = np.array(E0), np.array(E1)
    m = np.zeros((len(ys), len(xs)), dtype=bool)
    y0, y1 = E0[:, 1], E1[:, 1]
    for i, y in enumerate(ys):
        cr = (y0 > y) != (y1 > y)
        if not cr.any():
            continue
        a, b = E0[cr], E1[cr]
        xc = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
        cnt = (xc[None, :] < xs[:, None]).sum(axis=1)
        m[i] = cnt % 2 == 1
    return m


def _tangent(sg, t: float) -> np.ndarray:
    if isinstance(sg, Arc):
        return np.asarray(sg.tangent(t), dtype=float)
    d = np.asarray(sg.p1, dtype=float) - np.asarray(sg.p0, dtype=float)
    return d / float(np.hypot(*d))


# ---------------------------------------------------------------- malzeme ızgarası


@dataclass
class MaterialGrid:
    """XY malzeme ızgarası; m[i, j] True = malzeme, hücre merkezi (x0 + (j + ½)h, y0 + (i + ½)h)."""

    x0: float
    y0: float
    h: float
    nx: int
    ny: int
    m: np.ndarray  # (ny, nx) bool

    @classmethod
    def from_region(cls, region: Region, h: float, pad: float = 0.0) -> MaterialGrid:
        """Merkezi bölgede olan hücreler malzeme."""
        h, pad = _num("h", h), _num("pad", pad)
        if h <= 0 or pad < 0:
            raise CamError(f"h > 0 ve pad ≥ 0 olmalı (h={h}, pad={pad})")
        lo, hi = region.outer.bbox()
        lo, hi = lo - pad, hi + pad
        nx = max(1, math.ceil((hi[0] - lo[0]) / h - 1e-12))
        ny = max(1, math.ceil((hi[1] - lo[1]) / h - 1e-12))
        if nx * ny > 50_000_000:
            raise CamError(f"Malzeme ızgarası çok büyük: {nx}×{ny} hücre (h'yi büyütün)")
        g = cls(float(lo[0]), float(lo[1]), h, nx, ny, np.zeros((ny, nx), dtype=bool))
        X, Y = g.centers()
        g.m = _inside(region, X, Y, h)
        return g

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        xs = self.x0 + (np.arange(self.nx) + 0.5) * self.h
        ys = self.y0 + (np.arange(self.ny) + 0.5) * self.h
        return np.meshgrid(xs, ys)

    def _window(self, a: np.ndarray, b: np.ndarray, r: float):
        lo = np.minimum(a, b) - r
        hi = np.maximum(a, b) + r
        j0 = max(0, math.floor((lo[0] - self.x0) / self.h - 0.5))
        j1 = min(self.nx, math.ceil((hi[0] - self.x0) / self.h + 0.5))
        i0 = max(0, math.floor((lo[1] - self.y0) / self.h - 0.5))
        i1 = min(self.ny, math.ceil((hi[1] - self.y0) / self.h + 0.5))
        return i0, i1, j0, j1

    def _segment_mask(self, a, b, r: float):
        a, b = _xy(a), _xy(b)
        r = _num("r", r)
        if r <= 0:
            raise CamError(f"r pozitif olmalı (r={r})")
        i0, i1, j0, j1 = self._window(a, b, r)
        if i0 >= i1 or j0 >= j1:
            return None
        ex = (self.x0 + (np.arange(j0, j1) + 0.5) * self.h - a[0])[None, :]  # X − a_x (satır)
        ey = (self.y0 + (np.arange(i0, i1) + 0.5) * self.h - a[1])[:, None]  # Y − a_y (sütun)
        ab = b - a
        L2 = float(ab @ ab)
        if L2 > 0:
            t = np.clip((ex * ab[0] + ey * ab[1]) / L2, 0.0, 1.0)
            d2 = (ex - t * ab[0]) ** 2 + (ey - t * ab[1]) ** 2
        else:
            d2 = ex**2 + ey**2
        return (slice(i0, i1), slice(j0, j1)), d2 <= r * r

    def cut_segment(self, a, b, r: float) -> float:
        """Merkezi [a, b]'ye uzaklığı ≤ r olan hücreleri boşaltır; boşaltılan alan [mm²]."""
        w = self._segment_mask(a, b, r)
        if w is None:
            return 0.0
        sl, k = w
        sub = self.m[sl]
        n = int(np.count_nonzero(sub & k))
        sub[k] = False
        return n * self.h * self.h

    def _would_cut(self, a, b, r: float) -> bool:
        w = self._segment_mask(a, b, r)
        return w is not None and bool(np.any(self.m[w[0]] & w[1]))

    def cut_arc(self, p0, p1, center, ccw: bool, r: float) -> float:
        """Yayı sapması ≤ h/4 kirişlerle cut_segment dizisine çevirir (p0 = p1 tam tur)."""
        pts = _arc_points(_xy(p0), _xy(p1), _xy(center), bool(ccw), self.h / 4)
        return sum(self.cut_segment(pts[i], pts[i + 1], r) for i in range(len(pts) - 1))

    def engagement(self, a, b, r: float, n: int = 1440) -> float:
        """Adım [a, b]'nin temas açısı φ [derece]; ızgarayı değiştirmez."""
        a, b = _xy(a), _xy(b)
        r = _num("r", r)
        if r <= 0:
            raise CamError(f"r pozitif olmalı (r={r})")
        if isinstance(n, bool) or not isinstance(n, int | np.integer) or n < 4:
            raise CamError(f"n en az 4 olan bir tam sayı olmalı (n={n!r})")
        return self._count(a, b, r, _ring(int(n))) * 360.0 / n

    def _count(self, a: np.ndarray, b: np.ndarray, r: float, U: np.ndarray) -> int:
        ab = b - a
        L2 = float(ab @ ab)
        if L2 > 0:
            # Yalnız ön yarı (U·ab ≥ 0) dist ≥ r(1 − DIST_REL) olabilir: arka yarıda dist ≤ r·√(1 − ε²)
            # (ε = −U·ab/|ab|), ±90°'nin 2 örnek ötesinde ε ≫ √(2·DIST_REL). Sonuç tüm halkayla aynıdır.
            n = len(U)
            k0 = round(math.atan2(ab[1], ab[0]) * n / TWO_PI)
            U = U[(k0 + _front(n)) % n]
        qx = b[0] + r * U[:, 0]
        qy = b[1] + r * U[:, 1]
        h = self.h
        if (
            b[0] - r > self.x0
            and b[1] - r > self.y0
            and b[0] + r < self.x0 + self.nx * h
            and b[1] + r < self.y0 + self.ny * h
        ):
            # takım dairesi ızgaranın içinde: sınır denetimi gerekmez (floor = int kesme, değerler ≥ 0)
            mat = self.m[((qy - self.y0) / h).astype(np.intp), ((qx - self.x0) / h).astype(np.intp)]
        else:
            j = np.floor((qx - self.x0) / h).astype(np.int64)
            i = np.floor((qy - self.y0) / h).astype(np.int64)
            ok = (i >= 0) & (i < self.ny) & (j >= 0) & (j < self.nx)
            mat = np.zeros(len(qx), dtype=bool)
            mat[ok] = self.m[i[ok], j[ok]]
        if not mat.any():
            return 0
        if L2 > 0:
            ex, ey = qx - a[0], qy - a[1]
            t = np.clip((ex * ab[0] + ey * ab[1]) / L2, 0.0, 1.0)
            d2 = (ex - t * ab[0]) ** 2 + (ey - t * ab[1]) ** 2
            mat = mat & (d2 >= (r * (1 - DIST_REL)) ** 2)
        return int(np.count_nonzero(mat))

    def area(self) -> float:
        """Kalan malzeme alanı h²·Σm [mm²]."""
        return float(np.count_nonzero(self.m)) * self.h * self.h

    def copy(self) -> MaterialGrid:
        return MaterialGrid(self.x0, self.y0, self.h, self.nx, self.ny, self.m.copy())


_RINGS: dict[int, np.ndarray] = {}


def _ring(n: int) -> np.ndarray:
    U = _RINGS.get(n)
    if U is None:
        a = np.arange(n) * TWO_PI / n
        U = _RINGS[n] = np.column_stack([np.cos(a), np.sin(a)])
    return U


_FRONTS: dict[int, np.ndarray] = {}


def _front(n: int) -> np.ndarray:
    """Halka indislerinde ilerleme yönünün ±(90° + 2 örnek) çevresi (göreli)."""
    k = _FRONTS.get(n)
    if k is None:
        half = math.ceil(n / 4) + 2
        k = _FRONTS[n] = np.arange(-half, half + 1) if 2 * half + 1 < n else np.arange(n)
    return k


def _arc_points(p0, p1, c, ccw: bool, tol: float) -> list[np.ndarray]:
    """Yay p0 → p1 (merkez c) kiriş noktaları: n = ⌈Δθ / (2·arccos(1 − tol/R))⌉ (SPEC 05 kuralı)."""
    R = float(np.hypot(*(p0 - c)))
    if R < 1e-12:
        return [p0, p1]
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    if np.hypot(*(p1 - p0)) < TOL:
        dth = TWO_PI
    else:
        dth = ((a1 - a0) if ccw else (a0 - a1)) % TWO_PI
    step = 2 * math.acos(1 - tol / R) if tol < R else math.pi / 2
    n = max(1, math.ceil(dth / step - 1e-12))
    s = 1.0 if ccw else -1.0
    pts = [p0]
    for i in range(1, n):
        th = a0 + s * dth * i / n
        pts.append(c + R * np.array([math.cos(th), math.sin(th)]))
    pts.append(p1)
    return pts


# ---------------------------------------------------------------- ortak doğrulama ve hareket kurucu


def _check_common(tool: Tool, cut: Cut, engagement: float, ramp_angle: float) -> tuple[float, float]:
    if not isinstance(tool, Tool) or tool.kind is not ToolKind.FLAT:
        raise CamError("SPEC 19 sadece düz parmak freze kabul eder")
    if not tool.center_cutting:
        raise CamError(f"Takım '{tool.name}' merkezden kesmiyor; helis giriş SPEC 03c'de (SPEC 19 reddeder)")
    if not isinstance(cut, Cut):
        raise CamError("cut bir Cut olmalı")
    if cut.stepover is not None:
        raise CamError("Adaptif / trokoidal işlemde stepover verilmez; temas açısı (engagement) kullanılır")
    if cut.a_p > tool.flute_length + TOL:
        raise CamError(f"a_p kesici boydan büyük olamaz (a_p={cut.a_p}, kesici boy={tool.flute_length})")
    phi = _num("engagement", engagement)
    if not 0 < phi < 180:
        raise CamError(f"Hedef temas açısı 0 < φ_t < 180 olmalı (φ_t={phi})")
    ra = _num("ramp_angle", ramp_angle)
    if not 0 < ra <= 15:
        raise CamError(f"Rampa açısı 0 < α ≤ 15° olmalı (α={ra})")
    return phi, ra


@dataclass
class _Moves:
    cut: Cut
    pos: np.ndarray
    moves: list[Move] = field(default_factory=list)

    def _add(self, mt: MoveType, p, feed=None, center=None) -> None:
        p = np.asarray(p, dtype=float)
        if center is None and np.linalg.norm(p - self.pos) < TOL:
            return
        c = None if center is None else (float(center[0]), float(center[1]))
        self.moves.append(Move(mt, (float(p[0]), float(p[1]), float(p[2])), feed, c))
        self.pos = p

    def rapid(self, x, y, z) -> None:
        self._add(MoveType.RAPID, (x, y, z))

    def line(self, x, y, z, feed=None) -> None:
        self._add(MoveType.LINEAR, (x, y, z), feed or self.cut.feed)

    def circle(self, c, z: float, ccw: bool, feed=None) -> None:
        """Bulunulan XY noktasından c merkezli tam tur; Z bitişte z (helis turu)."""
        mt = MoveType.ARC_CCW if ccw else MoveType.ARC_CW
        self._add(mt, (self.pos[0], self.pos[1], z), feed or self.cut.feed, c)

    def retract(self) -> None:
        if self.pos[2] < self.cut.z_safe:
            self.rapid(self.pos[0], self.pos[1], self.cut.z_safe)

    def helix_entry(self, p, c, rho: float, z: float, z_prev: float, ramp: float, ccw: bool) -> None:
        """p (c'den ρ uzakta) üstüne gel, z_prev + clearance'tan eğimi ≤ ramp olan helisle z'ye in;
        tabanda tam tur."""
        cut = self.cut
        self.retract()
        self.rapid(p[0], p[1], cut.z_safe)
        z_hi = max(z_prev + cut.clearance, z)
        self.rapid(p[0], p[1], z_hi)
        dz = z_hi - z
        if rho <= 0:
            self.line(p[0], p[1], z, cut.plunge_feed)
            return
        if dz > 0:
            n = max(1, math.ceil(dz / (TWO_PI * rho * math.tan(math.radians(ramp))) - 1e-9))
            for k in range(1, n + 1):
                self.circle(c, z_hi - dz * k / n, ccw, cut.plunge_feed)
        self.circle(c, z, ccw)

    def toolpath(self, name: str, tool: Tool, start) -> Toolpath:
        self.retract()
        tp = Toolpath(name=name, tool=tool, start=start, moves=self.moves, rpm=self.cut.rpm)
        tp.validate()
        return tp


# ---------------------------------------------------------------- trokoidal kanal


def trochoidal_slot(
    p0,
    p1,
    width: float,
    tool: Tool,
    cut: Cut,
    engagement: float,
    *,
    ramp_angle: float = 2.0,
    climb: bool = True,
) -> Toolpath:
    """P0 → P1 düz kanalı, döngü yarıçapı ρ = (w − D)/2 ve aralığı ≤ p(ρ, φ_t) olan trokoidle açar."""
    phi, ra = _check_common(tool, cut, engagement, ramp_angle)
    P0, P1 = _xy(p0), _xy(p1)
    w = _num("width", width)
    r = tool.D / 2
    if w <= tool.D + TOL:
        raise CamError(f"Kanal genişliği takım çapından büyük olmalı (w={w}, D={tool.D})")
    L = float(np.hypot(*(P1 - P0)))
    if L < TOL:
        raise CamError("Kanal boyu sıfır (P0 = P1)")
    rho = (w - tool.D) / 2
    p = trochoid_loop_pitch(rho, r, phi)
    N = max(1, math.ceil(L / p - 1e-9))
    t = (P1 - P0) / L
    cs = [P0 + (L * k / N) * t for k in range(N + 1)]
    cs[-1] = P1.copy()
    back = -rho * t
    ccw = bool(climb)
    s0 = cs[0] + back
    start = (float(s0[0]), float(s0[1]), float(cut.z_safe))
    b = _Moves(cut, np.array(start))
    z_prev = cut.z_top
    for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
        b.helix_entry(s0, cs[0], rho, z, z_prev, ra, ccw)
        for c in cs[1:]:
            q = c + back
            b.line(q[0], q[1], z)
            b.circle(c, z, ccw)
        b.retract()
        z_prev = z
    return b.toolpath("trokoidal kanal", tool, start)


# ---------------------------------------------------------------- adaptif cep


@dataclass
class AdaptiveResult:
    toolpath: Toolpath
    material: MaterialGrid  # bir paso derinliğinin son ızgarası
    uncut_area: float  # T'nin iç hücrelerinde kalan malzeme [mm²]
    max_engagement: float  # helis dışındaki adımların en büyük φ'si [derece]


@dataclass
class _Plan:
    """Bir C bileşeninin XY planı: helis + geçişler (her geçiş nokta listesi, ilk nokta başlangıç)."""

    entry: np.ndarray  # helis merkezi
    rho: float
    start: np.ndarray  # helis başlangıç / bitiş noktası
    passes: list[list[np.ndarray]] = field(default_factory=list)
    keep_down: list[bool] = field(default_factory=list)  # geçiş k'ya inmeden mi gelindi (k ≥ 1)


class _Adaptive:
    def __init__(self, region, r, leave, phi_t, step, h, samples, climb, helix_radius):
        self.region = region
        self.r = r
        self.leave = leave
        self.phi_t = phi_t
        self.step = step
        self.h = h
        self.U = _ring(samples)
        self.n = samples
        self.Us = _ring(SCREEN_N)
        self.sgn = 1.0 if climb else -1.0  # tırmanma: malzeme sağda → sağa dönmek temas açısını büyütür
        self.helix_radius = helix_radius
        self.R_need = r + leave
        self.margin = step * step / (8 * self.R_need) + 1e-9  # kirişin C'nin içbükey yayına batma payı
        self.bnd = _Boundary(region)
        self.grid = MaterialGrid.from_region(region, h)
        self.inside = self.grid.m.copy()
        self.max_phi = 0.0
        self.pool = np.zeros((0, 2))
        self.air_max = 4 * r  # adaptive_pocket C'nin çevresine göre büyütür
        self.reach = np.zeros_like(self.inside)
        self.clr = self._clearance()
        self.interior = np.zeros_like(self.inside)  # T = C ⊕ B_r hücreleri (adaptive_pocket doldurur)

    # ---- geçerlilik: merkez C içinde, kiriş payıyla
    def _clearance(self) -> np.ndarray:
        """Hücre merkezlerinde sınıra uzaklık (dışarıda −1); valid() için ön eleme."""
        X, Y = self.grid.centers()
        c = np.full(self.inside.shape, -1.0)
        c[self.inside] = self.bnd.dist_chunked(np.column_stack([X[self.inside], Y[self.inside]]))
        return c

    def valid_many(self, Q: np.ndarray) -> np.ndarray:
        """Q (N, 2) noktaları C içinde mi (kiriş payıyla). |d(p) − d(hücre merkezi)| ≤ |p − hücre merkezi|
        ön elemesi (uzaklık 1-Lipschitz), belirsiz olanlarda kesin uzaklık."""
        g = self.grid
        Q = np.asarray(Q, dtype=float).reshape(-1, 2)
        j = np.floor((Q[:, 0] - g.x0) / g.h).astype(np.int64)
        i = np.floor((Q[:, 1] - g.y0) / g.h).astype(np.int64)
        ok = (i >= 0) & (i < g.ny) & (j >= 0) & (j < g.nx)
        d0 = np.full(len(Q), -1.0)
        d0[ok] = self.clr[i[ok], j[ok]]
        need = self.R_need + self.margin
        e = np.hypot(Q[:, 0] - g.x0 - (j + 0.5) * g.h, Q[:, 1] - g.y0 - (i + 0.5) * g.h) * (1 + 1e-9) + 1e-12
        out = d0 - e >= need
        unsure = (d0 >= 0) & ~out & (d0 + e >= need)
        if unsure.any():
            out[unsure] = self.bnd.dist(Q[unsure]) >= need
        return out

    def valid(self, p: np.ndarray) -> bool:
        """valid_many'nin tek nokta için skaler yolu (aynı kural)."""
        g = self.grid
        j = math.floor((p[0] - g.x0) / g.h)
        i = math.floor((p[1] - g.y0) / g.h)
        if not (0 <= i < g.ny and 0 <= j < g.nx):
            return False
        d0 = float(self.clr[i, j])
        need = self.R_need + self.margin
        e = math.hypot(p[0] - g.x0 - (j + 0.5) * g.h, p[1] - g.y0 - (i + 0.5) * g.h) * (1 + 1e-9) + 1e-12
        if d0 - e >= need:
            return True
        if d0 < 0 or d0 + e < need:
            return False
        return self.bnd.dist1(float(p[0]), float(p[1])) >= need

    def phi(self, a: np.ndarray, b: np.ndarray) -> float:
        return self.grid._count(a, b, self.r, self.U) * 360.0 / self.n

    def phi_many(self, a: np.ndarray, B: np.ndarray) -> np.ndarray:
        """Aynı başlangıçtan birçok adımın φ'si (vektörel; _count ile aynı kural)."""
        g = self.grid
        r = self.r
        ab = B - a[None]
        L2 = np.einsum("ij,ij->i", ab, ab)
        U = self.U[None]
        if np.all(L2 > 0):  # _count'taki gibi yalnız ön yarı
            k0 = np.round(np.arctan2(ab[:, 1], ab[:, 0]) * self.n / TWO_PI).astype(np.int64)
            U = self.U[(k0[:, None] + _front(self.n)[None]) % self.n]
        Q = B[:, None, :] + r * U
        j = np.floor((Q[..., 0] - g.x0) / g.h).astype(np.int64)
        i = np.floor((Q[..., 1] - g.y0) / g.h).astype(np.int64)
        ok = (i >= 0) & (i < g.ny) & (j >= 0) & (j < g.nx)
        mat = np.zeros(ok.shape, dtype=bool)
        mat[ok] = g.m[i[ok], j[ok]]
        L2s = np.where(L2 > 0, L2, 1.0)
        dot = (Q[..., 0] - a[0]) * ab[:, None, 0] + (Q[..., 1] - a[1]) * ab[:, None, 1]
        t = np.clip(dot / L2s[:, None], 0, 1)
        d2 = (Q[..., 0] - a[0] - t * ab[:, None, 0]) ** 2 + (Q[..., 1] - a[1] - t * ab[:, None, 1]) ** 2
        mat &= (d2 >= (r * (1 - DIST_REL)) ** 2) | (L2[:, None] == 0)
        return mat.sum(axis=1) * 360.0 / self.n

    # ---- bir adım: temas açısını φ_t'ye en çok yaklaştıran geçerli yön
    def best_step(self, c: np.ndarray, th: float, s: float):
        sg = self.sgn

        def ev(d):
            q = c + s * np.array([math.cos(th + sg * d), math.sin(th + sg * d)])
            if not self.valid(q):
                return q, None
            return q, self.phi(c, q)

        def good(f):
            return f is not None and f <= self.phi_t

        # d > 0: sola (boşaltılmış tarafa), d < 0: sağa (malzemeye) dönüş (tırmanmada)
        q0, f0 = ev(0.0)
        if good(f0):
            d_g, q_g, f_g = 0.0, q0, f0
            d = 0.0
            d_b = None
            best = (f0, 0.0, q0)
            while d > -math.pi + 1e-9:
                d -= SCAN
                q, f = ev(d)
                if good(f):
                    d_g, q_g, f_g = d, q, f
                    if f > best[0]:
                        best = (f, d, q)
                else:
                    d_b = d
                    break
            if d_b is None:
                return best[2], best[0], th + sg * best[1]
        else:
            d_b = 0.0
            d = 0.0
            d_g = None
            while d < math.pi - 1e-9:
                d += SCAN
                q, f = ev(d)
                if good(f):
                    d_g, q_g, f_g = d, q, f
                    break
                d_b = d
            if d_g is None:
                return None, 0.0, th
        for _ in range(BISECT):
            dm = 0.5 * (d_g + d_b)
            q, f = ev(dm)
            if good(f):
                d_g, q_g, f_g = dm, q, f
            else:
                d_b = dm
        return q_g, f_g, th + sg * d_g

    def full_scan(self, c: np.ndarray, th: float, s: float):
        """Bütün yönler (10° aralıklı): iyi (geçerli ve φ ≤ φ_t) yönden sağındaki kötü yöne geçişler
        ikiye bölünür (tırmanmada malzeme sağda); en büyük φ, eşitlikte rotadan en az sapan seçilir."""
        sg = self.sgn
        K = round(TWO_PI / SCAN)
        angs = th + np.arange(K) * TWO_PI / K
        Bq = c[None] + s * np.column_stack([np.cos(angs), np.sin(angs)])
        vq = self.valid_many(Bq)
        fq = np.full(K, np.nan)
        if vq.any():
            fq[vq] = self.phi_many(c, Bq[vq])
        res = [(Bq[k], float(fq[k]) if vq[k] else None) for k in range(K)]
        good = [f is not None and f <= self.phi_t for _, f in res]
        cands = []
        for k in range(K):
            kb = (k - int(sg)) % K  # sağdaki komşu (tırmanma) / soldaki (geleneksel)
            if good[k] and not good[kb]:
                a_g, a_b = angs[k], angs[k] - sg * TWO_PI / K
                q_g, f_g = res[k]
                for _ in range(BISECT):
                    am = 0.5 * (a_g + a_b)
                    q = c + s * np.array([math.cos(am), math.sin(am)])
                    f = self.phi(c, q) if self.valid(q) else None
                    if f is not None and f <= self.phi_t:
                        a_g, q_g, f_g = am, q, f
                    else:
                        a_b = am
                cands.append((f_g, a_g, q_g))
        if not cands:
            cands = [(res[k][1], angs[k], res[k][0]) for k in range(K) if good[k]]
        if not cands:
            return None, 0.0, th

        def dev(a):
            return abs((a - th + math.pi) % TWO_PI - math.pi)

        fmax = max(f for f, _, _ in cands)
        f, a, q = min((c_ for c_ in cands if c_[0] >= fmax - 0.5), key=lambda c_: dev(c_[1]))
        return q, f, a

    def step_from(self, c, th, air: bool = False):
        """Tam adım, olmazsa yarıya inen adımlarla (en kısa ≈ h/2) φ > 0 olan adım."""
        s = self.step
        while s >= self.h / 2:
            q, f, th2 = self.best_step(c, th, s)
            if q is None or f <= 0:
                q2, f2, th3 = self.full_scan(c, th, s)
                if q2 is not None and (q is None or f2 > f):
                    q, f, th2 = q2, f2, th3
            if q is not None and (f > 0 or air):
                return q, f, th2
            s *= 0.5
        return None, 0.0, th

    def useful(self, a, b) -> bool:
        """Adım T'nin iç hücrelerinden malzeme kaldırır mı (sınırdaki yarım hücreler sayılmaz)."""
        w = self.grid._segment_mask(a, b, self.r)
        return w is not None and bool(np.any(self.grid.m[w[0]] & w[1] & self.interior[w[0]]))

    def run_pass(self, c: np.ndarray, th: float) -> list[np.ndarray]:
        """Cephe izleme. İç hücrelerden malzeme kaldırmayan adımlar bekletilir (kesilmez); kaldıran bir adım
        gelince önce onlar kesilir. Bekleyen adımların boyu air_max'ı aşınca geçiş biter, onlar atılır."""
        pts = [c.copy()]
        pend: list[tuple[np.ndarray, np.ndarray]] = []
        idle = 0.0
        while True:
            q, f, th2 = self.step_from(c, th, air=True)
            if q is None:
                break
            if self.useful(c, q):
                for a, b in pend:
                    self.grid.cut_segment(a, b, self.r)
                    pts.append(b)
                pend = []
                self.grid.cut_segment(c, q, self.r)
                self.max_phi = max(self.max_phi, f)
                pts.append(q)
                idle = 0.0
            else:
                pend.append((c, q))
                idle += float(np.hypot(*(q - c)))
                if idle > self.air_max:
                    break
            c, th = q, th2
        return pts

    # ---- yeni geçiş başlangıcı: çevresine malzeme değen geçmiş merkez
    def heading_at(self, p: np.ndarray):
        g = self.grid
        Q = p + self.r * self.U
        j = np.floor((Q[:, 0] - g.x0) / g.h).astype(np.int64)
        i = np.floor((Q[:, 1] - g.y0) / g.h).astype(np.int64)
        ok = (i >= 0) & (i < g.ny) & (j >= 0) & (j < g.nx)
        mat = np.zeros(len(Q), dtype=bool)
        mat[ok] = g.m[i[ok], j[ok]] & self.interior[i[ok], j[ok]]
        if not mat.any():
            return None
        v = self.U[mat].sum(axis=0)
        if np.hypot(*v) < 1e-12:
            v = self.U[mat][0]
        a = math.atan2(v[1], v[0])
        return a + self.sgn * math.pi / 2  # malzeme sağda (tırmanma) / solda (geleneksel)

    def screen(self, P: np.ndarray) -> np.ndarray:
        """Her merkezin çevresinde (SCREEN_N nokta) malzeme sayısı."""
        g = self.grid
        out = np.zeros(len(P), dtype=np.int64)
        for k0 in range(0, len(P), 4000):
            Q = P[k0 : k0 + 4000, None, :] + self.r * self.Us[None]
            j = np.floor((Q[..., 0] - g.x0) / g.h).astype(np.int64)
            i = np.floor((Q[..., 1] - g.y0) / g.h).astype(np.int64)
            ok = (i >= 0) & (i < g.ny) & (j >= 0) & (j < g.nx)
            mat = np.zeros(ok.shape, dtype=bool)
            mat[ok] = g.m[i[ok], j[ok]] & self.interior[i[ok], j[ok]]
            out[k0 : k0 + 4000] = mat.sum(axis=1)
        return out

    def link_ok(self, a: np.ndarray, b: np.ndarray) -> bool:
        L = float(np.hypot(*(b - a)))
        n = max(1, math.ceil(L / self.step))
        for k in range(1, n):
            if not self.valid(a + (b - a) * k / n):
                return False
        return not self.grid._would_cut(a, b, self.r)

    def entry_point(self, comp: Region):
        """Bileşen içinde sınıra en uzak hücre merkezi (eşitlikte en uzakların ağırlık merkezine
        en yakını)."""
        X, Y = self.grid.centers()
        cand = self.inside & self.grid.m
        P = np.column_stack([X[cand], Y[cand]])
        if len(P) == 0:
            return None, 0.0
        d = self.bnd.dist_chunked(P)
        ok = d >= self.R_need + self.margin
        if not ok.any():
            return None, 0.0
        P, d = P[ok], d[ok]
        inside = np.array([comp.contains(q) for q in P[np.argsort(-d)[:4000]]])
        order = np.argsort(-d)[:4000][inside]
        if len(order) == 0:
            return None, 0.0
        dmax = d[order[0]]
        top = order[d[order] >= dmax - self.h]
        g = P[top].mean(axis=0)
        k = top[np.argmin(np.hypot(*(P[top] - g).T))]
        return P[k], float(d[k])

    def contour_points(self, comp: Region) -> list[list[np.ndarray]]:
        """C'nin kiriş payı kadar içerideki sınırı (offset r + leave + pay), aralığı ≤ step noktalarla;
        köşeler dahil.
        Halkalar doğal yönde (bölge solda → malzeme sağda, tırmanma); geleneksel frezede ters."""
        loops = []
        for reg in offset(self.region, self.R_need + self.margin):
            if not comp.contains(reg.outer.segments[0].p0):
                continue
            for loop in reg.loops:
                if self.sgn < 0:
                    loop = loop.reversed()
                pts = []
                for sgm in loop.segments:
                    n = max(1, math.ceil(sgm.length / self.step - 1e-9))
                    pts += [np.asarray(sgm.point(k / n), dtype=float) for k in range(n)]
                pts.append(pts[0].copy())
                loops.append(pts)
        return loops

    def corners(self, comp: Region) -> list[tuple[np.ndarray, np.ndarray]]:
        """C'nin (kiriş payı kadar içerideki) sınırındaki dışbükey köşeler ve içe açıortay yönleri."""
        out = []
        for reg in offset(self.region, self.R_need + self.margin):
            if not comp.contains(reg.outer.segments[0].p0):
                continue
            for loop in reg.loops:
                segs = loop.segments
                for k, sg in enumerate(segs):
                    nx = segs[(k + 1) % len(segs)]
                    t1, t2 = _tangent(sg, 1.0), _tangent(nx, 0.0)
                    if t1[0] * t2[1] - t1[1] * t2[0] > 1e-9:  # sola dönüş: bölge solda → dışbükey köşe
                        u = t2 - t1
                        nu = float(np.hypot(*u))
                        if nu > 1e-9:
                            out.append((np.asarray(sg.p1, dtype=float), u / nu))
        return out

    def corner_visits(self, comp: Region, plan: _Plan, cur: np.ndarray) -> np.ndarray:
        """Köşeye açıortay boyunca, φ ≤ φ_t kalan en derin noktaya kadar gir (köşe kalıntısının yanındaki
        iç hücreler için); giriş noktası diski boş bir noktadır. Her adım kalıntıyı biraz keser, bu yüzden
        aynı açıortayda daha derine birkaç kısa adım daha denenir (köşenin kendisinde ızgaradaki φ şişer)."""
        for v, u in self.corners(comp):
            p0 = v + self.step * u
            if not self.valid(p0):
                continue
            run = self.approach(p0)
            if not run:
                continue
            a, t_a = p0, self.step
            pts: list[np.ndarray] = []
            for _ in range(CORNER_STEPS):
                lo, hi = 0.0, t_a  # hi: iyi (a'nın kendisi), lo: köşe
                best = None
                for _ in range(12):
                    t = 0.5 * (lo + hi)
                    b = v + t * u
                    if self.valid(b) and self.phi(a, b) <= self.phi_t:
                        hi, best = t, b
                    else:
                        lo = t
                if best is None or not self.useful(a, best):
                    break
                self.max_phi = max(self.max_phi, self.phi(a, best))
                self.grid.cut_segment(a, best, self.r)
                pts.append(best)
                a, t_a = best, hi
            if not pts:
                if len(run) > 1:  # yaklaşma adımı kesildi: geçiş olarak yaz
                    cur = self.flush(plan, run, cur)
                continue
            cur = self.flush(plan, run + pts, cur)
        return cur

    def cleanup(self, comp: Region, plan: _Plan, cur: np.ndarray) -> np.ndarray:
        """Sınır geçişi: köşelere tam ulaşır. φ ≤ φ_t olan ve malzeme kaldıran ardışık adımlar geçiş olur;
        φ_t'yi aşan adım kesilmez, sonraki geçiş diski boşalmış bir noktadan başlar."""
        loops = self.contour_points(comp)
        # ters yön ikinci tur: köşeye öbür duvardan gelince o duvarın şeridi zaten kesilmiş olur
        for pts in loops + [lp[::-1] for lp in loops]:
            k0 = int(np.argmin([np.hypot(*(q - cur)) for q in pts[:-1]]))
            ring = pts[k0:-1] + pts[:k0] + [pts[k0].copy()]
            run: list[np.ndarray] = []
            pend: list[np.ndarray] = []
            for a, b in zip(ring[:-1], ring[1:], strict=True):
                if not run:
                    run = self.approach(a)  # dalış noktası diski boşalmış bir geçmiş merkez olmalı
                    pend = []
                    if not run:
                        continue
                f = self.phi(a, b)
                if f > self.phi_t:
                    cur = self.flush(plan, run, cur)
                    run = []
                    continue
                if self.useful(a, b):
                    for q in pend:
                        self.grid.cut_segment(run[-1], q, self.r)
                        run.append(q)
                    pend = []
                    self.grid.cut_segment(a, b, self.r)
                    self.max_phi = max(self.max_phi, f)
                    run.append(b)
                else:
                    pend.append(b)
            cur = self.flush(plan, run, cur)
        return cur

    def approach(self, a: np.ndarray) -> list[np.ndarray]:
        """a'ya inilebilecek yol: a'nın diski boşsa [a]; değilse step içindeki en yakın geçmiş merkezden
        (diski boş) a'ya φ ≤ φ_t olan tek adım [p, a]; yoksa []."""
        if not self.grid._would_cut(a, a, self.r):
            return [a]
        if len(self.pool) == 0:
            return []
        d = np.hypot(*(self.pool - a).T)
        for k in np.argsort(d)[:8]:
            if d[k] > self.step or d[k] < 1e-12:
                break
            p = self.pool[k].copy()
            if self.grid._would_cut(p, p, self.r) or self.phi(p, a) > self.phi_t:
                continue
            self.grid.cut_segment(p, a, self.r)
            return [p, a]
        return []

    def flush(self, plan: _Plan, pts: list[np.ndarray], cur: np.ndarray) -> np.ndarray:
        if len(pts) < 2:
            return cur
        plan.passes.append(pts)
        plan.keep_down.append(self.link_ok(cur, pts[0]))
        self.pool_add(pts)
        return pts[-1]

    def pool_add(self, pts) -> None:
        self.pool = np.vstack([self.pool, np.asarray(pts, dtype=float).reshape(-1, 2)])

    def restarts(self, plan: _Plan, cur: np.ndarray) -> np.ndarray:
        """Çevresine (ulaşılabilir) malzeme değen geçmiş merkezlerden, ilk adımı malzeme kaldıran geçişler."""
        while True:
            if len(self.pool) == 0:
                return cur
            cnt = self.screen(self.pool)
            self.pool = self.pool[cnt > 0]  # malzeme yalnız azalır: çevresi boşalan nokta bir daha gerekmez
            if len(self.pool) == 0:
                return cur
            order = np.argsort(np.hypot(*(self.pool - cur).T))
            started = False
            dead = np.zeros(len(self.pool), dtype=bool)
            for k in order:
                p = self.pool[k].copy()
                th = self.heading_at(p)
                q = None
                if th is not None:
                    q, f, th = self.step_from(p, th)
                if q is None or not self.grid._would_cut(p, q, self.r):
                    dead[k] = True
                    continue
                kd = self.link_ok(cur, p)
                pts = self.run_pass(p, th)
                if len(pts) < 2:
                    dead[k] = True
                    continue
                plan.passes.append(pts)
                plan.keep_down.append(kd)
                self.pool = self.pool[~dead]
                self.pool_add(pts[1:])
                cur = pts[-1]
                started = True
                break
            if not started:
                return cur

    def component(self, comp: Region) -> _Plan | None:
        r = self.r
        e, de = self.entry_point(comp)
        if e is None:
            return None
        hr = 0.5 * r if self.helix_radius is None else self.helix_radius
        rho = min(hr, de - self.R_need - self.margin)
        if rho <= 1e-6:
            rho = 0.0
        start = e + np.array([rho, 0.0])
        if rho > 0:
            self.grid.cut_arc(start, start, e, self.sgn > 0, r)
            self.pool = np.array([e + rho * u for u in _ring(16)])
        else:
            self.grid.cut_segment(e, e, r)
            self.pool = e[None].copy()
        plan = _Plan(entry=e, rho=rho, start=start)
        th = math.pi / 2 if self.sgn > 0 else -math.pi / 2  # çember teğeti, malzeme dışarıda
        pts = self.run_pass(start, th)
        plan.passes.append(pts)
        plan.keep_down.append(True)
        self.pool_add(pts[1:])
        cur = pts[-1]
        for _ in range(4):
            before = self.grid.area()
            cur = self.restarts(plan, cur)
            cur = self.cleanup(comp, plan, cur)
            cur = self.corner_visits(comp, plan, cur)
            if self.grid.area() == before:
                break
        return plan


def _reach(A: _Adaptive, comps: list[Region]) -> tuple[np.ndarray, np.ndarray]:
    """T = C ⊕ B_r hücreleri (merkezin C'ye uzaklığı ≤ r) ve iç hücreler (≤ r − h)."""
    g = A.grid
    X, Y = g.centers()
    P = np.column_stack([X[A.inside], Y[A.inside]])
    reach = np.zeros_like(A.inside)
    interior = np.zeros_like(A.inside)
    if len(P):
        inC = A.bnd.dist_chunked(P) >= A.R_need
        dC = np.full(len(P), np.inf)
        for c in comps:
            dC = np.minimum(dC, _Boundary(c).dist_chunked(P))
        reach[A.inside] = inC | (dC <= A.r)
        interior[A.inside] = inC | (dC <= A.r - A.h)
    return reach, interior


def adaptive_pocket(
    region: Region,
    tool: Tool,
    cut: Cut,
    engagement: float,
    *,
    leave: float = 0.0,
    step: float | None = None,
    cell: float | None = None,
    helix_radius: float | None = None,
    ramp_angle: float = 2.0,
    climb: bool = True,
    samples: int = 1440,
) -> AdaptiveResult:
    """Temas açısı ≤ φ_t olan adaptif cep yolu (SPEC 19)."""
    if not isinstance(region, Region):
        raise CamError("region bir Region olmalı")
    phi, ra = _check_common(tool, cut, engagement, ramp_angle)
    D = tool.D
    r = D / 2
    leave = _num("leave", leave)
    if leave < 0:
        raise CamError(f"leave negatif olamaz ({leave})")
    step = D / 20 if step is None else _num("step", step)
    if not 0 < step <= r / 2 + TOL:
        raise CamError(f"Adım 0 < step ≤ r/2 olmalı (step={step}, r={r})")
    h = D / 100 if cell is None else _num("cell", cell)
    if not 0 < h <= D / 20 + TOL:
        raise CamError(f"Hücre 0 < h ≤ D/20 olmalı (h={h}, D={D})")
    if helix_radius is not None:
        helix_radius = _num("helix_radius", helix_radius)
        if helix_radius < 0:
            raise CamError(f"helix_radius negatif olamaz ({helix_radius})")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 360:
        raise CamError(f"samples en az 360 olan tam sayı olmalı ({samples!r})")
    comps = offset(region, r + leave)
    if not comps:
        raise CamError(f"Takım bölgeye sığmıyor (D={D}, leave={leave})")

    A = _Adaptive(region, r, leave, phi, step, h, samples, bool(climb), helix_radius)
    A.reach, A.interior = _reach(A, comps)
    A.air_max = max(4 * r, sum(lp.length for c in comps for lp in c.loops) + D)
    plans = [p for p in (A.component(c) for c in comps) if p is not None]
    if not plans:
        raise CamError(f"Takım bölgeye sığmıyor (D={D}, leave={leave})")

    # yolu her paso derinliğinde aynı XY ile yaz
    ccw = bool(climb)
    s0 = plans[0].start
    start = (float(s0[0]), float(s0[1]), float(cut.z_safe))
    b = _Moves(cut, np.array(start))
    z_prev = cut.z_top
    for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
        for pl in plans:
            b.helix_entry(pl.start, pl.entry, pl.rho, z, z_prev, ra, ccw)
            for k, pts in enumerate(pl.passes):
                p = pts[0]
                if k > 0:
                    if pl.keep_down[k]:
                        b.line(p[0], p[1], z)
                    else:
                        b.retract()
                        b.rapid(p[0], p[1], cut.z_safe)
                        b.rapid(p[0], p[1], max(z_prev + cut.clearance, z))
                        b.line(p[0], p[1], z, cut.plunge_feed)
                for q in pts[1:]:
                    b.line(q[0], q[1], z)
            b.retract()
        z_prev = z
    tp = b.toolpath("adaptif cep", tool, start)

    # rapor: T'nin iç hücrelerinde (C'ye uzaklığı ≤ r − h) kalan malzeme
    g = A.grid
    uncut = float(np.count_nonzero(g.m & A.interior)) * h * h
    return AdaptiveResult(tp, g, uncut, A.max_phi)
