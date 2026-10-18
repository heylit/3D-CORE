"""
SPEC 29 §7 — İşlem planının simülasyonla doğrulanması: freze SPEC 05 (dexel, ikinci bağlamada ters
çevrilmiş harita), torna SPEC 22.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.model import CamError
from cam.plan import MillPlan
from cam.plan_turn import TurnPlan
from cam.profile import Line, Profile, Region
from cam.sim import Collision, Machine
from cam.sim.dexel import DexelMap
from cam.sim.lathe import simulate_lathe
from cam.sim.part import mesh_zmap, part_zmap
from cam.sim.radial import RadialMap, profile_rmap
from cam.sim.simulate import simulate
from cam.sim.zmap import ZMap
from geometry.part import Part


@dataclass(frozen=True)
class PlanCheck:
    ok: bool
    collisions: tuple[Collision, ...]
    removed_volume: float
    rest_volume: float
    gouge_volume: float
    expected_rest: float  # freze: Σ kose_artigi; torna: 0
    total_time: float  # s, bağlamaların toplamı


def verify_mill(plan: MillPlan, part: Part, cell: float = 0.5, machine: Machine | None = None) -> PlanCheck:
    """§7 freze: bağlama 1 dexel; bağlama 2'de ters çevrilmiş harita ve ters çevrilmiş parça ağı."""
    if not isinstance(plan, MillPlan):
        raise CamError(f"verify_mill: MillPlan bekleniyor ({type(plan).__name__})")
    stock = plan.setups[0].stock
    grid = ZMap.from_stock(stock, cell)
    collisions: list[Collision] = []
    gouge = 0.0
    total = 0.0
    dexel: DexelMap | None = None
    for i in range(len(plan.setups)):
        if i == 0:
            part_z = part_zmap(part, grid)
        else:
            V, T = part.mesh()
            V = np.asarray(V, dtype=float).copy()
            y_c, z_c = (stock.ymin + stock.ymax) / 2, (stock.zmin + stock.zmax) / 2
            V[:, 1] = 2 * y_c - V[:, 1]
            V[:, 2] = 2 * z_c - V[:, 2]
            part_z = mesh_zmap(V, T, grid)
            dexel = None if dexel is None else dexel.flipped()
        ops = plan.ops_for(i)
        if not ops:
            continue
        r = simulate(ops, stock, cell, machine, part_z=part_z, model="dexel", initial=dexel)
        collisions += r.collisions
        gouge += r.gouge_volume()
        total += r.total_time
        dexel = r.dexel
    V_son = stock.volume if dexel is None else dexel.volume()
    expected = sum(n.value for n in plan.notes if n.code == "kose_artigi")
    return PlanCheck(
        ok=not collisions,
        collisions=tuple(collisions),
        removed_volume=stock.volume - V_son,
        rest_volume=V_son - part.volume + gouge,
        gouge_volume=gouge,
        expected_rest=expected,
        total_time=total,
    )


def _section(plan: TurnPlan) -> Region:
    """§7 kesit: dış profil eksenle (varsa iç profille) uçlarında dik doğrularla kapatılır."""
    dis = plan.outer.finish.segments
    on, arka = dis[0].p0, dis[-1].p1
    if plan.inner is None:
        ic = [Line((arka[0], 0.0), (on[0], 0.0))] if abs(arka[0] - on[0]) > 1e-9 else []
    else:
        ic = [s.reversed() for s in reversed(plan.inner.finish.segments)]  # arka → ön
    segs = list(dis)
    for s in ic:
        _join(segs, s.p0)
        segs.append(s)
    if not ic:
        _join(segs, (arka[0], 0.0))
    _join(segs, on)
    return Region(Profile(segs, True))


def _join(segs: list, q) -> None:
    """Son parçanın ucundan q'ya doğru (sıfır boyda eklenmez)."""
    p = segs[-1].p1
    if float(np.hypot(*(np.asarray(q, dtype=float) - p))) > 1e-9:
        segs.append(Line(p, q))


def verify_turn(plan: TurnPlan, cell: float = 0.25, machine: Machine | None = None) -> PlanCheck:
    """§7 torna: SPEC 22 simulate_lathe, parça kesitin radyal haritası."""
    if not isinstance(plan, TurnPlan):
        raise CamError(f"verify_turn: TurnPlan bekleniyor ({type(plan).__name__})")
    setup = plan.setup
    grid = RadialMap.from_stock(setup.stock, cell, list(setup.fixtures))
    part = profile_rmap(_section(plan), grid)
    r = simulate_lathe([o.op for o in plan.ops], setup, cell, machine, part=part)
    return PlanCheck(
        ok=not r.collisions,
        collisions=tuple(r.collisions),
        removed_volume=r.removed_volume,
        rest_volume=r.rest_volume(),
        gouge_volume=r.gouge_volume(),
        expected_rest=0.0,
        total_time=r.total_time,
    )
