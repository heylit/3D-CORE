"""SPEC 00 Ek 2 — Dalga 2 CAM arayüzü testleri (K11–K15).

Testler sadece SPEC 00 Ek 2 metninden ve main'deki Dalga 1 `cam/model.py` arayüzünden yazıldı;
Ek 2 uygulama kodu okunmadı (henüz yok).

Uygulanmamış kural: Ek 2 tipleri `cam.model`'de yokken her test `NotImplementedError` ile düşer
(`ek2` dekoratörü); kök conftest bunu "uygulanmamış" sayar. Modül düzeyinde yeni ad import
edilmez, yoksa toplama aşaması düşer.

G18 yön kuralı (ISO 6983, +Y'den bakınca sağ el kuralı): +Y etrafında pozitif dönüş
x' = x·cosθ + z·sinθ, z' = −x·sinθ + z·cosθ; yani G3 +Z'yi +X'e, +X'i −Z'ye götürür.
Yay merkezi ZX'te (x, z) sırasıyla verilir (I, K).
"""

from __future__ import annotations

import functools
import json
import math

import numpy as np
import pytest

import cam.model as M
from cam.model import CamError, Move, MoveType, Stock, Tool, ToolKind, Toolpath

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
R = 10.0  # yay testlerinde yarıçap [mm]
NAN, INF = float("nan"), float("inf")

EK2_ADLARI = (
    "Plane",
    "FeedMode",
    "LatheToolKind",
    "CuttingData",
    "ToolHolder",
    "LatheTool",
    "tool_from_dict",
    "ToolLibrary",
    "CylinderStock",
    "Wcs",
    "Setup",
)


def ek2(test):
    """Ek 2 tipleri yoksa testi NotImplementedError ile düşürür ("uygulanmamış")."""

    @functools.wraps(test)
    def sarici(*args, **kwargs):
        eksik = [ad for ad in EK2_ADLARI if not hasattr(M, ad)]
        if eksik:
            raise NotImplementedError(f"SPEC 00 Ek 2 uygulanmamış: cam.model içinde yok: {eksik}")
        return test(*args, **kwargs)

    return sarici


def jsonla(d: dict) -> dict:
    """JSON metnine yazıp geri okur (gidiş-dönüş gerçek JSON üzerinden olsun)."""
    return json.loads(json.dumps(d))


# ---------------------------------------------------------------- yardımcı kurucular


def holder() -> M.ToolHolder:
    """ER32 benzeri uydurma tutucu: ağızda r = 20, 40 mm'de r = 25, 60 mm ölçü boyu."""
    return M.ToolHolder(name="ER32", gauge_length=60.0, profile=((0.0, 20.0), (40.0, 25.0), (60.0, 25.0)))


def freze(**kw) -> Tool:
    """Ø10 düz freze; yeni alanlar anahtar sözcükle."""
    return Tool(id=1, name="freze10", kind=ToolKind.FLAT, D=10.0, flute_length=22.0, **kw)


def torna(**kw) -> M.LatheTool:
    """CNMG benzeri dış tornalama takımı: κr = 95°, εr = 80°, rε = 0.8."""
    args = dict(id=11, name="CNMG", kind=M.LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=95.0, eps_r=80.0)
    args.update(kw)
    return M.LatheTool(**args)


def kanal(**kw) -> M.LatheTool:
    """3 mm kanal takımı: κr = 90°, εr = 90°, rε = 0.2."""
    args = dict(
        id=12,
        name="kanal3",
        kind=M.LatheToolKind.GROOVE,
        nose_r=0.2,
        tip=3,
        kappa_r=90.0,
        eps_r=90.0,
        width=3.0,
    )
    args.update(kw)
    return M.LatheTool(**args)


def zx_yolu(moves, start, tool=None, **kw) -> Toolpath:
    """ZX (G18) düzleminde takım yolu; takım verilmezse freze."""
    return Toolpath(
        name="zx",
        tool=freze() if tool is None else tool,
        start=start,
        moves=moves,
        rpm=2000.0,
        plane=M.Plane.ZX,
        **kw,
    )


