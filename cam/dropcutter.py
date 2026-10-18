"""
SPEC 06 / 06b — Drop-cutter: takımı Z boyunca üçgen ağına değene kadar indirme.

CL = takım ucu (en alt nokta, eksen üzerinde). Verilen (x, y) için takımın XY izdüşüm diskiyle
örtüşen her üçgende üç test yapılır (köşe, yüz, kenar); temas yüksekliği hepsinin en büyüğüdür
(Yau vd. 2004; OpenCAMLib BatchDropCutter yapısı).

Takım dışbükey profil f(ρ) ile verilir (cam.cutter.Cutter). Küresel ve düz uçta SPEC 06 kapalı
formları; diğer profillerde (torik, konik, ofsetler) genel test: köşe z = P_z − f(d), yüz
z = z_düzlem(c) + f*(m) (Legendre), kenar g(t) = P_z(t) − f(d(t)) içbükey → altın oran araması.

Hesap noktalar × aday üçgen çiftleri üzerinde vektörlenir. Aday üçgenler, üçgen ağırlık
merkezlerinin XY kd-ağacıyla süzülür (scipy.spatial.cKDTree).

Birimler: mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from cam.cutter import Cutter
from cam.model import CamError, Tool

TOL = 1e-9  # mm
NZ_TOL = 1e-12  # bundan küçük |n_z| dik üçgen sayılır
_CIFT = 2_000_000  # tek seferde değerlendirilen en çok (nokta, üçgen) çifti


@dataclass
class TriMesh:
    """Üçgen ağı: köşeler V (n, 3) [mm], üçgenler T (m, 3) indeks."""

    V: np.ndarray
    T: np.ndarray
    _P: np.ndarray = field(init=False, repr=False)  # (m, 3, 3) üçgen köşeleri
    _n: np.ndarray = field(init=False, repr=False)  # (m, 3) birim normal, n_z ≥ 0
    _agac: cKDTree = field(init=False, repr=False)
    _r_max: float = field(init=False, repr=False)  # ağırlık merkezinden köşeye en büyük XY uzaklık
    _G: np.ndarray = field(init=False, repr=False)  # (m, 2) XY ağırlık merkezleri
    _r: np.ndarray = field(init=False, repr=False)  # (m,) ağırlık merkezinden köşeye XY uzaklık

    def __post_init__(self) -> None:
        V = np.asarray(self.V, dtype=float)
        T = np.asarray(self.T)
        if V.ndim != 2 or V.shape[1] != 3 or len(V) == 0:
            raise CamError(f"TriMesh: V (n, 3) ve boş olmayan olmalı (şekil {V.shape})")
        if T.ndim != 2 or T.shape[1] != 3 or len(T) == 0:
            raise CamError(f"TriMesh: T (m, 3) ve boş olmayan olmalı (şekil {T.shape})")
        if not np.all(np.isfinite(V)):
            raise CamError("TriMesh: V sonlu olmalı")
        if not np.issubdtype(T.dtype, np.integer):
            if not np.all(T == np.round(T)):
                raise CamError("TriMesh: T tam sayı indeks olmalı")
            T = T.astype(int)
        if T.min() < 0 or T.max() >= len(V):
            raise CamError(f"TriMesh: T indeksi 0..{len(V) - 1} dışında")
        P = V[T]
        N = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        alan2 = np.linalg.norm(N, axis=1)  # 2·alan
        if np.any(0.5 * alan2 < TOL * TOL):
            raise CamError(f"TriMesh: sıfır alanlı üçgen (indeks {int(np.argmin(alan2))})")
        n = N / alan2[:, None]
        n[n[:, 2] < 0] *= -1  # drop-cutter yukarı bakan normal kullanır
        G = P[:, :, :2].mean(axis=1)
        self.V, self.T = V, T
        self._P, self._n = P, n
        self._agac = cKDTree(G)
        self._G = G
        self._r = np.linalg.norm(P[:, :, :2] - G[:, None, :], axis=2).max(axis=1)
        self._r_max = float(np.max(self._r))

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.V.min(axis=0), self.V.max(axis=0)

    @classmethod
    def from_part(cls, part, tol: float = 0.01) -> TriMesh:
        """geometry.part.Part.mesh(tol) ile ağ (kiriş sapması tol [mm])."""
        V, T = part.mesh(tol)
        return cls(V=V, T=T)


def kesici(tool: Tool | Cutter) -> Cutter:
    """Takımın profili; desteklenmeyen takım (matkap) → CamError."""
    return tool if isinstance(tool, Cutter) else Cutter.from_tool(tool)


def _ic(P: np.ndarray, q: np.ndarray) -> np.ndarray:
    """q (k, 2) noktası P (k, 3, 3) üçgeninin XY izdüşümünde mi (ağırlık merkezli koordinatlar ≥ −TOL)."""
    a, b, c = P[:, 0, :2], P[:, 1, :2], P[:, 2, :2]
    v0, v1, v2 = b - a, c - a, q - a
    d00 = np.einsum("ij,ij->i", v0, v0)
    d01 = np.einsum("ij,ij->i", v0, v1)
    d11 = np.einsum("ij,ij->i", v1, v1)
    d20 = np.einsum("ij,ij->i", v2, v0)
    d21 = np.einsum("ij,ij->i", v2, v1)
    den = d00 * d11 - d01 * d01
    with np.errstate(divide="ignore", invalid="ignore"):
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
    u = 1 - v - w
    return (den > 0) & (u >= -TOL) & (v >= -TOL) & (w >= -TOL)


def _duzlem_z(P0: np.ndarray, n: np.ndarray, q: np.ndarray) -> np.ndarray:
    """n·(p − P₀) = 0 düzleminin q (k, 2) noktasındaki z'si (n_z > 0)."""
    return P0[:, 2] - (n[:, 0] * (q[:, 0] - P0[:, 0]) + n[:, 1] * (q[:, 1] - P0[:, 1])) / n[:, 2]


