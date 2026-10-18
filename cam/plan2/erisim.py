"""SPEC 57 §2–3 — Aday erişim yönleri, yön başına üstten erişilebilir özellikler, ulaşılabilen yönler.

Erişim: parça sınır kutusundan parça çıkarılır; kalan her bağlı bölge (cep, kanal, delik, basamak) ayrı
değerlendirilir. Bölge `d` yönünden erişilebilir ⇔ (i) yerel çerçevede ayak izinin üstündeki sütunda parça
malzemesi yok, (ii) bölge tek başına bir kutudan çıkarıldığında SPEC 27 `recognize` onu tanıyor (2.5D).
Delikler `Part.holes` kayıtlarından gelir (aday yön = −eksen). Stok parçadan büyükse ana yönlerdeki fazla
yüz alma özelliğidir. Bölge, delik ve yüz anahtarları dünyadadır: aynı özellik iki kez işlenmez.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from cam.features import FaceFeature, Features, HoleFeature, recognize
from cam.model import CamError, Frame, MachineProfile, Stock
from cam.multiaxis.indexed import from_normal, local_stock
from cam.profile import Profile
from geometry.part import GeometryError, Hole, Part

ANA = (
    np.array([1.0, 0.0, 0.0]),
    np.array([-1.0, 0.0, 0.0]),
    np.array([0.0, 1.0, 0.0]),
    np.array([0.0, -1.0, 0.0]),
    np.array([0.0, 0.0, 1.0]),
    np.array([0.0, 0.0, -1.0]),
)
COS_TOL = 1e-9  # yön eşitliği (kosinüs)
MARJ = 2.0  # mm: tanıma kutusunun bölge çevresindeki payı
V_TOL = 1e-3  # mm³: sütunda bundan küçük kesişim erişimi engellemez
DELIK_PAY = 0.05  # bağıl: saf delik bölgesi hacim payı


# ---------------------------------------------------------------- aday yönler


def _aci(u: np.ndarray, v: np.ndarray) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, float(u @ v)))))


def _birim(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    if v.shape != (3,) or not math.isfinite(n) or n < 1e-12:
        raise CamError(f"Erişim: yön sonlu, sıfırdan farklı (3,) vektör olmalı ({v!r})")
    return v / n


def _ang_tol(ang_tol) -> float:
    if isinstance(ang_tol, bool) or not isinstance(ang_tol, (int, float)) or not 0 <= ang_tol < 90:
        raise CamError(f"Erişim: ang_tol [0°, 90°) aralığında olmalı ({ang_tol!r})")
    return float(ang_tol)


def candidate_directions(part: Part, ang_tol: float = 0.5) -> tuple[np.ndarray, ...]:
    """±X, ±Y, ±Z ∪ düzlemsel yüz normalleri ∪ delik eksenleri, `ang_tol` derece ile kümelenmiş.

    Sıra: ana yönler, sonra yüz sırasıyla normaller, sonra delik kayıtları; küme temsilcisi ilk gelen yön.
    """
    if not isinstance(part, Part):
        raise CamError(f"Erişim: Part bekleniyor ({type(part).__name__})")
    tol = _ang_tol(ang_tol)
    try:
        yuzler = part.planar_faces()
    except GeometryError as e:
        raise CamError(str(e)) from e
    adaylar = [d.copy() for d in ANA]
    adaylar += [_birim(f.normal) for f in yuzler]
    adaylar += [_birim(-np.asarray(h.axis, dtype=float)) for h in part.holes]
    out: list[np.ndarray] = []
    for d in adaylar:
        if not any(_aci(d, r) <= tol + 1e-12 for r in out):
            out.append(d)
    return tuple(out)


# ---------------------------------------------------------------- çerçeveler


def frame_for(d, o=(0.0, 0.0, 0.0)) -> Frame:
    """Yön `d` için yerel çerçeve: z = d, x ipucu +X (d ≈ ±X ise +Y)."""
    d = _birim(d)
    x_hint = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)
    return from_normal(o, d, x_hint)


def to_local(frame: Frame) -> np.ndarray:
    """Dünya → yerel rijit dönüşüm (4×4): p_l = Rᵀ (p − o)."""
    R = np.array(frame.R)
    T = np.eye(4)
    T[:3, :3] = R.T
    T[:3, 3] = -R.T @ np.array(frame.origin)
    return T


def _kutu(lo, hi, name: str) -> Part:
    """Eksenlere hizalı kutu parça (Part kurucusuna build123d katısı verilir)."""
    import build123d as bd  # geç içe aktarma: OCCT yalnız erişim hesabında gerekir

    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    L = hi - lo
    kutu = bd.Pos(*lo) * bd.Box(*L, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    return Part(kutu, name=name)


def _parcalar(p: Part | None) -> list[Part]:
    if p is None:
        return []
    katilar = list(p.shape.solids())
    if len(katilar) <= 1:
        return [p]
    return [Part(s, name=f"{p.name}-{i}") for i, s in enumerate(katilar)]


def _kose(lo, hi) -> np.ndarray:
    return np.array(list(itertools.product(*zip(lo, hi, strict=True))), dtype=float)


# ---------------------------------------------------------------- erişim çözümlemesi


@dataclass(frozen=True)
class Item:
    """Bir yönden erişilen özellik birimi: anahtar (dünya kimliği) ve yerel özellikleri."""

    key: tuple
    features: Features  # yerel çerçevede
    z_low: np.ndarray  # dünyada en alt nokta adayları (çene engeli için köşeler / delik noktaları), (k, 3)


class Access:
    """Parça + stok için bölgeler ve yön başına erişim (önbellekli)."""

    def __init__(self, part: Part, stock: Stock, tol: float = 1e-3, hole_d_max: float = 20.0) -> None:
        if not isinstance(part, Part):
            raise CamError(f"Erişim: Part bekleniyor ({type(part).__name__})")
        if not isinstance(stock, Stock):
            raise CamError(f"Erişim: kutu stok (Stock) bekleniyor ({type(stock).__name__})")
        self.part = part
        self.stock = stock
        self.tol = float(tol)
        self.hole_d_max = float(hole_d_max)
        lo, hi = (np.asarray(v, dtype=float) for v in part.bbox)
        self.lo, self.hi = lo, hi
        try:
            kutu = _kutu(lo, hi, "zarf")
            self.regions = [r for r in _parcalar(kutu.cut(part)) if r.volume > V_TOL]
        except GeometryError as e:
            raise CamError(f"Erişim: bölge ayrıştırması başarısız ({e})") from e
        self.holes = tuple(part.holes)
        self._delik_bolgesi = [self._saf_delik(r) for r in self.regions]
        self._cache: dict[tuple, list[Item]] = {}

    def _saf_delik(self, r: Part) -> bool:
        """Bölge yalnız bir kayıtlı delikten mi oluşuyor (hacmi π r² t, orta noktası kutusunda)?"""
        lo, hi = r.bbox
        for h in self.holes:
            m = np.asarray(h.origin) + np.asarray(h.axis) * h.depth / 2
            V = math.pi * h.d**2 / 4 * h.depth
            icinde = bool(np.all(m >= np.asarray(lo) - 1e-6) and np.all(m <= np.asarray(hi) + 1e-6))
            if icinde and abs(r.volume - V) <= DELIK_PAY * V + 1e-6:
                return True
        return False

    # ------------------------------------------------ yön başına

    def items(self, d) -> list[Item]:
        """`d` yönünden erişilen özellik birimleri (yerel çerçeve `frame_for(d)`)."""
        d = _birim(d)
        k = tuple(np.round(d, 12))
        if k not in self._cache:
            self._cache[k] = self._items(d)
        return self._cache[k]

    def _items(self, d: np.ndarray) -> list[Item]:
        F = frame_for(d)
        T = to_local(F)
        out: list[Item] = []
        out += self._yuz(d, F)
        parca_l = None
        for i, r in enumerate(self.regions):
            if self._delik_bolgesi[i]:
                continue
            if parca_l is None:
                parca_l = self.part.moved(T)
            feats = self._bolge(r.moved(T), parca_l)
            if feats is not None:
                lo, hi = r.bbox
                out.append(Item(("bolge", i), feats, _kose(lo, hi)))
        out += self._delikler(d, F)
        return out

    def _yuz(self, d: np.ndarray, F: Frame) -> list[Item]:
        """Ana yönde stok fazlası → yüz alma (stok üstünden parça üstüne)."""
        for k, a in enumerate(ANA):
            if float(d @ a) >= 1 - COS_TOL:
                ax = k // 2
                ust = (self.stock.xmax, self.stock.ymax, self.stock.zmax)[ax] - self.hi[ax]
                alt = self.lo[ax] - (self.stock.xmin, self.stock.ymin, self.stock.zmin)[ax]
                derin = ust if k % 2 == 0 else alt
                if derin <= self.tol:
                    return []
                yerel = local_stock(self.stock, F)
                z = yerel.zmax - derin
                sinir = Profile.rectangle(
                    yerel.xmin, yerel.ymin, yerel.xmax - yerel.xmin, yerel.ymax - yerel.ymin
                )
                ff = Features(
                    faces=(FaceFeature(z=z, depth=derin, boundary=sinir),), pockets=(), opens=(), holes=()
                )
                lo = self.lo.copy()
                hi = self.hi.copy()
                if k % 2 == 0:
                    lo[ax] = hi[ax]
                else:
                    hi[ax] = lo[ax]
                return [Item(("yuz", k), ff, _kose(lo, hi))]
        return []

    def _bolge(self, r_l: Part, parca_l: Part) -> Features | None:
        """Yerel çerçevede bölge erişilebilir ve 2.5D ise SPEC 27 özellikleri (delik hariç), yoksa None."""
        lo, hi = (np.asarray(v, dtype=float) for v in r_l.bbox)
        H = float(np.linalg.norm(self.hi - self.lo)) + 10.0
        try:
            sutun = _kutu((lo[0], lo[1], hi[2] + 10 * self.tol), (hi[0], hi[1], hi[2] + H), "sutun")
            if parca_l.common(sutun, tol_v=V_TOL) is not None:
                return None  # üstü kapalı: ustten_erisilemez (SPEC 29)
            B_lo = np.array([lo[0] - MARJ, lo[1] - MARJ, lo[2] - MARJ])
            B_hi = np.array([hi[0] + MARJ, hi[1] + MARJ, hi[2]])
            Q = _kutu(B_lo, B_hi, "tanima").cut(r_l)
            F = recognize(Q, Stock(*B_lo, *B_hi), tol=self.tol, hole_d_max=self.hole_d_max)
        except (CamError, GeometryError):
            return None  # 2.5D değil ya da tanınamıyor
        if not F.pockets and not F.opens and not F.faces:
            return None
        return Features(faces=F.faces, pockets=F.pockets, opens=F.opens, holes=())

    def _delikler(self, d: np.ndarray, F: Frame) -> list[Item]:
        out = []
        for j, h in enumerate(self.holes):
            a = np.asarray(h.axis, dtype=float)
            if float(-a @ d) < 1 - COS_TOL:
                continue
            yerel = dataclasses.replace(
                h,
                origin=F.to_local(np.asarray(h.origin, dtype=float)),
                axis=np.array([0.0, 0.0, -1.0]),
            )
            ff = Features(faces=(), pockets=(), opens=(), holes=(HoleFeature(yerel, "kayit"),))
            out.append(Item(("delik", j), ff, _delik_noktalari(h)))
        return out


def _delik_noktalari(h: Hole) -> np.ndarray:
    """Delik giriş ve dip çemberlerinden örnek noktalar (dünya)."""
    a = np.asarray(h.axis, dtype=float)
    u = np.cross(a, [1.0, 0.0, 0.0] if abs(a[0]) < 0.9 else [0.0, 1.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(a, u)
    o = np.asarray(h.origin, dtype=float)
    pts = []
    for t in (0.0, h.depth):
        for k in range(8):
            phi = k * math.pi / 4
            pts.append(o + a * t + h.d / 2 * (math.cos(phi) * u + math.sin(phi) * v))
    return np.array(pts)


def accessible(part: Part, d, stock: Stock, tol: float = 1e-3, hole_d_max: float = 20.0) -> Features:
    """`d` yönüne bakan yerel çerçevede (`frame_for(d)`) tanınan, üstten erişilebilir özellikler."""
    items = Access(part, stock, tol, hole_d_max).items(d)
    return merge_features([it.features for it in items])


def merge_features(fs: list[Features]) -> Features:
    return Features(
        faces=tuple(f for F in fs for f in F.faces),
        pockets=tuple(p for F in fs for p in F.pockets),
        opens=tuple(o for F in fs for o in F.opens),
        holes=tuple(h for F in fs for h in F.holes),
    )


# ---------------------------------------------------------------- ulaşılabilen yönler (§3)


def _tilt_limit(ax) -> float:
    if ax.min is None and ax.max is None:
        return 180.0
    return max(abs(float(ax.min)), abs(float(ax.max)))


def reachable(c, profile: MachineProfile) -> Callable[[np.ndarray], bool]:
    """Bağlama yüzü `c` (tablaya dayalı yüzün dış normali) iken tezgâhın ulaşabildiği yönler için yüklem R(c).

    3 eksen: R = {−c}. Döner tabla iş miline paralel (C) + devrilme ekseni: ∠(d, −c) ≤ θ_max, d ≠ c.
    Tek döner eksen, iş miline dik (yatay B tabla): R = {d ⊥ c}. Döner eksen sınırı (B) şimdilik uygulanmaz.
    """
    c = _birim(c)
    if not isinstance(profile, MachineProfile):
        raise CamError(f"Erişim: MachineProfile bekleniyor ({type(profile).__name__})")
    up = -c
    kin = profile.kinematics
    if kin is None or not kin.rotary:
        return lambda d: float(_birim(d) @ up) >= 1 - COS_TOL
    s = _birim(kin.spindle)
    paralel = [r for r in kin.rotary if abs(float(_birim(r.u) @ s)) >= 1 - 1e-6]
    dik = [r for r in kin.rotary if abs(float(_birim(r.u) @ s)) <= 1e-6]
    if not paralel and len(dik) == 1 and len(kin.rotary) == 1:
        return lambda d: abs(float(_birim(d) @ c)) <= 1e-9
    if not dik:  # yalnız iş miline paralel döner eksen: yön değişmez
        return lambda d: float(_birim(d) @ up) >= 1 - COS_TOL
    theta = min(_tilt_limit(r) for r in dik)

    def R(d) -> bool:
        d = _birim(d)
        return float(d @ c) < 1 - COS_TOL and _aci(d, up) <= theta + 1e-9

    return R
