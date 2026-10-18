"""SPEC 72 — cam/sim/cevrim.py testleri: torna, hareket dışı süreler, kalibrasyon, CycleTime (K9–K11, K13).

Testler yalnız specs/72-cevrim-suresi.md metninden ve iskeletin arayüzünden (imzalar, docstring'ler,
durum/72-cevrim-suresi.md ekleri: Dwell(P), TimeProfile.spindle_overlap) yazıldı;
fonksiyon gövdeleri okunmadı.

Varsayımlar (koordinatöre bildirildi):
- Kesme / hızlı kalemleri her işlemin toolpath_time(op, prof.dynamics) değerinin toplamıdır; DrillOp, SPEC 04
  hole_moves açılımıyla (G81, G98: dönüş = başlangıç z) aynı süreyi verir.
- Takım değişimi sayımı: liste girdisinde ardışık farklı tool_id + ilk takım; MillPlan'da
  plan.tool_changes().
- İş mili: devir geçişleri |Δn|/ṅ; takım değişimiyle örtüşen geçiş "max" kipinde takim_degisimi'nin
  üstüne yalnız aşan kısmı (max(0, t_iş_mili − t_tc)) is_mili'ye ekler, "toplam" kipinde tamamını.
  M5 duruşunun sayılıp sayılmadığı bu testlerde sonucu etkilemez (yalnız farklar ve sınırlar sınanır).
- Palet ve program sabiti program başına bir kez; bağlama her Setup için setup_time
  (liste girdisi = 1 bağlama).
- calibrate: çiftler (t_tahmin, t_ölçülen); ölçüm < 3 uyarısı warnings.warn (UserWarning) ile.
- K9 referansı (kodlayıcı): Machine(rapid = dyn.v_max, accel = a), tüm a_max = a, j = None, tol = 0;
  tam eşitlik eksene paralel doğrular ve ZX yaylarında.
"""

from __future__ import annotations

import json
import math
import warnings

import numpy as np
import pytest

from cam.gcode.cycles import DrillOp, hole_moves
from cam.model import CamError, FeedMode, Move, MoveType, Setup, Stock, Tool, ToolKind, Toolpath, Wcs
from cam.plan import MillPlan, PlannedOp
from cam.sim.cevrim import KINDS, CycleTime, Dwell, TimeProfile, calibrate, cycle_time
from cam.sim.lathe_time import lathe_move_time
from cam.sim.sure import Dynamics, toolpath_time
from cam.sim.timing import Machine
from tests.cam.lsimref import G0 as LG0
from tests.cam.lsimref import G1 as LG1
from tests.cam.lsimref import lpath, turn_tool

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
REL = 1e-12


def dyn(
    a: float = 1000.0, j: float | None = 1e4, tol: float = 0.01, v=(30000.0, 30000.0, 20000.0)
) -> Dynamics:
    return Dynamics(v_max=tuple(v), a_max=(a, a, a), j_max=None if j is None else (j, j, j), tol=tol)


def profile(**kw) -> TimeProfile:
    """Uydurma tezgâh zaman profili (ölçülmedi)."""
    args = dict(machine="UYDURMA-DMU", dynamics=dyn(), tool_change=5.0, spindle_accel=1000.0)
    args.update(kw)
    return TimeProfile(**args)


def freze(id: int, D: float = 10.0) -> Tool:
    return Tool(id=id, name=f"freze{id}", kind=ToolKind.FLAT, D=D, flute_length=30.0)


def mill_path(tool_id: int, rpm: float, dx: float = 0.0) -> Toolpath:
    """Uydurma kısa freze yolu (G0 – G1 dikdörtgen – G0)."""
    z = -1.0
    mv = [
        Move(G0, (dx, 0.0, 1.0)),
        Move(G1, (dx, 0.0, z), feed=300.0),
        Move(G1, (dx + 40.0, 0.0, z), feed=1500.0),
        Move(G1, (dx + 40.0, 20.0, z), feed=1500.0),
        Move(G1, (dx, 20.0, z), feed=1500.0),
        Move(G1, (dx, 0.0, z), feed=1500.0),
        Move(G0, (dx, 0.0, 10.0)),
    ]
    tp = Toolpath(f"T{tool_id}", freze(tool_id), (dx, 0.0, 10.0), mv, rpm=rpm)
    tp.validate()
    return tp


