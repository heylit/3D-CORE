"""Kenar sınıflama, birleştirme, görünen/gizli önceliği (SPEC 16). Saf numpy.

HLR'nin ham çıktısı teknik resme uygun değildir: üst ve alt yüz kenarları üst görünüşte üst üste düşer,
izdüşen daireler dejenere B-spline doğru olarak gelir. Burada:
1. sınıflama: örnek noktalar → doğru / yay / çoklu çizgi,
2. birleştirme: aynı doğru (çember) üzerindeki parçalar 1D aralık (açı aralığı) olarak birleşir,
3. öncelik: gizli aralıklardan görünen aralıklar çıkarılır (H ← H ∖ V).
"""

from __future__ import annotations

import math

import numpy as np

from geometry.drawing.types import Arc2D, Entity, Line2D, Polyline2D, Text2D
from geometry.part import GeometryError

Aralik = tuple[float, float]


# ---------- 1. sınıflama ----------


def _dogru_mu(P: np.ndarray, tol_s: float) -> tuple[np.ndarray, np.ndarray] | None:
    """Noktalar tek doğru üzerindeyse uç noktalar (asal yön boyunca en uzak iki nokta), değilse None."""
    m = P.mean(axis=0)
    Q = P - m
    _, sv, Vt = np.linalg.svd(Q, full_matrices=False)
    if sv[0] <= tol_s:
        return None  # tek nokta: boy yok
    d = Vt[0]
    n = np.array([-d[1], d[0]])
    if np.abs(Q @ n).max() > tol_s:
        return None
    s = Q @ d
    return m + s.min() * d, m + s.max() * d


def _cember_mi(P: np.ndarray, tol_s: float) -> tuple[np.ndarray, float] | None:
    """Kåsa yöntemi: x² + y² + D x + E y + F = 0 en küçük kareler; tüm noktalar |‖p − c‖ − r| ≤ tol_s."""
    if len(P) < 3:
        return None
    A = np.column_stack([P[:, 0], P[:, 1], np.ones(len(P))])
    b = -(P[:, 0] ** 2 + P[:, 1] ** 2)
    (D, E, F), *_ = np.linalg.lstsq(A, b, rcond=None)
    c = np.array([-D / 2.0, -E / 2.0])
    r2 = c @ c - F
    if not r2 > 0:
        return None
    r = math.sqrt(r2)
    if np.abs(np.linalg.norm(P - c, axis=1) - r).max() > tol_s:
        return None
    return c, r


def _yay_acilari(P: np.ndarray, c: np.ndarray, r: float, tol_s: float) -> tuple[float, float]:
    """Sıralı noktalardan CCW (a0, a1), derece. Kapalıysa tam çember."""
    if np.linalg.norm(P[0] - P[-1]) <= tol_s:
        a0 = math.degrees(math.atan2(*(P[0] - c)[::-1]))
        return a0, a0 + 360.0
    th = np.unwrap(np.arctan2(P[:, 1] - c[1], P[:, 0] - c[0]))
    t0, t1 = math.degrees(th[0]), math.degrees(th[-1])
    if t1 < t0:  # CW gidiyor: ters çevir
        t0, t1 = t1, t0
    return t0, t1


def classify(P: np.ndarray, tol_s: float = 1e-6) -> Line2D | Arc2D | Polyline2D:
    """Örnek noktalardan (k, 2) doğru / yay / çoklu çizgi sınıflaması (katman: GORUNUR)."""
    P = np.asarray(P, dtype=float)
    if P.ndim != 2 or P.shape[1] != 2 or len(P) < 2 or not np.isfinite(P).all():
        raise GeometryError("classify: en az iki sonlu (x, y) noktası gerekli")
    uc = _dogru_mu(P, tol_s)
    if uc is not None:
        return Line2D(uc[0], uc[1], "GORUNUR")
    cem = _cember_mi(P, tol_s)
    if cem is not None:
        c, r = cem
        a0, a1 = _yay_acilari(P, c, r, tol_s)
        return Arc2D(c, r, a0, a1, "GORUNUR")
    return Polyline2D(P.copy(), "GORUNUR")


# ---------- 2. aralık cebiri ----------


