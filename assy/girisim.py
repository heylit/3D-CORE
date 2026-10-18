"""
Montajda girişim, temas ve boşluk kontrolü (SPEC 09).

Her yaprak çifti için önce kesişim hacmi V∩, sonra sınırlar arası uzaklık d:
    V∩ > tol_v                → GIRISIM
    d ≤ tol_d                 → TEMAS
    tol_d < d < clearance     → DAR
    aksi halde                → serbest (raporlanmaz)
Kaba eleme: taşınmış AABB'ler x eksenine göre sıralanıp süpürülür (Ericson, Real-Time Collision
Detection, Bölüm 7.5).

Saf Python + numpy: parça yalnızca Part arayüzünden (bbox, moved, common, distance, volume,
center_of_mass) kullanılır.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np

from assy.model import AssyError, Node
from assy.tree import validate, walk

if TYPE_CHECKING:
    from geometry.part import Part


class ClashKind(StrEnum):
    GIRISIM = "girisim"
    TEMAS = "temas"
    DAR = "dar"


@dataclass(frozen=True)
class Clash:
    a: str  # yaprak yolu (SPEC 07 walk biçimi), walk sırasında önce gelen
    b: str
    kind: ClashKind
    volume: float  # mm³; GIRISIM dışında 0
    distance: float  # mm; GIRISIM'de 0
    center: np.ndarray | None  # GIRISIM: kesişimin ağırlık merkezi (dünya); diğerleri None
    points: tuple[np.ndarray, np.ndarray] | None  # TEMAS / DAR: en yakın noktalar (dünya, a'da, b'de)


def world_aabb(part: Part, T: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Yerel bbox'ın 8 köşesi T ile taşınıp min / max alınmış dünya kutusu (gerçek şekli her zaman içerir)."""
    lo, hi = (np.asarray(v, dtype=float) for v in part.bbox)
    kose = np.array(
        [[(lo, hi)[i][0], (lo, hi)[j][1], (lo, hi)[k][2]] for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    )
    T = np.asarray(T, dtype=float)
    kose = kose @ T[:3, :3].T + T[:3, 3]
    return kose.min(axis=0), kose.max(axis=0)


def _negatif_degil(**degerler: float) -> None:
    for ad, v in degerler.items():
        if not (math.isfinite(v) and v >= 0):
            raise AssyError(f"{ad} sonlu ve ≥ 0 olmalı ({ad}={v})")


def _yapraklar(root: Node, parts: Mapping[str, Part]) -> list[tuple[str, Node, np.ndarray]]:
    """validate + walk sırasıyla (yol, yaprak, T_dünya); ağaçtaki her parça kimliği parts'ta olmalı."""
    validate(root)
    yapraklar = [(y, n, T) for y, n, T in walk(root) if n.part is not None]
    eksik = sorted({n.part for _, n, _ in yapraklar} - set(parts))
    if eksik:
        raise AssyError(f"Parça bulunamadı: {eksik}")
    return yapraklar


def _kapsam(yapraklar, dugumler: dict[str, Node], scope: str, across: bool) -> list[tuple[int, str | None]]:
    """scope altındaki yaprakların indisleri ve (across için) scope'un hangi doğrudan çocuğunda oldukları."""
    if scope not in dugumler:
        raise AssyError(f"Bilinmeyen scope: '{scope}'")
    if dugumler[scope].part is not None:
        raise AssyError(f"scope bir yaprak olamaz: '{scope}'")
    if across and len(dugumler[scope].children) < 2:
        raise AssyError(f"across=True için scope '{scope}' en az iki çocuklu olmalı")
    on = f"{scope}/" if scope else ""
    secilen = []
    for i, (y, _, _) in enumerate(yapraklar):
        if y.startswith(on):
            secilen.append((i, y[len(on) :].split("/")[0]))
    return secilen


def _adaylar(
    kutular: list[tuple[np.ndarray, np.ndarray]], esik_c: float, tol_d: float
) -> list[tuple[int, int]]:
    """Sort and sweep (x ekseni): kutu boşluğu g < esik_c veya g ≤ tol_d olan çiftler (i < j)."""
    sira = sorted(range(len(kutular)), key=lambda i: kutular[i][0][0])
    ciftler = []
    for s, i in enumerate(sira):
        lo_i, hi_i = kutular[i]
        for j in sira[s + 1 :]:
            lo_j, hi_j = kutular[j]
            gx = lo_j[0] - hi_i[0]
            if gx >= esik_c and gx > tol_d:
                break  # x'e göre sıralı: sonrakiler daha da uzakta
            g = float(np.linalg.norm(np.maximum(0.0, np.maximum(lo_j - hi_i, lo_i - hi_j))))
            if g < esik_c or g <= tol_d:
                ciftler.append((min(i, j), max(i, j)))
    return sorted(ciftler)


def _sinifla(a: str, b: str, pa, pb, clearance: float, tol_v: float, tol_d: float) -> Clash | None:
    """Teori tablosu: önce hacim, sonra sınırlar arası uzaklık."""
    k = pa.common(pb, tol_v)
    if k is not None and k.volume > tol_v:
        merkez = np.array(k.center_of_mass, dtype=float)
        return Clash(a, b, ClashKind.GIRISIM, float(k.volume), 0.0, merkez, None)
    d, p, q = pa.distance(pb)
    nokta = (np.array(p, dtype=float), np.array(q, dtype=float))
    if d <= tol_d:
        return Clash(a, b, ClashKind.TEMAS, 0.0, float(d), None, nokta)
    if d < clearance:
        return Clash(a, b, ClashKind.DAR, 0.0, float(d), None, nokta)
    return None


def check(
    root: Node,
    parts: Mapping[str, Part],
    clearance: float = 0.0,
    tol_v: float = 1e-6,
    tol_d: float = 1e-6,
    scope: str = "",
    across: bool = False,
    ignore: Iterable[tuple[str, str]] = (),
) -> list[Clash]:
    """scope altındaki yaprak çiftlerinde girişim / temas / dar boşluk listesi (walk sırasıyla)."""
    _negatif_degil(clearance=clearance, tol_v=tol_v, tol_d=tol_d)
    yapraklar = _yapraklar(root, parts)
    dugumler = {y: n for y, n, _ in walk(root)}
    yollar = {y for y, _, _ in yapraklar}
    atla = set()
    for cift in ignore:
        a, b = cift
        bilinmeyen = sorted({a, b} - yollar)
        if bilinmeyen:
            raise AssyError(f"ignore içinde yaprak olmayan yol: {bilinmeyen}")
        atla.add(frozenset((a, b)))
    secilen = _kapsam(yapraklar, dugumler, scope, across)

    kutular = [world_aabb(parts[yapraklar[i][1].part], yapraklar[i][2]) for i, _ in secilen]
    tasinmis: dict[int, Part] = {}

    def dunya(k: int) -> Part:
        i = secilen[k][0]
        if i not in tasinmis:
            _, n, T = yapraklar[i]
            tasinmis[i] = parts[n.part].moved(T)
        return tasinmis[i]

    sonuc = []
    for ka, kb in _adaylar(kutular, clearance, tol_d):
        a, b = yapraklar[secilen[ka][0]][0], yapraklar[secilen[kb][0]][0]
        if across and secilen[ka][1] == secilen[kb][1]:
            continue
        if frozenset((a, b)) in atla:
            continue
        c = _sinifla(a, b, dunya(ka), dunya(kb), clearance, tol_v, tol_d)
        if c is not None:
            sonuc.append(c)
    return sonuc


def gap(root: Node, parts: Mapping[str, Part], a: str, b: str) -> tuple[float, np.ndarray, np.ndarray]:
    """İki yaprak arasında dünya koordinatında en küçük uzaklık ve en yakın noktalar (kaba eleme yok)."""
    yapraklar = {y: (n, T) for y, n, T in _yapraklar(root, parts)}
    bilinmeyen = sorted({a, b} - yapraklar.keys())
    if bilinmeyen:
        raise AssyError(f"gap: yaprak olmayan yol: {bilinmeyen}")
    if a == b:
        raise AssyError(f"gap: iki uç aynı yaprak ('{a}')")
    (na, Ta), (nb, Tb) = yapraklar[a], yapraklar[b]
    d, p, q = parts[na.part].moved(Ta).distance(parts[nb.part].moved(Tb))
    return float(d), np.array(p, dtype=float), np.array(q, dtype=float)
