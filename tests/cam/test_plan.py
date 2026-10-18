"""SPEC 29 — cam/plan.py testleri (K1–K11, K15 freze). OCCT gerektirmez: özellikler elle kurulur.

Testler yalnızca SPEC 29 metninden ve bağımlı modüllerin sabit imzalarından (cam.ops2d, cam.offset,
cam.cutting, cam.setups, cam.gcode, cam.tool_length) yazıldı; cam/plan.py gövdesi okunmadı.
Beklenen işlemler SPEC'in §3–5'te adını verdiği çağrılarla doğrudan kurulur ve plandakiyle karşılaştırılır
(takım yolunun adı hariç). Takımlar Ek A (tests/cam/plan_ek_a.py), malzeme "al".

El hesapları:
- Kesme: sf = milling(T, "al", n_max); a_p = min(ap, flute_length); s = min(ae, D/2);
  Cut(z_t, z_b, a_p, sf.F, 0.3·sf.F, sf.n, clearance_height(setup), 1.0, s).
- Sığma: offset(Ω, D/2) ≠ []. 40×30 cepte Ø16 sığar; 16×12 cepte Ø16 sığmaz, Ø10 sığar.
- Köşe artığı: n·(r² − R_c²)·(1 − π/4)·H (φ = 90°).
- Delik: z_dip = z_e − depth − b, b = min(1, z_e − depth − z_stok_alt); r = z_e + 1;
  depth/D > 3 → G83, q = D.
- En yakın komşu (K6): (10,10) → (15,45) [35.4] → (80,12) [72.9] → (90,50) [39.3].
- İkinci bağlama (K9): z_c = (−3 + 22)/2 = 9.5 → z_bottom = 2·9.5 − 0 = 19.
"""

from __future__ import annotations

import copy
import math
import random
import re

import pytest

from cam import ops2d
from cam.cutting import milling
from cam.features import FaceFeature, Features, HoleFeature, OpenFeature, PocketFeature
from cam.gcode import FANUC, GRBL, DrillOp, write
from cam.model import CamError, CylinderStock, Setup, Stock, ToolLibrary, Toolpath, Wcs
from cam.offset import offset
from cam.ops2d import Cut
from cam.plan import (
    MillOptions,
    MillPlan,
    PlannedOp,
    PlanNote,
    Unplanned,
    plan_mill_features,
)
from cam.profile import Profile, Region
from cam.setups import clearance_height
from cam.tool_length import length_offsets
from geometry.part import Hole
from tests.cam.plan_ek_a import (
    MALZEME,
    dikdortgen,
    freze_lib,
    kose_artigi,
    yol,
    yuvarlak_dikdortgen,
)

REL = 1e-9
ASAGI = (0.0, 0.0, -1.0)
STOK = Stock(-2, -2, 0, 102, 62, 22)
E_PARCA = Profile.rectangle(0, 0, 100, 60)


# ---------------------------------------------------------------- yardımcılar


def ozellik(faces=(), pockets=(), opens=(), holes=()) -> Features:
    return Features(faces=tuple(faces), pockets=tuple(pockets), opens=tuple(opens), holes=tuple(holes))


def yuz(z: float = 20.0, stock: Stock = STOK) -> FaceFeature:
    return FaceFeature(z=z, depth=stock.zmax - z, boundary=E_PARCA)


def cep_k2() -> PocketFeature:
    """40×30 cep, köşe yarıçapı 5, [12, 20], merkez (50, 30)."""
    return PocketFeature(Region(yuvarlak_dikdortgen(50, 30, 40, 30, 5)), 20.0, 12.0, 5.0)


def cep_keskin() -> PocketFeature:
    """16×12 keskin köşeli cep, [8, 12], merkez (50, 30)."""
    return PocketFeature(Region(dikdortgen(50, 30, 16, 12)), 12.0, 8.0, 0.0)


def acik_basamak() -> OpenFeature:
    """Zarf 100×60, ada [0, 100]×[10, 60], [15, 20] (K5)."""
    return OpenFeature(E_PARCA, (Profile.rectangle(0, 10, 100, 50),), 20.0, 15.0)