def torna_yolu(moves=None, start=(20.0, 0.0, 5.0), **kw) -> Toolpath:
    """Torna yolu: LatheTool, ZX, y = 0, devir başı ilerleme."""
    if moves is None:
        moves = [Move(G1, (20.0, 0.0, -30.0), feed=0.2), Move(G1, (25.0, 0.0, -30.0), feed=0.2)]
    args = dict(
        name="dis_tornalama",
        tool=torna(),
        start=start,
        moves=moves,
        rpm=3000.0,
        plane=M.Plane.ZX,
        feed_mode=M.FeedMode.PER_REV,
        css=180.0,
    )
    args.update(kw)
    return Toolpath(**args)


# ---------------------------------------------------------------- sabitler


@ek2
def test_yeni_sabitler():
    assert M.Plane.XY.value == "G17"
    assert M.Plane.ZX.value == "G18"
    assert M.Plane("G18") is M.Plane.ZX
    assert M.FeedMode.PER_MIN.value == "G94"
    assert M.FeedMode.PER_REV.value == "G95"
    assert M.LatheToolKind.TURN.value == "tornalama"
    assert M.LatheToolKind.BORE.value == "ic_tornalama"
    assert M.LatheToolKind.GROOVE.value == "kanal"
    assert M.LatheToolKind.THREAD.value == "dis"


@ek2
def test_torna_ve_freze_tur_degerleri_cakismiyor():
    """JSON'da takım türü `kind` değerinden anlaşıldığı için iki küme ayrık olmalı."""
    assert not {k.value for k in M.LatheToolKind} & {k.value for k in ToolKind}


# ---------------------------------------------------------------- K11: CuttingData


@ek2
def test_kesme_verisi_freze_ve_torna():
    f = M.CuttingData(Vc=200.0, fz=0.05, ap=5.0, ae=2.0)
    assert (f.Vc, f.fz, f.fn, f.ap, f.ae) == (200.0, 0.05, None, 5.0, 2.0)
    t = M.CuttingData(Vc=180.0, fn=0.25)
    assert (t.Vc, t.fz, t.fn, t.ap, t.ae) == (180.0, None, 0.25, None, None)


@pytest.mark.parametrize(
    "kw",
    [
        dict(Vc=0.0, fz=0.05),  # Vc > 0
        dict(Vc=-100.0, fz=0.05),
        dict(Vc=200.0),  # fz de fn de yok
        dict(Vc=200.0, fz=0.05, fn=0.2),  # ikisi birden
        dict(Vc=200.0, fz=0.0),
        dict(Vc=200.0, fn=-0.1),
        dict(Vc=200.0, fz=0.05, ap=0.0),
        dict(Vc=200.0, fz=0.05, ae=-1.0),
        dict(Vc=NAN, fz=0.05),
        dict(Vc=INF, fz=0.05),
        dict(Vc=200.0, fz=NAN),
        dict(Vc=200.0, fn=INF),
        dict(Vc=200.0, fz=0.05, ap=NAN),
        dict(Vc=200.0, fz=0.05, ae=INF),
    ],
)
@ek2
def test_kesme_verisi_gecersiz(kw):
    with pytest.raises(CamError):
        M.CuttingData(**kw)


@ek2
def test_kesme_verisi_json_gidis_donus():
    for c in (M.CuttingData(Vc=200.0, fz=0.05, ap=5.0, ae=2.0), M.CuttingData(Vc=180.0, fn=0.25)):
        assert M.CuttingData.from_dict(jsonla(c.to_dict())) == c


# ---------------------------------------------------------------- K11: ToolHolder


@ek2
def test_tutucu_gecerli_ve_json():
    h = holder()
    assert h.gauge_length == 60.0
    assert len(h.profile) == 3
    h2 = M.ToolHolder.from_dict(jsonla(h.to_dict()))
    assert h2.name == "ER32"
    assert h2.gauge_length == 60.0
    assert [tuple(p) for p in h2.profile] == [(0.0, 20.0), (40.0, 25.0), (60.0, 25.0)]


@ek2
def test_tutucu_esit_z_kademe_kabul():
    """z azalmayan: aynı z'de iki nokta (kademe / omuz) geçerli."""
    M.ToolHolder(
        name="kademe", gauge_length=50.0, profile=((0.0, 15.0), (20.0, 15.0), (20.0, 30.0), (50.0, 30.0))
    )


