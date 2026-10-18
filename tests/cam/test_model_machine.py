"""Tezgâh profili ve kinematik arayüz eki testleri (SPEC 30, SPEC 31, SPEC 41 arayüzü):
AxisLimits, MachineProfile, RotaryAxis, Kinematics.

Testler yalnızca onaylanan davranış sözleşmesinden, specs-taslak/30-tezgah-profili.md'deki
arayüz önerisinden ve arayuz/cok-eksen-arayuz-onerisi.md'den yazıldı; uygulama kodu okunmadı.

Davranış:
- RotaryAxis(name A/B/C, carrier masa/kafa, u birim, pivot; min ve max ikisi birden None ya da min < max).
- Kinematics: en çok 2 döner eksen, adlar tekil, eksenler paralel değil, spindle birim, gauge.
- AxisLimits ve MachineProfile frozen. Kurucu doğrulamaz; validate() ve from_dict doğrular.
- controller grbl / fanuc / haas / sinumerik / heidenhain; kind "lathe" şimdilik CamError.
- rpm_max ve feed_max kw_only ve zorunlu.
- program_no üst sınırı fanuc'ta 9999, haas'ta 99999. decimals 3 ya da 4.
- presets yalnız heidenhain'de. tool_change_z, Z kursunun içinde olmalı.
"""

from __future__ import annotations

import dataclasses
import json
import math

import numpy as np
import pytest

from cam.model import AxisLimits, CamError, Kinematics, MachineProfile, RotaryAxis

CONTROLLERS = ["grbl", "fanuc", "haas", "sinumerik", "heidenhain"]


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


def ac_kinematik() -> Kinematics:
    """Masa-masa A/C kinematiği (uydurma)."""
    return Kinematics(
        rotary=(
            RotaryAxis("A", "masa", (1.0, 0.0, 0.0), pivot=(0.0, 0.0, -100.0), min=-30.0, max=110.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0)),
        ),
        spindle=(0.0, 0.0, 1.0),
        gauge=(0.0, 0.0, 150.0),
    )


def json_gidis_donus(d: dict) -> dict:
    return json.loads(json.dumps(d))


# ================================================================ RotaryAxis


@pytest.mark.parametrize("name", ["A", "B", "C"])
@pytest.mark.parametrize("carrier", ["masa", "kafa"])
def test_rotary_valid(name, carrier):
    a = RotaryAxis(name, carrier, (0.0, 1.0, 0.0))
    assert a.min is None and a.max is None
    assert np.allclose(a.pivot, (0.0, 0.0, 0.0))


def test_rotary_limits():
    a = RotaryAxis("B", "kafa", (0.0, 1.0, 0.0), pivot=(0.0, 0.0, 50.0), min=-120.0, max=120.0)
    assert (a.min, a.max) == (-120.0, 120.0)


@pytest.mark.parametrize("name", ["D", "X", "a", "", "AB"])
def test_rotary_bad_name(name):
    with pytest.raises(CamError):
        RotaryAxis(name, "masa", (1.0, 0.0, 0.0))


@pytest.mark.parametrize("carrier", ["table", "head", "Masa", ""])
def test_rotary_bad_carrier(carrier):
    with pytest.raises(CamError):
        RotaryAxis("A", carrier, (1.0, 0.0, 0.0))


@pytest.mark.parametrize(
    "u", [(2.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 0.0), (math.nan, 0.0, 0.0), (1.0, 0.0)]
)
def test_rotary_bad_u(u):
    with pytest.raises(CamError):
        RotaryAxis("A", "masa", u)


def test_rotary_bad_pivot():
    with pytest.raises(CamError):
        RotaryAxis("A", "masa", (1.0, 0.0, 0.0), pivot=(0.0, math.inf, 0.0))


@pytest.mark.parametrize(
    ("lo", "hi"),
    [(-30.0, None), (None, 110.0), (10.0, 10.0), (110.0, -30.0), (math.nan, 10.0), (0.0, math.inf)],
)
def test_rotary_bad_limits(lo, hi):
    with pytest.raises(CamError):
        RotaryAxis("A", "masa", (1.0, 0.0, 0.0), min=lo, max=hi)