def delik(x, y, d, depth, through, z=20.0, axis=ASAGI, **kw) -> HoleFeature:
    return HoleFeature(Hole(origin=(x, y, z), axis=axis, d=d, depth=depth, through=through, **kw), "kayit")


def plan(features, stock=STOK, lib=None, part_zmin=0.0, material=MALZEME, **kw) -> MillPlan:
    return plan_mill_features(features, part_zmin, stock, lib or freze_lib(), material, **kw)


def kurulum(stock=STOK, fixtures=()) -> Setup:
    return Setup("baglama-1", Wcs("G54"), stock, list(fixtures))


def kesme(T, z_top, z_bottom, setup, stepover=True, n_max=None) -> Cut:
    sf = milling(T, MALZEME, n_max)
    cd = T.cutting[MALZEME]
    s = min(cd.ae, T.D / 2) if stepover else None
    return Cut(
        z_top=z_top,
        z_bottom=z_bottom,
        a_p=min(cd.ap, T.flute_length),
        feed=sf.F,
        plunge_feed=0.3 * sf.F,
        rpm=sf.n,
        z_safe=clearance_height(setup),
        clearance=1.0,
        stepover=s,
    )


def T(id: int, lib: ToolLibrary | None = None):
    return (lib or freze_lib()).get(id)


def ozet(p: MillPlan) -> list[tuple[str, int, str]]:
    return [(o.kind, o.tool_id, o.feature) for o in p.ops]


def kodlar(p: MillPlan) -> list[tuple[str, str]]:
    return [(u.feature, u.code) for u in p.unplanned]


def notlar(p: MillPlan) -> list[tuple[str, str]]:
    return [(n.feature, n.code) for n in p.notes]


def ayni_yol(op: PlannedOp, beklenen: Toolpath) -> None:
    assert isinstance(op.op, Toolpath)
    assert yol(op.op) == yol(beklenen)


# ---------------------------------------------------------------- K1


def test_yuz_alma():
    lib = freze_lib()
    p = plan(ozellik(faces=[yuz()]), lib=lib)
    assert isinstance(p, MillPlan)
    assert p.material == MALZEME
    assert len(p.setups) == 1
    assert p.setups[0].name == "baglama-1" and p.setups[0].wcs.code == "G54"
    assert p.unplanned == () and p.notes == ()
    assert len(p.ops) == 1
    op = p.ops[0]
    assert (op.kind, op.tool_id, op.feature, op.setup) == ("yuz_alma", 1, "faces[0]", 0)
    assert op.name == "01-yuz_alma-T1"
    T1 = lib.get(1)
    sf = milling(T1, MALZEME)
    assert op.spindle == sf
    assert op.a_p == 4.0
    assert op.stepover == 6.0  # min(ae = 6, D/2 = 8)
    c = kesme(T1, 22.0, 20.0, kurulum())
    assert c.plunge_feed == pytest.approx(0.3 * sf.F, rel=REL)
    ayni_yol(op, ops2d.face(STOK, T1, c))
    assert op.op.rpm == sf.n

    # n_max sınırı
    p5 = plan(ozellik(faces=[yuz()]), lib=lib, options=MillOptions(n_max=5000))
    op5 = p5.ops[0]
    assert op5.op.rpm == 5000 and op5.spindle.n == 5000
    assert op5.spindle == milling(T1, MALZEME, 5000)
    ayni_yol(op5, ops2d.face(STOK, T1, kesme(T1, 22.0, 20.0, kurulum(), n_max=5000)))

    # özet
    s = p.summary()
    assert s == [
        {
            "name": "01-yuz_alma-T1",
            "kind": "yuz_alma",
            "setup": 0,
            "feature": "faces[0]",
            "tool_id": 1,
            "n": sf.n,
            "F": sf.F,
            "a_p": 4.0,
            "stepover": 6.0,
        }
    ]
    assert p.ops_for(0) == [op.op]