@pytest.mark.parametrize(
    "gauge_length, profile",
    [
        (0.0, ((0.0, 20.0), (0.0, 25.0))),  # gauge_length > 0
        (-10.0, ((0.0, 20.0), (5.0, 20.0))),
        (60.0, ((0.0, 20.0),)),  # en az 2 nokta
        (60.0, ()),
        (60.0, ((5.0, 20.0), (60.0, 25.0))),  # ilk z = 0 değil
        (60.0, ((0.0, 20.0), (40.0, 25.0), (30.0, 25.0))),  # z azalıyor
        (60.0, ((0.0, 20.0), (70.0, 25.0))),  # z > gauge_length
        (60.0, ((0.0, 0.0), (60.0, 25.0))),  # r > 0
        (60.0, ((0.0, 20.0), (60.0, -5.0))),
        (NAN, ((0.0, 20.0), (60.0, 25.0))),
        (60.0, ((0.0, 20.0), (NAN, 25.0))),
    ],
)
@ek2
def test_tutucu_gecersiz(gauge_length, profile):
    with pytest.raises(CamError):
        M.ToolHolder(name="bozuk", gauge_length=gauge_length, profile=profile)


# ---------------------------------------------------------------- K11: Tool yeni alanları


@ek2
def test_freze_yeni_alan_varsayilanlari():
    t = freze()
    assert t.flutes is None
    assert t.shank_d is None
    assert t.stickout is None
    assert t.holder is None
    assert t.cutting == {}
    assert t.shank == 10.0  # shank_d yok → D
    assert t.gauge_length is None


@ek2
def test_freze_cutting_varsayilani_paylasilmiyor():
    a, b = freze(), freze()
    a.cutting["AL6061"] = M.CuttingData(Vc=300.0, fz=0.08)
    assert b.cutting == {}


@ek2
def test_freze_sap_capi():
    assert freze(shank_d=12.0).shank == 12.0


@ek2
def test_gauge_length_tutucu_arti_tasma():
    """Ölçü boyu = tutucu ölçü boyu + taşma: 60 + 35 = 95."""
    t = freze(holder=holder(), stickout=35.0, flutes=4)
    assert t.gauge_length == pytest.approx(95.0, rel=1e-12)


@pytest.mark.parametrize("kw", [dict(holder=None, stickout=35.0), dict(stickout=None)])
@ek2
def test_gauge_length_eksikse_none(kw):
    args = dict(holder=holder())
    args.update(kw)
    assert freze(**args).gauge_length is None


@ek2
def test_taşma_kesici_boya_esit_kabul():
    assert freze(stickout=22.0).stickout == 22.0


@pytest.mark.parametrize(
    "kw",
    [
        dict(flutes=0),  # >= 1
        dict(flutes=-2),
        dict(shank_d=0.0),  # > 0
        dict(shank_d=-6.0),
        dict(shank_d=NAN),
        dict(stickout=21.9),  # >= flute_length (22)
        dict(stickout=NAN),
    ],
)
@ek2
def test_freze_yeni_alan_gecersiz(kw):
    with pytest.raises(CamError):
        freze(**kw)


@ek2
def test_freze_kesme_verisi_fz_zorunlu():
    t = freze(cutting={"C45": M.CuttingData(Vc=150.0, fz=0.04)})
    assert t.cutting["C45"].fz == 0.04
    with pytest.raises(CamError):
        freze(cutting={"C45": M.CuttingData(Vc=150.0, fn=0.2)})


@ek2
def test_freze_json_gidis_donus_tum_alanlar():
    t = freze(
        flutes=3,
        shank_d=10.0,
        stickout=35.0,
        holder=holder(),
        cutting={"AL6061": M.CuttingData(Vc=300.0, fz=0.08, ap=10.0, ae=3.0)},
    )
    t2 = Tool.from_dict(jsonla(t.to_dict()))
    assert isinstance(t2, Tool)
    assert t2.to_dict() == t.to_dict()
    assert t2.kind is ToolKind.FLAT
    assert t2.flutes == 3
    assert t2.gauge_length == pytest.approx(95.0, rel=1e-12)
    assert t2.cutting["AL6061"] == M.CuttingData(Vc=300.0, fz=0.08, ap=10.0, ae=3.0)


