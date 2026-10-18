"""
SPEC 22 — Radyal dexel: Z ekseni nz hücreye bölünür; her hücre, merkezindeki z = z_i doğrusu üzerinde
malzemenin r aralık listesini tutar [(l_1, u_1), (l_2, u_2), …] (sıralı, ayrık, boyu > 0).

Hacim (Pappus, hücre başına kesin): V = Σ π·(u² − l²)·dz.
Aralık farkı (SPEC 05 dexel kuralı): [l, u] − [a, b] → [l, min(u, a)], [max(l, b), u] (boyu > 0 ise).
Parça haritası: z = z_i doğrusunun bölge sınırını kestiği noktalar, yarı açık kuralla (min ≤ z < max)
sıralanır ve çift–tek kuralıyla eşlenir; boyu 0 aralık yazılmaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.model import CamError, CylinderStock
from cam.profile import Arc, Profile, Region


def _pos_finite(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def iv_subtract(iv: list[tuple[float, float]], a: float, b: float) -> list[tuple[float, float]]:
    """Aralık listesinden [a, b] çıkarılır (SPEC 05 dexel kuralı)."""
    out: list[tuple[float, float]] = []
    for lo, hi in iv:
        if a >= hi or b <= lo:
            out.append((lo, hi))
            continue
        if min(hi, a) - lo > 0:
            out.append((lo, min(hi, a)))
        if hi - max(lo, b) > 0:
            out.append((max(lo, b), hi))
    return out


def iv_overlap(iv: list[tuple[float, float]], a: float, b: float) -> tuple[float, float]:
    """[a, b] ile listenin kesişiminin en uzun parçası: (boy, parçanın dış ucu); kesişim yoksa (0, 0)."""
    best, at = 0.0, 0.0
    for lo, hi in iv:
        d = min(hi, b) - max(lo, a)
        if d > best:
            best, at = d, min(hi, b)
    return best, at


def iv_volume(iv: list[tuple[float, float]], dz: float) -> float:
    return sum(math.pi * (u * u - lo * lo) * dz for lo, u in iv)


@dataclass
class RadialMap:
    """Radyal dexel ızgarası: hücre merkezi z_i = z0 + (i + ½)·dz; iv[i] hücrenin r aralıkları."""

    z0: float
    dz: float
    nz: int
    r_max: float
    iv: list[list[tuple[float, float]]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.iv:
            self.iv = [[] for _ in range(self.nz)]

    @classmethod
    def from_stock(
        cls,
        stock: CylinderStock,
        cell: float,
        fixtures=(),
        max_cells: int = 1_000_000,
    ) -> RadialMap:
        """Stok sınırları hücre sınırı; bağlama elemanları ızgaraya alttan / üstten tam hücre ekler."""
        if not isinstance(stock, CylinderStock):
            raise CamError(f"Torna simülasyonu CylinderStock ister ({type(stock).__name__})")
        if not _pos_finite(cell):
            raise CamError(f"Hücre boyu pozitif ve sonlu olmalı (cell={cell})")
        fixtures = list(fixtures)
        for f in fixtures:
            if not isinstance(f, CylinderStock):
                raise CamError(f"Bağlama elemanı CylinderStock olmalı ({type(f).__name__})")
        L = stock.zmax - stock.zmin
        n_s = max(1, math.ceil(L / cell - 1e-9))
        dz = L / n_s
        zf_min = min([f.zmin for f in fixtures], default=stock.zmin)
        zf_max = max([f.zmax for f in fixtures], default=stock.zmax)
        n_alt = max(0, math.ceil((stock.zmin - zf_min) / dz - 1e-9))
        n_ust = max(0, math.ceil((zf_max - stock.zmax) / dz - 1e-9))
        nz = n_alt + n_s + n_ust
        if nz > max_cells:
            raise CamError(f"Izgara çok büyük ({nz} > max_cells={max_cells})")
        r_max = max([stock.D / 2] + [f.D / 2 for f in fixtures])
        g = cls(stock.zmin - n_alt * dz, dz, nz, r_max)
        for i in range(n_alt, n_alt + n_s):
            g.iv[i] = [(stock.d / 2, stock.D / 2)]
        return g

    @classmethod
    def empty_like(cls, grid: RadialMap) -> RadialMap:
        return cls(grid.z0, grid.dz, grid.nz, grid.r_max)

    def same_grid(self, other: RadialMap) -> bool:
        return (self.z0, self.dz, self.nz) == (other.z0, other.dz, other.nz)

    def centers(self) -> np.ndarray:
        return self.z0 + (np.arange(self.nz) + 0.5) * self.dz

    def _check(self, i: int) -> None:
        if not 0 <= i < self.nz:
            raise CamError(f"Hücre indisi 0..{self.nz - 1} olmalı (i={i})")

    def intervals(self, i: int) -> list[tuple[float, float]]:
        self._check(i)
        return list(self.iv[i])

    def subtract(self, i: int, a: float, b: float) -> None:
        self._check(i)
        if not a < b:
            raise CamError(f"Aralık farkı: a < b olmalı (a={a}, b={b})")
        self.iv[i] = iv_subtract(self.iv[i], float(a), float(b))

    def add(self, i: int, a: float, b: float) -> None:
        """[a, b] eklenir; çakışan ve değen aralıklar birleştirilir."""
        self._check(i)
        if not a < b:
            raise CamError(f"Aralık ekleme: a < b olmalı (a={a}, b={b})")
        out: list[tuple[float, float]] = []
        a, b = float(a), float(b)
        for lo, hi in self.iv[i]:
            if hi < a or lo > b:
                out.append((lo, hi))
            else:
                a, b = min(a, lo), max(b, hi)
        out.append((a, b))
        out.sort()
        self.iv[i] = out

    def outer(self) -> np.ndarray:
        return np.array([iv[-1][1] if iv else 0.0 for iv in self.iv], dtype=float)

    def inner(self) -> np.ndarray:
        return np.array([iv[0][0] if iv else 0.0 for iv in self.iv], dtype=float)

    def volume(self) -> float:
        return float(sum(iv_volume(iv, self.dz) for iv in self.iv))

    def copy(self) -> RadialMap:
        return RadialMap(self.z0, self.dz, self.nz, self.r_max, [list(iv) for iv in self.iv])


# ---------------------------------------------------------------- parça haritası


def _pairs(xs: list[float]) -> list[tuple[float, float]]:
    """Sıralı kesişimler → çift–tek aralıkları, x ≥ 0'a kırpılmış, boyu > 0."""
    xs = sorted(xs)
    out = []
    for lo, hi in zip(xs[0::2], xs[1::2], strict=False):
        lo = max(lo, 0.0)
        if hi > lo:
            out.append((lo, hi))
    return out


