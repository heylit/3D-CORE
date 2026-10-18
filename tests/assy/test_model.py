"""SPEC 00 — assy/model.py veri modeli testleri (K5–K7).

Testler sadece SPEC 00'daki arayüzden yazıldı; uygulama kodu okunmadı.
Dönüşüm kuralı (Craig, Bölüm 2): T = [[R, t], [0, 1]], p' = R p + t, d' = R d.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from assy.model import (
    Assembly,
    AssyError,
    Component,
    Mate,
    MateKind,
    Ref,
    RefKind,
    is_rigid,
    rot_x,
    rot_y,
    rot_z,
    transform,
)


def plane(comp: str, origin=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0)) -> Ref:
    """Kısa yazım: bileşen üzerinde düzlem referansı."""
    return Ref(comp, RefKind.PLANE, origin, direction)


def make_assembly() -> Assembly:
    """İki bileşenli montaj: sabit 'govde' ve z etrafında 90° dönmüş + (100,0,0) ötelenmiş 'mil'."""
    govde = Component(name="govde", part="braket", fixed=True)
    mil = Component(name="mil", part="mil20", T=transform(rot_z(90), (100.0, 0.0, 0.0)))
    mate = Mate(
        MateKind.CONCENTRIC,
        Ref("govde", RefKind.AXIS, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        Ref("mil", RefKind.AXIS, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    )
    return Assembly(name="montaj", components=[govde, mil], mates=[mate])


# ---------------------------------------------------------------- K5: transform, rot_*, is_rigid


def test_rot_90_exact():
    """90° dönüş matrisleri tam değer (SPEC K5): cos 90° = 0, sin 90° = 1, yuvarlama artığı yok."""
    np.testing.assert_array_equal(rot_x(90), [[1, 0, 0], [0, 0, -1], [0, 1, 0]])
    np.testing.assert_array_equal(rot_y(90), [[0, 0, 1], [0, 1, 0], [-1, 0, 0]])
    np.testing.assert_array_equal(rot_z(90), [[0, -1, 0], [1, 0, 0], [0, 0, 1]])


def test_rot_z_180_and_270_exact():
    """rot_z(180) = diag(-1,-1,1); rot_z(270) = rot_z(-90)."""
    np.testing.assert_array_equal(rot_z(180), [[-1, 0, 0], [0, -1, 0], [0, 0, 1]])
    np.testing.assert_array_equal(rot_z(270), [[0, 1, 0], [-1, 0, 0], [0, 0, 1]])


def test_rot_z_30_general():
    """rot_z(θ) = [[cos θ, -sin θ, 0], [sin θ, cos θ, 0], [0, 0, 1]], θ = 30°."""
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    np.testing.assert_allclose(rot_z(30), [[c, -s, 0], [s, c, 0], [0, 0, 1]], rtol=1e-12, atol=1e-15)


def test_transform_default_identity():
    T = transform()
    assert T.shape == (4, 4)
    np.testing.assert_array_equal(T, np.eye(4))


def test_transform_maps_point():
    """R = rot_z(90), t = (10, 0, 0): p = (1, 0, 0) → R p + t = (0, 1, 0) + (10, 0, 0) = (10, 1, 0)."""
    T = transform(rot_z(90), (10.0, 0.0, 0.0))
    np.testing.assert_allclose(T @ [1.0, 0.0, 0.0, 1.0], [10.0, 1.0, 0.0, 1.0], atol=1e-12)
    np.testing.assert_array_equal(T[3], [0, 0, 0, 1])


def test_is_rigid_true_cases():
    assert is_rigid(np.eye(4))
    assert is_rigid(transform(rot_x(37) @ rot_y(-12) @ rot_z(123), (5.0, -7.0, 2.5)))


def test_is_rigid_reflection_false():
    """Yansıma diag(1,1,-1): R^T R = I ama det R = -1 → rijit değil."""
    assert not is_rigid(transform(np.diag([1.0, 1.0, -1.0])))


def test_is_rigid_scale_and_last_row_false():
    assert not is_rigid(transform(2.0 * np.eye(3)))  # R^T R = 4 I ≠ I
    T = np.eye(4)
    T[3, 0] = 1.0  # son satır [0,0,0,1] değil
    assert not is_rigid(T)


# ---------------------------------------------------------------- K6: Ref, Component


def test_enum_values():
    assert RefKind.PLANE.value == "duzlem"
    assert RefKind.AXIS.value == "eksen"
    assert RefKind.POINT.value == "nokta"
    assert MateKind.COINCIDENT.value == "cakisik"
    assert MateKind.CONCENTRIC.value == "es_eksen"
    assert MateKind.DISTANCE.value == "mesafe"
    assert MateKind.ANGLE.value == "aci"


def test_ref_direction_normalized():
    """(3, 4, 0) / 5 = (0.6, 0.8, 0); (0, 0, 7) / 7 = (0, 0, 1)."""
    r = Ref("govde", RefKind.PLANE, (1.0, 2.0, 3.0), (3.0, 4.0, 0.0))
    np.testing.assert_allclose(np.asarray(r.direction, dtype=float), [0.6, 0.8, 0.0], rtol=1e-12)
    r2 = Ref("govde", RefKind.AXIS, (0.0, 0.0, 0.0), (0.0, 0.0, 7.0))
    np.testing.assert_allclose(np.asarray(r2.direction, dtype=float), [0.0, 0.0, 1.0], rtol=1e-12)


def test_ref_default_direction_z():
    r = Ref("govde", RefKind.POINT, (1.0, 1.0, 1.0))
    np.testing.assert_allclose(np.asarray(r.direction, dtype=float), [0.0, 0.0, 1.0], rtol=1e-12)


def test_ref_zero_direction_rejected():
    with pytest.raises(AssyError):
        Ref("govde", RefKind.PLANE, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def test_component_defaults():
    c = Component(name="a", part="p")
    np.testing.assert_array_equal(c.T, np.eye(4))
    assert c.fixed is False


@pytest.mark.parametrize(
    "T",
    [
        transform(np.diag([1.0, -1.0, 1.0])),  # yansıma, det = -1
        transform(1.5 * np.eye(3)),  # ölçek
    ],
)
def test_component_non_rigid_rejected(T):
    with pytest.raises(AssyError):
        Component(name="a", part="p", T=T)


# ---------------------------------------------------------------- K7: Mate, Assembly


@pytest.mark.parametrize(
    "kind, value",
    [
        (MateKind.DISTANCE, -0.1),  # mesafe < 0
        (MateKind.ANGLE, -1.0),  # açı < 0°
        (MateKind.ANGLE, 180.5),  # açı > 180°
    ],
)
def test_mate_value_out_of_range(kind, value):
    """Hata kurulumda veya validate()'te verilebilir; ikisi de kabul."""
    a, b = plane("govde"), plane("mil")
    with pytest.raises(AssyError):
        m = Mate(kind, a, b, value)
        asm = make_assembly()
        asm.mates.append(m)
        asm.validate()


