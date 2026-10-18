"""SPEC 43 testleri için bağımsız referans hesaplar (cam.sim.tridexel / simulate5 kodu okunmadan).

Bu modül test değildir (adı test_ ile başlamaz). Yalnız numpy, cam/model.py (sabit arayüz) ve SPEC 05
testlerinin referans modülü (tests/cam/simref.py) kullanılır.

Kullanılan formüller (takım ekseni a birim, uç T; nokta p için w = p − T, eksen boyu z = w·a,
eksenden uzaklık d = √(|w|² − z²)):
- Kesen kısım (SPEC 43 "Takım katısı"): d ≤ R ve h(d) ≤ z ≤ L_f; h SPEC 05 profili (simref.h_ref).
- Gövde: basamak j için d ≤ ρ_j ve z ≥ H_j (yarı sonsuz silindirlerin birleşimi).
- Işın p(s) = o + s·u ile sonlu silindir {d ≤ ρ, z_alt ≤ z ≤ z_üst}: d(s)² ≤ ρ² ikinci derece eşitsizliği
  (|w + s u|² − ((w + s u)·a)² ≤ ρ²) ile z dilimi doğrusal eşitsizliğinin kesişimi.
- Küre (küresel uç, merkez T + R·a): |w + s u − R a|² ≤ R².
- Küresel kesen = küre ∪ silindir {R ≤ z ≤ L_f} (L_f ≥ 2R iken tam eşit; ikisi de dışbükey ve kesişik,
  ışın aralığı [min s₀, max s₁]).
- Genel referans: üyelik fonksiyonu üzerinde yoğun örnekleme + ikiye bölme (60 adım) → uç hatası ≪ 1e-9.
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import Frame, Move, MoveType, Stock, Tool, ToolKind, Toolpath
from tests.cam.simref import h_ref

EPS = 1e-15


# ------------------------------------------------------------------ çerçeve, yol


def basis(a) -> np.ndarray:
    """Sütunları (e1, e2, a) olan sağ el ortonormal matris; a birim."""
    a = np.asarray(a, dtype=float)
    a = a / np.linalg.norm(a)
    yardim = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(yardim, a)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    return np.column_stack([e1, e2, a])


def frame(origin, a) -> Frame:
    """Yerel z'si a olan iş düzlemi (p_wcs = origin + R·p_yerel)."""
    M = basis(a)
    return Frame(tuple(float(v) for v in origin), tuple(tuple(float(v) for v in r) for r in M))


def tilted_path(tool: Tool, a, world_points, kinds=None, feed: float = 600.0, name: str = "egik") -> Toolpath:
    """Sabit eksenli (a) yol: dünya noktaları iş düzlemine (yerel z = a, orijin ilk nokta) çevrilir,
    hareketlerde axis verilmez (→ çerçevenin z'si). kinds: her hareket için MoveType (varsayılan G1)."""
    fr = frame(world_points[0], a)
    loc = [tuple(float(v) for v in fr.to_local(p)) for p in world_points]
    kinds = kinds or [MoveType.LINEAR] * (len(loc) - 1)
    mv = [Move(k, p, None if k is MoveType.RAPID else feed) for k, p in zip(kinds, loc[1:], strict=True)]
    return Toolpath(name, tool, loc[0], mv, 1000.0, frame=fr)


def unit(*v) -> tuple[float, float, float]:
    a = np.asarray(v, dtype=float)
    return tuple(float(x) for x in a / np.linalg.norm(a))


def axis_xz(theta_deg: float) -> tuple[float, float, float]:
    """XZ düzleminde düşeyden θ eğik eksen (+X'e doğru)."""
    t = math.radians(theta_deg)
    return (math.sin(t), 0.0, math.cos(t))


# ------------------------------------------------------------------ ızgara


def grid3(stock: Stock, cell: float):
    """(n, d, merkezler) üç eksen için: n = ⌈L/Δ⌉, d = L/n, c_i = min + (i + ½)·d."""
    out = []
    for lo, hi in ((stock.xmin, stock.xmax), (stock.ymin, stock.ymax), (stock.zmin, stock.zmax)):
        n = math.ceil((hi - lo) / cell)
        d = (hi - lo) / n
        out.append((n, d, lo + (np.arange(n) + 0.5) * d))
    return out