# ---------------------------------------------------------------- K11: LatheTool


@ek2
def test_torna_takimi_gecerli():
    t = torna()
    assert t.kind is M.LatheToolKind.TURN
    assert t.width == 0.0
    assert t.cutting == {}
    k = kanal()
    assert k.width == 3.0


@pytest.mark.parametrize(
    "kw",
    [
        dict(kind=M.LatheToolKind.BORE, kappa_r=93.0, eps_r=55.0),  # DNMG iç tornalama
        dict(kind=M.LatheToolKind.THREAD, nose_r=0.0, kappa_r=60.0, eps_r=60.0),  # diş: rε = 0 serbest
        dict(tip=0),  # 0 ve 9 burun merkezi
        dict(tip=9),
        dict(kappa_r=90.0, eps_r=90.0),  # κr + εr = 180 sınırda geçerli
    ],
)
@ek2
def test_torna_takimi_gecerli_varyantlar(kw):
    torna(**kw)


@ek2
def test_kanal_burun_yaricapi_yarim_genislige_esit_kabul():
    kanal(nose_r=1.5, width=3.0)


@pytest.mark.parametrize(
    "kw",
    [
        dict(nose_r=-0.1),  # >= 0
        dict(nose_r=0.0),  # TURN için > 0
        dict(kind=M.LatheToolKind.BORE, nose_r=0.0),  # BORE için > 0
        dict(tip=-1),  # 0..9
        dict(tip=10),
        dict(kappa_r=0.0),  # 0 < κr < 180
        dict(kappa_r=180.0),
        dict(eps_r=0.0),  # 0 < εr < 180
        dict(eps_r=180.0),
        dict(kappa_r=95.0, eps_r=90.0),  # κr + εr > 180: arka kenarda boşluk yok
        dict(width=3.0),  # TURN'de width = 0
        dict(nose_r=NAN),
        dict(kappa_r=NAN),
        dict(eps_r=INF),
    ],
)
@ek2
def test_torna_takimi_gecersiz(kw):
    with pytest.raises(CamError):
        torna(**kw)


@pytest.mark.parametrize(
    "kw",
    [
        dict(width=0.0),  # GROOVE için width > 0
        dict(width=-3.0),
        dict(nose_r=1.6, width=3.0),  # rε <= width / 2
        dict(width=NAN),
    ],
)
@ek2
def test_kanal_gecersiz(kw):
    with pytest.raises(CamError):
        kanal(**kw)


@ek2
def test_torna_kesme_verisi_fn_zorunlu():
    t = torna(cutting={"C45": M.CuttingData(Vc=220.0, fn=0.25, ap=2.0)})
    assert t.cutting["C45"].fn == 0.25
    with pytest.raises(CamError):
        torna(cutting={"C45": M.CuttingData(Vc=220.0, fz=0.1)})


@ek2
def test_torna_takimi_json_ve_tool_from_dict():
    t = kanal(cutting={"C45": M.CuttingData(Vc=120.0, fn=0.05)})
    d = jsonla(t.to_dict())
    t2 = M.LatheTool.from_dict(d)
    assert t2.to_dict() == t.to_dict()
    t3 = M.tool_from_dict(d)
    assert isinstance(t3, M.LatheTool)
    assert t3.kind is M.LatheToolKind.GROOVE
    assert t3.width == 3.0
    f = M.tool_from_dict(jsonla(freze(flutes=2).to_dict()))
    assert isinstance(f, Tool)
    assert f.flutes == 2


# ---------------------------------------------------------------- K12: ToolLibrary


def karisik_kutuphane() -> M.ToolLibrary:
    return M.ToolLibrary(
        tools=[
            freze(
                flutes=3, stickout=35.0, holder=holder(), cutting={"AL6061": M.CuttingData(Vc=300.0, fz=0.08)}
            ),
            Tool(id=2, name="kuresel6", kind=ToolKind.BALL, D=6.0, flute_length=12.0),
            torna(cutting={"C45": M.CuttingData(Vc=220.0, fn=0.25, ap=2.0)}),
            kanal(),
        ]
    )


@ek2
def test_kutuphane_bos_varsayilan_paylasilmiyor():
    a = M.ToolLibrary()
    assert a.tools == []
    a.add(freze())
    assert M.ToolLibrary().tools == []


