"""SPEC 06 testleri için bağımsız 3D referans hesapları.

Bu modül `cam` paketinden hiçbir şey import etmez: ağ üreticileri, nokta–üçgen uzaklığı, yükseklik
alanı enterpolasyonu, disk altındaki en yüksek nokta ve iz (scallop) sırtı ölçümü burada, uygulamadan
bağımsız olarak hesaplanır.

Kaynaklar:
- Noktanın üçgene en kısa uzaklığı: düzleme dik izdüşüm üçgenin içindeyse düzlem uzaklığı, değilse
  üç kenar doğru parçasına uzaklığın en küçüğü (Ericson, Real-Time Collision Detection, 5.1.5).
- Doğrusal bir fonksiyonun dışbükey bir kümedeki (üçgen ∩ disk) en büyüğü kümenin uç noktalarındadır:
  diskin içindeki üçgen köşeleri, kenar–çember kesişimleri ve çember üzerinde eğim yönündeki nokta.
- Sırt yüksekliği: kesitte iki komşu takım dairesinin, yüzey ekseninden çıkan ışın üzerindeki
  kesişimleri eşitlenir (sayısal kök bulma, scipy.optimize.brentq).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq

# --- Ağ üreticileri -------------------------------------------------------------------------------


def grid_mesh(f, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """z = f(x, y) yükseklik alanı. Her hücre (i, j) iki üçgen: (00, 10, 11) ve (00, 11, 01)."""
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    Z = f(X, Y) if callable(f) else np.asarray(f, dtype=float)
    V = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    ny = len(ys)
    i, j = np.meshgrid(np.arange(len(xs) - 1), np.arange(ny - 1), indexing="ij")
    i, j = i.ravel(), j.ravel()
    v00 = i * ny + j
    v10 = (i + 1) * ny + j
    v11 = (i + 1) * ny + j + 1
    v01 = i * ny + j + 1
    T = np.vstack([np.column_stack([v00, v10, v11]), np.column_stack([v00, v11, v01])])
    return V, T.astype(int)


def grid_height(xs: np.ndarray, ys: np.ndarray, Z: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """grid_mesh ağının (x, y)'deki yüksekliği: hücre üçgeni içinde doğrusal enterpolasyon.
    Eşit aralıklı ızgara varsayılır; ızgara dışı → nan."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    hx = xs[1] - xs[0]
    hy = ys[1] - ys[0]
    fx = (x - xs[0]) / hx
    fy = (y - ys[0]) / hy
    i = np.clip(np.floor(fx).astype(int), 0, len(xs) - 2)
    j = np.clip(np.floor(fy).astype(int), 0, len(ys) - 2)
    u = fx - i
    v = fy - j
    z00 = Z[i, j]
    z10 = Z[i + 1, j]
    z11 = Z[i + 1, j + 1]
    z01 = Z[i, j + 1]
    alt = z00 + u * (z10 - z00) + v * (z11 - z10)  # (00, 10, 11): v ≤ u
    ust = z00 + v * (z01 - z00) + u * (z11 - z01)  # (00, 11, 01): v ≥ u
    z = np.where(v <= u, alt, ust)
    disari = (fx < -1e-12) | (fy < -1e-12) | (fx > len(xs) - 1 + 1e-12) | (fy > len(ys) - 1 + 1e-12)
    return np.where(disari, np.nan, z)


def box_mesh(a: float, b: float, c: float) -> tuple[np.ndarray, np.ndarray]:
    """[0,a] × [0,b] × [0,c] kapalı kutu, 12 üçgen, dışa yönlü."""
    V = np.array(
        [[0, 0, 0], [a, 0, 0], [a, b, 0], [0, b, 0], [0, 0, c], [a, 0, c], [a, b, c], [0, b, c]],
        dtype=float,
    )
    T = np.array(
        [
            [0, 2, 1], [0, 3, 2],  # alt (−z)
            [4, 5, 6], [4, 6, 7],  # üst (+z)
            [0, 1, 5], [0, 5, 4],  # y = 0
            [1, 2, 6], [1, 6, 5],  # x = a
            [2, 3, 7], [2, 7, 6],  # y = b
            [3, 0, 4], [3, 4, 7],  # x = 0
        ]
    )  # fmt: skip
    return V, T


