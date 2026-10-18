"""SPEC 17 K3–K9, K12, K14 — eskiz çözücü, serbestlik, çelişki teşhisi, sürükleme, değişmezlik, ölçek.

Testler yalnızca specs/17-kroki.md ("Çözüm", "Serbestlik derecesi", "Çelişki teşhisi", "Fazla tanımlı",
"Sürükleme", kabul kriterleri) ve sketch/model.py arayüzünden yazıldı; sketch/solver.py gövdesi okunmadı.
Kapalı formlar elle türetildi.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from sketch.constraints import residual
from sketch.model import Arc, Circle, Constraint, ConstraintType, Line, Point, Sketch, SketchError
from sketch.regions import area, regions
from sketch.solver import SolveResult, dof, drag, solve

CT = ConstraintType
TOL_X = 1e-9  # mm
TOL_A = 1e-9  # rad


# --- Yardımcılar --------------------------------------------------------------------------------------


def eskiz(points: dict, entities: dict, constraints: list) -> Sketch:
    return Sketch(points=points, entities=entities, constraints=constraints)


def kopya(s: Sketch) -> Sketch:
    return Sketch.from_dict(s.to_dict())


def cozulmus(s: Sketch, res: SolveResult) -> Sketch:
    k = kopya(s)
    res.apply(k)
    return k


def max_artik(s: Sketch) -> float:
    """Eskizdeki (güncel) konumlarda tüm kısıtların max|r|'si."""
    m = 0.0
    for k in range(len(s.constraints)):
        r = np.atleast_1d(np.asarray(residual(s, k, {}), dtype=float))
        m = max(m, float(np.abs(r).max()))
    return m


def P(res: SolveResult, ident: str) -> np.ndarray:
    return np.asarray(res.points[ident], dtype=float)


def aci(u, v) -> float:
    """İki vektör arasındaki işaretsiz açı (rad)."""
    u, v = np.asarray(u, float), np.asarray(v, float)
    return math.atan2(abs(u[0] * v[1] - u[1] * v[0]), float(u @ v))


def ucgen_345(A=(0.0, 0.0), B=(4.3, 0.4), C=(3.6, 3.3), sabit=True, yatay=True) -> Sketch:
    """A sabit, AB yatay, |AB| = 4, |BC| = 3, |CA| = 5. Kapalı form: B = (4, 0), C = (4, 3)."""
    pts = {"A": Point(*A, fixed=sabit), "B": Point(*B), "C": Point(*C)}
    ents = {"ab": Line("A", "B"), "bc": Line("B", "C"), "ca": Line("C", "A")}
    cs = [
        Constraint(CT.LENGTH, ("ab",), 4.0),
        Constraint(CT.DISTANCE, ("B", "C"), 3.0),
        Constraint(CT.LENGTH, ("ca",), 5.0),
    ]
    if yatay:
        cs.insert(0, Constraint(CT.HORIZONTAL, ("ab",)))
    return eskiz(pts, ents, cs)


def dikdortgen(a=(0.2, -0.3), b=(39.0, 1.0), c=(41.0, 29.0), d=(-1.0, 31.0), sabit=False) -> Sketch:
    """Paylaşılan 4 nokta, 4 çizgi; H, V, H, V."""
    pts = {"a": Point(*a, fixed=sabit), "b": Point(*b), "c": Point(*c), "d": Point(*d)}
    ents = {"ab": Line("a", "b"), "bc": Line("b", "c"), "cd": Line("c", "d"), "da": Line("d", "a")}
    cs = [
        Constraint(CT.HORIZONTAL, ("ab",)),
        Constraint(CT.VERTICAL, ("bc",)),
        Constraint(CT.HORIZONTAL, ("cd",)),
        Constraint(CT.VERTICAL, ("da",)),
    ]
    return eskiz(pts, ents, cs)


# --- K3: üçgen ----------------------------------------------------------------------------------------


