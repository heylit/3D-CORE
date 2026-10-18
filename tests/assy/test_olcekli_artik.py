"""
Ölçekli artıklar (inceleme bulgusu O1): yön artıkları birimsiz, konum artıkları mm.
Durma ölçütü ikisini aynı ölçekte karşılaştırmalı: yön artığı karakteristik uzunluk L ile
çarpılır (L = referans noktalarının dünya çapı, en az 1 mm). Böylece tol "mm" demektir:
1000 mm'lik parçada 1e-4 rad'lık yön hatası uçta 0,1 mm'dir ve tol = 1e-3 mm ile kabul edilemez.
"""

from __future__ import annotations

import math

import numpy as np

from assy.mates import angular_rows
from assy.model import Assembly, Component, Mate, MateKind, Ref, RefKind
from assy.solver import solve


def _rot_x(phi: float) -> np.ndarray:
    c, s = math.cos(phi), math.sin(phi)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _yuz_yuze_egik(phi: float, L: float) -> Assembly:
    """A: z = 0 düzlemi (orijinde). B: (0, L, 0)'dan geçen, normali −z düzlem; B o nokta
    etrafında x ekseninde phi kadar eğik. Nokta tam yerinde, sadece yön hatalı."""
    p = np.array([0.0, L, 0.0])
    T = np.eye(4)
    T[:3, :3] = _rot_x(phi)
    T[:3, 3] = p - _rot_x(phi) @ p
    return Assembly(
        "egik",
        [Component("A", "a", fixed=True), Component("B", "b", T=T)],
        [
            Mate(
                MateKind.COINCIDENT,
                Ref("A", RefKind.PLANE, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
                Ref("B", RefKind.PLANE, tuple(p), (0.0, 0.0, -1.0)),
            )
        ],
    )


def test_angular_error_scaled_by_part_size():
    L, tol = 1000.0, 1e-3
    asm = _yuz_yuze_egik(1e-4, L)
    res = solve(asm, tol=tol)
    asm2 = _yuz_yuze_egik(0.0, L)
    res.apply(asm2)
    n_b = res.T["B"][:3, :3] @ np.array([0.0, 0.0, -1.0])
    hata = math.acos(min(1.0, float(-n_b[2])))
    assert hata * L <= tol


def test_angular_rows_mark_direction_only_rows():
    """Düzlem–düzlem: ilk 3 satır (n_a + n_b) yön, son satır mesafe (mm)."""
    asm = _yuz_yuze_egik(0.0, 10.0)
    np.testing.assert_array_equal(angular_rows(asm, asm.mates[0]), [True, True, True, False])