def cylinder_strip_mesh(
    rho: float, z_axis: float, x0: float, x1: float, th_max: float, eps: float, convex: bool
) -> tuple[np.ndarray, np.ndarray, float]:
    """X eksenine paralel, ekseni (y=0, z=z_axis) olan silindirin şeridi; açı θ ∈ [−th_max, th_max]
    düşeyden ölçülür. Dışbükey: üst yarı z = z_axis + ρ cos θ; içbükey (oluk): alt yarı
    z = z_axis − ρ cos θ. Köşeler silindir üstünde; kiriş hatası ρ(1 − cos(Δθ/2)) ≤ eps.
    Döner: V, T, gerçek kiriş hatası."""
    dth_max = 2 * math.acos(1 - eps / rho)
    n = math.ceil(2 * th_max / dth_max)
    th = np.linspace(-th_max, th_max, n + 1)
    sgn = 1.0 if convex else -1.0
    y = rho * np.sin(th)
    z = z_axis + sgn * rho * np.cos(th)
    V = np.vstack(
        [np.column_stack([np.full_like(y, x0), y, z]), np.column_stack([np.full_like(y, x1), y, z])]
    )
    k = np.arange(n)
    a0, a1, b0, b1 = k, k + 1, n + 1 + k, n + 2 + k
    T = np.vstack([np.column_stack([a0, b0, b1]), np.column_stack([a0, b1, a1])])
    hata = rho * (1 - math.cos((th[1] - th[0]) / 2))
    return V, T.astype(int), hata


def sphere_cap_mesh(rho: float, theta_max: float, n_ring: int, n_seg: int) -> tuple[np.ndarray, np.ndarray]:
    """Merkezi orijinde ρ yarıçaplı kürenin üst başlığı (kutuptan θ_max'a), enlem–boylam ağı.
    Kutup bir yelpaze ile kapatılır (sıfır alanlı üçgen yok). Köşeler küre üstünde."""
    V = [[0.0, 0.0, rho]]
    for i in range(1, n_ring + 1):
        th = theta_max * i / n_ring
        for k in range(n_seg):
            ph = 2 * math.pi * k / n_seg
            V.append(
                [rho * math.sin(th) * math.cos(ph), rho * math.sin(th) * math.sin(ph), rho * math.cos(th)]
            )
    T = []
    for k in range(n_seg):
        T.append([0, 1 + k, 1 + (k + 1) % n_seg])
    for i in range(1, n_ring):
        b0 = 1 + (i - 1) * n_seg
        b1 = 1 + i * n_seg
        for k in range(n_seg):
            k1 = (k + 1) % n_seg
            T.append([b0 + k, b1 + k, b1 + k1])
            T.append([b0 + k, b1 + k1, b0 + k1])
    return np.array(V), np.array(T, dtype=int)


# --- Uzaklıklar -----------------------------------------------------------------------------------


def _segment_dist2(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """p noktasının (a_i, b_i) doğru parçalarına uzaklığının karesi, (m,)."""
    ab = b - a
    L2 = np.einsum("ij,ij->i", ab, ab)
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / np.where(L2 > 0, L2, 1.0), 0.0, 1.0)
    q = a + t[:, None] * ab
    d = p - q
    return np.einsum("ij,ij->i", d, d)


def point_mesh_distance(p, V: np.ndarray, T: np.ndarray) -> float:
    """p noktasının üçgen ağına en kısa 3D uzaklığı (tam)."""
    p = np.asarray(p, dtype=float)
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    n = np.cross(B - A, C - A)
    n2 = np.einsum("ij,ij->i", n, n)
    s = np.einsum("ij,ij->i", p - A, n) / n2
    q = p - s[:, None] * n  # düzleme dik izdüşüm
    # ağırlık merkezli koordinatlar (alan oranları, işaretli)
    w0 = np.einsum("ij,ij->i", np.cross(B - q, C - q), n) / n2
    w1 = np.einsum("ij,ij->i", np.cross(C - q, A - q), n) / n2
    w2 = 1.0 - w0 - w1
    ic = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    d_duz = np.where(ic, s * s * n2, np.inf)
    d_ken = np.minimum.reduce([_segment_dist2(p, A, B), _segment_dist2(p, B, C), _segment_dist2(p, C, A)])
    return float(math.sqrt(np.min(np.minimum(d_duz, d_ken))))


