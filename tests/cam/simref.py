"""SPEC 05 testleri için bağımsız referans hesaplar (cam.sim'e güvenmeden).

Bu modül test değildir (adı test_ ile başlamaz). Sadece numpy ve sabit arayüzler (cam/model.py) kullanır;
cam.sim'in iç dosyaları okunmadı, beklenen değerler SPEC 05 "Teori" bölümündeki formüllerden yazıldı.

Kullanılan formüller:
- Izgara: nx = ⌈Lx/Δ⌉, dx = Lx/nx, merkez x_i = xmin + (i + ½)·dx (SPEC 05 "Z-haritası").
- Takım alt yüzeyi h(d): düz 0; küresel R − √(R² − d²); köşe radyüslü d ≤ R − r_c → 0,
  aksi r_c − √(r_c² − (d − R + r_c)²); d > R → +∞ (SPEC 05 "Takım alt yüzeyi").
- Doğru parçası boyunca d(t)² = a t² − 2 (w·v) t + |w|², v = Δxy, w = q − P0xy; d(t) ≤ ρ aralığı
  t ∈ t_c ± √(t_c² − (|w|² − ρ²)/a), t_c = (w·v)/a, [0, 1] ile kesişimi (a = 0: düşey hareket).
- Düz takım zarfı: z(t) doğrusal → en küçük değer aralık ucunda (Δz ≥ 0 → t_a, değilse t_b).
- Küresel / köşe radyüslü zarf: [t_a, t_b] aralığında ≥ 10⁵ eşit örnekle kaba kuvvet en küçük değer.
- Nokta–doğru parçası uzaklığı: izdüşüm parametresi clamp((w·v)/|v|², 0, 1).
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import Move, MoveType, Stock, Tool, ToolKind, Toolpath

FEED = 600.0
RPM = 1000.0


# ------------------------------------------------------------------ takımlar


def flat(D: float = 6.0, Lf: float = 30.0, **kw) -> Tool:
    return Tool(1, "duz", ToolKind.FLAT, D, Lf, **kw)


def ball(D: float = 6.0, Lf: float = 30.0, **kw) -> Tool:
    return Tool(2, "kuresel", ToolKind.BALL, D, Lf, **kw)


def bull(D: float = 6.0, rc: float = 1.5, Lf: float = 30.0, **kw) -> Tool:
    return Tool(3, "koseli", ToolKind.FLAT, D, Lf, corner_r=rc, **kw)


def drill(D: float = 8.0, Lf: float = 25.0, **kw) -> Tool:
    return Tool(4, "matkap", ToolKind.DRILL, D, Lf, **kw)


def h_ref(tool: Tool, d) -> np.ndarray:
    """Takım alt yüzeyi h(d), SPEC 05 formülleriyle."""
    d = np.asarray(d, dtype=float)
    R = tool.D / 2
    rc = 0.0 if tool.kind is ToolKind.DRILL else tool.corner_r
    out = np.full(d.shape, np.inf)
    ic = d <= R
    if rc == 0.0:
        out[ic] = 0.0
        return out
    düz = d <= R - rc
    out[düz] = 0.0
    yay = ic & ~düz
    out[yay] = rc - np.sqrt(rc**2 - (d[yay] - R + rc) ** 2)
    return out


# ------------------------------------------------------------------ ızgara


def grid(stock: Stock, cell: float) -> tuple[int, int, float, float, np.ndarray, np.ndarray]:
    """(nx, ny, dx, dy, X, Y); X, Y hücre merkezleri, şekil (ny, nx)."""
    Lx = stock.xmax - stock.xmin
    Ly = stock.ymax - stock.ymin
    nx = math.ceil(Lx / cell)
    ny = math.ceil(Ly / cell)
    dx = Lx / nx
    dy = Ly / ny
    xs = stock.xmin + (np.arange(nx) + 0.5) * dx
    ys = stock.ymin + (np.arange(ny) + 0.5) * dy
    X, Y = np.meshgrid(xs, ys)
    return nx, ny, dx, dy, X, Y


# ------------------------------------------------------------------ doğru parçası


def seg_dist(X, Y, p0, p1) -> np.ndarray:
    """Hücre merkezlerinin XY'de [p0, p1] doğru parçasına uzaklığı."""
    ax, ay = p0[0], p0[1]
    vx, vy = p1[0] - ax, p1[1] - ay
    wx, wy = X - ax, Y - ay
    L2 = vx * vx + vy * vy
    if L2 == 0.0:
        return np.hypot(wx, wy)
    t = np.clip((wx * vx + wy * vy) / L2, 0.0, 1.0)
    return np.hypot(wx - t * vx, wy - t * vy)


