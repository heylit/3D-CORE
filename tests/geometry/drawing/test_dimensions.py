"""SPEC 16 — K8: ölçü metni ve temel ölçüler (geometry/drawing/dimensions.py).

`format_value` OCCT gerektirmez; `basic_dimensions` görünüş ürettiği için `occt` işaretli.
Teori: değer 0.01 mm'ye yuvarlanır, sondaki sıfırlar atılır, ayırıcı virgül, çapta "Ø" öneki.
Temel ölçüler: ön → a (yatay), c (dikey); üst → b (dikey), her tam çember için Ø d ve merkez konumu
(yatay x − u_min, dikey y − v_min); aynı konum tekrar ediyorsa tek. Uygulama gövdeleri okunmadı.
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from geometry.drawing.dimensions import basic_dimensions, format_value

A, B, C = 100.0, 60.0, 30.0


@pytest.mark.parametrize(
    "value, beklenen",
    [
        (12.5, "12,5"),
        (12.50, "12,5"),
        (10.0, "10"),
        (3.14159, "3,14"),
        (100.0, "100"),
        (7.25, "7,25"),
        (2.999, "3"),
        (0.5, "0,5"),
    ],
)
def test_format_value(value, beklenen):
    assert format_value(value) == beklenen


@pytest.mark.parametrize("value, beklenen", [(10.0, "Ø10"), (12.5, "Ø12,5"), (6.0, "Ø6")])
def test_format_value_cap(value, beklenen):
    assert format_value(value, diameter=True) == beklenen


# --- basic_dimensions (OCCT) -----------------------------------------------------------------------


def _parca(delikler):
    pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')
    from geometry.features import block, hole

    part = block(A, B, C)
    for x, y, d in delikler:
        part = hole(part, x, y, d)
    return part


def _olculer(part):
    from geometry.drawing.views import project

    views = [project(part, yon) for yon in ("on", "ust", "sol")]
    return basic_dimensions(part, views)


def _kume(dims) -> Counter:
    return Counter((d.kind, round(d.value, 9)) for d in dims)


def _tutarli(d):
    """Dimension alanları birbirini tutuyor: değer p1-p2'den, metin format_value'dan."""
    p1, p2 = np.asarray(d.p1, float), np.asarray(d.p2, float)
    if d.kind == "yatay":
        assert abs(p2[0] - p1[0]) == pytest.approx(d.value, abs=1e-6)
    elif d.kind == "dikey":
        assert abs(p2[1] - p1[1]) == pytest.approx(d.value, abs=1e-6)
    else:
        assert 2 * np.linalg.norm(p2 - p1) == pytest.approx(d.value, abs=1e-6)
    assert d.text == format_value(d.value, diameter=d.kind == "cap")


@pytest.mark.occt
def test_delikli_blok_temel_olculer():
    """Delik d = 10, eksen (20, 25): ön {a, c}, üst {b, Ø d, x, y}; başka ölçü yok."""
    dims = _olculer(_parca([(20.0, 25.0, 10.0)]))
    assert _kume(dims["on"]) == Counter({("yatay", A): 1, ("dikey", C): 1})
    assert _kume(dims["ust"]) == Counter(
        {("dikey", B): 1, ("cap", 10.0): 1, ("yatay", 20.0): 1, ("dikey", 25.0): 1}
    )
    assert tuple(dims.get("sol", ())) == ()
    for ds in dims.values():
        for d in ds:
            _tutarli(d)


@pytest.mark.occt
def test_ayni_konum_tek_yazilir():
    """İki delik aynı x'te (20): yatay konum 20 bir kez; dikey konumlar 15 ve 45 ayrı; iki çap."""
    dims = _olculer(_parca([(20.0, 15.0, 10.0), (20.0, 45.0, 8.0)]))
    assert _kume(dims["on"]) == Counter({("yatay", A): 1, ("dikey", C): 1})
    assert _kume(dims["ust"]) == Counter(
        {
            ("dikey", B): 1,
            ("cap", 10.0): 1,
            ("cap", 8.0): 1,
            ("yatay", 20.0): 1,
            ("dikey", 15.0): 1,
            ("dikey", 45.0): 1,
        }
    )
    for ds in dims.values():
        for d in ds:
            _tutarli(d)
