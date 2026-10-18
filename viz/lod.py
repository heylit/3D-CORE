"""
SPEC 53 — Kademeli ağ (LOD): quadric error metric ile kenar daraltma (Garland–Heckbert 1997),
Hausdorff uzaklığı ve ekran uzayı hatasıyla seviye seçimi. Saf numpy.

Quadric: üçgen düzlemi p = (n, −n·x₀) için K = p pᵀ; köşe quadriği Q = Σ K (komşu üçgenler).
Kenar (u, v) daraltılınca yeni köşe v̄ = argmin v̄ᵀ (Q_u + Q_v) v̄ (3 × 3 doğrusal sistem; tekilse uçlardan
ve orta noktadan en iyisi); maliyet en küçük kenar önce daraltılır.
Ekran hatası e_px = d_H · f / (z · s) (odak f, uzaklık z, piksel boyu s);
seçilen seviye e_px ≤ px olan en kabası.
Sınır kenarları ve keskin kenarlar (dihedral açı > keep_angle) daraltılmaz; uçları özellik köşesidir ve
yerinde kalır. Bağlantı koşulu (iki köşenin ortak komşuları tam iki) ve üçgen normalinin dönmemesi
daraltmayı kabul etmenin şartıdır; böylece kapalı ağ kapalı kalır.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np

from viz.scene import VizError

_TEKIL = 1e-10  # quadric 3 × 3 bloğunun koşul eşiği (göreli determinant)


@dataclass
class Level:
    """Bir LOD seviyesi: köşeler V, üçgenler T, oran ve asıl ağa tek yönlü Hausdorff uzaklığı."""

    V: np.ndarray
    T: np.ndarray
    ratio: float
    hausdorff: float


# ---------------------------------------------------------------- doğrulama ve yardımcılar


def _ag(V, T) -> tuple[np.ndarray, np.ndarray]:
    V = np.asarray(V, dtype=float)
    T = np.asarray(T)
    if V.ndim != 2 or V.shape[1] != 3 or len(V) == 0 or not np.all(np.isfinite(V)):
        raise VizError(f"LOD: V (n, 3) sonlu köşeler olmalı (şekil {V.shape})")
    if T.ndim != 2 or T.shape[1] != 3 or len(T) == 0:
        raise VizError(f"LOD: T (m, 3) üçgenler olmalı (şekil {T.shape})")
    if not np.issubdtype(T.dtype, np.integer):
        if not np.all(T == np.round(T)):
            raise VizError("LOD: T tam sayı indeks olmalı")
        T = T.astype(np.int64)
    if T.min() < 0 or T.max() >= len(V):
        raise VizError(f"LOD: T indeksi 0..{len(V) - 1} dışında")
    if np.any((T[:, 0] == T[:, 1]) | (T[:, 1] == T[:, 2]) | (T[:, 0] == T[:, 2])):
        raise VizError("LOD: yozlaşmış üçgen (tekrarlanan köşe)")
    return V, T.astype(np.int64)


def _kenarlar(T: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Tekil kenarlar (k, 2) (u < v), üçgen sayıları, yönlü kenar → tekil indeks ve yönlü kenarın üçgeni."""
    E = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    F = np.tile(np.arange(len(T)), 3)
    Es = np.sort(E, axis=1)
    tekil, ters, say = np.unique(Es, axis=0, return_inverse=True, return_counts=True)
    return tekil, say, ters.reshape(-1), F


