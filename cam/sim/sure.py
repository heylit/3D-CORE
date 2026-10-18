"""
SPEC 72 — Sarsıntı sınırlı (S eğrisi) hareket süresi, köşe hızı, ileri-geri hız planlaması, eksen sınırları.

SPEC 05'in `move_time`'ı (tam duruş, sonsuz sarsıntı) aynen kalır; bu modül onun genellemesidir:
j → ∞ ve tol = 0 iken süreler SPEC 05 ile aynıdır (K3).

Birimler: hız mm/s (iç hesap), girdi F ve eksen hızları mm/dk; ivme mm/s², sarsıntı mm/s³;
döner eksen hızı derece/dk, ivmesi derece/s².
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import CamError, Toolpath  # noqa: F401  (CamError gövdelerde kullanılacak)


@dataclass(frozen=True)
class Dynamics:
    """Eksen başına dinamik sınırlar (X, Y, Z [+ döner]).

    v_max mm/dk, a_max mm/s², j_max mm/s³ (None → sonsuz sarsıntı); rot_v derece/dk, rot_a derece/s²;
    tol = yol toleransı ε [mm] (0 → her köşede tam duruş); lookahead = ileri bakış ufku (None → sınırsız).
    Pozitif olmayan / sonlu olmayan değer → CamError.
    """

    v_max: tuple[float, ...]
    a_max: tuple[float, ...]
    j_max: tuple[float, ...] | None
    rot_v: tuple[float, ...] = ()
    rot_a: tuple[float, ...] = ()
    tol: float = 0.0
    lookahead: int | None = None

    def __post_init__(self) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class PathTime:
    """Bir takım yolunun süresi [s]: kesme (G1/G2/G3) ve hızlı (G0) ayrı."""

    cut: float
    rapid: float
    n_moves: int

    @property
    def total(self) -> float:
        return self.cut + self.rapid


def scurve_time(L: float, v: float, a: float, j: float | None, v0: float = 0.0, v1: float = 0.0) -> float:
    """L boyunu v0 hızla girip v1 hızla çıkarak, v, a, j sınırlarıyla geçme süresi [s] (Teori 1–2)."""
    raise NotImplementedError


def junction_speed(u1, u2, F: float, a: float, tol: float, L1: float, L2: float) -> float:
    """İki doğrusal segment arasındaki köşe hızı [mm/s] (Teori 3); F mm/s."""
    raise NotImplementedError


def plan_speeds(segments, dyn: Dynamics) -> list[float]:
    """Segment sınır hızları [mm/s], ileri-geri geçişle (Teori 4); ilk ve son 0."""
    raise NotImplementedError


def toolpath_time(tp: Toolpath, dyn: Dynamics) -> PathTime:
    """Takım yolunun süresi (Teori 1–5)."""
    raise NotImplementedError
