"""SPEC 00 — geometry/part.py testleri (K8). OCCT gerektirir (build123d yoksa atlanır).

Testler sadece SPEC 00'daki arayüzden yazıldı; uygulama kodu okunmadı.
build123d Box varsayılan olarak orijinde ortalanır: 10×20×30 kutu → x ∈ [-5, 5], y ∈ [-10, 10], z ∈ [-15, 15].
"""

from __future__ import annotations

import numpy as np
import pytest

from geometry.part import GeometryError, Part

pytestmark = pytest.mark.occt

A, B, C = 10.0, 20.0, 30.0  # kutu kenarları [mm]


def make_box_part() -> Part:
    from build123d import Box

    return Part(Box(A, B, C), name="kutu")


@pytest.mark.occt
def test_box_volume_and_area():
    """V = a·b·c = 10·20·30 = 6000 mm³; S = 2(ab + bc + ca) = 2(200 + 600 + 300) = 2200 mm²."""
    p = make_box_part()
    assert p.volume == pytest.approx(6000.0, rel=1e-6)
    assert p.area == pytest.approx(2200.0, rel=1e-6)


@pytest.mark.occt
def test_box_center_of_mass_and_bbox():
    """Orijinde ortalanmış kutu: ağırlık merkezi (0,0,0); sınır kutusu ±(a/2, b/2, c/2) = ±(5, 10, 15)."""
    p = make_box_part()
    com = p.center_of_mass
    assert np.shape(com) == (3,)
    np.testing.assert_allclose(com, [0.0, 0.0, 0.0], atol=1e-6)
    lo, hi = p.bbox
    np.testing.assert_allclose(lo, [-5.0, -10.0, -15.0], atol=1e-6)
    np.testing.assert_allclose(hi, [5.0, 10.0, 15.0], atol=1e-6)


@pytest.mark.occt
def test_translated_box_center_of_mass():
    """(100, -50, 7) ötelenmiş kutu: ağırlık merkezi öteleme vektörüne eşit, hacim değişmez."""
    from build123d import Box, Pos

    p = Part(Pos(100, -50, 7) * Box(A, B, C))
    np.testing.assert_allclose(p.center_of_mass, [100.0, -50.0, 7.0], atol=1e-6)
    assert p.volume == pytest.approx(6000.0, rel=1e-6)


@pytest.mark.occt
def test_default_name():
    from build123d import Box

    assert Part(Box(1, 1, 1)).name == "parca"


@pytest.mark.occt
def test_step_roundtrip_preserves_volume(tmp_path):
    """STEP'e yaz → oku: hacim 6000 mm³ ve alan 2200 mm² korunur."""
    path = tmp_path / "kutu.step"
    make_box_part().to_step(path)
    assert path.exists() and path.stat().st_size > 0
    p2 = Part.from_step(path, name="okunan")
    assert p2.name == "okunan"
    assert p2.volume == pytest.approx(6000.0, rel=1e-6)
    assert p2.area == pytest.approx(2200.0, rel=1e-6)


@pytest.mark.occt
def test_from_step_missing_file(tmp_path):
    with pytest.raises(GeometryError):
        Part.from_step(tmp_path / "yok.step")


@pytest.mark.occt
def test_to_stl_writes_file(tmp_path):
    path = tmp_path / "kutu.stl"
    make_box_part().to_stl(path)
    assert path.exists() and path.stat().st_size > 0


@pytest.mark.occt
def test_empty_or_zero_volume_shape_rejected():
    """Boş Compound (hacim 0) ve tek yüz (hacim 0) → GeometryError."""
    from build123d import Box, Compound

    with pytest.raises(GeometryError):
        Part(Compound())
    with pytest.raises(GeometryError):
        Part(Box(A, B, C).faces()[0])


# ---------- Delik kaydı (Hole) ve Part.holes (SPEC 23 arayüz eki) ----------


def make_hole(**kw):
    from geometry.part import Hole

    degerler = dict(origin=(5.0, 5.0, 10.0), axis=(0.0, 0.0, -1.0), d=6.0, depth=10.0, through=True)
    degerler.update(kw)
    return Hole(**degerler)


def test_part_without_holes_is_empty():
    """Mevcut Part(shape, name) çağrısı aynen çalışır; kayıt yok."""
    assert make_box_part().holes == ()


def test_part_keeps_holes_in_order():
    from build123d import Box

    h1 = make_hole()
    h2 = make_hole(origin=(1.0, 2.0, 10.0), d=8.4, csk_d=16.0, csk_angle=90.0)
    p = Part(Box(A, B, C), name="kutu", holes=[h1, h2])
    assert len(p.holes) == 2 and p.holes[0] is h1 and p.holes[1] is h2
    assert isinstance(p.holes, tuple)


def test_part_rejects_non_hole_records():
    from build123d import Box

    with pytest.raises(GeometryError):
        Part(Box(A, B, C), holes=[(0, 0, 0)])


def test_hole_arrays_are_float_and_readonly():
    h = make_hole(origin=[1, 2, 3])
    assert h.origin.dtype == float and h.origin.shape == (3,)
    np.testing.assert_allclose(h.axis, [0.0, 0.0, -1.0])
    with pytest.raises(ValueError):
        h.origin[0] = 9.0


def test_hole_threaded_and_countersunk_ok():
    """M8: kılavuz matkabı d = 8 − 1.25 = 6.75 mm."""
    h = make_hole(d=6.75, depth=15.0, through=False, thread="M8", thread_d=8.0, pitch=1.25, thread_depth=12.0)
    assert h.thread == "M8" and h.thread_depth == 12.0
    h = make_hole(d=8.4, csk_d=16.0, csk_angle=90.0)
    assert h.csk_d == 16.0


@pytest.mark.parametrize(
    "kw",
    [
        dict(axis=(0.0, 0.0, -2.0)),  # birim değil
        dict(axis=(0.0, 0.0)),  # (3,) değil
        dict(origin=(0.0, float("nan"), 0.0)),
        dict(d=0.0),
        dict(depth=-1.0),
        dict(d=float("inf")),
        dict(csk_d=6.0, csk_angle=90.0),  # csk_d <= d
        dict(csk_d=12.0, csk_angle=180.0),
        dict(csk_d=12.0),  # açı eksik
        dict(thread="M8", thread_d=8.0, pitch=1.25, thread_depth=12.0),  # thread_depth > depth
        dict(thread="M8", thread_d=5.0, pitch=0.8, thread_depth=5.0),  # thread_d <= d
        dict(thread="M8", thread_d=8.0, pitch=0.0, thread_depth=5.0),
        dict(thread_d=8.0, pitch=1.25, thread_depth=5.0),  # thread adı yok
    ],
)
def test_hole_invalid_raises(kw):
    with pytest.raises(GeometryError):
        make_hole(**kw)