def _fill(grid: RadialMap, crossings: list[list[float]]) -> RadialMap:
    m = RadialMap.empty_like(grid)
    for i, xs in enumerate(crossings):
        for lo, hi in _pairs(xs):
            m.add(i, lo, hi)
    return m


def _line_crossings(S: np.ndarray, zc: np.ndarray, out: list[list[float]]) -> None:
    """Doğru parçaları S (k, 2, 2), (u, v) uçları: min(u) ≤ z < max(u) yarı açık kural; u sabitse atlanır."""
    if len(S) == 0:
        return
    u0, v0, u1, v1 = S[:, 0, 0], S[:, 0, 1], S[:, 1, 0], S[:, 1, 1]
    S_ok = u0 != u1
    u0, v0, u1, v1 = u0[S_ok], v0[S_ok], u1[S_ok], v1[S_ok]
    umin, umax = np.minimum(u0, u1), np.maximum(u0, u1)
    for i, z in enumerate(zc):
        m = (umin <= z) & (z < umax)
        if m.any():
            t = (z - u0[m]) / (u1[m] - u0[m])
            out[i].extend((v0[m] + t * (v1[m] - v0[m])).tolist())


def _arc_crossings(s: Arc, zc: np.ndarray, out: list[list[float]]) -> None:
    """Yay u-monoton parçalara (θ = kπ) bölünür; parçada v = c_v ± √(R² − (z − c_u)²)."""
    cu, cv, R = float(s.c[0]), float(s.c[1]), float(s.R)
    ta, tb = (s.a0, s.a0 + s.sweep) if s.ccw else (s.a0 - s.sweep, s.a0)
    k0, k1 = math.floor(ta / math.pi) + 1, math.ceil(tb / math.pi) - 1
    cuts = [ta] + [k * math.pi for k in range(k0, k1 + 1)] + [tb]

    def u_at(th: float, k: int | None) -> float:
        if k is not None:
            return cu + (R if k % 2 == 0 else -R)
        return cu + R * math.cos(th)

    ks = [None] + list(range(k0, k1 + 1)) + [None]
    # uç noktalar profildeki köşelerle birebir aynı olsun
    p_a, p_b = (s.p0, s.p1) if s.ccw else (s.p1, s.p0)
    for j in range(len(cuts) - 1):
        a, b = cuts[j], cuts[j + 1]
        if b - a <= 0:
            continue
        ua = float(p_a[0]) if j == 0 else u_at(a, ks[j])
        ub = float(p_b[0]) if j == len(cuts) - 2 else u_at(b, ks[j + 1])
        if ua == ub:
            continue
        sg = 1.0 if math.sin(0.5 * (a + b)) > 0 else -1.0
        lo, hi = min(ua, ub), max(ua, ub)
        for i, z in enumerate(zc):
            if lo <= z < hi:
                out[i].append(cv + sg * math.sqrt(max(R * R - (z - cu) ** 2, 0.0)))