def _birlesim(araliklar: list[Aralik], tol: float) -> list[Aralik]:
    """Örtüşen veya değen (tol içinde) aralıkları birleştirir."""
    out: list[list[float]] = []
    for a, b in sorted(araliklar):
        if out and a <= out[-1][1] + tol:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _fark(H: list[Aralik], V: list[Aralik], tol: float) -> list[Aralik]:
    """H ∖ V (ikisi de birleşmiş); boyu tol'dan kısa kalan parçalar atılır."""
    out = []
    for a, b in H:
        parcalar = [(a, b)]
        for c, d in V:
            yeni = []
            for p, q in parcalar:
                if d <= p or c >= q:
                    yeni.append((p, q))
                    continue
                if c > p:
                    yeni.append((p, c))
                if d < q:
                    yeni.append((d, q))
            parcalar = yeni
        out += [(p, q) for p, q in parcalar if q - p > tol]
    return out


# ---------- 3. doğru ve çember grupları ----------


def _dogru_anahtari(L: Line2D) -> tuple[np.ndarray, float, float, float] | None:
    """(d, c, s0, s1): yön d (işareti sabit), doğruya uzaklık c = n·p, doğru üzerindeki aralık [s0, s1]."""
    v = L.p1 - L.p0
    boy = float(np.linalg.norm(v))
    if boy == 0.0:
        return None
    d = v / boy
    if d[0] < -1e-12 or (abs(d[0]) <= 1e-12 and d[1] < 0):
        d = -d
    n = np.array([-d[1], d[0]])
    s = sorted([float(L.p0 @ d), float(L.p1 @ d)])
    return d, float(L.p0 @ n), s[0], s[1]


class _DogruGrubu:
    def __init__(self, d: np.ndarray, c: float) -> None:
        self.d, self.c = d, c
        self.V: list[Aralik] = []
        self.H: list[Aralik] = []

    def ayni_mi(self, d: np.ndarray, c: float, tol_s: float) -> bool:
        capraz = abs(self.d[0] * d[1] - self.d[1] * d[0])
        return capraz <= 1e-9 and abs(self.c - c) <= tol_s

    def cizgiler(self, araliklar: list[Aralik], layer: str) -> list[Line2D]:
        n = np.array([-self.d[1], self.d[0]])
        return [Line2D(self.c * n + a * self.d, self.c * n + b * self.d, layer) for a, b in araliklar]


class _CemberGrubu:
    def __init__(self, c: np.ndarray, r: float) -> None:
        self.c, self.r = c, r
        self.V: list[Aralik] = []
        self.H: list[Aralik] = []

    def ayni_mi(self, c: np.ndarray, r: float, tol_s: float) -> bool:
        return float(np.linalg.norm(self.c - c)) <= tol_s and abs(self.r - r) <= tol_s


def _aci_parcalari(a0: float, a1: float) -> list[Aralik]:
    """[a0, a1] açı aralığını [0, 360] içinde en çok iki parçaya böler."""
    if a1 - a0 >= 360.0:
        return [(0.0, 360.0)]
    b0 = a0 % 360.0
    b1 = b0 + (a1 - a0)
    if b1 <= 360.0:
        return [(b0, b1)]
    return [(b0, 360.0), (0.0, b1 - 360.0)]


def _yaylar(grup: _CemberGrubu, araliklar: list[Aralik], layer: str, tol_a: float) -> list[Arc2D]:
    """[0, 360] parçalarını yaylara çevirir; 360'ta biten ve 0'dan başlayan parça tek yay olur."""
    if not araliklar:
        return []
    if len(araliklar) == 1 and araliklar[0][1] - araliklar[0][0] >= 360.0 - tol_a:
        return [Arc2D(grup.c, grup.r, 0.0, 360.0, layer)]
    araliklar = list(araliklar)
    if len(araliklar) > 1 and araliklar[0][0] <= tol_a and araliklar[-1][1] >= 360.0 - tol_a:
        ilk, son = araliklar.pop(0), araliklar.pop()
        araliklar.append((son[0], ilk[1] + 360.0))
    return [Arc2D(grup.c, grup.r, a, b, layer) for a, b in araliklar]


