"""SPEC 05 K2–K6 — takım alt yüzeyi h(d), doğrusal süpürme zarfı ve yaylar.

Testler SPEC 05 "Takım alt yüzeyi", "Doğrusal hareketin süpürme zarfı" ve "Yaylar" bölümlerinden yazıldı;
cam.sim kodu okunmadı. Referanslar tests/cam/simref.py'de (formüller orada).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import Move, MoveType, Stock
from cam.sim import ZMap, simulate, sweep_envelope, tool_height
from tests.cam import simref as ref
from tests.cam.simref import G0, G1, ball, bull, drill, flat, path

TOOLS = {
    "duz": flat(D=10.0),
    "kuresel": ball(D=10.0),
    "koseli": bull(D=10.0, rc=2.0),
    "matkap": drill(D=8.0),
}


# ------------------------------------------------------------------ K2 h(d)


@pytest.mark.parametrize("ad", list(TOOLS))
def test_K2_profil_formulu(ad):
    tool = TOOLS[ad]
    R = tool.D / 2
    d = np.linspace(0.0, R, 1001)
    h = np.asarray(tool_height(tool, d), dtype=float)
    np.testing.assert_allclose(h, ref.h_ref(tool, d), rtol=0, atol=1e-12)


def test_K2_bilinen_degerler():
    R = 5.0
    assert float(tool_height(TOOLS["kuresel"], np.array([R]))[0]) == pytest.approx(R, abs=1e-12)
    assert float(tool_height(TOOLS["kuresel"], np.array([3.0]))[0]) == pytest.approx(
        1.0, abs=1e-12
    )  # 5 − √(25−9)
    # köşe radyüslü R = 5, r_c = 2: düz kısım d ≤ 3; d = 5 → h = r_c
    h = np.asarray(tool_height(TOOLS["koseli"], np.array([0.0, 3.0, 5.0])), dtype=float)
    np.testing.assert_allclose(h, [0.0, 0.0, 2.0], rtol=0, atol=1e-12)
    # matkap uç açısı modelde yok → düz kabul
    np.testing.assert_array_equal(
        np.asarray(tool_height(TOOLS["matkap"], np.array([0.0, 2.0, 4.0]))), [0, 0, 0]
    )


@pytest.mark.parametrize("ad", list(TOOLS))
def test_K2_disarida_sonsuz(ad):
    tool = TOOLS[ad]
    R = tool.D / 2
    d = np.array([R + 1e-9, R + 0.5, 100.0])
    h = np.asarray(tool_height(tool, d), dtype=float)
    assert np.all(np.isposinf(h))


# ------------------------------------------------------------------ ortak ızgara

STOK = Stock(0.0, 0.0, -20.0, 40.3, 30.7, 0.0)


def _izgara(cell: float = 0.5):
    g = ZMap.from_stock(STOK, cell)
    X, Y = g.centers()
    return g, X, Y


def _zarf(tool, p0, p1, X, Y) -> np.ndarray:
    return np.asarray(sweep_envelope(tool, p0, p1, X, Y), dtype=float)


# ------------------------------------------------------------------ K3 düz, yatay


P0 = (5.3, 7.1, -3.0)
P1 = (31.7, 22.4, -3.0)


def test_K3_duz_yatay_zarf():
    tool = flat(D=6.0)
    _, X, Y = _izgara()
    d = ref.seg_dist(X, Y, P0, P1)
    net = np.abs(d - 3.0) > 1e-9  # sınıflandırma merkez uzaklığına göre; tam sınır dışarıda tutulur
    e = _zarf(tool, P0, P1, X, Y)
    ic = net & (d < 3.0)
    dis = net & (d > 3.0)
    assert ic.sum() > 100 and dis.sum() > 100
    assert np.all(e[ic] == -3.0)
    assert np.all(np.isposinf(e[dis]))


def test_K3_duz_yatay_simulasyon():
    """Dalma + yatay G1 + geri çekme: stadyum içi z0, dışı değişmemiş (zmax)."""
    tool = flat(D=6.0)
    yol = path(tool, (P0[0], P0[1], 5.0), [G1(*P0), G1(*P1), G1(P1[0], P1[1], 5.0)])
    res = simulate([yol], STOK, cell=0.5)
    g, X, Y = _izgara()
    d = ref.seg_dist(X, Y, P0, P1)
    net = np.abs(d - 3.0) > 1e-9
    z = res.zmap.z
    assert np.all(z[net & (d < 3.0)] == -3.0)
    assert np.all(z[net & (d > 3.0)] == STOK.zmax)


# ------------------------------------------------------------------ K4 küresel / köşe radyüslü, yatay


@pytest.mark.parametrize("ad", ["kuresel", "koseli"])
def test_K4_yatay_profil(ad):
    """Yatay harekette e(q) = z0 + h(d_min) (h artan → en yakın noktada en küçük)."""
    tool = TOOLS[ad]
    R = tool.D / 2
    _, X, Y = _izgara()
    d = ref.seg_dist(X, Y, P0, P1)
    net = np.abs(d - R) > 1e-9
    e = _zarf(tool, P0, P1, X, Y)
    ic = net & (d < R)
    assert ic.sum() > 100
    np.testing.assert_allclose(e[ic], P0[2] + ref.h_ref(tool, d[ic]), rtol=0, atol=1e-9)
    assert np.all(np.isposinf(e[net & (d > R)]))


def test_K4_kuresel_simulasyon():
    tool = ball(D=10.0)
    yol = path(tool, (P0[0], P0[1], 5.0), [G1(*P0), G1(*P1), G1(P1[0], P1[1], 5.0)])
    res = simulate([yol], STOK, cell=0.5)
    _, X, Y = _izgara()
    d = ref.seg_dist(X, Y, P0, P1)
    net = np.abs(d - 5.0) > 1e-9
    beklenen = np.where(d < 5.0, np.minimum(STOK.zmax, -3.0 + ref.h_ref(tool, np.minimum(d, 5.0))), STOK.zmax)
    np.testing.assert_allclose(res.zmap.z[net], beklenen[net], rtol=0, atol=1e-9)


# ------------------------------------------------------------------ K5 eğik hareketler

EGIK = {
    "rampa": ((8.2, 6.3, -1.0), (30.9, 19.4, -4.5)),
    "rampa_yukari": ((30.9, 19.4, -6.0), (8.2, 9.3, -2.0)),
    "dalma": ((17.3, 12.6, 2.0), (17.3, 12.6, -7.5)),
    "kalkis": ((17.3, 12.6, -7.5), (17.3, 12.6, 2.0)),
    "uzay": ((3.1, 25.2, 1.0), (21.4, 13.8, -9.0)),
    "dik_uzay": ((20.2, 10.1, 2.0), (21.0, 10.9, -9.0)),  # neredeyse düşey
}


def _iyi_kosullu(X, Y, p0, p1, R) -> np.ndarray:
    """Sınırdan ≥ 1e-3 uzak hücreler (aralık uçları iyi koşullu)."""
    return np.abs(ref.seg_dist(X, Y, p0, p1) - R) > 1e-3


@pytest.mark.parametrize("ad", list(EGIK))
def test_K5_duz_egik_kapali_form(ad):
    """Düz takım: z(t) doğrusal → en küçük değer d(t) ≤ R aralığının ucunda (kapalı form)."""
    p0, p1 = EGIK[ad]
    tool = flat(D=6.0)
    _, X, Y = _izgara()
    e = _zarf(tool, p0, p1, X, Y)
    beklenen = ref.flat_envelope_ref(X, Y, p0, p1, 3.0)
    m = _iyi_kosullu(X, Y, p0, p1, 3.0)
    assert np.isfinite(beklenen[m]).sum() > 20
    np.testing.assert_array_equal(np.isfinite(e[m]), np.isfinite(beklenen[m]))
    son = m & np.isfinite(beklenen)
    np.testing.assert_allclose(e[son], beklenen[son], rtol=0, atol=1e-12)


@pytest.mark.parametrize("ad", list(EGIK))
@pytest.mark.parametrize("takim", ["kuresel", "koseli"])
def test_K5_egri_uc_kaba_kuvvet(ad, takim):
    """Küresel / köşe radyüslü: ≥ 10⁵ örnekli kaba kuvvet referansıyla ≤ 1e-6 mm."""
    p0, p1 = EGIK[ad]
    tool = {"kuresel": ball(D=6.0), "koseli": bull(D=6.0, rc=1.5)}[takim]
    R = tool.D / 2
    _, X, Y = _izgara()
    e = _zarf(tool, p0, p1, X, Y)
    d = ref.seg_dist(X, Y, p0, p1)
    aday = np.argwhere(d < R - 1e-6)
    assert len(aday) > 20
    rng = np.random.default_rng(5)
    secilen = aday[rng.choice(len(aday), size=min(60, len(aday)), replace=False)]
    for j, i in secilen:
        r = ref.brute_envelope(tool, float(X[j, i]), float(Y[j, i]), p0, p1)
        assert e[j, i] == pytest.approx(r, abs=1e-6), (j, i)
    disari = d > R + 1e-6
    assert np.all(np.isposinf(e[disari]))


def test_K5_dalma_kuresel_kapali_form():
    """Düşey dalmada d sabit: e = min(z0, z1) + h(d)."""
    p0, p1 = EGIK["dalma"]
    tool = ball(D=6.0)
    _, X, Y = _izgara()
    e = _zarf(tool, p0, p1, X, Y)
    d = np.hypot(X - p0[0], Y - p0[1])
    m = d < 3.0 - 1e-9
    np.testing.assert_allclose(e[m], -7.5 + ref.h_ref(tool, d[m]), rtol=0, atol=1e-9)


# ------------------------------------------------------------------ K6 yaylar

C = (20.15, 15.35)
RC = 9.0
ARC_TOL = 1e-3


def _daire_yolu(tool, tip: MoveType, z_bas: float, z_son: float):
    bas = (C[0] + RC, C[1], z_bas)
    son = (C[0] + RC, C[1], z_son)
    mv = [G1(*bas), Move(tip, son, 300.0, center=C), G1(son[0], son[1], 5.0)]
    return path(tool, (bas[0], bas[1], 5.0), mv, "daire")


@pytest.mark.parametrize("tip", [MoveType.ARC_CW, MoveType.ARC_CCW])
def test_K6_tam_daire_kanal(tip):
    """Düz takım, tam daire: halka |RC − R| ≤ |q − c| ≤ RC + R; sınırdan arc_tol + 1e-9'dan uzak hücreler."""
    tool = flat(D=6.0)
    res = simulate([_daire_yolu(tool, tip, -2.0, -2.0)], STOK, cell=0.5, arc_tol=ARC_TOL)
    _, X, Y = _izgara()
    r = np.hypot(X - C[0], Y - C[1])
    sinir = np.minimum(np.abs(r - (RC - 3.0)), np.abs(r - (RC + 3.0)))
    net = sinir > ARC_TOL + 1e-9
    ic = net & (r > RC - 3.0) & (r < RC + 3.0)
    dis = net & ~((r > RC - 3.0) & (r < RC + 3.0))
    assert ic.sum() > 500
    assert np.all(res.zmap.z[ic] == -2.0)
    assert np.all(res.zmap.z[dis] == STOK.zmax)


