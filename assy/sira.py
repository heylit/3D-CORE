"""
Montaj sırası ve demontaj yolu (SPEC 36).

Sökerek montaj: tam montajdan her adımda bir birim, kalan birimlere girmeden tek bir doğrusal ötelemeyle
sökülür; geriye taban kalır. Montaj sırası demontaj sırasının tersidir.
    j, i'yi d yönünde engeller  ⇔  ∃ s > 0 :  V((i + s d) ∩ j) > tol_v
Kaynak: Wilson & Latombe, "Geometric reasoning about mechanical assembly", Artificial Intelligence 71, 1994.

Saf Python + numpy: parça yalnızca Part arayüzünden (bbox, moved, common, volume) kullanılır.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from assy.girisim import world_aabb
from assy.model import Assembly, AssyError, MateKind, Node, RefKind, transform
from assy.tree import validate, walk

if TYPE_CHECKING:
    from geometry.part import Part

DIRECTIONS: tuple[np.ndarray, ...] = tuple(
    np.array(v, dtype=float) for v in [(0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]
)

_SIFIR = 1e-12  # yön bileşeni bundan küçükse 0 sayılır
_AYNI_YON = 1e-9  # 1 − d·d' ≤ bu ise iki yön aynı


@dataclass(frozen=True)
class Step:
    """Montaj sırasında bir adım. Taban: direction None, distance 0, T_out = T."""

    path: str  # birim yolu (SPEC 07 walk biçimi)
    leaves: tuple[str, ...]  # birimdeki yaprak yolları, walk sırasıyla
    direction: np.ndarray | None  # sökme yönü d (birim, dünya); montajda birim −d yönünde gelir
    distance: float  # s_çık, mm
    T: np.ndarray  # birimin yerindeki dünya dönüşümü
    T_out: np.ndarray  # Tr(distance · d) · T


@dataclass
class _Yaprak:
    yol: str
    parca: object  # dünyaya taşınmış Part
    yerel: object  # yerel Part (hareket ettirmek için)
    T: np.ndarray
    lo: np.ndarray
    hi: np.ndarray


@dataclass
class _Birim:
    yol: str
    T: np.ndarray
    yapraklar: list[_Yaprak]
    lo: np.ndarray
    hi: np.ndarray


# ---------- Girdi denetimi ----------


def _pozitif(**degerler: float) -> None:
    for ad, v in degerler.items():
        if not (isinstance(v, (int, float)) and math.isfinite(v) and v > 0):
            raise AssyError(f"{ad} sonlu ve > 0 olmalı ({ad}={v})")


def _negatif_degil(**degerler: float) -> None:
    for ad, v in degerler.items():
        if not (isinstance(v, (int, float)) and math.isfinite(v) and v >= 0):
            raise AssyError(f"{ad} sonlu ve ≥ 0 olmalı ({ad}={v})")


def _tekil_yonler(directions: Iterable) -> list[np.ndarray]:
    """Normlanmış yönler; birbirinin aynısı olanlardan ilk geçen tutulur."""
    yonler: list[np.ndarray] = []
    for v in directions:
        d = np.asarray(v, dtype=float).reshape(-1)
        if d.shape != (3,) or not np.all(np.isfinite(d)):
            raise AssyError(f"Yön sonlu 3 bileşenli vektör olmalı ({v!r})")
        n = float(np.linalg.norm(d))
        if n < _SIFIR:
            raise AssyError(f"Yön vektörü sıfır olamaz ({v!r})")
        d = d / n
        if all(1.0 - float(d @ e) > _AYNI_YON for e in yonler):
            yonler.append(d)
    if not yonler:
        raise AssyError("Yön listesi boş olamaz")
    return yonler


def _altinda(yol: str, onek: str) -> bool:
    return onek == "" or yol == onek or yol.startswith(onek + "/")


def _birimler(
    root: Node, parts: Mapping[str, Part], scope: str, units: str, ignore: Iterable[tuple[str, str]]
) -> tuple[list[_Birim], set[frozenset[str]], list[_Yaprak]]:
    """validate + kapsamdaki birimler (walk sırasıyla), yok sayılan yaprak çiftleri, kapsamdaki yapraklar."""
    validate(root)
    dugumler = {y: (n, T) for y, n, T in walk(root)}
    eksik = sorted({n.part for n, _ in dugumler.values() if n.part is not None} - set(parts))
    if eksik:
        raise AssyError(f"Parça bulunamadı: {eksik}")
    if scope not in dugumler:
        raise AssyError(f"Bilinmeyen scope: '{scope}'")
    kapsam = dugumler[scope][0]
    if kapsam.part is not None:
        raise AssyError(f"scope bir yaprak olamaz: '{scope}'")
    if units not in ("yaprak", "cocuk"):
        raise AssyError(f"units 'yaprak' veya 'cocuk' olmalı ({units!r})")

    yapraklar: list[_Yaprak] = []
    for y, (n, T) in dugumler.items():
        if n.part is None or not _altinda(y, scope) or y == scope:
            continue
        p = parts[n.part]
        lo, hi = world_aabb(p, T)
        yapraklar.append(_Yaprak(y, p.moved(T), p, T, lo, hi))

    if units == "yaprak":
        onekler = [y.yol for y in yapraklar]
    else:
        onekler = [f"{scope}/{c.name}" if scope else c.name for c in kapsam.children]
    birimler = []
    for onek in onekler:
        uyeler = [y for y in yapraklar if _altinda(y.yol, onek)]
        lo = np.min([y.lo for y in uyeler], axis=0)
        hi = np.max([y.hi for y in uyeler], axis=0)
        birimler.append(_Birim(onek, dugumler[onek][1], uyeler, lo, hi))
    if len(birimler) < 2:
        raise AssyError(f"Kapsamda tek birim var, sökülecek bir şey yok (scope='{scope}', units='{units}')")

    yaprak_yollari = {y.yol for y in yapraklar}
    yok_say: set[frozenset[str]] = set()
    for cift in ignore:
        a, b = cift
        if a not in yaprak_yollari or b not in yaprak_yollari:
            raise AssyError(f"ignore: kapsamdaki bir yaprak olmayan yol ({a!r}, {b!r})")
        if a == b:
            raise AssyError(f"ignore: çiftin iki ucu aynı ({a!r})")
        yok_say.add(frozenset((a, b)))
    return birimler, yok_say, yapraklar


# ---------- Engel sınaması ----------


def _pencere(lo_i, hi_i, lo_j, hi_j, d: np.ndarray) -> tuple[float, float] | None:
    """i + s d'nin kutusunun j'ninkiyle her eksende kesin örtüştüğü s aralığının (0, ∞) ile kesişimi."""
    a, b = 0.0, math.inf
    for k in range(3):
        if d[k] > _SIFIR:
            a, b = max(a, (lo_j[k] - hi_i[k]) / d[k]), min(b, (hi_j[k] - lo_i[k]) / d[k])
        elif d[k] < -_SIFIR:
            a, b = max(a, (hi_j[k] - lo_i[k]) / d[k]), min(b, (lo_j[k] - hi_i[k]) / d[k])
        elif not (lo_i[k] < hi_j[k] and hi_i[k] > lo_j[k]):
            return None
    return (a, b) if b > a else None


def _noktalar(a: float, b: float, eps: float, delta: float) -> list[float]:
    """P = sıralı(({ε} ∪ {kδ} ∪ {(a + b)/2}) ∩ (a, b))."""
    P = {eps, (a + b) / 2}
    k = max(1, math.floor(a / delta))
    while k * delta < b:
        P.add(k * delta)
        k += 1
    return sorted(s for s in P if a < s < b)


def _ortusur(lo_a, hi_a, lo_b, hi_b) -> bool:
    return bool(np.all(lo_a < hi_b) and np.all(hi_a > lo_b))


class _Sinayici:
    """(i, j, d) engel sınamaları; her üçlü en çok bir kez hesaplanır."""

    def __init__(self, birimler, yok_say, eps: float, delta: float, tol_v: float) -> None:
        self.birimler = {b.yol: b for b in birimler}
        self.yok_say = yok_say
        self.eps, self.delta, self.tol_v = eps, delta, tol_v
        self.onbellek: dict[tuple[str, str, int], bool] = {}

    def engeller(self, i: str, j: str, k: int, d: np.ndarray) -> bool:
        """j, i'yi d (k. yön) yönünde engelliyor mu?"""
        anahtar = (i, j, k)
        if anahtar not in self.onbellek:
            self.onbellek[anahtar] = self._hesapla(self.birimler[i], self.birimler[j], d)
        return self.onbellek[anahtar]

    def _hesapla(self, bi: _Birim, bj: _Birim, d: np.ndarray) -> bool:
        ciftler = [
            (yi, yj)
            for yi in bi.yapraklar
            for yj in bj.yapraklar
            if frozenset((yi.yol, yj.yol)) not in self.yok_say
        ]
        if not ciftler:
            return False
        pencere = _pencere(bi.lo, bi.hi, bj.lo, bj.hi, d)
        if pencere is None:
            return False
        for s in _noktalar(*pencere, self.eps, self.delta):
            tasinmis: dict[str, object] = {}  # bu s'de ötelenmiş yapraklar
            for yi, yj in ciftler:
                if not _ortusur(yi.lo + s * d, yi.hi + s * d, yj.lo, yj.hi):
                    continue
                if yi.yol not in tasinmis:
                    tasinmis[yi.yol] = yi.yerel.moved(transform(t=s * d) @ yi.T)
                kesisim = tasinmis[yi.yol].common(yj.parca, self.tol_v)
                if kesisim is not None and kesisim.volume > self.tol_v:
                    return True
        return False


