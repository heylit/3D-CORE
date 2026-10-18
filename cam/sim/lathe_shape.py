"""
SPEC 22 — Torna takımının kesiti: kesici bölge K = Q ⊕ D(r), gövde uzantısı, tutucu; süpürme aralıkları.

Dış çerçevede (T = 3 yönü) C'ye göre kenar yönleri e(α) = (−cos α, sin α), (z, x) sırasında;
ana kenar e₁ = e(κr), arka kenar e₂ = e(κr + εr). İç çerçevede şekil x → −x aynalanır.
Eksenel takım (matkap, x = 0): uç konisi L_uç = (D/2)/tan(φ/2) + flute_length boyunda [−D/2, D/2] dikdörtgen.
Doğrusal süpürme: conv(Q(P0) ∪ Q(P1)) ⊕ D(r); z = z_i doğrusuyla kesişim tek aralık [a, b] (x cinsinden).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.model import CamError, LatheTool, LatheToolKind, Tool, ToolKind

REACH = 1000.0  # mm, gövde uzantısının kesildiği varsayılan boy (simülasyon ızgaraya göre verir)
AXIAL = (ToolKind.DRILL, ToolKind.CONE)


@dataclass
class LatheShape:
    """Burun merkezi C'ye göre (z, x) çokgenler; core ve body r yarıçaplı diskle genişletilir."""

    core: np.ndarray  # (m, 2) kesici çekirdek Q
    r: float  # burun yarıçapı
    body: np.ndarray  # (p, 2) gövde uzantısı Q_B (kesilmiş)
    holder: np.ndarray | None  # (h, 2) tutucu H
    half_width: float  # tutucunun y yönünde yarı kalınlığı


def e(alpha: float) -> np.ndarray:
    """Kenar yönü e(α) = (−cos α, sin α), α derece."""
    a = math.radians(alpha)
    return np.array([-math.cos(a), math.sin(a)])


def cutter_shape(tool: LatheTool | Tool, side: str | None, reach: float | None = None) -> LatheShape:
    """LatheTool: side "dis" veya "ic"; edge_len None, uyumsuz tür/taraf, tutucu K'ye giriyor → CamError.

    Eksenel takım (Tool, DRILL/CONE; SPEC 40 E4): uca göre koni + kesici boy beşgeni, r = 0,
    gövde = sap; side yok sayılır. reach: gövde uzantısının kesildiği boy (None → l + 1000 mm).
    """
    if isinstance(tool, Tool):
        return _axial_shape(tool, reach)
    if not isinstance(tool, LatheTool):
        raise CamError(f"Torna simülasyonu LatheTool veya eksenel Tool ister ({type(tool).__name__})")
    if side not in ("dis", "ic"):
        raise CamError(f"Taraf 'dis' veya 'ic' olmalı ({side!r})")
    l = tool.edge_len  # noqa: E741
    if l is None:
        raise CamError(f"Takım '{tool.name}': kesici kenar boyu (edge_len) yok; kesici bölge tanımsız")
    r = float(tool.nose_r)
    Lt = l + REACH if reach is None else max(float(reach), l + 1.0)
    kind = tool.kind
    if kind is LatheToolKind.TURN and side != "dis":
        raise CamError(f"Takım '{tool.name}': dış tornalama ucu yalnız dışta kullanılır")
    if kind is LatheToolKind.BORE and side != "ic":
        raise CamError(f"Takım '{tool.name}': iç tornalama ucu yalnız içte kullanılır")
    if kind is LatheToolKind.GROOVE:
        uygun = (3, 4) if side == "dis" else (1, 2)
        if tool.tip not in uygun:
            raise CamError(f"Takım '{tool.name}': kanal ucu {side} tarafta T ∈ {uygun} olmalı (T={tool.tip})")
        w = float(tool.width) - 2 * r
        if w < 0:
            raise CamError(f"Takım '{tool.name}': kanal genişliği 2r'den küçük")
        zl = 0.0 if tool.tip in (3, 2) else -w
        core = np.array([[zl, 0.0], [zl + w, 0.0], [zl + w, l], [zl, l]])
        body = np.array([[zl, l], [zl + w, l], [zl + w, Lt], [zl, Lt]])
    else:
        e1, e2 = e(tool.kappa_r), e(tool.kappa_r + tool.eps_r)
        core = np.array([[0.0, 0.0], l * e1, l * e2])
        body = np.array([l * e1, Lt * e1, Lt * e2, l * e2])
    holder = None
    hw = 0.0
    if tool.holder is not None:
        holder = np.array(tool.holder.polygon, dtype=float)
        hw = float(tool.holder.half_width)
        if _poly_distance(holder, core) < r - 1e-9:
            raise CamError(f"Takım '{tool.name}': tutucu kesici bölgeye (K) giriyor")
    if side == "ic":
        m = np.array([1.0, -1.0])
        core, body = core * m, body * m
        holder = None if holder is None else holder * m
    return LatheShape(core, r, body, holder, hw)