def rays(stock: Stock, cell: float, axis: str):
    """Ailedeki ışınlar: [(i, j, origin, direction, (lo, hi))]; aralık parametresi dünya koordinatı."""
    (nx, _, xs), (ny, _, ys), (nz, _, zs) = grid3(stock, cell)
    out = []
    if axis == "z":
        for i in range(nx):
            for j in range(ny):
                out.append((i, j, (xs[i], ys[j], 0.0), (0.0, 0.0, 1.0), (stock.zmin, stock.zmax)))
    elif axis == "x":
        for j in range(ny):
            for k in range(nz):
                out.append((j, k, (0.0, ys[j], zs[k]), (1.0, 0.0, 0.0), (stock.xmin, stock.xmax)))
    else:
        for i in range(nx):
            for k in range(nz):
                out.append((i, k, (xs[i], 0.0, zs[k]), (0.0, 1.0, 0.0), (stock.ymin, stock.ymax)))
    return out


def fark(iv, a: float, b: float):
    """SPEC 05 aralık farkı [l, u] − [a, b]."""
    out = []
    for lo, hi in iv:
        if min(hi, a) - lo > 0:
            out.append((lo, min(hi, a)))
        if hi - max(lo, b) > 0:
            out.append((max(lo, b), hi))
    return out


# ------------------------------------------------------------------ vektörel ışın–katı kesişimleri


def _kes(a0, a1, b0, b1):
    return np.maximum(a0, b0), np.minimum(a1, b1)


def ray_cylinder(o, u, T, a, rho: float, z_lo: float, z_hi: float):
    """Işın o + s·u (u birim) ile {d ≤ rho, z_lo ≤ z ≤ z_hi} silindiri.

    T (n,3) uçlar, a (n,3) veya (3,) eksenler.
    Dönüş (s0, s1) dizileri; kesişim yoksa s0 > s1 (veya nan)."""
    o = np.asarray(o, dtype=float)
    u = np.asarray(u, dtype=float)
    T = np.atleast_2d(np.asarray(T, dtype=float))
    a = np.broadcast_to(np.asarray(a, dtype=float), T.shape)
    w = o - T
    wa = np.einsum("ij,ij->i", w, a)
    ua = a @ u
    # dilim z_lo ≤ wa + s·ua ≤ z_hi
    with np.errstate(divide="ignore", invalid="ignore"):
        s_a = (z_lo - wa) / ua
        s_b = (z_hi - wa) / ua
    paralel = np.abs(ua) < EPS
    z0 = np.where(paralel, np.where((wa >= z_lo) & (wa <= z_hi), -np.inf, np.inf), np.minimum(s_a, s_b))
    z1 = np.where(paralel, np.where((wa >= z_lo) & (wa <= z_hi), np.inf, -np.inf), np.maximum(s_a, s_b))
    # disk: A s² + B s + C ≤ 0
    A = 1.0 - ua**2
    B = 2.0 * (w @ u - wa * ua)
    C = np.einsum("ij,ij->i", w, w) - wa**2 - rho**2
    eksenel = A < 1e-14
    disk = B * B - 4 * A * C
    with np.errstate(divide="ignore", invalid="ignore"):
        kok = np.sqrt(np.maximum(disk, 0.0))
        q = -0.5 * (B + np.copysign(kok, B))
        r1 = q / A
        r2 = np.where(q != 0, C / q, 0.0)
    d0 = np.where(eksenel, np.where(C <= 0, -np.inf, np.inf), np.where(disk >= 0, np.minimum(r1, r2), np.inf))
    d1 = np.where(
        eksenel, np.where(C <= 0, np.inf, -np.inf), np.where(disk >= 0, np.maximum(r1, r2), -np.inf)
    )
    return _kes(z0, z1, d0, d1)


def ray_sphere(o, u, C, R: float):
    o = np.asarray(o, dtype=float)
    C = np.atleast_2d(np.asarray(C, dtype=float))
    w = o - C
    b = w @ np.asarray(u, dtype=float)
    c = np.einsum("ij,ij->i", w, w) - R * R
    disk = b * b - c
    kok = np.sqrt(np.maximum(disk, 0.0))
    s0 = np.where(disk >= 0, -b - kok, np.inf)
    s1 = np.where(disk >= 0, -b + kok, -np.inf)
    return s0, s1


