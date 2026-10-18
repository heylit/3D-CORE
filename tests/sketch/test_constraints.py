"""SPEC 17 K1, K2 — kısıt artıkları ve analitik Jacobian.

Testler yalnızca specs/17-kroki.md "Kısıt artıkları", "Satır ölçeği" tablosundan ve sketch/model.py
arayüzünden yazıldı; sketch/constraints.py gövdesi okunmadı. Beklenen değerler elle hesaplandı.

Ölçek: yön satırları (PARALLEL, PERPENDICULAR, ANGLE) L ile çarpılır,
L = max(eskiz noktalarının sınır kutusu köşegeni, 1 mm).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from sketch.constraints import jacobian, residual
from sketch.model import Arc, Circle, Constraint, ConstraintType, Line, Point, Sketch, SketchError

CT = ConstraintType


# --- Yardımcılar --------------------------------------------------------------------------------------


def eskiz(points: dict, entities: dict, constraints: list) -> Sketch:
    return Sketch(points=points, entities=entities, constraints=constraints)


def olcek(s: Sketch) -> float:
    """SPEC "Satır ölçeği": L = max(sınır kutusu köşegeni, 1 mm)."""
    xy = np.array([(p.x, p.y) for p in s.points.values()])
    return max(float(np.linalg.norm(xy.max(axis=0) - xy.min(axis=0))), 1.0)


def r_of(s: Sketch, x_map: dict | None = None, k: int = 0) -> np.ndarray:
    return np.atleast_1d(np.asarray(residual(s, k, x_map or {}), dtype=float))


def iki_cizgi(a0, a1, b0, b1, c: Constraint) -> Sketch:
    pts = {"a0": Point(*a0), "a1": Point(*a1), "b0": Point(*b0), "b1": Point(*b1)}
    ents = {"la": Line("a0", "a1"), "lb": Line("b0", "b1")}
    return eskiz(pts, ents, [c])


def yonlu(deg: float, n: float = 4.0, start=(0.0, 10.0)) -> tuple:
    """start'tan deg derece doğrultusunda n uzunlukta çizginin uçları."""
    t = math.radians(deg)
    return start, (start[0] + n * math.cos(t), start[1] + n * math.sin(t))


# --- K1: artıklar, her tablo satırı -------------------------------------------------------------------


def test_residual_coincident():
    s = eskiz({"p": Point(1.0, 2.0), "q": Point(1.0, 2.0)}, {}, [Constraint(CT.COINCIDENT, ("p", "q"))])
    r = r_of(s)
    assert r.shape == (2,)
    assert np.allclose(r, 0.0, atol=1e-12)
    # r = q − p
    assert np.allclose(r_of(s, {"q": np.array([4.0, 6.0])}), [3.0, 4.0], atol=1e-12)


def test_residual_point_on_line():
    s = eskiz(
        {"p0": Point(0.0, 0.0), "p1": Point(10.0, 0.0), "q": Point(5.0, 0.0)},
        {"l": Line("p0", "p1")},
        [Constraint(CT.POINT_ON_LINE, ("q", "l"))],
    )
    assert r_of(s).shape == (1,)
    assert abs(r_of(s)[0]) < 1e-12
    # 2 mm kaçık nokta (çizginin solunda) → r = d × (q − p0) / |d| = 2
    assert r_of(s, {"q": np.array([5.0, 2.0])})[0] == pytest.approx(2.0, abs=1e-12)
    # sonsuz doğru: parça dışındaki nokta da sağlar
    assert abs(r_of(s, {"q": np.array([25.0, 0.0])})[0]) < 1e-12