def test_ucgen_345_kapali_form():
    s = ucgen_345()
    res = solve(s)
    assert np.allclose(P(res, "A"), (0.0, 0.0), atol=TOL_X)
    assert np.allclose(P(res, "B"), (4.0, 0.0), atol=TOL_X)
    assert np.allclose(P(res, "C"), (4.0, 3.0), atol=TOL_X)
    # B köşesinde dik açı
    assert aci(P(res, "A") - P(res, "B"), P(res, "C") - P(res, "B")) == pytest.approx(math.pi / 2, abs=TOL_A)
    assert res.dof == 0
    assert res.residual <= 1e-10
    assert max_artik(cozulmus(s, res)) <= 1e-10


def test_eskenar_ucgen():
    pts = {"p1": Point(0.0, 0.0, fixed=True), "p2": Point(9.5, 0.3), "p3": Point(5.2, 8.1)}
    ents = {"l12": Line("p1", "p2"), "l23": Line("p2", "p3"), "l31": Line("p3", "p1")}
    cs = [
        Constraint(CT.HORIZONTAL, ("l12",)),
        Constraint(CT.LENGTH, ("l12",), 10.0),
        Constraint(CT.EQUAL, ("l12", "l23")),
        Constraint(CT.EQUAL, ("l12", "l31")),
    ]
    res = solve(eskiz(pts, ents, cs))
    p1, p2, p3 = P(res, "p1"), P(res, "p2"), P(res, "p3")
    assert np.allclose(p2, (10.0, 0.0), atol=TOL_X)
    assert np.allclose(p3, (5.0, 5.0 * math.sqrt(3.0)), atol=TOL_X)
    for a, b, c in ((p1, p2, p3), (p2, p3, p1), (p3, p1, p2)):
        assert aci(b - a, c - a) == pytest.approx(math.pi / 3, abs=TOL_A)
    assert res.dof == 0


# --- K4: dikdörtgen -----------------------------------------------------------------------------------


def test_dikdortgen_dof_adim_adim():
    s = dikdortgen()
    assert dof(s) == 4
    assert solve(s).dof == 4

    s.constraints += [Constraint(CT.LENGTH, ("ab",), 40.0), Constraint(CT.LENGTH, ("bc",), 30.0)]
    assert dof(s) == 2
    assert solve(s).dof == 2

    s.points["a"] = Point(0.0, 0.0, fixed=True)
    res = solve(s)
    assert res.dof == 0
    assert dof(s) == 0
    for k, beklenen in {"a": (0, 0), "b": (40, 0), "c": (40, 30), "d": (0, 30)}.items():
        assert np.allclose(P(res, k), beklenen, atol=TOL_X), k
    assert tuple(res.redundant) == ()


def test_dikdortgen_parallel_gereksiz():
    s = dikdortgen()
    s.constraints += [Constraint(CT.PARALLEL, ("ab", "cd")), Constraint(CT.PARALLEL, ("bc", "da"))]
    res = solve(s)
    assert res.dof == 4
    assert dof(s) == 4
    assert set(res.redundant) == {4, 5}

    t = dikdortgen(a=(0.0, 0.0), sabit=True)
    t.constraints += [
        Constraint(CT.LENGTH, ("ab",), 40.0),
        Constraint(CT.LENGTH, ("bc",), 30.0),
        Constraint(CT.PARALLEL, ("ab", "cd")),
        Constraint(CT.PARALLEL, ("bc", "da")),
    ]
    res = solve(t)
    assert res.dof == 0
    assert set(res.redundant) == {6, 7}
    assert np.allclose(P(res, "c"), (40.0, 30.0), atol=TOL_X)


# --- K5: teğet ----------------------------------------------------------------------------------------


def teget_cizgi(y0: float) -> Sketch:
    pts = {"c": Point(0.0, 0.0, fixed=True), "p0": Point(-20.0, y0), "p1": Point(20.0, y0 + 0.5)}
    ents = {"o": Circle("c", 9.7), "l": Line("p0", "p1")}
    cs = [
        Constraint(CT.RADIUS, ("o",), 10.0),
        Constraint(CT.HORIZONTAL, ("l",)),
        Constraint(CT.TANGENT, ("l", "o")),
    ]
    return eskiz(pts, ents, cs)


