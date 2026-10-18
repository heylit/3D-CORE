"""SPEC 10 — fikstür çarpışması: K8 kesici, K9 gövde (sap, tutucu), K10 pabuç ve bağlantılar,
K11 `simulate_setup`, K15 `fixture_collisions` hataları.

Testler sadece SPEC 10 metninden yazıldı; `cam/baglama.py` uygulama kodu okunmadı.
Teori ("Fikstür çarpışması"): her SPEC 05 adımı için takımın en alçak yüzeyi
e(q) = min(e_kesici(q), min_j [H_j + e_düz(q; ρ_j + δ)]), δ = √(dx² + dy²)/2; z_F(q) − e(q) > tol olan
hücre varsa kayıt, depth en büyük fark, (fixture, k) başına tek kayıt; part "kesici" | "sap" | "tutucu".
Bilinen sınır: bağlamadan yatay uzaklığı ≤ R + 2δ olan yol yanlış alarm verebilir (2δ = √2·Δ), > R + 2δ
uzaktaki yol kesin kayıtsız, < R (gerçek çarpışma) kesin kayıtlı. Testlerde Δ = 0.5 → √2·Δ = 0.7071…

Teori mengenesi (K2): sabit çene [−10, 90] × [−20, 0] × [−5, 10], hareketli çene y ∈ [50, 70], yatak üstü −5.
Teori pabucu (K4, y- kenarı): kol [30, 50] × [−72, 8] × [30, 42], cıvata ekseni (40, −32) r = 6, z ∈ [0, 57],
topuk [30, 50] × [−72, −57] × [0, 30]. Stok Stock(0, 0, 0, 80, 50, 30).
"""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from cam.model import CamError, Move, MoveType, Tool, ToolHolder, ToolKind, Toolpath
from cam.sim import simulate
from tests.cam.baglama_ara import (
    FixtureCollision,
    SetupSim,
    clamp_for,
    fixture_collisions,
    fixture_map,
    make_fixture,
    simulate_setup,
    vise_for,
)
from tests.cam.baglama_ref import CLAMP_OLCU, STOK, VISE_GRIP, VISE_OLCU

G0, G1, G2 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW
CELL = 0.5  # fikstür ızgarası Δ
BANT = math.sqrt(2) * CELL  # 2δ = √2·Δ
F = 600.0

FREZE = Tool(1, "f10", ToolKind.FLAT, 10.0, 30.0)  # R = 5, sap yarıçapı 5, L_f = 30
SAPLI = Tool(2, "f10_sap16", ToolKind.FLAT, 10.0, 10.0, shank_d=16.0)  # L_f = 10, sap ρ = 8
TUTUCU = ToolHolder("silindir", 50.0, ((0.0, 15.0), (40.0, 15.0)))  # yarıçap 15
TUTUCULU = Tool(3, "f10_tutucu", ToolKind.FLAT, 10.0, 10.0, shank_d=16.0, stickout=20.0, holder=TUTUCU)


def mengene_fx(ad: str = "mengene"):
    v, fr = vise_for(STOK, VISE_GRIP, "x", **VISE_OLCU)
    return make_fixture(ad, v, fr)


def pabuc_fx(ad: str = "pabuc", side: str = "y-", at: float = 40.0):
    c, fr = clamp_for(STOK, side, at, 8.0, **CLAMP_OLCU)
    return make_fixture(ad, c, fr)


def yol(start, moves, tool=FREZE, ad="yol") -> Toolpath:
    return Toolpath(
        ad,
        tool,
        start,
        [Move(t, p, None if t is G0 else F, c[0] if c else None) for t, p, *c in moves],
        rpm=3000.0,
    )


def m(t, p, c=None):
    return (t, p) if c is None else (t, p, c)


def calistir(ops, fixtures):
    res = simulate(ops, STOK, 1.0)
    maps = [fixture_map(fx, CELL) for fx in fixtures]
    return res, fixture_collisions(ops, res, maps)


def gecis_x(y: float, z: float, tool=FREZE) -> Toolpath:
    """x = −40'tan x = 120'ye y sabit geçiş: k1 G0 iniş, k2 G1 geçiş, k3 G0 çıkış."""
    return yol((-40, y, 50), [m(G0, (-40, y, z)), m(G1, (120, y, z)), m(G0, (120, y, 50))], tool)


