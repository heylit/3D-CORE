"""
SPEC 42 — eş zamanlı 5 eksen ince işleme: eksen boyunca drop-cutter, normal tahmini, yönelim
stratejileri, sap / tutucu çarpışmasından yana eğimle kaçınma, yönelim sürekliliği.

Ölçü noktası takım ucudur; küre merkezi c = p + R·a (a uçtan iş miline birim eksen).
Eksen boyunca drop: ağ F = from_normal(0, a, x_hint) çerçevesine çevrilir, SPEC 06 drop yerel (x, y)'de
çalışır; yerel +z = a olduğundan takım −a yönünde yüzeye değene kadar iner.

Birimler: mm, mm/dk, derece.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.dropcutter import TriMesh, drop
from cam.model import CamError, Frame, Move, MoveType, Tool, ToolKind, Toolpath
from cam.multiaxis.indexed import from_normal, local_mesh
from cam.multiaxis.kinematics import rotation
from cam.ops3d import Raster, _raster_cl
from cam.sim import body_steps

TOL = 1e-9
_YOK = -1e300  # drop'ta "değmiyor" bekçisi (floor olarak)
_EX, _EY, _EZ = np.eye(3)
TURLER = ("sabit", "normal", "noktaya", "noktadan")


def _birim(v, ne: str) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    if v.shape != (3,) or not np.all(np.isfinite(v)):
        raise CamError(f"{ne}: 3 bileşenli sonlu vektör olmalı ({v})")
    n = float(np.linalg.norm(v))
    if n < TOL:
        raise CamError(f"{ne}: sıfır vektör olamaz")
    return v / n


def _aci(u: np.ndarray, v: np.ndarray) -> float:
    """İki birim vektör arası açı [derece]."""
    return math.degrees(math.atan2(float(np.linalg.norm(np.cross(u, v))), float(u @ v)))


# ---------------------------------------------------------------- eksen boyunca drop


def _cerceve(a: np.ndarray, x_hint) -> Frame:
    """+z = a; x ipucu: verilen, ona paralelse +X, o da paralelse +Y."""
    adaylar = ([] if x_hint is None else [np.asarray(x_hint, dtype=float)]) + [_EX, _EY]
    for x in adaylar:
        xn = float(np.linalg.norm(x))
        if xn > TOL and np.linalg.norm(np.cross(x, a)) > 1e-6 * xn:
            return from_normal((0.0, 0.0, 0.0), a, x)
    raise CamError(f"Eksen boyunca drop: x ipucu kurulamadı (a = {tuple(a)})")  # erişilemez


class _Yerel:
    """Bir eksen yönü için yerel çerçeve ve ağ (aynı eksende tekrar kullanılır)."""

    def __init__(self, mesh: TriMesh, a: np.ndarray, x_hint=None) -> None:
        self.a = a
        self.F = _cerceve(a, x_hint)
        self.mesh = local_mesh(mesh, self.F)

    def drop(self, tool: Tool, p_l: np.ndarray) -> float | None:
        """Yerel (x, y)'de drop yüksekliği; ağla örtüşme yoksa None."""
        z = float(drop(self.mesh, tool, np.array([[p_l[0], p_l[1]]]), floor=_YOK)[0])
        return None if z <= _YOK else z


def _drop_along(yerel: _Yerel, tool: Tool, point) -> tuple[np.ndarray, float] | None:
    """(yerel uç, yerel z) ya da örtüşme yoksa None."""
    p_l = yerel.F.to_local(np.asarray(point, dtype=float))
    z = yerel.drop(tool, p_l)
    if z is None:
        return None
    return np.array([p_l[0], p_l[1], z]), z