def _kure(P: np.ndarray, n: np.ndarray, c: np.ndarray, R: float) -> np.ndarray:
    """Küresel uç, her (nokta, üçgen) çifti için temas z'si (temas yoksa −inf). c: (k, 2) CL XY."""
    k = len(c)
    z = np.full(k, -np.inf)
    # Köşe: z = P_z + √(R² − d²) − R
    for j in range(3):
        d2 = np.sum((P[:, j, :2] - c) ** 2, axis=1)
        ok = d2 <= R * R
        z[ok] = np.maximum(z[ok], P[ok, j, 2] + np.sqrt(R * R - d2[ok]) - R)
    # Yüz: CC_xy = c − R·n_xy; z = z_düzlem(CC) + R·n_z − R
    yuz = n[:, 2] >= NZ_TOL
    if np.any(yuz):
        Py, ny, cy = P[yuz], n[yuz], c[yuz]
        cc = cy - R * ny[:, :2]
        ok = _ic(Py, cc)
        zy = np.where(ok, _duzlem_z(Py[:, 0], ny, cc) + R * ny[:, 2] - R, -np.inf)
        z[yuz] = np.maximum(z[yuz], zy)
    # Kenar: |w|² − (w·u)² = R², w = C − P₀ → h = z_C − z₀ için ikinci derece, büyük kök
    for i, j in ((0, 1), (1, 2), (2, 0)):
        e = P[:, j] - P[:, i]
        L = np.linalg.norm(e, axis=1)
        u = e / L[:, None]
        a = c[:, 0] - P[:, i, 0]
        b = c[:, 1] - P[:, i, 1]
        s = a * u[:, 0] + b * u[:, 1]
        A = 1 - u[:, 2] ** 2
        B = -2 * u[:, 2] * s
        C = a * a + b * b - s * s - R * R
        disk = B * B - 4 * A * C
        ok = (A > NZ_TOL) & (disk >= 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            h = (-B + np.sqrt(np.where(ok, disk, 0))) / (2 * A)
        t = s + h * u[:, 2]
        ok &= (t >= 0) & (t <= L)
        z[ok] = np.maximum(z[ok], P[ok, i, 2] + h[ok] - R)
    return z


def _duz(P: np.ndarray, n: np.ndarray, c: np.ndarray, r: float) -> np.ndarray:
    """Düz uç, her (nokta, üçgen) çifti için temas z'si (temas yoksa −inf). c: (k, 2) CL XY."""
    k = len(c)
    z = np.full(k, -np.inf)
    # Köşe: d ≤ r ise z = P_z
    for j in range(3):
        ok = np.sum((P[:, j, :2] - c) ** 2, axis=1) <= r * r
        z[ok] = np.maximum(z[ok], P[ok, j, 2])
    # Yüz: disk yokuş yukarı kenarından değer, CC_xy = c − r·n_xy/|n_xy| (yatayda c)
    yuz = n[:, 2] >= NZ_TOL
    if np.any(yuz):
        Py, ny, cy = P[yuz], n[yuz], c[yuz]
        m = np.hypot(ny[:, 0], ny[:, 1])
        egik = m > 0
        yon = np.zeros_like(cy)
        yon[egik] = ny[egik, :2] / m[egik, None]
        cc = cy - r * yon
        ok = _ic(Py, cc)
        zy = np.where(ok, _duzlem_z(Py[:, 0], ny, cc), -np.inf)
        z[yuz] = np.maximum(z[yuz], zy)
    # Kenar: XY izdüşümünün daire içindeki [t₀, t₁] aralığı; z doğrusal → uçlardan büyüğü
    for i, j in ((0, 1), (1, 2), (2, 0)):
        e = P[:, j] - P[:, i]
        f = P[:, i, :2] - c
        a = e[:, 0] ** 2 + e[:, 1] ** 2
        b = 2 * (e[:, 0] * f[:, 0] + e[:, 1] * f[:, 1])
        cc = f[:, 0] ** 2 + f[:, 1] ** 2 - r * r
        disk = b * b - 4 * a * cc
        ok = (a > TOL * TOL) & (disk >= 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            kok = np.sqrt(np.where(ok, disk, 0))
            t0 = np.maximum((-b - kok) / (2 * a), 0.0)
            t1 = np.minimum((-b + kok) / (2 * a), 1.0)
        ok &= t0 <= t1
        zk = np.maximum(P[:, i, 2] + t0 * e[:, 2], P[:, i, 2] + t1 * e[:, 2])
        z[ok] = np.maximum(z[ok], zk[ok])
    return z


_ALTIN = (math.sqrt(5) - 1) / 2
_ALTIN_ADIM = 64  # aralık 0.618⁶⁴ ≈ 4e-14 katına iner


def altin(g, a: np.ndarray, b: np.ndarray, adim: int = _ALTIN_ADIM) -> tuple[np.ndarray, np.ndarray]:
    """[a, b] üzerinde içbükey g'nin en büyüğü ve yeri (vektörlü altın oran araması; uçlar dahil)."""
    x1 = b - _ALTIN * (b - a)
    x2 = a + _ALTIN * (b - a)
    g1, g2 = g(x1), g(x2)
    for _ in range(adim):
        sag = g1 < g2  # en büyük [x1, b]'de
        a = np.where(sag, x1, a)
        b = np.where(sag, b, x2)
        xn = np.where(sag, a + _ALTIN * (b - a), b - _ALTIN * (b - a))
        gn = g(xn)
        x1, x2, g1, g2 = (
            np.where(sag, x2, xn),
            np.where(sag, xn, x1),
            np.where(sag, g2, gn),
            np.where(sag, gn, g1),
        )
    X = np.stack([x1, x2, a, b])
    G = np.stack([g1, g2, g(a), g(b)])
    k = np.argmax(G, axis=0)
    sec = np.arange(G.shape[1])
    return G[k, sec], X[k, sec]


def altin_max(g, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """[a, b] üzerinde içbükey g'nin en büyük değeri."""
    return altin(g, a, b)[0]


def _genel(P: np.ndarray, n: np.ndarray, c: np.ndarray, K: Cutter, esik: float = np.inf) -> np.ndarray:
    """Genel dışbükey profil, her (nokta, üçgen) çifti için temas z'si (temas yoksa −inf).

    esik: köşe / yüz testi bunu zaten aşan çiftlerde kenar araması atlanır (yalnız "z_tri > esik"
    sorusu için; sonuç o çiftlerde en büyük değer değil, esik'ten büyük bir değerdir).
    """
    R = K.R
    k = len(c)
    z = np.full(k, -np.inf)
    tek_dogru = len(K.parcalar) == 1 and K.parcalar[0][0] == "dogru" and K.parcalar[0][4] > 0
    # Köşe: d ≤ R ise z = P_z − f(d)
    for j in range(3):
        d = np.hypot(P[:, j, 0] - c[:, 0], P[:, j, 1] - c[:, 1])
        ok = d <= R
        z[ok] = np.maximum(z[ok], P[ok, j, 2] - K.f_ic(d[ok]))
    # Yüz: m = |n_xy|/n_z, u = −n_xy/|n_xy| (yokuş yukarı); CC_xy = c + ρ*·u, z = z_düzlem(c) + f*(m)
    yuz = n[:, 2] >= NZ_TOL
    if np.any(yuz):
        Py, ny, cy = P[yuz], n[yuz], c[yuz]
        nxy = np.hypot(ny[:, 0], ny[:, 1])
        egik = nxy > 0
        u = np.zeros_like(cy)
        u[egik] = -ny[egik, :2] / nxy[egik, None]
        fs, rs = K.support(nxy / ny[:, 2])
        cc = cy + rs[:, None] * u
        ok = _ic(Py, cc)
        zy = np.where(ok, _duzlem_z(Py[:, 0], ny, cy) + fs, -np.inf)
        z[yuz] = np.maximum(z[yuz], zy)
    # Kenar: XY izdüşümünün R diskindeki [t₀, t₁] aralığında g(t) = P_z(t) − f(d(t)) içbükey
    for i, j in ((0, 1), (1, 2), (2, 0)):
        e = P[:, j] - P[:, i]
        f0 = P[:, i, :2] - c
        a = e[:, 0] ** 2 + e[:, 1] ** 2
        b = 2 * (e[:, 0] * f0[:, 0] + e[:, 1] * f0[:, 1])
        cc = f0[:, 0] ** 2 + f0[:, 1] ** 2 - R * R
        disk = b * b - 4 * a * cc
        ok = (a > TOL * TOL) & (disk >= 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            kok = np.sqrt(np.where(ok, disk, 0))
            t0 = np.maximum((-b - kok) / (2 * a), 0.0)
            t1 = np.minimum((-b + kok) / (2 * a), 1.0)
        ok &= (t0 <= t1) & (z <= esik)
        # Üst sınır: g(t) ≤ max(P_z) − f(d_min); mevcut değeri veya eşiği aşamayan kenar aranmaz
        with np.errstate(divide="ignore", invalid="ignore"):
            t_en = np.clip(np.where(a > 0, -b / (2 * a), 0.0), 0.0, 1.0)
        d_en = np.hypot(f0[:, 0] + t_en * e[:, 0], f0[:, 1] + t_en * e[:, 1])
        ust = np.maximum(P[:, i, 2], P[:, j, 2]) - K.f_ic(np.minimum(d_en, R))
        ok &= (ust > z) & (ust > esik if np.isfinite(esik) else True)
        if not np.any(ok):
            continue
        e_, f_, Pz = e[ok], f0[ok], P[ok, i, 2]

        def g(t, e_=e_, f_=f_, Pz=Pz):
            d = np.hypot(f_[:, 0] + t * e_[:, 0], f_[:, 1] + t * e_[:, 1])
            return Pz + t * e_[:, 2] - K.f_ic(np.minimum(d, R))

        if tek_dogru:
            zk = _kenar_dogru(g, e_, f_, K.parcalar[0][4], t0[ok], t1[ok])
        else:
            zk = altin_max(g, t0[ok], t1[ok])
        z[ok] = np.maximum(z[ok], zk)
    return z


def _kenar_dogru(g, e: np.ndarray, f0: np.ndarray, k: float, t0: np.ndarray, t1: np.ndarray) -> np.ndarray:
    """Tek doğru profil (f = k·ρ, koni) için kenar testi kapalı formda: g(t) = P_z + t·e_z − k·d(t).

    d(t)² = A·s² + D (s = t − t_en, D: doğruya dik uzaklığın karesi). g'(t) = 0 →
    A·s / √(A·s² + D) = q = e_z / k; q² < A ise s* = q·√D / √(A(A − q²)), yoksa g tekdüze (uçlar).
    İçbükey g'nin en büyüğü {t₀, t₁, kırpılmış t*} içindedir."""
    A = e[:, 0] ** 2 + e[:, 1] ** 2
    B = 2 * (e[:, 0] * f0[:, 0] + e[:, 1] * f0[:, 1])
    C = f0[:, 0] ** 2 + f0[:, 1] ** 2
    t_en = -B / (2 * A)
    D = np.maximum(C - A * t_en**2, 0.0)
    q = e[:, 2] / k
    ic = q * q < A
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(ic, q * np.sqrt(D) / np.sqrt(A * (A - q * q)), 0.0)
    t_y = np.clip(np.where(ic, t_en + s, t0), t0, t1)
    return np.maximum.reduce([g(t0), g(t1), g(t_y)])


def tri_z(P: np.ndarray, n: np.ndarray, c: np.ndarray, K: Cutter, esik: float = np.inf) -> np.ndarray:
    """Her (nokta, üçgen) çifti için z_tri(c) (temas yoksa −inf); profile göre doğru test.

    esik verilirse yalnız "z_tri > esik" doğru yanıtlanır (genel profilde kenar araması kısalır).
    """
    if K.tur == "kure":
        return _kure(P, n, c, K.R)
    if K.tur == "duz":
        return _duz(P, n, c, K.R)
    return _genel(P, n, c, K, esik)


def _ciftler(mesh: TriMesh, rad: float, xy: np.ndarray):
    """Nokta parçaları için (nokta indeksi, aday üçgen) çiftleri; parça başına en çok _CIFT çift."""
    adaylar = mesh._agac.query_ball_point(xy, rad + mesh._r_max + TOL)
    sayi = np.array([len(a) for a in adaylar])
    bas = 0
    while bas < len(xy):
        son = bas + max(1, int(np.searchsorted(np.cumsum(sayi[bas:]), _CIFT, side="right")))
        idx = np.repeat(np.arange(bas, son), sayi[bas:son])
        if len(idx):
            tri = np.concatenate([np.asarray(a, dtype=int) for a in adaylar[bas:son]])
            yield idx, tri
        bas = son


def girisim(mesh: TriMesh, tool: Tool | Cutter, xy: np.ndarray, z: float) -> np.ndarray:
    """z_CL(x, y) > z mi (takım ucu z'deyken ağa giriyor mu); üçgen yoksa False."""
    K = kesici(tool)
    xy = np.atleast_2d(np.asarray(xy, dtype=float))
    zc = np.full(len(xy), -np.inf)
    for idx, tri in _ciftler(mesh, K.R, xy):
        # z_tri ≤ max P_z − f(d_min); d_min ≥ |c − G| − r (r: üçgenin ağırlık merkezinden köşe uzaklığı)
        d_min = np.maximum(np.hypot(*(xy[idx] - mesh._G[tri]).T) - mesh._r[tri], 0.0)
        ust = mesh._P[tri, :, 2].max(axis=1) - K.f_ic(np.minimum(d_min, K.R)) > z
        idx, tri = idx[ust], tri[ust]
        np.maximum.at(zc, idx, tri_z(mesh._P[tri], mesh._n[tri], xy[idx], K, esik=z))
    return zc > z


def drop(mesh: TriMesh, tool: Tool | Cutter, xy: np.ndarray, floor: float | None = None) -> np.ndarray:
    """Her (x, y) için z_CL = max(köşe, yüz, kenar testleri) [mm].

    Diskle örtüşen üçgen yoksa: floor verilmişse floor, yoksa CamError. floor verilmişse sonuç
    max(z_CL, floor). Desteklenmeyen takım (matkap) → CamError.
    """
    K = kesici(tool)
    rad = K.R
    xy = np.atleast_2d(np.asarray(xy, dtype=float))
    if xy.ndim != 2 or xy.shape[1] != 2:
        raise CamError(f"drop: xy (k, 2) olmalı (şekil {xy.shape})")
    if not np.all(np.isfinite(xy)):
        raise CamError("drop: xy sonlu olmalı")
    if floor is not None and not np.isfinite(floor):
        raise CamError(f"drop: floor sonlu olmalı ({floor})")
    z = np.full(len(xy), -np.inf)
    for idx, tri in _ciftler(mesh, rad, xy):
        np.maximum.at(z, idx, tri_z(mesh._P[tri], mesh._n[tri], xy[idx], K))
    temassiz = ~np.isfinite(z)
    if floor is None:
        if np.any(temassiz):
            i = int(np.argmax(temassiz))
            raise CamError(f"drop: ({xy[i, 0]}, {xy[i, 1]}) noktasında takım ağa değmiyor (floor yok)")
        return z
    return np.maximum(np.where(temassiz, floor, z), floor)


def drop_one(mesh: TriMesh, tool: Tool | Cutter, x: float, y: float, floor: float | None = None) -> float:
    """Tek nokta için drop."""
    return float(drop(mesh, tool, np.array([[x, y]], dtype=float), floor)[0])