# ---------------------------------------------------------------- K8 kesici


def test_k8_sabit_cene_ustunden_gecis():
    # y = −10, z = 5: çene üstü 10 → depth = 10 − 5 = 5, adım k = 2 (G1), op 0
    ops = [gecis_x(-10.0, 5.0)]
    _, kayit = calistir(ops, [mengene_fx()])
    assert len(kayit) == 1
    c = kayit[0]
    assert isinstance(c, FixtureCollision)
    assert c.fixture == "mengene"
    assert c.k == 2
    assert c.op == 0
    assert c.part == "kesici"
    assert c.depth == pytest.approx(5.0, abs=1e-9)
    x, y, z = c.at
    assert z == pytest.approx(5.0, abs=1e-9)  # takımın o hücredeki yüksekliği
    assert -10.0 <= x <= 90.0 and -20.0 <= y <= 0.0  # çene üstündeki bir hücre merkezi


def test_k8_kayit_dondurulmus():
    c = FixtureCollision("m", 1, 0, "kesici", (0.0, 0.0, 0.0), 1.0)
    with pytest.raises(FrozenInstanceError):
        c.depth = 2.0


def test_k8_cene_ustunden_temiz():
    # z = 10.5 > çene üstü 10 → kayıt yok
    _, kayit = calistir([gecis_x(-10.0, 10.5)], [mengene_fx()])
    assert kayit == []


def test_k8_cene_yuzune_paralel_bant_disi():
    # dış yüz y = −20; takım merkezi R + √2·Δ + 0.01 uzakta → kesin kayıtsız
    y = -20.0 - (5.0 + BANT + 0.01)
    _, kayit = calistir([gecis_x(y, 5.0)], [mengene_fx()])
    assert kayit == []


def test_k8_cene_yuzune_paralel_gercek_carpisma():
    # takım merkezi yüzden R − 0.5 = 4.5 uzakta: takım çeneye 0.5 mm girer → kayıt, depth = 10 − 5
    y = -20.0 - 4.5
    _, kayit = calistir([gecis_x(y, 5.0)], [mengene_fx()])
    assert len(kayit) == 1
    assert (kayit[0].k, kayit[0].part) == (2, "kesici")
    assert kayit[0].depth == pytest.approx(5.0, abs=1e-9)


# ---------------------------------------------------------------- K9 gövde


def test_k9_sap_cene_ustunde():
    # kesici bant dışında (merkez dış yüzden R + √2·Δ + 0.01), sap (ρ = 8) çene üstüne biner;
    # sap alt yüzü z + L_f = −3 + 10 = 7 < 10 → part "sap", depth = 10 − 7 = 3
    y = -20.0 - (5.0 + BANT + 0.01)
    _, kayit = calistir([gecis_x(y, -3.0, SAPLI)], [mengene_fx()])
    assert len(kayit) == 1
    c = kayit[0]
    assert (c.k, c.part) == (2, "sap")
    assert c.depth == pytest.approx(10.0 - (-3.0 + 10.0), abs=1e-9)


def test_k9_tutucu_cene_ustunde():
    # kesici ve sap bant dışında (merkez dış yüzden ρ_sap + √2·Δ + 0.01 = 8.717…), tutucu (ρ = 15) biner;
    # tutucu alt yüzü z + stickout = −15 + 20 = 5 → part "tutucu", depth = 10 − 5 = 5
    y = -20.0 - (8.0 + BANT + 0.01)
    _, kayit = calistir([gecis_x(y, -15.0, TUTUCULU)], [mengene_fx()])
    assert len(kayit) == 1
    c = kayit[0]
    assert (c.k, c.part) == (2, "tutucu")
    assert c.depth == pytest.approx(10.0 - (-15.0 + 20.0), abs=1e-9)


def test_k9_tutucusuz_ayni_yol_temiz():
    y = -20.0 - (8.0 + BANT + 0.01)
    _, kayit = calistir([gecis_x(y, -15.0, SAPLI)], [mengene_fx()])
    assert kayit == []