def disc_max_height(V: np.ndarray, T: np.ndarray, cx: float, cy: float, r: float) -> float:
    """(cx, cy) merkezli r yarıçaplı yatay diskin altındaki ağın en yüksek noktası (tam).
    Disk hiçbir üçgenle örtüşmüyorsa −inf. Dik üçgenler kenarları ve köşeleriyle sayılır."""
    c = np.array([cx, cy])
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    best = -np.inf
    # 1) diskin içindeki köşeler
    icte = np.hypot(V[:, 0] - cx, V[:, 1] - cy) <= r
    used = np.zeros(len(V), dtype=bool)
    used[np.unique(T)] = True
    if np.any(icte & used):
        best = max(best, float(V[icte & used, 2].max()))
    # 2) kenar–çember kesişimleri
    for P, Q in ((A, B), (B, C), (C, A)):
        d = Q[:, :2] - P[:, :2]
        f = P[:, :2] - c
        a = np.einsum("ij,ij->i", d, d)
        b = 2 * np.einsum("ij,ij->i", f, d)
        cc = np.einsum("ij,ij->i", f, f) - r * r
        disc = b * b - 4 * a * cc
        ok = (a > 0) & (disc >= 0)
        sq = np.sqrt(np.where(ok, disc, 0.0))
        for t in ((-b - sq) / np.where(ok, 2 * a, 1.0), (-b + sq) / np.where(ok, 2 * a, 1.0)):
            g = ok & (t >= 0) & (t <= 1)
            if np.any(g):
                z = P[g, 2] + t[g] * (Q[g, 2] - P[g, 2])
                best = max(best, float(z.max()))
    # 3) yüz: çember üzerinde eğim yönündeki nokta (yatay üçgende merkez)
    n = np.cross(B - A, C - A)
    yuz = np.abs(n[:, 2]) > 1e-12 * np.linalg.norm(n, axis=1)
    if np.any(yuz):
        A_, B_, C_, n_ = A[yuz], B[yuz], C[yuz], n[yuz]
        grad = -n_[:, :2] / n_[:, 2:3]  # z = z_A + grad·(xy − xy_A)
        g = np.linalg.norm(grad, axis=1)
        yon = np.where(g[:, None] > 0, grad / np.where(g > 0, g, 1.0)[:, None], 0.0)
        q = c + r * yon
        z = A_[:, 2] + np.einsum("ij,ij->i", grad, q - A_[:, :2])

        # q üçgenin XY izdüşümünde mi?
        def cross2(u, v):
            return u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]

        s0 = cross2(B_[:, :2] - A_[:, :2], q - A_[:, :2])
        s1 = cross2(C_[:, :2] - B_[:, :2], q - B_[:, :2])
        s2 = cross2(A_[:, :2] - C_[:, :2], q - C_[:, :2])
        tol = 1e-12
        ic = ((s0 >= -tol) & (s1 >= -tol) & (s2 >= -tol)) | ((s0 <= tol) & (s1 <= tol) & (s2 <= tol))
        if np.any(ic):
            best = max(best, float(z[ic].max()))
    return best


def flat_tool_distance(pts: np.ndarray, cl, r: float) -> float:
    """Noktaların düz uçlu takım katısına (r yarıçaplı, tabanı CL'de, yukarı sonsuz silindir) en kısa
    uzaklığı. İçerideki nokta için 0."""
    d = np.hypot(pts[:, 0] - cl[0], pts[:, 1] - cl[1])
    dz = cl[2] - pts[:, 2]  # > 0: nokta tabanın altında
    yatay = np.maximum(d - r, 0.0)
    dikey = np.maximum(dz, 0.0)
    return float(np.min(np.hypot(yatay, dikey)))


def sample_triangles(V: np.ndarray, T: np.ndarray, n: int) -> np.ndarray:
    """Her üçgenden ağırlık merkezli ızgara ile (n+1)(n+2)/2 nokta (köşe ve kenarlar dahil)."""
    i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
    m = (i + j) <= n
    a = (i[m] / n)[:, None]
    b = (j[m] / n)[:, None]
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    P = A[:, None, :] + a[None] * (B - A)[:, None, :] + b[None] * (C - A)[:, None, :]
    return P.reshape(-1, 3)


# --- Kaba kuvvet drop-cutter (yükseklik alanı) ----------------------------------------------------


def brute_drop(height, V: np.ndarray, T: np.ndarray, x: float, y: float, R: float, ball: bool) -> float:
    """Takım alt yüzeyini sık örnekleyerek z_CL alt sınırı: max_p (f(p) − g(p − c)).
    g: küresel uçta R − √(R² − ρ²), düzde 0. Her örnek gerçek bir alt sınırdır; en iyi örneklerin
    çevresi iki kez sıklaştırılır. Ağ köşeleri de aday olarak eklenir."""

    def g(u, v):
        q = np.minimum(u * u + v * v, R * R)
        return R - np.sqrt(R * R - q) if ball else np.zeros_like(u)

    def deger(u, v):
        z = height(x + u, y + v) - g(u, v)
        return np.where(np.isnan(z), -np.inf, z)

    # kaba: kutupsal ızgara (çember dahil)
    rr = R * np.sqrt(np.linspace(0, 1, 160))
    ph = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    RR, PH = np.meshgrid(rr, ph, indexing="ij")
    u = (RR * np.cos(PH)).ravel()
    v = (RR * np.sin(PH)).ravel()
    z = deger(u, v)
    best = float(z.max())
    # ağ köşeleri
    du = V[:, 0] - x
    dv = V[:, 1] - y
    ic = du * du + dv * dv <= R * R
    if np.any(ic):
        best = max(best, float(np.max(V[ic, 2] - g(du[ic], dv[ic]))))
    # sıklaştırma: en iyi 8 örneğin çevresi
    h = 2 * R / 160 + R * 2 * np.pi / 720
    for k in np.argsort(z)[-8:]:
        u0, v0 = u[k], v[k]
        for w in (h, h / 20):
            gu, gv = np.meshgrid(np.linspace(-w, w, 81), np.linspace(-w, w, 81), indexing="ij")
            uu = (u0 + gu).ravel()
            vv = (v0 + gv).ravel()
            disk = uu * uu + vv * vv <= R * R
            uu, vv = uu[disk], vv[disk]
            if len(uu) == 0:
                break
            zz = deger(uu, vv)
            i = int(np.argmax(zz))
            best = max(best, float(zz[i]))
            u0, v0 = uu[i], vv[i]
    return best


