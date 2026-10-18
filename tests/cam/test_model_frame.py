"""Çok eksen arayüz eki testleri (SPEC 41 arayüzü): Frame, Move.axis, Toolpath.frame.

Testler yalnızca onaylanan davranış sözleşmesinden ve /mnt/project-files/arayuz/cok-eksen-arayuz-onerisi.md
önerisinden yazıldı; uygulama kodu okunmadı.

Davranış:
- Frame(origin, R): R 3x3, sütunları yerel x, y, z eksenlerinin WCS birim vektörleri;
  p_wcs = origin + R·p_yerel. ‖RᵀR − I‖ ≤ 1e-9 ve det R > 0, aksi CamError (normalleştirme yok).
- to_world, to_local, to_world_vec, to_local_vec, to_dict / from_dict.
- Move.axis birim vektör (| ‖n‖ − 1 | ≤ 1e-9) ya da None.
- Toolpath.frame Frame ya da None. Torna yolunda axis → CamError; yayda axis +z dışında → CamError.
- to_dict "frame" ve her hareket için "axis" yazar; bu anahtarlar olmayan eski sözlükler yüklenir.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from cam.model import (
    CamError,
    FeedMode,
    Frame,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Tool,
    ToolKind,
    Toolpath,
)

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW

I3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def rot_z(deg: float) -> tuple:
    """z ekseni etrafında dönme matrisi (satır satır)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def rot_x(deg: float) -> tuple:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def egik_frame() -> Frame:
    """x etrafında 30°, sonra z etrafında 45° döndürülmüş, (10, 20, 5)'e taşınmış düzlem."""
    R = np.array(rot_z(45.0)) @ np.array(rot_x(30.0))
    return Frame(origin=(10.0, 20.0, 5.0), R=tuple(tuple(r) for r in R))


def freze() -> Tool:
    return Tool(id=1, name="f6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)


def xy_yolu(moves=None, **kw) -> Toolpath:
    if moves is None:
        moves = [Move(G1, (10.0, 0.0, 0.0), feed=500.0), Move(G1, (10.0, 10.0, 0.0), feed=500.0)]
    args = dict(name="xy", tool=freze(), start=(0.0, 0.0, 0.0), moves=moves, rpm=10000.0)
    args.update(kw)
    return Toolpath(**args)


def torna_yolu(moves) -> Toolpath:
    tool = LatheTool(id=11, name="CNMG", kind=LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=95.0, eps_r=80.0)
    return Toolpath(
        name="torna",
        tool=tool,
        start=(20.0, 0.0, 5.0),
        moves=moves,
        rpm=1500.0,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
    )


def kur_ve_dogrula(make):
    """Hata kurucuda ya da validate()'te çıkabilir; ikisini birlikte dene."""
    tp = make()
    tp.validate()
    return tp


# ================================================================ Frame


def test_identity_frame():
    f = Frame(origin=(0.0, 0.0, 0.0), R=I3)
    p = np.array([1.0, 2.0, 3.0])
    assert np.allclose(f.to_world(p), p)
    assert np.allclose(f.to_local(p), p)


def test_columns_are_local_axes():
    # z etrafında +90°: yerel x → WCS +y, yerel y → WCS −x
    f = Frame(origin=(0.0, 0.0, 0.0), R=rot_z(90.0))
    assert np.allclose(f.to_world_vec((1.0, 0.0, 0.0)), (0.0, 1.0, 0.0), atol=1e-12)
    assert np.allclose(f.to_world_vec((0.0, 1.0, 0.0)), (-1.0, 0.0, 0.0), atol=1e-12)
    assert np.allclose(f.to_world_vec((0.0, 0.0, 1.0)), (0.0, 0.0, 1.0), atol=1e-12)


def test_to_world_translation_and_rotation():
    f = Frame(origin=(10.0, 20.0, 5.0), R=rot_z(90.0))
    # p_wcs = origin + R·p: (1, 0, 2) → (10, 21, 7)
    assert np.allclose(f.to_world((1.0, 0.0, 2.0)), (10.0, 21.0, 7.0), atol=1e-12)
    assert np.allclose(f.to_local((10.0, 21.0, 7.0)), (1.0, 0.0, 2.0), atol=1e-12)


def test_vectors_ignore_origin():
    f = Frame(origin=(100.0, -50.0, 7.0), R=I3)
    assert np.allclose(f.to_world_vec((0.0, 0.0, 1.0)), (0.0, 0.0, 1.0))
    assert np.allclose(f.to_local_vec((1.0, 0.0, 0.0)), (1.0, 0.0, 0.0))


def test_roundtrip_points_and_vectors():
    f = egik_frame()
    rng = np.random.default_rng(3)
    P = rng.uniform(-50.0, 50.0, size=(20, 3))
    assert np.allclose(f.to_local(f.to_world(P)), P, atol=1e-12)
    assert np.allclose(f.to_world(f.to_local(P)), P, atol=1e-12)
    assert np.allclose(f.to_local_vec(f.to_world_vec(P)), P, atol=1e-12)
    # tek nokta ve (n, 3) dizi aynı sonucu verir
    assert np.allclose(f.to_world(P)[4], f.to_world(P[4]), atol=1e-12)


def test_rotation_preserves_lengths():
    f = egik_frame()
    v = np.array([3.0, -4.0, 12.0])
    assert np.linalg.norm(f.to_world_vec(v)) == pytest.approx(13.0, abs=1e-12)


def test_small_numerical_error_accepted():
    R = np.array(rot_z(30.0))
    R[0, 0] += 1e-12
    Frame(origin=(0.0, 0.0, 0.0), R=tuple(tuple(r) for r in R))


@pytest.mark.parametrize(
    "R",
    [
        ((1.001, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),  # ölçekli
        ((1.0, 1e-6, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),  # dik değil
        ((2.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 2.0)),  # normalleştirilmez
        ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    ],
)
def test_non_orthonormal_rejected(R):
    with pytest.raises(CamError):
        Frame(origin=(0.0, 0.0, 0.0), R=R)


@pytest.mark.parametrize(
    "R",
    [
        ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),  # yansıma
        ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),  # x ↔ y, sol el
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)),
    ],
)
def test_reflection_rejected(R):
    with pytest.raises(CamError):
        Frame(origin=(0.0, 0.0, 0.0), R=R)