# ---------------------------------------------------------------- K2


def test_cep_kalan_malzeme():
    lib = freze_lib()
    f = cep_k2()
    T1, T2 = lib.get(1), lib.get(2)
    p = plan(ozellik(pockets=[f]), lib=lib)
    assert ozet(p) == [("cep", 1, "pockets[0]"), ("cep_kalan", 2, "pockets[0]")]
    assert p.unplanned == () and p.notes == ()
    ayni_yol(p.ops[0], ops2d.pocket(f.region, T1, kesme(T1, 20.0, 12.0, kurulum())))
    # D₂ = 10 ≥ D₁/2 = 8 → dış halkada kontur, side = "ic", stepover yok
    beklenen = ops2d.contour(f.region.outer, T2, kesme(T2, 20.0, 12.0, kurulum(), stepover=False), "ic")
    ayni_yol(p.ops[1], beklenen)
    assert p.ops[1].stepover is None
    assert p.ops[1].a_p == 3.0
    assert [o.name for o in p.ops] == ["01-cep-T1", "02-cep_kalan-T2"]

    # rest = False → tek cep T2
    q = plan(ozellik(pockets=[f]), lib=lib, options=MillOptions(rest=False))
    assert ozet(q) == [("cep", 2, "pockets[0]")]
    ayni_yol(q.ops[0], ops2d.pocket(f.region, T2, kesme(T2, 20.0, 12.0, kurulum())))
    assert q.notes == ()


# ---------------------------------------------------------------- K3


def test_keskin_kose():
    lib = freze_lib()
    f = cep_keskin()
    T2, T3, T4 = lib.get(2), lib.get(3), lib.get(4)

    # stok üstü 22: T4'ün kesici boyu 12 < 22 − 8 = 14 → kalan takım T3 (Ø6 ≥ 10/2 → kontur)
    p = plan(ozellik(pockets=[f]), lib=lib)
    assert ozet(p) == [("cep", 2, "pockets[0]"), ("cep_kalan", 3, "pockets[0]")]
    ayni_yol(p.ops[0], ops2d.pocket(f.region, T2, kesme(T2, 12.0, 8.0, kurulum())))
    beklenen = ops2d.contour(f.region.outer, T3, kesme(T3, 12.0, 8.0, kurulum(), stepover=False), "ic")
    ayni_yol(p.ops[1], beklenen)
    assert notlar(p) == [("pockets[0]", "kose_artigi")]
    assert p.notes[0].value == pytest.approx(4 * 3**2 * (1 - math.pi / 4) * 4, rel=REL)
    assert p.notes[0].value == pytest.approx(kose_artigi(3.0, 4, 4.0), rel=REL)

    # stok üstü 20: 20 − 8 = 12 ≤ 12 → T4 (Ø4 < 10/2 → tam cep)
    s20 = Stock(-2, -2, 0, 102, 62, 20)
    q = plan(ozellik(pockets=[f]), stock=s20, lib=lib)
    assert ozet(q) == [("cep", 2, "pockets[0]"), ("cep_kalan", 4, "pockets[0]")]
    ayni_yol(q.ops[0], ops2d.pocket(f.region, T2, kesme(T2, 12.0, 8.0, kurulum(s20))))
    ayni_yol(q.ops[1], ops2d.pocket(f.region, T4, kesme(T4, 12.0, 8.0, kurulum(s20))))
    assert q.ops[1].stepover == 1.5 and q.ops[1].a_p == 1.0
    assert notlar(q) == [("pockets[0]", "kose_artigi")]
    assert q.notes[0].value == pytest.approx(4 * 2**2 * (1 - math.pi / 4) * 4, rel=REL)


# ---------------------------------------------------------------- K4