def t_interval(qx: float, qy: float, p0, p1, rho: float) -> tuple[float, float] | None:
    """d(t) ≤ rho olan t ∈ [0, 1] aralığı; yoksa None."""
    vx, vy = p1[0] - p0[0], p1[1] - p0[1]
    wx, wy = qx - p0[0], qy - p0[1]
    a = vx * vx + vy * vy
    ww = wx * wx + wy * wy
    if a == 0.0:
        return (0.0, 1.0) if ww <= rho * rho else None
    tc = (wx * vx + wy * vy) / a
    disk = tc * tc - (ww - rho * rho) / a
    if disk < 0.0:
        return None
    s = math.sqrt(disk)
    ta, tb = max(tc - s, 0.0), min(tc + s, 1.0)
    if ta > tb:
        return None
    return ta, tb


def flat_envelope_ref(X, Y, p0, p1, rho: float) -> np.ndarray:
    """min { z(t) : d(t) ≤ rho } kapalı formla; dokunmayan inf."""
    out = np.full(np.shape(X), np.inf)
    dz = p1[2] - p0[2]
    for idx in np.ndindex(out.shape):
        iv = t_interval(float(X[idx]), float(Y[idx]), p0, p1, rho)
        if iv is None:
            continue
        t = iv[0] if dz >= 0 else iv[1]
        out[idx] = p0[2] + t * dz
    return out


def flat_top_ref(X, Y, p0, p1, rho: float, Lf: float) -> np.ndarray:
    """e_üst = L_f + max { z(t) : d(t) ≤ rho }; dokunmayan −inf."""
    out = np.full(np.shape(X), -np.inf)
    dz = p1[2] - p0[2]
    for idx in np.ndindex(out.shape):
        iv = t_interval(float(X[idx]), float(Y[idx]), p0, p1, rho)
        if iv is None:
            continue
        t = iv[1] if dz >= 0 else iv[0]
        out[idx] = Lf + p0[2] + t * dz
    return out


def brute_envelope(tool: Tool, qx: float, qy: float, p0, p1, n: int = 200_001) -> float:
    """e(q) kaba kuvvetle: [t_a, t_b] aralığında n eşit örnek (uçlar dahil)."""
    iv = t_interval(qx, qy, p0, p1, tool.D / 2)
    if iv is None:
        return math.inf
    t = np.linspace(iv[0], iv[1], n)
    px = p0[0] + t * (p1[0] - p0[0])
    py = p0[1] + t * (p1[1] - p0[1])
    pz = p0[2] + t * (p1[2] - p0[2])
    d = np.minimum(np.hypot(qx - px, qy - py), tool.D / 2)  # aralık içi; yuvarlama taşmasını kırp
    return float(np.min(pz + h_ref(tool, d)))


# ------------------------------------------------------------------ yay


def arc_dist(X, Y, c, Rc: float, th0: float, sweep: float) -> np.ndarray:
    """Merkez c, yarıçap Rc, th0'dan saat yönü tersinde sweep kadar yaya uzaklık."""
    ax = np.arctan2(Y - c[1], X - c[0])
    rel = np.mod(ax - th0, 2 * math.pi)
    radial = np.abs(np.hypot(X - c[0], Y - c[1]) - Rc)
    e0 = (c[0] + Rc * math.cos(th0), c[1] + Rc * math.sin(th0))
    th1 = th0 + sweep
    e1 = (c[0] + Rc * math.cos(th1), c[1] + Rc * math.sin(th1))
    uc = np.minimum(np.hypot(X - e0[0], Y - e0[1]), np.hypot(X - e1[0], Y - e1[1]))
    return np.where(rel <= sweep, radial, uc)


# ------------------------------------------------------------------ yollar


def G0(x, y, z) -> Move:
    return Move(MoveType.RAPID, (x, y, z))


def G1(x, y, z, F: float = FEED) -> Move:
    return Move(MoveType.LINEAR, (x, y, z), F)