@pytest.mark.parametrize("y0, y_beklenen, sigma", [(12.0, 10.0, -1), (-13.0, -10.0, 1)])
def test_teget_cizgi_daire_dal(y0, y_beklenen, sigma):
    """Çizgi +x yönünde; merkez çizginin sağında (y0 > 0) → σ = −1, solunda → σ = +1."""
    s = teget_cizgi(y0)
    res = solve(s)
    assert P(res, "p0")[1] == pytest.approx(y_beklenen, abs=TOL_X)
    assert P(res, "p1")[1] == pytest.approx(y_beklenen, abs=TOL_X)
    assert res.radii["o"] == pytest.approx(10.0, abs=TOL_X)
    assert res.sides[2] == sigma
    k = cozulmus(s, res)
    assert k.constraints[2].side == sigma
    assert max_artik(k) <= 1e-10


def iki_daire(cb, rb0: float = 4.0, internal: bool = False) -> Sketch:
    pts = {"ca": Point(0.0, 0.0, fixed=True), "cb": Point(*cb)}
    ents = {"a": Circle("ca", 10.0), "b": Circle("cb", rb0)}
    cs = [
        Constraint(CT.RADIUS, ("a",), 10.0),
        Constraint(CT.RADIUS, ("b",), 4.0),
        Constraint(CT.TANGENT, ("a", "b"), internal=internal),
    ]
    return eskiz(pts, ents, cs)


def test_teget_daire_daire_dis():
    res = solve(iki_daire((15.0, 2.0)))
    assert np.linalg.norm(P(res, "cb")) == pytest.approx(14.0, abs=TOL_X)


def test_teget_daire_daire_ic():
    res = solve(iki_daire((5.0, 1.0), internal=True))
    assert np.linalg.norm(P(res, "cb")) == pytest.approx(6.0, abs=TOL_X)
    assert res.sides[2] == 1  # sign(r_a − r_b)


def test_teget_ic_cakisik_merkez_hata():
    with pytest.raises(SketchError):
        solve(iki_daire((0.0, 0.0), internal=True))


# --- K6: kanal (obround) ------------------------------------------------------------------------------

KANAL_A, KANAL_R = 30.0, 5.0


def kanal() -> Sketch:
    """İki yay + iki çizgi; uçlar paylaşılan noktalar. Döngü CCW: b1 → b2 → (y2) → t2 → t1 → (y1) → b1."""
    pts = {
        "c1": Point(0.3, -0.2),
        "c2": Point(29.5, 0.4),
        "b1": Point(0.2, -5.3),
        "b2": Point(30.4, -4.8),
        "t2": Point(29.7, 5.2),
        "t1": Point(-0.3, 4.9),
    }
    ents = {
        "alt": Line("b1", "b2"),
        "ust": Line("t2", "t1"),
        "y2": Arc("c2", "b2", "t2"),
        "y1": Arc("c1", "t1", "b1"),
    }
    cs = [
        Constraint(CT.TANGENT, ("alt", "y1")),
        Constraint(CT.TANGENT, ("alt", "y2")),
        Constraint(CT.TANGENT, ("ust", "y1")),
        Constraint(CT.TANGENT, ("ust", "y2")),
        Constraint(CT.DISTANCE, ("c1", "c2"), KANAL_A),
        Constraint(CT.RADIUS, ("y1",), KANAL_R),
        Constraint(CT.EQUAL, ("y1", "y2")),
    ]
    return eskiz(pts, ents, cs)


def test_kanal_alan():
    s = kanal()
    res = solve(s)
    k = cozulmus(s, res)
    assert max_artik(k) <= 1e-10
    bol = regions(k)
    assert len(bol) == 1
    assert area(bol[0]) == pytest.approx(2 * KANAL_R * KANAL_A + math.pi * KANAL_R**2, abs=1e-9)


def test_kanal_dof():
    """K6: düzlemde rijit hareket → dof = 3."""
    assert solve(kanal()).dof == 3


