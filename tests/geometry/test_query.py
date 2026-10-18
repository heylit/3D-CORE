"""Part sorguları (inceleme Y5): Z kesiti, düzlemsel / silindirik yüzler, üçgen ağı. OCCT gerektirir.

Uydurma geometri: blok 100×60×20, üstten cep 40×20 r=3 t=5 (merkez 50, 30), boydan boya delik d=8 (15, 15).
Analitik değerler:
    blok kesiti           A = 100 · 60 = 6000 mm²
    delik                 A = π r² = 16π mm²
    cep                   A = w l − (4 − π) r² = 800 − 9(4 − π) mm²
Çokgen yaklaşımı: köşeler eğri üzerinde, kiriş sapması ≤ tol → |A_çokgen − A| ≤ çevre · tol.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d")

from geometry.features import block, cylinder, hole, pocket  # noqa: E402
from geometry.mesh import mesh_volume, tessellate  # noqa: E402
from geometry.part import CylindricalFace, GeometryError, PlanarFace, Region  # noqa: E402

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 20.0
PW, PL, PR, PT, PX, PY = 40.0, 20.0, 3.0, 5.0, 50.0, 30.0
D, HX, HY = 8.0, 15.0, 15.0
TOL = 0.01


def isaretli_alan(P: np.ndarray) -> float:
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


@pytest.fixture(scope="module")
def parca():
    return hole(pocket(block(A, B, C), PX, PY, PW, PL, PT, r=PR), HX, HY, D)


# ---------------------------------------------------------------- section_z


def test_section_through_pocket_and_hole(parca):
    """z = 18 (cep bölgesi): tek bölge, dış sınır 6000 CCW; iki iç sınır (delik, cep) CW."""
    bolgeler = parca.section_z(18.0, TOL)
    assert len(bolgeler) == 1
    r = bolgeler[0]
    assert isinstance(r, Region)
    assert r.outer.shape[1] == 2
    assert isaretli_alan(r.outer) == pytest.approx(A * B, rel=1e-9)
    assert len(r.holes) == 2
    alanlar = sorted(-isaretli_alan(h) for h in r.holes)
    assert all(isaretli_alan(h) < 0 for h in r.holes)
    a_delik, a_cep = math.pi * (D / 2) ** 2, PW * PL - (4 - math.pi) * PR**2
    assert alanlar[0] == pytest.approx(a_delik, abs=math.pi * D * TOL)
    assert alanlar[1] == pytest.approx(a_cep, abs=2 * (PW + PL) * TOL)


def test_section_below_pocket_has_only_hole(parca):
    r = parca.section_z(10.0, TOL)
    assert len(r) == 1 and len(r[0].holes) == 1


def test_section_hole_polygon_within_tolerance(parca):
    """Delik çokgeninin köşeleri daire üzerinde; ardışık köşeler arası sehim r(1 − cos(Δθ/2)) ≤ tol."""
    delik = min(parca.section_z(10.0, TOL)[0].holes, key=lambda h: -isaretli_alan(h))
    rho = np.hypot(delik[:, 0] - HX, delik[:, 1] - HY)
    np.testing.assert_allclose(rho, D / 2, atol=1e-6)
    theta = np.unwrap(np.arctan2(delik[:, 1] - HY, delik[:, 0] - HX))
    dtheta = np.abs(np.diff(np.append(theta, theta[0] - 2 * np.pi)))  # CW: açı azalır
    assert np.all((D / 2) * (1 - np.cos(dtheta / 2)) <= TOL * (1 + 1e-6))
    assert not np.allclose(delik[0], delik[-1])  # son nokta ilkini tekrar etmez


def test_section_two_regions():
    """Y boyunca taşan cep → U kanal: z = 18'de iki ayrı 10×10 bölge."""
    u = pocket(block(30.0, 10.0, 20.0), 15.0, 5.0, 10.0, 20.0, 15.0)
    bolgeler = u.section_z(18.0, TOL)
    assert len(bolgeler) == 2
    for r in bolgeler:
        assert isaretli_alan(r.outer) == pytest.approx(100.0, rel=1e-9)
        assert r.holes == ()


@pytest.mark.parametrize("z", [-1.0, C + 1.0])
def test_section_outside_is_empty(parca, z):
    assert parca.section_z(z, TOL) == []