def test_residual_point_on_circle_ve_yay():
    s = eskiz(
        {"c": Point(1.0, 1.0), "q": Point(4.0, 5.0)},
        {"o": Circle("c", 5.0)},
        [Constraint(CT.POINT_ON_CIRCLE, ("q", "o"))],
    )
    assert abs(r_of(s)[0]) < 1e-12
    # |q − c| − r = 10 − 5
    assert r_of(s, {"q": np.array([7.0, 9.0])})[0] == pytest.approx(5.0, abs=1e-12)
    # x_map'te daire kimliği → yarıçap
    assert r_of(s, {"o": 4.0})[0] == pytest.approx(1.0, abs=1e-12)

    y = eskiz(
        {"c": Point(0.0, 0.0), "s": Point(5.0, 0.0), "e": Point(0.0, 5.0), "q": Point(3.0, 4.0)},
        {"y": Arc("c", "s", "e")},
        [Constraint(CT.POINT_ON_CIRCLE, ("q", "y"))],
    )
    assert abs(r_of(y)[0]) < 1e-12
    # yay yarıçapı r = |s − c|; tam çember: açıklık dışındaki nokta da sağlar
    assert abs(r_of(y, {"q": np.array([-3.0, -4.0])})[0]) < 1e-12
    assert r_of(y, {"q": np.array([6.0, 8.0])})[0] == pytest.approx(5.0, abs=1e-12)


def test_residual_midpoint():
    s = eskiz(
        {"p0": Point(0.0, 0.0), "p1": Point(10.0, 4.0), "q": Point(5.0, 2.0)},
        {"l": Line("p0", "p1")},
        [Constraint(CT.MIDPOINT, ("q", "l"))],
    )
    assert r_of(s).shape == (2,)
    assert np.allclose(r_of(s), 0.0, atol=1e-12)
    assert np.allclose(r_of(s, {"q": np.array([6.0, 1.0])}), [1.0, -1.0], atol=1e-12)