# --- K7: serbestlik sayımı ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "points, entities, kimlik, beklenen",
    [
        ({"p": Point(1.0, 2.0)}, {}, "p", 2),
        ({"p0": Point(0.0, 0.0), "p1": Point(3.0, 1.0)}, {"l": Line("p0", "p1")}, "l", 4),
        ({"c": Point(1.0, 1.0)}, {"o": Circle("c", 2.0)}, "o", 3),
        (
            {"c": Point(0.0, 0.0), "s": Point(5.0, 0.0), "e": Point(0.0, 4.0)},
            {"y": Arc("c", "s", "e")},
            "y",
            5,
        ),
    ],
)
def test_bos_oge_serbestligi(points, entities, kimlik, beklenen):
    s = eskiz(points, entities, [])
    assert dof(s) == beklenen
    res = solve(s)
    assert res.dof == beklenen
    assert res.freedom[kimlik] == beklenen


def test_yay_ic_satiri_yaricaplari_esitler():
    """Yayın kendi satırı |s − c| − |e − c| = 0: eşit olmayan başlangıç çözümde eşitlenir."""
    pts = {"c": Point(0.0, 0.0), "s": Point(5.0, 0.0), "e": Point(0.0, 4.0)}
    s = eskiz(pts, {"y": Arc("c", "s", "e")}, [])
    res = solve(s)
    rs = np.linalg.norm(P(res, "s") - P(res, "c"))
    re = np.linalg.norm(P(res, "e") - P(res, "c"))
    assert rs == pytest.approx(re, abs=1e-10)


def test_daire_uzerindeki_nokta_tek_serbestlik_ve_yonu():
    pts = {"c": Point(0.0, 0.0, fixed=True), "q": Point(6.0, 8.0)}
    s = eskiz(
        pts,
        {"o": Circle("c", 10.0)},
        [Constraint(CT.RADIUS, ("o",), 10.0), Constraint(CT.POINT_ON_CIRCLE, ("q", "o"))],
    )
    res = solve(s)
    assert res.dof == 1
    assert res.freedom["q"] == 1
    assert res.freedom["o"] == 0
    # (6, 8)'de teğet yön ±(−0.8, 0.6); x bileşeni ≥ 0 olacak işaret → (0.8, −0.6)
    assert np.allclose(np.asarray(res.directions["q"], float), (0.8, -0.6), atol=1e-9)


def test_tam_tanimli_eskizde_her_oge_sifir():
    res = solve(ucgen_345())
    for k in ("A", "B", "C", "ab", "bc", "ca"):
        assert res.freedom[k] == 0, k


def test_ayni_kisit_iki_kez():
    s = dikdortgen()
    s.constraints.append(Constraint(CT.HORIZONTAL, ("ab",)))
    assert dof(s) == 4
    res = solve(s)
    assert res.dof == 4
    assert 4 in res.redundant


# --- K8: çelişki teşhisi ------------------------------------------------------------------------------


def test_celiski_iki_mesafe():
    s = eskiz(
        {"p": Point(0.0, 0.0), "q": Point(5.5, 0.5)},
        {},
        [Constraint(CT.DISTANCE, ("p", "q"), 5.0), Constraint(CT.DISTANCE, ("p", "q"), 7.0)],
    )
    with pytest.raises(SketchError) as e:
        solve(s)
    assert tuple(sorted(e.value.constraints)) == (0, 1)


def test_celiski_ucgen_aci_ayri_daire_haric():
    s = ucgen_345()
    s.points["m"] = Point(50.0, 50.0)
    s.entities["o"] = Circle("m", 3.0)
    s.constraints.append(Constraint(CT.RADIUS, ("o",), 4.0))  # 4: üçgene bağlı değil
    s.constraints.append(Constraint(CT.ANGLE, ("ab", "bc"), 60.0))  # 5: dik köşede 60°
    with pytest.raises(SketchError) as e:
        solve(s)
    kume = set(e.value.constraints)
    assert {1, 2, 3, 5} <= kume  # üç uzunluk + açı
    assert 4 not in kume


# --- K9: sürükleme ------------------------------------------------------------------------------------


def test_surukle_daire_uzerinde():
    s = eskiz(
        {"c": Point(0.0, 0.0, fixed=True), "q": Point(10.0, 0.0)},
        {"o": Circle("c", 10.0)},
        [Constraint(CT.RADIUS, ("o",), 10.0), Constraint(CT.POINT_ON_CIRCLE, ("q", "o"))],
    )
    once = s.to_dict()
    res = drag(s, "q", (30.0, 40.0))
    assert np.allclose(P(res, "q"), (6.0, 8.0), atol=TOL_X)
    assert max_artik(cozulmus(s, res)) <= 1e-10
    assert s.to_dict() == once


