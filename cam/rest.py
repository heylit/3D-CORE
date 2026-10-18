"""
SPEC 03b — Kalan malzeme denetimi ve halka ağacı (D/2 < s ≤ D yan pasolu cep).

Seviye koşulu: düğüm R, adım σ, çocuklar X = R ⊖ B_σ için
    A = R ⊖ B_r  ⊆  Y = X ⊕ B_(r+ε)
Koşul her düğümde sağlanırsa erişilebilir kümenin her noktası bir halkaya ≤ r + ε uzaklıktadır (Önerme 2).
σ ≤ r'de koşul her zaman sağlanır (Önerme 1); koşul σ'da tekdüzedir (Önerme 4), en büyük geçerli adım
ikiye bölmeyle aranır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cam.geom2d import AREA_TOL, LINK_TOL, TOL, intersect
from cam.model import CamError
from cam.offset import _chain, _to_regions, merge_segments, offset, offset_union
from cam.profile import Profile, Region, Segment

COVER_TOL = 1e-7  # mm: ε, kabul edilen en büyük kesilmemiş kalınlık
BISECT_N = 8  # adım küçültmede ikiye bölme sayısı
INRADIUS_TOL = 1e-9  # iç yarıçap ikiye bölme hassasiyeti (D'ye göre)
MIN_EXTRA = 10 * LINK_TOL  # mm: yaprak ek halkasının en küçük ofseti


@dataclass
class RingNode:
    """Halka ağacı düğümü: region sınırı takım merkezi yolu, step üst düğümden ofset (kökte r)."""

    region: Region
    step: float
    children: list[RingNode] = field(default_factory=list)


# ---------------------------------------------------------------- kesin denetim


def _segments(regions: list[Region]) -> list[Segment]:
    return [s for rg in regions for lp in rg.loops for s in lp.segments]


def _inside(p, regions: list[Region]) -> bool:
    return any(rg.contains(p) for rg in regions)


def _pieces(segs: list[Segment], others: list[Segment]) -> list[Segment]:
    """segs parçalarını others ile kesişim noktalarından böler (boyu ≤ LINK_TOL olanlar atılır)."""
    out: list[Segment] = []
    for s in segs:
        ts = [0.0, 1.0]
        for o in others:
            ts.extend(t for t, _ in intersect(s, o))
        ts.sort()
        L = s.length
        for t0, t1 in zip(ts[:-1], ts[1:], strict=True):
            if (t1 - t0) * L > LINK_TOL:
                out.append(s.sub(t0, t1))
    return out


def _check(sigma: float, r: float) -> None:
    if not sigma > 0 or not r > 0:
        raise CamError(f"covered/residue: σ > 0 ve r > 0 olmalı (σ={sigma}, r={r})")


def _sets(region: Region, sigma: float, r: float) -> tuple[list[Region], list[Region]]:
    """A = R ⊖ B_r ve Y = (R ⊖ B_σ) ⊕ B_(r+ε)."""
    A = offset(region, r)
    if not A:
        return [], []
    Y = offset_union(offset(region, sigma), -(r + COVER_TOL))
    return A, Y


def _split(A: list[Region], Y: list[Region]) -> tuple[list[Segment], list[Segment]]:
    """∂A'nın Y dışındaki ve ∂Y'nin A içindeki alt parçaları (A \\ Y'nin sınırı)."""
    a_segs, y_segs = _segments(A), _segments(Y)
    a_out = [s for s in _pieces(a_segs, y_segs) if not _inside(s.point(0.5), Y)]
    y_in = [s for s in _pieces(y_segs, a_segs) if _inside(s.point(0.5), A)]
    return a_out, y_in


def covered(region: Region, sigma: float, r: float) -> bool:
    """Seviye koşulu A ⊆ Y (kesin, örneklemesiz): ∂A Y içinde ve ∂Y'nin hiçbir parçası A içinde değil."""
    _check(sigma, r)
    if sigma <= r + TOL:
        return True  # Önerme 1 (ayrıca σ ≈ r'de Y'nin ofsetinde sıfır yarıçaplı yaylar oluşur)
    A, Y = _sets(region, sigma, r)
    if not A:
        return True
    if not Y:
        return False
    a_out, y_in = _split(A, Y)
    return not a_out and not y_in


def residue(region: Region, sigma: float, r: float) -> list[Region]:
    """A \\ Y bölgeleri; covered(...) ⇔ residue(...) == []."""
    _check(sigma, r)
    if sigma <= r + TOL:
        return []  # Önerme 1
    A, Y = _sets(region, sigma, r)
    if not A:
        return []
    if not Y:
        return A
    a_out, y_in = _split(A, Y)
    # A \ Y'nin içi ∂A'nın solunda, Y'nin dışında: ∂Y parçaları ters yönde
    pieces = a_out + [s.reversed() for s in y_in]
    loops = []
    for chain in _chain(pieces):
        p = Profile(merge_segments(chain))
        if abs(p.area) > AREA_TOL:
            loops.append(p)
    return _to_regions(loops)


# ---------------------------------------------------------------- halka ağacı


def _inradius(region: Region, hi: float, tol: float) -> float:
    """offset(region, t) boşalan en küçük t'nin üst sınırı (ikiye bölme). offset(region, hi) boş olmalı."""
    lo = 0.0
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if offset(region, mid):
            lo = mid
        else:
            hi = mid
    return hi


def _leaf_extra(region: Region, r: float, s: float) -> list[RingNode]:
    """SPEC 03 yaprak kuralı: iç yarıçap t* > r ise t* − r adımlı ek halka(lar); onlar işlenmez."""
    t_star = _inradius(region, s, INRADIUS_TOL * 2 * r)
    if t_star - r <= TOL:
        return []
    # LINK_TOL: ikiye bölmenin erken "boş" demesine karşı pay. En az MIN_EXTRA: ofset budaması
    # KEEP_TOL ölçeğindeki d'de kararsız (t* ≈ r olan dar dikdörtgende halka kapanmıyordu).
    t_extra = max(t_star - r + LINK_TOL, MIN_EXTRA)
    return [RingNode(c, t_extra) for c in offset(region, t_extra)]


def _step(region: Region, r: float, s: float) -> tuple[float, list[Region]]:
    """Düğümün adımı ve çocuk bölgeleri; çocuk yoksa (yaprak) ([], s)."""
    X = offset(region, s)
    if s <= r + TOL or not X or covered(region, s, r):
        return s, X
    lo, hi = r, s  # lo Önerme 1 ile geçerli
    for _ in range(BISECT_N):
        m = 0.5 * (lo + hi)
        if covered(region, m, r):
            lo = m
        else:
            hi = m
    return lo, offset(region, lo)


def _node(region: Region, step: float, r: float, s: float) -> RingNode:
    node = RingNode(region, step)
    sigma, X = _step(region, r, s)
    if X:
        node.children = [_node(c, sigma, r, s) for c in X]
    else:
        node.children = _leaf_extra(region, r, s)
    return node


def ring_tree(region: Region, r: float, s: float) -> list[RingNode]:
    """Kökler Ω ⊖ B_r bileşenleri; her düğümde adım s ya da ikiye bölmeyle küçültülmüş adım."""
    if not r > 0:
        raise CamError(f"ring_tree: r > 0 olmalı (r={r})")
    if not 0 < s <= 2 * r + TOL:
        raise CamError(f"ring_tree: yan paso 0 < s ≤ 2r olmalı (s={s}, r={r})")
    return [_node(rg, r, r, s) for rg in offset(region, r)]