def path_time(tp: Toolpath, d: Dynamics) -> float:
    return toolpath_time(tp, d).total


def kinds_sum(ct: CycleTime) -> float:
    bk = ct.by_kind()
    return sum(bk[k] for k in KINDS)


# ================================================================ K9: torna


def turn_paths():
    """G95 ve G96 uydurma torna yolları: Z boyunca tornalama, X boyunca alın, ZX yayı,
    eksene paralel G0'lar."""
    tool = turn_tool()
    arc = Move(MoveType.ARC_CCW, (24.0, 0.0, -34.0), 0.15, center=(24.0, -30.0))  # R = 4, merkez (x, z)
    moves = [
        LG0(20.0, 2.0),
        LG1(20.0, -30.0, 0.2),
        arc,
        LG1(30.0, -34.0, 0.1),
        LG0(30.0, 2.0),
        LG0(20.0, 2.0),
        LG1(20.0, 0.0, 0.15),
        LG1(2.0, 0.0, 0.15),  # alın (X boyunca)
        LG0(2.0, 5.0),
    ]
    g95 = lpath(tool, (40.0, 5.0), [LG0(40.0, 2.0), LG0(20.0, 2.0)] + moves[1:], rpm=1200.0)
    g96 = lpath(tool, (40.0, 5.0), [LG0(40.0, 2.0), LG0(20.0, 2.0)] + moves[1:], rpm=3000.0, css=150.0)
    return {"G95": g95, "G96": g96}


def spec22_total(tp: Toolpath, machine: Machine) -> float:
    p0 = np.array(tp.start)
    t = 0.0
    for m in tp.moves:
        p1 = np.array(m.end)
        t += lathe_move_time(p0, p1, m, tp, machine)
        p0 = p1
    return t


@pytest.mark.parametrize("name", ["G95", "G96"])
@pytest.mark.parametrize("a", [300.0, 2000.0])
def test_lathe_reduces_to_spec22(name, a):
    """K9: j = None, tol = 0: G95 / G96 torna yolunun süresi SPEC 22 lathe_move_time toplamına eşit
    (Machine(rapid = v_max, accel = a)), göreli 1e-12; cycle_time'ın kesme + hızlı kalemleri de aynı."""
    v = (8000.0, 8000.0, 10000.0)
    tp = turn_paths()[name]
    exp = spec22_total(tp, Machine(rapid=v, accel=a))
    d = dyn(a=a, j=None, tol=0.0, v=v)
    assert toolpath_time(tp, d).total == pytest.approx(exp, rel=REL)
    ct = cycle_time([tp], profile(dynamics=d, tool_change=0.0, spindle_accel=None))
    bk = ct.by_kind()
    assert bk["kesme"] + bk["hizli"] == pytest.approx(exp, rel=REL)


@pytest.mark.parametrize("name", ["G95", "G96"])
def test_lathe_finite_jerk_slower(name):
    """K9: j sonlu iken süre sonsuz sarsıntılıdan büyük."""
    v = (8000.0, 8000.0, 10000.0)
    tp = turn_paths()[name]
    t_inf = toolpath_time(tp, dyn(a=1000.0, j=None, tol=0.0, v=v)).total
    t_j = toolpath_time(tp, dyn(a=1000.0, j=2000.0, tol=0.0, v=v)).total
    assert t_j > t_inf


def test_lathe_taper_not_slower_than_spec22():
    """K9 (kodlayıcı notu): konik / çapraz doğruda eksen bazlı a_yol ≥ a → süre ≤ SPEC 22 referansı."""
    tp = lpath(
        turn_tool(), (20.0, 2.0), [LG1(20.0, 0.0, 0.2), LG1(30.0, -20.0, 0.2), LG0(30.0, 5.0)], rpm=1500.0
    )
    v = (8000.0, 8000.0, 10000.0)
    assert (
        toolpath_time(tp, dyn(a=800.0, j=None, tol=0.0, v=v)).total
        <= spec22_total(tp, Machine(rapid=v, accel=800.0)) + 1e-12
    )