def profile_rmap(region: Region | Profile, grid: RadialMap) -> RadialMap:
    """(u, v) = (z, x) düzlemindeki kapalı bölgenin yarı kesit haritası (çift–tek kuralı)."""
    if isinstance(region, Profile):
        if not region.closed:
            raise CamError("profile_rmap: profil kapalı olmalı")
        loops = [region]
    elif isinstance(region, Region):
        loops = region.loops
    else:
        raise CamError(f"profile_rmap: Region veya Profile bekleniyor ({type(region).__name__})")
    zc = grid.centers()
    out: list[list[float]] = [[] for _ in range(grid.nz)]
    lines = []
    for loop in loops:
        for s in loop.segments:
            if isinstance(s, Arc):
                _arc_crossings(s, zc, out)
            else:
                lines.append([s.p0, s.p1])
    _line_crossings(np.array(lines, dtype=float).reshape(-1, 2, 2), zc, out)
    return _fill(grid, out)


def mesh_rmap(V, T, grid: RadialMap) -> RadialMap:
    """Üçgen ağı y = 0 düzlemiyle kesilir (y ≥ 0 artı taraf); kesit doğruları (z, x) profile_rmap gibi."""
    V = np.asarray(V, dtype=float)
    T = np.asarray(T, dtype=int)
    if V.ndim != 2 or V.shape[1] != 3 or T.ndim != 2 or T.shape[1] != 3:
        raise CamError("mesh_rmap: V (n, 3), T (m, 3) olmalı")
    P = V[T]  # (m, 3, 3)
    pos = P[:, :, 1] >= 0
    npos = pos.sum(axis=1)
    P = P[(npos == 1) | (npos == 2)]
    pos = pos[(npos == 1) | (npos == 2)]
    segs = []
    for tri, sg in zip(P, pos, strict=True):
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if sg[a] != sg[b]:
                pa, pb = tri[a], tri[b]
                t = pa[1] / (pa[1] - pb[1])
                q = pa + t * (pb - pa)
                if pa[1] == 0:
                    q = pa
                elif pb[1] == 0:
                    q = pb
                pts.append((q[2], q[0]))
        if len(pts) == 2 and pts[0] != pts[1]:
            segs.append(pts)
    zc = grid.centers()
    out: list[list[float]] = [[] for _ in range(grid.nz)]
    _line_crossings(np.array(segs, dtype=float).reshape(-1, 2, 2), zc, out)
    return _fill(grid, out)


def part_rmap(part, grid: RadialMap, tol: float = 0.01) -> RadialMap:
    """Part (SPEC 02) → ağ (part.mesh(tol)) → mesh_rmap. Parçanın dönel simetrik olduğu varsayılır."""
    V, T = part.mesh(tol)
    return mesh_rmap(V, T, grid)