# ---------------------------------------------------------------- K10 pabuç ve bağlantılar


def test_k10_burun_altindan_yuz_alma():
    # z = zmax − 1 = 29'da y = 4 boyunca: kol üstü 42 → depth = 42 − 29 = t_a + 1 = 13
    ops = [yol((-20, 4, 50), [m(G0, (-20, 4, 29)), m(G1, (100, 4, 29)), m(G0, (100, 4, 50))])]
    _, kayit = calistir(ops, [pabuc_fx()])
    assert len(kayit) == 1
    c = kayit[0]
    assert (c.fixture, c.k, c.part) == ("pabuc", 2, "kesici")
    assert c.depth == pytest.approx(12.0 + 1.0, abs=1e-9)


def test_k10_burna_bant_disinda_duran_paso():
    # burun (kolun stok tarafı ucu) y = 8; −Y yönünde gelen paso burna R + √2·Δ + 1 kala durur → kayıt yok
    y_dur = 8.0 + 5.0 + BANT + 1.0
    ops = [yol((40, 60, 50), [m(G0, (40, 60, 29)), m(G1, (40, y_dur, 29)), m(G0, (40, y_dur, 50))])]
    _, kayit = calistir(ops, [pabuc_fx()])
    assert kayit == []


def test_k10_baglanti_g0_civatadan_geciyor():
    # op0 (−10, −32, 20)'de biter, op1 (100, −32, 20)'den başlar: SPEC 05 araya G0 bağlantısı ekler (k = 2),
    # bağlantı z = 20'de cıvatanın (üst 57) içinden geçer → depth = 57 − 20 = 37, kayıt bağlantının k'sıyla
    op0 = yol((-20, -32, 20), [m(G1, (-10, -32, 20))], ad="op0")
    op1 = yol((100, -32, 20), [m(G1, (110, -32, 20))], ad="op1")
    res, kayit = calistir([op0, op1], [pabuc_fx()])
    baglanti = [s for s in res.steps if s.link]
    assert len(baglanti) == 1
    assert len(kayit) == 1
    c = kayit[0]
    assert c.k == baglanti[0].k
    assert c.op == baglanti[0].op
    assert c.part == "kesici"
    assert c.depth == pytest.approx(57.0 - 20.0, abs=1e-9)


def daire(r_y: float) -> Toolpath:
    # cıvata çevresinde z = 50'de (kol üstü 42'nin üstünde, cıvata üstü 57'nin altında) tam daire G2
    p = (40.0 + r_y, -32.0, 50.0)
    return yol((p[0], p[1], 60.0), [m(G1, p), m(G2, p, (40.0, -32.0)), m(G0, (p[0], p[1], 60.0))])


def test_k10_civata_cevresinde_daire_bant_disi():
    # r_y − R > d_b/2 + √2·Δ + ε_yay → kayıt yok (ε_yay = arc_tol = 1e-3)
    r_y = 5.0 + 6.0 + BANT + 1e-3 + 0.01
    _, kayit = calistir([daire(r_y)], [pabuc_fx()])
    assert kayit == []


def test_k10_civata_cevresinde_daire_carpisma():
    # r_y − R < d_b/2 − 0.5 → takım cıvataya girer: daire adımında (k = 2) kayıt, depth = 57 − 50
    r_y = 5.0 + 6.0 - 0.5 - 0.1
    _, kayit = calistir([daire(r_y)], [pabuc_fx()])
    daire_kayit = [c for c in kayit if c.k == 2]
    assert len(daire_kayit) == 1
    assert daire_kayit[0].part == "kesici"
    assert daire_kayit[0].depth == pytest.approx(7.0, abs=1e-9)


# ---------------------------------------------------------------- K11 simulate_setup


def iki_baglama():
    # a_mengene (Teori) ve b_pabuc: x+ kenarı, at = 11 → burun (72, 11, 30), R_z(180°):
    # kol x ∈ [72, 152], y ∈ [1, 21], z ∈ [30, 42]; cıvata ekseni (112, 11); topuk x ∈ [137, 152]
    return [mengene_fx("a_mengene"), pabuc_fx("b_pabuc", "x+", 11.0)]


