"""SPEC 29 — cam/plan_turn.py ve verify_turn testleri (K13, K14, K15 torna). OCCT gerektirmez.

Testler yalnızca SPEC 29 metninden ve bağımlı modüllerin sabit imzalarından (cam.lathe_ops, cam.turn_features,
cam.gcode.write_lathe) yazıldı; cam/plan_turn.py ve cam/plan_verify.py gövdeleri okunmadı.
Takımlar Ek A (tests/cam/plan_ek_a.py), malzeme "al", rpm_max = 3000.
Kesme: TurnCut(feed = fn, rpm = 3000, css = Vc, a_p = cd.ap, clearance = 1.0).

SPEC 20 ön koşulları için seçilen varsayılan (koordinatör onaylı, 2026-10-18): `rough()` profilin stok ön
yüzünden başlamasını ve ham yüzeye çıkmasını ister. Bu yüzden alın planlandıysa sonraki SPEC 20 çağrıları alnı
alınmış stokla (`CylinderStock(D, zmin, z_face, d)`) yapılır; kaba profili `tf.rough`, sonundan ham yüzeye
(dışta D/2, içte d/2) dik doğruyla uzatılır. Finiş ve kanal işlemlerinin kesme hareketleri stoktan
bağımsızdır;
bunlar yalnız G1/G2/G3 hareketleriyle karşılaştırılır.

K14 (§7): kesit profil ucunda kapandığından aynaya bağlı arka bölge (z ∈ [zmin, z_son]) kalan malzemeye girer:
V_arka = π (D/2)² (z_son − zmin). Üst sınır = V_arka + Pappus burun artıkları + ızgara sınırı.
"""

from __future__ import annotations

import math

import pytest

from cam.gcode import write_lathe
from cam.lathe_ops import TurnCut, face, finish, groove, rough
from cam.model import CamError, CylinderStock, FeedMode, Plane, Stock, Toolpath
from cam.plan import PlannedOp
from cam.plan_turn import TurnOptions, TurnPlan, plan_turn
from cam.plan_verify import PlanCheck, verify_turn
from cam.profile import Line, Profile
from cam.turn_features import turn_features
from tests.cam.plan_ek_a import MALZEME, cizgi, kesme_hareketleri, torna_lib, yol

RPM = 3000
STOK = CylinderStock(D=32, zmin=-10, zmax=62)
BORU = CylinderStock(D=32, zmin=-10, zmax=62, d=10)
K10 = [(60, 0), (60, 10), (40, 10), (40, 8), (34, 8), (34, 10), (20, 10), (20, 15), (0, 15)]
IC = [(60, 7), (40, 7), (40, 5)]  # iç profil: Ø14 → omuz → Ø10 (boru iç çapı)
V_KANAL = [(60, 0), (60, 10), (40, 10), (37, 8), (34, 10), (20, 10), (20, 15), (0, 15)]
DAR_KANAL = [(60, 0), (60, 10), (40, 10), (40, 8), (38, 8), (38, 10), (20, 10), (20, 15), (0, 15)]


def kesme(T) -> TurnCut:
    cd = T.cutting[MALZEME]
    return TurnCut(feed=cd.fn, rpm=RPM, css=cd.Vc, a_p=cd.ap, clearance=1.0)


def alinmis(stock: CylinderStock, z_face: float) -> CylinderStock:
    return CylinderStock(D=stock.D, zmin=stock.zmin, zmax=z_face, d=stock.d)


def uzat(p: Profile, x: float) -> Profile:
    """Profili sonundan x yarıçapına dik doğruyla uzatır (gerekmiyorsa aynen)."""
    e = p.end
    if abs(e[1] - x) < 1e-9:
        return p
    return Profile([*p.segments, Line(e, (e[0], x))], False)


def tplan(outer=K10, stock=STOK, inner=None, lib=None, material=MALZEME, **opt) -> TurnPlan:
    return plan_turn(
        cizgi(*outer),
        stock,
        lib or torna_lib(),
        material,
        TurnOptions(rpm_max=RPM, **opt),
        inner=None if inner is None else cizgi(*inner),
    )


def ozet(p) -> list[tuple[str, int, str]]:
    return [(o.kind, o.tool_id, o.feature) for o in p.ops]


def kodlar(p) -> list[tuple[str, str]]:
    return [(u.feature, u.code) for u in p.unplanned]


# ---------------------------------------------------------------- K13


