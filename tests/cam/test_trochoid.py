"""SPEC 19 — trokoidal kanal (K13–K17).

Testler yalnızca SPEC 19 "Trokoidal kanal" kuralı ve "Arayüz" metninden yazıldı; cam/adaptive.py gövdeleri
okunmadı.
Kanal P0 → P1, genişlik w, ρ = (w − D)/2, t birim yön, L = |P1 − P0|:
  döngü merkezleri c_k = P0 + k·(L/N)·t (k = 0..N), eşit aralık p' = L/N.
  Her paso: c_0 − ρt'ye giriş, c_0 merkezli helis (n_h = ⌈ΔZ / (2πρ·tan(ramp_angle))⌉, ΔZ = z_önceki +
  clearance − z_i),
  tabanda bir tam tur, her k = 1..N için G1 (c_(k−1) − ρt → c_k − ρt) ve c_k merkezli tam tur.
Kesme boyu (K16): n_h·√((2πρ)² + (ΔZ/n_h)²) + (N + 1)·2πρ + L.
Ön nokta temas açısı (formül 3): cos φ = ((ρ + r)² − d² − r²) / (2dr), d = ρ + p'.

Ek A (onaylandı 2026-10-18): formül 3 yalnız ön noktadaki açıyı verir; döngü boyunca en büyük açı φ_loop(ρ,
r, p)
daha büyüktür. Döngü aralığı p* = trochoid_loop_pitch(ρ, r, φ_t) (φ_loop ≤ φ_t olan en büyük p), N = ⌈L/p*⌉.
K14 üç biçimde sınanır: (1) ızgarada yeniden oynatma, her parça φ ≤ φ_t + tol(φ_t) + kiriş payı
(adaptref.chord_margin);
(2) ızgarasız (tam) temas: yol boyunca en büyük φ, trochoid_loop_engagement(ρ, r, L/N) ile aynı ve ≤ φ_t +
0,2°;
(3) ön noktada φ = formül 3 (p' = L/N), ızgarada tol(φ) içinde.
Not: Ek A'daki "en büyük φ, tol + 0,2° içinde" eşitliği ızgara yeniden oynatmasında sağlanamıyor (ρ ≲ r küçük
döngülerde
yeni süpürülmüş hücrelerin nicemlemesi ve kiriş payı, h = D/100'de ±2°..±17°); bu eşitlik (2)'de ızgarasız
sınanır.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.adaptive import MaterialGrid, trochoid_loop_engagement, trochoid_loop_pitch, trochoidal_slot
from cam.model import CamError, MoveType, Tool, ToolKind, Toolpath
from cam.ops2d import depths
from cam.profile import Profile, Region
from tests.cam.adaptref import (
    ARC_TYPES,
    arc_sweep,
    cell_centers,
    chord_margin,
    exact_engagements,
    feed_runs,
    flat_tool,
    is_helix,
    make_cut,
    move_length,
    replay,
    tol_phi,
)
from tests.cam.ref2d import moves_of

D = 10.0
r = D / 2
W = 15.0  # ρ = 2,5
PHI_T = 60.0
P0 = np.array([10.0, 5.0])
THETA = math.radians(30.0)
T_DIR = np.array([math.cos(THETA), math.sin(THETA)])
N_DIR = np.array([-T_DIR[1], T_DIR[0]])  # t'nin 90° solu
L = 12.0


def pitch_ref(rho: float, phi: float) -> float:
    """Formül 3 (testin kendi hesabı)."""
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    return -r * c + math.sqrt((rho + r) ** 2 - r * r * s * s) - rho


def phi_front_ref(rho: float, p: float) -> float:
    """Formül 3: ön noktada φ [derece]."""
    d = rho + p
    return math.degrees(math.acos(((rho + r) ** 2 - d * d - r * r) / (2 * d * r)))


def multi_cut(**kw):
    """z 0 → −10, a_p 4: 3 paso; clearance 1,5."""
    args = dict(z_bottom=-10.0, a_p=4.0, clearance=1.5)
    args.update(kw)
    return make_cut(**args)


def slot(w=W, phi_t=PHI_T, length=L, cut=None, climb=True, ramp_angle=2.0, tool=None):
    return trochoidal_slot(
        P0,
        P0 + length * T_DIR,
        w,
        tool or flat_tool(D),
        cut or multi_cut(),
        phi_t,
        ramp_angle=ramp_angle,
        climb=climb,
    )


def loop_centers(tp: Toolpath) -> list[np.ndarray]:
    """İlk pasonun yatay (helis dışı) yay merkezleri, ilk görülme sırasıyla."""
    out: list[np.ndarray] = []
    for p in feed_runs(tp)[0]:
        if p.type in ARC_TYPES and not is_helix(p):
            c = p.center[:2]
            if not out or float(np.hypot(*(out[-1] - c))) > 1e-9:
                out.append(c.copy())
    return out


def geometry(tp: Toolpath, w: float, length: float = L):
    """Yoldan: ρ, N, p' = L/N ve beklenen merkezler c_k = P0 + k·p'·t."""
    rho = (w - D) / 2
    N = len(loop_centers(tp)) - 1
    assert N >= 1
    pp = length / N
    return rho, N, pp, [P0 + k * pp * T_DIR for k in range(N + 1)]


# ---------------------------------------------------------------- K13 geometri


def test_k13_validate_and_safe_z():
    cut = multi_cut()
    tp = slot(cut=cut)
    tp.validate()
    assert tp.start[2] == pytest.approx(cut.z_safe, abs=1e-9)
    assert tp.moves[-1].end[2] == pytest.approx(cut.z_safe, abs=1e-9)
    # her paso G0'larla ayrılmış bir kesme grubu; derinlikler depths() ile aynı
    runs = feed_runs(tp)
    zs = depths(cut.z_top, cut.z_bottom, cut.a_p)
    assert len(runs) == len(zs)
    for run, z in zip(runs, zs, strict=True):
        assert min(p.p1[2] for p in run) == pytest.approx(z, abs=1e-9)


@pytest.mark.parametrize("w,phi_t", [(W, 60.0), (18.0, 45.0), (11.0, 90.0)])
def test_k13_loops_and_links(w, phi_t):
    cut = multi_cut()
    tp = slot(w=w, phi_t=phi_t, cut=cut)
    rho, N, pp, centers = geometry(tp, w)
    p_star = trochoid_loop_pitch(rho, r, phi_t)
    assert 0 < p_star <= pitch_ref(rho, phi_t) * (1 + 1e-12)
    assert N == math.ceil(L / p_star)  # Ek A K13
    for run, z in zip(feed_runs(tp), depths(cut.z_top, cut.z_bottom, cut.a_p), strict=True):
        flat = [p for p in run if not is_helix(p)]
        # tabandaki yatay hareketler: yaylar c_k merkezli, toplam süpürme her merkezde 2π; G1'ler arka
        # noktalar arası
        arcs = [p for p in flat if p.type in ARC_TYPES]
        lines = [p for p in flat if p.type is MoveType.LINEAR]
        for p in flat:
            assert p.p0[2] == pytest.approx(z, abs=1e-9) and p.p1[2] == pytest.approx(z, abs=1e-9)
        seq: list[int] = []
        sweep = np.zeros(N + 1)
        for p in arcs:
            k = int(np.argmin([np.hypot(*(p.center[:2] - c)) for c in centers]))
            assert np.allclose(p.center[:2], centers[k], atol=1e-9)
            R, _, _ = p.arc_form()
            assert R == pytest.approx(rho, abs=1e-9)
            sweep[k] += arc_sweep(p)
            if not seq or seq[-1] != k:
                seq.append(k)
        assert seq == list(range(N + 1)), "döngüler c_0, c_1, …, c_N sırasıyla"
        assert np.allclose(sweep, 2 * math.pi, atol=1e-9), "her merkezde bir tam tur"
        assert len(lines) == N
        for k, p in enumerate(lines, start=1):
            assert np.allclose(p.p0[:2], centers[k - 1] - rho * T_DIR, atol=1e-9)
            assert np.allclose(p.p1[:2], centers[k] - rho * T_DIR, atol=1e-9)
            assert float(np.hypot(*(p.p1[:2] - p.p0[:2]))) == pytest.approx(L / N, abs=1e-9)


@pytest.mark.parametrize("climb,beklenen", [(True, MoveType.ARC_CCW), (False, MoveType.ARC_CW)])
def test_k13_turn_direction(climb, beklenen):
    tp = slot(climb=climb)
    turns = [p for p in moves_of(tp) if p.type in ARC_TYPES and not is_helix(p)]
    assert turns
    assert all(p.type is beklenen for p in turns)


@pytest.mark.parametrize("ramp_angle", [2.0, 5.0])
def test_k13_helix(ramp_angle):
    cut = multi_cut()
    tp = slot(cut=cut, ramp_angle=ramp_angle)
    rho = (W - D) / 2
    tan_r = math.tan(math.radians(ramp_angle))
    z_prev = cut.z_top
    for run, z in zip(feed_runs(tp), depths(cut.z_top, cut.z_bottom, cut.a_p), strict=True):
        dZ = z_prev + cut.clearance - z
        n_h = math.ceil(dZ / (2 * math.pi * rho * tan_r) - 1e-12)
        helix = [p for p in run if is_helix(p)]
        assert helix, "her pasoda helis"
        # helis paso grubunun başında, c_0 − ρt'den z_önceki + clearance'tan başlar, z_i'de biter
        assert run[0] is helix[0]
        assert np.allclose(helix[0].p0[:2], P0 - rho * T_DIR, atol=1e-9)
        assert helix[0].p0[2] == pytest.approx(z_prev + cut.clearance, abs=1e-9)
        assert helix[-1].p1[2] == pytest.approx(z, abs=1e-9)
        toplam = 0.0
        for p in helix:
            assert np.allclose(p.center[:2], P0, atol=1e-9)
            R, _, sw = p.arc_form()
            assert R == pytest.approx(rho, abs=1e-9)
            assert p.p1[2] < p.p0[2]
            assert (p.p0[2] - p.p1[2]) / (rho * sw) <= tan_r * (1 + 1e-9)
            toplam += sw
        assert toplam / (2 * math.pi) == pytest.approx(n_h, abs=1e-9)
        z_prev = z


# ---------------------------------------------------------------- K16 kesme boyu


@pytest.mark.parametrize("w,phi_t,ramp", [(W, 60.0, 2.0), (18.0, 45.0, 3.0), (11.0, 90.0, 2.0)])
def test_k16_cut_length_closed_form(w, phi_t, ramp):
    cut = multi_cut()
    tp = slot(w=w, phi_t=phi_t, cut=cut, ramp_angle=ramp)
    rho, N, pp, centers = geometry(tp, w)
    tan_r = math.tan(math.radians(ramp))
    z_prev = cut.z_top
    for run, z in zip(feed_runs(tp), depths(cut.z_top, cut.z_bottom, cut.a_p), strict=True):
        dZ = z_prev + cut.clearance - z
        n_h = math.ceil(dZ / (2 * math.pi * rho * tan_r) - 1e-12)
        beklenen = n_h * math.hypot(2 * math.pi * rho, dZ / n_h) + (N + 1) * 2 * math.pi * rho + L
        assert sum(move_length(p) for p in run) == pytest.approx(beklenen, rel=1e-6)
        z_prev = z


# ---------------------------------------------------------------- K14 temas, K15 kesilen bölge


def _stock_grid(length: float, w: float, h: float) -> MaterialGrid:
    """Kanalı her yönde w/2 + 3 mm kapsayan dolu dikdörtgen stok."""
    e = P0 + length * T_DIR
    m = w / 2 + 3.0
    lo = np.minimum(P0, e) - m
    hi = np.maximum(P0, e) + m
    return MaterialGrid.from_region(Region(Profile.rectangle(lo[0], lo[1], *(hi - lo))), h)


SINGLE = dict(z_bottom=-5.0, a_p=5.0)  # tek paso


@pytest.mark.parametrize("w,phi_t", [(W, 60.0), (18.0, 45.0), (13.0, 90.0)])
def test_k14_replay_each_piece(w, phi_t):
    """(1) Yeniden oynatmada helis ve tabandaki ilk tur dışındaki her parça φ ≤ φ_t + tol(φ_t) + kiriş
    payı."""
    cut = make_cut(**SINGLE)
    tp = slot(w=w, phi_t=phi_t, cut=cut)
    g = _stock_grid(L, w, D / 100)
    rep = replay(g, tp, r, step=D / 20, z_top=cut.z_top)
    assert rep.phis
    tol = tol_phi(phi_t, g.h, r)
    for phi, s, arc, q in zip(rep.phis, rep.lens, rep.is_arc, rep.where, strict=True):
        assert phi <= phi_t + tol + chord_margin(s, r, arc), (phi, q, arc)


@pytest.mark.slow
@pytest.mark.parametrize("w,phi_t", [(W, 60.0), (18.0, 45.0), (13.0, 90.0), (11.0, 90.0)])
def test_k14_exact_max_along_path(w, phi_t):
    """(2) Izgarasız: yol boyunca (helis ve tabandaki ilk tur hariç) en büyük φ = φ_loop(ρ, r, L/N) ve ≤ φ_t
    + 0,2°.

    Kısa kanal (L_k = 2,5·p*, N = 3): Ek A1'e göre en büyük açı ilk döngüdedir (sonrakilerde daha eski
    döngüler malzemeyi yalnız azaltır). Ölçüm adaptref.exact_engagements (Ek A1 tanımı, yaylar analitik;
    yayda 0,5°, n_α = 2880). Pay: Ek A'nın 0,2°'si + örnekleme 0,3°.
    """
    rho = (w - D) / 2
    p_star = trochoid_loop_pitch(rho, r, phi_t)
    length = 2.5 * p_star
    cut = make_cut(**SINGLE)
    tp = slot(w=w, phi_t=phi_t, length=length, cut=cut)
    _, N, pp, _ = geometry(tp, w, length)
    assert N == 3
    vals = exact_engagements(tp, r, cut.z_top, n=2880, d_ang=0.5)
    phi_max, where, _ = max(vals, key=lambda v: v[0])
    beklenen = trochoid_loop_engagement(rho, r, pp)
    assert beklenen <= phi_t + 0.2
    assert phi_max <= phi_t + 0.2 + 0.3, (phi_max, where)
    assert abs(phi_max - beklenen) <= 0.2 + 0.3, (phi_max, beklenen, where)


def _front_engagement(tp: Toolpath, w: float, length: float, k: int, h=D / 100):
    """Döngü k'nın ön noktasındaki temas açısı (formül 3'ün tanımladığı nokta), ızgarada.

    Izgara, yolun c_k − ρt'ye varan G1 bağlantısına kadarki bütün kesme hareketleriyle yeniden oynatılır;
    sonra takım
    ön nokta b = c_k + ρt'de döngü yönünde (tırmanmada +n) kısa bir adımla (S = 1e-3) ölçülür. Döngü k'nın
    b'ye
    kadarki alt yarısı yalnız b'nin arkasındaki (−n tarafı) malzemeyi keser; tanımdaki dist(q, [a, b]) ≥ r
    koşulu
    o tarafı zaten dışarıda bırakır, bu yüzden ölçüme katılmaz.
    """
    rho, N, pp, centers = geometry(tp, w, length)
    hedef = centers[k] - rho * T_DIR
    son = None
    for i, m in enumerate(tp.moves):
        if m.type is MoveType.LINEAR and np.allclose(m.end[:2], hedef, atol=1e-9):
            son = i
            break
    assert son is not None, f"c_{k} − ρt'ye giden G1 bağlantısı yok"
    kismi = Toolpath(tp.name, tp.tool, tp.start, tp.moves[: son + 1], rpm=tp.rpm)
    g = _stock_grid(length, w, h)
    replay(g, kismi, r, step=D / 20, z_top=0.0)
    b = centers[k] + rho * T_DIR
    return g, g.engagement(b - 1e-3 * N_DIR, b, r)


@pytest.mark.parametrize("w,phi_t", [(W, 60.0), (18.0, 45.0), (13.0, 90.0)])
def test_k14b_front_point_engagement(w, phi_t):
    """(b) Döngünün ön noktasında φ = φ(ρ, L/N) (formül 3), ızgara toleransı tol(φ) içinde."""
    tp = slot(w=w, phi_t=phi_t, cut=make_cut(**SINGLE))
    rho, N, pp, _ = geometry(tp, w)
    beklenen = phi_front_ref(rho, pp)
    assert beklenen <= phi_t + 1e-9
    for k in sorted({min(2, N), N}):
        g, got = _front_engagement(tp, w, L, k)
        assert abs(got - beklenen) <= tol_phi(beklenen, g.h, r), (k, got, beklenen)


@pytest.mark.parametrize("w,phi_t", [(W, 60.0), (18.0, 45.0)])
def test_k15_cut_region(w, phi_t):
    tp = slot(w=w, phi_t=phi_t, cut=make_cut(**SINGLE))
    rho, N, pp, centers = geometry(tp, w)
    g = _stock_grid(L, w, D / 100)
    replay(g, tp, r, step=D / 20, z_top=0.0)
    ilk = _stock_grid(L, w, g.h)
    X, Y = cell_centers(g)
    P = np.stack([X, Y], axis=-1)
    dc = np.min([np.linalg.norm(P - c, axis=-1) for c in centers], axis=0)
    assert not g.m[dc <= w / 2 - g.h].any(), "dairelerin içi boşalmalı"
    ab = L * T_DIR
    t = np.clip(((P - P0) @ ab) / (ab @ ab), 0.0, 1.0)
    ds = np.linalg.norm(P - (P0 + t[..., None] * ab), axis=-1)
    uzak = ds > w / 2 + g.h
    assert np.array_equal(g.m[uzak], ilk.m[uzak]), "kanalın dışı kesilmemeli"


# ---------------------------------------------------------------- K17 hatalı girdiler


def _bad(**kw):
    args = dict(w=W, phi_t=PHI_T, length=L, cut=None, tool=None)
    args.update(kw)
    return lambda: slot(**args)


@pytest.mark.parametrize(
    "call",
    [
        _bad(w=D),
        _bad(w=D - 1.0),
        _bad(length=0.0),
        _bad(phi_t=0.0),
        _bad(phi_t=180.0),
        _bad(phi_t=-5.0),
        _bad(cut=multi_cut(stepover=3.0)),
        _bad(tool=Tool(id=2, name="kuresel10", kind=ToolKind.BALL, D=D, flute_length=30.0)),
        _bad(tool=flat_tool(D, center_cutting=False)),
        _bad(tool=flat_tool(D, flute_length=3.0)),  # a_p = 4 > kesici boy 3
    ],
)
def test_k17_bad_inputs(call):
    with pytest.raises(CamError):
        call()