def test_lathe_g94_supported():
    """Teori 7: G94 (mm/dk) torna yolu da kabul (SPEC 22: G94 = SPEC 05 kuralı)."""
    tp = lpath(turn_tool(), (20.0, 2.0), [LG1(20.0, -20.0, 300.0)], rpm=1500.0, feed_mode=FeedMode.PER_MIN)
    v = (8000.0, 8000.0, 10000.0)
    exp = spec22_total(tp, Machine(rapid=v, accel=800.0))
    assert toolpath_time(tp, dyn(a=800.0, j=None, tol=0.0, v=v)).total == pytest.approx(exp, rel=REL)


# ================================================================ K10: hareket dışı süreler


def two_tool_ops():
    return [mill_path(1, 6000.0), Dwell(2.0), mill_path(2, 9000.0, dx=60.0)]


def test_tool_changes_and_dwell():
    """K10: iki takımlı liste: takim_degisimi = 2·t_tc (ilk takım dahil); G4 P2 → bekleme = 2;
    kesme + hızlı = Σ toolpath_time; by_kind() toplamı total_raw (1e-12); total = k·total_raw."""
    prof = profile(tool_change=5.0, spindle_accel=None, k=1.25)
    ops = two_tool_ops()
    ct = cycle_time(ops, prof)
    bk = ct.by_kind()
    assert set(bk) == set(KINDS)
    assert bk["takim_degisimi"] == pytest.approx(10.0, rel=REL)
    assert bk["bekleme"] == pytest.approx(2.0, rel=REL)
    assert bk["is_mili"] == 0.0  # spindle_accel = None → anlık
    exp_motion = path_time(ops[0], prof.dynamics) + path_time(ops[2], prof.dynamics)
    assert bk["kesme"] + bk["hizli"] == pytest.approx(exp_motion, rel=1e-12)
    assert kinds_sum(ct) == pytest.approx(ct.total_raw, rel=1e-12)
    assert ct.total == pytest.approx(1.25 * ct.total_raw, rel=1e-12)
    assert ct.k == 1.25


def test_same_tool_twice_one_change():
    """K10: aynı takım ardışık iki işlemde → tek takım değişimi (29 tool_changes() sayımı)."""
    prof = profile(tool_change=4.0, spindle_accel=None)
    ct = cycle_time([mill_path(1, 6000.0), mill_path(1, 6000.0, dx=60.0)], prof)
    assert ct.by_kind()["takim_degisimi"] == pytest.approx(4.0, rel=REL)


def test_spindle_overlap_max_vs_total():
    """K10 / Karar 4: iş mili geçişleri |Δn|/ṅ: 0 → 6000 (6 s) ve 6000 → 9000 (3 s),
    ṅ = 1000 dev/dk/s, t_tc = 5. "max" kipinde takım değişimiyle örtüşen kısım bir kez sayılır:
    "toplam" − "max" = min(5, 6) + min(5, 3) = 8;
    takım değişiminin kendisi iki kipte de 2·t_tc."""
    ops = two_tool_ops()
    mx = cycle_time(ops, profile(spindle_overlap="max")).by_kind()
    tp = cycle_time(ops, profile(spindle_overlap="toplam")).by_kind()
    assert mx["takim_degisimi"] == pytest.approx(10.0, rel=REL)
    assert tp["takim_degisimi"] == pytest.approx(10.0, rel=REL)
    assert tp["is_mili"] - mx["is_mili"] == pytest.approx(8.0, rel=1e-12)
    assert mx["is_mili"] >= 1.0 - 1e-12  # 0 → 6000 geçişinin t_tc'yi aşan 1 s'si


def test_spindle_time_scales_with_accel():
    """K10: t = |Δn|/ṅ: t_tc = 0 iken ṅ iki katına çıkınca is_mili yarıya iner."""
    ops = two_tool_ops()
    a = cycle_time(ops, profile(tool_change=0.0, spindle_accel=1000.0)).by_kind()["is_mili"]
    b = cycle_time(ops, profile(tool_change=0.0, spindle_accel=2000.0)).by_kind()["is_mili"]
    assert a > 0
    assert b == pytest.approx(a / 2, rel=1e-12)
    assert a >= 9.0 - 1e-12  # en az 6 + 3 s geçiş


