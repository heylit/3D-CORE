"""SPEC 22 K5–K9 — alın, boy, kaba + ince profil (Pappus), kanal, diş ve iç tornalama hacimleri.

Testler SPEC 22 "Radyal dexel", "Kesici bölge", "Doğrusal hareketin süpürmesi" ve "Parça haritası"
bölümlerinden yazıldı; cam.sim kodu okunmadı. Yollar SPEC 20 üreticileriyle (cam.lathe_ops) kurulur.

Kaynaklar:
- Pappus–Guldin: dönel hacim V = 2π·A·r̄ = π∫x² dz (kesik koni π·h/3·(r₁² + r₁r₂ + r₂²)).
- İçbükey keskin köşede burun yarıçapı dolgusu (spandrel): alan A = r²(1 − π/4), köşeden ağırlık merkezi
  uzaklığı d = r·(10 − 3π)/(12 − 3π) (kare − çeyrek daire).
- Malzeme sonucu alt adımlardan bağımsızdır; doğrusal hareket zincirinde son harita, her adımın kesin
  süpürme aralığının (x → r) hücre aralıklarından çıkarılmasıdır: tests/cam/lsimref.py `cut_map`.
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from cam.lathe import tip_offset
from cam.lathe_ops import TurnCut, face, finish, groove, iso_thread_depth, rough, thread, turn
from cam.model import CylinderStock
from cam.profile import Arc, Line, Profile, Region
from cam.sim import RadialMap, profile_rmap, simulate_lathe
from tests.cam.lsimref import (
    bore_tool,
    centers,
    cut_map,
    groove_tool,
    thread_tool,
    turn_core,
    turn_tool,
)

R_N = 0.8  # tornalama ucu burun yarıçapı
STOK = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0)


def _P(*a: float) -> np.ndarray:
    return np.array(a, dtype=float)


def _spandrel(xc: float, r: float) -> float:
    """İçbükey köşe dolgusunun dönel hacmi: 2π·(x_c + d)·A."""
    A = r * r * (1 - math.pi / 4)
    d = r * (10 - 3 * math.pi) / (12 - 3 * math.pi)
    return 2 * math.pi * (xc + d) * A


def _harita_esit(rmap: RadialMap, beklenen: list, tol: float = 1e-9) -> None:
    assert rmap.nz == len(beklenen)
    for i, iv in enumerate(beklenen):
        got = rmap.intervals(i)
        assert len(got) == len(iv), f"hücre {i}: {got} ≠ {iv}"
        for (a, b), (c, d) in zip(got, iv, strict=True):
            assert a == pytest.approx(c, abs=tol) and b == pytest.approx(d, abs=tol), (
                f"hücre {i}: {got} ≠ {iv}"
            )


def _uc_noktalari(tp) -> list[tuple[float, float]]:
    """Yolun hayali uç noktaları (x, z); yalnız doğrusal hareketli yollar için."""
    return [(p[0], p[2]) for p in tp.points()]


# ------------------------------------------------------------------ K5 alın


def test_K5_alin_tornalama():
    """H = 2.3 mm alın, dolu çubuk: kaldırılan π/4·D²·H (hata ≤ π/4·D²·dz); önde hiç aralık kalmaz."""
    cell, z_face = 0.5, -2.3
    tool = turn_tool(R_N)
    tp = face(STOK, tool, TurnCut(feed=0.2, rpm=1000.0, a_p=1.0), z_face)
    sonuc = simulate_lathe([tp], STOK, cell=cell)
    zc = sonuc.rmap.centers()
    H = -z_face
    assert sonuc.removed_volume == pytest.approx(math.pi / 4 * 40.0**2 * H, abs=math.pi / 4 * 40.0**2 * cell)
    for i, z in enumerate(zc):
        if z > z_face:
            assert sonuc.rmap.intervals(i) == [], f"z = {z}"  # eksene kadar temiz
        else:
            assert sonuc.rmap.intervals(i) == [pytest.approx((0.0, 20.0), abs=1e-9)]
    assert sonuc.collisions == []


def test_K5_alin_boru():
    boru = CylinderStock(D=40.0, zmin=-30.0, zmax=0.0, d=10.0)
    tp = face(boru, turn_tool(R_N), TurnCut(feed=0.2, rpm=1000.0, a_p=1.0), -1.7)
    sonuc = simulate_lathe([tp], boru, cell=0.25)
    assert sonuc.removed_volume == pytest.approx(
        math.pi / 4 * (40.0**2 - 10.0**2) * 1.7, abs=math.pi / 4 * 1600 * 0.25
    )
    for i, z in enumerate(sonuc.rmap.centers()):
        if z > -1.7:
            assert sonuc.rmap.intervals(i) == []


# ------------------------------------------------------------------ K6 boy


def test_K6_boy_tornalama():
    cell, x_f, z_end, R = 0.5, 16.0, -20.2, 20.0
    tool = turn_tool(R_N)
    tp = turn(STOK, tool, TurnCut(feed=0.2, rpm=1000.0, a_p=1.5), x_f, z_end)
    sonuc = simulate_lathe([tp], STOK, cell=cell)
    o = sonuc.rmap.outer()
    for i, z in enumerate(sonuc.rmap.centers()):
        if z >= z_end + R_N:
            assert o[i] == pytest.approx(x_f, abs=1e-9), f"z = {z}"
        elif z < z_end:
            assert o[i] == pytest.approx(R, abs=1e-9), f"z = {z}"  # boy sonunun arkası el değmemiş
    V = math.pi * (R**2 - x_f**2) * (-z_end) - _spandrel(x_f, R_N)
    assert sonuc.removed_volume == pytest.approx(V, abs=math.pi * R**2 * cell)
    assert sonuc.removed_volume == pytest.approx(STOK.volume - sonuc.rmap.volume(), rel=1e-9)


@pytest.mark.parametrize("hangi", ["alin", "boy", "kanal", "dis"])
def test_K5_K6_K8_harita_bagimsiz_referansla(hangi):
    """Doğrusal yollarda son harita = kesin süpürme aralıklarının farkı (alt adımdan bağımsız), 1e-9."""
    if hangi == "alin":
        stok, tool = STOK, turn_tool(R_N)
        tp = face(stok, tool, TurnCut(feed=0.2, rpm=1000.0, a_p=1.0), -2.3)
        core = turn_core(tool)
    elif hangi == "boy":
        stok, tool = STOK, turn_tool(R_N)
        tp = turn(stok, tool, TurnCut(feed=0.2, rpm=1000.0, a_p=1.5), 16.0, -20.2)
        core = turn_core(tool)
    elif hangi == "kanal":
        stok, tool = STOK, groove_tool(tip=3, w=3.0, r=0.3, edge=6.0)
        tp = groove(stok, tool, TurnCut(feed=0.05, rpm=600.0), -20.0, -12.0, 20.0, 16.0)
        core = np.array([[0.0, 0.0], [2.4, 0.0], [2.4, 6.0], [0.0, 6.0]])
    else:
        stok, tool = CylinderStock(D=20.0, zmin=-30.0, zmax=0.0), thread_tool(r=0.1, edge=3.0)
        tp = thread(
            stok, tool, TurnCut(feed=1.0, rpm=500.0), 2.0, -15.0, 10.0, 1.5, iso_thread_depth(1.5), 0.3
        )
        core = turn_core(tool)
    sonuc = simulate_lathe([tp], stok, cell=0.5)
    zc = centers(stok, 0.5)
    init = [[(stok.d / 2, stok.D / 2)] for _ in zc]
    q = tip_offset(tool.tip, tool.nose_r)
    beklenen = cut_map(init, zc, core, tool.nose_r, q, _uc_noktalari(tp))
    _harita_esit(sonuc.rmap, beklenen)


# ------------------------------------------------------------------ K7 Pappus (kaba + ince)


def _profil() -> Profile:
    """Koni + silindir + omuz + dışbükey yay + silindir + omuz, ön uçtan arkaya (z, x)."""
    return Profile(
        [
            Line(_P(0, 8), _P(-6, 12)),
            Line(_P(-6, 12), _P(-14, 12)),
            Line(_P(-14, 12), _P(-14, 13)),
            Arc(_P(-14, 13), _P(-18, 17), _P(-18, 13), True),
            Line(_P(-18, 17), _P(-24, 17)),
            Line(_P(-24, 17), _P(-24, 20)),
        ],
        closed=False,
    )


K7_STOK = CylinderStock(D=40.0, zmin=-40.0, zmax=0.0)
K7_KOSELER = ((-14.0, 12.0), (-24.0, 17.0))  # keskin içbükey köşeler (z_c, x_c)


def _parca_bolgesi() -> Region:
    """Parça yarı kesiti: profil + stok arkası (z ∈ [−40, −24], x ≤ 20) + eksen."""
    segs = [Line(_P(0, 0), _P(0, 8)), *_profil().segments]
    segs += [Line(_P(-24, 20), _P(-40, 20)), Line(_P(-40, 20), _P(-40, 0)), Line(_P(-40, 0), _P(0, 0))]
    return Region(Profile(segs, closed=True))


def _V_parca() -> float:
    """π∫x² dz: koni 8→12 (h 6), silindir 12 (8), yay x = 13 + √(16 − u²) (4), silindir 17 (6),
    stok 20 (16)."""
    koni = 6 / 3 * (64 + 96 + 144)
    yay = 676 + 104 * math.pi + 128 / 3
    return math.pi * (koni + 144 * 8 + yay + 289 * 6 + 400 * 16)


@functools.cache
def _k7(cell: float):
    tool = turn_tool(R_N)
    cut = TurnCut(feed=0.2, rpm=1000.0, a_p=2.0)
    ops = [rough(_profil(), K7_STOK, tool, cut, allowance=0.3), finish(_profil(), K7_STOK, tool, cut)]
    grid = RadialMap.from_stock(K7_STOK, cell)
    part = profile_rmap(_parca_bolgesi(), grid)
    return simulate_lathe(ops, K7_STOK, cell=cell, part=part, arc_tol=1e-5)


@pytest.mark.parametrize("cell", [1.0, 0.5, 0.25])
def test_K7_pappus_hacmi(cell):
    sonuc = _k7(cell)
    Pk = _profil().length
    V = _V_parca() + sum(_spandrel(xc, R_N) for _, xc in K7_KOSELER)
    assert sonuc.rmap.volume() == pytest.approx(V, abs=Pk * cell * 2 * math.pi * 20.0)
    assert sonuc.removed_volume == pytest.approx(K7_STOK.volume - sonuc.rmap.volume(), rel=1e-9)


@pytest.mark.parametrize("cell", [1.0, 0.5, 0.25])
def test_K7_kalan_malzeme_yalniz_koselerde(cell):
    """rest_volume = içbükey köşe hücrelerinde burun dolgusu:
    Σ π·dz·((x_c + r − √(r² − (z_i − z_c − r)²))² − x_c²)."""
    sonuc = _k7(cell)
    zc = sonuc.rmap.centers()
    dz = sonuc.rmap.dz
    beklenen = 0.0
    for z_c, x_c in K7_KOSELER:
        for z in zc:
            if z_c < z < z_c + R_N:
                x = x_c + R_N - math.sqrt(R_N**2 - (z - z_c - R_N) ** 2)
                beklenen += math.pi * dz * (x * x - x_c * x_c)
    assert beklenen > 0
    assert sonuc.rest_volume() == pytest.approx(beklenen, rel=1e-9, abs=1e-9)


# ------------------------------------------------------------------ K8 kanal ve diş


def test_K8_kanal_cok_dalis():
    """W = 8 > w = 3 (4 dalış): kanal hücrelerinde dış yarıçap x_bottom (köşe r dolgusu hariç)."""
    tool = groove_tool(tip=3, w=3.0, r=0.3, edge=6.0)
    tp = groove(STOK, tool, TurnCut(feed=0.05, rpm=600.0), -20.0, -12.0, 20.0, 16.0)
    sonuc = simulate_lathe([tp], STOK, cell=0.25)
    o = sonuc.rmap.outer()
    for i, z in enumerate(sonuc.rmap.centers()):
        if -20.0 + 0.3 <= z <= -12.0 - 0.3:
            assert o[i] == pytest.approx(16.0, abs=1e-9), f"z = {z}"
        elif z < -20.0 or z > -12.0:
            assert o[i] == pytest.approx(20.0, abs=1e-9), f"z = {z}"
    assert not [c for c in sonuc.collisions if c.kind == "kenar_asimi"]


def test_K8_dis_radyal_dalma():
    """T = 8, P = 1.5, h = 17/24·(√3/2)·P: uçlardan l'den uzak hücrelerde dış yarıçap x0 − h."""
    stok = CylinderStock(D=20.0, zmin=-30.0, zmax=0.0)
    l, x0, h = 3.0, 10.0, iso_thread_depth(1.5)  # noqa: E741
    tool = thread_tool(r=0.1, edge=l)
    tp = thread(stok, tool, TurnCut(feed=1.0, rpm=500.0), 2.0, -15.0, x0, 1.5, h, 0.3)
    sonuc = simulate_lathe([tp], stok, cell=0.25)
    o = sonuc.rmap.outer()
    n = 0
    for i, z in enumerate(sonuc.rmap.centers()):
        if -15.0 + l <= z <= 0.0 - l:
            assert o[i] == pytest.approx(x0 - h, abs=1e-9), f"z = {z}"
            n += 1
        elif z < -15.0 - l:
            assert o[i] == pytest.approx(x0, abs=1e-9)
    assert n > 0
    assert not [c for c in sonuc.collisions if c.kind == "kenar_asimi"]


