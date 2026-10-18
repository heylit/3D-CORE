"""SPEC 46 H11 — flanşı kısıtlı eskiz + ekstrüzyonla kurmak (SPEC 17 + 26). K11."""

from __future__ import annotations

import numpy as np
import pytest

from tests.uctan_uca.conftest import D_KOSE, D_MERKEZ, KOSELER, MERKEZ, A, B, H, V_flans, halka

model = halka("17", "sketch.model", "Sketch", "Plane", "Point", "Line", "Circle", "Constraint")
solver = halka("17", "sketch.solver", "solve")
bolgeler = halka("17", "sketch.regions", "regions")
extrude = halka("26", "geometry.extrude", "extrude")

pytestmark = pytest.mark.occt


def _k(tur: str, *refs: str, value: float | None = None):
    return model.Constraint(tur, refs, value)


def flans_eskizi():
    """80 × 80 kare + Ø20 merkez + 4 × Ø6.6 köşe deliği. Başlangıç konumları bilerek kaydırılmış;
    ölçüler yalnız kısıtlardan gelir (tam kısıtlı, dof = 0)."""
    s = model.Sketch(plane=model.Plane.XY())
    s.points["o"] = model.Point(0.0, 0.0, fixed=True)
    for ad, (x, y) in {"a": (0.5, -0.3), "b": (78.0, 0.7), "c": (81.0, 79.0), "d": (-0.6, 82.0)}.items():
        s.points[ad] = model.Point(x, y)
    for ad, (p0, p1) in {"ab": ("a", "b"), "bc": ("b", "c"), "cd": ("c", "d"), "da": ("d", "a")}.items():
        s.entities[ad] = model.Line(p0, p1)
    s.constraints += [
        _k("coincident", "a", "o"),
        _k("horizontal", "ab"),
        _k("horizontal", "cd"),
        _k("vertical", "bc"),
        _k("vertical", "da"),
        _k("length", "ab", value=A),
        _k("length", "bc", value=B),
    ]
    delikler = [("m", MERKEZ, D_MERKEZ)] + [(f"k{i}", p, D_KOSE) for i, p in enumerate(KOSELER)]
    for ad, (x, y), d in delikler:
        s.points[f"{ad}_c"] = model.Point(x + 0.4, y - 0.3)
        s.entities[ad] = model.Circle(f"{ad}_c", d / 2 + 0.2)
        s.constraints += [
            _k("hdistance", "o", f"{ad}_c", value=x),
            _k("vdistance", "o", f"{ad}_c", value=y),
            _k("diameter", ad, value=d),
        ]
    s.validate()
    return s


@pytest.fixture(scope="module")
def eskiz_flans():
    s = flans_eskizi()
    sonuc = solver.solve(s)
    assert sonuc.dof == 0
    assert sonuc.residual <= 1e-9
    sonuc.apply(s)
    r = bolgeler.regions(s)
    assert len(r) == 1 and len(r[0].holes) == 5
    return extrude.extrude(r, s.plane, H, name="flans_eskiz")


def test_k11_hacim_ve_kutu(eskiz_flans, flans):
    assert eskiz_flans.volume == pytest.approx(V_flans(), rel=1e-6)
    assert eskiz_flans.volume == pytest.approx(flans.volume, rel=1e-6)
    (e0, e1), (f0, f1) = eskiz_flans.bbox, flans.bbox
    assert np.allclose(e0, f0, atol=1e-6) and np.allclose(e1, f1, atol=1e-6)


def test_k11_simetrik_fark(eskiz_flans, flans):
    ortak = eskiz_flans.common(flans)
    assert ortak is not None
    fark = eskiz_flans.volume + flans.volume - 2.0 * ortak.volume
    assert fark <= 1e-6 * V_flans()
