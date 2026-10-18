"""SPEC 21 — torna G-code gidiş-dönüş testleri (K10–K11): read_lathe(write_lathe(yollar)).

Testler sadece SPEC 21 metninden ve sabit arayüzlerden (cam/model.py, cam.lathe_ops imzaları) yazıldı;
cam/gcode/lathe.py gövdesi okunmadı. Geometri uydurmadır.

Okunan her yol (tc = (x_tc, z_tc) takım değiştirme noktası, P_A = yolun başı):
- start = (x_A, 0, z_tc): takım değişiminden sonraki ilk G0 X<2x_A> z_tc'de.
- moves = [G0 → P_A (z_A ≠ z_tc ise)] + özgün hareketler + [geri çekme G0'ları: Z<z_tc>, X<2x_tc>].
Toleranslar: x 0,25·10⁻³, z 0,5·10⁻³ mm; ilerleme 0,5·10⁻³, hatve 0,5·10⁻⁴ mm/dev; yay merkezi 1e-2 mm;
rpm ve css tam sayıya yuvarlanmış değer.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.gcode import fmt
from cam.gcode.lathe import read_lathe, write_lathe
from cam.lathe_ops import TurnCut, face, finish, groove, iso_thread_depth, rough, thread, turn
from cam.model import (
    ARCS,
    CylinderStock,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Toolpath,
)
from cam.profile import Arc, Line, Profile

TC = (50.0, 50.0)
TOL_X = 0.25e-3
TOL_Z = 0.5e-3
TOL_F = 0.5e-3
TOL_P = 0.5e-4
TOL_C = 1e-2

TURN, BORE, GROOVE, THREAD = (
    LatheToolKind.TURN,
    LatheToolKind.BORE,
    LatheToolKind.GROOVE,
    LatheToolKind.THREAD,
)
G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW

BAR = CylinderStock(D=50.0, zmin=-100.0, zmax=0.0)
BAR60 = CylinderStock(D=60.0, zmin=-100.0, zmax=0.0)
TUBE = CylinderStock(D=60.0, zmin=-100.0, zmax=0.0, d=16.0)
M20 = CylinderStock(D=20.0, zmin=-50.0, zmax=0.0)
TUBE40 = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0, d=16.0)


# ------------------------------------------------------------------ karşılaştırma


def same_point(a, b) -> None:
    assert abs(a[0] - b[0]) <= TOL_X, (a, b)
    assert a[1] == 0.0
    assert abs(a[2] - b[2]) <= TOL_Z, (a, b)


def check_roundtrip(orig: Toolpath, got: Toolpath, tc=TC) -> None:
    got.validate()
    assert got.plane is Plane.ZX and got.feed_mode is FeedMode.PER_REV
    assert got.tool == orig.tool
    assert got.name.startswith(f"T{orig.tool.id}-")
    assert got.rpm == round(orig.rpm)
    assert got.css == (None if orig.css is None else round(orig.css))

    x_tc, z_tc = tc
    xA, _, zA = orig.start
    same_point(got.start, (xA, 0.0, z_tc))
    k = 0
    if fmt(zA, 3) != fmt(z_tc, 3):
        k = 1
        assert got.moves[0].type is G0
        same_point(got.moves[0].end, orig.start)

    n = len(orig.moves)
    assert len(got.moves) >= k + n
    lead_tol = TOL_P if orig.tool.kind is THREAD else TOL_F
    for i, (m0, m1) in enumerate(zip(orig.moves, got.moves[k : k + n], strict=True)):
        assert m1.type is m0.type, (i, m0, m1)
        same_point(m1.end, m0.end)
        if m0.type is G0:
            assert m1.feed is None
        else:
            assert abs(m1.feed - m0.feed) <= lead_tol, (i, m0.feed, m1.feed)
        if m0.type in ARCS:
            assert np.hypot(*np.subtract(m1.center, m0.center)) <= TOL_C, (i, m0.center, m1.center)

    # araya sadece eksen eksen geri çekme G0'ları: Z<z_tc>, sonra X<2x_tc>
    tail = got.moves[k + n :]
    assert len(tail) <= 2
    p = got.moves[k + n - 1].end
    for m in tail:
        assert m.type is G0
        moved = [abs(m.end[0] - p[0]) > 1e-9, abs(m.end[2] - p[2]) > 1e-9]
        assert sum(moved) == 1  # tek eksen
        p = m.end
    same_point(p, (x_tc, 0.0, z_tc))


# ------------------------------------------------------------------ K10 SPEC 20 işlemleri


def ttool(id: int, tip: int = 3, r: float = 0.8, kind=TURN) -> LatheTool:
    return LatheTool(id, f"T{id}", kind, nose_r=r, tip=tip, kappa_r=93.0, eps_r=55.0)


def gtool(id: int) -> LatheTool:
    return LatheTool(id, f"K{id}", GROOVE, nose_r=0.2, tip=3, kappa_r=90.0, eps_r=90.0, width=3.0)


def thtool(id: int, tip: int = 8) -> LatheTool:
    return LatheTool(id, f"D{id}", THREAD, nose_r=0.1, tip=tip, kappa_r=60.0, eps_r=60.0)


def cut(a_p: float | None = 2.0, css: float | None = 180.0) -> TurnCut:
    return TurnCut(feed=0.2, rpm=2000.0, css=css, a_p=a_p)


def tcut() -> TurnCut:
    return TurnCut(feed=0.1, rpm=800.0)


def p_shoulder() -> Profile:
    """Omuzlu mil (z, x): x = 10 (z 0..−20), x = 16 (−20..−40), alın x = 25'e."""
    return Profile.polygon(
        [(0.0, 10.0), (-20.0, 10.0), (-20.0, 16.0), (-40.0, 16.0), (-40.0, 25.0)], closed=False
    )


