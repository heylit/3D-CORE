"""G-code yazıcı, çok eksen arayüz ekiyle gelen yolları reddeder (SPEC 41 arayüzü).

Testler yalnızca onaylanan davranış sözleşmesinden yazıldı; uygulama kodu okunmadı.

Davranış: 3 eksen yazıcı (cam.gcode.write) iş düzlemi (frame) taşıyan ya da takım ekseni +z dışında
olan bir hareketi bulunan yolu CamError ile reddeder. axis = (0, 0, 1) ile None aynı programı verir.
"""

from __future__ import annotations

import math

import pytest

from cam.gcode import FANUC, GRBL, write
from cam.model import CamError, Frame, Move, MoveType, Tool, ToolKind, Toolpath

G0, G1, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CCW

DIALECTS = pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["grbl", "fanuc"])

I3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def yol(axis=None, frame=None) -> Toolpath:
    tool = Tool(id=1, name="f6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)
    moves = [
        Move(G1, (0.0, 0.0, -1.0), feed=200.0, axis=axis),
        Move(G1, (10.0, 0.0, -1.0), feed=500.0, axis=axis),
        Move(G1, (10.0, 10.0, -1.0), feed=500.0, axis=axis),
        Move(G0, (10.0, 10.0, 5.0), axis=axis),
    ]
    return Toolpath(name="kare", tool=tool, start=(0.0, 0.0, 5.0), moves=moves, rpm=10000.0, frame=frame)


@DIALECTS
def test_plain_path_written(dialect):
    assert "G1" in write([yol()], dialect)


@DIALECTS
def test_explicit_z_axis_same_as_none(dialect):
    assert write([yol(axis=(0.0, 0.0, 1.0))], dialect) == write([yol()], dialect)


@DIALECTS
@pytest.mark.parametrize("axis", [(0.6, 0.0, 0.8), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)])
def test_tilted_axis_rejected(dialect, axis):
    with pytest.raises(CamError):
        write([yol(axis=axis)], dialect)


@DIALECTS
def test_single_tilted_move_rejected(dialect):
    tp = yol()
    tp.moves[2] = Move(G1, (10.0, 10.0, -1.0), feed=500.0, axis=(0.0, 0.6, 0.8))
    with pytest.raises(CamError):
        write([tp], dialect)


@DIALECTS
@pytest.mark.parametrize(
    "frame",
    [
        pytest.param(Frame(origin=(0.0, 0.0, 0.0), R=I3), id="birim"),
        pytest.param(Frame(origin=(10.0, 0.0, 0.0), R=I3), id="kaydirilmis"),
        pytest.param(
            Frame(
                origin=(0.0, 0.0, 0.0),
                R=(
                    (1.0, 0.0, 0.0),
                    (0.0, math.cos(0.5), -math.sin(0.5)),
                    (0.0, math.sin(0.5), math.cos(0.5)),
                ),
            ),
            id="egik",
        ),
    ],
)
def test_frame_rejected(dialect, frame):
    with pytest.raises(CamError):
        write([yol(frame=frame)], dialect)


@DIALECTS
def test_frame_in_second_op_rejected(dialect):
    with pytest.raises(CamError):
        write([yol(), yol(frame=Frame(origin=(0.0, 0.0, 0.0), R=I3))], dialect)
