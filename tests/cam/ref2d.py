"""SPEC 03 testleri için bağımsız 2D referans geometri (cam.geom2d'ye güvenmeden).

Bu modül test değildir (adı test_ ile başlamaz); SPEC 03 testlerinin beklenen değerlerini
uygulamadan bağımsız hesaplamak için kullanılır. Sadece numpy ve cam/model.py (sabit arayüz).

Kullanılan formüller:
- Nokta–doğru parçası uzaklığı: dik izdüşüm parametresi t = clamp(((p−a)·(b−a)) / |b−a|², 0, 1),
  uzaklık |p − (a + t(b−a))|.
- Nokta–yay uzaklığı: p'nin merkeze göre açısı yayın süpürme aralığındaysa | |p−c| − R |,
  değilse uç noktalardan yakın olanına uzaklık (daire üzerinde en yakın nokta radyal izdüşümdür).
- Noktanın çokgen içinde olması: çift-tek (ray casting) kuralı, +x yönünde ışın.
- Yönlü alan: shoelace, ½ Σ (x_i y_{i+1} − x_{i+1} y_i) (O'Rourke, Bölüm 1).
- Yay süpürmesi cam/model.py kuralıyla aynı: G2 saat yönü, G3 saat yönü tersi, başlangıç = bitiş ise 2π.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.model import MoveType, Toolpath

TWO_PI = 2.0 * math.pi
KESME = {MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW}


# ------------------------------------------------------------------ temel uzaklıklar


def dist_points_lines(P: np.ndarray, A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """(N,2) noktaların (M,2)-(M,2) doğru parçalarına uzaklıkları, (N, M)."""
    P = np.asarray(P, dtype=float).reshape(-1, 2)
    A = np.asarray(A, dtype=float).reshape(-1, 2)
    B = np.asarray(B, dtype=float).reshape(-1, 2)
    if len(A) == 0:
        return np.full((len(P), 0), np.inf)
    AB = B - A                                       # (M,2)
    L2 = np.einsum("ij,ij->i", AB, AB)               # (M,)
    AP = P[:, None, :] - A[None, :, :]               # (N,M,2)
    t = np.einsum("nmk,mk->nm", AP, AB) / np.where(L2 > 0, L2, 1.0)
    t = np.clip(t, 0.0, 1.0)
    Q = A[None, :, :] + t[:, :, None] * AB[None, :, :]
    return np.linalg.norm(P[:, None, :] - Q, axis=2)


def dist_points_arcs(
    P: np.ndarray, C: np.ndarray, R: np.ndarray, th0: np.ndarray, sw: np.ndarray
) -> np.ndarray:
    """(N,2) noktaların yaylara uzaklıkları, (N, K).

    Yay k: merkez C[k], yarıçap R[k], saat yönü tersinde th0[k]'dan sw[k] kadar süpürür.
    """
    P = np.asarray(P, dtype=float).reshape(-1, 2)
    C = np.asarray(C, dtype=float).reshape(-1, 2)
    if len(C) == 0:
        return np.full((len(P), 0), np.inf)
    R = np.asarray(R, dtype=float)
    th0 = np.asarray(th0, dtype=float)
    sw = np.asarray(sw, dtype=float)
    V = P[:, None, :] - C[None, :, :]                # (N,K,2)
    rho = np.linalg.norm(V, axis=2)
    phi = np.arctan2(V[..., 1], V[..., 0])
    rel = np.mod(phi - th0[None, :], TWO_PI)
    inside = (rel <= sw[None, :] + 1e-15) | (sw[None, :] >= TWO_PI - 1e-12)
    d_radial = np.abs(rho - R[None, :])
    E0 = C + R[:, None] * np.stack([np.cos(th0), np.sin(th0)], axis=1)
    E1 = C + R[:, None] * np.stack([np.cos(th0 + sw), np.sin(th0 + sw)], axis=1)
    d0 = np.linalg.norm(P[:, None, :] - E0[None], axis=2)
    d1 = np.linalg.norm(P[:, None, :] - E1[None], axis=2)
    return np.where(inside, d_radial, np.minimum(d0, d1))


def arc_ccw_form(p0, p1, c, cw: bool) -> tuple[float, float, float]:
    """Yayı (R, θ_başlangıç, süpürme) saat yönü tersi biçimine çevirir (cam/model.py kuralı)."""
    p0 = np.asarray(p0, dtype=float)[:2]
    p1 = np.asarray(p1, dtype=float)[:2]
    c = np.asarray(c, dtype=float)[:2]
    R = float(np.hypot(*(p0 - c)))
    t0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    t1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    if cw:
        sw = (t0 - t1) % TWO_PI
        start = t1
    else:
        sw = (t1 - t0) % TWO_PI
        start = t0
    if sw < 1e-12:
        sw = TWO_PI
    return R, start, sw


# ------------------------------------------------------------------ eğri kümesi


@dataclass
class Egriler:
    """Doğru ve yaylardan oluşan küme; noktadan kümeye en kısa uzaklık için."""

    A: list = field(default_factory=list)      # doğru başlangıçları
    B: list = field(default_factory=list)      # doğru bitişleri
    C: list = field(default_factory=list)      # yay merkezleri
    R: list = field(default_factory=list)
    th0: list = field(default_factory=list)
    sw: list = field(default_factory=list)

    def line(self, a, b) -> None:
        self.A.append(tuple(a)[:2])
        self.B.append(tuple(b)[:2])

    def arc(self, c, R: float, th0: float, sw: float) -> None:
        self.C.append(tuple(c)[:2])
        self.R.append(R)
        self.th0.append(th0)
        self.sw.append(sw)

    def circle(self, c, R: float) -> None:
        self.arc(c, R, 0.0, TWO_PI)

    def polygon(self, pts) -> None:
        pts = [tuple(p) for p in pts]
        for i in range(len(pts)):
            self.line(pts[i], pts[(i + 1) % len(pts)])

    def distance(self, P: np.ndarray) -> np.ndarray:
        """(N,2) noktaların kümeye en kısa uzaklığı, (N,)."""
        P = np.asarray(P, dtype=float).reshape(-1, 2)
        parts = []
        if self.A:
            parts.append(dist_points_lines(P, np.array(self.A), np.array(self.B)))
        if self.C:
            parts.append(
                dist_points_arcs(P, np.array(self.C), np.array(self.R), np.array(self.th0), np.array(self.sw))
            )
        if not parts:
            return np.full(len(P), np.inf)
        return np.min(np.hstack(parts), axis=1)


def polygon_contains(P: np.ndarray, pts) -> np.ndarray:
    """Çift-tek kuralı ile noktalar çokgenin içinde mi, (N,) bool."""
    P = np.asarray(P, dtype=float).reshape(-1, 2)
    V = np.asarray(pts, dtype=float)
    W = np.roll(V, -1, axis=0)
    x, y = P[:, 0:1], P[:, 1:2]
    y0, y1 = V[None, :, 1], W[None, :, 1]
    x0, x1 = V[None, :, 0], W[None, :, 0]
    crosses = (y0 > y) != (y1 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
    hit = crosses & (xi > x)
    return (np.count_nonzero(hit, axis=1) % 2) == 1


def shoelace(pts: np.ndarray) -> float:
    """Kapalı nokta dizisinin yönlü alanı (son nokta ilkine bağlanır)."""
    pts = np.asarray(pts, dtype=float)
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


@dataclass
class RefBolge:
    """Testin kendi tanımladığı bölge: dış çokgen veya daire, delikler (çokgen veya daire).

    halka tanımı: ("poly", [(x, y), ...]) veya ("circle", (cx, cy), R)
    """

    outer: tuple
    holes: list = field(default_factory=list)

    def boundary(self) -> Egriler:
        e = Egriler()
        for h in [self.outer, *self.holes]:
            if h[0] == "poly":
                e.polygon(h[1])
            else:
                e.circle(h[1], h[2])
        return e

    @staticmethod
    def _inside_ring(P: np.ndarray, h) -> np.ndarray:
        if h[0] == "poly":
            return polygon_contains(P, h[1])
        c = np.asarray(h[1], dtype=float)
        return np.linalg.norm(P - c, axis=1) < h[2]

    def contains(self, P: np.ndarray) -> np.ndarray:
        P = np.asarray(P, dtype=float).reshape(-1, 2)
        ok = self._inside_ring(P, self.outer)
        for h in self.holes:
            ok &= ~self._inside_ring(P, h)
        return ok


# ------------------------------------------------------------------ takım yolu ayrıştırma


@dataclass
class Parca:
    """Takım yolunun bir hareketi: tip, başlangıç ve bitiş (3D), ilerleme, yay merkezi."""

    type: MoveType
    p0: np.ndarray
    p1: np.ndarray
    feed: float | None
    center: np.ndarray | None

    @property
    def horizontal(self) -> bool:
        return abs(self.p0[2] - self.p1[2]) < 1e-12

    @property
    def is_plunge(self) -> bool:
        """Düşey G1 dalma: XY sabit, Z azalıyor."""
        return (
            self.type is MoveType.LINEAR
            and float(np.hypot(*(self.p1[:2] - self.p0[:2]))) < 1e-12
            and self.p1[2] < self.p0[2]
        )

    def arc_form(self) -> tuple[float, float, float]:
        return arc_ccw_form(self.p0, self.p1, self.center, self.type is MoveType.ARC_CW)

    def length_xy(self) -> float:
        if self.type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            R, _, sw = self.arc_form()
            return R * sw
        return float(np.hypot(*(self.p1[:2] - self.p0[:2])))

    def sample(self, step: float = 0.25) -> np.ndarray:
        """Hareket üzerinde örnek noktalar (3D), uçlar dahil; ilerleme yönünde sıralı."""
        n = max(2, int(math.ceil(max(self.length_xy(), abs(self.p1[2] - self.p0[2])) / step)) + 1)
        t = np.linspace(0.0, 1.0, n)
        z = self.p0[2] + t * (self.p1[2] - self.p0[2])
        if self.type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            c = self.center
            R, _, sw = self.arc_form()
            t0 = math.atan2(self.p0[1] - c[1], self.p0[0] - c[0])
            sgn = -1.0 if self.type is MoveType.ARC_CW else 1.0
            th = t0 + sgn * sw * t
            return np.column_stack([c[0] + R * np.cos(th), c[1] + R * np.sin(th), z])
        xy = self.p0[None, :2] + t[:, None] * (self.p1[:2] - self.p0[:2])[None, :]
        return np.column_stack([xy, z])


def moves_of(tp: Toolpath) -> list[Parca]:
    """Takım yolunu (başlangıç, bitiş) çiftlerine ayırır."""
    out = []
    p0 = np.array(tp.start, dtype=float)
    for m in tp.moves:
        p1 = np.array(m.end, dtype=float)
        c = None if m.center is None else np.array(m.center, dtype=float)
        out.append(Parca(m.type, p0, p1, m.feed, c))
        p0 = p1
    return out


def cutting_moves(tp: Toolpath, z: float | None = None, tol: float = 1e-9) -> list[Parca]:
    """Yatay kesme hareketleri (G1/G2/G3, Z sabit). z verilirse sadece o derinliktekiler."""
    res = [p for p in moves_of(tp) if p.type in KESME and p.horizontal]
    if z is not None:
        res = [p for p in res if abs(p.p0[2] - z) < tol]
    return res


def cut_depths(tp: Toolpath) -> list[float]:
    """Yatay kesme hareketlerinin farklı Z değerleri, yukarıdan aşağıya."""
    zs: list[float] = []
    for p in cutting_moves(tp):
        if not any(abs(p.p0[2] - z) < 1e-9 for z in zs):
            zs.append(float(p.p0[2]))
    return sorted(zs, reverse=True)


def curves_of(parts: list[Parca]) -> Egriler:
    """Hareketlerin XY izdüşümünü uzaklık kümesine çevirir (yaylar analitik)."""
    e = Egriler()
    for p in parts:
        if p.type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            R, th0, sw = p.arc_form()
            e.arc(p.center, R, th0, sw)
        elif float(np.hypot(*(p.p1[:2] - p.p0[:2]))) > 0:
            e.line(p.p0[:2], p.p1[:2])
    return e


def sample_xy(parts: list[Parca], step: float = 0.25) -> np.ndarray:
    """Hareketlerin üzerindeki örnek noktalar (XY), (N, 2)."""
    if not parts:
        return np.zeros((0, 2))
    return np.vstack([p.sample(step)[:, :2] for p in parts])


def grid(x0: float, x1: float, y0: float, y1: float, nx: int = 40, ny: int = 40) -> np.ndarray:
    """Kapalı dikdörtgen üzerinde nx × ny düzgün örnek ızgara, (nx·ny, 2)."""
    X, Y = np.meshgrid(np.linspace(x0, x1, nx), np.linspace(y0, y1, ny))
    return np.column_stack([X.ravel(), Y.ravel()])
