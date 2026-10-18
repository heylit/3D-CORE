"""
SPEC 50 — yanak (swarf) frezeleme: regle yüzeyi düz ucun yan yüzüyle tek pasoda işleme.

S(u, v) = (1 − v)·C₀(u) + v·C₁(u); takım ekseni cetvel yönü g = norm(C₁ − C₀), eksen doğrusu cetvelin
n_m yönünde R ötesinde. Gelişebilir yüzeyde hata 0; bükülmüşte e ≈ R·(1 − cos Δφ) ve gerçek girme ölçülür.

Ek A: u örnek sırası (u_i = i/(n − 1)), v C₀ → C₁; yüzey örnekler arasında bilineer.
n = side·norm(∂S/∂u × ∂S/∂v), ∂S/∂u = C_m = (C₀ + C₁)/2 dizisinin merkezi farkı; takım +n yanında.

Birimler: mm, mm/dk, dev/dk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.model import CamError, Move, MoveType, PathMeta, Tool, ToolKind, Toolpath

TOL = 1e-9  # mm
_INCE = 12  # yerel arama: pencere daraltma adımı
_INCE_N = 9  # yerel arama: pencere başına ızgara


@dataclass
class RuledSurface:
    """Eş parametreli iki ray: C0 alt, C1 üst (n, 3)."""

    C0: np.ndarray
    C1: np.ndarray

    def __post_init__(self) -> None:
        C0 = np.array(self.C0, dtype=float)
        C1 = np.array(self.C1, dtype=float)
        for ad, C in (("C0", C0), ("C1", C1)):
            if C.ndim != 2 or C.shape[1] != 3 or not np.all(np.isfinite(C)):
                raise CamError(f"RuledSurface: {ad} (n, 3) sonlu dizi olmalı ({C.shape})")
        if C0.shape != C1.shape:
            raise CamError(f"RuledSurface: raylar eş sayıda nokta ister ({len(C0)} ≠ {len(C1)})")
        if len(C0) < 2:
            raise CamError(f"RuledSurface: en az 2 cetvel gerekli ({len(C0)})")
        boy = np.linalg.norm(C1 - C0, axis=1)
        if np.any(boy < TOL):
            raise CamError(f"RuledSurface: {int(np.argmin(boy))}. cetvel sıfır boylu")
        self.C0, self.C1 = C0, C1

    @property
    def n(self) -> int:
        return len(self.C0)

    def teget(self) -> np.ndarray:
        """∂S/∂u: C_m dizisinin merkezi farkı, uçlarda tek yanlı (n, 3)."""
        Cm = (self.C0 + self.C1) / 2
        t = np.empty_like(Cm)
        t[1:-1] = Cm[2:] - Cm[:-2]
        t[0] = Cm[1] - Cm[0]
        t[-1] = Cm[-1] - Cm[-2]
        return t

    def nokta(self, s: np.ndarray, v: np.ndarray) -> np.ndarray:
        """S(s, v), s ∈ [0, n − 1] örnek parametresi (bilineer); (k, 3)."""
        s = np.clip(np.asarray(s, dtype=float), 0.0, self.n - 1)
        v = np.asarray(v, dtype=float)
        i = np.minimum(np.floor(s).astype(int), self.n - 2)
        w = (s - i)[:, None]
        C0 = (1 - w) * self.C0[i] + w * self.C0[i + 1]
        C1 = (1 - w) * self.C1[i] + w * self.C1[i + 1]
        return C0 + v[:, None] * (C1 - C0)


def _takim(tool: Tool, nerede: str) -> float:
    if tool.kind is not ToolKind.FLAT or tool.corner_r != 0:
        raise CamError(
            f"{nerede}: yalnız köşesiz düz uç (FLAT) desteklenir ({tool.kind.value}, r_c={tool.corner_r})"
        )
    return tool.D / 2


def _side(side: int) -> int:
    if isinstance(side, bool) or side not in (1, -1):
        raise CamError(f"swarf: side +1 ya da −1 olmalı ({side!r})")
    return int(side)


def _konum(
    S: RuledSurface, s: float, side: int, r: float, allowance_z: float
) -> tuple[np.ndarray, np.ndarray]:
    """s örnek parametresinde (uç, eksen g): p = C₀ + r·n_m + allowance_z·g."""
    s = min(max(float(s), 0.0), S.n - 1)
    i = min(int(math.floor(s)), S.n - 2)
    w = s - i
    C0 = (1 - w) * S.C0[i] + w * S.C0[i + 1]
    C1 = (1 - w) * S.C1[i] + w * S.C1[i + 1]
    T = S.teget()
    t = (1 - w) * T[i] + w * T[i + 1]
    d = C1 - C0
    nm = np.cross(t, d)
    nn = float(np.linalg.norm(nm))
    if nn < TOL * float(np.linalg.norm(d)):
        raise CamError(f"swarf: u = {s / (S.n - 1):.6g}: ilerleme yönü cetvele paralel, normal tanımsız")
    g = d / float(np.linalg.norm(d))
    return C0 + r * side * nm / nn + allowance_z * g, g


def _girme(S: RuledSurface, p: np.ndarray, g: np.ndarray, R: float, L: float, n_check: int) -> float:
    """Bilineer yüzeyin (p, g, [0, L], R) silindirine en büyük girmesi; kaba ızgara + yerel daraltma."""

    def e(s: np.ndarray, v: np.ndarray) -> np.ndarray:
        d = S.nokta(s, v) - p
        h = d @ g
        r = np.linalg.norm(d - np.outer(h, g), axis=1)
        return np.where((h >= 0) & (h <= L), R - r, -np.inf)

    # aday yamalar: yama noktası = k. cetvel noktası + w·((1 − v)ΔC₀ + vΔC₁), |·| ≤ genişlik;
    # cetvel parçasının eksene dik uzaklığı − genişlik ≥ R ise girme olamaz
    A, B = S.C0[:-1] - p, S.C1[:-1] - p
    gen = np.maximum(
        np.linalg.norm(S.C0[1:] - S.C0[:-1], axis=1), np.linalg.norm(S.C1[1:] - S.C1[:-1], axis=1)
    )
    hA, hB = A @ g, B @ g
    Ad, Bd = A - np.outer(hA, g), B - np.outer(hB, g)
    D = Bd - Ad
    DD = np.einsum("ij,ij->i", D, D)
    lam = np.clip(-np.einsum("ij,ij->i", Ad, D) / np.where(DD > 0, DD, 1.0), 0.0, 1.0)
    r = np.linalg.norm(Ad + lam[:, None] * D, axis=1)
    aday = (r - gen < R) & (np.maximum(hA, hB) + gen >= 0) & (np.minimum(hA, hB) - gen <= L)
    if not np.any(aday):
        return 0.0
    q = np.linspace(0.0, 1.0, n_check)
    ks = np.flatnonzero(aday)
    s = (ks[:, None, None] + q[None, :, None] + 0 * q[None, None, :]).ravel()
    v = np.broadcast_to(q[None, None, :], (len(ks), n_check, n_check)).ravel()
    E = e(s, v)
    j = int(np.argmax(E))
    best, s0, v0 = float(E[j]), float(s[j]), float(v[j])
    if not math.isfinite(best):
        return 0.0
    ds, dv = 1.0 / (n_check - 1), 1.0 / (n_check - 1)
    for _ in range(_INCE):
        a = np.linspace(-1.0, 1.0, _INCE_N)
        ss = np.clip(s0 + ds * a, 0.0, S.n - 1)
        vv = np.clip(v0 + dv * a, 0.0, 1.0)
        SS, VV = np.meshgrid(ss, vv)
        E = e(SS.ravel(), VV.ravel())
        j = int(np.argmax(E))
        if E[j] > best:
            best, s0, v0 = float(E[j]), float(SS.ravel()[j]), float(VV.ravel()[j])
        ds, dv = ds / 4, dv / 4
    return max(0.0, best)


def _n_check(n_check: int) -> int:
    if isinstance(n_check, bool) or not isinstance(n_check, int) or n_check < 2:
        raise CamError(f"swarf: n_check ≥ 2 tam sayı olmalı ({n_check!r})")
    return n_check


def swarf(
    surface: RuledSurface,
    tool: Tool,
    side: int = +1,
    allowance: float = 0.0,
    allowance_z: float = 0.0,
    tol_swarf: float = 0.01,
    n_check: int = 21,
    *,
    feed: float,
    rpm: float,
    clearance: float = 5.0,
) -> Toolpath:
    """Yanak yolu; her Move.axis = g(u), meta (yanak, 5). Hata tol_swarf'ı aşarsa CamError.

    n = side·norm(∂S/∂u × ∂S/∂v) (u örnek sırası, v C0 → C1); takım +n yanında; yüzey bilineer.
    """
    R = _takim(tool, "swarf")
    side, n_check = _side(side), _n_check(n_check)
    for ad, val in (("allowance", allowance), ("allowance_z", allowance_z), ("clearance", clearance)):
        if not (math.isfinite(val) and val >= 0):
            raise CamError(f"swarf: {ad} negatif olmayan sonlu sayı olmalı ({val})")
    for ad, val in (("tol_swarf", tol_swarf), ("feed", feed), ("rpm", rpm)):
        if not (math.isfinite(val) and val > 0):
            raise CamError(f"swarf: {ad} pozitif olmalı ({val})")
    S = surface
    boy = np.linalg.norm(S.C1 - S.C0, axis=1)
    if float(boy.max()) > tool.flute_length + TOL:
        i = int(np.argmax(boy))
        raise CamError(f"swarf: {i}. cetvel boyu {boy[i]:.4g} > kesici boy {tool.flute_length}")
    P, G = [], []
    for i in range(S.n):
        p, g = _konum(S, i, side, R + allowance, allowance_z)
        e = _girme(S, p, g, R, tool.flute_length, n_check)
        if e > tol_swarf:
            raise CamError(
                f"swarf: nokta {i} (u = {i / (S.n - 1):.6g}): yanak hatası {e:.4g} mm > tol {tol_swarf}, "
                "yüzey bu takımla yanak frezelemeye uygun değil"
            )
        P.append(p)
        G.append(g)

    def tup(x: np.ndarray) -> tuple[float, float, float]:
        return tuple(float(c) for c in x)

    moves = [Move(MoveType.LINEAR, tup(p), feed=feed, axis=tup(g)) for p, g in zip(P, G, strict=True)]
    moves.append(Move(MoveType.RAPID, tup(P[-1] + clearance * G[-1]), axis=tup(G[-1])))
    tp = Toolpath(
        name="yanak-5x",
        tool=tool,
        start=tup(P[0] + clearance * G[0]),
        moves=moves,
        rpm=rpm,
        meta=PathMeta(strategy="yanak", axis_mode="5", allowance=allowance, allowance_z=allowance_z),
    )
    tp.validate()
    return tp


def swarf_error(surface: RuledSurface, tool: Tool, u: float, side: int = +1, n_check: int = 101) -> float:
    """u'daki takım konumunun (pay yok) gerçek yüzeye en büyük girmesi [mm]."""
    R = _takim(tool, "swarf_error")
    side, n_check = _side(side), _n_check(n_check)
    if not (math.isfinite(u) and 0.0 <= u <= 1.0):
        raise CamError(f"swarf_error: u 0..1 olmalı ({u})")
    S = surface
    p, g = _konum(S, u * (S.n - 1), side, R, 0.0)
    return _girme(S, p, g, R, tool.flute_length, n_check)
