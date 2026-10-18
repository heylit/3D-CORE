"""SPEC 09 — geometry/boolean.py ve Part.moved / common / cut / fuse / distance testleri (K1–K3).

Testler sadece specs/09-girisim.md'deki teori ve arayüzden yazıldı; geometry/boolean.py gövdesi okunmadı.
OCCT gerektirir (build123d yoksa atlanır). build123d Box orijinde ortalanır; Pos(c) * Box(a, b, h) kutusu
c ± (a/2, b/2, h/2) aralığındadır. Beklenen değerler analitik:
    eksen hizalı bloklar   V∩ = Π_k max(0, min(hi_k) − max(lo_k))
                           V(A − B) = V_A − V∩,  V(A ∪ B) = V_A + V_B − V∩
    45° dönmüş küp (2h)    V∩ = 16 h³ (√2 − 1)  (kesit düzgün sekizgen)
    küre merceği           V∩ = π (r₁ + r₂ − D)² (D² + 2D r₁ − 3r₁² + 2D r₂ + 6 r₁ r₂ − 3 r₂²) / (12 D)
    ayrık küreler          d = D − r₁ − r₂, en yakın noktalar merkez doğrusunda
Küre merceği build123d 0.13'ün `a & b` hatasını (küçük kürenin tamamı) yakalamak için vardır.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from assy.model import rot_x, rot_z, transform
from geometry.part import GeometryError, Hole, Part

pytestmark = pytest.mark.occt

REL = 1e-9


def blok(lo, hi, name: str = "blok", holes=()) -> Part:
    """[lo, hi] eksen hizalı blok."""
    from build123d import Box, Pos

    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    c, s = (lo + hi) / 2, hi - lo
    return Part(Pos(*c) * Box(*s), name=name, holes=holes)


def kure(c, r: float, name: str = "kure") -> Part:
    from build123d import Pos, Sphere

    return Part(Pos(*c) * Sphere(r), name=name)


def mercek(r1: float, r2: float, D: float) -> float:
    return (
        math.pi
        * (r1 + r2 - D) ** 2
        * (D**2 + 2 * D * r1 - 3 * r1**2 + 2 * D * r2 + 6 * r1 * r2 - 3 * r2**2)
        / (12 * D)
    )


# ---------- K1 moved ----------

DELIK = dict(origin=(5.0, 5.0, 30.0), axis=(0.0, 0.0, -1.0), d=6.0, depth=10.0, through=False)


def test_moved_rz90_bbox_and_center():
    """[0,10]×[0,20]×[0,30] blok, Rz90 + t = (100, 0, 0): Rz90 (x, y, z) = (−y, x, z).

    x' = 100 − y ∈ [80, 100], y' = x ∈ [0, 10], z' ∈ [0, 30]; c = (5, 10, 15) → c' = (90, 5, 15).
    """
    p = blok((0, 0, 0), (10, 20, 30), name="govde")
    q = p.moved(transform(rot_z(90), (100.0, 0.0, 0.0)))
    assert isinstance(q, Part)
    assert q.name == "govde"
    assert q.volume == pytest.approx(6000.0, rel=REL)
    np.testing.assert_allclose(q.center_of_mass, [90.0, 5.0, 15.0], atol=1e-9)
    lo, hi = q.bbox
    np.testing.assert_allclose(lo, [80.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [100.0, 10.0, 30.0], atol=1e-6)


def test_moved_general_rotation_volume_center_and_holes():
    """Genel dönme R = Rz30 · Rx40, t = (12, −7, 3): V aynı, c' = R c + t; delik o' = R o + t, a' = R a."""
    h = Hole(**DELIK)
    p = blok((0, 0, 0), (10, 20, 30), name="govde", holes=[h])
    R = rot_z(30) @ rot_x(40)
    t = np.array([12.0, -7.0, 3.0])
    q = p.moved(transform(R, t))
    assert q.volume == pytest.approx(p.volume, rel=REL)
    np.testing.assert_allclose(q.center_of_mass, R @ np.array([5.0, 10.0, 15.0]) + t, atol=1e-9)
    assert len(q.holes) == 1
    hq = q.holes[0]
    np.testing.assert_allclose(hq.origin, R @ np.array(DELIK["origin"]) + t, atol=1e-9)
    np.testing.assert_allclose(hq.axis, R @ np.array(DELIK["axis"]), atol=1e-9)
    assert (hq.d, hq.depth, hq.through) == (6.0, 10.0, False)


