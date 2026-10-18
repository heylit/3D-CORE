"""SPEC 22 testleri için bağımsız referans hesaplar (cam.sim'e güvenmeden).

Bu modül test değildir (adı test_ ile başlamaz). Sadece numpy, sabit arayüzler (cam/model.py) ve SPEC 20
yol üreticileri kullanılır; cam.sim'in SPEC 22 dosyaları okunmadı. Beklenen değerler SPEC 22 "Teori"
bölümündeki tanımlardan yazıldı.

Kullanılan tanımlar (SPEC 22):
- Kenar yönleri e(α) = (−cos α, sin α), (z, x) sırasında; e₁ = e(κr), e₂ = e(κr + εr).
- Çekirdek üçgen Q = üçgen(C, C + l·e₁, C + l·e₂), kesici bölge K = Q ⊕ D(r).
- Doğrusal süpürme S = conv(Q(P0) ∪ Q(P1)) ⊕ D(r); z = z_i doğrusuyla kesişim tek aralık [a, b].
  Dışbükey çokgen ⊕ disk'in sınırı ötelenmiş kenarlar ve köşe yaylarıdır; doğruyla kesişimin uçları
  bu parçaların doğruyla kesişim noktalarının en küçüğü ve en büyüğüdür (kesin hesap).
- Kaba kuvvet: hareket boyunca ≥ 10⁵ eşit konumda durağan bölgenin aralığı, en küçük a / en büyük b.
- x → r: a ≥ 0 → [a, b]; b ≤ 0 → [−b, −a]; aksi [0, max(−a, b)].
- Aralık farkı: [l, u] − [a, b] → [l, min(u, a)], [max(l, b), u] (boyu > 0 ise).
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import (
    CylinderStock,
    FeedMode,
    LatheHolder,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Toolpath,
)

RPM = 1000.0
FEED = 0.2  # mm/dev


# ------------------------------------------------------------------ takımlar


def turn_tool(
    r: float = 0.8,
    edge: float = 8.0,
    holder: LatheHolder | None = None,
    id: int = 1,
    kr: float = 93.0,
    er: float = 80.0,
) -> LatheTool:
    """CNMG benzeri dış tornalama ucu, T = 3."""
    return LatheTool(id, "tornalama", LatheToolKind.TURN, r, 3, kr, er, edge_len=edge, holder=holder)


def bore_tool(r: float = 0.4, edge: float = 6.0, holder: LatheHolder | None = None, id: int = 2) -> LatheTool:
    """İç tornalama ucu, T = 2 (dış çerçevede T = 3'ün aynası)."""
    return LatheTool(id, "ic_tornalama", LatheToolKind.BORE, r, 2, 93.0, 80.0, edge_len=edge, holder=holder)


def groove_tool(tip: int = 3, w: float = 3.0, r: float = 0.3, edge: float = 6.0, id: int = 3) -> LatheTool:
    return LatheTool(id, "kanal", LatheToolKind.GROOVE, r, tip, 90.0, 90.0, width=w, edge_len=edge)


def thread_tool(r: float = 0.1, edge: float = 3.0, id: int = 4) -> LatheTool:
    """60° diş ucu, T = 8."""
    return LatheTool(id, "dis", LatheToolKind.THREAD, r, 8, 60.0, 60.0, edge_len=edge)


def e(alpha_deg: float) -> np.ndarray:
    """Kenar yönü e(α) = (−cos α, sin α), (z, x)."""
    a = math.radians(alpha_deg)
    return np.array([-math.cos(a), math.sin(a)])


def tip_q(tip: int, r: float) -> np.ndarray:
    """Hayali uç kayması q_T = r·(s_z, s_x) (SPEC 20, Fanuc uç numarası)."""
    s = {
        0: (0, 0),
        1: (1, 1),
        2: (-1, 1),
        3: (-1, -1),
        4: (1, -1),
        5: (1, 0),
        6: (0, 1),
        7: (-1, 0),
        8: (0, -1),
        9: (0, 0),
    }
    return r * np.array(s[tip], dtype=float)


# ------------------------------------------------------------------ yol kurucular (x, z)


def G0(x: float, z: float) -> Move:
    return Move(MoveType.RAPID, (x, 0.0, z))


def G1(x: float, z: float, F: float = FEED) -> Move:
    return Move(MoveType.LINEAR, (x, 0.0, z), F)


def lpath(
    tool: LatheTool,
    start: tuple[float, float],
    moves: list[Move],
    rpm: float = RPM,
    css: float | None = None,
    feed_mode: FeedMode = FeedMode.PER_REV,
    name: str = "yol",
) -> Toolpath:
    """Torna yolu: start = (x, z), G18, varsayılan G95."""
    tp = Toolpath(
        name=name,
        tool=tool,
        start=(start[0], 0.0, start[1]),
        moves=list(moves),
        rpm=rpm,
        plane=Plane.ZX,
        feed_mode=feed_mode,
        css=css,
    )
    tp.validate()
    return tp


def centers(stock: CylinderStock, cell: float, n_below: int = 0) -> np.ndarray:
    """SPEC 22 ızgarası: n_s = ⌈L/Δ⌉, dz = L/n_s, z_i = z0 + (i + ½)·dz, z0 = zmin − n_below·dz."""
    n_s = math.ceil(stock.length / cell)
    dz = stock.length / n_s
    z0 = stock.zmin - n_below * dz
    return z0 + (np.arange(n_s + n_below) + 0.5) * dz


# ------------------------------------------------------------------ aralık işlemleri


def iv_subtract(iv: list[tuple[float, float]], a: float, b: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for lo, hi in iv:
        if min(hi, a) - lo > 0:
            out.append((lo, min(hi, a)))
        if hi - max(lo, b) > 0:
            out.append((max(lo, b), hi))
    return out


def iv_length_overlap(p: list[tuple[float, float]], q: list[tuple[float, float]]) -> float:
    """İki aralık listesinin kesişiminin en uzun parçası."""
    best = 0.0
    for a, b in p:
        for c, d in q:
            best = max(best, min(b, d) - max(a, c))
    return best


def iv_volume(iv: list[tuple[float, float]], dz: float) -> float:
    return sum(math.pi * (u * u - lo * lo) * dz for lo, u in iv)


def iv_is_valid(iv) -> bool:
    """Sıralı, ayrık, her aralığın boyu > 0, l ≥ 0."""
    prev = -math.inf
    for lo, hi in iv:
        if not (lo >= 0 and hi > lo and lo > prev):
            return False
        prev = hi
    return True


# ------------------------------------------------------------------ süpürme aralığı (kesin)


def hull(P: np.ndarray) -> np.ndarray:
    """Dışbükey zarf (monoton zincir), saat yönü tersi; tekrar eden noktalar atılır."""
    pts = sorted({(float(p[0]), float(p[1])) for p in P})
    if len(pts) <= 2:
        return np.array(pts)

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and cr(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and cr(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def rounded_x(H: np.ndarray, r: float, z: float) -> tuple[float, float]:
    """Dışbükey çokgen H ⊕ D(r)'nin z doğrusuyla kesişimi [a, b] (x); kesişmezse (inf, −inf)."""
    cand: list[float] = []
    m = len(H)
    for v in H:
        d = z - v[0]
        if abs(d) <= r:
            s = math.sqrt(max(r * r - d * d, 0.0))
            cand += [v[1] - s, v[1] + s]
    edges = [(H[i], H[(i + 1) % m]) for i in range(m)] if m >= 2 else []
    for p, q in edges:
        t = q - p
        L = math.hypot(*t)
        if L == 0:
            continue
        n = np.array([t[1], -t[0]]) / L
        for sg in (1.0, -1.0):
            a, b = p + sg * r * n, q + sg * r * n
            if a[0] == b[0]:
                if z == a[0]:
                    cand += [a[1], b[1]]
                continue
            u = (z - a[0]) / (b[0] - a[0])
            if 0.0 <= u <= 1.0:
                cand.append(a[1] + u * (b[1] - a[1]))
    if not cand:
        return math.inf, -math.inf
    return min(cand), max(cand)


def sweep_x(poly, r: float, p0, p1, z) -> tuple[np.ndarray, np.ndarray]:
    """conv(poly + p0 ∪ poly + p1) ⊕ D(r) ∩ {z = z_i}, kesin. p0, p1 (z, x)."""
    poly = np.atleast_2d(np.asarray(poly, dtype=float))
    H = hull(np.vstack([poly + np.asarray(p0, float), poly + np.asarray(p1, float)]))
    z = np.atleast_1d(np.asarray(z, dtype=float))
    out = np.array([rounded_x(H, r, float(zi)) for zi in z])
    return out[:, 0], out[:, 1]


def brute_sweep_x(poly, r: float, p0, p1, z, n: int = 200_001) -> tuple[np.ndarray, np.ndarray]:
    """Kaba kuvvet: n eşit konumda durağan bölge H ⊕ D(r) aralığı; en küçük a, en büyük b."""
    poly = np.atleast_2d(np.asarray(poly, dtype=float))
    H = hull(poly)
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    t = np.linspace(0.0, 1.0, n)
    pos = p0[None, :] + t[:, None] * (p1 - p0)[None, :]  # (n, 2)
    z = np.atleast_1d(np.asarray(z, dtype=float))
    A = np.full(z.shape, np.inf)
    B = np.full(z.shape, -np.inf)
    m = len(H)
    for j, zi in enumerate(z):
        lo = np.full(n, np.inf)
        hi = np.full(n, -np.inf)
        for v in H:
            d = zi - (v[0] + pos[:, 0])
            ok = np.abs(d) <= r
            s = np.sqrt(np.clip(r * r - d * d, 0.0, None))
            xv = v[1] + pos[:, 1]
            lo = np.where(ok, np.minimum(lo, xv - s), lo)
            hi = np.where(ok, np.maximum(hi, xv + s), hi)
        for i in range(m if m >= 2 else 0):
            p, q = H[i], H[(i + 1) % m]
            tt = q - p
            L = math.hypot(*tt)
            if L == 0 or tt[0] == 0:
                continue
            nn = np.array([tt[1], -tt[0]]) / L
            for sg in (1.0, -1.0):
                a, b = p + sg * r * nn, q + sg * r * nn
                u = (zi - (a[0] + pos[:, 0])) / (b[0] - a[0])
                ok = (u >= 0) & (u <= 1)
                xv = a[1] + pos[:, 1] + u * (b[1] - a[1])
                lo = np.where(ok, np.minimum(lo, xv), lo)
                hi = np.where(ok, np.maximum(hi, xv), hi)
        A[j] = lo.min()
        B[j] = hi.max()
    return A, B


def radial(a: float, b: float, hw: float = 0.0) -> tuple[float, float]:
    """x aralığı → r aralığı (SPEC 22 "x → r", tutucu kalınlığı √(x² + hw²))."""
    if a >= 0:
        return a, math.hypot(b, hw)
    if b <= 0:
        return -b, math.hypot(a, hw)
    return 0.0, math.hypot(max(-a, b), hw)


def turn_core(tool: LatheTool) -> np.ndarray:
    """Dış çerçevede TURN/BORE/THREAD çekirdek üçgeni (C'ye göre)."""
    l = tool.edge_len  # noqa: E741
    return np.array([[0.0, 0.0], l * e(tool.kappa_r), l * e(tool.kappa_r + tool.eps_r)])


def cut_map(
    init: list[list[tuple[float, float]]],
    zc: np.ndarray,
    core: np.ndarray,
    r: float,
    q: np.ndarray,
    pts: list[tuple[float, float]],
    sgn: int = 1,
) -> list[list[tuple[float, float]]]:
    """Doğrusal hareket zinciri (hayali uç noktaları (x, z)) için malzeme sonucu (alt adımdan bağımsız).

    C = P − q (dış çerçevede); iç çerçevede (sgn = −1) şekil x → −x aynalanır.
    """
    core = core * np.array([1.0, sgn])
    out = [list(iv) for iv in init]
    for (x0, z0), (x1, z1) in zip(pts[:-1], pts[1:], strict=True):
        c0 = np.array([z0, x0]) - q
        c1 = np.array([z1, x1]) - q
        a, b = sweep_x(core, r, c0, c1, zc)
        for i in range(len(zc)):
            if a[i] <= b[i]:
                lo, hi = radial(a[i], b[i])
                if hi > lo:
                    out[i] = iv_subtract(out[i], lo, hi)
    return out
