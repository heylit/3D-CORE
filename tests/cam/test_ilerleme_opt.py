"""SPEC 32 K8–K13 — talaş incelmesi, güç / tork sınırı, geometri korunumu, bölütleme, hava ilerlemesi,
görünür atlama.

Beklenen ilerlemeler SPEC 32 "İlerleme ayarı" kapalı formlarından: c_ince = hex*/hex(ae),
c_P = (η·P_maks/P)^(1/(1−mc)), c_M = (η·M_maks/M)^(1/(1−mc)), c = min(c_ince, c_P, c_M, max_factor),
F' = ⌊min(F·c, feed_max)/res⌋·res. Ölçülen ae ve P değerleri plan.loads_before'dan alınır (ızgara hatası
kapalı formu bozmasın); kendileri K4/K5 toleransıyla tabloya bağlanır.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from cam.gcode import DrillOp
from cam.ilerleme_opt import FeedPlan, optimize_feed, split_moves
from cam.kuvvet import SpindleLimits, milling_loads
from cam.model import ARCS, Move, MoveType, Stock, Tool, Toolpath
from cam.sim import Machine, simulate
from tests.cam.kuvvet_ref import (
    AP,
    CELL,
    CELL_T,
    F_T,
    FZ,
    MC,
    REL_IZGARA,
    STOCK,
    T_STOCK,
    TABLO,
    D,
    F,
    asagi_yuvarlanmis,
    degisim,
    hex_kapali,
    kanal_programi,
    malzeme,
    parmak,
    torna_programi,
    torna_sim,
    yan_programi,
    yuk,
)

SEG = 10.0  # analiz bölütü: hücrenin katı, bölüt başına ölçülen ae kesine yakın
RES = 0.1


def _plan(ops, mat, limits=None, **kw) -> FeedPlan:
    kw.setdefault("seg", SEG)
    kw.setdefault("cell", CELL)
    return optimize_feed(ops, STOCK, mat, limits or SpindleLimits(), **kw)


# ------------------------------------------------------------------ K8 talaş incelmesi


def _yan_plan():
    mat = malzeme()
    tp, ix = yan_programi()
    return tp, ix, _plan([tp], mat)


def test_k8_inceltme_ae1():
    tp, ix, plan = _yan_plan()
    ld = yuk(plan.loads_before, 0, ix["ae1"])
    assert ld.ae == pytest.approx(1.0, rel=REL_IZGARA)
    c = FZ / hex_kapali(FZ, ld.ae)  # hex* = programlanan fz
    ch = degisim(plan, 0, ix["ae1"])
    assert ch.F_old == pytest.approx(F)
    asagi_yuvarlanmis(ch.F_new, F * min(c, 2.0), RES)
    assert ch.F_new == pytest.approx(900 / 0.6, rel=0.05)  # ≈ 1500
    assert ch.reason == "inceltme"
    assert plan.ops[0].moves[ix["ae1"]].feed == pytest.approx(ch.F_new, abs=1e-12)


def test_k8_degismedi():
    tp, ix, plan = _yan_plan()
    for ad in ("kanal", "ae5"):
        ch = degisim(plan, 0, ix[ad])
        assert ch.F_new == F, ad
        assert ch.reason == "degismedi", ad
        assert plan.ops[0].moves[ix[ad]].feed == F


def test_k8_target_hex():
    mat = malzeme()
    # hex* = 0.08 → kanalda (hex = fz = 0.1) c = 0.8, reason inceltme
    tp, ix = kanal_programi()
    plan = _plan([tp], mat, target_hex=0.08)
    ch = degisim(plan, 0, ix["kanal"])
    asagi_yuvarlanmis(ch.F_new, F * 0.08 / FZ, RES)
    assert ch.reason == "inceltme"


def test_k8_max_factor():
    mat = malzeme()
    tp, ix = yan_programi()
    plan = _plan([tp], mat, max_factor=1.5)
    ch = degisim(plan, 0, ix["ae1"])
    assert ch.F_new == pytest.approx(1350.0, abs=1e-9)
    assert ch.reason == "en_cok"


def test_k8_feed_max():
    mat = malzeme()
    tp, ix = yan_programi()
    plan = _plan([tp], mat, feed_max=1200.0)
    ch = degisim(plan, 0, ix["ae1"])
    assert ch.F_new == pytest.approx(1200.0, abs=1e-9)
    assert ch.reason == "ilerleme_siniri"
    assert degisim(plan, 0, ix["kanal"]).F_new == F  # sınırın altındakiler değişmez


# ------------------------------------------------------------------ K9 güç ve tork sınırı


@pytest.mark.parametrize("eta", [1.0, 0.8])
def test_k9_guc_siniri(eta):
    mat = malzeme()
    tp, ix = kanal_programi()
    lim = SpindleLimits(P_max=1.0, eta=eta)
    plan = _plan([tp], mat, lim)
    ld = yuk(plan.loads_before, 0, ix["kanal"])
    assert ld.P == pytest.approx(TABLO[10.0][2], rel=REL_IZGARA)
    c_P = (eta * 1.0 / ld.P) ** (1 / (1 - MC))  # η = 1: (1/1.343797)^(4/3)
    ch = degisim(plan, 0, ix["kanal"])
    asagi_yuvarlanmis(ch.F_new, F * c_P, RES)
    assert ch.reason == "guc"
    # yeniden simülasyonda o hareketin istediği güç sınırda: P/η ≤ 1.0 ve ≥ 1.0·(1 − 10⁻³)
    sonra = yuk(plan.loads_after, 0, ix["kanal"])
    assert sonra.P / eta <= 1.0 * (1 + 1e-9)
    assert sonra.P / eta >= 1.0 * (1 - 1e-3)
    assert plan.overloads_after == []
    assert any(o.kind == "guc" and o.move == ix["kanal"] for o in plan.overloads_before)


def test_k9_tork_siniri():
    mat = malzeme()
    tp, ix = kanal_programi()
    plan = _plan([tp], mat, SpindleLimits(M_max=4.0, eta=1.0))
    ld = yuk(plan.loads_before, 0, ix["kanal"])
    assert ld.M == pytest.approx(TABLO[10.0][3], rel=REL_IZGARA)
    ch = degisim(plan, 0, ix["kanal"])
    asagi_yuvarlanmis(ch.F_new, F * (4.0 / ld.M) ** (1 / (1 - MC)), RES)
    assert ch.reason == "tork"
    sonra = yuk(plan.loads_after, 0, ix["kanal"])
    assert 4.0 * (1 - 1e-3) <= sonra.M <= 4.0 * (1 + 1e-9)
    assert plan.overloads_after == []


def test_k9_en_az():
    mat = malzeme()
    # P_max çok küçük → c_P < min_factor → F' = F·min_factor, "en_az", aşırı yük kalır
    tp, ix = kanal_programi()
    plan = _plan([tp], mat, SpindleLimits(P_max=0.01, eta=1.0))
    ch = degisim(plan, 0, ix["kanal"])
    assert ch.F_new == pytest.approx(F * 0.1, abs=1e-9)
    assert ch.reason == "en_az"
    assert any(o.kind == "guc" and o.op == 0 and o.move == ix["kanal"] for o in plan.overloads_after)
    plan = _plan([tp], mat, SpindleLimits(P_max=0.01, eta=1.0), min_factor=0.5)
    assert degisim(plan, 0, ix["kanal"]).F_new == pytest.approx(F * 0.5, abs=1e-9)


def test_k9_torna_guc_siniri():
    mat = malzeme()
    torna_sim()
    tp = torna_programi()
    res = 1e-4  # G95 ilerlemesi mm/dev: ince çözünürlük
    plan = optimize_feed([tp], T_STOCK, mat, SpindleLimits(P_max=1.0, eta=1.0), cell=CELL_T, resolution=res)
    ld = yuk(plan.loads_before, 0, 1)
    c_P = (1.0 / ld.P) ** (1 / (1 - MC))
    ch = degisim(plan, 0, 1)
    asagi_yuvarlanmis(ch.F_new, F_T * c_P, res)
    assert ch.reason == "guc"
    sonra = yuk(plan.loads_after, 0, 1)
    assert 1.0 * (1 - 1e-3) <= sonra.P <= 1.0 * (1 + 1e-9)
    assert plan.overloads_after == []


def test_k9_torna_inceltme_yok():
    mat = malzeme()
    # tornada c_ince = 1: sınırsız iş milinde ilerleme değişmez
    torna_sim()
    tp = torna_programi()
    plan = optimize_feed([tp], T_STOCK, mat, SpindleLimits(), cell=CELL_T, resolution=1e-4)
    ch = degisim(plan, 0, 1)
    assert ch.F_new == F_T
    assert ch.reason == "degismedi"


# ------------------------------------------------------------------ K10 geometri değişmez


def _rastgele_program(seed: int = 32) -> tuple[Toolpath, Stock]:
    """Sabit tohumlu 30 hareket: G1 (eğik dahil), G2/G3 (helis dahil), G0 kalkış / konumlanma."""
    rng = np.random.default_rng(seed)
    tool = Tool(id=2, name="p6", kind="duz", D=6.0, flute_length=15.0, flutes=2)
    stock = Stock(0.0, 0.0, -10.0, 60.0, 40.0, 0.0)
    lo, hi = np.array([8.0, 8.0]), np.array([52.0, 32.0])
    p = np.array([10.0, 10.0, 5.0])
    moves: list[Move] = []

    def f():
        return float(rng.integers(30, 120) * 10)

    while len(moves) < 30:
        r = rng.random()
        if r < 0.12 and len(moves) <= 27:
            q = rng.uniform(lo, hi)
            moves += [Move(MoveType.RAPID, (p[0], p[1], 5.0)), Move(MoveType.RAPID, (q[0], q[1], 5.0))]
            p = np.array([q[0], q[1], 5.0])
        elif r < 0.6:
            q = rng.uniform(lo, hi)
            z = float(rng.uniform(-2.5, 0.5))
            moves.append(Move(MoveType.LINEAR, (q[0], q[1], z), feed=f()))
            p = np.array([q[0], q[1], z])
        else:
            rho = float(rng.uniform(3.0, 8.0))
            a = float(rng.uniform(0, 2 * math.pi))
            c = p[:2] + rho * np.array([math.cos(a), math.sin(a)])
            if np.any(c - rho < 3.0) or np.any(c + rho > np.array([57.0, 37.0])):
                continue
            th0 = a + math.pi  # merkezden başlangıca açı
            cw = bool(rng.random() < 0.5)
            d = float(rng.uniform(0.3, 2.5)) * (-1 if cw else 1)
            e = c + rho * np.array([math.cos(th0 + d), math.sin(th0 + d)])
            z = float(rng.uniform(-2.5, 0.5))
            t = MoveType.ARC_CW if cw else MoveType.ARC_CCW
            moves.append(Move(t, (e[0], e[1], z), feed=f(), center=(c[0], c[1])))
            p = np.array([e[0], e[1], z])
    tp = Toolpath("rastgele", tool, (10.0, 10.0, 5.0), moves[:30], rpm=4000.0)
    tp.validate()
    return tp, stock


@pytest.mark.parametrize("sinir", [{"P_max": 0.3, "eta": 0.8}, {}], ids=["sinirli", "sinirsiz"])
def test_k10_geometri_degismez(sinir):
    mat = malzeme()
    limits = SpindleLimits(**sinir)
    tp, stock = _rastgele_program()
    ops = [tp]
    once = copy.deepcopy(tp.to_dict())
    plan = optimize_feed(ops, stock, mat, limits, cell=CELL)
    assert tp.to_dict() == once  # girdi değişmedi
    assert len(plan.ops) == 1
    yeni = plan.ops[0]
    assert yeni is not tp
    assert len(yeni.moves) == len(tp.moves)  # split=False: hareket sayısı aynı
    assert yeni.rpm == tp.rpm and yeni.start == tp.start and yeni.tool == tp.tool
    assert yeni.plane == tp.plane and yeni.feed_mode == tp.feed_mode and yeni.css == tp.css
    for a, b in zip(tp.moves, yeni.moves, strict=True):
        assert a.type == b.type
        assert a.end == b.end
        assert a.center == b.center
        if a.type is MoveType.RAPID:
            assert b.feed == a.feed
    assert any(a.feed != b.feed for a, b in zip(tp.moves, yeni.moves, strict=True))
    for ch in plan.changes:
        assert ch.F_old == tp.moves[ch.move].feed
        assert ch.F_new == yeni.moves[ch.move].feed
    # son z-haritası birebir aynı
    r0 = simulate(ops, stock, cell=CELL)
    r1 = simulate(plan.ops, stock, cell=CELL)
    assert np.array_equal(r0.zmap.z, r1.zmap.z)
    # süreler: verilen Machine ile toplam simülasyon süresi
    assert plan.t_before == pytest.approx(r0.total_time, rel=1e-12)
    assert plan.t_after == pytest.approx(r1.total_time, rel=1e-12)
    if all(ch.F_new >= ch.F_old for ch in plan.changes):
        assert plan.t_after <= plan.t_before * (1 + 1e-12)
    if limits.P_max is None:
        # sınırsız: c = min(c_ince ≥ 1, max_factor) ≥ 1 → ilerleme düşmez, süre uzamaz
        assert all(ch.F_new >= ch.F_old for ch in plan.changes)
        assert plan.t_after <= plan.t_before * (1 + 1e-12)
    else:
        assert any(ch.F_new < ch.F_old for ch in plan.changes)


def test_k10_ivmeli_makine_suresi():
    mat = malzeme()
    tp, ix = kanal_programi()
    m = Machine(accel=500.0, tool_change=2.0)
    plan = _plan([tp], mat, SpindleLimits(P_max=1.0, eta=1.0), machine=m)
    assert plan.t_before == pytest.approx(simulate([tp], STOCK, cell=CELL, machine=m).total_time, rel=1e-12)
    assert plan.t_after == pytest.approx(
        simulate(plan.ops, STOCK, cell=CELL, machine=m).total_time, rel=1e-12
    )
    assert plan.t_after > plan.t_before  # ilerleme düştü


# ------------------------------------------------------------------ K11 bölütleme


def _yol(moves, start=(0.0, 0.0, 0.0)) -> Toolpath:
    return Toolpath("b", parmak(), start, moves, rpm=3000.0)


def test_k11_dogru_bolutleme():
    tp = _yol([Move(MoveType.LINEAR, (10.0, 0.0, -2.0), feed=500.0)])
    yeni, es = split_moves([tp], 3.0)
    L = math.sqrt(104.0)
    m = math.ceil(L / 3.0)  # 4
    mv = yeni[0].moves
    assert len(mv) == m
    assert es == [(0, 0)] * m
    for i, x in enumerate(mv, start=1):
        assert x.type is MoveType.LINEAR
        assert x.feed == 500.0
        np.testing.assert_allclose(x.end, np.array([10.0, 0.0, -2.0]) * i / m, atol=1e-12)
    assert mv[-1].end == (10.0, 0.0, -2.0)
    assert yeni[0].length() == pytest.approx(L, rel=1e-12)
    for k in range(m):
        assert _yol([mv[k]], start=(0.0, 0.0, 0.0) if k == 0 else mv[k - 1].end).length() <= 3.0 + 1e-12


def test_k11_g0_bolunmez_ve_eslesme():
    tp = _yol(
        [
            Move(MoveType.RAPID, (20.0, 0.0, 0.0)),
            Move(MoveType.LINEAR, (20.0, 7.0, 0.0), feed=300.0),
            Move(MoveType.RAPID, (0.0, 0.0, 5.0)),
        ]
    )
    yeni, es = split_moves([tp], 2.0)
    mv = yeni[0].moves
    assert [x.type for x in mv] == [MoveType.RAPID] + [MoveType.LINEAR] * 4 + [MoveType.RAPID]
    assert es == [(0, 0)] + [(0, 1)] * 4 + [(0, 2)]
    assert mv[0].end == (20.0, 0.0, 0.0) and mv[-1].end == (0.0, 0.0, 5.0)
    assert yeni[0].length() == pytest.approx(tp.length(), rel=1e-12)
    assert tp.moves[1].end == (20.0, 7.0, 0.0) and len(tp.moves) == 3  # girdi değişmedi


def _yay_parcalari(tp: Toolpath, mv: list[Move]):
    p0 = tp.start
    for x in mv:
        yield p0, x
        p0 = x.end


@pytest.mark.parametrize(
    "tip,son,dz",
    [
        (MoveType.ARC_CCW, (0.0, 10.0), 0.0),  # çeyrek, düz
        (MoveType.ARC_CW, (0.0, -10.0), -3.0),  # çeyrek helis
        (MoveType.ARC_CW, (10.0, 0.0), -2.0),  # tam daire helis (başlangıç = bitiş XY)
    ],
)
def test_k11_yay_bolutleme(tip, son, dz):
    tp = _yol([Move(tip, (son[0], son[1], dz), feed=400.0, center=(0.0, 0.0))], start=(10.0, 0.0, 0.0))
    seg = 3.0
    yeni, es = split_moves([tp], seg)
    mv = yeni[0].moves
    L = tp.length()
    m = math.ceil(L / seg)
    assert len(mv) == m
    assert es == [(0, 0)] * m
    tam = son == (10.0, 0.0)
    dth = 2 * math.pi if tam else math.pi / 2
    s = -1.0 if tip is MoveType.ARC_CW else 1.0
    for i, (p0, x) in enumerate(_yay_parcalari(tp, mv), start=1):
        assert x.type is tip
        assert x.center == (0.0, 0.0)
        assert x.feed == 400.0
        th = s * dth * i / m
        np.testing.assert_allclose(x.end, [10 * math.cos(th), 10 * math.sin(th), dz * i / m], atol=1e-12)
        assert _yol([x], start=p0).length() <= seg + 1e-12
    np.testing.assert_allclose(mv[-1].end, tp.moves[0].end, atol=1e-12)
    assert yeni[0].length() == pytest.approx(L, rel=1e-12)
    yeni[0].validate()


def test_k11_varsayilan_seg_D_yarisi():
    tp = _yol([Move(MoveType.LINEAR, (12.0, 0.0, 0.0), feed=500.0)])
    yeni, _ = split_moves([tp])
    assert len(yeni[0].moves) == math.ceil(12.0 / (D / 2))  # seg = D/2 = 5 → 3


def test_k11_hacim_korunur():
    stock = Stock(0.0, 0.0, -10.0, 60.0, 40.0, 0.0)
    dogru = Toolpath(
        "d", parmak(), (5.0, 5.0, 5.0),
        [Move(MoveType.LINEAR, (5.0, 5.0, -2.0), feed=300.0),
         Move(MoveType.LINEAR, (50.0, 30.0, -3.0), feed=600.0),
         Move(MoveType.LINEAR, (50.0, 10.0, -1.0), feed=600.0)],
        rpm=3000.0,
    )  # fmt: skip
    yeni, _ = split_moves([dogru], 3.0)
    v0 = simulate([dogru], stock, cell=CELL).removed_volume
    v1 = simulate(yeni, stock, cell=CELL).removed_volume
    assert v1 == pytest.approx(v0, rel=1e-9)
    yay = Toolpath(
        "y", parmak(), (40.0, 20.0, 5.0),
        [Move(MoveType.LINEAR, (40.0, 20.0, -2.0), feed=300.0),
         Move(MoveType.ARC_CCW, (40.0, 20.0, -4.0), feed=600.0, center=(30.0, 20.0)),
         Move(MoveType.ARC_CW, (20.0, 20.0, -4.0), feed=600.0, center=(30.0, 20.0))],
        rpm=3000.0,
    )  # fmt: skip
    yeni, _ = split_moves([yay], 3.0)
    v0 = simulate([yay], stock, cell=CELL, arc_tol=1e-5).removed_volume
    v1 = simulate(yeni, stock, cell=CELL, arc_tol=1e-5).removed_volume
    assert v1 == pytest.approx(v0, rel=1e-3)


def _yarim_hava_kanal() -> Toolpath:
    # tek G1: x = −40'tan (takım stok dışında) x = 40'a; yolun yarısı havada
    moves = [Move(MoveType.RAPID, (-40.0, 0.0, -AP)), Move(MoveType.LINEAR, (40.0, 0.0, -AP), feed=F)]
    return Toolpath("yarim", parmak(), (-40.0, 0.0, 10.0), moves, rpm=3000.0)


def test_k11_split_false_tam_kavrama():
    mat = malzeme()
    tp = _yarim_hava_kanal()
    lim = SpindleLimits(P_max=1.0, eta=1.0)
    plan = optimize_feed([tp], STOCK, mat, lim, cell=CELL)  # varsayılan seg = D/2
    ld = yuk(plan.loads_before, 0, 1)  # bölütlerin en kötüsü = tam kanal
    assert ld.ae == pytest.approx(10.0, rel=REL_IZGARA)
    assert ld.P == pytest.approx(TABLO[10.0][2], rel=REL_IZGARA)
    # bütün hareketin ortalaması girişteki tam kavramayı gizler
    ort = yuk(milling_loads([tp], simulate([tp], STOCK, cell=CELL), mat), 0, 1)
    assert ort.P < 0.8 * ld.P
    ch = degisim(plan, 0, 1)
    asagi_yuvarlanmis(ch.F_new, F * (1.0 / ld.P) ** (1 / (1 - MC)), RES)
    assert ch.reason == "guc"
    assert len(plan.ops[0].moves) == 2
    assert plan.overloads_after == []


def test_k11_split_true():
    mat = malzeme()
    tp = _yarim_hava_kanal()
    lim = SpindleLimits(P_max=1.0, eta=1.0)
    plan = optimize_feed([tp], STOCK, mat, lim, cell=CELL, split=True)
    mv = plan.ops[0].moves
    assert mv[0].type is MoveType.RAPID and mv[0].end == (-40.0, 0.0, -AP)
    g1 = mv[1:]
    assert all(x.type is MoveType.LINEAR for x in g1)
    # uçlar özgün doğru üzerinde, x artan, son uç özgün bitiş
    xs = [x.end[0] for x in g1]
    assert xs == sorted(xs) and xs[-1] == 40.0
    assert all(x.end[1] == 0.0 and x.end[2] == -AP for x in g1)
    # ardışık eşit ilerlemeler birleşmiş
    assert all(a.feed != b.feed for a, b in zip(g1[:-1], g1[1:], strict=False))
    # hava bölütleri (takım ön ucu x ≤ 0: merkez ≤ −5) değişmez ve tek harekete birleşmiş
    assert g1[0].feed == F
    assert g1[0].end[0] == pytest.approx(-5.0, abs=1e-9)
    # tam kavramalı bölütler (merkez ≥ 5) güç sınırıyla ayrı ayarlanmış
    assert g1[-1].feed < F
    ld = yuk(plan.loads_before, 0, 1)
    asagi_yuvarlanmis(g1[-1].feed, F * (1.0 / ld.P) ** (1 / (1 - MC)), RES)
    assert g1[-1].end[0] == 40.0 and xs[-2] <= 5.0 + 1e-9
    # aynı malzeme kaldırılır
    v0 = simulate([tp], STOCK, cell=CELL).removed_volume
    v1 = simulate(plan.ops, STOCK, cell=CELL).removed_volume
    assert v1 == pytest.approx(v0, rel=1e-9)
    assert plan.overloads_after == []


# ------------------------------------------------------------------ K12 hava ilerlemesi


def test_k12_hava_ilerlemesi():
    mat = malzeme()
    tp, ix = kanal_programi()
    plan = _plan([tp], mat, air_feed=3000.0, feed_max=2500.0)
    ch = degisim(plan, 0, ix["hava_g1"])
    assert ch.F_new == pytest.approx(2500.0, abs=1e-9)
    assert ch.reason == "hava"
    assert degisim(plan, 0, ix["kanal"]).F_new == F
    for j, (a, b) in enumerate(zip(tp.moves, plan.ops[0].moves, strict=True)):
        if a.type is MoveType.RAPID:
            assert b.type is MoveType.RAPID and b.feed == a.feed and b.end == a.end, j
            assert all(c.move != j for c in plan.changes if c.F_new != c.F_old)


def test_k12_hava_ilerlemesi_sinirsiz():
    mat = malzeme()
    tp, ix = kanal_programi()
    plan = _plan([tp], mat, air_feed=3000.0)
    assert plan.ops[0].moves[ix["hava_g1"]].feed == pytest.approx(3000.0, abs=1e-9)


def test_k12_air_feed_yok():
    mat = malzeme()
    tp, ix = kanal_programi()
    plan = _plan([tp], mat, feed_max=2500.0)
    assert plan.ops[0].moves[ix["hava_g1"]].feed == F
    for a, b in zip(tp.moves, plan.ops[0].moves, strict=True):
        if a.type is MoveType.RAPID:
            assert b.feed == a.feed


# ------------------------------------------------------------------ K13 görünür atlama


def _delikli_program():
    tp, ix = kanal_programi()
    matkap = Tool(id=7, name="matkap", kind="matkap", D=6.0, flute_length=30.0, flutes=2)
    drill = DrillOp(
        name="delik", tool=matkap, rpm=1500.0, start=(80.0, 10.0, 10.0), holes=[(80.0, 10.0), (80.0, -10.0)],
        z=-8.0, r=2.0, feed=150.0,
    )  # fmt: skip
    return [tp, drill], ix, drill


def test_k13_delme_atlanir():
    mat = malzeme()
    ops, ix, drill = _delikli_program()
    res = simulate(ops, STOCK, cell=CELL)
    loads = milling_loads(ops, res, mat)
    assert len(loads) == len(res.steps)
    delme = [ld for ld, s in zip(loads, res.steps, strict=True) if s.op == 1]
    assert delme and all(ld.kind == "atlandi" for ld in delme)
    assert all(ld.move is None for ld in delme)
    for ld, s in zip(loads, res.steps, strict=True):
        if s.link:
            assert ld.kind == "atlandi" and ld.move is None
    assert any(s.removed > 0 for s in res.steps if s.op == 1)  # delme malzeme kaldırdı, yine de atlandı


def test_k13_plan_skipped():
    mat = malzeme()
    ops, ix, drill = _delikli_program()
    once = copy.deepcopy(drill)
    plan = _plan(ops, mat, SpindleLimits(P_max=1.0, eta=1.0))
    assert plan.skipped == [1]
    assert isinstance(plan.ops[1], DrillOp)
    assert plan.ops[1] == once
    assert drill == once
    assert all(c.op != 1 for c in plan.changes)
    assert degisim(plan, 0, ix["kanal"]).reason == "guc"
    yeni, _ = split_moves(ops, 3.0)
    assert yeni[1] == once


def test_k10_yay_turleri_korunur():
    mat = malzeme()
    # yaylı programda split=False yeni programda yay türleri ve merkezleri aynı (K10'un kısa hâli)
    tp, stock = _rastgele_program(seed=7)
    plan = optimize_feed([tp], stock, mat, SpindleLimits(), cell=CELL)
    for a, b in zip(tp.moves, plan.ops[0].moves, strict=True):
        if a.type in ARCS:
            assert b.type is a.type and b.center == a.center