# ------------------------------------------------------------------ K9 iç tornalama


BORU = CylinderStock(D=60.0, zmin=-40.0, zmax=0.0, d=20.0)
R_B = 0.4


def _ic_profil() -> Profile:
    return Profile.polygon([(0, 18), (-10, 18), (-10, 14), (-20, 14), (-20, 10)], closed=False)


@functools.cache
def _k9(cell: float):
    tool = bore_tool(r=R_B, edge=6.0)
    cut = TurnCut(feed=0.15, rpm=800.0, a_p=2.0)
    ops = [
        rough(_ic_profil(), BORU, tool, cut, allowance=0.2, side="ic"),
        finish(_ic_profil(), BORU, tool, cut, side="ic"),
    ]
    return simulate_lathe(ops, BORU, cell=cell, arc_tol=1e-5)


@pytest.mark.parametrize("cell", [1.0, 0.5, 0.25])
def test_K9_ic_tornalama(cell):
    sonuc = _k9(cell)
    inner = sonuc.rmap.inner()
    o = sonuc.rmap.outer()
    for i, z in enumerate(sonuc.rmap.centers()):
        assert o[i] == pytest.approx(30.0, abs=1e-9)  # dış yüzeye dokunulmaz
        if z > -10.0 + R_B:
            assert inner[i] == pytest.approx(18.0, abs=1e-9), f"z = {z}"
        elif -20.0 + R_B < z < -10.0:
            assert inner[i] == pytest.approx(14.0, abs=1e-9), f"z = {z}"
        elif z < -20.0:
            assert inner[i] == pytest.approx(10.0, abs=1e-9), f"z = {z}"
    # Pappus: dış silindir − delik basamakları (+ iki içbükey köşe dolgusu, tolerans içinde)
    V = math.pi * (30.0**2 * 40.0 - 18.0**2 * 10.0 - 14.0**2 * 10.0 - 10.0**2 * 20.0)
    Pk = _ic_profil().length
    assert sonuc.rmap.volume() == pytest.approx(V, abs=Pk * cell * 2 * math.pi * 30.0)
    assert sonuc.removed_volume == pytest.approx(BORU.volume - sonuc.rmap.volume(), rel=1e-9)
