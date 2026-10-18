"""
SPEC 39 — İşlenmiş parça ikizi: simüle edilen durumdan kapalı ağ (kolon / yüzey), ikili STL ve
CAD parçasına göre işaretli sapma haritası (3B nokta–üçgen uzaklığı).

Kolon ağı: her hücre aralığı [l, u] bir dik prizmadır; ağ prizmaların birleşiminin sınırıdır (üst, alt
yüzler ve komşu hücre aralıklarının simetrik farkı kadar dik duvar). Düşey kenarlar her hücre köşesi
doğrusunda, o doğruya değen tüm yüzlerin köşe yükseklikleriyle bölünür (T-birleşimi yok); böylece her
yönlü kenarın tersi de bulunur (kapalı) ve hacim durumun hacmine eşittir.

SPEC 05 dosyalarını değiştirmez; `cam.sim.ikiz` olarak içe aktarılır.

Birimler: mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from cam.model import CamError
from cam.sim.dexel import DexelMap
from cam.sim.part import mesh_zmap
from cam.sim.zmap import ZMap

State = ZMap | DexelMap

_STL_DT = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("attr", "<u2")])


# ---------------------------------------------------------------- ağ yardımcıları


def _check_mesh(V, T) -> tuple[np.ndarray, np.ndarray]:
    V = np.asarray(V, dtype=float)
    T = np.asarray(T)
    if V.ndim != 2 or V.shape[1] != 3 or T.ndim != 2 or T.shape[1] != 3:
        raise CamError(f"Ağ şekli (n, 3) ve (m, 3) olmalı ({V.shape}, {T.shape})")
    if len(V) == 0 or len(T) == 0:
        raise CamError("Ağ boş")
    if not np.issubdtype(T.dtype, np.integer):
        raise CamError("Üçgen indeksleri tamsayı olmalı")
    if T.min() < 0 or T.max() >= len(V):
        raise CamError("Üçgen indeksi köşe aralığı dışında")
    if not np.all(np.isfinite(V)):
        raise CamError("Ağ köşelerinde sonlu olmayan değer")
    return V, T


def mesh_volume(V: np.ndarray, T: np.ndarray) -> float:
    """Diverjans teoremi: Σ v₀·(v₁ × v₂) / 6."""
    V = np.asarray(V, dtype=float)
    T = np.asarray(T)
    v0, v1, v2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def _is_closed(T: np.ndarray) -> bool:
    """Her yönlü kenar (a, b) sayısı ters yönlü (b, a) sayısına eşit mi."""
    T = np.asarray(T, dtype=np.int64)
    E = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    n = int(E.max()) + 1 if len(E) else 1
    ileri = np.unique(E[:, 0] * n + E[:, 1], return_counts=True)
    geri = np.unique(E[:, 1] * n + E[:, 0], return_counts=True)
    return bool(np.array_equal(ileri[0], geri[0]) and np.array_equal(ileri[1], geri[1]))


def write_stl(path: str | Path, V: np.ndarray, T: np.ndarray, name: str = "ikiz") -> None:
    """İkili STL yazar (80 bayt başlık, uint32 sayı, üçgen başına 50 bayt, little-endian)."""
    V, T = _check_mesh(V, T)
    try:
        bas = name.encode("ascii")
    except UnicodeEncodeError as hata:
        raise CamError(f"STL adı ASCII olmalı ({name!r})") from hata
    if len(bas) > 80:
        raise CamError(f"STL adı en çok 80 bayt ({len(bas)})")
    if bas.startswith(b"solid"):
        raise CamError("İkili STL başlığı 'solid' ile başlayamaz (ASCII STL ile karışır)")
    P = V[T]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    L = np.linalg.norm(n, axis=1)
    n = np.divide(n, L[:, None], out=np.zeros_like(n), where=L[:, None] > 0)
    kayit = np.zeros(len(T), dtype=_STL_DT)
    kayit["n"] = n
    kayit["v"] = P
    with open(path, "wb") as f:
        f.write(bas.ljust(80, b" "))
        f.write(np.array([len(T)], dtype="<u4").tobytes())
        f.write(kayit.tobytes())


@dataclass
class TwinMesh:
    """İkiz ağı: köşeler V (n, 3), üçgenler T (m, 3), üst yüz üçgeninin hücresi face_cell (m,), aksi −1."""

    V: np.ndarray
    T: np.ndarray
    face_cell: np.ndarray

    def volume(self) -> float:
        return mesh_volume(self.V, self.T)

    def is_closed(self) -> bool:
        return _is_closed(self.T)

    def to_stl(self, path: str | Path, name: str = "ikiz") -> None:
        write_stl(path, self.V, self.T, name)


class _Kurucu:
    """Kaynaklı köşe ve üçgen biriktirici. Köşe anahtarı (köşe indeksi i, j, z)."""

    def __init__(self, state: State) -> None:
        self.s = state
        self.id: dict[tuple[int, int, float], int] = {}
        self.V: list[tuple[float, float, float]] = []
        self.T: list[tuple[int, int, int]] = []
        self.fc: list[int] = []

    def kose(self, i: int, j: int, z: float) -> int:
        k = (i, j, z)
        v = self.id.get(k)
        if v is None:
            v = len(self.V)
            self.id[k] = v
            self.V.append((self.s.x0 + i * self.s.dx, self.s.y0 + j * self.s.dy, z))
        return v

    def ucgen(self, a: int, b: int, c: int, n: np.ndarray, hucre: int = -1) -> None:
        """Üçgeni dış normal n yönünde sağ el kuralıyla ekler (gerekirse ters çevirir)."""
        if a == b or b == c or a == c:
            return
        P = np.array([self.V[a], self.V[b], self.V[c]])
        if float(np.cross(P[1] - P[0], P[2] - P[0]) @ n) < 0:
            b, c = c, b
        self.T.append((a, b, c))
        self.fc.append(hucre)

    def sonuc(self) -> TwinMesh:
        return TwinMesh(
            np.array(self.V, dtype=float).reshape(-1, 3),
            np.array(self.T, dtype=np.int64).reshape(-1, 3),
            np.array(self.fc, dtype=np.int64),
        )


def _araliklar(state: State) -> list[list[list[tuple[float, float]]]]:
    """Hücre başına aralıklar [j][i]."""
    if isinstance(state, ZMap):
        return [[[(state.zmin, float(z))] if z > state.zmin else [] for z in row.tolist()] for row in state.z]
    return [[state.intervals(i, j) for i in range(state.nx)] for j in range(state.ny)]


def _fark(A: list[tuple[float, float]], B: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """A − B (sıralı ayrık aralık listeleri)."""
    out = []
    for lo, hi in A:
        parca = [(lo, hi)]
        for b0, b1 in B:
            yeni = []
            for p0, p1 in parca:
                if b1 <= p0 or b0 >= p1:
                    yeni.append((p0, p1))
                    continue
                if b0 > p0:
                    yeni.append((p0, b0))
                if b1 < p1:
                    yeni.append((b1, p1))
            parca = yeni
        out.extend(parca)
    return out


def _kolon(state: State) -> TwinMesh:
    nx, ny = state.nx, state.ny
    I = _araliklar(state)  # noqa: E741
    if not any(I[j][i] for j in range(ny) for i in range(nx)):
        raise CamError("İkiz ağı: malzeme kalmamış (boş katı)")

    def hucre(i: int, j: int) -> list[tuple[float, float]]:
        return I[j][i] if 0 <= i < nx and 0 <= j < ny else []

    # duvar parçaları: (köşe a, köşe b, z0, z1, dış normal)
    duvarlar: list[tuple[tuple[int, int], tuple[int, int], float, float, np.ndarray]] = []
    for j in range(ny):
        for i in range(-1, nx):  # x yönü kenarı: (i, j) | (i + 1, j), x = i + 1 doğrusu
            A, B = hucre(i, j), hucre(i + 1, j)
            ka, kb = (i + 1, j), (i + 1, j + 1)
            for z0, z1 in _fark(A, B):
                duvarlar.append((ka, kb, z0, z1, np.array([1.0, 0.0, 0.0])))
            for z0, z1 in _fark(B, A):
                duvarlar.append((ka, kb, z0, z1, np.array([-1.0, 0.0, 0.0])))
    for j in range(-1, ny):
        for i in range(nx):  # y yönü kenarı: (i, j) | (i, j + 1), y = j + 1 doğrusu
            A, B = hucre(i, j), hucre(i, j + 1)
            ka, kb = (i, j + 1), (i + 1, j + 1)
            for z0, z1 in _fark(A, B):
                duvarlar.append((ka, kb, z0, z1, np.array([0.0, 1.0, 0.0])))
            for z0, z1 in _fark(B, A):
                duvarlar.append((ka, kb, z0, z1, np.array([0.0, -1.0, 0.0])))

    # köşe doğrusu kırılma yükseklikleri
    kirik: dict[tuple[int, int], set[float]] = {}
    for j in range(ny):
        for i in range(nx):
            for lo, hi in I[j][i]:
                for k in ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)):
                    kirik.setdefault(k, set()).update((lo, hi))
    for ka, kb, z0, z1, _ in duvarlar:
        for k in (ka, kb):
            kirik.setdefault(k, set()).update((z0, z1))
    sirali = {k: np.array(sorted(v)) for k, v in kirik.items()}

    K = _Kurucu(state)
    ust, alt = np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])
    for j in range(ny):
        for i in range(nx):
            c = j * nx + i
            for lo, hi in I[j][i]:
                for z, n, h in ((hi, ust, c), (lo, alt, -1)):
                    a, b = K.kose(i, j, z), K.kose(i + 1, j, z)
                    d, e = K.kose(i + 1, j + 1, z), K.kose(i, j + 1, z)
                    K.ucgen(a, b, d, n, h)
                    K.ucgen(a, d, e, n, h)
    for ka, kb, z0, z1, n in duvarlar:
        zs = sirali[ka]
        L = [K.kose(*ka, float(z)) for z in zs[(zs >= z0) & (zs <= z1)]]
        zs = sirali[kb]
        R = [K.kose(*kb, float(z)) for z in zs[(zs >= z0) & (zs <= z1)]]
        p, q = 0, 0  # fermuar: her üçgenin iki köşesi bir doğruda, biri öbüründe
        while p < len(L) - 1 or q < len(R) - 1:
            sol = q == len(R) - 1 or (p < len(L) - 1 and K.V[L[p + 1]][2] <= K.V[R[q + 1]][2])
            if sol:
                K.ucgen(L[p], L[p + 1], R[q], n)
                p += 1
            else:
                K.ucgen(L[p], R[q + 1], R[q], n)
                q += 1
    return K.sonuc()


def _yuzey(state: ZMap) -> TwinMesh:
    nx, ny = state.nx, state.ny
    z = state.z
    if not np.any(z > state.zmin):
        raise CamError("İkiz ağı: malzeme kalmamış (boş katı)")
    # düğüm yüksekliği: komşu hücrelerin ortalaması
    top = np.zeros((ny + 1, nx + 1))
    say = np.zeros((ny + 1, nx + 1))
    for dj in (0, 1):
        for di in (0, 1):
            top[dj : dj + ny, di : di + nx] += z
            say[dj : dj + ny, di : di + nx] += 1
    H = top / say
    K = _Kurucu(state)
    ust, alt = np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])
    for j in range(ny):
        for i in range(nx):
            a, b = K.kose(i, j, float(H[j, i])), K.kose(i + 1, j, float(H[j, i + 1]))
            d, e = K.kose(i + 1, j + 1, float(H[j + 1, i + 1])), K.kose(i, j + 1, float(H[j + 1, i]))
            K.ucgen(a, b, d, ust, j * nx + i)
            K.ucgen(a, d, e, ust, j * nx + i)
            zm = state.zmin
            a, b = K.kose(i, j, zm), K.kose(i + 1, j, zm)
            d, e = K.kose(i + 1, j + 1, zm), K.kose(i, j + 1, zm)
            K.ucgen(a, b, d, alt)
            K.ucgen(a, d, e, alt)
    # perdeler: sınır düğümleri arasında üstten zmin'e
    kenar = []
    kenar += [((i, 0), (i + 1, 0), np.array([0.0, -1.0, 0.0])) for i in range(nx)]
    kenar += [((i, ny), (i + 1, ny), np.array([0.0, 1.0, 0.0])) for i in range(nx)]
    kenar += [((0, j), (0, j + 1), np.array([-1.0, 0.0, 0.0])) for j in range(ny)]
    kenar += [((nx, j), (nx, j + 1), np.array([1.0, 0.0, 0.0])) for j in range(ny)]
    for (i1, j1), (i2, j2), n in kenar:
        u1, u2 = K.kose(i1, j1, float(H[j1, i1])), K.kose(i2, j2, float(H[j2, i2]))
        b1, b2 = K.kose(i1, j1, state.zmin), K.kose(i2, j2, state.zmin)
        if u1 != b1:
            K.ucgen(u1, b1, b2, n)
        if u2 != b2:
            K.ucgen(u1, b2, u2, n)
    return K.sonuc()


def twin_mesh(state: State, mode: str = "kolon") -> TwinMesh:
    """Durumdan kapalı ağ; mode "kolon" (kesin hacim) ya da "yuzey" (yalnız ZMap, görüntü)."""
    if not isinstance(state, ZMap | DexelMap):
        raise CamError(f"Durum ZMap ya da DexelMap olmalı ({type(state).__name__})")
    if mode == "kolon":
        return _kolon(state)
    if mode == "yuzey":
        if not isinstance(state, ZMap):
            raise CamError("Yüzey ağı yalnız z-haritasından kurulur")
        return _yuzey(state)
    raise CamError(f"Bilinmeyen ağ biçimi: {mode!r} (kolon veya yuzey)")


# ---------------------------------------------------------------- uzaklık


def _closest(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Noktaların üçgendeki en yakın noktası (Ericson 5.1.5); p (..., 3), a, b, c yayınlanabilir."""
    ab, ac = b - a, c - a
    ap, bp, cp = p - a, p - b, p - c

    def dot(u, v):
        return np.sum(u * v, axis=-1)

    d1, d2 = dot(ab, ap), dot(ac, ap)
    d3, d4 = dot(ab, bp), dot(ac, bp)
    d5, d6 = dot(ab, cp), dot(ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        v_ab = d1 / (d1 - d3)
        w_ac = d2 / (d2 - d6)
        w_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        den = 1.0 / (va + vb + vc)
        v_i, w_i = vb * den, vc * den
    kosullar = [
        (d1 <= 0) & (d2 <= 0),
        (d3 >= 0) & (d4 <= d3),
        (vc <= 0) & (d1 >= 0) & (d3 <= 0),
        (d6 >= 0) & (d5 <= d6),
        (vb <= 0) & (d2 >= 0) & (d6 <= 0),
        (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0),
    ]
    shape = np.broadcast_shapes(p.shape, a.shape)
    secenek = [
        np.broadcast_to(a, shape),
        np.broadcast_to(b, shape),
        a + v_ab[..., None] * ab,
        np.broadcast_to(c, shape),
        a + w_ac[..., None] * ac,
        b + w_bc[..., None] * (c - b),
    ]
    sonuc = a + v_i[..., None] * ab + w_i[..., None] * ac
    for kosul, deger in zip(kosullar[::-1], secenek[::-1], strict=True):
        sonuc = np.where(kosul[..., None], deger, sonuc)
    return sonuc


def point_triangle_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Noktalardan (k, 3) tek üçgene kesin uzaklık (Ericson 5.1.5)."""
    p = np.asarray(p, dtype=float).reshape(-1, 3)
    a, b, c = (np.asarray(v, dtype=float) for v in (a, b, c))
    return np.linalg.norm(p - _closest(p, a, b, c), axis=-1)


def point_mesh_distance(p: np.ndarray, V: np.ndarray, T: np.ndarray, blok: int = 64) -> np.ndarray:
    """Noktalardan (k, 3) ağa en kısa uzaklık (tüm üçgenler, bloklar halinde)."""
    V, T = _check_mesh(V, T)
    p = np.asarray(p, dtype=float).reshape(-1, 3)
    d = np.full(len(p), np.inf)
    if len(p) == 0:
        return d
    P = p[:, None, :]
    for s in range(0, len(T), blok):
        t = T[s : s + blok]
        a, b, c = V[t[:, 0]][None], V[t[:, 1]][None], V[t[:, 2]][None]
        dd = np.linalg.norm(P - _closest(P, a, b, c), axis=-1)
        d = np.minimum(d, dd.min(axis=1))
    return d


# ---------------------------------------------------------------- sapma


@dataclass
class Deviation:
    """İşaretli sapma s (+ fazlalık, − çakma), düşey fark dz, ölçülen hücreler ve özet."""

    s: np.ndarray
    dz: np.ndarray
    measured: np.ndarray
    max_excess: float
    max_gouge: float
    rms: float

    def bands(self, edges: list[float]) -> np.ndarray:
        """Kenarlar b_0 < … < b_m: [< b_0, [b_0, b_1), …, ≥ b_m] aralıklarındaki ölçülen hücre sayısı."""
        b = np.asarray(edges, dtype=float)
        if b.ndim != 1 or len(b) == 0 or not np.all(np.isfinite(b)) or np.any(np.diff(b) <= 0):
            raise CamError(f"Bant kenarları sonlu ve kesin artan olmalı ({edges})")
        k = np.searchsorted(b, self.s[self.measured], side="right")
        return np.bincount(k, minlength=len(b) + 1)

    def within(self, lo: float, hi: float) -> bool:
        """Tüm ölçülen hücrelerde −lo ≤ s ≤ hi mi."""
        for ad, v in (("lo", lo), ("hi", hi)):
            if not (math.isfinite(v) and v >= 0):
                raise CamError(f"Tolerans {ad} sonlu ve ≥ 0 olmalı ({v})")
        s = self.s[self.measured]
        return bool(np.all((s >= -lo) & (s <= hi)))


def deviation(state: State, V: np.ndarray, T: np.ndarray, part_z: np.ndarray | None = None) -> Deviation:
    """CAD ağına göre hücre başına işaretli sapma haritası."""
    if not isinstance(state, ZMap | DexelMap):
        raise CamError(f"Durum ZMap ya da DexelMap olmalı ({type(state).__name__})")
    V, T = _check_mesh(V, T)
    top = state.z.copy() if isinstance(state, ZMap) else state.top()
    if part_z is None:
        grid = ZMap(state.x0, state.y0, state.dx, state.dy, state.nx, state.ny, state.zmin, state.zmax, top)
        zP = mesh_zmap(V, T, grid)
    else:
        zP = np.asarray(part_z, dtype=float)
        if zP.shape != top.shape:
            raise CamError(f"part_z şekli ızgarayla uyuşmuyor ({zP.shape} ≠ {top.shape})")
    measured = np.isfinite(zP) | (top > state.zmin)
    dz = top - np.maximum(zP, state.zmin)
    sigma = np.where(top > zP, 1.0, np.where(top < zP, -1.0, 0.0))
    s = np.zeros_like(top)
    hedef = measured & (sigma != 0)
    if hedef.any():
        X, Y = np.meshgrid(state.xs(), state.ys())
        P = np.column_stack([X[hedef], Y[hedef], top[hedef]])
        s[hedef] = sigma[hedef] * point_mesh_distance(P, V, T)
    sm = s[measured]
    if sm.size:
        max_excess = float(max(sm.max(), 0.0))
        max_gouge = float(max((-sm).max(), 0.0))
        rms = float(np.sqrt(np.mean(sm**2)))
    else:
        max_excess = max_gouge = rms = 0.0
    return Deviation(s, dz, measured, max_excess, max_gouge, rms)