def setup(name: str) -> Setup:
    return Setup(name=name, wcs=Wcs(), stock=Stock(0.0, 0.0, -20.0, 100.0, 50.0, 0.0))


def two_setup_plan() -> MillPlan:
    """Uydurma iki bağlamalı plan: bağlama 0'da T1, T2; bağlama 1'de T2 → tool_changes() = 3."""
    from cam.cutting import SpindleFeed

    def op(i: int, s: int, tid: int, rpm: float) -> PlannedOp:
        return PlannedOp(
            name=f"{i:02d}-cep-T{tid}",
            kind="cep",
            setup=s,
            feature="uydurma",
            tool_id=tid,
            op=mill_path(tid, rpm, dx=10.0 * i),
            spindle=SpindleFeed(n=int(rpm), F=1500.0, Vc=100.0, f=0.05),
            a_p=1.0,
            stepover=5.0,
        )

    ops = (op(1, 0, 1, 6000.0), op(2, 0, 2, 8000.0), op(3, 1, 2, 8000.0))
    return MillPlan(
        material="uydurma", features=None, setups=(setup("A"), setup("B")), ops=ops, unplanned=(), notes=()
    )


def test_mill_plan_setups_and_tool_changes():
    """K10: iki bağlama → baglama = 2·setup_time; takim_degisimi = tool_changes()·t_tc;
    palet, sabit profilden; OpTime.setup bağlama indisi; by_kind() toplamı total_raw."""
    plan = two_setup_plan()
    assert plan.tool_changes() == 3
    prof = profile(tool_change=6.0, spindle_accel=None, pallet=12.0, program_fixed=20.0)
    ct = cycle_time(plan, prof, setup_time=30.0)
    bk = ct.by_kind()
    assert bk["baglama"] == pytest.approx(60.0, rel=REL)
    assert bk["takim_degisimi"] == pytest.approx(3 * 6.0, rel=REL)
    assert bk["palet"] == pytest.approx(12.0, rel=REL)
    assert bk["sabit"] == pytest.approx(20.0, rel=REL)
    assert [o.setup for o in ct.ops] == [0, 0, 1]
    assert [o.tool_id for o in ct.ops] == [1, 2, 2]
    assert kinds_sum(ct) == pytest.approx(ct.total_raw, rel=1e-12)
    assert ct.total == pytest.approx(ct.total_raw, rel=1e-12)  # k = 1 varsayılan


def test_list_input_is_one_setup():
    """Varsayım: liste girdisi tek bağlama → baglama = setup_time."""
    ct = cycle_time([mill_path(1, 6000.0)], profile(spindle_accel=None), setup_time=45.0)
    assert ct.by_kind()["baglama"] == pytest.approx(45.0, rel=REL)


def test_drill_op_matches_hole_moves():
    """Teori 6: DrillOp (G81) hole_moves (SPEC 04) açılımıyla aynı kesme + hızlı süresi."""
    tool = freze(3, D=6.0)
    op = DrillOp(
        "delik",
        tool,
        rpm=2000.0,
        start=(0.0, 0.0, 10.0),
        holes=[(10.0, 5.0), (30.0, 5.0)],
        z=-8.0,
        r=2.0,
        feed=120.0,
    )
    op.validate()
    p = op.start
    moves: list[Move] = []
    for x, y in op.holes:
        mv = hole_moves("G81", p, x, y, op.z, op.r, op.start[2], op.feed)
        moves += mv
        p = mv[-1].end
    tp = Toolpath("delik", tool, op.start, moves, rpm=op.rpm)
    tp.validate()
    prof = profile(spindle_accel=None)
    ct = cycle_time([op], prof)
    bk = ct.by_kind()
    assert bk["kesme"] + bk["hizli"] == pytest.approx(path_time(tp, prof.dynamics), rel=1e-12)


def test_optime_total_and_to_dict_json():
    """Arayüz: OpTime.total kalemlerin toplamı; CycleTime.to_dict() JSON'a uygun (json.dumps geçer)."""
    ct = cycle_time(two_tool_ops(), profile())
    for o in ct.ops:
        assert o.total == pytest.approx(o.cut + o.rapid + o.tool_change + o.spindle + o.dwell, rel=1e-15)
        assert all(v >= 0 for v in (o.cut, o.rapid, o.tool_change, o.spindle, o.dwell))
    text = json.dumps(ct.to_dict())
    assert isinstance(json.loads(text), dict)