@ek2
def test_kutuphane_get_ve_add():
    lib = karisik_kutuphane()
    lib.validate()
    assert lib.get(11).name == "CNMG"
    assert lib.get(2).kind is ToolKind.BALL
    yeni = Tool(id=5, name="matkap8", kind=ToolKind.DRILL, D=8.0, flute_length=40.0)
    lib.add(yeni)
    assert lib.get(5) is yeni


@ek2
def test_kutuphane_bilinmeyen_id():
    with pytest.raises(CamError):
        karisik_kutuphane().get(99)


@ek2
def test_kutuphane_yinelenen_id_add():
    lib = karisik_kutuphane()
    with pytest.raises(CamError):
        lib.add(
            Tool(id=11, name="ayni_id", kind=ToolKind.FLAT, D=4.0, flute_length=10.0)
        )  # 11 torna takımında


@ek2
def test_kutuphane_yinelenen_id_validate():
    lib = M.ToolLibrary(tools=[freze(), torna(id=1)])
    with pytest.raises(CamError):
        lib.validate()


@ek2
def test_kutuphane_json_gidis_donus_birebir():
    lib = karisik_kutuphane()
    d = lib.to_dict()
    lib2 = M.ToolLibrary.from_dict(jsonla(d))
    assert lib2.to_dict() == d
    assert [type(t) for t in lib2.tools] == [Tool, Tool, M.LatheTool, M.LatheTool]
    assert [t.id for t in lib2.tools] == [1, 2, 11, 12]
    assert lib2.get(1).gauge_length == pytest.approx(95.0, rel=1e-12)
    assert lib2.get(2).corner_r == 3.0
    assert lib2.get(11).cutting["C45"] == M.CuttingData(Vc=220.0, fn=0.25, ap=2.0)
    assert lib2.get(12).kind is M.LatheToolKind.GROOVE


# ---------------------------------------------------------------- K13: Stock, CylinderStock, Wcs, Setup


@ek2
def test_stock_json_gidis_donus():
    s = Stock(-50.0, -30.0, -20.0, 50.0, 30.0, 0.0)
    assert Stock.from_dict(jsonla(s.to_dict())) == s


@ek2
def test_silindir_dolu_ve_boru():
    """V = π/4·(D² − d²)·L. Dolu: π/4·40²·100; boru: π/4·(40² − 30²)·100."""
    dolu = M.CylinderStock(D=40.0, zmin=-100.0, zmax=0.0)
    assert dolu.d == 0.0
    assert dolu.length == pytest.approx(100.0, rel=1e-12)
    assert dolu.volume == pytest.approx(math.pi / 4 * 40.0**2 * 100.0, rel=1e-12)
    boru = M.CylinderStock(D=40.0, zmin=-100.0, zmax=0.0, d=30.0)
    assert boru.volume == pytest.approx(math.pi / 4 * (40.0**2 - 30.0**2) * 100.0, rel=1e-12)


@ek2
def test_silindir_bbox():
    lo, hi = M.CylinderStock(D=40.0, zmin=-100.0, zmax=2.0, d=10.0).bbox()
    np.testing.assert_allclose(lo, [-20.0, -20.0, -100.0], rtol=0, atol=1e-12)
    np.testing.assert_allclose(hi, [20.0, 20.0, 2.0], rtol=0, atol=1e-12)


@pytest.mark.parametrize(
    "kw",
    [
        dict(D=0.0, zmin=0.0, zmax=10.0),  # D > 0
        dict(D=-40.0, zmin=0.0, zmax=10.0),
        dict(D=40.0, zmin=10.0, zmax=10.0),  # zmax > zmin
        dict(D=40.0, zmin=10.0, zmax=0.0),
        dict(D=40.0, zmin=0.0, zmax=10.0, d=-1.0),  # 0 <= d < D
        dict(D=40.0, zmin=0.0, zmax=10.0, d=40.0),
        dict(D=NAN, zmin=0.0, zmax=10.0),
        dict(D=40.0, zmin=0.0, zmax=INF),
    ],
)
@ek2
def test_silindir_gecersiz(kw):
    with pytest.raises(CamError):
        M.CylinderStock(**kw)