def test_rotary_dict_roundtrip():
    a = RotaryAxis("A", "masa", (1.0, 0.0, 0.0), pivot=(0.0, 0.0, -100.0), min=-30.0, max=110.0)
    a2 = RotaryAxis.from_dict(json_gidis_donus(a.to_dict()))
    assert a2.to_dict() == a.to_dict()
    assert a2.name == "A" and a2.carrier == "masa"
    assert np.allclose(a2.u, a.u) and np.allclose(a2.pivot, a.pivot)


def test_rotary_from_dict_rejects_bad_value():
    d = RotaryAxis("A", "masa", (1.0, 0.0, 0.0)).to_dict()
    d["name"] = "Q"
    with pytest.raises(CamError):
        RotaryAxis.from_dict(d)


# ================================================================ Kinematics


def test_kinematics_default_three_axis():
    k = Kinematics()
    assert tuple(k.rotary) == ()
    assert np.allclose(k.spindle, (0.0, 0.0, 1.0))
    assert np.allclose(k.gauge, (0.0, 0.0, 0.0))


def test_kinematics_one_and_two_axes():
    Kinematics(rotary=(RotaryAxis("A", "masa", (1.0, 0.0, 0.0)),))
    k = ac_kinematik()
    assert [a.name for a in k.rotary] == ["A", "C"]


def test_kinematics_head_table():
    # kafa B + masa C
    Kinematics(rotary=(RotaryAxis("C", "masa", (0.0, 0.0, 1.0)), RotaryAxis("B", "kafa", (0.0, 1.0, 0.0))))


def test_kinematics_more_than_two_rejected():
    with pytest.raises(CamError):
        Kinematics(
            rotary=(
                RotaryAxis("A", "masa", (1.0, 0.0, 0.0)),
                RotaryAxis("B", "masa", (0.0, 1.0, 0.0)),
                RotaryAxis("C", "masa", (0.0, 0.0, 1.0)),
            )
        )


def test_kinematics_duplicate_names_rejected():
    with pytest.raises(CamError):
        Kinematics(
            rotary=(RotaryAxis("A", "masa", (1.0, 0.0, 0.0)), RotaryAxis("A", "kafa", (0.0, 1.0, 0.0)))
        )


@pytest.mark.parametrize("u2", [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)])
def test_kinematics_parallel_axes_rejected(u2):
    with pytest.raises(CamError):
        Kinematics(rotary=(RotaryAxis("A", "masa", (1.0, 0.0, 0.0)), RotaryAxis("B", "kafa", u2)))


def test_kinematics_nutating_axes_accepted():
    # 45° eğik (nutasyonlu) B ekseni ile C: paralel değil
    s = math.sqrt(0.5)
    Kinematics(rotary=(RotaryAxis("B", "kafa", (0.0, s, s)), RotaryAxis("C", "kafa", (0.0, 0.0, 1.0))))


@pytest.mark.parametrize("spindle", [(0.0, 0.0, 2.0), (0.0, 0.0, 0.0), (0.0, math.nan, 1.0)])
def test_kinematics_bad_spindle(spindle):
    with pytest.raises(CamError):
        Kinematics(spindle=spindle)


def test_kinematics_bad_gauge():
    with pytest.raises(CamError):
        Kinematics(gauge=(0.0, 0.0, math.nan))


def test_kinematics_dict_roundtrip():
    k = ac_kinematik()
    k2 = Kinematics.from_dict(json_gidis_donus(k.to_dict()))
    assert k2.to_dict() == k.to_dict()
    assert [a.name for a in k2.rotary] == ["A", "C"]
    assert np.allclose(k2.gauge, (0.0, 0.0, 150.0))


def test_kinematics_from_dict_rejects_parallel():
    d = ac_kinematik().to_dict()
    d["rotary"][1]["u"] = [1.0, 0.0, 0.0]
    with pytest.raises(CamError):
        Kinematics.from_dict(d)


# ================================================================ AxisLimits, MachineProfile: yapı


