"""SPEC 57 §6 — plan_auto_turn: torna ters bağlama (K10). OCCT gerektirmez.

Testler yalnızca SPEC 57 metninden ve iskeletteki imzalardan yazıldı; gövdeler okunmadı.
Takımlar SPEC 29 Ek A (tests/cam/plan_ek_a.py), malzeme "al", rpm_max = 3000. Profil (z, x)
ön → arka, açık.

K10 mili, z ∈ [0, 100]: ön uç Ø16 (z 85…100, boy 15), orta Ø30 (z 25…85, boy 60), arka uç Ø20
(z 0…25, boy 25). Stok Ø32, z ∈ [−2, 102]; ayna kavrama boyu g_t = 20 → bağlama 1'de ayna
z ∈ [−2, 18]'i tutar, aynaya g_t + clearance'tan yakın arka bölüm işlenemez → ters bağlama gerekir.
Boyu ≥ 20 silindirlerden en büyük çaplısı Ø30 (Ø20 da 25 boyunda ama daha küçük) → ikinci kavrama
yüzü Ø30.
Kavrama yüzeyi yok: bütün kademeler 15 mm boyunda (< 20).
Uzun stok: z ∈ [−25, 102] → 127 ≥ 100 + 20 + kesme kanalı payı → tek bağlama.
"""

from __future__ import annotations

import pytest

from cam.model import CamError, CylinderStock
from cam.plan2.plan import plan_auto_turn
from cam.plan_turn import TurnOptions, TurnPlan
from cam.plan_verify import PlanCheck, verify_turn
from tests.cam.plan_ek_a import MALZEME, cizgi, torna_lib

SECENEK = TurnOptions(rpm_max=3000)
MIL = cizgi((100, 0), (100, 8), (85, 8), (85, 15), (25, 15), (25, 10), (0, 10), (0, 0))
KISA_KADEMELER = cizgi(
    (100, 0),
    (100, 8),
    (85, 8),
    (85, 15),
    (70, 15),
    (70, 12),
    (55, 12),
    (55, 14),
    (40, 14),
    (40, 11),
    (25, 11),
    (25, 13),
    (10, 13),
    (10, 10),
    (0, 10),
    (0, 0),
)
STOK = CylinderStock(D=32, zmin=-2, zmax=102)
UZUN = CylinderStock(D=32, zmin=-25, zmax=102)


def _kodlar(plans) -> list[str]:
    return [u.code for p in plans for u in p.unplanned]


def test_ters_baglama_iki_plan():
    plans = plan_auto_turn(MIL, torna_lib(), MALZEME, SECENEK, stock=STOK, grip=20.0)
    assert isinstance(plans, tuple) and len(plans) == 2
    assert all(isinstance(p, TurnPlan) for p in plans)
    assert all(p.ops for p in plans)
    assert "kavrama_yuzeyi_yok" not in _kodlar(plans)


@pytest.mark.slow
def test_ters_baglama_dogrulama():
    plans = plan_auto_turn(MIL, torna_lib(), MALZEME, SECENEK, stock=STOK, grip=20.0)
    assert len(plans) == 2
    for p in plans:
        c = verify_turn(p)
        assert isinstance(c, PlanCheck)
        assert c.ok and c.collisions == ()
        assert c.gouge_volume <= 1e-9


def test_ikinci_baglama_ters_cevrilmis():
    """İkinci bağlamanın finiş profili ters çevrilmiş parçanın kalan ucudur: Ø20 var, Ø16 yok."""
    plans = plan_auto_turn(MIL, torna_lib(), MALZEME, SECENEK, stock=STOK, grip=20.0)
    ikinci = plans[1].outer.finish
    xs = [p[1] for s in ikinci.segments for p in (s.p0, s.p1)]
    assert max(xs) <= 15.0 + 1e-9
    assert any(abs(x - 10.0) < 1e-9 for x in xs)  # Ø20 ucu
    assert not any(abs(x - 8.0) < 1e-9 for x in xs)  # Ø16 ucu birinci bağlamada kaldı


def test_kavrama_yuzeyi_yok():
    try:
        plans = plan_auto_turn(KISA_KADEMELER, torna_lib(), MALZEME, SECENEK, stock=STOK, grip=20.0)
    except CamError as e:
        assert "kavrama_yuzeyi_yok" in str(e)
    else:
        assert "kavrama_yuzeyi_yok" in _kodlar(plans)
    with pytest.raises(CamError):
        plan_auto_turn(
            KISA_KADEMELER,
            torna_lib(),
            MALZEME,
            TurnOptions(rpm_max=3000, strict=True),
            stock=STOK,
            grip=20.0,
        )


def test_kisa_kavrama_boyuyla_kademe_yeter():
    # g_t = 12: 15 mm'lik kademeler artık kavrama yüzü olabilir → ters bağlama kurulur
    plans = plan_auto_turn(KISA_KADEMELER, torna_lib(), MALZEME, SECENEK, stock=STOK, grip=12.0)
    assert len(plans) == 2
    assert "kavrama_yuzeyi_yok" not in _kodlar(plans)


def test_uzun_cubuk_tek_baglama():
    plans = plan_auto_turn(MIL, torna_lib(), MALZEME, SECENEK, stock=UZUN, grip=20.0)
    assert len(plans) == 1
    assert plans[0].ops


def test_determinizm():
    a = plan_auto_turn(MIL, torna_lib(), MALZEME, SECENEK, stock=STOK, grip=20.0)
    b = plan_auto_turn(MIL, torna_lib(), MALZEME, SECENEK, stock=STOK, grip=20.0)
    assert [p.summary() for p in a] == [p.summary() for p in b]