def ray_cutter(tool: Tool, o, u, T, a):
    """Kesen kısımla kesişim (düz / matkap: silindir; küresel: küre ∪ silindir). Vektörel (T, a)."""
    R = tool.D / 2
    Lf = tool.flute_length
    if tool.kind is ToolKind.BALL:
        assert Lf >= 2 * R
        T = np.atleast_2d(np.asarray(T, dtype=float))
        a2 = np.broadcast_to(np.asarray(a, dtype=float), T.shape)
        k0, k1 = ray_sphere(o, u, T + R * a2, R)
        c0, c1 = ray_cylinder(o, u, T, a2, R, R, Lf)
        kv = k0 <= k1
        cv = c0 <= c1
        s0 = np.where(kv & cv, np.minimum(k0, c0), np.where(kv, k0, c0))
        s1 = np.where(kv & cv, np.maximum(k1, c1), np.where(kv, k1, c1))
        return s0, s1
    assert tool.corner_r == 0.0 or tool.kind is ToolKind.DRILL
    return ray_cylinder(o, u, T, a, R, 0.0, Lf)


def union(s0, s1):
    ok = s0 <= s1
    if not np.any(ok):
        return None
    return float(np.min(s0[ok])), float(np.max(s1[ok]))


def sweep_ref(tool: Tool, o, u, p0, p1, a, n: int = 2001, iters: int = 100):
    """Sabit eksenli doğrusal hareketin süpürmesiyle ışın kesişimi [s0, s1].

    s0(t) (giriş) t'de dışbükey, s1(t) (çıkış) içbükeydir (dışbükey takımın doğru boyunca ötelenmesi):
    n eşit örnekle en iyi komşuluk bulunur, sonra üçe bölme araması (iters adım) ile incelir."""
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    a = np.asarray(a, dtype=float)

    def ss(t):
        T = p0 + np.atleast_1d(t)[:, None] * (p1 - p0)
        s0, s1 = ray_cutter(tool, o, u, T, a)
        ok = s0 <= s1
        return np.where(ok, s0, np.inf), np.where(ok, s1, -np.inf)

    t = np.linspace(0.0, 1.0, n)
    s0, s1 = ss(t)
    if not np.any(np.isfinite(s0)):
        return None

    def incelt(i, f):
        lo, hi = t[max(i - 1, 0)], t[min(i + 1, n - 1)]
        for _ in range(iters):
            m1 = lo + (hi - lo) / 3
            m2 = hi - (hi - lo) / 3
            if f(m1) <= f(m2):
                hi = m2
            else:
                lo = m1
        return min(f(lo), f(hi), f(t[i]))

    g0 = incelt(int(np.argmin(s0)), lambda x: float(ss(x)[0][0]))
    g1 = -incelt(int(np.argmax(s1)), lambda x: -float(ss(x)[1][0]))
    return g0, g1


def rotate_ref(tool: Tool, o, u, T, a0, a1, n: int = 20_001):
    """Uç sabit, eksen a0 → a1 slerp: yoğun açısal örneklemle ışın kesişimi birleşimi [min s0, max s1]."""
    a0 = np.asarray(a0, dtype=float)
    a1 = np.asarray(a1, dtype=float)
    th = math.acos(max(-1.0, min(1.0, float(a0 @ a1))))
    t = np.linspace(0.0, 1.0, n)[:, None]
    A = (np.sin((1 - t) * th) * a0 + np.sin(t * th) * a1) / math.sin(th)
    TT = np.broadcast_to(np.asarray(T, dtype=float), A.shape)
    return union(*ray_cutter(tool, o, u, TT, A))


# ------------------------------------------------------------------ üyelik + ikiye bölme


def member_cutter(tool: Tool, P, T, a) -> np.ndarray:
    w = np.atleast_2d(P) - np.asarray(T, dtype=float)
    z = w @ np.asarray(a, dtype=float)
    d = np.sqrt(np.maximum(np.einsum("ij,ij->i", w, w) - z * z, 0.0))
    h = h_ref(tool, d)
    return (h <= z) & (z <= tool.flute_length)


