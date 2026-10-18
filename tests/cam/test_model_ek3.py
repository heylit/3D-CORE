"""cam/model Ek 3 (A0) arayüz testleri: yeni takım türleri, giriş, bağlama, iş mili gücü, torna profili.

Testler yalnızca onaylanan Ek 3 metninden (arayuz/a0-cam-ek3-onerisi.md) ve main'deki mevcut
`cam/model.py` arayüzünden yazıldı; Ek 3 uygulama kodu okunmadı.

Uygulanmamış kural: Ek 3 adları/alanları `cam.model`'de yokken her test `NotImplementedError` ile düşer
(`ek3` dekoratörü); kök conftest bunu "uygulanmamış" sayar. Modül düzeyinde yeni ad import edilmez,
yoksa toplama aşaması düşer.

Beklenen değerler el ile türetildi. Uç kesici ağız boyu (punta): h = (D/2)·cot(φ/2);
havşa: h = ((D − tip_d)/2)·cot(φ/2); kılavuz giriş boyu: lead·pitch.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import math

import pytest

import cam.model as M
from cam.model import AxisLimits, CamError, Frame, MachineProfile, Tool, ToolKind

NAN, INF = float("nan"), float("inf")
I3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

EK3_ADLARI = ("EntryKind", "EntryMode", "Fixture")
EK3_TURLERI = ("SPOT", "CHAMFER", "TAP")
EK3_TOOL_ALANLARI = ("tip_d", "pitch", "lead", "ramp_angle_max")
EK3_PROFIL_ALANLARI = ("spindle_power_kw", "spindle_torque_nm")


def _eksikler() -> list[str]:
    eksik = [ad for ad in EK3_ADLARI if not hasattr(M, ad)]
    eksik += [f"ToolKind.{t}" for t in EK3_TURLERI if t not in ToolKind.__members__]
    tool_alan = {f.name for f in dataclasses.fields(Tool)}
    eksik += [f"Tool.{a}" for a in EK3_TOOL_ALANLARI if a not in tool_alan]
    profil_alan = {f.name for f in dataclasses.fields(MachineProfile)}
    eksik += [f"MachineProfile.{a}" for a in EK3_PROFIL_ALANLARI if a not in profil_alan]
    return eksik


def ek3(test):
    """Ek 3 adları yoksa testi NotImplementedError ile düşürür ("uygulanmamış")."""

    @functools.wraps(test)
    def sarici(*args, **kwargs):
        eksik = _eksikler()
        if eksik:
            raise NotImplementedError(f"cam/model Ek 3 uygulanmamış: cam.model içinde yok: {eksik}")
        return test(*args, **kwargs)

    return sarici


def jsonla(d: dict) -> dict:
    """JSON metnine yazıp geri okur (gidiş-dönüş gerçek JSON üzerinden olsun)."""
    return json.loads(json.dumps(d))


def kind(ad: str) -> ToolKind:
    return ToolKind[ad]


def cot(derece: float) -> float:
    return 1.0 / math.tan(math.radians(derece))


def tool(ad: str, D: float = 10.0, flute_length: float = 30.0, **kw) -> Tool:
    """Ø10 takım; tür adı ve ek alanlar parametre."""
    return Tool(id=1, name="t", kind=kind(ad), D=D, flute_length=flute_length, **kw)


def spot(**kw) -> Tool:
    args = {"tip_angle": 90.0, **kw}
    return tool("SPOT", **args)


def chamfer(**kw) -> Tool:
    args = {"tip_angle": 90.0, **kw}
    return tool("CHAMFER", **args)


def tap(**kw) -> Tool:
    args = {"pitch": 1.5, "lead": 3.0, **kw}
    return tool("TAP", **args)


# Her türün geçerli zorunlu alanları (Ek 3 tablo + #60 CONE)
ZORUNLU = {
    "FLAT": {},
    "BALL": {},
    "DRILL": {},
    "CONE": {"tip_angle": 90.0},
    "SPOT": {"tip_angle": 90.0},
    "CHAMFER": {"tip_angle": 90.0},
    "TAP": {"pitch": 1.5, "lead": 3.0},
}


# ================================================================ 1. yeni takım türleri


@ek3
def test_new_kind_values():
    assert ToolKind.SPOT.value == "punta"
    assert ToolKind.CHAMFER.value == "havsa"
    assert ToolKind.TAP.value == "kilavuz"
    assert ToolKind("punta") is ToolKind.SPOT
    assert ToolKind("havsa") is ToolKind.CHAMFER
    assert ToolKind("kilavuz") is ToolKind.TAP


@ek3
def test_old_kind_values_unchanged():
    assert ToolKind.FLAT.value == "duz"
    assert ToolKind.BALL.value == "kuresel"
    assert ToolKind.DRILL.value == "matkap"
    assert ToolKind.CONE.value == "konik"


@ek3
@pytest.mark.parametrize("deger", ["punta", "havsa", "kilavuz"])
def test_new_kind_as_string(deger):
    ad = {"punta": "SPOT", "havsa": "CHAMFER", "kilavuz": "TAP"}[deger]
    t = Tool(id=1, name="t", kind=deger, D=10.0, flute_length=30.0, **ZORUNLU[ad])
    assert t.kind is kind(ad)


@ek3
@pytest.mark.parametrize("ad", list(ZORUNLU))
def test_new_field_defaults(ad):
    t = tool(ad, **ZORUNLU[ad])
    assert t.ramp_angle_max is None
    if ad != "CHAMFER":
        assert t.tip_d == 0.0
    if ad != "TAP":
        assert t.pitch is None
        assert t.lead is None


@ek3
def test_chamfer_tip_d_default_zero():
    assert chamfer().tip_d == 0.0


# ---------------------------------------------------------------- SPOT (punta)


@ek3
@pytest.mark.parametrize("phi", [1.0, 60.0, 90.0, 120.0, 142.0])
def test_spot_valid_angles(phi):
    # D=10 → h = 5·cot(φ/2); φ=1° → h ≈ 573 mm, kesici boyu yeterli verilir
    h = 5.0 * cot(phi / 2)
    t = spot(tip_angle=phi, flute_length=h * 1.001)
    assert t.tip_angle == pytest.approx(phi)
    assert t.corner_r == 0.0


@ek3
def test_spot_requires_tip_angle():
    with pytest.raises(CamError):
        tool("SPOT")
    with pytest.raises(CamError):
        spot(tip_angle=None)


@ek3
@pytest.mark.parametrize("phi", [0.0, -10.0, 180.0, 200.0, NAN, INF])
def test_spot_tip_angle_out_of_range(phi):
    with pytest.raises(CamError):
        spot(tip_angle=phi)


@ek3
@pytest.mark.parametrize("r", [0.5, 1.0])
def test_spot_corner_r_rejected(r):
    with pytest.raises(CamError):
        spot(corner_r=r)


@ek3
@pytest.mark.parametrize(("D", "phi"), [(10.0, 90.0), (6.0, 120.0), (8.0, 60.0)])
def test_spot_edge_height(D, phi):
    h = (D / 2) * cot(phi / 2)  # φ=90°: h = D/2; φ=60°: h = (D/2)·√3
    assert spot(D=D, tip_angle=phi, flute_length=h * 1.001).D == D
    with pytest.raises(CamError):
        spot(D=D, tip_angle=phi, flute_length=h * 0.999)


@ek3
def test_spot_edge_height_equal_accepted():
    # D=10, φ=90° → h = 5 tam; kural h ≤ flute_length
    assert spot(D=10.0, tip_angle=90.0, flute_length=5.0).flute_length == 5.0


# ---------------------------------------------------------------- CHAMFER (havşa)


@ek3
@pytest.mark.parametrize("tip_d", [0.0, 2.0, 9.9])
def test_chamfer_valid_tip_d(tip_d):
    assert chamfer(tip_d=tip_d).tip_d == pytest.approx(tip_d)


@ek3
@pytest.mark.parametrize("tip_d", [10.0, 12.0, -0.1, NAN, INF])
def test_chamfer_bad_tip_d(tip_d):
    # 0 ≤ tip_d < D (D = 10)
    with pytest.raises(CamError):
        chamfer(tip_d=tip_d)


@ek3
def test_chamfer_requires_tip_angle():
    with pytest.raises(CamError):
        tool("CHAMFER")
    with pytest.raises(CamError):
        chamfer(tip_angle=None)


@ek3
@pytest.mark.parametrize("phi", [0.0, 180.0, -1.0, NAN])
def test_chamfer_tip_angle_out_of_range(phi):
    with pytest.raises(CamError):
        chamfer(tip_angle=phi)


@ek3
def test_chamfer_corner_r_rejected():
    with pytest.raises(CamError):
        chamfer(corner_r=0.5)


@ek3
@pytest.mark.parametrize(("D", "tip_d", "phi"), [(10.0, 4.0, 90.0), (12.0, 0.0, 90.0), (16.0, 4.0, 60.0)])
def test_chamfer_edge_height(D, tip_d, phi):
    # (10, 4, 90°): h = 3; (12, 0, 90°): h = 6; (16, 4, 60°): h = 6·√3 ≈ 10.392
    h = ((D - tip_d) / 2) * cot(phi / 2)
    assert chamfer(D=D, tip_d=tip_d, tip_angle=phi, flute_length=h * 1.001).tip_d == tip_d
    with pytest.raises(CamError):
        chamfer(D=D, tip_d=tip_d, tip_angle=phi, flute_length=h * 0.999)


@ek3
def test_chamfer_tip_d_shortens_edge():
    # tip_d olmadan h = 5 > 4 → red; tip_d = 4 ile h = 3 ≤ 4 → kabul
    with pytest.raises(CamError):
        chamfer(D=10.0, tip_angle=90.0, flute_length=4.0)
    assert chamfer(D=10.0, tip_d=4.0, tip_angle=90.0, flute_length=4.0).tip_d == 4.0


# ---------------------------------------------------------------- TAP (kılavuz)


@ek3
def test_tap_valid():
    t = tap()
    assert t.pitch == pytest.approx(1.5)
    assert t.lead == pytest.approx(3.0)
    assert t.corner_r == 0.0
    assert t.tip_angle is None


@ek3
@pytest.mark.parametrize("eksik", ["pitch", "lead"])
def test_tap_requires_pitch_and_lead(eksik):
    with pytest.raises(CamError):
        tap(**{eksik: None})


@ek3
def test_tap_requires_both_missing():
    with pytest.raises(CamError):
        tool("TAP")


@ek3
@pytest.mark.parametrize("alan", ["pitch", "lead"])
@pytest.mark.parametrize("deger", [0.0, -1.0, NAN, INF])
def test_tap_bad_pitch_lead(alan, deger):
    with pytest.raises(CamError):
        tap(**{alan: deger})


@ek3
def test_tap_lead_length_strict():
    # lead·pitch = 4 · 1.5 = 6 mm; kural lead·pitch < flute_length (kesin)
    with pytest.raises(CamError):
        tap(pitch=1.5, lead=4.0, flute_length=6.0)
    with pytest.raises(CamError):
        tap(pitch=1.5, lead=4.0, flute_length=5.0)
    assert tap(pitch=1.5, lead=4.0, flute_length=6.01).lead == 4.0


@ek3
def test_tap_rejects_tip_angle():
    with pytest.raises(CamError):
        tap(tip_angle=90.0)


@ek3
def test_tap_corner_r_rejected():
    with pytest.raises(CamError):
        tap(corner_r=0.5)


# ---------------------------------------------------------------- türe bağlı alan kısıtları


@ek3
@pytest.mark.parametrize("ad", ["FLAT", "BALL", "DRILL", "CONE", "SPOT", "TAP"])
def test_tip_d_only_on_chamfer(ad):
    with pytest.raises(CamError):
        tool(ad, tip_d=1.0, **ZORUNLU[ad])


@ek3
@pytest.mark.parametrize("ad", ["FLAT", "BALL", "DRILL", "CONE", "SPOT", "CHAMFER"])
@pytest.mark.parametrize("alan", ["pitch", "lead"])
def test_pitch_lead_only_on_tap(ad, alan):
    with pytest.raises(CamError):
        tool(ad, **{alan: 1.0}, **ZORUNLU[ad])


@ek3
@pytest.mark.parametrize("ad", ["FLAT", "BALL", "TAP"])
def test_tip_angle_rejected_kinds(ad):
    with pytest.raises(CamError):
        tool(ad, **{**ZORUNLU[ad], "tip_angle": 90.0})


@ek3
def test_drill_tip_angle_still_optional():
    assert tool("DRILL").tip_angle is None
    assert tool("DRILL", tip_angle=118.0).tip_angle == pytest.approx(118.0)


@ek3
@pytest.mark.parametrize("ad", ["SPOT", "CHAMFER", "TAP"])
def test_new_kinds_center_cutting_free(ad):
    # yeni türlerde varsayılan True, False'a kısıt yok
    assert tool(ad, **ZORUNLU[ad]).center_cutting is True
    assert tool(ad, center_cutting=False, **ZORUNLU[ad]).center_cutting is False


@ek3
def test_drill_center_cutting_rule_unchanged():
    with pytest.raises(CamError):
        tool("DRILL", center_cutting=False)


# ---------------------------------------------------------------- ramp_angle_max


@ek3
@pytest.mark.parametrize("ad", list(ZORUNLU))
@pytest.mark.parametrize("a", [0.5, 3.0, 45.0, 90.0])
def test_ramp_angle_max_valid_every_kind(ad, a):
    assert tool(ad, ramp_angle_max=a, **ZORUNLU[ad]).ramp_angle_max == pytest.approx(a)


@ek3
@pytest.mark.parametrize("a", [0.0, -1.0, 90.01, 120.0, NAN, INF])
def test_ramp_angle_max_bad(a):
    with pytest.raises(CamError):
        tool("FLAT", ramp_angle_max=a)


# ---------------------------------------------------------------- JSON


@ek3
@pytest.mark.parametrize("ad", list(ZORUNLU))
def test_to_dict_writes_new_fields(ad):
    d = tool(ad, **ZORUNLU[ad]).to_dict()
    for anahtar in EK3_TOOL_ALANLARI:
        assert anahtar in d


@ek3
@pytest.mark.parametrize(
    "t",
    [
        pytest.param(lambda: spot(tip_angle=120.0, ramp_angle_max=5.0), id="punta"),
        pytest.param(lambda: chamfer(tip_d=2.0, tip_angle=60.0, flute_length=12.0), id="havsa"),
        pytest.param(lambda: tap(pitch=1.25, lead=2.5, center_cutting=False), id="kilavuz"),
        pytest.param(lambda: tool("FLAT", ramp_angle_max=3.0), id="duz"),
    ],
)
def test_tool_json_roundtrip(t):
    t1 = t()
    t2 = Tool.from_dict(jsonla(t1.to_dict()))
    assert t2.kind is t1.kind
    assert t2.to_dict() == t1.to_dict()
    for anahtar in EK3_TOOL_ALANLARI:
        assert getattr(t2, anahtar) == getattr(t1, anahtar)


@ek3
@pytest.mark.parametrize("ad", list(ZORUNLU))
def test_from_dict_old_json_loads(ad):
    # Ek 3 alanları olmayan eski sözlük değişmeden yüklenir
    d = tool(ad, **ZORUNLU[ad]).to_dict()
    for anahtar in ("tip_d", "ramp_angle_max") + (() if ad == "TAP" else ("pitch", "lead")):
        del d[anahtar]
    t = Tool.from_dict(jsonla(d))
    assert t.tip_d == 0.0
    assert t.ramp_angle_max is None


@ek3
def test_from_dict_tap_missing_pitch_rejected():
    d = tap().to_dict()
    del d["pitch"]
    with pytest.raises(CamError):
        Tool.from_dict(d)


@ek3
@pytest.mark.parametrize(
    ("ad", "anahtar", "deger"),
    [
        ("FLAT", "tip_d", 1.0),
        ("FLAT", "pitch", 1.0),
        ("SPOT", "lead", 2.0),
        ("CHAMFER", "tip_d", 10.0),
        ("TAP", "pitch", 0.0),
        ("FLAT", "ramp_angle_max", 0.0),
    ],
)
def test_from_dict_validates_new_fields(ad, anahtar, deger):
    d = tool(ad, **ZORUNLU[ad]).to_dict()
    d[anahtar] = deger
    with pytest.raises(CamError):
        Tool.from_dict(d)


# ================================================================ 2. giriş biçimi


@ek3
def test_entry_kind_values():
    assert M.EntryKind.PLUNGE.value == "dalma"
    assert M.EntryKind.RAMP.value == "rampa"
    assert M.EntryKind.HELIX.value == "helis"
    assert len(M.EntryKind) == 3


@ek3
def test_entry_mode_defaults():
    e = M.EntryMode()
    assert e.kind is M.EntryKind.PLUNGE
    assert e.angle == pytest.approx(2.0)
    assert e.radius is None
    assert e.length is None


@ek3
@pytest.mark.parametrize(("deger", "ad"), [("dalma", "PLUNGE"), ("rampa", "RAMP"), ("helis", "HELIX")])
def test_entry_kind_from_string(deger, ad):
    assert M.EntryMode(kind=deger).kind is M.EntryKind[ad]


@ek3
@pytest.mark.parametrize("deger", ["", "spiral", "RAMP", "zigzag"])
def test_entry_bad_kind(deger):
    with pytest.raises(CamError):
        M.EntryMode(kind=deger)


@ek3
@pytest.mark.parametrize("ad", ["PLUNGE", "RAMP", "HELIX"])
@pytest.mark.parametrize("a", [0.1, 2.0, 45.0, 89.9])
def test_entry_angle_valid(ad, a):
    assert M.EntryMode(kind=M.EntryKind[ad], angle=a).angle == pytest.approx(a)


@ek3
@pytest.mark.parametrize("ad", ["PLUNGE", "RAMP", "HELIX"])
@pytest.mark.parametrize("a", [0.0, 90.0, -2.0, 120.0, NAN, INF])
def test_entry_angle_bad(ad, a):
    # 0 < angle < 90 her türde (PLUNGE'da kullanılmaz ama doğrulanır)
    with pytest.raises(CamError):
        M.EntryMode(kind=M.EntryKind[ad], angle=a)


@ek3
def test_entry_helix_radius():
    e = M.EntryMode(kind=M.EntryKind.HELIX, angle=3.0, radius=4.0)
    assert e.radius == pytest.approx(4.0)
    assert M.EntryMode(kind=M.EntryKind.HELIX).radius is None


@ek3
@pytest.mark.parametrize("r", [0.0, -1.0, NAN, INF])
def test_entry_helix_bad_radius(r):
    with pytest.raises(CamError):
        M.EntryMode(kind=M.EntryKind.HELIX, radius=r)


@ek3
@pytest.mark.parametrize("ad", ["PLUNGE", "RAMP"])
def test_entry_radius_only_helix(ad):
    with pytest.raises(CamError):
        M.EntryMode(kind=M.EntryKind[ad], radius=4.0)


@ek3
def test_entry_ramp_length():
    e = M.EntryMode(kind=M.EntryKind.RAMP, angle=5.0, length=20.0)
    assert e.length == pytest.approx(20.0)
    assert M.EntryMode(kind=M.EntryKind.RAMP).length is None


@ek3
@pytest.mark.parametrize("L", [0.0, -5.0, NAN, INF])
def test_entry_ramp_bad_length(L):
    with pytest.raises(CamError):
        M.EntryMode(kind=M.EntryKind.RAMP, length=L)


@ek3
@pytest.mark.parametrize("ad", ["PLUNGE", "HELIX"])
def test_entry_length_only_ramp(ad):
    with pytest.raises(CamError):
        M.EntryMode(kind=M.EntryKind[ad], length=20.0)


@ek3
@pytest.mark.parametrize(
    "e",
    [
        pytest.param(lambda: M.EntryMode(), id="dalma"),
        pytest.param(lambda: M.EntryMode(kind=M.EntryKind.RAMP, angle=4.0, length=15.0), id="rampa"),
        pytest.param(lambda: M.EntryMode(kind=M.EntryKind.HELIX, angle=1.5, radius=3.0), id="helis"),
        pytest.param(lambda: M.EntryMode(kind=M.EntryKind.RAMP, angle=7.0), id="rampa-boysuz"),
    ],
)
def test_entry_json_roundtrip(e):
    e1 = e()
    e2 = M.EntryMode.from_dict(jsonla(e1.to_dict()))
    assert e2 == e1
    assert e2.kind is e1.kind


@ek3
def test_entry_from_dict_only_kind():
    e = M.EntryMode.from_dict({"kind": "helis"})
    assert e.kind is M.EntryKind.HELIX
    assert e.angle == pytest.approx(2.0)
    assert e.radius is None
    assert e.length is None


@ek3
def test_entry_from_dict_unknown_key_rejected():
    d = M.EntryMode().to_dict()
    d["bilinmeyen"] = 1
    with pytest.raises(CamError):
        M.EntryMode.from_dict(d)


@ek3
def test_entry_from_dict_missing_kind_rejected():
    with pytest.raises(CamError):
        M.EntryMode.from_dict({"angle": 3.0})


@ek3
@pytest.mark.parametrize(
    "d",
    [
        {"kind": "spiral"},
        {"kind": "rampa", "angle": 90.0},
        {"kind": "dalma", "radius": 3.0},
        {"kind": "helis", "length": 10.0},
        {"kind": "helis", "radius": -1.0},
    ],
)
def test_entry_from_dict_validates(d):
    with pytest.raises(CamError):
        M.EntryMode.from_dict(d)


# ================================================================ 3. bağlama (Fixture)


def fixture(**kw):
    args = {"name": "Mengene 1", "part_ref": "mengene_125", **kw}
    return M.Fixture(**args)


@ek3
def test_fixture_defaults():
    f = fixture()
    assert f.name == "Mengene 1"
    assert f.part_ref == "mengene_125"
    assert f.kind == "ozel"
    assert f.params == ()
    assert isinstance(f.frame, Frame)
    assert f.frame == Frame((0.0, 0.0, 0.0), I3)


@ek3
def test_fixture_frozen():
    f = fixture()
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.name = "Baska"


@ek3
def test_fixture_own_default_frame():
    # her Fixture kendi birim Frame'ini alır (paylaşılan nesne yok)
    assert fixture().frame is not fixture().frame


@ek3
@pytest.mark.parametrize("kind_", ["mengene", "ayna", "pabuc", "ozel"])
def test_fixture_kinds(kind_):
    assert fixture(kind=kind_).kind == kind_


@ek3
@pytest.mark.parametrize("kind_", ["", "Mengene", "vise", "pabuç", "diger"])
def test_fixture_bad_kind(kind_):
    with pytest.raises(CamError):
        fixture(kind=kind_)


@ek3
@pytest.mark.parametrize("name", ["A", "mengene_1", "Montaj/Alt-Grup/Pabuc 2", "a" * 64, "0-9 _/-"])
def test_fixture_good_name(name):
    assert fixture(name=name).name == name


@ek3
@pytest.mark.parametrize("name", ["", "a" * 65, "mengene.1", "ayna:1", "Pabuç", "a\\b", "x\ty"])
def test_fixture_bad_name(name):
    with pytest.raises(CamError):
        fixture(name=name)


@ek3
def test_fixture_empty_part_ref_rejected():
    with pytest.raises(CamError):
        fixture(part_ref="")


@ek3
def test_fixture_frame_given():
    fr = Frame((10.0, -5.0, 2.0), ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)))
    assert fixture(frame=fr).frame == fr


@ek3
@pytest.mark.parametrize("fr", [None, {"origin": [0, 0, 0], "R": [list(r) for r in I3]}, (0.0, 0.0, 0.0)])
def test_fixture_frame_must_be_frame(fr):
    with pytest.raises(CamError):
        fixture(frame=fr)


@ek3
def test_fixture_params_valid():
    p = (("acilim", 125.0), ("cene_genislik", 125.0), ("yukseklik", 40.0))
    assert fixture(kind="mengene", params=p).params == p


@ek3
@pytest.mark.parametrize(
    "p",
    [
        (("b", 1.0), ("a", 2.0)),  # sırasız
        (("a", 1.0), ("a", 2.0)),  # tekil değil
        (("a", NAN),),
        (("a", INF),),
        (("", 1.0),),  # boş ad
        ((3, 1.0),),  # ad str değil
    ],
)
def test_fixture_bad_params(p):
    with pytest.raises(CamError):
        fixture(params=p)


@ek3
def test_fixture_to_dict():
    fr = Frame((1.0, 2.0, 3.0), I3)
    f = fixture(kind="mengene", frame=fr, params=(("acilim", 100.0), ("yukseklik", 40.0)))
    d = f.to_dict()
    assert set(d) == {"name", "part_ref", "frame", "kind", "params"}
    assert d["name"] == "Mengene 1"
    assert d["part_ref"] == "mengene_125"
    assert d["frame"] == fr.to_dict()
    assert d["kind"] == "mengene"
    assert d["params"] == {"acilim": 100.0, "yukseklik": 40.0}


@ek3
def test_fixture_json_roundtrip():
    fr = Frame((0.0, 0.0, -20.0), ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))
    f = fixture(name="Ayna/3", kind="ayna", frame=fr, params=(("cap", 160.0),))
    assert M.Fixture.from_dict(jsonla(f.to_dict())) == f


@ek3
def test_fixture_from_dict_minimal():
    f = M.Fixture.from_dict({"name": "P1", "part_ref": "pabuc"})
    assert f.kind == "ozel"
    assert f.params == ()
    assert f.frame == Frame((0.0, 0.0, 0.0), I3)


@ek3
def test_fixture_from_dict_sorts_params():
    d = {"name": "M", "part_ref": "m", "kind": "mengene", "params": {"z": 3.0, "a": 1.0, "m": 2.0}}
    assert M.Fixture.from_dict(d).params == (("a", 1.0), ("m", 2.0), ("z", 3.0))


@ek3
@pytest.mark.parametrize(
    ("anahtar", "deger"),
    [("name", "a.b"), ("part_ref", ""), ("kind", "vise"), ("params", {"a": NAN})],
)
def test_fixture_from_dict_validates(anahtar, deger):
    d = fixture().to_dict()
    d[anahtar] = deger
    with pytest.raises(CamError):
        M.Fixture.from_dict(d)


# ================================================================ 4. iş mili gücü ve torku


def profil(**kw) -> MachineProfile:
    """Geçerli uydurma dik işleme merkezi profili (Fanuc)."""
    args = dict(
        name="ORNEK-DIK 1",
        controller="fanuc",
        x=AxisLimits(-300.0, 300.0),
        y=AxisLimits(-200.0, 200.0),
        z=AxisLimits(-450.0, 0.0),
        rpm_max=8000.0,
        feed_max=10000.0,
    )
    args.update(kw)
    return MachineProfile(**args)


@ek3
def test_spindle_defaults_none():
    m = profil()
    assert m.spindle_power_kw is None
    assert m.spindle_torque_nm is None
    m.validate()


@ek3
def test_spindle_values_valid():
    m = profil(spindle_power_kw=11.0, spindle_torque_nm=70.0)
    m.validate()
    assert m.spindle_power_kw == pytest.approx(11.0)
    assert m.spindle_torque_nm == pytest.approx(70.0)


@ek3
@pytest.mark.parametrize("alan", ["spindle_power_kw", "spindle_torque_nm"])
@pytest.mark.parametrize("deger", [0.0, -1.0, NAN, INF])
def test_spindle_bad_values(alan, deger):
    with pytest.raises(CamError):
        profil(**{alan: deger}).validate()


@ek3
@pytest.mark.parametrize("alan", ["spindle_power_kw", "spindle_torque_nm"])
def test_spindle_constructor_does_not_validate(alan):
    m = profil(**{alan: -1.0})  # kurucu doğrulamaz
    with pytest.raises(CamError):
        m.validate()


@ek3
def test_spindle_json():
    m = profil(spindle_power_kw=7.5, spindle_torque_nm=47.7)
    d = m.to_dict()
    assert d["spindle_power_kw"] == pytest.approx(7.5)
    assert d["spindle_torque_nm"] == pytest.approx(47.7)
    m2 = MachineProfile.from_dict(jsonla(d))
    assert m2 == m


@ek3
def test_spindle_old_json_loads():
    d = profil().to_dict()
    del d["spindle_power_kw"]
    del d["spindle_torque_nm"]
    m = MachineProfile.from_dict(jsonla(d))
    assert m.spindle_power_kw is None
    assert m.spindle_torque_nm is None


@ek3
@pytest.mark.parametrize("alan", ["spindle_power_kw", "spindle_torque_nm"])
def test_spindle_from_dict_validates(alan):
    d = profil().to_dict()
    d[alan] = 0.0
    with pytest.raises(CamError):
        MachineProfile.from_dict(d)


# ================================================================ 4b. torna profili


def torna(**kw) -> MachineProfile:
    """Geçerli uydurma torna profili (Fanuc); x kursu çap cinsinden."""
    args = dict(
        name="ORNEK-TORNA 1",
        controller="fanuc",
        kind="lathe",
        x=AxisLimits(0.0, 300.0),
        z=AxisLimits(-500.0, 0.0),
        rpm_max=4000.0,
        feed_max=6000.0,
    )
    args.update(kw)
    return MachineProfile(**args)


@ek3
def test_lathe_valid():
    torna().validate()
    torna(x=None, z=None).validate()
    torna(spindle_power_kw=15.0, spindle_torque_nm=200.0, decimals=4, rpm_min=50.0).validate()


@ek3
@pytest.mark.parametrize("controller", ["grbl", "haas", "sinumerik", "heidenhain"])
def test_lathe_only_fanuc(controller):
    with pytest.raises(CamError):
        torna(controller=controller, program_no_range=(1, 9999)).validate()


@ek3
@pytest.mark.parametrize(
    "kw",
    [
        {"y": AxisLimits(-50.0, 50.0)},
        {"tool_change_z": -10.0},
        {"presets": {"G54": 1}},
    ],
)
def test_lathe_mill_only_fields_rejected(kw):
    with pytest.raises(CamError):
        torna(**kw).validate()


@ek3
def test_lathe_kinematics_rejected():
    kin = M.Kinematics(rotary=(M.RotaryAxis("C", "masa", (0.0, 0.0, 1.0)),))
    with pytest.raises(CamError):
        torna(kinematics=kin).validate()


@ek3
@pytest.mark.parametrize("kw", [{"x": None}, {"z": None}])
def test_lathe_x_z_together(kw):
    with pytest.raises(CamError):
        torna(**kw).validate()


@ek3
@pytest.mark.parametrize(
    "kw",
    [
        {"rpm_max": -1.0},
        {"feed_max": 0.0},
        {"decimals": 5},
        {"program_no_range": (1, 10000)},
        {"spindle_power_kw": 0.0},
        {"x": AxisLimits(300.0, 0.0)},
    ],
)
def test_lathe_common_rules(kw):
    with pytest.raises(CamError):
        torna(**kw).validate()


@ek3
def test_lathe_json_roundtrip():
    m = torna(spindle_power_kw=11.0)
    m2 = MachineProfile.from_dict(jsonla(m.to_dict()))
    assert m2 == m
    assert m2.kind == "lathe"


@ek3
@pytest.mark.parametrize(("key", "value"), [("controller", "haas"), ("tool_change_z", -5.0), ("x", None)])
def test_lathe_from_dict_validates(key, value):
    d = torna().to_dict()
    d[key] = value
    with pytest.raises(CamError):
        MachineProfile.from_dict(d)


@ek3
@pytest.mark.parametrize("kind_", ["torna", "", "router", "LATHE"])
def test_other_kinds_still_rejected(kind_):
    with pytest.raises(CamError):
        torna(kind=kind_).validate()