def test_cycle_times_never_nan_or_negative():
    """K13: hiçbir kalem nan veya negatif değil."""
    ct = cycle_time(two_tool_ops(), profile(pallet=3.0, program_fixed=7.0), setup_time=10.0)
    for k, v in ct.by_kind().items():
        assert math.isfinite(v) and v >= 0, k
    assert math.isfinite(ct.total) and ct.total > 0


# ================================================================ TimeProfile doğrulama


@pytest.mark.parametrize(
    "kw",
    [
        dict(tool_change=-1.0),
        dict(tool_change=float("nan")),
        dict(turret_index=-0.5),
        dict(spindle_accel=0.0),
        dict(spindle_accel=-100.0),
        dict(pallet=-1.0),
        dict(program_fixed=float("inf")),
        dict(k=0.0),
        dict(k=-1.1),
        dict(spindle_overlap="ikisi"),
        dict(machine=""),
    ],
)
def test_time_profile_bad_values_raise(kw):
    """Arayüz: negatif / sonlu olmayan süre, k ≤ 0, bilinmeyen spindle_overlap, boş ad → CamError."""
    with pytest.raises(CamError):
        profile(**kw)


def test_time_profile_bad_dynamics_type_raises():
    with pytest.raises(CamError):
        profile(dynamics={"v_max": (1.0, 1.0, 1.0)})


def test_time_profile_defaults():
    """Arayüz: k = 1, verified = False, spindle_overlap = "max" varsayılan (Karar 2, 4)."""
    p = profile()
    assert p.k == 1.0 and p.verified is False and p.spindle_overlap == "max"


def test_dwell_bad_value_raises():
    """K13: negatif / sonlu olmayan bekleme → CamError (kurulumda veya kullanımda)."""
    for P in (-1.0, float("nan")):
        with pytest.raises(CamError):
            cycle_time([mill_path(1, 6000.0), Dwell(P)], profile())


# ================================================================ K11: kalibrasyon


def test_calibrate_exact():
    """K11: tahmin (100, 200, 300), ölçüm (110, 220, 330) → k = Σ t_ölç·t_tah / Σ t_tah² = 1.1, RMS hata 0."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 3 ölçümde uyarı yok
        k, err = calibrate([(100.0, 110.0), (200.0, 220.0), (300.0, 330.0)])
    assert k == pytest.approx(1.1, rel=1e-12)
    assert err == pytest.approx(0.0, abs=1e-12)


def test_calibrate_least_squares_through_origin():
    """Teori 9: k = Σ t_ölç·t_tah / Σ t_tah² (orijinden geçen doğru); dağınık ölçümde hata > 0."""
    pairs = [(100.0, 105.0), (200.0, 190.0), (400.0, 430.0)]
    exp = sum(t * m for t, m in pairs) / sum(t * t for t, _ in pairs)
    k, err = calibrate(pairs)
    assert k == pytest.approx(exp, rel=1e-12)
    assert err > 0 and math.isfinite(err)


def test_calibrate_empty_raises():
    """K11: boş liste → CamError."""
    with pytest.raises(CamError):
        calibrate([])


def test_calibrate_two_measurements_warns():
    """K11: ölçüm sayısı < 3 → uyarı notu (varsayım: warnings.warn, UserWarning); k yine hesaplanır."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        k, _ = calibrate([(100.0, 110.0), (200.0, 220.0)])
    assert any(issubclass(x.category, UserWarning) for x in w)
    assert k == pytest.approx(1.1, rel=1e-12)


@pytest.mark.parametrize(
    "pairs", [[(-1.0, 10.0), (1.0, 1.0), (2.0, 2.0)], [(1.0, float("nan")), (2.0, 2.0), (3.0, 3.0)]]
)
def test_calibrate_bad_pairs_raise(pairs):
    """K13: negatif / sonlu olmayan süre → CamError (sessiz nan yok)."""
    with pytest.raises(CamError):
        calibrate(pairs)