def test_torna_plani():
    lib = torna_lib()
    T21, T22, T23 = lib.get(21), lib.get(22), lib.get(23)
    p = tplan(lib=lib)
    assert isinstance(p, TurnPlan)
    assert p.material == MALZEME
    assert p.inner is None
    assert p.setup.name == "torna-1" and p.setup.stock.to_dict() == STOK.to_dict()
    assert ozet(p) == [
        ("alin", 21, "alin"),
        ("dis_kaba", 21, "dis"),
        ("dis_finis", 22, "dis"),
        ("kanal", 23, "grooves[0]"),
    ]
    assert p.unplanned == ()
    assert [o.name for o in p.ops] == ["01-alin-T21", "02-dis_kaba-T21", "03-dis_finis-T22", "04-kanal-T23"]
    assert all(isinstance(o, PlannedOp) and o.setup == 0 for o in p.ops)

    tf = turn_features(cizgi(*K10), STOK, "dis")
    assert p.outer.z_face == pytest.approx(60.0)
    sf = alinmis(STOK, 60.0)

    alin, kaba, fin, kanal = (o.op for o in p.ops)
    assert yol(alin) == yol(face(STOK, T21, kesme(T21), 60.0))
    beklenen_kaba = rough(uzat(tf.rough, STOK.D / 2), sf, T21, kesme(T21), allowance=0.2, side="dis")
    assert kesme_hareketleri(kaba) == kesme_hareketleri(beklenen_kaba)
    assert kesme_hareketleri(fin) == kesme_hareketleri(finish(tf.rough, sf, T22, kesme(T22), side="dis"))
    beklenen_kanal = groove(sf, T23, kesme(T23), 34.0, 40.0, 10.0, 8.0, side="dis")
    assert kesme_hareketleri(kanal) == kesme_hareketleri(beklenen_kanal)

    for o in p.ops:
        T = lib.get(o.tool_id)
        cd = T.cutting[MALZEME]
        tp = o.op
        assert isinstance(tp, Toolpath)
        assert tp.plane is Plane.ZX and tp.feed_mode is FeedMode.PER_REV
        assert tp.css == cd.Vc and tp.rpm == RPM
        assert all(m.feed == cd.fn for m in tp.moves if m.feed is not None)
        assert o.spindle.n == RPM and o.spindle.Vc == cd.Vc and o.spindle.f == cd.fn
    assert p.ops[1].a_p == 2.0

    # G-code: SPEC 21 write_lathe birebir
    g = p.gcode(spindle="M3", tool_change=(50.0, 80.0))
    assert g == write_lathe([o.op for o in p.ops], "M3", (50.0, 80.0), program_no=1)
    assert p.gcode("M3", (50.0, 80.0), program_no=7) == write_lathe(
        [o.op for o in p.ops], "M3", (50.0, 80.0), program_no=7
    )
    s = p.summary()
    assert [d["name"] for d in s] == [o.name for o in p.ops]
    assert {"name", "kind", "setup", "feature", "tool_id", "n", "F", "a_p", "stepover"} <= set(s[0])


def test_torna_ic_profil():
    lib = torna_lib()
    T24 = lib.get(24)

    # dolu stok + iç profil → on_delik_yok, dış işlemler yine planlanır
    p = tplan(inner=IC, lib=lib)
    assert ("ic", "on_delik_yok") in kodlar(p)
    assert [o.kind for o in p.ops] == ["alin", "dis_kaba", "dis_finis", "kanal"]

    # boru stok (d = 10) → ic_kaba, ic_finis (T24)
    q = tplan(inner=IC, stock=BORU, lib=lib)
    assert q.inner is not None
    assert ozet(q) == [
        ("alin", 21, "alin"),
        ("dis_kaba", 21, "dis"),
        ("ic_kaba", 24, "ic"),
        ("ic_finis", 24, "ic"),
        ("dis_finis", 22, "dis"),
        ("kanal", 23, "grooves[0]"),
    ]
    assert q.unplanned == ()
    tfi = turn_features(cizgi(*IC), BORU, "ic")
    sf = alinmis(BORU, 60.0)
    ic_kaba, ic_fin = q.ops[2].op, q.ops[3].op
    beklenen = rough(uzat(tfi.rough, BORU.d / 2), sf, T24, kesme(T24), allowance=0.2, side="ic")
    assert kesme_hareketleri(ic_kaba) == kesme_hareketleri(beklenen)
    assert kesme_hareketleri(ic_fin) == kesme_hareketleri(finish(tfi.rough, sf, T24, kesme(T24), side="ic"))