@ek2
def test_silindir_json_gidis_donus():
    c = M.CylinderStock(D=40.0, zmin=-100.0, zmax=0.0, d=30.0)
    assert M.CylinderStock.from_dict(jsonla(c.to_dict())) == c


@ek2
def test_wcs_varsayilan_ve_donusum():
    w0 = M.Wcs()
    assert w0.code == "G54"
    np.testing.assert_array_equal(np.asarray(w0.to_machine((1.0, 2.0, 3.0)), dtype=float), [1.0, 2.0, 3.0])
    w = M.Wcs(code="G55", origin=(-250.0, -120.5, -310.0))
    p = (10.0, 20.0, -5.0)
    m = np.asarray(w.to_machine(p), dtype=float)
    np.testing.assert_allclose(m, [-240.0, -100.5, -315.0], rtol=0, atol=1e-12)
    np.testing.assert_allclose(np.asarray(w.to_work(m), dtype=float), p, rtol=0, atol=1e-12)


@pytest.mark.parametrize("code", ["G54", "G55", "G56", "G57", "G58", "G59"])
@ek2
def test_wcs_gecerli_kodlar(code):
    assert M.Wcs(code=code).code == code


@pytest.mark.parametrize("code", ["G53", "G60", "G54.1", "", "X54"])
@ek2
def test_wcs_gecersiz_kod(code):
    with pytest.raises(CamError):
        M.Wcs(code=code)


@ek2
def test_wcs_json_gidis_donus():
    w = M.Wcs(code="G57", origin=(-250.0, -120.5, -310.0))
    w2 = M.Wcs.from_dict(jsonla(w.to_dict()))
    assert w2.code == "G57"
    assert tuple(w2.origin) == (-250.0, -120.5, -310.0)


@ek2
def test_setup_varsayilan_fixtures_paylasilmiyor():
    a = M.Setup(name="op1", wcs=M.Wcs(), stock=Stock(0.0, 0.0, -20.0, 100.0, 60.0, 0.0))
    b = M.Setup(name="op2", wcs=M.Wcs(), stock=Stock(0.0, 0.0, -20.0, 100.0, 60.0, 0.0))
    assert a.fixtures == []
    a.fixtures.append(Stock(-10.0, -10.0, -60.0, 110.0, 0.0, -20.0))
    assert b.fixtures == []


@ek2
def test_setup_json_gidis_donus_kutu_ve_silindir():
    freze_kurulum = M.Setup(
        name="mengene",
        wcs=M.Wcs(code="G54", origin=(-200.0, -100.0, -300.0)),
        stock=Stock(0.0, 0.0, -20.0, 100.0, 60.0, 0.0),
        fixtures=[
            Stock(-5.0, -15.0, -40.0, 105.0, 0.0, -10.0),
            M.CylinderStock(D=12.0, zmin=-40.0, zmax=-20.0),
        ],
    )
    torna_kurulum = M.Setup(
        name="ayna",
        wcs=M.Wcs(code="G56", origin=(0.0, 0.0, -450.0)),
        stock=M.CylinderStock(D=50.0, zmin=-120.0, zmax=1.0),
        fixtures=[M.CylinderStock(D=160.0, zmin=-200.0, zmax=-90.0, d=50.0)],
    )
    for s in (freze_kurulum, torna_kurulum):
        d = s.to_dict()
        s2 = M.Setup.from_dict(jsonla(d))
        assert s2.to_dict() == d
        assert s2.name == s.name
        assert type(s2.stock) is type(s.stock)
        assert [type(f) for f in s2.fixtures] == [type(f) for f in s.fixtures]
        assert s2.stock == s.stock
        assert s2.fixtures == s.fixtures


# ---------------------------------------------------------------- K14: G18 yayları


@ek2
def test_toolpath_yeni_alan_varsayilanlari():
    tp = Toolpath(
        name="xy",
        tool=freze(),
        start=(0.0, 0.0, 5.0),
        moves=[Move(G1, (10.0, 0.0, 5.0), feed=500.0)],
        rpm=1.0,
    )
    assert tp.plane is M.Plane.XY
    assert tp.feed_mode is M.FeedMode.PER_MIN
    assert tp.css is None