def _hazirla(root, parts, directions, scope, units, ignore, step, eps, tol_v):
    yonler = _tekil_yonler(directions)
    if step is not None:
        _pozitif(step=step)
    _pozitif(eps=eps)
    _negatif_degil(tol_v=tol_v)
    birimler, yok_say, yapraklar = _birimler(root, parts, scope, units, ignore)
    if step is None:
        step = min(float(np.min(np.subtract(*reversed(y.yerel.bbox)))) for y in yapraklar)
        _pozitif(step=step)
    return yonler, birimler, _Sinayici(birimler, yok_say, eps, step, tol_v)


# ---------- Arayüz ----------


def sequence(
    root: Node,
    parts: Mapping[str, Part],
    base: str | None = None,
    directions: Sequence = DIRECTIONS,
    *,
    scope: str = "",
    units: str = "yaprak",
    ignore: Iterable[tuple[str, str]] = (),
    step: float | None = None,
    eps: float = 0.01,
    tol_v: float = 1e-6,
    pay: float = 5.0,
) -> list[Step]:
    """Montaj sırası (taban başta). Demontaj sırası: reversed(...)'ın tabandan önceki kısmı."""
    _negatif_degil(pay=pay)
    yonler, birimler, sinayici = _hazirla(root, parts, directions, scope, units, ignore, step, eps, tol_v)
    yollar = [b.yol for b in birimler]
    if base is None:
        base = _hacimce_taban(birimler)
    elif base not in yollar:
        raise AssyError(f"base bir birim değil: '{base}'")

    kalan = list(yollar)
    sokme: list[Step] = []
    while len(kalan) > 1:
        secim = _sokulebilir(kalan, base, yonler, sinayici)
        if secim is None:
            kilitli = [y for y in kalan if y != base]
            raise AssyError(f"Montaj sökülemez; kalan birimler: {kilitli}")
        i, d = secim
        kalan.remove(i)
        bi = sinayici.birimler[i]
        s = _cikis(bi, [sinayici.birimler[j] for j in kalan], d, pay)
        sokme.append(Step(i, _yollar(bi), d.copy(), s, bi.T.copy(), transform(t=s * d) @ bi.T))

    bt = sinayici.birimler[base]
    taban = Step(base, _yollar(bt), None, 0.0, bt.T.copy(), bt.T.copy())
    return [taban, *reversed(sokme)]