def _normaller(V: np.ndarray, T: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    N = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    alan2 = np.linalg.norm(N, axis=1)
    return N / np.where(alan2 > 0, alan2, 1.0)[:, None], alan2


# ---------------------------------------------------------------- sadeleştirme


def simplify(V, T, target: int, keep_angle: float = 30.0) -> tuple[np.ndarray, np.ndarray]:
    """Üçgen sayısını target'a (ya da korunan kenarlar izin verdiği kadar) indirir."""
    V, T = _ag(V, T)
    if isinstance(target, bool) or not isinstance(target, int | np.integer):
        raise VizError(f"simplify: target tam sayı olmalı ({target!r})")
    if target < 4 or target >= len(T):
        raise VizError(f"simplify: 4 ≤ target < üçgen sayısı ({len(T)}) olmalı (target={target})")
    if not (isinstance(keep_angle, int | float) and 0 <= keep_angle <= 180):
        raise VizError(f"simplify: keep_angle 0..180 derece olmalı ({keep_angle})")
    return _Daraltici(V, T, float(keep_angle)).calis(int(target))


class _Daraltici:
    def __init__(self, V: np.ndarray, T: np.ndarray, keep_angle: float) -> None:
        self.V = V.copy()
        self.T = T.copy()
        self.canli = np.ones(len(T), dtype=bool)
        n_tri, alan2 = _normaller(V, T)
        if np.any(alan2 <= 0):
            raise VizError("LOD: sıfır alanlı üçgen")
        tekil, say, ters, F = _kenarlar(T)
        if np.any(say > 2):
            raise VizError("LOD: manifold olmayan kenar (üçten fazla üçgen ortak)")
        # keskin kenar: iki komşu üçgen normali arasındaki açı > keep_angle
        kilit = say == 1
        iki = np.nonzero(say == 2)[0]
        sira = np.argsort(ters, kind="stable")
        f_sirali = F[sira]
        bas = np.concatenate([[0], np.cumsum(say)])
        f1 = f_sirali[bas[iki]]
        f2 = f_sirali[bas[iki] + 1]
        cos = np.einsum("ij,ij->i", n_tri[f1], n_tri[f2])
        kilit[iki] = cos < math.cos(math.radians(keep_angle))
        self.ozellik = np.zeros(len(V), dtype=bool)
        self.ozellik[tekil[kilit].ravel()] = True
        self.kilit_kenar = {(int(a), int(b)) for a, b in tekil[kilit]}
        # köşe quadrikleri
        d = -np.einsum("ij,ij->i", n_tri, V[T[:, 0]])
        p = np.column_stack([n_tri, d])
        K = p[:, :, None] * p[:, None, :] * (alan2 / 2)[:, None, None]  # alanla ağırlıklı
        self.Q = np.zeros((len(V), 4, 4))
        for c in range(3):
            np.add.at(self.Q, T[:, c], K)
        self.yuz: list[set[int]] = [set() for _ in range(len(V))]
        for f, (a, b, c) in enumerate(T.tolist()):
            self.yuz[a].add(f)
            self.yuz[b].add(f)
            self.yuz[c].add(f)
        self.surum = np.zeros(len(V), dtype=np.int64)
        self.yigin: list[tuple[float, int, int, int, int]] = []
        for a, b in tekil.tolist():
            self._it(a, b)

    def _komsu(self, v: int) -> set[int]:
        s: set[int] = set()
        for f in self.yuz[v]:
            s.update(self.T[f].tolist())
        s.discard(v)
        return s

    def _hedef(self, a: int, b: int) -> tuple[float, np.ndarray] | None:
        """Daraltma maliyeti ve yeni konum; izin yoksa None."""
        if (min(a, b), max(a, b)) in self.kilit_kenar:
            return None
        oa, ob = self.ozellik[a], self.ozellik[b]
        if oa and ob:
            return None
        Q = self.Q[a] + self.Q[b]
        if oa or ob:
            adaylar = [self.V[a] if oa else self.V[b]]
        else:
            A = Q[:3, :3]
            olcek = float(np.abs(A).max()) or 1.0
            if abs(np.linalg.det(A)) > _TEKIL * olcek**3:
                adaylar = [np.linalg.solve(A, -Q[:3, 3])]
            else:
                adaylar = [self.V[a], self.V[b], (self.V[a] + self.V[b]) / 2]
        en = None
        for x in adaylar:
            h = np.append(x, 1.0)
            c = float(h @ Q @ h)
            if en is None or c < en[0]:
                en = (max(c, 0.0), x)
        return en

    def _it(self, a: int, b: int) -> None:
        h = self._hedef(a, b)
        if h is not None:
            heapq.heappush(self.yigin, (h[0], a, b, int(self.surum[a]), int(self.surum[b])))

    def _gecerli(self, a: int, b: int, x: np.ndarray) -> bool:
        ortak = self._komsu(a) & self._komsu(b)
        ab_yuz = self.yuz[a] & self.yuz[b]
        if len(ortak) != len(ab_yuz):  # bağlantı koşulu (kapalı ağda 2 ortak komşu)
            return False
        if len(self.yuz[a] | self.yuz[b]) - len(ab_yuz) < 3:
            return False  # dörtyüzlüden küçüğe inme
        for v in (a, b):
            for f in self.yuz[v] - ab_yuz:
                tri = self.T[f]
                P = self.V[tri]
                n0 = _cross(P[1] - P[0], P[2] - P[0])
                P = P.copy()
                P[tri == v] = x
                n1 = _cross(P[1] - P[0], P[2] - P[0])
                if n0[0] * n1[0] + n0[1] * n1[1] + n0[2] * n1[2] <= 1e-12 * (
                    n0[0] ** 2 + n0[1] ** 2 + n0[2] ** 2
                ):
                    return False  # normal dönüyor veya üçgen yozlaşıyor
        return True

    def calis(self, target: int) -> tuple[np.ndarray, np.ndarray]:
        kalan = int(self.canli.sum())
        while kalan > target and self.yigin:
            _, a, b, sa, sb = heapq.heappop(self.yigin)
            if sa != self.surum[a] or sb != self.surum[b]:
                continue
            h = self._hedef(a, b)
            if h is None or not self._gecerli(a, b, h[1]):
                continue
            kalan -= self._daralt(a, b, h[1])
        return self._sikistir()

    def _daralt(self, a: int, b: int, x: np.ndarray) -> int:
        """b'yi a'ya katar; silinen üçgen sayısı."""
        silinen = self.yuz[a] & self.yuz[b]
        for f in silinen:
            self.canli[f] = False
            for v in self.T[f].tolist():
                self.yuz[v].discard(f)
        for f in self.yuz[b]:
            self.T[f][self.T[f] == b] = a
            self.yuz[a].add(f)
        self.yuz[b] = set()
        self.V[a] = x
        self.Q[a] = self.Q[a] + self.Q[b]
        self.ozellik[a] |= self.ozellik[b]
        for k in [k for k in self.kilit_kenar if b in k]:
            self.kilit_kenar.discard(k)
            u = k[0] if k[1] == b else k[1]
            self.kilit_kenar.add((min(a, u), max(a, u)))
        self.surum[a] += 1
        self.surum[b] += 1
        for u in self._komsu(a):
            self._it(a, u)
        return len(silinen)

    def _sikistir(self) -> tuple[np.ndarray, np.ndarray]:
        T = self.T[self.canli]
        kullanilan = np.unique(T)
        yeni = np.full(len(self.V), -1, dtype=np.int64)
        yeni[kullanilan] = np.arange(len(kullanilan))
        return self.V[kullanilan].copy(), yeni[T]


def _cross(a, b) -> tuple[float, float, float]:
    """Tek vektör çarpımı (np.cross'un küçük dizi yükü olmadan)."""
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


# ---------------------------------------------------------------- Hausdorff


def hausdorff(V0, T0, V1, T1, n: int = 20_000) -> float:
    """Tek yönlü Hausdorff uzaklığı.

    (V1, T1) yüzeyinden örneklenen noktaların (V0, T0) yüzeyine en büyük uzaklığı. Örnekler: (V1, T1)'in
    köşeleri + alanla orantılı n düzgün nokta (sabit tohum).
    """
    V0, T0 = _ag(V0, T0)
    V1, T1 = _ag(V1, T1)
    if isinstance(n, bool) or not isinstance(n, int | np.integer) or n < 0:
        raise VizError(f"hausdorff: n negatif olmayan tam sayı olmalı ({n!r})")
    P = np.vstack([V1[np.unique(T1)], _ornekle(V1, T1, int(n))])
    return float(_uzaklik(P, V0[T0]).max())


def _ornekle(V: np.ndarray, T: np.ndarray, n: int) -> np.ndarray:
    if n == 0:
        return np.zeros((0, 3))
    rng = np.random.default_rng(0)
    _, alan2 = _normaller(V, T)
    f = rng.choice(len(T), size=n, p=alan2 / alan2.sum())
    r1 = np.sqrt(rng.random(n))
    r2 = rng.random(n)
    A, B, C = V[T[f, 0]], V[T[f, 1]], V[T[f, 2]]
    return (1 - r1)[:, None] * A + (r1 * (1 - r2))[:, None] * B + (r1 * r2)[:, None] * C


def _uzaklik(P: np.ndarray, Tri: np.ndarray) -> np.ndarray:
    """Her noktanın üçgen kümesine en kısa uzaklığı. Düzgün ızgara: üçgen, kutusunun m kadar şişirilmiş
    hücrelerine yazılır; m'den uzak kalan noktalar tüm üçgenlerle (bloklu) yeniden hesaplanır."""
    lo = Tri.min(axis=1)
    hi = Tri.max(axis=1)
    kenar = float(np.mean(np.linalg.norm(Tri[:, 1] - Tri[:, 0], axis=1)))
    h = max(kenar, 1e-12)
    m = h
    g0 = np.minimum(lo.min(axis=0), P.min(axis=0)) - m
    i_lo = np.floor((lo - m - g0) / h).astype(np.int64)
    i_hi = np.floor((hi + m - g0) / h).astype(np.int64)
    boyut = np.maximum(i_hi.max(axis=0), np.floor((P.max(axis=0) - g0) / h).astype(np.int64)) + 1
    # üçgen → hücre listesi
    hucre, ucgen = [], []
    sayi = np.prod(i_hi - i_lo + 1, axis=1)
    for f in np.nonzero(sayi)[0].tolist():
        a, b = i_lo[f], i_hi[f]
        Ix, Jy, Kz = np.meshgrid(*(np.arange(a[d], b[d] + 1) for d in range(3)), indexing="ij")
        c = (Ix * boyut[1] + Jy) * boyut[2] + Kz
        hucre.append(c.ravel())
        ucgen.append(np.full(c.size, f))
    hucre = np.concatenate(hucre)
    ucgen = np.concatenate(ucgen)
    s = np.argsort(hucre, kind="stable")
    hucre, ucgen = hucre[s], ucgen[s]
    ip = np.floor((P - g0) / h).astype(np.int64)
    cp = (ip[:, 0] * boyut[1] + ip[:, 1]) * boyut[2] + ip[:, 2]
    b0 = np.searchsorted(hucre, cp, side="left")
    b1 = np.searchsorted(hucre, cp, side="right")
    d = np.full(len(P), np.inf)
    adet = b1 - b0
    if adet.sum():
        nokta = np.repeat(np.arange(len(P)), adet)
        yer = np.repeat(b0 - np.cumsum(np.concatenate([[0], adet[:-1]])), adet) + np.arange(adet.sum())
        dd = _nokta_ucgen(P[nokta], Tri[ucgen[yer]])
        np.minimum.at(d, nokta, dd)
    uzak = np.nonzero(~(d <= m))[0]
    for i in range(0, len(uzak), 64):
        q = uzak[i : i + 64]
        for j in range(0, len(Tri), 4096):
            blok = Tri[j : j + 4096]
            dd = _nokta_ucgen(np.repeat(P[q], len(blok), axis=0), np.tile(blok, (len(q), 1, 1)))
            d[q] = np.minimum(d[q], dd.reshape(len(q), len(blok)).min(axis=1))
    return d


def _nokta_ucgen(p: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Nokta–üçgen en kısa uzaklığı (Ericson, Real-Time Collision Detection 5.1.5), satır başına."""
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    ab, ac, ap = b - a, c - a, p - a

    def dot(x, y):
        return np.einsum("ij,ij->i", x, y)

    d1, d2 = dot(ab, ap), dot(ac, ap)
    bp = p - b
    d3, d4 = dot(ab, bp), dot(ac, bp)
    cp = p - c
    d5, d6 = dot(ab, cp), dot(ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    payda = va + vb + vc
    payda = np.where(payda != 0, payda, 1.0)
    v = vb / payda
    w = vc / payda
    q = a + v[:, None] * ab + w[:, None] * ac  # iç bölge
    with np.errstate(divide="ignore", invalid="ignore"):
        t_ab = np.clip(d1 / np.where(d1 - d3 != 0, d1 - d3, 1.0), 0, 1)
        t_ac = np.clip(d2 / np.where(d2 - d6 != 0, d2 - d6, 1.0), 0, 1)
        t_bc = np.clip((d4 - d3) / np.where((d4 - d3) + (d5 - d6) != 0, (d4 - d3) + (d5 - d6), 1.0), 0, 1)
    sec = [
        (d1 <= 0) & (d2 <= 0),
        (d3 >= 0) & (d4 <= d3),
        (d6 >= 0) & (d5 <= d6),
        (vc <= 0) & (d1 >= 0) & (d3 <= 0),
        (vb <= 0) & (d2 >= 0) & (d6 <= 0),
        (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0),
    ]
    sonuc = [a, b, c, a + t_ab[:, None] * ab, a + t_ac[:, None] * ac, b + t_bc[:, None] * (c - b)]
    for s, r in zip(sec[::-1], sonuc[::-1], strict=True):
        q = np.where(s[:, None], r, q)
    return np.linalg.norm(p - q, axis=1)


# ---------------------------------------------------------------- seviyeler ve seçim


def levels(V, T, ratios=(0.5, 0.25, 0.125)) -> list[Level]:
    """Asıl ağ (oran 1, Hausdorff 0) ve her oran için sadeleşmiş seviye, inceden kabaya.

    Her seviye bir öncekinden sadeleştirilir; Hausdorff her zaman asıl ağa göre ölçülür.
    """
    V, T = _ag(V, T)
    r = [float(x) for x in ratios]
    if any(not 0 < x < 1 for x in r) or any(b >= a for a, b in zip([1.0] + r, r, strict=False)):
        raise VizError(f"levels: oranlar (0, 1) içinde ve azalan olmalı ({ratios})")
    sonuc = [Level(V, T, 1.0, 0.0)]
    Vk, Tk = V, T
    for x in r:
        hedef = max(4, round(x * len(T)))
        if hedef < len(Tk):
            Vk, Tk = simplify(Vk, Tk, hedef)
        sonuc.append(Level(Vk, Tk, x, hausdorff(V, T, Vk, Tk)))
    return sonuc


def pick(levels: list[Level], z: float, f: float, s: float, px: float = 1.0) -> int:
    """e_px = d_H · f / (z · s) ≤ px olan en kaba seviyenin indeksi."""
    if not levels:
        raise VizError("pick: seviye listesi boş")
    for ad, v in (("z", z), ("f", f), ("s", s), ("px", px)):
        if not (isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v > 0):
            raise VizError(f"pick: {ad} pozitif ve sonlu olmalı ({ad}={v})")
    secilen = 0
    for i, lv in enumerate(levels):
        if lv.hausdorff * f / (z * s) <= px:
            secilen = i
    return secilen