@ek2
def test_g18_ceyrek_yay_g3_z_den_x_e():
    """+Z'den (0, 0, R) +X'e (R, 0, 0), merkez (x, z) = (0, 0): G3 çeyrek yay, boy πR/2."""
    tp = zx_yolu([Move(G3, (R, 0.0, 0.0), feed=300.0, center=(0.0, 0.0))], start=(0.0, 0.0, R))
    tp.validate()
    assert tp.length() == pytest.approx(math.pi * R / 2, rel=1e-12)


@ek2
def test_g18_ayni_uclarla_g2_ucte_iki_daire():
    """Aynı uçlar G2 ile ters yönden döner: 3πR/2."""
    tp = zx_yolu([Move(G2, (R, 0.0, 0.0), feed=300.0, center=(0.0, 0.0))], start=(0.0, 0.0, R))
    tp.validate()
    assert tp.length() == pytest.approx(3 * math.pi * R / 2, rel=1e-12)


@ek2
def test_g18_merkez_x_z_sirasinda():
    """Merkez (x, z) = (5, −3): başlangıç (5, 0, −3 + R) → G3 → (5 + R, 0, −3), boy πR/2."""
    tp = zx_yolu([Move(G3, (5.0 + R, 0.0, -3.0), feed=300.0, center=(5.0, -3.0))], start=(5.0, 0.0, -3.0 + R))
    tp.validate()
    assert tp.length() == pytest.approx(math.pi * R / 2, rel=1e-12)


@ek2
def test_g18_helis_y_de_ilerleme():
    """Tam daire XZ'de, Y'de h = 4 ilerleme: s = sqrt((2πR)² + h²)."""
    h = 4.0
    tp = zx_yolu([Move(G3, (R, h, 0.0), feed=300.0, center=(0.0, 0.0))], start=(R, 0.0, 0.0))
    tp.validate()
    assert tp.length() == pytest.approx(math.hypot(2 * math.pi * R, h), rel=1e-12)


@ek2
def test_g18_g3_yarim_daire_bbox_negatif_z():
    """G3 +X'ten −Z'ye döner: (R, 0, 0) → (−R, 0, 0) yarım dairesi z = −R'den geçer."""
    tp = zx_yolu([Move(G3, (-R, 0.0, 0.0), feed=300.0, center=(0.0, 0.0))], start=(R, 0.0, 0.0))
    tp.validate()
    lo, hi = tp.bbox()
    np.testing.assert_allclose(lo, [-R, 0.0, -R], rtol=0, atol=1e-9)
    np.testing.assert_allclose(hi, [R, 0.0, 0.0], rtol=0, atol=1e-9)


@ek2
def test_g18_g2_yarim_daire_bbox_pozitif_z():
    tp = zx_yolu([Move(G2, (-R, 0.0, 0.0), feed=300.0, center=(0.0, 0.0))], start=(R, 0.0, 0.0))
    tp.validate()
    lo, hi = tp.bbox()
    np.testing.assert_allclose(lo, [-R, 0.0, 0.0], rtol=0, atol=1e-9)
    np.testing.assert_allclose(hi, [R, 0.0, R], rtol=0, atol=1e-9)


@ek2
def test_g18_yaricap_denetimi_zx_duzleminde():
    """XY'de yarıçaplar tutar (5, 5) ama ZX'te tutmaz (5, 0) → hata."""
    tp = zx_yolu([Move(G3, (0.0, 5.0, 0.0), feed=300.0, center=(0.0, 0.0))], start=(5.0, 0.0, 0.0))
    with pytest.raises(CamError):
        tp.validate()


@ek2
def test_g18_yaricap_xy_de_tutmasa_da_gecerli():
    """ZX'te yarıçaplar 5 ve 5: geçerli (XY'ye göre bakılsaydı 5 ve 0 olurdu)."""
    zx_yolu([Move(G3, (0.0, 0.0, 5.0), feed=300.0, center=(0.0, 0.0))], start=(5.0, 0.0, 0.0)).validate()


# ---------------------------------------------------------------- K14: torna yolu doğrulaması


@ek2
def test_torna_yolu_gecerli():
    tp = torna_yolu()
    tp.validate()
    assert tp.length() == pytest.approx(35.0 + 5.0, rel=1e-12)