def blocking(
    root: Node,
    parts: Mapping[str, Part],
    directions: Sequence = DIRECTIONS,
    *,
    scope: str = "",
    units: str = "yaprak",
    ignore: Iterable[tuple[str, str]] = (),
    step: float | None = None,
    eps: float = 0.01,
    tol_v: float = 1e-6,
) -> list[tuple[np.ndarray, set[tuple[str, str]]]]:
    """Tekilleştirilmiş her yön için (d, {(i, j) : j, i'yi d yönünde engeller})."""
    yonler, birimler, sinayici = _hazirla(root, parts, directions, scope, units, ignore, step, eps, tol_v)
    sonuc = []
    for k, d in enumerate(yonler):
        kenarlar = {
            (bi.yol, bj.yol)
            for bi in birimler
            for bj in birimler
            if bi is not bj and sinayici.engeller(bi.yol, bj.yol, k, d)
        }
        sonuc.append((d.copy(), kenarlar))
    return sonuc


def mate_directions(assy: Assembly) -> list[np.ndarray]:
    """Kısıtlardan aday yönler (dünya): CONCENTRIC ekseni, düzlem–düzlem normali; her biri önce +, sonra −."""
    adaylar: list[np.ndarray] = []
    for m in assy.mates:
        duzlemler = m.a.kind is RefKind.PLANE and m.b.kind is RefKind.PLANE
        if m.kind is MateKind.CONCENTRIC or (
            duzlemler and m.kind in (MateKind.COINCIDENT, MateKind.DISTANCE)
        ):
            _, n = assy.world(m.a)
            adaylar += [n, -n]
    return _tekil_yonler(adaylar) if adaylar else []


