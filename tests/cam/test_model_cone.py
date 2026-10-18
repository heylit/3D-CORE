"""Konik takım arayüz eki testleri (SPEC 06b arayüz eki): ToolKind.CONE ve Tool.tip_angle.

Testler yalnızca onaylanan davranış sözleşmesinden yazıldı; alanın uygulama kodu okunmadı.

Davranış:
- ToolKind.CONE = "konik".
- tip_angle [derece, tam uç açısı φ], varsayılan None.
- CONE'da zorunlu; DRILL'de isteğe bağlı; FLAT ve BALL'da verilirse CamError.
- Sonlu ve 0 < φ < 180.
- CONE'da corner_r == 0 ve kenar yüksekliği (D/2)/tan(φ/2) ≤ flute_length.
- to_dict "tip_angle" yazar; from_dict'te anahtar isteğe bağlı.
"""

from __future__ import annotations

import json
import math

import pytest

from cam.model import CamError, Tool, ToolKind


def cone(D: float = 6.0, tip_angle: float | None = 90.0, flute_length: float = 20.0, **kw) -> Tool:
    """Konik takım; varsayılan Ø6, 90° uç açısı (kenar yüksekliği 3 mm)."""
    return Tool(
        id=7, name="konik6", kind=ToolKind.CONE, D=D, flute_length=flute_length, tip_angle=tip_angle, **kw
    )


def h_c(D: float, phi: float) -> float:
    """Koninin kenar yüksekliği (D/2)·cot(φ/2)."""
    return (D / 2) / math.tan(math.radians(phi) / 2)


# ---------------------------------------------------------------- tip


def test_cone_kind_value():
    assert ToolKind.CONE.value == "konik"
    assert ToolKind("konik") is ToolKind.CONE


def test_cone_kind_as_string():
    t = Tool(id=1, name="k", kind="konik", D=6.0, flute_length=20.0, tip_angle=90.0)
    assert t.kind is ToolKind.CONE


# ---------------------------------------------------------------- CONE


@pytest.mark.parametrize("phi", [30.0, 60.0, 90.0, 120.0, 179.0])
def test_cone_valid_angles(phi):
    t = cone(tip_angle=phi)
    assert t.tip_angle == pytest.approx(phi)
    assert t.corner_r == 0.0


def test_cone_requires_tip_angle():
    with pytest.raises(CamError):
        cone(tip_angle=None)


@pytest.mark.parametrize("phi", [0.0, 180.0, -30.0, 200.0, math.nan, math.inf, -math.inf])
def test_cone_tip_angle_out_of_range(phi):
    with pytest.raises(CamError):
        cone(tip_angle=phi)


@pytest.mark.parametrize("r", [0.5, 3.0])
def test_cone_corner_r_rejected(r):
    with pytest.raises(CamError):
        cone(corner_r=r)


@pytest.mark.parametrize(("D", "phi"), [(6.0, 90.0), (6.0, 60.0), (10.0, 30.0), (2.0, 120.0)])
def test_cone_edge_height_fits_flute(D, phi):
    # kenar yüksekliği kesici boyun hemen altında → kabul
    t = cone(D=D, tip_angle=phi, flute_length=h_c(D, phi) * 1.001)
    assert t.tip_angle == pytest.approx(phi)


@pytest.mark.parametrize(("D", "phi"), [(6.0, 90.0), (6.0, 60.0), (10.0, 30.0), (2.0, 120.0)])
def test_cone_edge_height_exceeds_flute(D, phi):
    # kenar yüksekliği kesici boydan uzun → CamError
    with pytest.raises(CamError):
        cone(D=D, tip_angle=phi, flute_length=h_c(D, phi) * 0.999)


def test_cone_sharp_angle_long_edge():
    # Ø10, 10° uç: h_c = 5·cot(5°) ≈ 57.15 mm > 20 mm
    with pytest.raises(CamError):
        cone(D=10.0, tip_angle=10.0, flute_length=20.0)


# ---------------------------------------------------------------- diğer tipler


def test_default_none_for_mills():
    assert Tool(id=1, name="f", kind=ToolKind.FLAT, D=6.0, flute_length=20.0).tip_angle is None
    assert Tool(id=1, name="b", kind=ToolKind.BALL, D=6.0, flute_length=20.0).tip_angle is None


@pytest.mark.parametrize("kind", [ToolKind.FLAT, ToolKind.BALL])
def test_mills_reject_tip_angle(kind):
    with pytest.raises(CamError):
        Tool(id=1, name="f", kind=kind, D=6.0, flute_length=20.0, tip_angle=90.0)


def test_drill_tip_angle_optional():
    assert Tool(id=1, name="m", kind=ToolKind.DRILL, D=6.0, flute_length=40.0).tip_angle is None
    t = Tool(id=1, name="m", kind=ToolKind.DRILL, D=6.0, flute_length=40.0, tip_angle=118.0)
    assert t.tip_angle == pytest.approx(118.0)


@pytest.mark.parametrize("phi", [0.0, 180.0, -118.0, math.nan, math.inf])
def test_drill_tip_angle_out_of_range(phi):
    with pytest.raises(CamError):
        Tool(id=1, name="m", kind=ToolKind.DRILL, D=6.0, flute_length=40.0, tip_angle=phi)


# ---------------------------------------------------------------- sözlük


def test_to_dict_writes_tip_angle():
    assert cone().to_dict()["tip_angle"] == pytest.approx(90.0)
    d = Tool(id=1, name="f", kind=ToolKind.FLAT, D=6.0, flute_length=20.0).to_dict()
    assert "tip_angle" in d
    assert d["tip_angle"] is None


def test_cone_roundtrip():
    t = cone(tip_angle=60.0, flute_length=10.0)
    t2 = Tool.from_dict(json.loads(json.dumps(t.to_dict())))
    assert t2.kind is ToolKind.CONE
    assert t2.tip_angle == pytest.approx(60.0)
    assert t2.to_dict() == t.to_dict()


def test_drill_roundtrip():
    t = Tool(id=2, name="m", kind=ToolKind.DRILL, D=8.0, flute_length=40.0, tip_angle=118.0)
    t2 = Tool.from_dict(json.loads(json.dumps(t.to_dict())))
    assert t2.tip_angle == pytest.approx(118.0)


@pytest.mark.parametrize("kind", [ToolKind.FLAT, ToolKind.BALL, ToolKind.DRILL])
def test_from_dict_missing_key_is_none(kind):
    d = Tool(id=1, name="t", kind=kind, D=6.0, flute_length=20.0).to_dict()
    del d["tip_angle"]
    assert Tool.from_dict(d).tip_angle is None


def test_from_dict_cone_missing_key_rejected():
    d = cone().to_dict()
    del d["tip_angle"]
    with pytest.raises(CamError):
        Tool.from_dict(d)


def test_from_dict_cone_bad_angle_rejected():
    d = cone().to_dict()
    d["tip_angle"] = 180.0
    with pytest.raises(CamError):
        Tool.from_dict(d)


def test_from_dict_flat_with_angle_rejected():
    d = Tool(id=1, name="f", kind=ToolKind.FLAT, D=6.0, flute_length=20.0).to_dict()
    d["tip_angle"] = 90.0
    with pytest.raises(CamError):
        Tool.from_dict(d)