def test_residual_horizontal_vertical_cizgi():
    s = eskiz(
        {"p0": Point(0.0, 3.0), "p1": Point(10.0, 3.0)},
        {"l": Line("p0", "p1")},
        [Constraint(CT.HORIZONTAL, ("l",)), Constraint(CT.VERTICAL, ("l",))],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12
    assert r_of(s, {"p1": np.array([10.0, 5.0])}, k=0)[0] == pytest.approx(2.0, abs=1e-12)  # d_y
    assert r_of(s, k=1)[0] == pytest.approx(10.0, abs=1e-12)  # d_x
    assert abs(r_of(s, {"p1": np.array([0.0, 9.0])}, k=1)[0]) < 1e-12


def test_residual_horizontal_vertical_nokta_nokta():
    s = eskiz(
        {"p": Point(0.0, 3.0), "q": Point(7.0, 3.0)},
        {},
        [Constraint(CT.HORIZONTAL, ("p", "q")), Constraint(CT.VERTICAL, ("p", "q"))],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12
    assert r_of(s, {"q": np.array([7.0, 4.0])}, k=0)[0] == pytest.approx(1.0, abs=1e-12)  # q_y − p_y
    assert r_of(s, k=1)[0] == pytest.approx(7.0, abs=1e-12)  # q_x − p_x
    assert abs(r_of(s, {"q": np.array([0.0, -2.0])}, k=1)[0]) < 1e-12


def test_residual_parallel():
    c = Constraint(CT.PARALLEL, ("la", "lb"))
    s = iki_cizgi((0, 0), (10, 0), (0, 5), (4, 5), c)
    assert abs(r_of(s)[0]) < 1e-12
    # zıt yön de paralel sayılır (sin φ = 0)
    s2 = iki_cizgi((0, 0), (10, 0), (4, 5), (0, 5), c)
    assert abs(r_of(s2)[0]) < 1e-12
    # 30° → L · sin 30°
    b0, b1 = yonlu(30.0)
    s3 = iki_cizgi((0, 0), (10, 0), b0, b1, c)
    assert r_of(s3)[0] == pytest.approx(olcek(s3) * 0.5, abs=1e-12)


def test_residual_perpendicular():
    c = Constraint(CT.PERPENDICULAR, ("la", "lb"))
    s = iki_cizgi((0, 0), (10, 0), (20, 0), (20, 5), c)
    assert abs(r_of(s)[0]) < 1e-12
    s2 = iki_cizgi((0, 0), (10, 0), (20, 5), (20, 0), c)  # −90° de dik
    assert abs(r_of(s2)[0]) < 1e-12
    # 60° → L · cos 60°
    b0, b1 = yonlu(60.0)
    s3 = iki_cizgi((0, 0), (10, 0), b0, b1, c)
    assert r_of(s3)[0] == pytest.approx(olcek(s3) * 0.5, abs=1e-12)


def test_residual_angle():
    b0, b1 = yonlu(30.0)
    s = iki_cizgi((0, 0), (10, 0), b0, b1, Constraint(CT.ANGLE, ("la", "lb"), 30.0))
    assert abs(r_of(s)[0]) < 1e-12
    # 30° yerine 31° → r = L · π/180 (a'dan b'ye CCW pozitif)
    b0, b1 = yonlu(31.0)
    s2 = iki_cizgi((0, 0), (10, 0), b0, b1, Constraint(CT.ANGLE, ("la", "lb"), 30.0))
    assert r_of(s2)[0] == pytest.approx(olcek(s2) * math.pi / 180.0, abs=1e-12)
    # işaretli: −30°
    b0, b1 = yonlu(-30.0)
    s3 = iki_cizgi((0, 0), (10, 0), b0, b1, Constraint(CT.ANGLE, ("la", "lb"), -30.0))
    assert abs(r_of(s3)[0]) < 1e-12
    s4 = iki_cizgi((0, 0), (10, 0), b0, b1, Constraint(CT.ANGLE, ("la", "lb"), 30.0))
    assert r_of(s4)[0] == pytest.approx(-olcek(s4) * math.pi / 3.0, abs=1e-12)


def test_residual_angle_wrap():
    """b doğrultusu 179°, θ = −179° → wrap(358°) = −2° → r = −L · 2π/180."""
    b0, b1 = yonlu(179.0)
    s = iki_cizgi((0, 0), (10, 0), b0, b1, Constraint(CT.ANGLE, ("la", "lb"), -179.0))
    assert r_of(s)[0] == pytest.approx(-olcek(s) * 2.0 * math.pi / 180.0, abs=1e-12)
    # θ = 180: b zıt yönde
    s2 = iki_cizgi((0, 0), (10, 0), (5, 5), (1, 5), Constraint(CT.ANGLE, ("la", "lb"), 180.0))
    assert abs(r_of(s2)[0]) < 1e-12


def test_residual_equal_cizgi():
    c = Constraint(CT.EQUAL, ("la", "lb"))
    s = iki_cizgi((0, 0), (10, 0), (0, 5), (6, 13), c)  # |d_b| = 10
    assert abs(r_of(s)[0]) < 1e-12
    s2 = iki_cizgi((0, 0), (10, 0), (0, 5), (7, 5), c)  # |d_a| − |d_b| = 3
    assert r_of(s2)[0] == pytest.approx(3.0, abs=1e-12)


def test_residual_equal_daire_yay():
    s = eskiz(
        {"c1": Point(0.0, 0.0), "c2": Point(20.0, 0.0), "s": Point(23.0, 0.0), "e": Point(20.0, 3.0)},
        {"o1": Circle("c1", 5.0), "o2": Circle("c2", 5.0), "y": Arc("c2", "s", "e")},
        [Constraint(CT.EQUAL, ("o1", "o2")), Constraint(CT.EQUAL, ("o1", "y"))],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12
    assert r_of(s, {"o2": 3.0}, k=0)[0] == pytest.approx(2.0, abs=1e-12)  # r_a − r_b
    assert r_of(s, k=1)[0] == pytest.approx(2.0, abs=1e-12)  # 5 − |s − c| = 5 − 3
    assert abs(r_of(s, {"s": np.array([25.0, 0.0])}, k=1)[0]) < 1e-12


def test_residual_length():
    s = eskiz(
        {"p0": Point(0.0, 0.0), "p1": Point(3.0, 4.0)},
        {"l": Line("p0", "p1")},
        [Constraint(CT.LENGTH, ("l",), 5.0), Constraint(CT.LENGTH, ("l",), 4.0)],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12
    assert r_of(s, k=1)[0] == pytest.approx(1.0, abs=1e-12)


def test_residual_distance_nokta_nokta():
    s = eskiz(
        {"p": Point(0.0, 0.0), "q": Point(3.0, 4.0)},
        {},
        [Constraint(CT.DISTANCE, ("p", "q"), 5.0), Constraint(CT.DISTANCE, ("p", "q"), 3.0)],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12
    assert r_of(s, k=1)[0] == pytest.approx(2.0, abs=1e-12)


def test_residual_distance_nokta_cizgi_isaretli():
    s = eskiz(
        {"p0": Point(0.0, 0.0), "p1": Point(10.0, 0.0), "q": Point(4.0, 3.0)},
        {"l": Line("p0", "p1")},
        [
            Constraint(CT.DISTANCE, ("q", "l"), 3.0),
            Constraint(CT.DISTANCE, ("q", "l"), -3.0),
            Constraint(CT.DISTANCE, ("q", "l"), 0.0),
        ],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12  # sol taraf pozitif
    assert r_of(s, k=1)[0] == pytest.approx(6.0, abs=1e-12)
    assert r_of(s, {"q": np.array([4.0, -3.0])}, k=0)[0] == pytest.approx(-6.0, abs=1e-12)
    assert r_of(s, k=2)[0] == pytest.approx(3.0, abs=1e-12)  # D = 0 serbest


def test_residual_hdistance_vdistance():
    s = eskiz(
        {"p": Point(1.0, 1.0), "q": Point(4.0, 7.0)},
        {},
        [
            Constraint(CT.HDISTANCE, ("p", "q"), 3.0),
            Constraint(CT.HDISTANCE, ("p", "q"), -3.0),
            Constraint(CT.VDISTANCE, ("p", "q"), 6.0),
            Constraint(CT.VDISTANCE, ("p", "q"), 5.0),
            Constraint(CT.VDISTANCE, ("q", "p"), -6.0),
        ],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12
    assert r_of(s, k=1)[0] == pytest.approx(6.0, abs=1e-12)
    assert abs(r_of(s, k=2)[0]) < 1e-12
    assert r_of(s, k=3)[0] == pytest.approx(1.0, abs=1e-12)
    assert abs(r_of(s, k=4)[0]) < 1e-12


def test_residual_radius_diameter():
    s = eskiz(
        {"c": Point(0.0, 0.0), "c2": Point(20.0, 0.0), "s": Point(26.0, 0.0), "e": Point(20.0, 6.0)},
        {"o": Circle("c", 5.0), "y": Arc("c2", "s", "e")},
        [
            Constraint(CT.RADIUS, ("o",), 5.0),
            Constraint(CT.RADIUS, ("o",), 4.0),
            Constraint(CT.DIAMETER, ("o",), 10.0),
            Constraint(CT.DIAMETER, ("o",), 8.0),
            Constraint(CT.RADIUS, ("y",), 6.0),
            Constraint(CT.DIAMETER, ("y",), 10.0),
        ],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12
    assert r_of(s, k=1)[0] == pytest.approx(1.0, abs=1e-12)
    assert abs(r_of(s, k=2)[0]) < 1e-12
    assert r_of(s, k=3)[0] == pytest.approx(2.0, abs=1e-12)  # 2r − D
    assert abs(r_of(s, k=4)[0]) < 1e-12  # yay r = |s − c| = 6
    assert r_of(s, k=5)[0] == pytest.approx(2.0, abs=1e-12)


def test_residual_tangent_cizgi_daire():
    """Çizgi (0,10)→(10,10), merkez orijinde: d × (c − p0)/|d| = −10 (merkez sağda)."""
    pts = {"p0": Point(0.0, 10.0), "p1": Point(10.0, 10.0), "c": Point(0.0, 0.0)}
    s = eskiz(
        pts,
        {"l": Line("p0", "p1"), "o": Circle("c", 10.0)},
        [Constraint(CT.TANGENT, ("l", "o"), side=-1), Constraint(CT.TANGENT, ("l", "o"), side=1)],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12
    assert r_of(s, {"o": 8.0}, k=0)[0] == pytest.approx(-2.0, abs=1e-12)
    assert r_of(s, k=1)[0] == pytest.approx(-20.0, abs=1e-12)


def test_residual_tangent_cizgi_yay():
    pts = {
        "p0": Point(10.0, 10.0),
        "p1": Point(0.0, 10.0),  # yön −x: merkez solda
        "c": Point(0.0, 0.0),
        "s": Point(10.0, 0.0),
        "e": Point(0.0, 10.0),
    }
    s = eskiz(
        pts, {"l": Line("p0", "p1"), "y": Arc("c", "s", "e")}, [Constraint(CT.TANGENT, ("l", "y"), side=1)]
    )
    assert abs(r_of(s)[0]) < 1e-12
    # yay yarıçapı |s − c| = 12 → 10 − 12
    assert r_of(s, {"s": np.array([12.0, 0.0])})[0] == pytest.approx(-2.0, abs=1e-12)


def test_residual_tangent_daire_daire_dis():
    s = eskiz(
        {"ca": Point(0.0, 0.0), "cb": Point(8.0, 0.0)},
        {"a": Circle("ca", 3.0), "b": Circle("cb", 5.0)},
        [Constraint(CT.TANGENT, ("a", "b"))],
    )
    assert abs(r_of(s)[0]) < 1e-12
    # |c_b − c_a| − (r_a + r_b) = 10 − 8
    assert r_of(s, {"cb": np.array([6.0, 8.0])})[0] == pytest.approx(2.0, abs=1e-12)


def test_residual_tangent_daire_daire_ic():
    s = eskiz(
        {"ca": Point(0.0, 0.0), "cb": Point(6.0, 0.0)},
        {"a": Circle("ca", 10.0), "b": Circle("cb", 4.0)},
        [
            Constraint(CT.TANGENT, ("a", "b"), side=1, internal=True),
            Constraint(CT.TANGENT, ("a", "b"), side=-1, internal=True),
        ],
    )
    assert abs(r_of(s, k=0)[0]) < 1e-12  # 6 − (10 − 4)
    assert r_of(s, {"cb": np.array([8.0, 0.0])}, k=0)[0] == pytest.approx(2.0, abs=1e-12)
    assert r_of(s, k=1)[0] == pytest.approx(12.0, abs=1e-12)  # 6 + 6


def test_residual_symmetric():
    """Eksen x = 0 (çizgi (0,0)→(0,10)); p, q eksene göre simetrik."""
    s = eskiz(
        {"a0": Point(0.0, 0.0), "a1": Point(0.0, 10.0), "p": Point(-3.0, 2.0), "q": Point(3.0, 2.0)},
        {"l": Line("a0", "a1")},
        [Constraint(CT.SYMMETRIC, ("p", "q", "l"))],
    )
    r = r_of(s)
    assert r.shape == (2,)
    assert np.allclose(r, 0.0, atol=1e-12)
    # q = (5, 4): m = (1, 3) → d × (m − p0)/|d| = −1 ; (q − p) · d/|d| = 2
    assert np.allclose(r_of(s, {"q": np.array([5.0, 4.0])}), [-1.0, 2.0], atol=1e-12)


def test_residual_x_map_haritada_olmayanlar_eskizden():
    """x_map yalnızca verilen kimlikleri değiştirir; eskiz nesnesi değişmez."""
    s = eskiz(
        {"p0": Point(0.0, 0.0), "p1": Point(10.0, 0.0), "q": Point(5.0, 0.0)},
        {"l": Line("p0", "p1")},
        [Constraint(CT.POINT_ON_LINE, ("q", "l"))],
    )
    once = s.to_dict()
    # çizgi 3 mm yukarı: q (eskizdeki) 3 mm sağda kalır → −3
    r = r_of(s, {"p0": np.array([0.0, 3.0]), "p1": np.array([10.0, 3.0])})
    assert r[0] == pytest.approx(-3.0, abs=1e-12)
    assert s.to_dict() == once


def test_residual_desteklenmeyen_cift():
    s = eskiz(
        {"c": Point(0.0, 0.0), "p": Point(1.0, 1.0)},
        {"o": Circle("c", 5.0)},
        [Constraint(CT.HORIZONTAL, ("o",)), Constraint(CT.LENGTH, ("p",), 3.0)],
    )
    for k in range(2):
        with pytest.raises(SketchError):
            residual(s, k, {})
        with pytest.raises(SketchError):
            jacobian(s, k, ["c", "p", "o"])


# --- K2: Jacobian = merkezi fark ----------------------------------------------------------------------

H = 1e-6


def rastgele_eskiz(seed: int) -> Sketch:
    """Rastgele (tohumlu) noktalar [-10, 10]²'de; iki sabit köşe noktası sınır kutusunu (dolayısıyla L'yi)
    pertürbasyondan bağımsız tutar."""
    rng = np.random.default_rng(seed)
    ad = ["a0", "a1", "b0", "b1", "c1", "c2", "yc", "ys", "ye", "q", "p"]
    pts = {k: Point(*rng.uniform(-10.0, 10.0, size=2)) for k in ad}
    pts["F1"] = Point(-30.0, -30.0, fixed=True)
    pts["F2"] = Point(30.0, 30.0, fixed=True)
    ents = {
        "la": Line("a0", "a1"),
        "lb": Line("b0", "b1"),
        "o1": Circle("c1", float(rng.uniform(2.0, 5.0))),
        "o2": Circle("c2", float(rng.uniform(2.0, 5.0))),
        "y": Arc("yc", "ys", "ye"),
    }
    return eskiz(pts, ents, [])


def aci_deg(s: Sketch) -> float:
    pa = np.array([s.points["a1"].x - s.points["a0"].x, s.points["a1"].y - s.points["a0"].y])
    pb = np.array([s.points["b1"].x - s.points["b0"].x, s.points["b1"].y - s.points["b0"].y])
    return math.degrees(math.atan2(pa[0] * pb[1] - pa[1] * pb[0], pa @ pb))


def tablo(s: Sketch) -> list[Constraint]:
    """Her tablo satırı (ve yay / daire varyantları) için bir kısıt."""
    phi = aci_deg(s)
    theta = phi - 15.0  # wrap süreksizliğinden uzak
    if theta <= -180.0:
        theta += 360.0
    return [
        Constraint(CT.COINCIDENT, ("p", "q")),
        Constraint(CT.POINT_ON_LINE, ("q", "la")),
        Constraint(CT.POINT_ON_CIRCLE, ("q", "o1")),
        Constraint(CT.POINT_ON_CIRCLE, ("q", "y")),
        Constraint(CT.MIDPOINT, ("q", "la")),
        Constraint(CT.HORIZONTAL, ("la",)),
        Constraint(CT.HORIZONTAL, ("p", "q")),
        Constraint(CT.VERTICAL, ("lb",)),
        Constraint(CT.VERTICAL, ("p", "q")),
        Constraint(CT.PARALLEL, ("la", "lb")),
        Constraint(CT.PERPENDICULAR, ("la", "lb")),
        Constraint(CT.ANGLE, ("la", "lb"), theta),
        Constraint(CT.EQUAL, ("la", "lb")),
        Constraint(CT.EQUAL, ("o1", "o2")),
        Constraint(CT.EQUAL, ("o1", "y")),
        Constraint(CT.LENGTH, ("la",), 7.0),
        Constraint(CT.DISTANCE, ("p", "q"), 4.0),
        Constraint(CT.DISTANCE, ("q", "lb"), -2.5),
        Constraint(CT.HDISTANCE, ("p", "q"), 1.5),
        Constraint(CT.VDISTANCE, ("p", "q"), -2.0),
        Constraint(CT.RADIUS, ("o1",), 3.0),
        Constraint(CT.RADIUS, ("y",), 3.0),
        Constraint(CT.DIAMETER, ("o2",), 6.0),
        Constraint(CT.DIAMETER, ("y",), 6.0),
        Constraint(CT.TANGENT, ("la", "o1"), side=1),
        Constraint(CT.TANGENT, ("lb", "y"), side=-1),
        Constraint(CT.TANGENT, ("o1", "o2")),
        Constraint(CT.TANGENT, ("o1", "y")),
        Constraint(CT.TANGENT, ("o1", "o2"), side=1, internal=True),
        Constraint(CT.TANGENT, ("y", "o2"), side=-1, internal=True),
        Constraint(CT.SYMMETRIC, ("p", "q", "lb")),
    ]


def sayisal_jacobian(s: Sketch, k: int, unknowns: list[str]) -> np.ndarray:
    sutunlar = []
    for u in unknowns:
        if u in s.points:
            x0 = np.array([s.points[u].x, s.points[u].y])
            for i in range(2):
                e = np.zeros(2)
                e[i] = H
                rp = r_of(s, {u: x0 + e}, k)
                rm = r_of(s, {u: x0 - e}, k)
                sutunlar.append((rp - rm) / (2 * H))
        else:
            r0 = s.entities[u].r
            sutunlar.append((r_of(s, {u: r0 + H}, k) - r_of(s, {u: r0 - H}, k)) / (2 * H))
    return np.column_stack(sutunlar)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_jacobian_matches_fd(seed):
    s = rastgele_eskiz(seed)
    s.constraints = tablo(s)
    serbest = [k for k, p in s.points.items() if not p.fixed]
    unknowns = serbest + ["o1", "o2"]
    n_sutun = 2 * len(serbest) + 2
    for k, c in enumerate(s.constraints):
        J = np.asarray(jacobian(s, k, unknowns), dtype=float)
        n_satir = r_of(s, k=k).size
        assert J.shape == (n_satir, n_sutun), (k, c.type)
        J_fd = sayisal_jacobian(s, k, unknowns)
        assert np.allclose(J, J_fd, rtol=0.0, atol=1e-6), (k, c.type, c.refs, np.abs(J - J_fd).max())


def test_jacobian_sutun_duzeni_ve_sabitler():
    """Sütunlar unknowns sırasıyla; listede olmayan noktanın sütunu yok."""
    s = eskiz(
        {"p0": Point(0.0, 0.0), "p1": Point(3.0, 4.0)},
        {"l": Line("p0", "p1")},
        [Constraint(CT.LENGTH, ("l",), 5.0)],
    )
    # |d| türevi: ∂/∂p1 = d/|d| = (0.6, 0.8), ∂/∂p0 = −(0.6, 0.8)
    assert np.allclose(jacobian(s, 0, ["p0", "p1"]), [[-0.6, -0.8, 0.6, 0.8]], atol=1e-12)
    assert np.allclose(jacobian(s, 0, ["p1", "p0"]), [[0.6, 0.8, -0.6, -0.8]], atol=1e-12)
    assert np.allclose(jacobian(s, 0, ["p1"]), [[0.6, 0.8]], atol=1e-12)

    d = eskiz({"c": Point(0.0, 0.0)}, {"o": Circle("c", 5.0)}, [Constraint(CT.DIAMETER, ("o",), 10.0)])
    assert np.allclose(jacobian(d, 0, ["c", "o"]), [[0.0, 0.0, 2.0]], atol=1e-12)
    assert np.allclose(jacobian(d, 0, ["o"]), [[2.0]], atol=1e-12)