@pytest.mark.parametrize(
    "z, tol", [(math.nan, TOL), (math.inf, TOL), (10.0, 0.0), (10.0, -1.0), (10.0, math.nan)]
)
def test_section_bad_input(parca, z, tol):
    with pytest.raises(GeometryError):
        parca.section_z(z, tol)


# ---------------------------------------------------------------- planar_faces


def test_block_planar_faces():
    """10×20×30 blok: 6 düzlemsel yüz, dış normaller ±eksenler, alanlar ve yüz merkezleri tam."""
    yuzler = block(10.0, 20.0, 30.0).planar_faces()
    assert len(yuzler) == 6 and all(isinstance(f, PlanarFace) for f in yuzler)
    beklenen = {
        (-1, 0, 0): (600.0, (0, 10, 15)),
        (1, 0, 0): (600.0, (10, 10, 15)),
        (0, -1, 0): (300.0, (5, 0, 15)),
        (0, 1, 0): (300.0, (5, 20, 15)),
        (0, 0, -1): (200.0, (5, 10, 0)),
        (0, 0, 1): (200.0, (5, 10, 30)),
    }
    bulunan = {}
    for f in yuzler:
        n = tuple(int(v) for v in np.round(f.normal))
        np.testing.assert_allclose(f.normal, n, atol=1e-12)
        bulunan[n] = f
    assert set(bulunan) == set(beklenen)
    for n, (alan, merkez) in beklenen.items():
        assert bulunan[n].area == pytest.approx(alan, rel=1e-9)
        np.testing.assert_allclose(bulunan[n].origin, merkez, atol=1e-9)


def test_pocket_floor_faces_up(parca):
    """Cep tabanı z = C − t'de, normal +Z, alan = cep kesit alanı − 0 (delik cebe değmiyor)."""
    taban = [f for f in parca.planar_faces() if abs(f.origin[2] - (C - PT)) < 1e-9 and f.normal[2] > 0.5]
    assert len(taban) == 1
    np.testing.assert_allclose(taban[0].normal, [0, 0, 1], atol=1e-12)
    assert taban[0].area == pytest.approx(PW * PL - (4 - math.pi) * PR**2, rel=1e-9)


# ---------------------------------------------------------------- cylindrical_faces


def test_through_hole_is_concave_full_cylinder(parca):
    tam = [f for f in parca.cylindrical_faces() if f.angle == pytest.approx(360.0)]
    assert len(tam) == 1
    f = tam[0]
    assert isinstance(f, CylindricalFace)
    assert f.concave
    assert f.radius == pytest.approx(D / 2)
    assert f.length == pytest.approx(C)
    assert abs(f.axis[2]) == pytest.approx(1.0)
    np.testing.assert_allclose(f.origin[:2], [HX, HY], atol=1e-9)
    uc = f.origin + f.length * f.axis
    assert sorted([f.origin[2], uc[2]]) == pytest.approx([0.0, C])
    assert f.area == pytest.approx(math.pi * D * C, rel=1e-9)


def test_pocket_corners_are_concave_quarter_cylinders(parca):
    koseler = [f for f in parca.cylindrical_faces() if f.angle == pytest.approx(90.0)]
    assert len(koseler) == 4
    assert all(f.concave and f.radius == pytest.approx(PR) and f.length == pytest.approx(PT) for f in koseler)


def test_cylinder_outer_face_is_convex():
    yuzler = cylinder(5.0, 10.0).cylindrical_faces()
    assert len(yuzler) == 1
    f = yuzler[0]
    assert not f.concave
    assert (
        f.radius == pytest.approx(5.0) and f.length == pytest.approx(10.0) and f.angle == pytest.approx(360.0)
    )


def test_face_indices_unique_and_cover_all(parca):
    """Bu parçada her yüz ya düzlem ya silindir: indeksler ortak numaralama, çakışmasız ve eksiksiz."""
    idx = [f.index for f in parca.planar_faces()] + [f.index for f in parca.cylindrical_faces()]
    assert sorted(idx) == list(range(len(idx)))
    assert len(idx) == len(parca.shape.faces())


# ---------------------------------------------------------------- mesh


def test_mesh_matches_tessellate(parca):
    V, T = parca.mesh(0.05)
    V2, T2 = tessellate(parca, 0.05)
    np.testing.assert_array_equal(V, V2)
    np.testing.assert_array_equal(T, T2)
    assert mesh_volume(V, T) == pytest.approx(parca.volume, rel=1e-3)