def test_surukle_sabit_uzunluk():
    s = eskiz(
        {"p0": Point(0.0, 0.0, fixed=True), "p1": Point(10.0, 0.0)},
        {"l": Line("p0", "p1")},
        [Constraint(CT.LENGTH, ("l",), 10.0)],
    )
    once = s.to_dict()
    hedef = np.array([20.0, 15.0])
    res = drag(s, "p1", hedef)
    assert np.allclose(P(res, "p1"), 10.0 * hedef / np.linalg.norm(hedef), atol=TOL_X)  # (8, 6)
    assert max_artik(cozulmus(s, res)) <= 1e-10
    assert s.to_dict() == once


def test_surukle_yatay_cizgi_uzerinde():
    s = eskiz(
        {"p0": Point(0.0, 3.0, fixed=True), "p1": Point(10.0, 3.0), "q": Point(2.0, 3.0)},
        {"l": Line("p0", "p1")},
        [Constraint(CT.HORIZONTAL, ("l",)), Constraint(CT.POINT_ON_LINE, ("q", "l"))],
    )
    once = s.to_dict()
    res = drag(s, "q", (5.0, 7.0))
    assert np.allclose(P(res, "q"), (5.0, 3.0), atol=TOL_X)
    assert P(res, "p1")[1] == pytest.approx(3.0, abs=TOL_X)
    assert max_artik(cozulmus(s, res)) <= 1e-10
    assert s.to_dict() == once


def test_surukle_sabit_nokta_hata():
    s = eskiz(
        {"p0": Point(0.0, 0.0, fixed=True), "p1": Point(10.0, 0.0)},
        {"l": Line("p0", "p1")},
        [Constraint(CT.LENGTH, ("l",), 10.0)],
    )
    with pytest.raises(SketchError):
        drag(s, "p0", (1.0, 1.0))


# --- K12: değişmezlik ---------------------------------------------------------------------------------


def serbest_eskiz(T=None) -> Sketch:
    """Sabit noktası olmayan eskiz: 3-4-5 üçgen + AB'ye teğet r = 1 daire. T: rijit hareket."""
    ham = {"A": (0.1, -0.2), "B": (4.3, 0.4), "C": (3.6, 3.3), "m": (2.2, 1.4)}
    if T is not None:
        ham = {k: tuple(T(np.array(v))) for k, v in ham.items()}
    pts = {k: Point(float(v[0]), float(v[1])) for k, v in ham.items()}
    ents = {"ab": Line("A", "B"), "bc": Line("B", "C"), "ca": Line("C", "A"), "o": Circle("m", 1.3)}
    cs = [
        Constraint(CT.LENGTH, ("ab",), 4.0),
        Constraint(CT.DISTANCE, ("B", "C"), 3.0),
        Constraint(CT.LENGTH, ("ca",), 5.0),
        Constraint(CT.RADIUS, ("o",), 1.0),
        Constraint(CT.TANGENT, ("ab", "o")),
    ]
    return eskiz(pts, ents, cs)


def test_rijit_hareket_degismezligi():
    t = math.radians(37.0)
    Rm = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    o = np.array([12.0, -7.0])

    def T(v):
        return Rm @ v + o

    r0 = solve(serbest_eskiz())
    r1 = solve(serbest_eskiz(T))
    for k in r0.points:
        assert np.allclose(P(r1, k), T(P(r0, k)), atol=TOL_X), k
    assert r1.radii["o"] == pytest.approx(r0.radii["o"], abs=TOL_X)
    assert r1.dof == r0.dof


def test_solve_girdiyi_degistirmez():
    s = kanal()
    once = s.to_dict()
    solve(s)
    assert s.to_dict() == once


def test_saglanmis_eskiz_sifir_iterasyon():
    s = dikdortgen(a=(0.0, 0.0), b=(40.0, 0.0), c=(40.0, 30.0), d=(0.0, 30.0))
    res = solve(s)
    assert res.iterations == 0
    for k, p in s.points.items():
        assert np.allclose(P(res, k), (p.x, p.y), atol=1e-12, rtol=0.0)


