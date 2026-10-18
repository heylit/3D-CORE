"""SPEC 18 S2 arayüzü — SegLine / SegArc `src` alanı testleri.

Sözleşme (specs/00-arayuzler.md): `src: str = ""` son alan; bölge kenarının geldiği eskiz öğesinin
kimliği ("" → bilinmiyor). Metin olmayan değer SketchError fırlatır. Mevcut çağrılar değişmeden çalışır.
Frozen dataclass karşılaştırması alanı içerir (alan compare=True; diziler == ile
karşılaştırılamadığından eşitlik alan meta verisinden sınanır).
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from sketch.model import SegArc, SegLine, SketchError, SketchRegion


def _line(**kw):
    return SegLine(np.array([0.0, 0.0]), np.array([10.0, 0.0]), **kw)


def _arc(**kw):
    return SegArc(np.array([0.0, 0.0]), 5.0, np.array([5.0, 0.0]), np.array([0.0, 5.0]), True, **kw)


@pytest.mark.parametrize("cls", [SegLine, SegArc])
def test_src_son_alan_ve_varsayilan_bos(cls):
    alanlar = dataclasses.fields(cls)
    son = alanlar[-1]
    assert son.name == "src"
    assert son.default == ""
    assert son.compare is True
    assert son.hash is None or son.hash is True


@pytest.mark.parametrize("yap", [_line, _arc])
def test_varsayilan_bos_metin(yap):
    s = yap()
    assert s.src == ""
    assert isinstance(s.src, str)


@pytest.mark.parametrize("yap", [_line, _arc])
def test_anahtar_kelimeyle_src(yap):
    assert yap(src="L3").src == "L3"


def test_konumsal_src():
    # Alan son sırada olduğundan konumsal olarak da verilebilir.
    s = SegLine([0.0, 0.0], [1.0, 1.0], "L1")
    assert s.src == "L1"
    a = SegArc([0.0, 0.0], 2.0, [2.0, 0.0], [2.0, 0.0], False, "C7")
    assert a.src == "C7"


def test_mevcut_cagrilar_degismeden_calisir():
    s = SegLine([0.0, 0.0], [3.0, 4.0])
    np.testing.assert_allclose(s.p0, [0.0, 0.0])
    np.testing.assert_allclose(s.p1, [3.0, 4.0])
    a = SegArc(center=[1.0, 1.0], r=1.0, start=[2.0, 1.0], end=[1.0, 2.0], ccw=True)
    assert a.r == 1.0 and a.ccw is True
    np.testing.assert_allclose(a.center, [1.0, 1.0])
    # Bölge kurulumu da src'siz kenarlarla çalışır.
    kare = (
        SegLine([0.0, 0.0], [1.0, 0.0]),
        SegLine([1.0, 0.0], [1.0, 1.0]),
        SegLine([1.0, 1.0], [0.0, 1.0]),
        SegLine([0.0, 1.0], [0.0, 0.0]),
    )
    bolge = SketchRegion(kare)
    assert all(k.src == "" for k in bolge.outer)


@pytest.mark.parametrize("kotu", [1, 3.5, None, b"L1", ["L1"], ("L1",)])
@pytest.mark.parametrize("yap", [_line, _arc])
def test_metin_olmayan_src_hata(yap, kotu):
    with pytest.raises(SketchError):
        yap(src=kotu)


def test_sketch_error_value_error_alt_sinifi():
    with pytest.raises(ValueError):
        _line(src=42)


@pytest.mark.parametrize("yap", [_line, _arc])
def test_frozen_src_degistirilemez(yap):
    s = yap(src="L1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.src = "L2"  # type: ignore[misc]


@pytest.mark.parametrize("yap", [_line, _arc])
def test_replace_ile_src(yap):
    s = yap(src="L1")
    t = dataclasses.replace(s, src="L9")
    assert t.src == "L9" and s.src == "L1"
    with pytest.raises(SketchError):
        dataclasses.replace(s, src=7)