def clean_edges(visible: list[Entity], hidden: list[Entity], tol_s: float = 1e-6) -> list[Entity]:
    """Ham kenarları birleştirir, gizliden görüneni çıkarır (GORUNUR / GIZLI katmanlı çıktı)."""
    dogrular: list[_DogruGrubu] = []
    cemberler: list[_CemberGrubu] = []
    cokluler: dict[str, list[Polyline2D]] = {"GORUNUR": [], "GIZLI": []}

    def ekle(e: Entity, gorunur: bool) -> None:
        if isinstance(e, Polyline2D):
            ciz = classify(e.P, tol_s)
            if not isinstance(ciz, Polyline2D):
                ekle(ciz, gorunur)
            else:
                cokluler["GORUNUR" if gorunur else "GIZLI"].append(ciz)
            return
        if isinstance(e, Line2D):
            k = _dogru_anahtari(e)
            if k is None or k[3] - k[2] <= tol_s:
                return
            d, c, s0, s1 = k
            g = next((g for g in dogrular if g.ayni_mi(d, c, tol_s)), None)
            if g is None:
                g = _DogruGrubu(d, c)
                dogrular.append(g)
            (g.V if gorunur else g.H).append((s0, s1))
            return
        if isinstance(e, Arc2D):
            g = next((g for g in cemberler if g.ayni_mi(e.c, e.r, tol_s)), None)
            if g is None:
                g = _CemberGrubu(np.asarray(e.c, dtype=float), float(e.r))
                cemberler.append(g)
            (g.V if gorunur else g.H).extend(_aci_parcalari(e.a0, e.a1))
            return
        if isinstance(e, Text2D):
            raise GeometryError("clean_edges: yazı kenar değildir")
        raise GeometryError(f"clean_edges: bilinmeyen varlık {type(e).__name__}")

    for e in visible:
        ekle(e, True)
    for e in hidden:
        ekle(e, False)

    out: list[Entity] = []
    for g in dogrular:
        V = _birlesim(g.V, tol_s)
        H = _fark(_birlesim(g.H, tol_s), V, tol_s)
        out += g.cizgiler(V, "GORUNUR") + g.cizgiler(H, "GIZLI")
    for g in cemberler:
        tol_a = math.degrees(tol_s / g.r)
        V = _birlesim(g.V, tol_a)
        H = _fark(_birlesim(g.H, tol_a), V, tol_a)
        out += _yaylar(g, V, "GORUNUR", tol_a) + _yaylar(g, H, "GIZLI", tol_a)
    out += _tekil_cokluler(cokluler["GORUNUR"], [], tol_s, "GORUNUR")
    out += _tekil_cokluler(cokluler["GIZLI"], cokluler["GORUNUR"], tol_s, "GIZLI")
    return out


def _ayni_cizgi(A: np.ndarray, B: np.ndarray, tol_s: float) -> bool:
    if A.shape != B.shape:
        return False
    return bool(np.abs(A - B).max() <= tol_s or np.abs(A - B[::-1]).max() <= tol_s)


def _tekil_cokluler(
    L: list[Polyline2D], ortu: list[Polyline2D], tol_s: float, layer: str
) -> list[Polyline2D]:
    """Aynı çoklu çizgiyi bir kez tutar; ortu listesinde olanları atar (genel eğride parça çıkarma yok)."""
    out: list[Polyline2D] = []
    for p in L:
        if any(_ayni_cizgi(p.P, q.P, tol_s) for q in ortu + out):
            continue
        out.append(Polyline2D(p.P, layer))
    return out


def total_length(edges: list[Entity], layer: str) -> float:
    """Katmandaki toplam boy (yay boyu r·Δθ)."""
    L = 0.0
    for e in edges:
        if getattr(e, "layer", None) != layer:
            continue
        if isinstance(e, Line2D):
            L += float(np.linalg.norm(np.asarray(e.p1) - np.asarray(e.p0)))
        elif isinstance(e, Arc2D):
            L += e.r * math.radians(e.a1 - e.a0)
        elif isinstance(e, Polyline2D):
            L += float(np.linalg.norm(np.diff(e.P, axis=0), axis=1).sum())
    return L