def test_moved_does_not_change_input():
    h = Hole(**DELIK)
    p = blok((0, 0, 0), (10, 20, 30), holes=[h])
    p.moved(transform(rot_z(30), (50.0, 0.0, 0.0)))
    np.testing.assert_allclose(p.center_of_mass, [5.0, 10.0, 15.0], atol=1e-9)
    lo, hi = p.bbox
    np.testing.assert_allclose(lo, [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [10.0, 20.0, 30.0], atol=1e-6)
    assert p.holes == (h,)
    np.testing.assert_array_equal(p.holes[0].origin, DELIK["origin"])


@pytest.mark.parametrize(
    "T",
    [
        np.diag([2.0, 1.0, 1.0, 1.0]),  # ölçek
        np.diag([-1.0, 1.0, 1.0, 1.0]),  # yansıma, det R = −1
        np.array([[1.0, 0.5, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]),  # kayma
        np.array([[1.0, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1, 1]]),  # son satır yanlış
        np.eye(3),  # boyut yanlış
    ],
    ids=["olcek", "yansima", "kayma", "son-satir", "3x3"],
)
def test_moved_rejects_non_rigid(T):
    p = blok((0, 0, 0), (10, 20, 30))
    with pytest.raises(GeometryError):
        p.moved(T)


# ---------- K2 common / cut / fuse ----------

# A = [0,10]×[0,20]×[0,30] (6000), B = [4,14]×[5,25]×[10,20] (2000)
# A ∩ B = [4,10]×[5,20]×[10,20] → 6 · 15 · 10 = 900, ağırlık merkezi (7, 12.5, 15)
A_LO, A_HI = (0, 0, 0), (10, 20, 30)
B_LO, B_HI = (4, 5, 10), (14, 25, 20)


def test_common_axis_aligned_blocks():
    a, b = blok(A_LO, A_HI, name="a"), blok(B_LO, B_HI, name="b")
    c = a.common(b)
    assert isinstance(c, Part)
    assert c.name == "a"
    assert c.volume == pytest.approx(900.0, rel=REL)
    np.testing.assert_allclose(c.center_of_mass, [7.0, 12.5, 15.0], atol=1e-9)
    assert b.common(a).volume == pytest.approx(900.0, rel=REL)


def test_cut_axis_aligned_blocks():
    """V(A − B) = 6000 − 900 = 5100; V(B − A) = 2000 − 900 = 1100."""
    a, b = blok(A_LO, A_HI, name="a"), blok(B_LO, B_HI, name="b")
    c = a.cut(b)
    assert c.name == "a"
    assert c.volume == pytest.approx(5100.0, rel=REL)
    assert b.cut(a).volume == pytest.approx(1100.0, rel=REL)


def test_fuse_axis_aligned_blocks_single_solid():
    """V(A ∪ B) = 6000 + 2000 − 900 = 7100; sonuç tek katı."""
    a, b = blok(A_LO, A_HI, name="a"), blok(B_LO, B_HI, name="b")
    f = a.fuse(b)
    assert f.name == "a"
    assert f.volume == pytest.approx(7100.0, rel=REL)
    assert len(f.shape.solids()) == 1


def test_boolean_hole_records():
    """cut: A'nın delik kayıtları korunur; fuse: A'nınkiler, sonra B'ninkiler."""
    ha = Hole(**DELIK)
    hb = Hole(origin=(10.0, 15.0, 20.0), axis=(1.0, 0.0, 0.0), d=4.0, depth=4.0, through=True)
    a = blok(A_LO, A_HI, name="a", holes=[ha])
    b = blok(B_LO, B_HI, name="b", holes=[hb])
    assert a.cut(b).holes == (ha,)
    assert a.fuse(b).holes == (ha, hb)
    assert b.fuse(a).holes == (hb, ha)


def test_boolean_does_not_change_inputs():
    a, b = blok(A_LO, A_HI, name="a"), blok(B_LO, B_HI, name="b")
    a.common(b)
    a.cut(b)
    a.fuse(b)
    assert a.volume == pytest.approx(6000.0, rel=REL)
    assert b.volume == pytest.approx(2000.0, rel=REL)
    assert (a.name, b.name) == ("a", "b")


def test_common_rotated_cube_octagon():
    """Kenarı 2h = 10 iki küp, aynı merkez, biri Z'de 45° dönmüş: V∩ = 16 h³ (√2 − 1), merkez orijin."""
    from build123d import Box, Rot

    h = 5.0
    a = Part(Box(2 * h, 2 * h, 2 * h), name="kup")
    b = Part(Rot(0, 0, 45) * Box(2 * h, 2 * h, 2 * h), name="donmus")
    c = a.common(b)
    assert c.volume == pytest.approx(16 * h**3 * (math.sqrt(2) - 1), rel=REL)
    np.testing.assert_allclose(c.center_of_mass, [0.0, 0.0, 0.0], atol=1e-9)


def test_common_rotated_cube_via_moved():
    """Aynı sekizgen, dönmüş küp Part.moved(Rz45) ile: 16 h³ (√2 − 1)."""
    from build123d import Box

    h = 5.0
    a = Part(Box(2 * h, 2 * h, 2 * h), name="kup")
    b = a.moved(transform(rot_z(45)))
    assert a.common(b).volume == pytest.approx(16 * h**3 * (math.sqrt(2) - 1), rel=REL)


@pytest.mark.parametrize("D", [8.0, 12.0, 14.0])
def test_common_sphere_lens(D):
    """r₁ = 10, r₂ = 6, |r₁ − r₂| < D < r₁ + r₂: mercek hacmi; merkez x ekseninde (simetri).

    D = 12: 167.5516 (build123d 0.13 `&` hatası küçük kürenin tamamını, 904.78'i verir).
    """
    r1, r2 = 10.0, 6.0
    a, b = kure((0, 0, 0), r1, "k1"), kure((D, 0, 0), r2, "k2")
    beklenen = mercek(r1, r2, D)
    c = a.common(b)
    assert c.volume == pytest.approx(beklenen, rel=1e-6)
    assert b.common(a).volume == pytest.approx(beklenen, rel=1e-6)
    np.testing.assert_allclose(c.center_of_mass[1:], [0.0, 0.0], atol=1e-6)
    assert 0.0 < c.center_of_mass[0] < D


def test_sphere_lens_cut_and_fuse():
    """D = 12: V(A − B) = V_A − V∩, V(A ∪ B) = V_A + V_B − V∩ (rel 1e-6)."""
    r1, r2, D = 10.0, 6.0, 12.0
    a, b = kure((0, 0, 0), r1), kure((D, 0, 0), r2)
    va, vb, vk = 4 / 3 * math.pi * r1**3, 4 / 3 * math.pi * r2**3, mercek(r1, r2, D)
    assert a.cut(b).volume == pytest.approx(va - vk, rel=1e-6)
    assert a.fuse(b).volume == pytest.approx(va + vb - vk, rel=1e-6)


def test_common_face_touching_blocks_is_none():
    """Yüz yüze değen bloklar: V∩ = 0 → None."""
    a, b = blok((0, 0, 0), (10, 10, 10)), blok((10, 0, 0), (20, 10, 10))
    assert a.common(b) is None


def test_common_disjoint_is_none():
    a, b = blok((0, 0, 0), (10, 10, 10)), blok((15, 0, 0), (20, 10, 10))
    assert a.common(b) is None


def test_common_tol_v_threshold():
    """Kesişim [9.5, 10]×[0,1]×[0,1] = 0.5 mm³: tol_v = 1 → None, tol_v = 0.1 → 0.5."""
    a, b = blok((0, 0, 0), (10, 1, 1)), blok((9.5, 0, 0), (20, 1, 1))
    assert a.common(b, tol_v=1.0) is None
    assert a.common(b, tol_v=0.1).volume == pytest.approx(0.5, rel=REL)


def test_common_negative_tol_v_raises():
    a, b = blok(A_LO, A_HI), blok(B_LO, B_HI)
    with pytest.raises(GeometryError):
        a.common(b, tol_v=-1e-6)


def test_common_contained_block():
    """[2,5]×[3,7]×[1,9] (3·4·8 = 96) tamamen [0,10]³ içinde: V∩ = 96, merkez (3.5, 5, 5)."""
    buyuk, kucuk = blok((0, 0, 0), (10, 10, 10)), blok((2, 3, 1), (5, 7, 9))
    c = buyuk.common(kucuk)
    assert c.volume == pytest.approx(96.0, rel=REL)
    np.testing.assert_allclose(c.center_of_mass, [3.5, 5.0, 5.0], atol=1e-9)
    assert buyuk.cut(kucuk).volume == pytest.approx(1000.0 - 96.0, rel=REL)


def test_cut_empty_result_raises():
    """İçerdeki küçük bloktan büyük blok çıkarılınca sonuç boş → GeometryError."""
    buyuk, kucuk = blok((0, 0, 0), (10, 10, 10)), blok((2, 3, 1), (5, 7, 9))
    with pytest.raises(GeometryError):
        kucuk.cut(buyuk)


# ---------- K3 distance ----------


def test_distance_blocks_face_gap():
    """[0,10]³ ile [17,20]×[0,10]×[0,10]: d = 7; p.x = 10, q.x = 17."""
    a, b = blok((0, 0, 0), (10, 10, 10)), blok((17, 0, 0), (20, 10, 10))
    d, p, q = a.distance(b)
    assert isinstance(d, float)
    assert np.shape(p) == (3,) and np.shape(q) == (3,)
    assert d == pytest.approx(7.0, abs=1e-9)
    assert p[0] == pytest.approx(10.0, abs=1e-9) and q[0] == pytest.approx(17.0, abs=1e-9)
    assert float(np.linalg.norm(q - p)) == pytest.approx(d, abs=1e-9)


def test_distance_blocks_edge_gap():
    """[0,10]³ ile [13,20]×[14,20]×[0,10]: x'te 3, y'de 4 boşluk → d = 5, en yakınlar kenarlar boyunca."""
    a, b = blok((0, 0, 0), (10, 10, 10)), blok((13, 14, 0), (20, 20, 10))
    d, p, q = a.distance(b)
    assert d == pytest.approx(5.0, abs=1e-9)
    np.testing.assert_allclose(p[:2], [10.0, 10.0], atol=1e-9)
    np.testing.assert_allclose(q[:2], [13.0, 14.0], atol=1e-9)
    assert p[2] == pytest.approx(q[2], abs=1e-9)
    assert -1e-9 <= p[2] <= 10.0 + 1e-9


def test_distance_disjoint_spheres_on_center_line():
    """r₁ = 10 merkez orijin, r₂ = 6 merkez (20, 15, 0): D = 25, d = 9, u = (0.8, 0.6, 0).

    p = r₁ u = (8, 6, 0), q = c₂ − r₂ u = (15.2, 11.4, 0).
    """
    a, b = kure((0, 0, 0), 10.0), kure((20, 15, 0), 6.0)
    d, p, q = a.distance(b)
    assert d == pytest.approx(9.0, abs=1e-9)
    np.testing.assert_allclose(p, [8.0, 6.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(q, [15.2, 11.4, 0.0], atol=1e-6)


def test_distance_touching_blocks_zero():
    a, b = blok((0, 0, 0), (10, 10, 10)), blok((10, 0, 0), (20, 10, 10))
    d, _, _ = a.distance(b)
    assert d == pytest.approx(0.0, abs=1e-9)


def test_distance_contained_is_between_boundaries():
    """d sınırlar arasıdır: [2,5]×[3,7]×[1,9] bloğu [0,10]³ içinde, en yakın yüzler z = 1 / z = 9 → d = 1."""
    buyuk, kucuk = blok((0, 0, 0), (10, 10, 10)), blok((2, 3, 1), (5, 7, 9))
    d, p, q = buyuk.distance(kucuk)
    assert d == pytest.approx(1.0, abs=1e-9)
    assert float(np.linalg.norm(q - p)) == pytest.approx(1.0, abs=1e-9)
