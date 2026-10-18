"""SPEC 46 H14 — otomatik işlem planı (SPEC 29). K14.

`plan_mill(flans, …)` ve `plan_turn(mil_profili, …)`: planlanmayan özellik yok, `verify_*` geçer; plan
işlemleri elle zincirin H4 / H5 / H9 / H10 denetimlerinden aynen geçer (elle zincir regresyon tabanı olarak
kalır, SPEC 46 §3).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL, read, write
from cam.model import MoveType, Tool, ToolKind, ToolLibrary
from cam.sim import ZMap, part_zmap, simulate
from tests.reference.gcode_check import compare, expected, safety
from tests.reference.gcode_ref import RefMachine
from tests.uctan_uca.conftest import (
    CUBUK_D,
    CUBUK_ZMAX,
    D_KOSE,
    D_MERKEZ,
    MALZEME,
    N_MAX,
    STOK_UST,
    H,
    V_flans,
    V_mil,
    halka,
    mil_profili,
)

plan = halka("29", "cam.plan", "plan_mill")
plan_turn = halka("29", "cam.plan_turn", "plan_turn", "TurnOptions")
verify = halka("29", "cam.plan_verify", "verify_mill", "verify_turn")
tsim = halka("22", "cam.sim", "simulate_lathe", "RadialMap", "part_rmap")
tprof = halka("28", "cam.turn_profile", "turn_profile")
lathe = halka("21", "cam.gcode.lathe", "write_lathe", "read_lathe")

CELL = 0.5
TC = (50.0, 100.0)
KESME = {MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW}
DIALECTS = [pytest.param(GRBL, id="GRBL"), pytest.param(FANUC, id="Fanuc")]


# --- Freze ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def plan_kutuphanesi(kutuphane):
    """§1 kütüphanesi + Ø20 matkap. Flanşın Ø20 deliği delik kaydı taşır; SPEC 29 kayıtlı deliği yalnız
    matkapla planlar (yoksa `takim_yok`), elle zincirdeki cep yolunu seçmez."""
    t3 = next(t for t in kutuphane.tools if t.id == 3)
    t4 = Tool(
        4,
        "matkap20",
        ToolKind.DRILL,
        D=D_MERKEZ,
        flute_length=30.0,
        flutes=2,
        stickout=50.0,
        holder=t3.holder,
        cutting=t3.cutting,
    )
    return ToolLibrary([*kutuphane.tools, t4])


@pytest.fixture(scope="module")
def freze_plani(flans, flans_stok, plan_kutuphanesi):
    return plan.plan_mill(flans, flans_stok, plan_kutuphanesi, MALZEME)


@pytest.fixture(scope="module")
def plan_ops(freze_plani):
    assert len(freze_plani.setups) == 1
    return freze_plani.ops_for(0)


pytestmark = pytest.mark.occt


def test_k14_freze_planlanmayan_yok(freze_plani):
    assert freze_plani.unplanned == ()
    assert freze_plani.ops


def test_k14_freze_dogrulama(freze_plani, flans):
    c = verify.verify_mill(freze_plani, flans, cell=CELL)
    assert c.ok, c
    assert c.collisions == ()


def test_k14_freze_sim_k4(plan_ops, flans_stok, flans):
    g = ZMap.from_stock(flans_stok, CELL)
    zP = np.asarray(part_zmap(flans, g, tol=0.01), dtype=float)
    r = simulate(plan_ops, flans_stok, cell=CELL, part_z=zP)
    assert r.collisions == []
    dV0 = flans_stok.volume - V_flans()
    duvar = (math.pi * D_MERKEZ + 4 * math.pi * D_KOSE) * H
    assert abs(r.removed_volume - dV0) <= 2 * CELL * duvar


@pytest.mark.parametrize("d", DIALECTS)
def test_k14_freze_gcode_k5(d, freze_plani, plan_ops, flans_stok, plan_kutuphanesi):
    setup = freze_plani.setups[0]
    metin = write(plan_ops, d, setup=setup)
    tr = RefMachine(tool_change=d.tool_change, peck_clearance=d.peck_clearance).run(metin)
    errs = compare(expected(plan_ops, d.peck_clearance), tr.moves)
    assert not errs, "\n".join(errs[:20])
    ihlal = safety(tr, STOK_UST, require_tlo=d is FANUC, require_wcs=d is FANUC)
    assert not ihlal, "\n".join(m for _, m in ihlal[:20])
    okunan = read(metin, {t.id: t for t in plan_kutuphanesi.tools}, d)
    a = simulate(plan_ops, flans_stok, cell=CELL)
    b = simulate(okunan, flans_stok, cell=CELL)
    assert np.abs(b.zmap.z - a.zmap.z).max() <= 10.0 ** (-d.decimals)


# --- Torna ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def torna_plani(mil, mil_stok, kutuphane):
    # SPEC 29 §6 profili alından (eksenden) başlayan dış profil ister: SPEC 28 `turn_profile(mil).outer`
    secenek = plan_turn.TurnOptions(rpm_max=N_MAX)
    dis = tprof.turn_profile(mil).outer
    return plan_turn.plan_turn(dis, mil_stok, kutuphane, MALZEME, secenek)


@pytest.fixture(scope="module")
def tplan_ops(torna_plani):
    return [o.op for o in torna_plani.ops]


def test_k14_torna_planlanmayan_yok(torna_plani):
    assert torna_plani.unplanned == ()
    assert torna_plani.ops


def test_k14_torna_dogrulama(torna_plani):
    c = verify.verify_turn(torna_plani)
    assert c.ok, c
    assert c.collisions == ()


def test_k14_torna_gcode_k9(tplan_ops, kutuphane):
    tools = {t.id: t for t in kutuphane.tools if t.id in {tp.tool.id for tp in tplan_ops}}
    okunan = lathe.read_lathe(lathe.write_lathe(tplan_ops, "M3", TC), tools, spindle="M3")

    def kesmeler(ops):
        return [(m.type, np.asarray(m.end, dtype=float)) for tp in ops for m in tp.moves if m.type in KESME]

    a, b = kesmeler(okunan), kesmeler(tplan_ops)
    assert [t for t, _ in a] == [t for t, _ in b]
    assert max(float(np.abs(p - q).max()) for (_, p), (_, q) in zip(a, b, strict=True)) <= 1e-3


def test_k14_torna_sim_k10(tplan_ops, mil_stok, mil):
    dz = 0.5
    g = tsim.RadialMap.from_stock(mil_stok, dz)
    r = tsim.simulate_lathe(tplan_ops, mil_stok, cell=dz, part=tsim.part_rmap(mil, g))
    assert r.collisions == []
    R = CUBUK_D / 2
    dV0 = math.pi * R**2 * CUBUK_ZMAX - V_mil()
    P = R + mil_profili().length
    assert abs(r.removed_volume - dV0) <= P * dz * 2 * math.pi * R
