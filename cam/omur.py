"""
Takım ömrü: Taylor, birikimli aşınma (Palmgren–Miner) ve planlı takım değişimi. SPEC 59.

Taylor: Vc · T^n = C → T(Vc) = (C / Vc)^(1/n) [dk], m = 1/n.
Miner: D = Σ ∫ dt / T(Vc(t)) = Σ ∫ (Vc / C)^m dt; yalnız SPEC 32 `Load.kind == "kesme"` adımları sayılır.
Freze: Vc = π · D_eff · n / 1000, D_eff = effective_diameter(tool, ap) (SPEC 14); adımda Vc sabit,
    t = SimStep.duration / 60 [dk].
Torna: r = |x|; G97 Vc = 2π r N / 1000, dt = ds / (f N); G96 r* = 1000 Vc₀ / (2π N_max) ayrımı (SPEC 22).
    Adım r = r* ve x = 0 noktalarında bölünür, her parçada 8 noktalı Gauss–Legendre. Tam sayı m'de
    integrand polinomdur ve sonuç kesindir; değilse parça ikiye bölünerek hata rtol altına indirilir.
Öneri: k = floor(D_lim / D_parça); k = 0 → program içi değişim (at_op).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from cam.cutting import effective_diameter
from cam.kuvvet import Load
from cam.model import ARCS, CamError, FeedMode, MoveType, Tool, ToolLibrary
from cam.sim.lathe_time import zx_arc
from cam.sim.simulate import SimResult
from malzeme.model import TAKIM_MALZEMELERI, Malzeme, ModelError, Taylor

D_LIM = 0.8  # varsayılan değiştirme sınırı (güvenlik payı)
DEGISIM_TURLERI = ("kenar", "kardes", "gerek_yok")
KESME = "kesme"

_GL_X, _GL_W = np.polynomial.legendre.leggauss(8)  # 8 noktalı Gauss–Legendre, [−1, 1]
_DERINLIK = 40  # ikiye bölme sınırı


def tool_life(taylor: Taylor, Vc: float) -> float:
    """T(Vc) [dk]; Taylor.omur'un ince sarmalayıcısı. Vc ≤ 0 veya sonsuz → ModelError."""
    if not (math.isfinite(Vc) and Vc > 0):
        raise ModelError(f"Takım ömrü: kesme hızı pozitif ve sonlu olmalı (Vc={Vc})")
    return float(taylor.omur(Vc))


# ---------------------------------------------------------------- sonuç sınıfları


