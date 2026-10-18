"""SPEC 29 — K12 uçtan uca freze: parça → plan_mill → verify_mill. OCCT gerektirir.

Testler yalnızca SPEC 29 metninden ve sabit arayüzlerden (geometry/part.py, geometry.features, cam.model)
yazıldı; cam/plan.py ve cam/plan_verify.py gövdeleri okunmadı. Takımlar Ek A (tests/cam/plan_ek_a.py).

Parça: 100×60×20 blok, K2 cebi (40×30, r = 5, [12, 20]), iç cep 16×12 keskin [8, 12], 2 adet Ø8 boydan.
Stok [−2, 102]×[−2, 62]×[−3, 22], bağlama elemanı yok.

Seçilen varsayılan (koordinatör onaylı, 2026-10-18): bu stokla SPEC 27, parçanın çevresinde 2 mm genişlikte
[0, 20] açık bölge tanır. Oraya yalnız Ø4 sığar ve 12 mm kesici boyu 22 − 0 = 22'ye yetmez →
`opens[0]` `kesici_boy_yetmez`. Çevre şeridi (V_şerit = (104·64 − 100·60)·20) bu yüzden kalan malzemeye
girer; kalan ve kaldırılan hacim beklentileri buna göre kurulur.
Izgara sınırı (§7): Σ P_i·Δ·H_i (cep çevreleri, delik çevreleri, parça dış çevresi; her biri kendi derinliği).
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

import build123d as bd  # noqa: E402

from cam.model import Stock  # noqa: E402
from cam.plan import MillPlan, plan_mill  # noqa: E402
from cam.plan_verify import PlanCheck, verify_mill  # noqa: E402
from geometry.features import block, hole, pocket  # noqa: E402
from geometry.part import Part  # noqa: E402
from tests.cam.plan_ek_a import MALZEME, freze_lib, kose_artigi  # noqa: E402

pytestmark = pytest.mark.occt

STOK = Stock(-2, -2, -3, 102, 62, 22)
DZ = 0.25


def parca() -> Part:
    p = pocket(block(100, 60, 20), 50, 30, 40, 30, 8, r=5)
    ic = bd.Pos(50, 30, 8) * bd.Box(16, 12, 4.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    solids = list((p.shape - ic).solids())
    assert len(solids) == 1
    p = Part(solids[0])
    return hole(hole(p, 10, 50, 8), 90, 10, 8)


def test_plan_mill_parca():
    part = parca()
    p = plan_mill(part, STOK, freze_lib(), MALZEME)
    assert isinstance(p, MillPlan)
    assert len(p.setups) == 2
    assert [(u.feature, u.code) for u in p.unplanned] == [("opens[0]", "kesici_boy_yetmez")]
    assert [(o.kind, o.tool_id, o.feature, o.setup) for o in p.ops if o.kind != "delik"] == [
        ("yuz_alma", 1, "faces[0]", 0),
        ("cep", 1, "pockets[0]", 0),
        ("cep_kalan", 2, "pockets[0]", 0),
        ("cep", 2, "pockets[1]", 0),
        ("cep_kalan", 3, "pockets[1]", 0),
        ("yuz_alma", 1, "alt_yuz", 1),
    ]
    (d,) = [o for o in p.ops if o.kind == "delik"]
    assert d.tool_id == 11 and d.setup == 0
    assert sorted(d.op.holes) == [(10.0, 50.0), (90.0, 10.0)]
    kose = [n for n in p.notes if n.code == "kose_artigi"]
    assert [n.feature for n in kose] == ["pockets[1]"]
    assert kose[0].value == pytest.approx(kose_artigi(3.0, 4, 4.0), rel=1e-9)
    (alt,) = [n for n in p.notes if n.code == "ikinci_baglama"]
    assert alt.value == pytest.approx(3.0)


@pytest.mark.slow
def test_uctan_uca():
    part = parca()
    p = plan_mill(part, STOK, freze_lib(), MALZEME)
    c = verify_mill(p, part, cell=DZ)
    assert isinstance(c, PlanCheck)
    assert c.ok and c.collisions == ()
    assert c.gouge_volume <= 1e-9
    beklenen_artik = kose_artigi(3.0, 4, 4.0)
    assert c.expected_rest == pytest.approx(beklenen_artik, rel=1e-9)
    assert c.total_time > 0

    V_serit = (104 * 64 - 100 * 60) * 20.0
    P_cep = 2 * (40 + 30) - (8 - 2 * math.pi) * 5  # yuvarlak köşeli dikdörtgen çevresi
    izgara = DZ * (P_cep * 8 + 2 * (16 + 12) * 4 + 2 * math.pi * 8 * 23 + 2 * (100 + 60) * 20)
    assert abs(c.rest_volume - (beklenen_artik + V_serit)) <= izgara
    V_parca = part.volume
    beklenen_kaldirilan = STOK.volume - V_parca - beklenen_artik - V_serit
    assert abs(c.removed_volume - beklenen_kaldirilan) <= izgara