def test_suzgecler():
    f = cep_k2()

    # malzeme için kesme verisi olan takım yok
    p = plan(ozellik(pockets=[f]), material="celik")
    assert p.ops == () and kodlar(p) == [("pockets[0]", "kesme_verisi_yok")]

    # ap / ae'siz takım (T5) aday değil: yalnız T5 → kesme_verisi_yok
    lib5 = ToolLibrary([T(5)])
    p = plan(ozellik(pockets=[f]), lib=lib5)
    assert p.ops == () and kodlar(p) == [("pockets[0]", "kesme_verisi_yok")]

    # 3 mm genişlik: hiçbir aday sığmaz (Ø4 en küçük aday)
    dar = PocketFeature(Region(dikdortgen(50, 30, 3, 20)), 20.0, 15.0, 0.0)
    p = plan(ozellik(pockets=[dar]))
    assert p.ops == () and kodlar(p) == [("pockets[0]", "takim_sigmiyor")]

    # 3.5 mm: T5 (Ø3) sığardı ama aday değil → yine takim_sigmiyor, T5 hiç kullanılmaz
    dar35 = PocketFeature(Region(dikdortgen(50, 30, 3.5, 20)), 20.0, 15.0, 0.0)
    p = plan(ozellik(pockets=[dar35]))
    assert p.ops == () and kodlar(p) == [("pockets[0]", "takim_sigmiyor")]

    # stok üstünden 40 mm derin: en uzun kesici boy 30 → kesici_boy_yetmez
    s50 = Stock(-2, -2, 0, 102, 62, 50)
    derin = PocketFeature(Region(yuvarlak_dikdortgen(50, 30, 40, 30, 5)), 20.0, 10.0, 5.0)
    p = plan(ozellik(pockets=[derin]), stock=s50)
    assert p.ops == () and kodlar(p) == [("pockets[0]", "kesici_boy_yetmez")]

    # süzgeç sırası: dar ve derin → önce sığma süzgeci boşalır
    dar_derin = PocketFeature(Region(dikdortgen(50, 30, 3, 20)), 20.0, 10.0, 0.0)
    p = plan(ozellik(pockets=[dar_derin]), stock=s50)
    assert kodlar(p) == [("pockets[0]", "takim_sigmiyor")]

    for o in plan(ozellik(pockets=[f, cep_keskin()])).ops:
        assert o.tool_id != 5

    # strict → CamError, mesajda adres ve kod
    with pytest.raises(CamError, match=re.escape("pockets[0]")) as e:
        plan(ozellik(pockets=[dar]), options=MillOptions(strict=True))
    assert "takim_sigmiyor" in str(e.value)


# ---------------------------------------------------------------- K5


def test_acik_bolge():
    lib = freze_lib()
    f = acik_basamak()
    T1 = lib.get(1)
    p = plan(ozellik(opens=[f]), lib=lib)
    assert ozet(p) == [("acik_bolge", 1, "opens[0]")]
    assert p.unplanned == ()
    buyuk = offset(Region(E_PARCA), -(8.0 + 1.0))
    assert len(buyuk) == 1
    dis = buyuk[0].outer
    # zarfın r_T + 1 = 9 dışa ofseti: köşe yarıçapı 9 olan yuvarlak köşeli dikdörtgen
    lo, hi = dis.bbox()
    assert lo[0] == pytest.approx(-9) and lo[1] == pytest.approx(-9)
    assert hi[0] == pytest.approx(109) and hi[1] == pytest.approx(69)
    assert dis.area == pytest.approx(118 * 78 - (4 - math.pi) * 81, rel=1e-9)
    omega = Region(dis, holes=list(f.islands))
    ayni_yol(p.ops[0], ops2d.pocket(omega, T1, kesme(T1, 20.0, 15.0, kurulum())))


# ---------------------------------------------------------------- K6


def _delikler(p: MillPlan) -> list[PlannedOp]:
    return [o for o in p.ops if o.kind in ("delik", "lamba")]