# ---------- Yardımcılar ----------


def _yollar(b: _Birim) -> tuple[str, ...]:
    return tuple(y.yol for y in b.yapraklar)


def _hacimce_taban(birimler: list[_Birim]) -> str:
    """Toplam yaprak hacmi en büyük birim; eşitse (rel 1e-9) walk sırasında önce gelen."""
    hacim = [sum(float(y.yerel.volume) for y in b.yapraklar) for b in birimler]
    V_max = max(hacim)
    return next(b.yol for b, V in zip(birimler, hacim, strict=True) if V >= V_max * (1 - 1e-9))


def _sokulebilir(kalan: list[str], base: str, yonler, sinayici: _Sinayici) -> tuple[str, np.ndarray] | None:
    """walk sırasında en sondaki sökülebilir birim ve onu serbest bırakan ilk yön."""
    for i in reversed(kalan):
        if i == base:
            continue
        for k, d in enumerate(yonler):
            if not any(sinayici.engeller(i, j, k, d) for j in kalan if j != i):
                return i, d
    return None


def _cikis(bi: _Birim, digerleri: list[_Birim], d: np.ndarray, pay: float) -> float:
    """s_çık = max(0, min_k s_k): i'nin kutusu kalanların kutusundan bir eksende pay kadar ayrılınca."""
    L = np.min([b.lo for b in digerleri], axis=0)
    H = np.max([b.hi for b in digerleri], axis=0)
    s_k = []
    for k in range(3):
        if d[k] > _SIFIR:
            s_k.append((H[k] + pay - bi.lo[k]) / d[k])
        elif d[k] < -_SIFIR:
            s_k.append((L[k] - pay - bi.hi[k]) / d[k])
    return max(0.0, min(s_k))
