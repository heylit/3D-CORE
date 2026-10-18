"""
SPEC 50 — eksen düzgünleştirme: yönelim dizisine simetrik pencereli ortalama, çakmazlık korunarak.

Ölçüt J = Σ_k |∠(a_k, a_{k+1}) − ∠(a_{k−1}, a_k)|; düzgünleştirme J'yi artıramaz.
Kesme dizisi: ekseni dolu, aynı ilerlemeli ardışık G1 hareketleri (dalma ayrı dizidir). Pencere dizi içinde,
eşit ağırlıklı, uçlarda kırpılır. Küresel uçta küre merkezi korunur (p = c − R·a); torikte eski uçtan geçen
yeni eksen doğrusunda 42 drop'u. Çakan, gövdesi çarpan ya da tezgâhta erişilemeyen noktada eski eksen kalır.

Birimler: mm, derece.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import CamError, Kinematics, Move, MoveType, Tool, ToolKind, Toolpath
from cam.multiaxis.kinematics import inverse_axes
from cam.multiaxis.toolpath5 import Avoid, Orientation, _Hesap, _Surus

_ESIT = 1e-15  # bundan küçük eksen değişimi "değişmedi" sayılır


def _aci(u: np.ndarray, v: np.ndarray) -> float:
    return math.atan2(float(np.linalg.norm(np.cross(u, v))), float(u @ v))


def _diziler(tp: Toolpath) -> list[list[int]]:
    """Kesintisiz G1 kesme dizileri: ekseni dolu, ilerlemesi aynı ardışık G1 hareket indeksleri."""
    diziler: list[list[int]] = []
    cur: list[int] = []
    for k, m in enumerate(tp.moves):
        kesme = m.type is MoveType.LINEAR and m.axis is not None
        if kesme and cur and tp.moves[cur[-1]].feed == m.feed:
            cur.append(k)
            continue
        if cur:
            diziler.append(cur)
        cur = [k] if kesme else []
    if cur:
        diziler.append(cur)
    return diziler


def _J(moves: list[Move], diziler: list[list[int]]) -> float:
    J = 0.0
    for d in diziler:
        A = [np.array(moves[k].axis) for k in d]
        for i in range(1, len(A) - 1):
            J += abs(_aci(A[i], A[i + 1]) - _aci(A[i - 1], A[i]))
    return J


def _ortalama(A: np.ndarray, h: int) -> np.ndarray:
    """Eşit ağırlıklı, uçlarda kırpılan pencere (yarı genişlik h) ortalaması, birimlenmiş."""
    n = len(A)
    B = np.empty_like(A)
    for k in range(n):
        s = A[max(0, k - h) : min(n, k + h + 1)].sum(axis=0)
        ns = float(np.linalg.norm(s))
        B[k] = A[k] if ns < 1e-12 else s / ns
    return B


def smooth_axes(
    tp: Toolpath,
    mesh: TriMesh,
    tool: Tool,
    w: int = 5,
    avoid: Avoid | None = None,
    kin: Kinematics | None = None,
) -> tuple[Toolpath, float, float]:
    """Düzgünleştirilmiş yol, J_eski, J_yeni.

    Pencere yalnız kesintisiz G1 kesme dizisinin içinde; dizi uçlarında kırpılır, ağırlık eşit.
    """
    if isinstance(w, bool) or not isinstance(w, int) or w < 1 or w % 2 == 0:
        raise CamError(f"smooth_axes: w tek ve ≥ 1 tam sayı olmalı ({w!r})")
    if not (tool.kind is ToolKind.BALL or (tool.kind is ToolKind.FLAT and tool.corner_r > 0)):
        raise CamError(f"smooth_axes: yalnız küresel ve torik uç desteklenir ({tool.kind.value})")
    if tp.frame is not None:
        raise CamError(f"smooth_axes: '{tp.name}' WCS'de olmalı (frame = None)")
    R = tool.D / 2
    kure = tool.kind is ToolKind.BALL
    h = _Hesap(mesh, tool, Orientation("normal"), avoid, None)
    diziler = _diziler(tp)
    J_eski = _J(tp.moves, diziler)
    moves = list(tp.moves)
    for d in diziler:
        A = np.array([tp.moves[k].axis for k in d], dtype=float)
        B = _ortalama(A, w // 2)
        for k, a0, a1 in zip(d, A, B, strict=True):
            if float(np.linalg.norm(a1 - a0)) <= _ESIT:
                continue
            m = tp.moves[k]
            p0 = np.array(m.end, dtype=float)
            c0 = p0 + R * a0 if kure else p0
            try:
                if kin is not None:
                    inverse_axes(kin, a1)
                p1, carp = h.konum(_Surus(c0, a0, np.zeros(3)), a1, None)
            except CamError:
                continue
            if carp is not None:
                continue
            if kure:
                p1 = c0 - R * a1
            moves[k] = dataclasses.replace(
                m, end=tuple(float(v) for v in p1), axis=tuple(float(v) for v in a1)
            )
    J_yeni = _J(moves, diziler)
    if J_yeni > J_eski:
        return tp, J_eski, J_eski
    yeni = dataclasses.replace(tp, moves=moves)
    yeni.validate()
    return yeni, J_eski, J_yeni