def test_torna_girinti_ve_dar_kanal():
    # V kanal → genel_girinti; finiş köprülenmiş zarfla, girintiye dalmaz
    p = tplan(outer=V_KANAL)
    assert kodlar(p) == [("recesses[0]", "genel_girinti")]
    assert [o.kind for o in p.ops] == ["alin", "dis_kaba", "dis_finis"]
    tf = turn_features(cizgi(*V_KANAL), STOK, "dis")
    T22 = torna_lib().get(22)
    beklenen = finish(tf.rough, alinmis(STOK, 60.0), T22, kesme(T22), side="dis")
    assert kesme_hareketleri(p.ops[2].op) == kesme_hareketleri(beklenen)

    # 2 mm kanal, 3 mm takım → takim_yok
    q = tplan(outer=DAR_KANAL)
    assert kodlar(q) == [("grooves[0]", "takim_yok")]
    assert [o.kind for o in q.ops] == ["alin", "dis_kaba", "dis_finis"]


# ---------------------------------------------------------------- K14


def _pappus(x_k: float, r: float) -> float:
    return 2 * math.pi * (x_k + r) * r * r * (1 - math.pi / 4)


def _hacim_k10() -> float:
    """K10 kesitinin dönel hacmi: π Σ x² Δz."""
    return math.pi * (10**2 * 20 + 8**2 * 6 + 10**2 * 14 + 15**2 * 20)


@pytest.mark.slow
def test_torna_dogrulama():
    p = tplan()
    c = verify_turn(p, cell=0.1)
    assert isinstance(c, PlanCheck)
    assert c.ok and c.collisions == ()
    assert c.gouge_volume <= 1e-9
    assert c.expected_rest == 0.0
    assert c.total_time > 0

    R = STOK.D / 2
    dz = 0.1
    V_arka = math.pi * R * R * (0.0 - STOK.zmin)
    # son takımın iç köşeleri: dış finiş (r = 0.4) omuz (20, 10); kanal (r = 0.2) tabanın iki köşesi (x = 8)
    burun = _pappus(10.0, 0.4) + 2 * _pappus(8.0, 0.2)
    # ızgara: dönel yüzey alanı ≤ 2π R · (profil + kapatma doğruları boyu), çarpı Δ
    L = cizgi(*K10).length + 15.0 + 60.0
    izgara = 2 * math.pi * R * L * dz
    assert c.rest_volume <= V_arka + burun + izgara
    # arka bölgeden en çok finişin ham yüzeye çıkış payı (≤ 1 mm boy) alınabilir
    assert c.rest_volume >= V_arka - math.pi * (R * R - 15.0**2) * 1.0 - izgara
    V_stok = STOK.volume
    assert c.removed_volume == pytest.approx(V_stok - _hacim_k10() - c.rest_volume, abs=izgara)


# ---------------------------------------------------------------- K15


@pytest.mark.parametrize(
    "kw",
    [
        {"material": ""},
        {"material": None},
        {"lib": "kutuphane"},
        {"stock": Stock(-16, -16, -10, 16, 16, 62)},
        {"rpm_max": 0.0},
        {"rpm_max": -1.0},
        {"rpm_max": math.nan},
        {"finish_allowance": -0.1},
        {"finish_allowance": math.inf},
        {"clearance": -1.0},
    ],
)
def test_hatalar(kw):
    kw = dict(kw)
    with pytest.raises(CamError):
        opt = TurnOptions(
            rpm_max=kw.pop("rpm_max", RPM),
            finish_allowance=kw.pop("finish_allowance", 0.2),
            clearance=kw.pop("clearance", 1.0),
        )
        plan_turn(
            cizgi(*K10),
            kw.pop("stock", STOK),
            kw.pop("lib", torna_lib()),
            kw.pop("material", MALZEME),
            opt,
        )


def test_hatalar_kutuphane_ve_strict():
    lib = torna_lib()
    lib.tools.append(torna_lib().get(21))  # yinelenen id
    with pytest.raises(CamError):
        tplan(lib=lib)
    with pytest.raises(CamError) as e:
        tplan(outer=V_KANAL, strict=True)
    assert "recesses[0]" in str(e.value) and "genel_girinti" in str(e.value)
