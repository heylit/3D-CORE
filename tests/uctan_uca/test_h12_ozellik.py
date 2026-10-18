"""SPEC 46 H12 — flanştan işleme özelliği tanıma (SPEC 27). K12."""

from __future__ import annotations

import pytest

from tests.uctan_uca.conftest import D_KOSE, D_MERKEZ, KOSELER, MERKEZ, H, halka

features = halka("27", "cam.features", "recognize")

pytestmark = pytest.mark.occt


def test_k12_alin_ve_delikler(flans, flans_stok):
    f = features.recognize(flans, flans_stok)
    assert len(f.faces) == 1
    assert f.faces[0].z == pytest.approx(H)
    assert f.faces[0].depth == pytest.approx(flans_stok.zmax - H)
    assert f.pockets == () and f.opens == ()
    delikler = sorted(
        (round(float(h.hole.origin[0]), 6), round(float(h.hole.origin[1]), 6), h.hole.d) for h in f.holes
    )
    beklenen = sorted([(*MERKEZ, D_MERKEZ)] + [(x, y, D_KOSE) for x, y in KOSELER])
    assert delikler == pytest.approx(beklenen)
    assert all(h.top_access for h in f.holes)