def test_delikler():
    lib = freze_lib()
    s3 = Stock(-2, -2, -3, 102, 62, 22)

    # Ø8 boydan, stok altı −3 → b = 1, depth/D = 2.5 → G81
    p = plan(ozellik(holes=[delik(30, 30, 8, 20, True)]), stock=s3, lib=lib)
    (op,) = _delikler(p)
    T11 = lib.get(11)
    sf = milling(T11, MALZEME)
    assert (op.kind, op.tool_id, op.feature, op.setup) == ("delik", 11, "holes[0]", 0)
    d = op.op
    assert isinstance(d, DrillOp)
    assert d.kind == "G81" and d.retract == "G98"
    assert d.z == pytest.approx(-1.0) and d.r == pytest.approx(21.0)
    assert d.holes == [(30.0, 30.0)]
    assert d.rpm == sf.n and d.feed == pytest.approx(sf.F, rel=REL)
    assert d.tool.id == 11
    assert op.spindle == sf
    assert ("holes[0]", "delik_tasma_kisildi") not in notlar(p)

    # Ø4 × 15 kör → 15/4 > 3 → G83, q = 4
    p = plan(ozellik(holes=[delik(30, 30, 4, 15, False)]), lib=lib)
    (op,) = _delikler(p)
    assert op.tool_id == 14
    assert op.op.kind == "G83" and op.op.q == pytest.approx(4.0)
    assert op.op.z == pytest.approx(5.0) and op.op.r == pytest.approx(21.0)

    # stok altı 0, boydan Ø8 → b = 0, not
    p = plan(ozellik(holes=[delik(30, 30, 8, 20, True)]), lib=lib)
    (op,) = _delikler(p)
    assert op.op.z == pytest.approx(0.0)
    assert notlar(p) == [("holes[0]", "delik_tasma_kisildi")]
    assert p.notes[0].value == pytest.approx(0.0, abs=1e-12)

    # lambalı Ø6.6 / Ø11 × 6.4 → delik (T12) + lamba (dairesel cep [13.6, 20], §3 → Ø10)
    lam = delik(30, 30, 6.6, 20, True, cbore_d=11.0, cbore_depth=6.4)
    p = plan(ozellik(holes=[lam]), stock=s3, lib=lib)
    ops = _delikler(p)
    assert [(o.kind, o.tool_id, o.feature) for o in ops] == [
        ("delik", 12, "holes[0]"),
        ("lamba", 2, "holes[0]"),
    ]
    tp = ops[1].op
    assert isinstance(tp, Toolpath)
    assert tp.rpm == milling(lib.get(2), MALZEME).n
    kesme_z = [m.end[2] for m in tp.moves if m.feed is not None]
    assert min(kesme_z) == pytest.approx(20 - 6.4, abs=1e-9)
    for m in tp.moves:
        if m.feed is not None:  # merkez yolu Ø11 − Ø10 = 0.5 yarıçaplı daire içinde
            assert math.hypot(m.end[0] - 30, m.end[1] - 30) <= 0.5 + 1e-6
    assert p.unplanned == ()

    # havşalı → delik + havsa_takimi_yok
    hv = delik(30, 30, 6.6, 20, True, csk_d=12.0, csk_angle=90.0)
    p = plan(ozellik(holes=[hv]), stock=s3, lib=lib)
    assert [(o.kind, o.tool_id) for o in _delikler(p)] == [("delik", 12)]
    assert kodlar(p) == [("holes[0]", "havsa_takimi_yok")]

    # M8 dişli → Ø6.8 delik + kilavuz_cevrimi_yok
    m8 = delik(30, 30, 6.8, 15, False, thread="M8", thread_d=8.0, pitch=1.25, thread_depth=12.0)
    p = plan(ozellik(holes=[m8]), lib=lib)
    assert [(o.kind, o.tool_id) for o in _delikler(p)] == [("delik", 13)]
    assert kodlar(p) == [("holes[0]", "kilavuz_cevrimi_yok")]

    # eğimli → ustten_erisilemez
    s, c = math.sin(math.radians(30)), math.cos(math.radians(30))
    eg = delik(30, 30, 8, 10, False, axis=(s, 0.0, -c))
    p = plan(ozellik(holes=[eg]), lib=lib)
    assert _delikler(p) == [] and kodlar(p) == [("holes[0]", "ustten_erisilemez")]

    # Ø5: kütüphanede yok → takim_yok
    p = plan(ozellik(holes=[delik(30, 30, 5, 10, False)]), lib=lib)
    assert _delikler(p) == [] and kodlar(p) == [("holes[0]", "takim_yok")]

    # aynı gruptaki 4 delik: en yakın komşu sırası
    xy = [(10, 10), (90, 50), (15, 45), (80, 12)]
    p = plan(ozellik(holes=[delik(x, y, 8, 20, True) for x, y in xy]), stock=s3, lib=lib)
    (op,) = _delikler(p)
    assert op.op.holes == [(10.0, 10.0), (15.0, 45.0), (80.0, 12.0), (90.0, 50.0)]
    m = re.fullmatch(r"holes\[([\d,\s]+)\]", op.feature)
    assert m is not None
    assert sorted(int(i) for i in m.group(1).split(",")) == [0, 1, 2, 3]