def test_axis_limits_frozen():
    lim = AxisLimits(-10.0, 10.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        lim.min = 0.0


def test_profile_frozen():
    m = profil()
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.rpm_max = 1.0


def test_rpm_max_and_feed_max_required():
    with pytest.raises(TypeError):
        MachineProfile(name="A", controller="grbl", feed_max=1000.0)
    with pytest.raises(TypeError):
        MachineProfile(name="A", controller="grbl", rpm_max=1000.0)


def test_rpm_max_feed_max_keyword_only():
    fields = {f.name: f for f in dataclasses.fields(MachineProfile)}
    assert fields["rpm_max"].kw_only
    assert fields["feed_max"].kw_only


def test_defaults():
    m = MachineProfile(name="A", controller="grbl", rpm_max=24000.0, feed_max=5000.0)
    assert m.kind == "mill"
    assert m.x is None and m.y is None and m.z is None
    assert m.rpm_min == 0.0
    assert m.rapid is None and m.tool_slots is None and m.tool_change_z is None
    assert tuple(m.program_no_range) == (1, 9999)
    assert m.decimals == 3
    assert m.verified is False
    assert m.presets is None
    assert m.kinematics is None
    m.validate()


def test_constructor_does_not_validate():
    # kurucu doğrulamaz: hatalı değerlerle de nesne kurulur, validate() reddeder
    m = MachineProfile(
        name="küçük ad", controller="yok", kind="lathe", rpm_max=-1.0, feed_max=0.0, decimals=7
    )
    with pytest.raises(CamError):
        m.validate()
    lim = AxisLimits(10.0, -10.0)
    assert lim.min == 10.0


def test_valid_profile():
    profil().validate()
    profil(
        rpm_min=100.0,
        rapid=(30000.0, 30000.0, 24000.0),
        tool_slots=24,
        tool_change_z=-10.0,
        program_no_range=(1, 7999),
        decimals=4,
        verified=True,
        kinematics=ac_kinematik(),
    ).validate()


@pytest.mark.parametrize("controller", CONTROLLERS)
def test_all_controllers_accepted(controller):
    profil(controller=controller, program_no_range=(1, 9999)).validate()


# ================================================================ validate kuralları


@pytest.mark.parametrize("name", ["", "küçük", "ornek", "DİK", "TEZGÂH", "A" * 33, "A/B", "A.B", "A(B)"])
def test_bad_name(name):
    with pytest.raises(CamError):
        profil(name=name).validate()


@pytest.mark.parametrize("name", ["A", "ORNEK-DIK 1", "HAAS_VF2", "A" * 32, "0123"])
def test_good_name(name):
    profil(name=name).validate()


@pytest.mark.parametrize("controller", ["", "FANUC", "linuxcnc", "mach3", "siemens"])
def test_bad_controller(controller):
    with pytest.raises(CamError):
        profil(controller=controller).validate()


@pytest.mark.parametrize("kind", ["lathe", "torna", "", "router"])
def test_bad_kind(kind):
    with pytest.raises(CamError):
        profil(kind=kind).validate()


@pytest.mark.parametrize("axis", ["x", "y", "z"])
@pytest.mark.parametrize(("lo", "hi"), [(0.0, 0.0), (10.0, -10.0), (math.nan, 0.0), (-math.inf, 0.0)])
def test_bad_axis_limits(axis, lo, hi):
    with pytest.raises(CamError):
        profil(**{axis: AxisLimits(lo, hi)}).validate()


@pytest.mark.parametrize(
    "kw",
    [
        {"rpm_max": 0.0},
        {"rpm_max": -100.0},
        {"rpm_max": math.nan},
        {"rpm_max": math.inf},
        {"rpm_min": -1.0},
        {"rpm_min": 8000.0},
        {"rpm_min": 9000.0},
        {"feed_max": 0.0},
        {"feed_max": -5.0},
        {"feed_max": math.nan},
    ],
)
def test_bad_rpm_feed(kw):
    with pytest.raises(CamError):
        profil(**kw).validate()


@pytest.mark.parametrize("rapid", [(0.0, 1.0, 1.0), (1.0, -1.0, 1.0), (1.0, 1.0, math.nan)])
def test_bad_rapid(rapid):
    with pytest.raises(CamError):
        profil(rapid=rapid).validate()


@pytest.mark.parametrize("slots", [0, -1])
def test_bad_tool_slots(slots):
    with pytest.raises(CamError):
        profil(tool_slots=slots).validate()


@pytest.mark.parametrize("tcz", [-450.0, -200.0, 0.0])
def test_tool_change_z_inside(tcz):
    profil(tool_change_z=tcz).validate()


@pytest.mark.parametrize("tcz", [10.0, -451.0, math.nan])
def test_tool_change_z_outside(tcz):
    with pytest.raises(CamError):
        profil(tool_change_z=tcz).validate()


def test_tool_change_z_without_z_limits():
    with pytest.raises(CamError):
        profil(z=None, tool_change_z=-10.0).validate()


@pytest.mark.parametrize("rng", [(0, 10), (10, 5), (-1, 10)])
def test_bad_program_no_range(rng):
    with pytest.raises(CamError):
        profil(program_no_range=rng).validate()


@pytest.mark.parametrize(("controller", "hi"), [("fanuc", 9999), ("haas", 99999)])
def test_program_no_upper_limit_ok(controller, hi):
    profil(controller=controller, program_no_range=(1, hi)).validate()
    profil(controller=controller, program_no_range=(hi, hi)).validate()


@pytest.mark.parametrize(("controller", "hi"), [("fanuc", 10000), ("haas", 100000)])
def test_program_no_upper_limit_exceeded(controller, hi):
    with pytest.raises(CamError):
        profil(controller=controller, program_no_range=(1, hi)).validate()


@pytest.mark.parametrize("decimals", [3, 4])
def test_good_decimals(decimals):
    profil(decimals=decimals).validate()


@pytest.mark.parametrize("decimals", [0, 2, 5, 6])
def test_bad_decimals(decimals):
    with pytest.raises(CamError):
        profil(decimals=decimals).validate()


def test_presets_heidenhain_accepted():
    profil(controller="heidenhain", presets={"G54": 1, "G55": 2}).validate()


@pytest.mark.parametrize("controller", ["grbl", "fanuc", "haas", "sinumerik"])
def test_presets_other_controllers_rejected(controller):
    with pytest.raises(CamError):
        profil(controller=controller, presets={"G54": 1}).validate()


def test_bad_kinematics_type_rejected():
    with pytest.raises(CamError):
        profil(kinematics={"rotary": []}).validate()


# ================================================================ sözlük


def test_to_dict_is_json():
    d = profil(kinematics=ac_kinematik(), rapid=(30000.0, 30000.0, 24000.0)).to_dict()
    json.dumps(d)


@pytest.mark.parametrize(
    "m",
    [
        pytest.param(lambda: profil(), id="fanuc"),
        pytest.param(
            lambda: profil(
                rpm_min=100.0,
                rapid=(30000.0, 30000.0, 24000.0),
                tool_slots=24,
                tool_change_z=-10.0,
                program_no_range=(1, 7999),
                decimals=4,
                verified=True,
                kinematics=ac_kinematik(),
            ),
            id="tam",
        ),
        pytest.param(lambda: profil(controller="heidenhain", presets={"G54": 1, "G55": 2}), id="heidenhain"),
        pytest.param(
            lambda: MachineProfile(name="GRBL", controller="grbl", rpm_max=24000.0, feed_max=5000.0),
            id="grbl",
        ),
    ],
)
def test_profile_roundtrip(m):
    m = m()
    m2 = MachineProfile.from_dict(json_gidis_donus(m.to_dict()))
    assert m2 == m
    assert m2.to_dict() == m.to_dict()
    # iki kayıt aynı metni verir
    assert json.dumps(m2.to_dict(), sort_keys=True) == json.dumps(m.to_dict(), sort_keys=True)


def test_from_dict_unknown_key_rejected():
    d = profil().to_dict()
    d["bilinmeyen"] = 1
    with pytest.raises(CamError):
        MachineProfile.from_dict(d)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("controller", "mach3"),
        ("kind", "lathe"),
        ("name", "küçük"),
        ("decimals", 5),
        ("rpm_max", -1.0),
        ("feed_max", 0.0),
        ("program_no_range", [1, 10000]),
        ("presets", {"G54": 1}),
        ("tool_change_z", 50.0),
    ],
)
def test_from_dict_validates(key, value):
    d = profil().to_dict()
    d[key] = value
    with pytest.raises(CamError):
        MachineProfile.from_dict(d)


def test_from_dict_bad_kinematics_rejected():
    d = profil(kinematics=ac_kinematik()).to_dict()
    d["kinematics"]["rotary"][0]["carrier"] = "table"
    with pytest.raises(CamError):
        MachineProfile.from_dict(d)


def test_from_dict_bad_axis_limits_rejected():
    d = profil().to_dict()
    d["z"] = {"min": 0.0, "max": -450.0}
    with pytest.raises(CamError):
        MachineProfile.from_dict(d)