def _axial_shape(tool: Tool, reach: float | None) -> LatheShape:
    if tool.kind not in AXIAL:
        raise CamError(f"Takım '{tool.name}': tornada yalnız matkap / konik takım ({tool.kind.value})")
    R = tool.D / 2
    Lf = float(tool.flute_length)
    phi = getattr(tool, "tip_angle", None)
    Lu = 0.0 if phi is None else R / math.tan(math.radians(phi) / 2)
    if Lu >= Lf:
        raise CamError(f"Takım '{tool.name}': uç konisi boyu kesici boydan kısa olmalı ({Lu} ≥ {Lf})")
    if Lu > 0:
        core = np.array([[0.0, 0.0], [Lu, R], [Lf, R], [Lf, -R], [Lu, -R]])
    else:
        core = np.array([[0.0, R], [Lf, R], [Lf, -R], [0.0, -R]])
    rs = (tool.shank_d if tool.shank_d is not None else tool.D) / 2
    Lt = Lf + REACH if reach is None else max(float(reach), Lf + 1.0)
    body = np.array([[Lf, rs], [Lt, rs], [Lt, -rs], [Lf, -rs]])
    return LatheShape(core, 0.0, body, None, 0.0)


# ---------------------------------------------------------------- dışbükey geometri


def hull(P: np.ndarray) -> np.ndarray:
    """Dışbükey zarf (monoton zincir), saat yönü tersi; tekrar eden noktalar atılır."""
    pts = sorted({(float(p[0]), float(p[1])) for p in P})
    if len(pts) <= 2:
        return np.array(pts, dtype=float).reshape(-1, 2)

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
    return np.array(lower[:-1] + upper[:-1], dtype=float)


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    t = b - a
    L2 = float(t @ t)
    u = 0.0 if L2 == 0 else min(max(float((p - a) @ t) / L2, 0.0), 1.0)
    return float(np.hypot(*(a + u * t - p)))


def _poly_distance(A: np.ndarray, B: np.ndarray) -> float:
    """İki dışbükey çokgen arası uzaklık; iç içe geçiyorsa (pozitif alanlı kesişim) −1."""
    A, B = hull(A), hull(B)
    gap = -math.inf
    for P, Q in ((A, B), (B, A)):
        for i in range(len(P)):
            t = P[(i + 1) % len(P)] - P[i]
            n = np.array([t[1], -t[0]])
            L = float(np.hypot(*n))
            if L == 0:
                continue
            n /= L
            gap = max(gap, float(np.min(Q @ n) - np.max(P @ n)))
    if gap < 1e-12:
        return -1.0
    d = math.inf
    for P, Q in ((A, B), (B, A)):
        for p in P:
            for i in range(len(Q)):
                d = min(d, _seg_dist(p, Q[i], Q[(i + 1) % len(Q)]))
    return d


def rounded_interval(H: np.ndarray, r: float, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Dışbükey çokgen H ⊕ D(r)'nin z doğrularıyla kesişimi (a, b); kesişmeyen (+inf, −inf).

    Sınır: köşe daireleri ve ±r ötelenmiş kenarlar; doğru üzerindeki aday noktaların en küçüğü / en büyüğü.
    """
    z = np.atleast_1d(np.asarray(z, dtype=float))
    a = np.full(z.shape, math.inf)
    b = np.full(z.shape, -math.inf)
    if len(H) == 0 or z.size == 0:
        return a, b
    d = z[None, :] - H[:, 0:1]
    ok = np.abs(d) <= r
    s = np.sqrt(np.clip(r * r - d * d, 0.0, None))
    hx = H[:, 1:2]
    a = np.minimum(a, np.where(ok, hx - s, math.inf).min(axis=0))
    b = np.maximum(b, np.where(ok, hx + s, -math.inf).max(axis=0))
    m = len(H)
    if m < 2:
        return a, b
    for i in range(m):
        p, q = H[i], H[(i + 1) % m]
        t = q - p
        L = math.hypot(t[0], t[1])
        if L == 0:
            continue
        n = np.array([t[1], -t[0]]) / L
        for sg in (1.0, -1.0) if r > 0 else (1.0,):
            A, B = p + sg * r * n, q + sg * r * n
            if A[0] == B[0]:
                hit = z == A[0]
                if hit.any():
                    lo, hi = min(A[1], B[1]), max(A[1], B[1])
                    a = np.where(hit, np.minimum(a, lo), a)
                    b = np.where(hit, np.maximum(b, hi), b)
                continue
            u = (z - A[0]) / (B[0] - A[0])
            hit = (u >= 0.0) & (u <= 1.0)
            x = A[1] + u * (B[1] - A[1])
            a = np.where(hit, np.minimum(a, x), a)
            b = np.where(hit, np.maximum(b, x), b)
    return a, b


def sweep_hull(poly: np.ndarray, p0, p1) -> np.ndarray:
    poly = np.atleast_2d(np.asarray(poly, dtype=float))
    return hull(np.vstack([poly + np.asarray(p0, dtype=float), poly + np.asarray(p1, dtype=float)]))


def sweep_interval(poly: np.ndarray, r: float, p0, p1, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """conv(poly + p0, poly + p1) ⊕ D(r)'nin z doğrularıyla kesişimi (a, b); kesişmeyen a = +inf, b = −inf."""
    return rounded_interval(sweep_hull(poly, p0, p1), float(r), z)


def to_radial(a: np.ndarray, b: np.ndarray, half_width: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """x aralığı [a, b] → r aralığı (eksen geçişi; tutucu kalınlığında üst uç √(x² + b²))."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(invalid="ignore"):
        lo = np.where(a >= 0, a, np.where(b <= 0, -b, 0.0))
        ust = np.where(a >= 0, b, np.where(b <= 0, -a, np.maximum(-a, b)))
    hi = np.hypot(ust, half_width) if half_width else ust
    bos = ~(a <= b)
    return np.where(bos, math.inf, lo), np.where(bos, -math.inf, hi)