@pytest.mark.parametrize(
    "R",
    [
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),  # 2x3
        ((1.0, 0.0), (0.0, 1.0), (0.0, 0.0)),  # 3x2
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0)),  # 4x3
    ],
)
def test_wrong_shape_rejected(R):
    with pytest.raises(CamError):
        Frame(origin=(0.0, 0.0, 0.0), R=R)


def test_non_finite_rejected():
    with pytest.raises(CamError):
        Frame(origin=(math.nan, 0.0, 0.0), R=I3)
    with pytest.raises(CamError):
        Frame(origin=(0.0, 0.0, 0.0), R=((math.nan, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))


def test_bad_origin_rejected():
    with pytest.raises(CamError):
        Frame(origin=(0.0, 0.0), R=I3)


def test_frame_dict_roundtrip():
    f = egik_frame()
    f2 = Frame.from_dict(json.loads(json.dumps(f.to_dict())))
    assert np.allclose(f2.origin, f.origin)
    assert np.allclose(np.array(f2.R), np.array(f.R))
    assert f2.to_dict() == f.to_dict()


def test_frame_from_dict_rejects_bad_R():
    d = Frame(origin=(0.0, 0.0, 0.0), R=I3).to_dict()
    d["R"] = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]]
    with pytest.raises(CamError):
        Frame.from_dict(d)


# ================================================================ Move.axis


def test_axis_default_none():
    assert Move(G1, (1.0, 0.0, 0.0), feed=100.0).axis is None


@pytest.mark.parametrize(
    "a",
    [
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.6, 0.0, 0.8),
        (0.0, math.sqrt(0.5), math.sqrt(0.5)),
    ],
)
def test_unit_axis_accepted(a):
    m = Move(G1, (1.0, 0.0, 0.0), feed=100.0, axis=a)
    assert np.allclose(m.axis, a)


def test_axis_within_tolerance_accepted():
    Move(G1, (1.0, 0.0, 0.0), feed=100.0, axis=(0.0, 0.0, 1.0 + 1e-12))


@pytest.mark.parametrize(
    "a",
    [
        (0.0, 0.0, 2.0),
        (0.0, 0.0, 1.0 + 1e-6),
        (0.6, 0.0, 0.7),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, math.nan),
        (0.0, 0.0, math.inf),
        (0.0, 1.0),
    ],
)
def test_bad_axis_rejected(a):
    with pytest.raises(CamError):
        Move(G1, (1.0, 0.0, 0.0), feed=100.0, axis=a)


def test_tilted_axis_on_linear_path_valid():
    a = (0.6, 0.0, 0.8)
    tp = kur_ve_dogrula(lambda: xy_yolu([Move(G1, (10.0, 0.0, 0.0), feed=500.0, axis=a)]))
    assert np.allclose(tp.moves[0].axis, a)


def test_tilted_axis_on_rapid_valid():
    kur_ve_dogrula(lambda: xy_yolu([Move(G0, (10.0, 0.0, 5.0), axis=(0.0, 0.6, 0.8))]))