@pytest.mark.parametrize(
    "kind, value", [(MateKind.DISTANCE, 0.0), (MateKind.ANGLE, 0.0), (MateKind.ANGLE, 180.0)]
)
def test_mate_value_limits_accepted(kind, value):
    asm = make_assembly()
    asm.mates.append(Mate(kind, plane("govde"), plane("mil"), value))
    asm.validate()


def test_valid_assembly_and_component_lookup():
    asm = make_assembly()
    asm.validate()
    assert asm.component("mil").part == "mil20"


def test_component_lookup_unknown():
    with pytest.raises(AssyError):
        make_assembly().component("yok")


def test_mates_default_empty_not_shared():
    """Varsayılan mates boş liste; iki montaj aynı listeyi paylaşmaz."""
    a1 = Assembly(name="a1", components=[Component(name="x", part="p")])
    a2 = Assembly(name="a2", components=[Component(name="y", part="p")])
    assert a1.mates == []
    a1.mates.append(Mate(MateKind.COINCIDENT, plane("x"), plane("y")))
    assert a2.mates == []


def test_validate_duplicate_component():
    asm = make_assembly()
    asm.components.append(Component(name="mil", part="baska"))
    with pytest.raises(AssyError):
        asm.validate()


def test_validate_mate_unknown_component():
    asm = make_assembly()
    asm.mates.append(Mate(MateKind.COINCIDENT, plane("govde"), plane("yok")))
    with pytest.raises(AssyError):
        asm.validate()


def test_validate_mate_same_component():
    asm = make_assembly()
    asm.mates.append(Mate(MateKind.DISTANCE, plane("mil"), plane("mil", (0.0, 0.0, 5.0)), 5.0))
    with pytest.raises(AssyError):
        asm.validate()


def test_world_ref_known_transform():
    """mil: R = rot_z(90), t = (100,0,0). Yerel origin (10,0,0) → R·o + t = (0,10,0) + (100,0,0) = (100,10,0);
    yerel yön (1,0,0) → R·d = (0,1,0)."""
    asm = make_assembly()
    o, d = asm.world(Ref("mil", RefKind.PLANE, (10.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
    np.testing.assert_allclose(o, [100.0, 10.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(d, [0.0, 1.0, 0.0], atol=1e-12)


def test_world_ref_identity_component():
    """govde T = I: dünya = yerel; yön birim vektöre normalize (0,0,2) → (0,0,1)."""
    o, d = make_assembly().world(Ref("govde", RefKind.AXIS, (1.0, 2.0, 3.0), (0.0, 0.0, 2.0)))
    np.testing.assert_allclose(o, [1.0, 2.0, 3.0], atol=1e-12)
    np.testing.assert_allclose(d, [0.0, 0.0, 1.0], atol=1e-12)


def test_dict_roundtrip_json():
    """to_dict → JSON metni → from_dict → to_dict birebir; T ve tipler korunur."""
    asm = make_assembly()
    asm.mates.append(Mate(MateKind.ANGLE, plane("govde", direction=(1.0, 0.0, 0.0)), plane("mil"), 45.0))
    d = asm.to_dict()
    asm2 = Assembly.from_dict(json.loads(json.dumps(d)))
    assert asm2.to_dict() == d
    np.testing.assert_array_equal(asm2.component("mil").T, asm.component("mil").T)
    assert asm2.component("govde").fixed is True
    assert asm2.mates[1].kind is MateKind.ANGLE
    assert asm2.mates[1].a.kind is RefKind.PLANE
    assert asm2.mates[1].value == pytest.approx(45.0, rel=1e-12)