def p_finish() -> Profile:
    """Pah + silindir + R2 içbükey dolgu + omuz + silindir + 30° koni + alın x = 30'a."""
    x_cone = 18.0 + 10.0 * math.tan(math.radians(30.0))
    return Profile(
        [
            Line((0.0, 8.0), (-2.0, 10.0)),
            Line((-2.0, 10.0), (-15.0, 10.0)),
            Arc((-15.0, 10.0), (-17.0, 12.0), (-15.0, 12.0), ccw=False),
            Line((-17.0, 12.0), (-17.0, 18.0)),
            Line((-17.0, 18.0), (-25.0, 18.0)),
            Line((-25.0, 18.0), (-35.0, x_cone)),
            Line((-35.0, x_cone), (-35.0, 30.0)),
        ],
        closed=False,
    )


def p_bore() -> Profile:
    """İç profil: ağızda pah, iç omuzlar, delik yüzeyi x = 8'e iner."""
    return Profile.polygon(
        [(0.0, 14.0), (-2.0, 12.0), (-15.0, 12.0), (-15.0, 10.0), (-30.0, 10.0), (-30.0, 8.0)], closed=False
    )


def spec20_ops() -> list[Toolpath]:
    return [
        face(BAR, ttool(1), cut(), z_face=-3.0),  # x = −r'ye iner: negatif X
        turn(BAR, ttool(2), cut(), x_final=20.0, z_end=-30.0),
        rough(p_shoulder(), BAR, ttool(3), cut(a_p=3.0), allowance=0.3),
        finish(p_finish(), BAR60, ttool(4), cut(a_p=None)),
        finish(p_bore(), TUBE, ttool(5, tip=2, r=0.4, kind=BORE), cut(a_p=None), side="ic"),
        groove(BAR, gtool(6), cut(a_p=None), z_left=-20.0, z_right=-12.0, x_top=25.0, x_bottom=20.0),
        thread(
            M20,
            thtool(7),
            tcut(),
            z_start=3.0,
            z_end=-20.0,
            x0=10.0,
            pitch=1.5,
            depth=iso_thread_depth(1.5),
            first=0.3,
            minimum=0.05,
        ),
        thread(
            TUBE40,
            thtool(8, tip=6),
            tcut(),
            z_start=2.0,
            z_end=-15.0,
            x0=8.0,
            pitch=1.5,
            depth=iso_thread_depth(1.5, external=False),
            first=0.25,
            spring=1,
            side="ic",
        ),
        thread(
            M20,
            thtool(9),
            tcut(),
            z_start=3.0,
            z_end=-20.0,
            x0=10.0,
            pitch=25.4 / 14,
            depth=iso_thread_depth(25.4 / 14),
            first=0.35,
            minimum=0.05,
            infeed="yanak",
        ),
    ]