# ---------------------------------------------------------------- K7


def test_yan_paso():
    lib = freze_lib(ae1=0.7 * 16)
    p = plan(ozellik(faces=[yuz()]), lib=lib)
    (op,) = p.ops
    assert op.stepover == pytest.approx(8.0)
    assert notlar(p) == [("faces[0]", "yan_paso_kisildi")]
    assert p.notes[0].value == pytest.approx(8.0)
    T1 = lib.get(1)
    ayni_yol(op, ops2d.face(STOK, T1, kesme(T1, 22.0, 20.0, kurulum())))


# ---------------------------------------------------------------- K8


def ozellik_k8() -> Features:
    return ozellik(
        faces=[yuz()],
        pockets=[cep_k2(), cep_keskin()],
        opens=[acik_basamak()],
        holes=[
            delik(10, 50, 8, 20, True),
            delik(90, 50, 8, 20, True),
            delik(90, 20, 6.6, 20, True, cbore_d=11.0, cbore_depth=6.4),
        ],
    )


def test_sira():
    p = plan(ozellik_k8())
    assert len(p.setups) == 1
    assert ozet(p) == [
        ("yuz_alma", 1, "faces[0]"),
        ("acik_bolge", 1, "opens[0]"),
        ("cep", 1, "pockets[0]"),
        ("cep_kalan", 2, "pockets[0]"),
        ("cep", 2, "pockets[1]"),
        ("cep_kalan", 3, "pockets[1]"),
        ("delik", 11, p.ops[6].feature),  # grup adresi aşağıda boşluksuz denetlenir
        ("delik", 12, "holes[2]"),
        ("lamba", 2, "holes[2]"),
    ]
    assert p.ops[6].feature.replace(" ", "") == "holes[0,1]"
    assert p.ops[6].op.holes == [(10.0, 50.0), (90.0, 50.0)]
    names = [o.name for o in p.ops]
    assert names == [f"{i + 1:02d}-{o.kind}-T{o.tool_id}" for i, o in enumerate(p.ops)]
    assert names[0] == "01-yuz_alma-T1" and names[-1] == "09-lamba-T2"
    assert all(o.setup == 0 for o in p.ops)
    # alan işlemlerinin üst seviyesi azalmayan değil (kesme hareketlerinin en üst Z'si)
    ust = []
    for o in p.ops[:6]:
        zs = [m.end[2] for m in o.op.moves if m.feed is not None]
        ust.append(max(zs))
    assert all(b <= a + 1e-9 for a, b in zip(ust, ust[1:], strict=False))
    # T1, T1, T1, T2, T2, T3, T11, T12, T2 → ilk takım + 5 geçiş
    assert p.tool_changes() == 6
    assert p.ops_for(0) == [o.op for o in p.ops]


# ---------------------------------------------------------------- K9