@ek2
def test_torna_yolu_yay_g18():
    """Torna yolunda R2 köşe: (20, 0, −28) → G2 → (22, 0, −30), merkez (x, z) = (22, −28).

    Merkezden bakınca başlangıç −X yönünde (−2, 0), bitiş −Z yönünde (0, −2). +Y etrafında pozitif
    dönüş (G3) −X'i +Z'ye götürür; −X → −Z negatif 90°'dir, yani G2. Boy π·2/2 = π.
    """
    moves = [
        Move(G1, (20.0, 0.0, -28.0), feed=0.2),
        Move(G2, (22.0, 0.0, -30.0), feed=0.1, center=(22.0, -28.0)),
        Move(G1, (25.0, 0.0, -30.0), feed=0.2),
    ]
    tp = torna_yolu(moves)
    tp.validate()
    assert tp.length() == pytest.approx(33.0 + math.pi + 3.0, rel=1e-12)


@ek2
def test_torna_yolu_xy_duzlemi_hata():
    with pytest.raises(CamError):
        torna_yolu(plane=M.Plane.XY).validate()


@ek2
def test_torna_yolu_baslangicta_y_hata():
    with pytest.raises(CamError):
        torna_yolu(start=(20.0, 0.5, 5.0)).validate()


@ek2
def test_torna_yolu_bitiste_y_hata():
    moves = [Move(G1, (20.0, 0.0, -30.0), feed=0.2), Move(G0, (30.0, -1.0, 5.0))]
    with pytest.raises(CamError):
        torna_yolu(moves).validate()


@pytest.mark.parametrize("css", [0.0, -50.0])
@ek2
def test_css_pozitif_olmali(css):
    with pytest.raises(CamError):
        torna_yolu(css=css).validate()


@ek2
def test_torna_yolu_json_gidis_donus():
    tp = torna_yolu()
    d = tp.to_dict()
    tp2 = Toolpath.from_dict(jsonla(d))
    assert isinstance(tp2.tool, M.LatheTool)
    assert tp2.plane is M.Plane.ZX
    assert tp2.feed_mode is M.FeedMode.PER_REV
    assert tp2.css == 180.0
    assert tp2.to_dict() == d
    tp2.validate()


# ---------------------------------------------------------------- K15: eski JSON


def eski_toolpath_json() -> dict:
    """Dalga 1 biçiminde (plane / feed_mode / css ve yeni takım alanları olmadan) takım yolu."""
    return {
        "name": "eski",
        "tool": {"id": 1, "name": "freze6", "kind": "duz", "D": 6.0, "flute_length": 20.0, "corner_r": 0.0},
        "start": [R, 0.0, 0.0],
        "rpm": 12000.0,
        "moves": [
            {"type": "G3", "end": [0.0, R, 0.0], "feed": 800.0, "center": [0.0, 0.0]},
            {"type": "G1", "end": [0.0, R, -2.0], "feed": 200.0, "center": None},
        ],
    }


def test_eski_json_okunuyor():
    """Dalga 1 JSON'u Ek 2'den önce de sonra da okunur; çeyrek yay XY'de (πR/2) + 2 mm dalış."""
    tp = Toolpath.from_dict(eski_toolpath_json())
    tp.validate()
    assert tp.length() == pytest.approx(math.pi * R / 2 + 2.0, rel=1e-12)


@ek2
def test_eski_json_yeni_alanlar_varsayilan():
    tp = Toolpath.from_dict(eski_toolpath_json())
    assert tp.plane is M.Plane.XY
    assert tp.feed_mode is M.FeedMode.PER_MIN
    assert tp.css is None
    assert isinstance(tp.tool, Tool)
    assert tp.tool.flutes is None
    assert tp.tool.holder is None
    assert tp.tool.cutting == {}


@ek2
def test_eski_takim_json_tool_from_dict():
    d = {"id": 3, "name": "kuresel8", "kind": "kuresel", "D": 8.0, "flute_length": 25.0, "corner_r": 4.0}
    for t in (Tool.from_dict(d), M.tool_from_dict(d)):
        assert isinstance(t, Tool)
        assert t.kind is ToolKind.BALL
        assert t.corner_r == 4.0
        assert t.stickout is None
        assert t.gauge_length is None