@pytest.mark.parametrize("spindle", ["M3", "M4"])
def test_k10_spec20_islemleri_tek_programda(spindle):
    ops = spec20_ops()
    for tp in ops:
        tp.validate()
    text = write_lathe(ops, spindle=spindle, tool_change=TC)
    tools = {tp.tool.id: tp.tool for tp in ops}
    got = read_lathe(text, tools, spindle=spindle)
    assert len(got) == len(ops)
    for o, g in zip(ops, got, strict=True):
        check_roundtrip(o, g)


def test_k10_dis_yollarinda_g32_ve_hatve():
    ops = spec20_ops()
    text = write_lathe(ops, spindle="M3", tool_change=TC)
    assert "G32" in text
    assert "F1.8143" in text  # 25,4/14 = 1,814285… → 4 ondalık
    assert "G96" in text and "G97 S800" in text


# ------------------------------------------------------------------ K11 rastgele


def random_path(seed: int, n: int = 200, css: float | None = 200.0) -> Toolpath:
    """Sabit tohumlu ZX yolu: G0 eksen eksen, G1, G2/G3 (süpürme 0,3..2π − 0,3), bütün yay x ∈ [0, 40]."""
    rng = np.random.default_rng(seed)
    X_MAX, Z_MIN, Z_MAX = 40.0, -80.0, 5.0
    z, x = 2.0, 20.0
    start = (x, 0.0, z)
    moves: list[Move] = []
    while len(moves) < n:
        kind = rng.choice(["G0", "G1", "ARC"], p=[0.3, 0.3, 0.4])
        feed = float(rng.uniform(0.05, 0.5))
        if kind == "G0":
            if rng.random() < 0.5:
                xn = float(rng.uniform(0.0, X_MAX))
                if abs(xn - x) < 0.05:
                    continue
                x = xn
            else:
                zn = float(rng.uniform(Z_MIN, Z_MAX))
                if abs(zn - z) < 0.05:
                    continue
                z = zn
            moves.append(Move(G0, (x, 0.0, z)))
        elif kind == "G1":
            xn, zn = float(rng.uniform(0.0, X_MAX)), float(rng.uniform(Z_MIN, Z_MAX))
            if math.hypot(xn - x, zn - z) < 0.05:
                continue
            x, z = xn, zn
            moves.append(Move(G1, (x, 0.0, z), feed=feed))
        else:
            r = float(rng.uniform(0.5, 6.0))
            th0 = float(rng.uniform(0.0, 2 * math.pi))
            cu, cv = z - r * math.cos(th0), x - r * math.sin(th0)  # (u, v) = (z, x)
            if cv - r < 0.0 or cv + r > X_MAX or cu - r < Z_MIN or cu + r > Z_MAX:
                continue
            delta = float(rng.uniform(0.3, 2 * math.pi - 0.3))
            ccw = bool(rng.random() < 0.5)
            th1 = th0 + delta if ccw else th0 - delta
            z, x = cu + r * math.cos(th1), cv + r * math.sin(th1)
            moves.append(Move(G3 if ccw else G2, (x, 0.0, z), feed=feed, center=(cv, cu)))
    tool = LatheTool(1, "T1", TURN, nose_r=0.8, tip=3, kappa_r=93.0, eps_r=55.0)
    tp = Toolpath(
        "rastgele", tool, start, moves, rpm=1500.0, plane=Plane.ZX, feed_mode=FeedMode.PER_REV, css=css
    )
    tp.validate()
    return tp


@pytest.mark.parametrize(("seed", "css", "spindle"), [(21, 200.0, "M3"), (2121, None, "M4")])
def test_k11_rastgele_gidis_donus(seed, css, spindle):
    tp = random_path(seed, css=css)
    assert len(tp.moves) == 200
    assert {m.type for m in tp.moves} == {G0, G1, G2, G3}
    text = write_lathe([tp], spindle=spindle, tool_change=TC)
    (got,) = read_lathe(text, {1: tp.tool}, spindle=spindle)
    check_roundtrip(tp, got)