@pytest.mark.parametrize(
    "tip, th0, sweep",
    [(MoveType.ARC_CCW, 0.0, math.pi), (MoveType.ARC_CW, -math.pi, math.pi)],
)
def test_K6_yarim_yay_yonu(tip, th0, sweep):
    """G3 (C+RC, cy)'den (C−RC, cy)'ye üst yarıyı, G2 alt yarıyı süpürür (+Z'den bakınca)."""
    tool = flat(D=6.0)
    bas = (C[0] + RC, C[1], -2.0)
    son = (C[0] - RC, C[1], -2.0)
    mv = [G1(*bas), Move(tip, son, 300.0, center=C), G1(son[0], son[1], 5.0)]
    res = simulate([path(tool, (bas[0], bas[1], 5.0), mv)], STOK, cell=0.5, arc_tol=ARC_TOL)
    _, X, Y = _izgara()
    d = ref.arc_dist(X, Y, C, RC, th0, sweep)
    net = np.abs(d - 3.0) > ARC_TOL + 1e-9
    assert np.all(res.zmap.z[net & (d < 3.0)] == -2.0)
    assert np.all(res.zmap.z[net & (d > 3.0)] == STOK.zmax)


@pytest.mark.parametrize("tip", [MoveType.ARC_CW, MoveType.ARC_CCW])
def test_K6_helis(tip):
    """Tam tur helis z: −1 → −3. Son noktanın R diski içindeki hücreler tam −3 (helisin en alçak noktası);
    halka hücreleri [−3, −1] aralığında; halka dışı değişmemiş."""
    tool = flat(D=6.0)
    res = simulate([_daire_yolu(tool, tip, -1.0, -3.0)], STOK, cell=0.5, arc_tol=ARC_TOL)
    _, X, Y = _izgara()
    z = res.zmap.z
    son = (C[0] + RC, C[1])
    uc = np.hypot(X - son[0], Y - son[1]) < 3.0 - 1e-9
    assert uc.sum() > 50
    np.testing.assert_allclose(z[uc], -3.0, rtol=0, atol=1e-9)
    r = np.hypot(X - C[0], Y - C[1])
    ic = (r > RC - 3.0 + ARC_TOL + 1e-9) & (r < RC + 3.0 - ARC_TOL - 1e-9)
    assert np.all((z[ic] >= -3.0 - 1e-9) & (z[ic] <= -1.0 + 1e-9))
    # helis z'si açıyla doğrusal: başlangıçtan çeyrek tur sonraki noktanın (yay üstü) hücresi en çok −1.5
    th_ceyrek = -math.pi / 2 if tip is MoveType.ARC_CW else math.pi / 2
    q = (C[0] + RC * math.cos(th_ceyrek), C[1] + RC * math.sin(th_ceyrek))
    j = int((q[1] - STOK.ymin) // res.zmap.dy)
    i = int((q[0] - STOK.xmin) // res.zmap.dx)
    assert z[j, i] <= -1.5 + 1e-9
    dis = (r < RC - 3.0 - ARC_TOL - 1e-9) | (r > RC + 3.0 + ARC_TOL + 1e-9)
    assert np.all(z[dis] == STOK.zmax)


def test_K6_yay_tek_adim():
    """Yay simülasyonda tek hareket olarak kalır: bir k, bir adım."""
    tool = flat(D=6.0)
    res = simulate([_daire_yolu(tool, MoveType.ARC_CW, -2.0, -2.0)], STOK, cell=1.0)
    assert len(res.steps) == 3
    assert res.steps[1].type is MoveType.ARC_CW
    assert res.steps[1].center == pytest.approx(C)
    assert res.points().shape == (4, 3)


def test_K3_hizli_hareket_de_keser():
    """G0 da aynı zarfla malzeme kaldırır (simülasyon gerçekte olanı gösterir)."""
    tool = flat(D=6.0)
    yol = path(tool, (-10.0, 15.0, -2.0), [G0(50.0, 15.0, -2.0)])
    res = simulate([yol], STOK, cell=0.5)
    _, X, Y = _izgara()
    d = np.abs(Y - 15.0)
    assert np.all(res.zmap.z[d < 3.0 - 1e-9] == -2.0)
    assert np.all(res.zmap.z[d > 3.0 + 1e-9] == STOK.zmax)
