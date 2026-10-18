"""
SPEC 06 — Drop-cutter: takımı Z boyunca üçgen ağına değene kadar indirme.

Küresel (BALL) ve düz (FLAT, corner_r = 0) uç. CL = takım ucu (en alt nokta, eksen üzerinde).
Verilen (x, y) için takımın XY izdüşüm diskiyle örtüşen her üçgende üç test yapılır (köşe, yüz,
kenar); temas yüksekliği hepsinin en büyüğüdür (Yau vd. 2004; OpenCAMLib BatchDropCutter yapısı).

Hesap noktalar × aday üçgen çiftleri üzerinde vektörlenir. Aday üçgenler, üçgen ağırlık
merkezlerinin XY kd-ağacıyla süzülür (scipy.spatial.cKDTree).

Birimler: mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from cam.model import CamError, Tool, ToolKind

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
        self._r_max = float(np.max(np.linalg.norm(P[:, :, :2] - G[:, None, :], axis=2)))

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.V.min(axis=0), self.V.max(axis=0)

    @classmethod
    def from_part(cls, part, tol: float = 0.01) -> TriMesh:
        """geometry.part.Part.mesh(tol) ile ağ (kiriş sapması tol [mm])."""
        V, T = part.mesh(tol)
        return cls(V=V, T=T)


def _yaricap(tool: Tool) -> float:
    """Desteklenen takımın yarıçapı; diğerleri CamError."""
    if tool.kind is ToolKind.BALL:
        return tool.D / 2
    if tool.kind is ToolKind.FLAT and tool.corner_r == 0:
        return tool.D / 2
    raise CamError(f"drop-cutter: '{tool.name}' desteklenmiyor (yalnız küresel ve köşesiz düz uç)")


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


def drop(mesh: TriMesh, tool: Tool, xy: np.ndarray, floor: float | None = None) -> np.ndarray:
    """Her (x, y) için z_CL = max(köşe, yüz, kenar testleri) [mm].

    Diskle örtüşen üçgen yoksa: floor verilmişse floor, yoksa CamError. floor verilmişse sonuç
    max(z_CL, floor). Desteklenmeyen takım (matkap, köşe radyüslü düz) → CamError.
    """
    rad = _yaricap(tool)
    xy = np.atleast_2d(np.asarray(xy, dtype=float))
    if xy.ndim != 2 or xy.shape[1] != 2:
        raise CamError(f"drop: xy (k, 2) olmalı (şekil {xy.shape})")
    if not np.all(np.isfinite(xy)):
        raise CamError("drop: xy sonlu olmalı")
    if floor is not None and not np.isfinite(floor):
        raise CamError(f"drop: floor sonlu olmalı ({floor})")
    test = _kure if tool.kind is ToolKind.BALL else _duz
    adaylar = mesh._agac.query_ball_point(xy, rad + mesh._r_max + TOL)
    sayi = np.array([len(a) for a in adaylar])
    z = np.full(len(xy), -np.inf)
    bas = 0
    while bas < len(xy):
        # toplam çift sayısı _CIFT'i aşmayacak kadar nokta (en az bir nokta)
        son = bas + max(1, int(np.searchsorted(np.cumsum(sayi[bas:]), _CIFT, side="right")))
        idx = np.repeat(np.arange(bas, son), sayi[bas:son])
        if len(idx):
            tri = np.concatenate([np.asarray(a, dtype=int) for a in adaylar[bas:son]])
            zc = test(mesh._P[tri], mesh._n[tri], xy[idx], rad)
            np.maximum.at(z, idx, zc)
        bas = son
    temassiz = ~np.isfinite(z)
    if floor is None:
        if np.any(temassiz):
            i = int(np.argmax(temassiz))
            raise CamError(f"drop: ({xy[i, 0]}, {xy[i, 1]}) noktasında takım ağa değmiyor (floor yok)")
        return z
    return np.maximum(np.where(temassiz, floor, z), floor)


def drop_one(mesh: TriMesh, tool: Tool, x: float, y: float, floor: float | None = None) -> float:
    """Tek nokta için drop."""
    return float(drop(mesh, tool, np.array([[x, y]], dtype=float), floor)[0])
