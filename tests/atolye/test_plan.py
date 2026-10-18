"""SPEC 38 K10 — SPEC 29 `MillPlan` → iş föyü uyarlayıcısı (`from_mill_plan`).

SPEC 29 (`cam.plan`) birleşene kadar atlanır. Plan, SPEC 29 K8 gibi yüz alma + keskin köşeli cep (SPEC 29 K3,
kalan malzeme ve `kose_artigi` notu) + delikler (Ø8 boydan, stok altı 0 → `delik_tasma_kisildi` notu; Ø5
kütüphanede yok → `takim_yok`) ile `plan_mill_features`'tan kurulur. Beklenenler planın kendisinden okunur:
uyarlayıcı planı değiştirmeden föye taşımalı.
Testler yalnız SPEC 38 ve SPEC 29 metinlerinden yazıldı; uygulama kodu okunmadı.
"""

from __future__ import annotations

import numpy as np
import pytest

plan_mod = pytest.importorskip("cam.plan")

from atolye import from_mill_plan  # noqa: E402
from cam.features import FaceFeature, Features, HoleFeature, PocketFeature  # noqa: E402
from cam.model import CuttingData, Stock, Tool, ToolHolder, ToolKind, ToolLibrary  # noqa: E402
from cam.profile import Profile, Region  # noqa: E402
from cam.sim import Machine  # noqa: E402
from geometry.drawing.dimensions import format_value  # noqa: E402
from geometry.part import Hole  # noqa: E402

H = ToolHolder("BT30-ER", 60, ((0, 15), (40, 20)))


def _lib() -> ToolLibrary:
    """SPEC 29 Ek A freze takımları (+ tutucu ve taşma: föyde ofsetler hesaplanabilsin)."""

    def f(id, ad, kind, D, fl, z, cd):
        return Tool(
            id, ad, kind, D=D, flute_length=fl, flutes=z, stickout=fl + 10, holder=H, cutting={"al": cd}
        )

    return ToolLibrary(
        [
            f(1, "freze16", ToolKind.FLAT, 16, 30, 3, CuttingData(300, fz=0.08, ap=4, ae=6)),
            f(2, "freze10", ToolKind.FLAT, 10, 25, 3, CuttingData(250, fz=0.05, ap=3, ae=4)),
            f(3, "freze6", ToolKind.FLAT, 6, 18, 3, CuttingData(200, fz=0.04, ap=2, ae=2.5)),
            f(4, "freze4", ToolKind.FLAT, 4, 12, 2, CuttingData(150, fz=0.03, ap=1, ae=1.5)),
            f(5, "freze3-veri-yok", ToolKind.FLAT, 3, 8, 2, CuttingData(120, fz=0.02)),
            f(11, "matkap8", ToolKind.DRILL, 8, 40, 2, CuttingData(80, fz=0.1)),
            f(12, "matkap6.6", ToolKind.DRILL, 6.6, 35, 2, CuttingData(80, fz=0.08)),
            f(13, "matkap6.8", ToolKind.DRILL, 6.8, 35, 2, CuttingData(80, fz=0.08)),
            f(14, "matkap4", ToolKind.DRILL, 4, 25, 2, CuttingData(70, fz=0.05)),
        ]
    )


def _plan():
    stock = Stock(-2, -2, 0, 102, 62, 22)
    E = Profile.rectangle(0, 0, 100, 60)
    asagi = np.array([0.0, 0.0, -1.0])
    features = Features(
        faces=(FaceFeature(z=20, depth=2, boundary=E),),
        pockets=(
            PocketFeature(Region(Profile.rectangle(20, 20, 16, 12)), z_top=12, z_bottom=8, r_corner=0.0),
        ),
        opens=(),
        holes=(
            HoleFeature(Hole(np.array([80.0, 30.0, 20.0]), asagi, 8.0, 20.0, True), "kayit"),
            HoleFeature(Hole(np.array([60.0, 45.0, 20.0]), asagi, 5.0, 5.0, False), "kayit"),
        ),
    )
    return plan_mod.plan_mill_features(features, 0.0, stock, _lib(), "al")


def test_from_mill_plan():
    plan = _plan()
    lib = _lib()
    job = from_mill_plan(plan, lib, "Plan işi", machine=Machine(tool_change=5), date="2026-10-18")
    assert job.title == "Plan işi" and job.material == plan.material == "al"
    assert job.date == "2026-10-18"
    assert len(job.setups) == len(plan.setups)
    for i, s in enumerate(job.setups):
        assert s.setup == plan.setups[i]
        assert len(s.ops) == len(plan.ops_for(i))
        assert [o.name for o in s.ops] == [po.name for po in plan.ops if po.setup == i]

    beklenen = [f"{u.feature}: {u.code} — {u.detail}" for u in plan.unplanned] + [
        f"{n.feature}: {n.code} = {format_value(n.value)} — {n.detail}" for n in plan.notes
    ]
    assert beklenen, "plan uyarı / not üretmeli (takim_yok, kose_artigi)"
    # Plan uyarıları ve notları sırasıyla, aynı biçimde föyün uyarılarında
    w = list(job.warnings)
    konum = [w.index(b) for b in beklenen]
    assert konum == sorted(konum)
    assert any(u.code == "takim_yok" for u in plan.unplanned)

    if len(plan.setups) == 1:
        assert job.setups[0].tool_changes == plan.tool_changes()
    assert sum(s.tool_changes for s in job.setups) == plan.tool_changes()
