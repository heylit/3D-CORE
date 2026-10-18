"""SPEC 19 — adaptif cep (K4–K12).

Testler yalnızca SPEC 19 "Adaptif cep yöntemi", "Arayüz" ve "Kabul kriterleri" metninden yazıldı;
cam/adaptive.py
gövdeleri okunmadı. Algoritmanın ayrıntısı uygulayıcıya bırakıldığından testler özellikleri sınar:
- K4 hareket kuralları (SPEC 03 ile aynı), K5 çakma yok (bölge sınırına uzaklık ≥ r + leave,
tests/cam/ref2d.py),
- K6/K7/K8/K10 "yeniden oynatma" (tests/cam/adaptref.py: from_region(Ω, h) üzerinde hareketler sırayla
  cut_segment / cut_arc ile uygulanır; helis ve tabandaki ilk tam tur hariç her parça ≤ step, φ kesimden önce
  ölçülür),
- K9 dar boğazın sessizce değil uncut_area ile raporlanması, K11 SPEC 05 simülasyonuyla hacim çapraz kontrolü.
T = C ⊕ B_r, C = Ω ⊖ B_(r + leave); T'nin iç hücreleri merkezi C'ye uzaklığı ≤ r − h olanlardır
(adaptref.t_inner
tutucu bir alt küme verir). Dikdörtgen a×b'de alan(T) = ab − (4 − π)r² (dört köşede r yarıçaplı yuvarlatma).
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from cam.adaptive import AdaptiveResult, MaterialGrid, adaptive_pocket
from cam.model import CamError, MoveType, Stock, Tool, ToolKind
from cam.ops2d import depths
from cam.profile import Profile, Region
from cam.sim.simulate import simulate
from tests.cam.adaptref import (
    FEED_TYPES,
    chord_margin,
    flat_tool,
    make_cut,
    replay,
    t_inner,
    tol_phi,
)
from tests.cam.ref2d import RefBolge, cut_depths, moves_of

# ---------------------------------------------------------------- test bölgeleri (uydurma geometri)

CIRCLE = ("circle", (0.0, 0.0), 50.0)
RECT = ("poly", [(0.0, 0.0), (100.0, 0.0), (100.0, 80.0), (0.0, 80.0)])
L_SHAPE = ("poly", [(0.0, 0.0), (50.0, 0.0), (50.0, 20.0), (20.0, 20.0), (20.0, 45.0), (0.0, 45.0)])
ISLAND_RECT = ("poly", [(0.0, 0.0), (60.0, 0.0), (60.0, 50.0), (0.0, 50.0)])
ISLAND = ("circle", (30.0, 25.0), 8.0)


def two_squares(w: float) -> tuple:
    """30×30 iki kare, aralarında 20 mm boyunda, w genişliğinde kanal (kanal ekseni y = 15)."""
    y1, y2 = 15.0 - w / 2, 15.0 + w / 2
    pts = [
        (0.0, 0.0), (30.0, 0.0), (30.0, y1), (50.0, y1), (50.0, 0.0), (80.0, 0.0),
        (80.0, 30.0), (50.0, 30.0), (50.0, y2), (30.0, y2), (30.0, 30.0), (0.0, 30.0),
    ]  # fmt: skip
    return ("poly", pts)


def to_profile(ring) -> Profile:
    if ring[0] == "poly":
        return Profile.polygon(ring[1])
    return Profile.circle(ring[1], ring[2])


def to_region(ref: RefBolge) -> Region:
    return Region(to_profile(ref.outer), [to_profile(h) for h in ref.holes])


def perimeter(ref: RefBolge) -> float:
    total = 0.0
    for ring in [ref.outer, *ref.holes]:
        if ring[0] == "poly":
            P = np.asarray(ring[1], dtype=float)
            total += float(np.sum(np.linalg.norm(np.roll(P, -1, axis=0) - P, axis=1)))
        else:
            total += 2 * math.pi * ring[2]
    return total


# ad: (bölge, D, φ_t, leave)
CASES = {
    "daire_45": (RefBolge(CIRCLE), 10.0, 45.0, 0.0),
    "daire_90": (RefBolge(CIRCLE), 10.0, 90.0, 0.0),
    "dikdortgen_45": (RefBolge(RECT), 10.0, 45.0, 0.0),
    "dikdortgen_90": (RefBolge(RECT), 10.0, 90.0, 0.0),
    "L_45": (RefBolge(L_SHAPE), 6.0, 45.0, 0.0),
    "L_90": (RefBolge(L_SHAPE), 6.0, 90.0, 0.0),
    "ada_45": (RefBolge(ISLAND_RECT, [ISLAND]), 10.0, 45.0, 0.0),
    "ada_90": (RefBolge(ISLAND_RECT, [ISLAND]), 10.0, 90.0, 0.0),
    "ada_90_leave": (RefBolge(ISLAND_RECT, [ISLAND]), 10.0, 90.0, 0.5),
    "kanal_genis_90": (RefBolge(two_squares(16.0)), 10.0, 90.0, 0.0),  # 1,6D
    "kanal_dar_60": (RefBolge(two_squares(10.1)), 10.0, 60.0, 0.0),  # D + 0,1
    "daire_60": (RefBolge(CIRCLE), 10.0, 60.0, 0.0),
    "dikdortgen_60": (RefBolge(RECT), 10.0, 60.0, 0.0),
}
K6_CASES = ["daire_45", "daire_90", "dikdortgen_45", "dikdortgen_90", "L_45", "L_90", "ada_45", "ada_90"]
K8_CASES = [*K6_CASES, "kanal_genis_90"]


@functools.cache
def run_case(name: str) -> tuple[AdaptiveResult, object]:
    """Adaptif cebi üretir ve tek paso derinliğinde yeniden oynatır (önbellekli: her durum bir kez)."""
    bolge, D, phi_t, leave = CASES[name]
    cut = make_cut()  # z 0 → −5, tek paso
    res = adaptive_pocket(to_region(bolge), flat_tool(D), cut, phi_t, leave=leave)
    g = MaterialGrid.from_region(to_region(bolge), res.material.h)
    rep = replay(g, res.toolpath, D / 2, step=D / 20, z_top=cut.z_top)
    return res, rep


# ---------------------------------------------------------------- K4 hareket kuralları


def _k4_check(tp, cut) -> None:
    tp.validate()
    assert tp.start[2] == pytest.approx(cut.z_safe, abs=1e-9)
    assert tp.moves[-1].end[2] == pytest.approx(cut.z_safe, abs=1e-9)
    zs = depths(cut.z_top, cut.z_bottom, cut.a_p)
    assert cut_depths(tp) == pytest.approx(zs, abs=1e-9)
    # her G0, ardından gelen kesme grubunun pasosu z_i için z_(i−1) + clearance'ın altına inmez (z_0 = z_top)
    moves = moves_of(tp)
    prev = [cut.z_top, *zs[:-1]]
    for j, p in enumerate(moves):
        if p.type is not MoveType.RAPID:
            continue
        sonraki = []
        for q in moves[j + 1 :]:
            if q.type is MoveType.RAPID:
                if sonraki:
                    break
                continue
            sonraki.append(q)
        if not sonraki:
            assert p.p1[2] >= cut.z_safe - 1e-9 or p.p1[2] >= cut.z_top + cut.clearance - 1e-9
            continue
        z_min = min(q.p1[2] for q in sonraki)
        i = int(np.argmin([abs(z_min - z) for z in zs]))
        assert z_min == pytest.approx(zs[i], abs=1e-9), "kesme grubu bir paso derinliğinde bitmeli"
        assert p.p1[2] >= prev[i] + cut.clearance - 1e-9, (j, p.p1, prev[i] + cut.clearance)
    # yaylar G2/G3, mutlak merkezli; kesme hareketlerinde ilerleme var
    for m in tp.moves:
        if m.type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            assert m.center is not None


@pytest.mark.slow
@pytest.mark.parametrize("a_p", [2.0, 5.0])
def test_k4_motion_rules(a_p):
    reg = Region(Profile.rectangle(0.0, 0.0, 40.0, 30.0))
    cut = make_cut(a_p=a_p)
    res = adaptive_pocket(reg, flat_tool(10.0), cut, 90.0)
    assert isinstance(res, AdaptiveResult)
    _k4_check(res.toolpath, cut)
    # XY her pasoda aynı: her paso derinliğinde yatay kesme hareketlerinin XY uçları aynı
    zs = depths(cut.z_top, cut.z_bottom, cut.a_p)
    xy = []
    for z in zs:
        pts = [
            (round(p.p0[0], 9), round(p.p0[1], 9), round(p.p1[0], 9), round(p.p1[1], 9))
            for p in moves_of(res.toolpath)
            if p.type in FEED_TYPES and abs(p.p0[2] - z) < 1e-9 and abs(p.p1[2] - z) < 1e-9
        ]
        xy.append(pts)
    assert all(x == xy[0] for x in xy[1:])


@pytest.mark.slow
def test_k4_defaults_and_result_grid():
    """Varsayılan hücre h = D/100; material = from_region(region, h) ızgarası (aynı x0, y0, nx, ny)."""
    D = 10.0
    reg = Region(Profile.rectangle(0.0, 0.0, 40.0, 30.0))
    res = adaptive_pocket(reg, flat_tool(D), make_cut(), 90.0)
    g = MaterialGrid.from_region(reg, D / 100)
    m = res.material
    assert m.h == pytest.approx(D / 100, rel=1e-12)
    assert (m.nx, m.ny) == (g.nx, g.ny)
    assert m.x0 == pytest.approx(g.x0, abs=1e-12) and m.y0 == pytest.approx(g.y0, abs=1e-12)
    assert m.m.shape == (g.ny, g.nx)


@pytest.mark.slow
def test_k4_case_paths_follow_rules():
    for name in ("L_90", "ada_90"):
        res, _ = run_case(name)
        _k4_check(res.toolpath, make_cut())


# ---------------------------------------------------------------- K5 çakma yok


@pytest.mark.slow
@pytest.mark.parametrize("name", [*K6_CASES, "ada_90_leave"])
def test_k5_no_gouge(name):
    bolge, D, _, leave = CASES[name]
    res, _ = run_case(name)
    pts = np.vstack([p.sample(0.25)[:, :2] for p in moves_of(res.toolpath) if p.type in FEED_TYPES])
    assert bolge.contains(pts).all(), "kesme hareketi bölgenin dışında"
    d = bolge.boundary().distance(pts)
    assert d.min() >= D / 2 + leave - 1e-6, (name, float(d.min()))


# ---------------------------------------------------------------- K6 temas sınırı
# Tolerans: tol(φ_t) + kiriş payı (adaptref.chord_margin: parça boyu s için s/(2r) radyan yan bant, yay
# parçasında
# ayrıca parça açısının yarısı). SPEC tol(φ) ızgara nicemlemesini kapsar, adım tanımındaki yan bandı kapsamaz;
# pay koordinatör onayıyla eklendi (2026-10-18). D/20 adımda ≈ 2,9°.


@pytest.mark.slow
@pytest.mark.parametrize("name", K6_CASES)
def test_k6_engagement_limit(name):
    _, D, phi_t, _ = CASES[name]
    res, rep = run_case(name)
    tol = tol_phi(phi_t, res.material.h, D / 2)
    assert rep.phis, "yeniden oynatmada ölçülen kesme parçası yok"
    for phi, s, arc, q in zip(rep.phis, rep.lens, rep.is_arc, rep.where, strict=True):
        assert phi <= phi_t + tol + chord_margin(s, D / 2, arc), (name, phi, q)
    step = D / 20
    assert res.max_engagement <= phi_t + tol + chord_margin(step, D / 2, False)
    assert res.max_engagement > 0


# ---------------------------------------------------------------- K7 dalmasız iniş


@pytest.mark.slow
@pytest.mark.parametrize("name", [*K8_CASES, "kanal_dar_60"])
def test_k7_no_plunge_into_material(name):
    res, rep = run_case(name)
    for q, area in rep.plunges:
        assert area == pytest.approx(0.0, abs=1e-12), (name, q, area)
    # helis dışında aşağı inen kesme hareketi ya düşey G1 ya da XY'li G1'dir; hızlı hareket kesme derinliğine
    # inmez
    for p in moves_of(res.toolpath):
        if p.type is MoveType.RAPID:
            assert p.p1[2] >= make_cut().z_top - 1e-9


# ---------------------------------------------------------------- K8 tam boşaltma


@pytest.mark.slow
@pytest.mark.parametrize("name", K8_CASES)
def test_k8_full_clearing(name):
    bolge, D, _, leave = CASES[name]
    res, rep = run_case(name)
    inner = t_inner(rep.grid, bolge, D / 2, leave)
    assert inner.any()
    kalan = int((rep.grid.m & inner).sum())
    assert kalan == 0, (name, kalan * rep.grid.h**2)
    assert res.uncut_area == 0


# ---------------------------------------------------------------- K9 sessiz hata yok


@pytest.mark.slow
def test_k9_narrow_channel_reported():
    name = "kanal_dar_60"
    bolge, D, phi_t, leave = CASES[name]
    res, rep = run_case(name)
    g = rep.grid
    # K6 bu şekilde de geçer
    tol = tol_phi(phi_t, g.h, D / 2)
    for phi, s, arc in zip(rep.phis, rep.lens, rep.is_arc, strict=True):
        assert phi <= phi_t + tol + chord_margin(s, D / 2, arc)
    assert res.max_engagement <= phi_t + tol + chord_margin(D / 20, D / 2, False)
    # kalan rapor edilir ve yeniden oynatmayla tutarlı
    inner = t_inner(g, bolge, D / 2, leave)
    kalan = g.h**2 * float((g.m & inner).sum())
    assert kalan > 0, "D + 0,1 genişliğinde kanal φ_t = 60° ile açılamaz; kalan olmalı"
    assert res.uncut_area > 0
    assert abs(res.uncut_area - kalan) <= g.h * perimeter(bolge), (res.uncut_area, kalan)
    m = res.material
    assert m.m.shape == g.m.shape
    assert int((m.m != g.m).sum()) <= g.nx + g.ny


# ---------------------------------------------------------------- K10 sabit temas (verim)


@pytest.mark.slow
@pytest.mark.parametrize("name,oran", [("daire_60", 0.70), ("dikdortgen_60", 0.50)])
def test_k10_constant_engagement(name, oran):
    _, _, phi_t, _ = CASES[name]
    _, rep = run_case(name)
    phis = np.asarray(rep.phis)
    lens = np.asarray(rep.lens)
    kesen = phis > 0
    toplam = float(lens[kesen].sum())
    assert toplam > 0
    yakin = float(lens[kesen & (phis >= phi_t - 5.0)].sum())
    assert yakin / toplam >= oran, (name, yakin / toplam)


# ---------------------------------------------------------------- K11 SPEC 05 çapraz kontrolü


@pytest.mark.slow
def test_k11_simulation_volume():
    a, b, D, H = 60.0, 40.0, 10.0, 5.0
    r = D / 2
    cut = make_cut(z_bottom=-H, a_p=2.5)
    reg = Region(Profile.rectangle(0.0, 0.0, a, b))
    res = adaptive_pocket(reg, flat_tool(D), cut, 90.0)
    stock = Stock(-5.0, -5.0, -20.0, a + 5.0, b + 5.0, 0.0)
    sim = simulate([res.toolpath], stock, cell=0.5)
    assert sim.collisions == []
    beklenen = (a * b - (4 - math.pi) * r * r) * H
    assert abs(sim.removed_volume - beklenen) <= 2 * (a + b) * H * 0.5, (sim.removed_volume, beklenen)


# ---------------------------------------------------------------- K12 hatalı girdiler

SMALL = Region(Profile.rectangle(0.0, 0.0, 40.0, 30.0))


def _call(region=SMALL, tool=None, cut=None, phi=90.0, **kw):
    return lambda: adaptive_pocket(region, tool or flat_tool(10.0), cut or make_cut(), phi, **kw)


@pytest.mark.parametrize(
    "call",
    [
        _call(cut=make_cut(stepover=3.0)),
        _call(phi=0.0),
        _call(phi=180.0),
        _call(phi=-10.0),
        _call(leave=-0.1),
        _call(step=0.0),
        _call(step=0.6 * 5.0),
        _call(cell=0.0),
        _call(cell=10.0 / 10),
        _call(ramp_angle=0.0),
        _call(ramp_angle=20.0),
        _call(tool=Tool(id=2, name="kuresel10", kind=ToolKind.BALL, D=10.0, flute_length=30.0)),
        _call(tool=flat_tool(10.0, center_cutting=False)),
        _call(tool=flat_tool(10.0, flute_length=4.0)),  # a_p = 5 > kesici boy 4
        _call(region=Region(Profile.circle((0.0, 0.0), 4.0))),  # Ø8 cep, Ø10 takım: C boş
    ],
)
def test_k12_bad_inputs(call):
    with pytest.raises(CamError):
        call()