@pytest.mark.parametrize("a", [None, (0.0, 0.0, 1.0)])
def test_arc_with_z_axis_valid(a):
    kur_ve_dogrula(lambda: xy_yolu([Move(G3, (10.0, 0.0, 0.0), feed=500.0, center=(5.0, 0.0), axis=a)]))


@pytest.mark.parametrize("kind", [G2, G3])
@pytest.mark.parametrize("a", [(0.6, 0.0, 0.8), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)])
def test_arc_with_tilted_axis_rejected(kind, a):
    with pytest.raises(CamError):
        kur_ve_dogrula(lambda: xy_yolu([Move(kind, (10.0, 0.0, 0.0), feed=500.0, center=(5.0, 0.0), axis=a)]))


@pytest.mark.parametrize("a", [(0.0, 0.0, 1.0), (1.0, 0.0, 0.0)])
def test_lathe_path_rejects_axis(a):
    with pytest.raises(CamError):
        kur_ve_dogrula(lambda: torna_yolu([Move(G1, (20.0, 0.0, -30.0), feed=0.2, axis=a)]))


def test_lathe_path_without_axis_valid():
    kur_ve_dogrula(lambda: torna_yolu([Move(G1, (20.0, 0.0, -30.0), feed=0.2)]))


# ================================================================ Toolpath.frame


def test_frame_default_none():
    assert xy_yolu().frame is None


def test_frame_accepted():
    f = egik_frame()
    tp = kur_ve_dogrula(lambda: xy_yolu(frame=f))
    assert tp.frame is f or tp.frame == f


@pytest.mark.parametrize(
    "bad", [{"origin": [0, 0, 0], "R": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}, "G54", (0.0, 0.0, 0.0)]
)
def test_frame_must_be_frame(bad):
    with pytest.raises(CamError):
        kur_ve_dogrula(lambda: xy_yolu(frame=bad))


def test_arc_in_frame_valid():
    # yaylar çerçevenin yerel XY'sinde
    kur_ve_dogrula(
        lambda: xy_yolu([Move(G2, (10.0, 0.0, 0.0), feed=500.0, center=(5.0, 0.0))], frame=egik_frame())
    )


# ================================================================ sözlük


def test_to_dict_writes_frame_and_axis_keys():
    d = xy_yolu().to_dict()
    assert "frame" in d
    assert d["frame"] is None
    assert all("axis" in m for m in d["moves"])
    assert all(m["axis"] is None for m in d["moves"])


def test_toolpath_roundtrip_with_frame_and_axis():
    moves = [
        Move(G0, (0.0, 0.0, 5.0)),
        Move(G1, (10.0, 0.0, 0.0), feed=500.0, axis=(0.6, 0.0, 0.8)),
        Move(G3, (20.0, 0.0, 0.0), feed=500.0, center=(15.0, 0.0), axis=(0.0, 0.0, 1.0)),
    ]
    tp = xy_yolu(moves, frame=egik_frame())
    tp2 = Toolpath.from_dict(json.loads(json.dumps(tp.to_dict())))
    tp2.validate()
    assert tp2.frame is not None
    assert np.allclose(np.array(tp2.frame.R), np.array(tp.frame.R))
    assert np.allclose(tp2.frame.origin, tp.frame.origin)
    assert tp2.moves[0].axis is None
    assert np.allclose(tp2.moves[1].axis, (0.6, 0.0, 0.8))
    assert np.allclose(tp2.moves[2].axis, (0.0, 0.0, 1.0))
    assert tp2.to_dict() == tp.to_dict()


def test_old_dict_without_frame_and_axis_loads():
    d = xy_yolu([Move(G1, (10.0, 0.0, 0.0), feed=500.0, axis=(0.6, 0.0, 0.8))]).to_dict()
    del d["frame"]
    for m in d["moves"]:
        del m["axis"]
    tp = Toolpath.from_dict(json.loads(json.dumps(d)))
    tp.validate()
    assert tp.frame is None
    assert tp.moves[0].axis is None


def test_from_dict_rejects_bad_axis():
    d = xy_yolu().to_dict()
    d["moves"][0]["axis"] = [0.0, 0.0, 2.0]
    with pytest.raises(CamError):
        kur_ve_dogrula(lambda: Toolpath.from_dict(d))


def test_from_dict_rejects_bad_frame():
    d = xy_yolu().to_dict()
    d["frame"] = {"origin": [0.0, 0.0, 0.0], "R": [[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]}
    with pytest.raises(CamError):
        kur_ve_dogrula(lambda: Toolpath.from_dict(d))