def test_apply_yaziyor():
    s = teget_cizgi(12.0)
    res = solve(s)
    s2 = kopya(s)
    res.apply(s2)
    for k, p in s2.points.items():
        assert np.allclose((p.x, p.y), P(res, k), atol=0.0, rtol=0.0)
    assert s2.entities["o"].r == pytest.approx(res.radii["o"], abs=0.0)
    assert s2.constraints[2].side == res.sides[2] == -1
    assert set(res.points) == set(s.points)  # sabit noktalar dahil
    assert set(res.radii) == {"o"}


# --- K14: ölçek (flanş) -------------------------------------------------------------------------------

N_DELIK, R_BOLT, R_DELIK, R_DIS = 12, 70.0, 6.0, 100.0


def flans() -> Sketch:
    """Dış daire + 12 delik + 12 construction çizgi (her biri kendi merkez ucuyla), delik başına bir çevre
    noktası ve bir orta nokta. 111 bilinmeyen, 111 satır → dof 0."""
    rng = np.random.default_rng(17)
    pts: dict[str, Point] = {"O": Point(0.0, 0.0, fixed=True), "C0": Point(0.4, -0.3)}
    ents: dict = {"dis": Circle("C0", 97.0)}
    cs = [Constraint(CT.COINCIDENT, ("C0", "O")), Constraint(CT.RADIUS, ("dis",), R_DIS)]

    def g(*v):
        return np.array(v) + rng.uniform(-1.0, 1.0, size=2)

    for i in range(N_DELIK):
        t = 2 * math.pi * i / N_DELIK
        u = np.array([math.cos(t), math.sin(t)])
        pts[f"o{i}"] = Point(*g(0.0, 0.0))
        pts[f"h{i}"] = Point(*g(*(R_BOLT * u)))
        pts[f"r{i}"] = Point(*g(*((R_BOLT + R_DELIK) * u)))
        pts[f"t{i}"] = Point(*g(*(0.5 * R_BOLT * u)))
        ents[f"k{i}"] = Line(f"o{i}", f"h{i}", construction=True)
        ents[f"d{i}"] = Circle(f"h{i}", 5.0 + float(rng.uniform(0.0, 2.0)))
        cs += [
            Constraint(CT.COINCIDENT, (f"o{i}", "O")),
            Constraint(CT.LENGTH, (f"k{i}",), R_BOLT),
            Constraint(CT.POINT_ON_CIRCLE, (f"r{i}", f"d{i}")),
            Constraint(CT.POINT_ON_LINE, (f"r{i}", f"k{i}")),
            Constraint(CT.MIDPOINT, (f"t{i}", f"k{i}")),
        ]
        if i == 0:
            cs += [Constraint(CT.HORIZONTAL, ("k0",)), Constraint(CT.RADIUS, ("d0",), R_DELIK)]
        else:
            cs += [
                Constraint(CT.ANGLE, (f"k{i - 1}", f"k{i}"), 360.0 / N_DELIK),
                Constraint(CT.EQUAL, ("d0", f"d{i}")),
            ]
    return eskiz(pts, ents, cs)


def test_flans_olcek():
    s = flans()
    t0 = time.perf_counter()
    res = solve(s)
    sure = time.perf_counter() - t0
    assert res.iterations <= 20
    assert sure < 0.5
    assert res.dof == 0
    for i in range(N_DELIK):
        t = 2 * math.pi * i / N_DELIK
        assert np.allclose(P(res, f"h{i}"), (R_BOLT * math.cos(t), R_BOLT * math.sin(t)), atol=TOL_X), i
        assert np.allclose(
            P(res, f"r{i}"), ((R_BOLT + R_DELIK) * math.cos(t), (R_BOLT + R_DELIK) * math.sin(t)), atol=TOL_X
        ), i
        assert res.radii[f"d{i}"] == pytest.approx(R_DELIK, abs=TOL_X)
    assert res.radii["dis"] == pytest.approx(R_DIS, abs=TOL_X)
    n_bilinmeyen = 2 * sum(not p.fixed for p in s.points.values()) + sum(
        isinstance(e, Circle) for e in s.entities.values()
    )
    assert n_bilinmeyen == 111