def drop_along(mesh: TriMesh, tool: Tool, point, a, x_hint=None) -> np.ndarray:
    """`point`'ten geçen `a` doğrultulu çizgide eksen boyunca drop; takım ucu (WCS)."""
    a = _birim(a, "drop_along: a")
    point = np.asarray(point, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise CamError(f"drop_along: point 3 bileşenli sonlu olmalı ({point})")
    yerel = _Yerel(mesh, a, x_hint)
    sonuc = _drop_along(yerel, tool, point)
    if sonuc is None:
        raise CamError(f"drop_along: {tuple(point)} noktasından a = {tuple(a)} boyunca takım ağa değmiyor")
    return yerel.F.to_world(sonuc[0])


# ---------------------------------------------------------------- normal tahmini


def _R(tool: Tool) -> float:
    return tool.D / 2


def _normaller(mesh: TriMesh, tool: Tool, xy: np.ndarray, h_n: float, floor: float | None) -> np.ndarray:
    """Ofset yüzeyden merkezi farkla birim normaller (k, 3): n ∝ (−∂z_c/∂x, −∂z_c/∂y, 1)."""
    k = len(xy)
    dx, dy = np.array([h_n, 0.0]), np.array([0.0, h_n])
    Q = np.vstack([xy + dx, xy - dx, xy + dy, xy - dy])
    z = drop(mesh, tool, Q, floor).reshape(4, k)
    n = np.column_stack([-(z[0] - z[1]) / (2 * h_n), -(z[2] - z[3]) / (2 * h_n), np.ones(k)])
    return n / np.linalg.norm(n, axis=1)[:, None]


def _h_n(tool: Tool, h_n: float | None) -> float:
    h = _R(tool) / 10 if h_n is None else float(h_n)
    if not (math.isfinite(h) and h > 0):
        raise CamError(f"surface_normal: h_n pozitif olmalı ({h_n})")
    return h


def surface_normal(mesh: TriMesh, tool: Tool, x: float, y: float, h_n: float | None = None) -> np.ndarray:
    """Ofset yüzeyden (z_c = drop + R) merkezi farkla birim normal."""
    return _normaller(mesh, tool, np.array([[float(x), float(y)]]), _h_n(tool, h_n), None)[0]


# ---------------------------------------------------------------- strateji ve kaçınma


@dataclass
class Orientation:
    """Takım ekseni stratejisi: "sabit", "normal", "noktaya", "noktadan"; açılar derece."""

    kind: str
    a: tuple[float, float, float] | None = None
    lead: float = 0.0
    tilt: float = 0.0
    point: tuple[float, float, float] | None = None
    max_tilt: float = 90.0

    def __post_init__(self) -> None:
        if self.kind not in TURLER:
            raise CamError(f"Orientation: tür {TURLER} içinden olmalı ({self.kind!r})")
        for ad in ("lead", "tilt", "max_tilt"):
            if not math.isfinite(getattr(self, ad)):
                raise CamError(f"Orientation.{ad} sonlu olmalı ({getattr(self, ad)})")
        if not 0 <= self.max_tilt <= 180:
            raise CamError(f"Orientation.max_tilt 0..180° olmalı ({self.max_tilt})")
        gerek = {"sabit": {"a"}, "normal": set(), "noktaya": {"point"}, "noktadan": {"point"}}[self.kind]
        verilen = {ad for ad in ("a", "point") if getattr(self, ad) is not None}
        if self.kind != "normal" and (self.lead != 0 or self.tilt != 0):
            verilen |= {"lead/tilt"}
        if verilen != gerek:
            raise CamError(
                f"Orientation '{self.kind}': gereken alanlar {sorted(gerek)}, verilen {sorted(verilen)}"
            )
        if self.a is not None:
            self.a = tuple(float(v) for v in _birim(self.a, "Orientation.a"))
        if self.point is not None:
            p = np.asarray(self.point, dtype=float)
            if p.shape != (3,) or not np.all(np.isfinite(p)):
                raise CamError(f"Orientation.point 3 bileşenli sonlu olmalı ({self.point})")
            self.point = tuple(float(v) for v in p)


@dataclass
class Avoid:
    """Gövde çarpışmasında yana eğim adımı ve sınırı [derece], çarpışma toleransı [mm]."""

    dtilt: float = 2.0
    tilt_max: float = 30.0
    tol: float = 1e-6

    def __post_init__(self) -> None:
        for ad in ("dtilt", "tilt_max", "tol"):
            if not math.isfinite(getattr(self, ad)):
                raise CamError(f"Avoid.{ad} sonlu olmalı ({getattr(self, ad)})")
        if self.dtilt <= 0:
            raise CamError(f"Avoid.dtilt pozitif olmalı ({self.dtilt})")
        if self.tilt_max < 0 or self.tol < 0:
            raise CamError(f"Avoid: tilt_max ve tol negatif olamaz ({self.tilt_max}, {self.tol})")

    def adimlar(self) -> list[float]:
        """Ek yana eğimler: +Δ, −Δ, +2Δ, −2Δ, … (|·| ≤ tilt_max)."""
        n = int(math.floor(self.tilt_max / self.dtilt + 1e-9))
        return [s * k * self.dtilt for k in range(1, n + 1) for s in (1.0, -1.0)]


# ---------------------------------------------------------------- tek nokta


@dataclass
class _Surus:
    """Sürüş noktası: merkez c₀, normal n, ilerleme yönü (birimsiz, n'e dik değil)."""

    c0: np.ndarray
    n: np.ndarray
    f: np.ndarray


class _Hesap:
    """finish5'in nokta başına hesabı (ağ, takım, strateji ve gövde basamakları sabit)."""

    def __init__(self, mesh, tool, orient: Orientation, avoid: Avoid | None, floor) -> None:
        self.mesh, self.tool, self.o, self.avoid, self.floor = mesh, tool, orient, avoid, floor
        self.R = _R(tool)
        self.h_n = self.R / 10
        self.govde = [
            (Tool(id=0, name=f"{tur}-{rho:g}", kind=ToolKind.FLAT, D=2 * rho, flute_length=1.0), H)
            for rho, H, tur in body_steps(tool)
        ]
        self._sabit: _Yerel | None = None

    def surus(self, xy: np.ndarray, f: np.ndarray) -> list[_Surus]:
        z = drop(self.mesh, self.tool, xy, self.floor) + self.R
        N = _normaller(self.mesh, self.tool, xy, self.h_n, self.floor)
        return [_Surus(np.array([x, y, zc]), n, f) for (x, y), zc, n in zip(xy, z, N, strict=True)]

    def _f(self, s: _Surus) -> np.ndarray:
        f = s.f - (s.f @ s.n) * s.n
        nf = float(np.linalg.norm(f))
        if nf < TOL:
            raise CamError(f"finish5: {tuple(s.c0)} noktasında ilerleme yönü normale paralel")
        return f / nf

    def eksen(self, s: _Surus) -> tuple[np.ndarray, np.ndarray | None]:
        """Stratejinin ekseni ve yana eğim ekseni f (gerekmiyorsa None)."""
        o = self.o
        if o.kind == "sabit":
            a, f = np.array(o.a), None
        elif o.kind == "normal":
            f = None
            a = s.n
            if o.lead != 0 or o.tilt != 0:
                f = self._f(s)
                lam = math.radians(o.lead)
                a = rotation(f, o.tilt) @ (s.n * math.cos(lam) + f * math.sin(lam))
        else:
            d = np.array(o.point) - s.c0 if o.kind == "noktaya" else s.c0 - np.array(o.point)
            a, f = _birim(d, f"finish5: '{o.kind}' ekseni ({tuple(s.c0)})"), None
        a = a / np.linalg.norm(a)
        if _aci(a, _EZ) > o.max_tilt + TOL:
            raise CamError(
                f"finish5: {tuple(s.c0)}: eksen düşeyle {_aci(a, _EZ):.3f}° > max_tilt {o.max_tilt}°"
            )
        return a, f

    def _yerel(self, a: np.ndarray, f) -> _Yerel:
        if self.o.kind == "sabit":
            if self._sabit is None:
                self._sabit = _Yerel(self.mesh, a)
            return self._sabit
        return _Yerel(self.mesh, a, f)

    def konum(self, s: _Surus, a: np.ndarray, f) -> tuple[np.ndarray, str | None]:
        """Uç (WCS) ve çarpışan gövde basamağı (yoksa None)."""
        yerel = self._yerel(a, f)
        sonuc = _drop_along(yerel, self.tool, s.c0)
        if sonuc is None:
            if self.floor is None:
                raise CamError(f"finish5: {tuple(s.c0)} noktasından eksen boyunca takım ağa değmiyor")
            return s.c0 - self.R * a, None
        p_l, z_uc = sonuc
        tol = 0.0 if self.avoid is None else self.avoid.tol
        for duz, H in self.govde:
            z_j = yerel.drop(duz, p_l)
            if z_j is not None and z_j > z_uc + H + tol:
                return yerel.F.to_world(p_l), f"{duz.name} (z_j = {z_j:.4f} > {z_uc + H:.4f})"
        return yerel.F.to_world(p_l), None

    def nokta(self, s: _Surus, i: int) -> tuple[np.ndarray, np.ndarray]:
        """(uç, eksen): strateji, konumlama, gerekirse yana eğimle kaçınma."""
        a, f = self.eksen(s)
        p, carp = self.konum(s, a, f)
        if carp is None:
            return p, a
        if self.avoid is None:
            raise CamError(f"finish5: nokta {i} {tuple(s.c0)}: gövde çarpışması {carp} (Avoid yok)")
        f = self._f(s) if f is None else f
        for dt in self.avoid.adimlar():
            ak = rotation(f, dt) @ a
            if _aci(ak, _EZ) > self.o.max_tilt + TOL:
                continue
            pk, ck = self.konum(s, ak, f)
            if ck is None:
                return pk, ak
        raise CamError(
            f"finish5: nokta {i} {tuple(s.c0)}: gövde çarpışması {carp}; "
            f"±{self.avoid.tilt_max}° yana eğimle kaçınılamadı"
        )


# ---------------------------------------------------------------- yol


def _ilerleme(C: np.ndarray) -> np.ndarray:
    """Komşu merkezlerden ilerleme yönleri (uçlarda tek yanlı fark)."""
    F = np.empty_like(C)
    F[1:-1] = C[2:] - C[:-2]
    F[0] = C[1] - C[0]
    F[-1] = C[-1] - C[-2]
    return F


def _surekli(h: _Hesap, xy: np.ndarray, r: Raster, max_dangle: float) -> tuple[np.ndarray, np.ndarray]:
    """Sürüş noktaları → (uçlar, eksenler); ardışık eksen açısı > max_dangle ise araya nokta eklenir."""
    S = h.surus(xy, np.zeros((len(xy), 3)))
    for s, f in zip(S, _ilerleme(np.array([s.c0 for s in S])), strict=True):
        s.f = f
    nokta = [h.nokta(s, i) for i, s in enumerate(S)]
    P, A, XY = [nokta[0][0]], [nokta[0][1]], [xy[0]]
    surus = [S[0]]
    yigin = [(xy[i], S[i], nokta[i]) for i in range(len(S) - 1, 0, -1)]
    while yigin:
        q, sq, (pq, aq) = yigin[-1]
        if _aci(A[-1], aq) <= max_dangle:
            P.append(pq)
            A.append(aq)
            XY.append(q)
            surus.append(sq)
            yigin.pop()
            continue
        boy = float(np.hypot(*(q - XY[-1])))
        if boy < 2 * r.ds_min - TOL:
            raise CamError(
                f"finish5: {tuple(XY[-1])} → {tuple(q)} arasında eksen {_aci(A[-1], aq):.3f}° döner "
                f"(> max_dangle {max_dangle}°), ds_min = {r.ds_min}'e inildi"
            )
        m = (XY[-1] + q) / 2
        sm = h.surus(m[None, :], np.zeros((1, 3)))[0]
        sm.f = sq.c0 - surus[-1].c0
        yigin.append((m, sm, h.nokta(sm, len(P))))
    return np.array(P), np.array(A)


def finish5(
    mesh: TriMesh,
    tool: Tool,
    raster: Raster,
    orient: Orientation,
    avoid: Avoid | None = None,
    max_dangle: float = 5.0,
    floor: float | None = None,
) -> Toolpath:
    """Küresel uçla 5 eksen raster ince işleme; her Move.axis dolu, frame = None.

    Giriş: z_safe'te eksen doğrusu üstünden G0, clearance kadar yukarıdan G1 dalma; çıkış eksen boyunca
    z_safe'e G0.
    """
    if tool.kind is not ToolKind.BALL:
        raise CamError(f"finish5: yalnız küresel uç (BALL) desteklenir ({tool.kind.value})")
    if not (math.isfinite(max_dangle) and max_dangle > 0):
        raise CamError(f"finish5: max_dangle pozitif olmalı ({max_dangle})")
    h = _Hesap(mesh, tool, orient, avoid, floor)
    cl = _raster_cl(lambda q: drop(mesh, tool, q, floor), raster)
    P, A = _surekli(h, cl[:, :2], raster, max_dangle)
    z_ust = float(P[:, 2].max())
    if raster.z_safe < z_ust + raster.clearance - TOL:
        raise CamError(
            f"finish5: z_safe en yüksek ucun clearance üstünde olmalı (z_safe={raster.z_safe}, z={z_ust})"
        )

    def guvenli(p: np.ndarray, a: np.ndarray) -> tuple[float, float, float]:
        s = (raster.z_safe - p[2]) / a[2] if a[2] > TOL else raster.clearance
        return tuple(float(v) for v in p + max(s, raster.clearance) * a)

    def ax(a: np.ndarray) -> tuple[float, float, float]:
        return tuple(float(v) for v in a)

    def pt(p: np.ndarray) -> tuple[float, float, float]:
        return tuple(float(v) for v in p)

    moves = [
        Move(MoveType.RAPID, pt(P[0] + raster.clearance * A[0]), axis=ax(A[0])),
        Move(MoveType.LINEAR, pt(P[0]), feed=raster.plunge_feed, axis=ax(A[0])),
    ]
    moves += [
        Move(MoveType.LINEAR, pt(p), feed=raster.feed, axis=ax(a)) for p, a in zip(P[1:], A[1:], strict=True)
    ]
    moves.append(Move(MoveType.RAPID, guvenli(P[-1], A[-1]), axis=ax(A[-1])))
    tp = Toolpath(name="ince-5x", tool=tool, start=guvenli(P[0], A[0]), moves=moves, rpm=raster.rpm)
    tp.validate()
    return tp
