"""SPEC 00 — cam/model.py veri modeli testleri (K1–K4).

Testler sadece SPEC 00'daki arayüzden yazıldı; uygulama kodu okunmadı.
Yay kuralı (ISO 6983, Smid Bölüm 29): G2 = saat yönü, G3 = saat yönü tersi (+Z'den bakınca),
merkez XY'de mutlak koordinat.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from cam.model import CamError, Move, MoveType, Stock, Tool, ToolKind, Toolpath

R = 10.0  # Yay testlerinde kullanılan yarıçap [mm]


def make_tool() -> Tool:
    """Ø6 düz parmak freze."""
    return Tool(id=1, name="freze6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)


def make_path(moves: list[Move], start=(R, 0.0, 0.0), rpm: float = 12_000.0) -> Toolpath:
    """Verilen hareketlerle takım yolu kurar (varsayılan başlangıç (R, 0, 0))."""
    return Toolpath(name="yol", tool=make_tool(), start=start, moves=moves, rpm=rpm)


# ---------------------------------------------------------------- K1: Tool, Stock


def test_enum_values():
    # SPEC 00 arayüzündeki sabit değerler
    assert ToolKind.FLAT.value == "duz"
    assert ToolKind.BALL.value == "kuresel"
    assert ToolKind.DRILL.value == "matkap"
    assert MoveType.RAPID.value == "G0"
    assert MoveType.LINEAR.value == "G1"
    assert MoveType.ARC_CW.value == "G2"
    assert MoveType.ARC_CCW.value == "G3"


def test_ball_tool_corner_r_is_half_D():
    """Küresel uçta köşe yarıçapı otomatik D/2 olur: 8 / 2 = 4."""
    t = Tool(id=2, name="kuresel8", kind=ToolKind.BALL, D=8.0, flute_length=25.0)
    assert t.corner_r == pytest.approx(4.0, rel=1e-12)


def test_flat_tool_defaults_and_bull_nose_limit():
    """Düz uçta varsayılan corner_r = 0; sınır değer corner_r = D/2 kabul edilir."""
    assert make_tool().corner_r == 0.0
    t = Tool(id=3, name="torus", kind=ToolKind.FLAT, D=10.0, flute_length=30.0, corner_r=5.0)
    assert t.corner_r == pytest.approx(5.0, rel=1e-12)


@pytest.mark.parametrize(
    "D, flute_length, corner_r",
    [
        (0.0, 20.0, 0.0),  # D = 0
        (-6.0, 20.0, 0.0),  # D < 0
        (6.0, 0.0, 0.0),  # flute_length = 0
        (6.0, -1.0, 0.0),  # flute_length < 0
        (6.0, 20.0, -0.1),  # corner_r < 0
        (6.0, 20.0, 3.001),  # corner_r > D/2 = 3
    ],
)
def test_tool_invalid_rejected(D, flute_length, corner_r):
    with pytest.raises(CamError):
        Tool(id=1, name="x", kind=ToolKind.FLAT, D=D, flute_length=flute_length, corner_r=corner_r)


def test_stock_size_and_volume():
    """Ham parça (-5..45) x (0..30) x (-20..0): boyut (50, 30, 20), hacim 50*30*20 = 30000 mm³."""
    s = Stock(-5.0, 0.0, -20.0, 45.0, 30.0, 0.0)
    np.testing.assert_allclose(s.size, [50.0, 30.0, 20.0], rtol=1e-12)
    assert s.volume == pytest.approx(30_000.0, rel=1e-12)


@pytest.mark.parametrize(
    "bounds",
    [
        (0, 0, 0, 0, 10, 10),  # xmax = xmin
        (0, 0, 0, 10, -1, 10),  # ymax < ymin
        (0, 0, 0, 10, 10, 0),  # zmax = zmin
    ],
)
def test_stock_invalid_rejected(bounds):
    with pytest.raises(CamError):
        Stock(*bounds)


# ---------------------------------------------------------------- K2: Toolpath.validate


def test_valid_path_passes_and_rapid_needs_no_feed():
    """G0 ilerleme istemez; geçerli bir yol hata vermez."""
    tp = make_path(
        [
            Move(MoveType.RAPID, (R, 0.0, 5.0)),
            Move(MoveType.LINEAR, (R, 0.0, -1.0), feed=300.0),
            Move(MoveType.ARC_CCW, (0.0, R, -1.0), feed=800.0, center=(0.0, 0.0)),
        ]
    )
    tp.validate()


@pytest.mark.parametrize("rpm", [0.0, -1000.0])
def test_validate_rpm_not_positive(rpm):
    with pytest.raises(CamError):
        make_path([Move(MoveType.LINEAR, (0.0, 0.0, 0.0), feed=100.0)], rpm=rpm).validate()


@pytest.mark.parametrize(
    "move",
    [
        Move(MoveType.LINEAR, (0.0, 0.0, 0.0)),  # G1 feed yok
        Move(MoveType.LINEAR, (0.0, 0.0, 0.0), feed=0.0),  # G1 feed = 0
        Move(MoveType.LINEAR, (0.0, 0.0, 0.0), feed=-50.0),  # G1 feed < 0
        Move(MoveType.ARC_CW, (-R, 0.0, 0.0), center=(0.0, 0.0)),  # G2 feed yok
        Move(MoveType.ARC_CCW, (-R, 0.0, 0.0), feed=0.0, center=(0.0, 0.0)),  # G3 feed = 0
    ],
)
def test_validate_feed_missing_or_not_positive(move):
    with pytest.raises(CamError):
        make_path([move]).validate()


@pytest.mark.parametrize("kind", [MoveType.ARC_CW, MoveType.ARC_CCW])
def test_validate_arc_without_center(kind):
    with pytest.raises(CamError):
        make_path([Move(kind, (-R, 0.0, 0.0), feed=500.0)]).validate()


def test_validate_arc_radius_mismatch():
    """Başlangıç yarıçapı 10, bitiş yarıçapı 10.001: fark 1e-3 > 1e-6 mm → hata."""
    with pytest.raises(CamError):
        make_path([Move(MoveType.ARC_CCW, (0.0, R + 1e-3, 0.0), feed=500.0, center=(0.0, 0.0))]).validate()


def test_validate_arc_radius_within_tolerance():
    """Fark 1e-8 mm < 1e-6 mm → kabul edilir."""
    make_path([Move(MoveType.ARC_CCW, (0.0, R + 1e-8, 0.0), feed=500.0, center=(0.0, 0.0))]).validate()


def test_validate_arc_zero_radius():
    """Başlangıç = merkez = bitiş: yarıçap 0 < 1e-9 → hata."""
    with pytest.raises(CamError):
        make_path(
            [Move(MoveType.ARC_CW, (0.0, 0.0, 0.0), feed=500.0, center=(0.0, 0.0))], start=(0.0, 0.0, 0.0)
        ).validate()


# ---------------------------------------------------------------- K3: points, length


def test_points_shape_and_values():
    """points() = başlangıç + her hareketin bitişi → (n+1, 3)."""
    tp = make_path(
        [
            Move(MoveType.RAPID, (0.0, 0.0, 5.0)),
            Move(MoveType.LINEAR, (3.0, 4.0, 5.0), feed=200.0),
        ],
        start=(0.0, 0.0, 10.0),
    )
    np.testing.assert_allclose(tp.points(), [[0, 0, 10], [0, 0, 5], [3, 4, 5]], rtol=1e-12)


def test_length_linear():
    """(0,0,0) → (3,4,0): 5 (3-4-5 üçgeni); → (3,4,12): +12. Toplam 17."""
    tp = make_path(
        [
            Move(MoveType.LINEAR, (3.0, 4.0, 0.0), feed=100.0),
            Move(MoveType.LINEAR, (3.0, 4.0, 12.0), feed=100.0),
        ],
        start=(0.0, 0.0, 0.0),
    )
    assert tp.length() == pytest.approx(17.0, rel=1e-12)


def test_length_quarter_arc_ccw():
    """(R,0) → (0,R), G3 (saat yönü tersi), merkez (0,0): Δθ = +π/2 → s = πR/2."""
    tp = make_path([Move(MoveType.ARC_CCW, (0.0, R, 0.0), feed=500.0, center=(0.0, 0.0))])
    assert tp.length() == pytest.approx(math.pi * R / 2, rel=1e-12)


def test_length_three_quarter_arc_cw():
    """(R,0) → (0,R), G2 (saat yönü): 0° → -270°, |Δθ| = 3π/2 → s = 3πR/2. Yön kuralı testi."""
    tp = make_path([Move(MoveType.ARC_CW, (0.0, R, 0.0), feed=500.0, center=(0.0, 0.0))])
    assert tp.length() == pytest.approx(3 * math.pi * R / 2, rel=1e-12)


@pytest.mark.parametrize("kind", [MoveType.ARC_CW, MoveType.ARC_CCW])
def test_length_full_circle(kind):
    """Başlangıç = bitiş (XY) → tam daire, |Δθ| = 2π → s = 2πR."""
    tp = make_path([Move(kind, (R, 0.0, 0.0), feed=500.0, center=(0.0, 0.0))])
    assert tp.length() == pytest.approx(2 * math.pi * R, rel=1e-12)


def test_length_helix():
    """Tam tur, Z 0 → -5: s = sqrt((2πR)² + h²) (SPEC 00 Teori)."""
    h = 5.0
    tp = make_path([Move(MoveType.ARC_CCW, (R, 0.0, -h), feed=500.0, center=(0.0, 0.0))])
    assert tp.length() == pytest.approx(math.sqrt((2 * math.pi * R) ** 2 + h**2), rel=1e-12)


def test_length_type_filter():
    """G0: 10 mm (Z 10 → 0); G1: 3-4-5 → 5 mm. Filtre sadece istenen tipleri toplar."""
    tp = make_path(
        [
            Move(MoveType.RAPID, (0.0, 0.0, 0.0)),
            Move(MoveType.LINEAR, (3.0, 4.0, 0.0), feed=100.0),
        ],
        start=(0.0, 0.0, 10.0),
    )
    assert tp.length() == pytest.approx(15.0, rel=1e-12)
    assert tp.length({MoveType.RAPID}) == pytest.approx(10.0, rel=1e-12)
    assert tp.length({MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW}) == pytest.approx(5.0, rel=1e-12)


# ---------------------------------------------------------------- K4: bbox, to_dict / from_dict


def test_bbox_half_circle_ccw_includes_top():
    """(10,0) → (-10,0) G3, merkez (0,0): yay (0,10)'dan geçer → max y = 10, min y = 0."""
    tp = make_path([Move(MoveType.ARC_CCW, (-R, 0.0, 0.0), feed=500.0, center=(0.0, 0.0))])
    lo, hi = tp.bbox()
    np.testing.assert_allclose(lo, [-R, 0.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(hi, [R, R, 0.0], atol=1e-12)


def test_bbox_half_circle_cw_includes_bottom():
    """(10,0) → (-10,0) G2, merkez (0,0): yay (0,-10)'dan geçer → min y = -10, max y = 0."""
    tp = make_path([Move(MoveType.ARC_CW, (-R, 0.0, 0.0), feed=500.0, center=(0.0, 0.0))])
    lo, hi = tp.bbox()
    np.testing.assert_allclose(lo, [-R, -R, 0.0], atol=1e-12)
    np.testing.assert_allclose(hi, [R, 0.0, 0.0], atol=1e-12)


def test_bbox_linear_includes_z():
    """Doğrusal yolda sınır kutusu nokta min / max'ıdır."""
    tp = make_path(
        [
            Move(MoveType.RAPID, (-2.0, 7.0, 5.0)),
            Move(MoveType.LINEAR, (4.0, -3.0, -1.5), feed=100.0),
        ],
        start=(0.0, 0.0, 0.0),
    )
    lo, hi = tp.bbox()
    np.testing.assert_allclose(lo, [-2.0, -3.0, -1.5], atol=1e-12)
    np.testing.assert_allclose(hi, [4.0, 7.0, 5.0], atol=1e-12)


def test_dict_roundtrip_json():
    """to_dict → JSON metni → from_dict → to_dict birebir aynı; tipler korunur."""
    tool = Tool(id=7, name="kuresel6", kind=ToolKind.BALL, D=6.0, flute_length=18.0)
    tp = Toolpath(
        name="kontur",
        tool=tool,
        start=(R, 0.0, 5.0),
        moves=[
            Move(MoveType.RAPID, (R, 0.0, 1.0)),
            Move(MoveType.LINEAR, (R, 0.0, -2.0), feed=250.0),
            Move(MoveType.ARC_CW, (-R, 0.0, -2.0), feed=900.0, center=(0.0, 0.0)),
            Move(MoveType.ARC_CCW, (R, 0.0, -3.0), feed=900.0, center=(0.0, 0.0)),
        ],
        rpm=15_000.0,
    )
    d = tp.to_dict()
    tp2 = Toolpath.from_dict(json.loads(json.dumps(d)))
    assert tp2.to_dict() == d
    assert tp2.tool.kind is ToolKind.BALL
    assert tp2.tool.corner_r == pytest.approx(3.0, rel=1e-12)
    assert [m.type for m in tp2.moves] == [m.type for m in tp.moves]
    assert tp2.moves[0].feed is None and tp2.moves[0].center is None
    assert tp2.length() == pytest.approx(tp.length(), rel=1e-12)


# ---------------------------------------------------------------- sonlu sayı kontrolleri (inceleme O3)

NAN, INF = math.nan, math.inf


@pytest.mark.parametrize(
    "make",
    [
        lambda: Tool(1, "t", ToolKind.FLAT, D=NAN, flute_length=20.0),
        lambda: Tool(1, "t", ToolKind.FLAT, D=INF, flute_length=20.0),
        lambda: Tool(1, "t", ToolKind.FLAT, D=6.0, flute_length=NAN),
        lambda: Tool(1, "t", ToolKind.FLAT, D=6.0, flute_length=INF),
        lambda: Tool(1, "t", ToolKind.FLAT, D=6.0, flute_length=20.0, corner_r=NAN),
        lambda: Stock(0, 0, 0, INF, 10, 10),
        lambda: Stock(-INF, 0, 0, 10, 10, 10),
        lambda: Move(MoveType.LINEAR, (0.0, NAN, 0.0), feed=100.0),
        lambda: Move(MoveType.RAPID, (INF, 0.0, 0.0)),
        lambda: Move(MoveType.LINEAR, (1.0, 0.0, 0.0), feed=INF),
        lambda: Move(MoveType.ARC_CW, (1.0, 0.0, 0.0), feed=100.0, center=(NAN, 0.0)),
    ],
)
def test_non_finite_rejected(make):
    with pytest.raises(CamError):
        make()


def test_toolpath_start_must_be_finite():
    t = Tool(1, "t", ToolKind.FLAT, D=6.0, flute_length=20.0)
    with pytest.raises(CamError):
        Toolpath("y", t, start=(0.0, 0.0, NAN), rpm=1000.0)


def test_validate_catches_nan_set_after_construction():
    """Hareket oluşturulduktan sonra yerinde bozulursa validate() yakalar (yazıcıya kadar beklemez)."""
    t = Tool(1, "t", ToolKind.FLAT, D=6.0, flute_length=20.0)
    moves = [Move(MoveType.LINEAR, (1, 0, 0), feed=100)]
    tp = Toolpath("y", t, start=(0.0, 0.0, 5.0), rpm=1000.0, moves=moves)
    tp.validate()
    tp.moves[0].end = (1.0, NAN, 0.0)
    with pytest.raises(CamError):
        tp.validate()
    tp.moves[0].end = (1.0, 0.0, 0.0)
    tp.rpm = INF
    with pytest.raises(CamError):
        tp.validate()