def path(tool: Tool, start, moves: list[Move], name: str = "yol") -> Toolpath:
    return Toolpath(name, tool, start, moves, RPM)


def rect_pocket(tool: Tool, x0, y0, a, b, z, z_safe: float = 5.0, rows: int | None = None) -> Toolpath:
    """Elle kurulmuş a × b dikdörtgen cep yolu (tek paso, derinlik z): ofsetli zigzag + kontur.

    Takım merkezi dikdörtgeni [x0+R, x0+a−R] × [y0+R, y0+b−R]; satır aralığı ≤ 2R olduğundan merkez
    dikdörtgeninin her noktası bir satıra ≤ R uzaklıkta, kenar noktaları kontur üstünde. Süpürülen bölge
    = merkez dikdörtgeni ⊕ R diski = köşe yarıçapı R olan a × b dikdörtgen, alan ab − (4 − π)R².
    """
    R = tool.D / 2
    xa, xb = x0 + R, x0 + a - R
    ya, yb = y0 + R, y0 + b - R
    if rows is None:
        rows = math.ceil((yb - ya) / (1.5 * R)) + 1
    ys = [ya + (yb - ya) * j / (rows - 1) for j in range(rows)]
    xm, ym = (xa + xb) / 2, (ya + yb) / 2
    mv = [G0(xm, ym, z_safe - 4.0), G1(xm, ym, z), G1(xa, ys[0], z)]
    for j, y in enumerate(ys):
        x_bas, x_son = (xa, xb) if j % 2 == 0 else (xb, xa)
        if j > 0:
            mv.append(G1(x_bas, y, z))
        mv.append(G1(x_son, y, z))
    # kontur: merkez dikdörtgeninin çevresi
    mv += [G1(xa, yb, z), G1(xa, ya, z), G1(xb, ya, z), G1(xb, yb, z), G1(xa, yb, z), G1(xa, yb, z_safe)]
    return path(tool, (xm, ym, z_safe), mv, "cep")


def in_rounded_rect(X, Y, x0, y0, a, b, R) -> np.ndarray:
    """İşaretli uzaklık: merkez dikdörtgenine uzaklık − R (≤ 0 → süpürülen bölgede)."""
    xa, xb = x0 + R, x0 + a - R
    ya, yb = y0 + R, y0 + b - R
    ddx = np.maximum(np.maximum(xa - X, X - xb), 0.0)
    ddy = np.maximum(np.maximum(ya - Y, Y - yb), 0.0)
    return np.hypot(ddx, ddy) - R


def random_program(tool: Tool, n: int = 50, seed: int = 20261018) -> Toolpath:
    """Sabit tohumlu rastgele program: G1, G0 ve G2/G3 (yarıçapı tutarlı yaylar) karışımı.

    Uç noktaları x ∈ [−5, 35], y ∈ [−5, 25], z ∈ [−8, 3]; stok 0..30 × 0..20 × zmin..0 için.
    """
    rng = np.random.default_rng(seed)
    p = (-5.0, -5.0, 3.0)
    mv: list[Move] = []
    for _ in range(n):
        u = rng.random()
        z = float(rng.uniform(-8.0, 3.0))
        if u < 0.2:
            q = (float(rng.uniform(-5, 35)), float(rng.uniform(-5, 25)), z)
            mv.append(G0(*q))
        elif u < 0.75:
            q = (float(rng.uniform(-5, 35)), float(rng.uniform(-5, 25)), z)
            mv.append(G1(*q))
        else:
            Rc = float(rng.uniform(2.0, 8.0))
            a0 = float(rng.uniform(0, 2 * math.pi))
            c = (p[0] - Rc * math.cos(a0), p[1] - Rc * math.sin(a0))
            a1 = a0 + float(rng.uniform(0.3, 5.0))
            q = (c[0] + Rc * math.cos(a1), c[1] + Rc * math.sin(a1), z)
            t = MoveType.ARC_CCW if rng.random() < 0.5 else MoveType.ARC_CW
            mv.append(Move(t, q, FEED, center=c))
        p = mv[-1].end
    return path(tool, (-5.0, -5.0, 3.0), mv, "rastgele")


RANDOM_STOCK = Stock(0.0, 0.0, -6.0, 30.0, 20.0, 0.0)