def test_ikinci_baglama():
    lib = freze_lib()
    s3 = Stock(-2, -2, -3, 102, 62, 22)
    p = plan(ozellik(faces=[yuz(stock=s3)]), stock=s3, lib=lib)
    assert len(p.setups) == 2
    s1, s2 = p.setups
    assert s1.wcs.code == "G54" and s2.wcs.code == "G55"
    assert s2.stock.to_dict() == s3.to_dict()
    assert s2.fixtures == []
    alt = [o for o in p.ops if o.setup == 1]
    assert len(alt) == 1
    op = alt[0]
    assert (op.kind, op.tool_id, op.feature) == ("yuz_alma", 1, "alt_yuz")
    assert op.name == "02-yuz_alma-T1"
    T1 = lib.get(1)
    ayni_yol(op, ops2d.face(s3, T1, kesme(T1, 22.0, 19.0, s2)))
    assert ("alt_yuz", "ikinci_baglama") in notlar(p)
    (n,) = [n for n in p.notes if n.code == "ikinci_baglama"]
    assert n.value == pytest.approx(3.0)
    assert p.ops_for(1) == [op.op]
    assert p.tool_changes() == 2  # her bağlamanın ilk takımı

    # wcs2 verilirse o kullanılır; fixtures2 varsayılanı bağlama 1'in elemanları
    cene = Stock(-10, -12, -3, 112, -2, 10)
    q = plan(ozellik(faces=[yuz(stock=s3)]), stock=s3, lib=lib, fixtures=[cene], wcs2=Wcs("G56"))
    assert q.setups[1].wcs.code == "G56"
    assert [f.to_dict() for f in q.setups[1].fixtures] == [cene.to_dict()]

    # parça stok altına oturuyorsa ikinci bağlama yok
    assert len(plan(ozellik(faces=[yuz()])).setups) == 1


# ---------------------------------------------------------------- K10


def test_baglama_carpismasi():
    f = acik_basamak()  # basamak stoğun y = −2 kenarına iner; Ø16 merkez yolu y = −1'e kadar
    cene15 = Stock(-10, -12, 0, 110, -2, 15)
    p = plan(ozellik(opens=[f]), fixtures=[cene15])
    assert [o for o in p.ops if o.feature == "opens[0]"] == []
    assert kodlar(p) == [("opens[0]", "baglama_carpismasi")]
    assert "bağlama elemanına" in p.unplanned[0].detail
    assert p.setups[0].fixtures[0].to_dict() == cene15.to_dict()

    cene14 = Stock(-10, -12, 0, 110, -2, 14)
    q = plan(ozellik(opens=[f]), fixtures=[cene14])
    assert [(o.kind, o.tool_id) for o in q.ops] == [("acik_bolge", 1)]
    assert q.unplanned == ()


# ---------------------------------------------------------------- K11


def _beklenen_gcode(p: MillPlan, lib: ToolLibrary, dialect) -> list[str]:
    out = []
    for i, s in enumerate(p.setups):
        ops = p.ops_for(i)
        ids = list(dict.fromkeys(o.tool_id for o in p.ops if o.setup == i))
        lo = length_offsets(lib, ids, ref_id=ids[0]) if dialect is GRBL else None
        out.append(write(ops, dialect, program_no=1 + i, setup=s, length_offsets=lo))
    return out


def _op_esit(a, b) -> bool:
    if isinstance(a, Toolpath):
        return isinstance(b, Toolpath) and a.to_dict() == b.to_dict()
    return a == b