def member_body(steps, P, T, a) -> np.ndarray:
    w = np.atleast_2d(P) - np.asarray(T, dtype=float)
    z = w @ np.asarray(a, dtype=float)
    d = np.sqrt(np.maximum(np.einsum("ij,ij->i", w, w) - z * z, 0.0))
    ic = np.zeros(len(w), dtype=bool)
    for rho, H in steps:
        ic |= (d <= rho) & (z >= H)
    return ic


def bisect_interval(member, o, u, S: float = 200.0, n: int = 40_001):
    """Dışbükey küme ile ışın kesişimi [s0, s1]: yoğun örnekle bul, uçları 60 adım ikiye bölmeyle incelt."""
    o = np.asarray(o, dtype=float)
    u = np.asarray(u, dtype=float)
    s = np.linspace(-S, S, n)
    ic = member(o + s[:, None] * u)
    idx = np.flatnonzero(ic)
    if len(idx) == 0:
        return None
    assert np.all(np.diff(idx) == 1), "kesişim tek aralık değil"
    assert 0 < idx[0] and idx[-1] < n - 1

    def uc(dis, ici):
        for _ in range(60):
            m = 0.5 * (dis + ici)
            if member((o + m * u)[None, :])[0]:
                ici = m
            else:
                dis = m
        return 0.5 * (dis + ici)

    return uc(s[idx[0] - 1], s[idx[0]]), uc(s[idx[-1] + 1], s[idx[-1]])


# ------------------------------------------------------------------ ağlar


def box_mesh(lo, hi) -> tuple[np.ndarray, np.ndarray]:
    """Eksenlere hizalı kutu: 8 köşe, 12 dışa yönlü üçgen."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    V = np.array(
        [
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
        ],
        dtype=float,
    )
    T = np.array(
        [
            (0, 2, 1), (0, 3, 2),  # alt (−z)
            (4, 5, 6), (4, 6, 7),  # üst (+z)
            (0, 1, 5), (0, 5, 4),  # y0 (−y)
            (3, 7, 6), (3, 6, 2),  # y1 (+y)
            (0, 4, 7), (0, 7, 3),  # x0 (−x)
            (1, 2, 6), (1, 6, 5),  # x1 (+x)
        ]
    )  # fmt: skip
    return V, T


def icosphere(c, r: float, n_bol: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Alt bölünmüş ikosahedron; köşeler küre üstünde (kapalı, dışa yönlü)."""
    p = (1 + math.sqrt(5)) / 2
    V = [(-1, p, 0), (1, p, 0), (-1, -p, 0), (1, -p, 0), (0, -1, p), (0, 1, p),
         (0, -1, -p), (0, 1, -p), (p, 0, -1), (p, 0, 1), (-p, 0, -1), (-p, 0, 1)]  # fmt: skip
    V = [np.array(v, dtype=float) / np.linalg.norm(v) for v in V]
    F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
         (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5),
         (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]  # fmt: skip
    for _ in range(n_bol):
        orta: dict = {}

        def m(i, j, orta=orta):
            k = (min(i, j), max(i, j))
            if k not in orta:
                v = V[i] + V[j]
                V.append(v / np.linalg.norm(v))
                orta[k] = len(V) - 1
            return orta[k]

        F2 = []
        for a, b, cc in F:
            ab, bc, ca = m(a, b), m(b, cc), m(cc, a)
            F2 += [(a, ab, ca), (b, bc, ab), (cc, ca, bc), (ab, bc, ca)]
        F = F2
    return np.asarray(c, dtype=float) + r * np.array(V), np.array(F)


def sagitta(V: np.ndarray, T: np.ndarray, c, r: float) -> float:
    """ε = r − (merkezden üçgen düzlemlerine en küçük uzaklık): ağın küreden en büyük içe sapması."""
    P = V[T]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    n /= np.linalg.norm(n, axis=1)[:, None]
    d = np.abs(np.einsum("ij,ij->i", P[:, 0] - np.asarray(c, dtype=float), n))
    return float(r - d.min())