@dataclass(frozen=True)
class StepWear:
    """Adım başına kesme süresi t [dk], adımdaki hız aralığı [m/dk] ve aşınma katkısı D."""

    k: int
    op: int
    tool_id: int
    t: float
    Vc_min: float
    Vc_max: float
    D: float

    def to_dict(self) -> dict:
        return {
            "k": self.k,
            "op": self.op,
            "tool_id": self.tool_id,
            "t": self.t,
            "Vc_min": self.Vc_min,
            "Vc_max": self.Vc_max,
            "D": self.D,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StepWear:
        return cls(
            k=int(d["k"]),
            op=int(d["op"]),
            tool_id=int(d["tool_id"]),
            t=float(d["t"]),
            Vc_min=float(d["Vc_min"]),
            Vc_max=float(d["Vc_max"]),
            D=float(d["D"]),
        )


@dataclass(frozen=True)
class ToolWear:
    """Takım başına toplam: kesme süresi t_cut [dk], aşınma D, en yüksek Vc [m/dk], adımlar."""

    tool_id: int
    tool_material: str
    t_cut: float
    D: float
    Vc_max: float
    steps: tuple[StepWear, ...]

    def to_dict(self) -> dict:
        return {
            "tool_id": self.tool_id,
            "tool_material": self.tool_material,
            "t_cut": self.t_cut,
            "D": self.D,
            "Vc_max": self.Vc_max,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> ToolWear:
        return cls(
            tool_id=int(d["tool_id"]),
            tool_material=str(d["tool_material"]),
            t_cut=float(d["t_cut"]),
            D=float(d["D"]),
            Vc_max=float(d["Vc_max"]),
            steps=tuple(StepWear.from_dict(s) for s in d["steps"]),
        )


def _int_or_none(v) -> int | None:
    return None if v is None else int(v)


@dataclass(frozen=True)
class ChangeAdvice:
    """Takım değişimi önerisi. kind ∈ {"kenar", "kardes", "gerek_yok"};
    parts_per_edge None iken program içi değişim (at_op dolu)."""

    tool_id: int
    kind: str
    parts_per_edge: int | None
    at_op: int | None
    sister_id: int | None
    D_part: float

    def to_dict(self) -> dict:
        return {
            "tool_id": self.tool_id,
            "kind": self.kind,
            "parts_per_edge": self.parts_per_edge,
            "at_op": self.at_op,
            "sister_id": self.sister_id,
            "D_part": self.D_part,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChangeAdvice:
        kind = str(d["kind"])
        if kind not in DEGISIM_TURLERI:
            raise CamError(f"Takım değişimi önerisi: bilinmeyen tür '{kind}' ({DEGISIM_TURLERI})")
        return cls(
            tool_id=int(d["tool_id"]),
            kind=kind,
            parts_per_edge=_int_or_none(d["parts_per_edge"]),
            at_op=_int_or_none(d["at_op"]),
            sister_id=_int_or_none(d["sister_id"]),
            D_part=float(d["D_part"]),
        )


# ---------------------------------------------------------------- ortak


def _taylorlar(ops, material: Malzeme, tool_materials: Mapping[int, str]) -> dict[int, tuple[str, Taylor]]:
    """Op'lardaki her takım için (takım malzemesi, Taylor); eksik eşlem / kayıt → ModelError."""
    sonuc: dict[int, tuple[str, Taylor]] = {}
    for op in ops:
        n = op.tool.id
        if n in sonuc:
            continue
        if n not in tool_materials:
            raise ModelError(f"T{n} için takım malzemesi verilmedi")
        tm = tool_materials[n]
        if tm not in TAKIM_MALZEMELERI:
            raise ModelError(f"T{n}: bilinmeyen takım malzemesi '{tm}' ({', '.join(TAKIM_MALZEMELERI)})")
        if tm not in material.taylor:
            raise ModelError(f"'{material.name}' kaydında '{tm}' için Taylor yok")
        sonuc[n] = (tm, material.taylor[tm])
    return sonuc


def _yuk_denetimi(result, loads: list[Load]) -> None:
    if len(loads) != len(result.steps):
        raise CamError(
            f"Takım ömrü: yük sayısı ({len(loads)}) adım sayısıyla ({len(result.steps)}) aynı olmalı"
        )


def _topla(ops, taylorlar: dict[int, tuple[str, Taylor]], adimlar: list[StepWear]) -> list[ToolWear]:
    """Adım katkılarını takım başına toplar; takımlar op'larda ilk görüldükleri sırada."""
    sonuc = []
    for n, (tm, _) in taylorlar.items():
        s = tuple(a for a in adimlar if a.tool_id == n)
        sonuc.append(
            ToolWear(
                tool_id=n,
                tool_material=tm,
                t_cut=math.fsum(a.t for a in s),
                D=math.fsum(a.D for a in s),
                Vc_max=max((a.Vc_max for a in s), default=0.0),
                steps=s,
            )
        )
    return sonuc


def _op(ops, step):
    if not 0 <= step.op < len(ops):
        raise CamError(f"Takım ömrü: adım {step.k} op {step.op} op listesinde yok ({len(ops)} op)")
    return ops[step.op]


# ---------------------------------------------------------------- freze


def mill_wear(
    ops,
    result: SimResult,
    loads: list[Load],
    material: Malzeme,
    tool_materials: Mapping[int, str],
) -> list[ToolWear]:
    """Freze: adım başına sabit Vc ile D_i = duration_i / T(Vc_i).
    len(loads) ≠ len(result.steps) → CamError."""
    _yuk_denetimi(result, loads)
    taylorlar = _taylorlar(ops, material, tool_materials)
    adimlar = []
    for step, load in zip(result.steps, loads, strict=True):
        if load.kind != KESME:
            continue
        op = _op(ops, step)
        tool = op.tool
        rpm = getattr(op, "rpm", 0.0)
        if not (rpm is not None and math.isfinite(rpm) and rpm > 0):
            raise CamError(f"Adım {step.k} (op {step.op}, T{tool.id}): kesmede devir yok, Vc hesaplanamıyor")
        D_eff = effective_diameter(tool, load.ap) if isinstance(tool, Tool) and load.ap > 0 else tool.D
        Vc = math.pi * D_eff * rpm / 1000
        t = step.duration / 60
        D = t / tool_life(taylorlar[tool.id][1], Vc)
        adimlar.append(StepWear(step.k, step.op, tool.id, t, Vc, Vc, D))
    return _topla(ops, taylorlar, adimlar)


# ---------------------------------------------------------------- torna


def _gl(g: Callable[[np.ndarray], np.ndarray], a: float, b: float) -> float:
    """∫_a^b g, 8 noktalı Gauss–Legendre."""
    h = (b - a) / 2
    return float(h * np.dot(_GL_W, g((a + b) / 2 + h * _GL_X)))


def _uyarlanir(g, a: float, b: float, tol: float, J: float, derinlik: int = 0) -> float:
    """İkiye bölerek ∫_a^b g; iki yarının toplamı tek parçadan tol kadar farklıysa yarılar yeniden bölünür."""
    c = (a + b) / 2
    I1, I2 = _gl(g, a, c), _gl(g, c, b)
    if abs(I1 + I2 - J) <= tol or derinlik >= _DERINLIK:
        return I1 + I2
    return _uyarlanir(g, a, c, tol / 2, I1, derinlik + 1) + _uyarlanir(g, c, b, tol / 2, I2, derinlik + 1)


class _Kesim:
    """Bir torna op'unun kesme hızı modeli: r [mm] → Vc [m/dk] ve dt/ds [dk/mm]."""

    def __init__(self, op, F: float) -> None:
        self.N = float(op.rpm)
        self.Vc0 = None if op.css is None else float(op.css)
        self.r_yildiz = None if self.Vc0 is None else 1000 * self.Vc0 / (2 * math.pi * self.N)
        self.per_rev = op.feed_mode is FeedMode.PER_REV
        self.F = F

    def n(self, r: np.ndarray) -> np.ndarray:
        """Devir [dev/dk]: G97 N; G96 min(1000 Vc₀ / (2π r), N_max)."""
        if self.Vc0 is None:
            return np.full_like(r, self.N)
        with np.errstate(divide="ignore"):
            return np.minimum(1000 * self.Vc0 / (2 * math.pi * r), self.N)

    def Vc(self, r: np.ndarray) -> np.ndarray:
        return 2 * math.pi * r * self.n(r) / 1000

    def dtds(self, r: np.ndarray) -> np.ndarray:
        """G95: 1 / (f n(r)); G94: 1 / F."""
        if self.per_rev:
            return 1 / (self.F * self.n(r))
        return np.full_like(r, 1 / self.F)


def _yol(step) -> tuple[Callable[[np.ndarray], np.ndarray], float, float, list[float]]:
    """Adımın parametrik yolu: (u → x, ds/du, u_bitiş, x'in uç değer verdiği iç u'lar).

    Doğru: u = s ∈ [0, L]. Yay (G18, x = c_v + R sin θ): u = θ − θa ∈ [0, Δθ], ds/du = L / Δθ.
    """
    p0, p1 = np.asarray(step.start, dtype=float), np.asarray(step.end, dtype=float)
    if step.type in ARCS:
        R, dth, th0, _, cv = zx_arc(p0, p1, step.center, step.type is MoveType.ARC_CW)
        ta = th0 - dth if step.type is MoveType.ARC_CW else th0
        L = math.hypot(R * dth, p1[1] - p0[1])
        uclar = [(th - ta) % (2 * math.pi) for th in (math.pi / 2, 3 * math.pi / 2)]
        return (lambda u: cv + R * np.sin(ta + u)), L / dth, dth, [u for u in uclar if 0 < u < dth]
    L = float(np.linalg.norm(p1 - p0))
    x0, x1 = p0[0], p1[0]
    return (lambda u: x0 + (x1 - x0) * u / L if L > 0 else np.full_like(u, x0)), 1.0, L, []


def _kesim_noktalari(x: Callable, u_son: float, uclar: list[float], degerler: list[float]) -> list[float]:
    """x(u) = ±r* ve x = 0 noktaları (ve x'in uç noktaları): [0, u_son] parça sınırları.

    Uç noktalar arasında x(u) tekdüzedir; her aralıkta kök ikiye bölmeyle bulunur.
    """
    sinirlar = sorted({0.0, u_son, *uclar})
    kes = set(sinirlar)
    for a, b in zip(sinirlar, sinirlar[1:], strict=False):
        xa, xb = float(x(np.array([a]))[0]), float(x(np.array([b]))[0])
        for v in degerler:
            if (xa - v) * (xb - v) < 0:
                lo, hi = a, b
                for _ in range(200):
                    c = (lo + hi) / 2
                    xc = float(x(np.array([c]))[0])
                    if (xa - v) * (xc - v) <= 0:
                        hi = c
                    else:
                        lo = c
                    if hi - lo <= 1e-15 * max(1.0, u_son):
                        break
                kes.add((lo + hi) / 2)
    return sorted(kes)


def _torna_adimi(step, op, taylor: Taylor, rtol: float) -> StepWear:
    tool = op.tool
    if not (op.rpm is not None and math.isfinite(op.rpm) and op.rpm > 0):
        raise CamError(f"Adım {step.k} (op {step.op}, T{tool.id}): kesmede devir yok, Vc hesaplanamıyor")
    F = step.feed
    if F is None or not (math.isfinite(F) and F > 0):
        raise CamError(
            f"Adım {step.k} (op {step.op}, T{tool.id}): kesmede ilerleme pozitif olmalı (feed={F})"
        )
    kesim = _Kesim(op, F)
    x, dsdu, u_son, uclar = _yol(step)
    if u_son <= 0:
        return StepWear(step.k, step.op, tool.id, 0.0, 0.0, 0.0, 0.0)
    degerler = [0.0] if kesim.r_yildiz is None else [-kesim.r_yildiz, 0.0, kesim.r_yildiz]
    u = _kesim_noktalari(x, u_son, uclar, degerler)

    C, m = float(taylor.C), 1 / float(taylor.n)

    def dt(uu: np.ndarray) -> np.ndarray:
        return kesim.dtds(np.abs(x(uu))) * dsdu

    def dD(uu: np.ndarray) -> np.ndarray:
        r = np.abs(x(uu))
        return (kesim.Vc(r) / C) ** m * kesim.dtds(r) * dsdu

    parcalar = list(zip(u, u[1:], strict=False))
    t = math.fsum(_gl(dt, a, b) for a, b in parcalar)
    J = [_gl(dD, a, b) for a, b in parcalar]
    if not float(m).is_integer():
        tol = rtol * 1e-2 * abs(math.fsum(J)) / max(len(parcalar), 1)
        J = [_uyarlanir(dD, a, b, tol, Ji) for (a, b), Ji in zip(parcalar, J, strict=True)]
    Vc_uc = kesim.Vc(np.abs(x(np.asarray(u))))
    return StepWear(step.k, step.op, tool.id, t, float(Vc_uc.min()), float(Vc_uc.max()), math.fsum(J))


def turn_wear(
    ops,
    result,
    loads: list[Load],
    material: Malzeme,
    tool_materials: Mapping[int, str],
    rtol: float = 1e-6,
) -> list[ToolWear]:
    """Torna: çapla değişen Vc; adımlar r = r* ve x = 0'da bölünür, 8 noktalı Gauss–Legendre.
    G96 / G97 ayrımı Toolpath.css ve rpm'den."""
    if not (math.isfinite(rtol) and rtol > 0):
        raise CamError(f"Takım ömrü: rtol pozitif olmalı ({rtol})")
    _yuk_denetimi(result, loads)
    taylorlar = _taylorlar(ops, material, tool_materials)
    adimlar = []
    for step, load in zip(result.steps, loads, strict=True):
        if load.kind != KESME:
            continue
        op = _op(ops, step)
        adimlar.append(_torna_adimi(step, op, taylorlar[op.tool.id][1], rtol))
    return _topla(ops, taylorlar, adimlar)


# ---------------------------------------------------------------- öneri

_FREZE_GEOMETRISI = ("kind", "D", "corner_r", "flutes", "flute_length")
_TORNA_GEOMETRISI = ("kind", "nose_r", "kappa_r", "eps_r")


def _kardes(lib: ToolLibrary, tool_id: int) -> int | None:
    """Kütüphanede aynı geometri ve kesme verisine sahip, en küçük kimlikli başka takım."""
    t = lib.get(tool_id)
    alanlar = _FREZE_GEOMETRISI if isinstance(t, Tool) else _TORNA_GEOMETRISI
    adaylar = [
        u.id
        for u in lib.tools
        if u.id != t.id
        and type(u) is type(t)
        and all(getattr(u, a) == getattr(t, a) for a in alanlar)
        and u.cutting == t.cutting
    ]
    return min(adaylar, default=None)


def _degisim_op(w: ToolWear, D_lim: float) -> int | None:
    """Birikimli D'nin D_lim'e ulaştığı adımın op'u (değişim o op'un başında)."""
    D = 0.0
    for s in w.steps:
        D += s.D
        if D >= D_lim - 1e-12:
            return s.op
    return None


def advise(
    wear: list[ToolWear], lib: ToolLibrary, parts: int = 1, D_lim: float = D_LIM
) -> list[ChangeAdvice]:
    """Planlı takım değişimi önerisi; 0 < D_lim ≤ 1, parts ≥ 1 tam sayı, aksi CamError."""
    if isinstance(D_lim, bool) or not (math.isfinite(D_lim) and 0 < D_lim <= 1):
        raise CamError(f"Takım değişimi: D_lim (0, 1] aralığında olmalı ({D_lim})")
    if isinstance(parts, bool) or not isinstance(parts, int | np.integer) or parts < 1:
        raise CamError(f"Takım değişimi: parça sayısı ≥ 1 tam sayı olmalı ({parts!r})")
    sonuc = []
    for w in wear:
        D = w.D
        if not (math.isfinite(D) and D >= 0):
            raise CamError(f"T{w.tool_id}: aşınma D geçersiz ({D})")
        if D == 0:
            sonuc.append(ChangeAdvice(w.tool_id, "gerek_yok", None, None, None, D))
            continue
        k = math.floor(D_lim / D + 1e-12)
        if parts * D <= D_lim + 1e-12:
            sonuc.append(ChangeAdvice(w.tool_id, "gerek_yok", k, None, None, D))
            continue
        kardes = _kardes(lib, w.tool_id)
        tur = "kenar" if kardes is None else "kardes"
        if k == 0:
            sonuc.append(ChangeAdvice(w.tool_id, tur, None, _degisim_op(w, D_lim), kardes, D))
        else:
            sonuc.append(ChangeAdvice(w.tool_id, tur, k, None, kardes, D))
    return sonuc