# --- İz (scallop) sırtı ---------------------------------------------------------------------------


def ray_circle(theta: float, C: np.ndarray, R: float, down: bool, far: bool) -> float:
    """Eksenden θ açısıyla çıkan ışının (düşeyden ölçülür; down=True ise aşağı bakan) C merkezli R
    yarıçaplı daireyle kesişimi: far=False yakın, True uzak nokta. Kesişim yoksa nan."""
    e = np.array([math.sin(theta), -math.cos(theta) if down else math.cos(theta)])
    b = float(e @ C)
    q = R * R - (float(C @ C) - b * b)
    if q < 0:
        return math.nan
    return b + math.sqrt(q) if far else b - math.sqrt(q)


def ridge_heights(centers: np.ndarray, R: float, rho: float, convex: bool) -> list[tuple[float, float]]:
    """Kesitte (eksene göre) takım daire merkezleri `centers` (k, 2) için komşu her çiftin
    (α, sırt yüksekliği). Dışbükeyde işlenmiş yüzey ışın üstündeki en yakın 'yakın' kesişim,
    sırt = r − ρ; içbükeyde en uzak 'uzak' kesişim, sırt = ρ − r. Sırt açısı iki komşu dairenin
    kesişimlerini eşitleyen kökle bulunur; o açıda diğer daireler de denetlenir."""
    down = not convex
    far = not convex
    phi = np.array([math.atan2(c[0], c[1] if convex else -c[1]) for c in centers])
    order = np.argsort(phi)
    C = centers[order]
    phi = phi[order]
    out = []
    for i in range(len(C) - 1):

        def fark(th, i=i):
            return ray_circle(th, C[i], R, down, far) - ray_circle(th, C[i + 1], R, down, far)

        th = brentq(fark, phi[i], phi[i + 1], xtol=1e-15, rtol=1e-15, maxiter=500)
        ts = [ray_circle(th, c, R, down, far) for c in C]
        ts = [t for t in ts if not math.isnan(t)]
        if convex:
            h = min(ts) - rho
        else:
            h = rho - max(ts)
        out.append((float(phi[i + 1] - phi[i]), float(h)))
    return out


def envelope_ridge_bruteforce(R: float, rho: float, alpha: float, convex: bool) -> float:
    """İdeal iki takım dairesi (merkezler ρ ± R yarıçaplı çemberde, aralarında α açı) için sırt
    yüksekliği: açı boyunca sık örnekleme + iki kez sıklaştırma (kapalı form kullanılmaz)."""
    c = rho + R if convex else rho - R
    C = np.array(
        [
            [c * math.sin(-alpha / 2), c * math.cos(alpha / 2)],
            [c * math.sin(alpha / 2), c * math.cos(alpha / 2)],
        ]
    )

    def h(th: np.ndarray) -> np.ndarray:
        e = np.stack([np.sin(th), np.cos(th)], axis=1)
        ts = []
        for Ci in C:
            b = e @ Ci
            q = R * R - (Ci @ Ci - b * b)
            sq = np.sqrt(np.where(q >= 0, q, np.nan))
            ts.append(b + sq if not convex else b - sq)
        ts = np.array(ts)
        if convex:
            return np.nanmin(ts, axis=0) - rho
        return rho - np.nanmax(ts, axis=0)

    lo, hi = -alpha / 2, alpha / 2
    for _ in range(3):
        th = np.linspace(lo, hi, 20001)
        v = h(th)
        k = int(np.nanargmax(v))
        best = float(v[k])
        step = th[1] - th[0]
        lo, hi = th[k] - 2 * step, th[k] + 2 * step
    return best