def iki_baglama_yolu() -> list[Toolpath]:
    # k1 G0 iniş (x = −40, temiz); k2 G1 y = −3, z = 5 boyunca: çene (depth 5) ve kol (depth 42 − 5 = 37);
    # k3 G0 çıkış (x = 160, kola 8 mm: temiz); k4 G0 z = 50'de (60, −10)'a (cıvataya 17 mm: temiz);
    # k5 G1 dalma (60, −10)'da çene üstüne: yalnız mengene, depth 5
    return [
        yol(
            (-40, -3, 50),
            [
                m(G0, (-40, -3, 5)),
                m(G1, (160, -3, 5)),
                m(G0, (160, -3, 50)),
                m(G0, (60, -10, 50)),
                m(G1, (60, -10, 5)),
            ],
        )
    ]


def test_k11_sim_alani_simulate_ile_ayni():
    ops = iki_baglama_yolu()
    sonuc = simulate_setup(ops, STOK, iki_baglama(), cell=1.0, fixture_cell=CELL)
    assert isinstance(sonuc, SetupSim)
    ref = simulate(iki_baglama_yolu(), STOK, 1.0)
    assert sonuc.sim.zmap.z.shape == ref.zmap.z.shape
    assert (sonuc.sim.zmap.z == ref.zmap.z).all()
    assert sonuc.sim.total_time == ref.total_time
    assert sonuc.sim.op_times == ref.op_times
    assert sonuc.sim.collisions == ref.collisions
    assert sonuc.sim.steps == ref.steps


def test_k11_kayitlar_k_fixture_sirasiyla():
    ops = iki_baglama_yolu()
    sonuc = simulate_setup(ops, STOK, iki_baglama(), cell=1.0, fixture_cell=CELL)
    assert [mp.fixture for mp in sonuc.maps] == ["a_mengene", "b_pabuc"]
    assert all(mp.dx == pytest.approx(CELL) for mp in sonuc.maps)
    kayit = sonuc.fixture_collisions
    assert [(c.k, c.fixture) for c in kayit] == [(2, "a_mengene"), (2, "b_pabuc"), (5, "a_mengene")]
    assert [c.depth for c in kayit] == pytest.approx([5.0, 37.0, 5.0], abs=1e-9)
    assert all(c.part == "kesici" for c in kayit)
    # aynı sonuç doğrudan fixture_collisions ile
    assert fixture_collisions(ops, sonuc.sim, sonuc.maps) == kayit


def test_k11_fixture_cell_yoksa_cell():
    sonuc = simulate_setup(iki_baglama_yolu(), STOK, [mengene_fx()], cell=1.0)
    assert sonuc.maps[0].dx == pytest.approx(1.0)  # 100 / ⌈100/1⌉
    assert sonuc.maps[0].nx == 100


def test_k11_yinelenen_fikstur_adi_hata():
    with pytest.raises(CamError):
        simulate_setup(iki_baglama_yolu(), STOK, [mengene_fx("ayni"), pabuc_fx("ayni", "x+", 11.0)], cell=1.0)


def test_k11_uyusmayan_ops_hata():
    # sonuç iki op'luk programdan; tek op'la denetim → adımların op dizini ops'a uymaz
    op0 = yol((-20, -32, 20), [m(G1, (-10, -32, 20))], ad="op0")
    op1 = yol((100, -32, 20), [m(G1, (110, -32, 20))], ad="op1")
    res = simulate([op0, op1], STOK, 1.0)
    maps = [fixture_map(pabuc_fx(), CELL)]
    with pytest.raises(CamError):
        fixture_collisions([op0], res, maps)


# ---------------------------------------------------------------- K15 fixture_collisions hataları


@pytest.mark.parametrize("ad", ["arc_tol", "tol"])
@pytest.mark.parametrize("deger", [0.0, -1e-3])
def test_k15_fixture_collisions_tolerans_hata(ad, deger):
    ops = [gecis_x(-10.0, 5.0)]
    res = simulate(ops, STOK, 1.0)
    maps = [fixture_map(mengene_fx(), CELL)]
    with pytest.raises(CamError):
        fixture_collisions(ops, res, maps, **{ad: deger})
