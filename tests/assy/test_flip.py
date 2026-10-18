"""Mate.flip (yön bayrağı) testleri: arayüz, artık, Jacobian ve çözüm.

Kural (assy/model.py, Mate): flip → yönlü referansın yönü ters alınır (b'nin; b NOKTA ise a'nın):
    PLANE–PLANE   : n_a + n_b  →  n_a − n_b      (yüz yüze → aynı yön)
    POINT–PLANE D : (p − q)·n − D  →  (p − q)·(−n) − D   (öbür taraf)
    ANGLE θ       : d_a·d_b − cos θ  →  d_a·(−d_b) − cos θ   (180° − θ)
Etkisiz kombinasyonlarda flip = True → AssyError.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from assy.mates import jacobian, residual
from assy.model import Assembly, AssyError, Component, Mate, MateKind, Ref, RefKind, transform
from assy.solver import solve

C, CON, DIS, ANG = MateKind.COINCIDENT, MateKind.CONCENTRIC, MateKind.DISTANCE, MateKind.ANGLE
TOL = 1e-9


def plane(comp, origin=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.PLANE, origin, normal)


def axis(comp, origin=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.AXIS, origin, direction)


def point(comp, origin=(0.0, 0.0, 0.0)) -> Ref:
    return Ref(comp, RefKind.POINT, origin)


def exp_so3(omega) -> np.ndarray:
    w = np.asarray(omega, dtype=float)
    th = float(np.linalg.norm(w))
    if th < 1e-15:
        return np.eye(3)
    k = w / th
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + math.sin(th) * K + (1.0 - math.cos(th)) * (K @ K)


def two_body(mate: Mate, T_B=None) -> Assembly:
    return Assembly(
        "iki",
        [Component("A", "a", fixed=True), Component("B", "b", T=np.eye(4) if T_B is None else T_B)],
        [mate],
    )


# ---------------------------------------------------------------- arayüz


def test_flip_defaults_false():
    assert Mate(C, plane("A"), plane("B", normal=(0, 0, -1))).flip is False


@pytest.mark.parametrize(
    "kind, a, b",
    [
        (CON, axis("A"), axis("B")),
        (C, axis("A"), axis("B")),
        (DIS, axis("A"), axis("B", (5, 0, 0))),
        (C, point("A"), point("B")),
        (DIS, point("A"), point("B", (5, 0, 0))),
        (C, point("A"), axis("B")),
        (C, point("A"), plane("B")),
        (C, plane("A"), point("B")),
    ],
)
def test_flip_without_effect_raises(kind, a, b):
    with pytest.raises(AssyError):
        Mate(kind, a, b, 5.0 if kind is DIS else 0.0, flip=True)


def test_flip_must_be_bool():
    with pytest.raises(AssyError):
        Mate(C, plane("A"), plane("B"), flip=1)


def test_flip_json_roundtrip_and_old_json():
    asm = two_body(Mate(DIS, plane("A"), plane("B"), 3.0, flip=True))
    d = json.loads(json.dumps(asm.to_dict()))
    assert d["mates"][0]["flip"] is True
    assert Assembly.from_dict(d).mates[0].flip is True
    del d["mates"][0]["flip"]  # bayraktan önce yazılmış JSON
    assert Assembly.from_dict(d).mates[0].flip is False


# ---------------------------------------------------------------- artık


def test_residual_plane_plane_aligned():
    """A: z = 0, n = +z; B: n = +z, t = (0, 0, 2) → flip: n_a − n_b = 0; (p_b − p_a)·n_a = 2."""
    asm = two_body(Mate(C, plane("A"), plane("B"), flip=True), transform(None, (0, 0, 2)))
    np.testing.assert_allclose(residual(asm, asm.mates[0]), [0, 0, 0, 2], atol=1e-15)


def test_residual_point_plane_other_side():
    """Düzlem A (z = 0, n = +z), nokta B z = −4: flip → (p − q)·(−n) − 4 = 0."""
    for a, b in ((point("B"), plane("A")), (plane("A"), point("B"))):
        asm = two_body(Mate(DIS, a, b, 4.0, flip=True), transform(None, (0, 0, -4)))
        np.testing.assert_allclose(residual(asm, asm.mates[0]), [0.0], atol=1e-15)


def test_residual_angle_supplement():
    """d_a = z, d_b = z döndürülmüş 60° → flip ile 120° sağlanır."""
    R = exp_so3(np.radians(60.0) * np.array([1.0, 0, 0]))
    asm = two_body(Mate(ANG, plane("A"), plane("B"), 120.0, flip=True), transform(R))
    np.testing.assert_allclose(residual(asm, asm.mates[0]), [0.0], atol=1e-15)


# ---------------------------------------------------------------- Jacobian (merkezi fark)


def fd_jacobian(asm: Assembly, mate: Mate, unknowns: list[str], h: float = 1e-6) -> np.ndarray:
    cols = []
    for name in unknowns:
        comp = asm.component(name)
        T0 = comp.T.copy()
        for k in range(6):
            r = []
            for s in (1.0, -1.0):
                x = np.zeros(6)
                x[k] = s * h
                T = T0.copy()
                T[:3, :3] = exp_so3(x[3:]) @ T0[:3, :3]
                T[:3, 3] = T0[:3, 3] + x[:3]
                comp.T = T
                r.append(residual(asm, mate))
            comp.T = T0
            cols.append((r[0] - r[1]) / (2 * h))
    return np.column_stack(cols)


FLIP_MATES = {
    "duzlem_duzlem": Mate(C, plane("A", (1, 2, 3), (0, 1, 1)), plane("B", (4, 0, 1), (1, 0, 0)), flip=True),
    "mesafe_duzlem": Mate(DIS, plane("A", (1, 2, 3)), plane("B", (4, 0, 1), (1, 1, 0)), 2.0, flip=True),
    "nokta_duzlem": Mate(DIS, point("A", (1, 2, 3)), plane("B", (0, 4, 1), (0, 1, 1)), 3.0, flip=True),
    "duzlem_nokta": Mate(DIS, plane("A", (0, 4, 1), (1, 0, 1)), point("B", (1, 2, 3)), 3.0, flip=True),
    "aci": Mate(ANG, axis("A", direction=(1, 1, 0)), plane("B", normal=(0, 1, 1)), 40.0, flip=True),
    "aci_180": Mate(ANG, plane("A"), axis("B", direction=(1, 0, 1)), 180.0, flip=True),
}


@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("name", list(FLIP_MATES))
def test_jacobian_matches_fd_with_flip(name, seed):
    rng = np.random.default_rng(seed)
    mate = FLIP_MATES[name]
    asm = Assembly(
        "jac",
        [
            Component("A", "a", T=transform(exp_so3(rng.normal(size=3)), rng.uniform(-20, 20, 3))),
            Component("B", "b", T=transform(exp_so3(rng.normal(size=3)), rng.uniform(-20, 20, 3))),
        ],
        [mate],
    )
    np.testing.assert_allclose(jacobian(asm, mate, ["A", "B"]), fd_jacobian(asm, mate, ["A", "B"]), atol=1e-6)


# ---------------------------------------------------------------- çözüm


def test_solve_plane_plane_aligned():
    """A'nın üst yüzü z = 10 (n = +z); B'nin yerel z = 0 yüzü (n = +z) aynı yönde çakışsın.
    Başlangıç 15° dönük, 5 mm kaçık. Beklenen: B'nin normali +z, yüz noktaları z = 10."""
    T0 = transform(exp_so3(np.radians(15.0) * np.array([1.0, 0, 0])), (2.0, 1.0, 15.0))
    asm = two_body(Mate(C, plane("A", (0, 0, 10)), plane("B"), flip=True), T0)
    T = solve(asm).T["B"]
    np.testing.assert_allclose(T[:3, :3] @ [0, 0, 1], [0, 0, 1], atol=TOL)
    for q in ((0, 0, 0), (10, 0, 0), (0, 10, 0)):
        assert (T[:3, :3] @ q + T[:3, 3])[2] == pytest.approx(10.0, abs=TOL)


def test_solve_point_plane_other_side():
    """Düzlem A: z = 10, n = +z. Nokta B'nin orijini; flip ile D = 4 → p_z = 10 − 4 = 6."""
    asm = two_body(Mate(DIS, point("B"), plane("A", (0, 0, 10)), 4.0, flip=True), transform(None, (0, 0, 9)))
    T = solve(asm).T["B"]
    assert T[2, 3] == pytest.approx(6.0, abs=TOL)


# ---------------------------------------------------------------- sonlu sayı kontrolleri (inceleme O3)


@pytest.mark.parametrize("value", [math.nan, math.inf])
def test_mate_value_must_be_finite(value):
    with pytest.raises(AssyError):
        Mate(DIS, plane("A"), plane("B"), value)


@pytest.mark.parametrize("origin, direction", [((math.nan, 0, 0), (0, 0, 1)), ((0, 0, 0), (0, math.nan, 1))])
def test_ref_must_be_finite(origin, direction):
    with pytest.raises(AssyError):
        Ref("A", RefKind.PLANE, origin, direction)