def test_gcode_ve_determinizm():
    lib = freze_lib()
    p = plan(ozellik_k8(), lib=lib)
    g = p.gcode(lib, GRBL)
    assert isinstance(g, list) and len(g) == 1
    assert g == _beklenen_gcode(p, lib, GRBL)
    assert p.gcode(lib, FANUC) == _beklenen_gcode(p, lib, FANUC)
    assert p.gcode(lib) == g  # varsayılan GRBL, program_no = 1

    s3 = Stock(-2, -2, -3, 102, 62, 22)
    p2 = plan(ozellik(faces=[yuz(stock=s3)], pockets=[cep_k2()]), stock=s3, lib=lib)
    g2 = p2.gcode(lib, GRBL)
    assert len(g2) == 2
    assert g2 == _beklenen_gcode(p2, lib, GRBL)

    # determinizm ve girdilerin değişmemesi
    F = ozellik_k8()
    lib_once = copy.deepcopy(lib.to_dict())
    stok_once = STOK.to_dict()
    halka = F.pockets[0].region.outer
    a = plan(F, lib=lib)
    b = plan(F, lib=lib)
    assert a.summary() == b.summary()
    assert len(a.ops) == len(b.ops)
    assert all(_op_esit(x.op, y.op) for x, y in zip(a.ops, b.ops, strict=True))
    assert [(u.feature, u.code, u.detail) for u in a.unplanned] == [
        (u.feature, u.code, u.detail) for u in b.unplanned
    ]
    assert [(n.feature, n.code, n.value) for n in a.notes] == [(n.feature, n.code, n.value) for n in b.notes]
    assert lib.to_dict() == lib_once
    assert STOK.to_dict() == stok_once
    assert F.pockets[0].region.outer is halka

    karisik = list(lib.tools)
    random.Random(29).shuffle(karisik)
    c = plan(F, lib=ToolLibrary(karisik))
    assert c.summary() == a.summary()
    assert all(_op_esit(x.op, y.op) for x, y in zip(a.ops, c.ops, strict=True))


# ---------------------------------------------------------------- K15


@pytest.mark.parametrize(
    "kw",
    [
        {"material": ""},
        {"material": 5},
        {"lib": [1, 2]},
        {"stock": CylinderStock(D=40, zmin=0, zmax=22)},
        {"part_zmin": -10.0},
        {"part_zmin": 30.0},
        {"options": {"n_max": 0.0}},
        {"options": {"n_max": -100.0}},
        {"options": {"n_max": math.nan}},
        {"options": {"plunge_ratio": 0.0}},
        {"options": {"plunge_ratio": 1.5}},
        {"options": {"plunge_ratio": math.inf}},
        {"options": {"clearance": -1.0}},
        {"options": {"open_margin": -1.0}},
        {"options": {"drill_tol": -0.1}},
        {"options": {"breakthrough": -1.0}},
        {"options": {"peck_limit": 0.0}},
        {"options": {"peck_q": 0.0}},
        {"options": {"clearance": math.nan}},
    ],
)
def test_hatalar(kw):
    F = ozellik(faces=[yuz()], pockets=[cep_k2()])
    with pytest.raises(CamError):
        kw = dict(kw)
        if "options" in kw:
            kw["options"] = MillOptions(**kw["options"])
        lib = kw.pop("lib", freze_lib())
        stock = kw.pop("stock", STOK)
        part_zmin = kw.pop("part_zmin", 0.0)
        material = kw.pop("material", MALZEME)
        plan_mill_features(F, part_zmin, stock, lib, material, **kw)


def test_hatalar_kutuphane_dogrulama():
    lib = freze_lib()
    lib.tools.append(copy.deepcopy(lib.tools[0]))  # yinelenen id → validate() geçmez
    with pytest.raises(CamError):
        plan(ozellik(faces=[yuz()]), lib=lib)


def test_hatalar_strict():
    dar = PocketFeature(Region(dikdortgen(50, 30, 3, 20)), 20.0, 15.0, 0.0)
    eg = delik(30, 30, 8, 10, False, axis=(0.6, 0.0, -0.8))
    with pytest.raises(CamError) as e:
        plan(ozellik(pockets=[dar], holes=[eg]), options=MillOptions(strict=True))
    m = str(e.value)
    for parca in ("pockets[0]", "takim_sigmiyor", "holes[0]", "ustten_erisilemez"):
        assert parca in m
    # strict olmadan: sıra adres, sonra kod
    p = plan(ozellik(pockets=[dar], holes=[eg]))
    assert kodlar(p) == sorted(kodlar(p))
    assert all(isinstance(u, Unplanned) for u in p.unplanned)
    assert all(isinstance(n, PlanNote) for n in p.notes)
