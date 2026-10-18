"""CAM Ek 4 (B0) arayüz testleri: torna-freze tezgâhı, silindir stokta frezeleme, 5 eksen yol bilgisi.

Testler yalnızca B0 metninden (spec-taslak/dalga-6/B0-cam-ek4.md, kabul kriterleri K1–K8) ve
`cam/model.py`'deki sınıf / alan imzalarından yazıldı; Ek 4 uygulama gövdeleri okunmadı.
Tezgâh adları uydurmadır (ORNEK-NTX, ORNEK-DMU); gerçek parametre yok.

Geçersiz girdinin hangi anda reddedildiği (kurucu mu, validate mi) metinde her sınıf için yazılı
olmadığından, ret beklenen testlerde kurma ve doğrulama aynı `pytest.raises` bloğundadır.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from cam.gcode import FANUC, GRBL, write
from cam.model import (
    AxisLimits,
    CamError,
    CAxis,
    FeedMode,
    Frame,
    Kinematics,
    LatheTool,
    LatheToolKind,
    MachineProfile,
    Move,
    MoveType,
    MultiAxisPost,
    PathMeta,
    Plane,
    RotaryAxis,
    Tool,
    ToolKind,
    Toolpath,
    Turret,
    TurretStation,
)

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
NAN, INF = float("nan"), float("inf")
I3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
EGIK = (0.6, 0.0, 0.8)  # birim, +z dışı takım ekseni
PROFIL_KLASORU = Path(__file__).resolve().parents[2] / "cam" / "post" / "profiles"

STRATEGIES = ["kaba", "yari_ince", "ince", "yanak", "delik", "dis", "kontur", "alin", "kanal"]
AXIS_MODES = ["3", "3+2", "5", "torna", "c_indeks", "polar", "silindirik"]
TCP = ["traori", "m128", "tcpm", "g43.4", "g43.5", "yok"]
SWIVEL = ["cycle800", "plane_spatial", "g68.2", "yok"]
# Dil uyumu tablosu (B0, MultiAxisPost): dil → (izinli tcp, izinli swivel)
DIL_UYUMU = {
    "sinumerik": ({"traori", "yok"}, {"cycle800", "yok"}),
    "heidenhain": ({"m128", "tcpm", "yok"}, {"plane_spatial", "yok"}),
    "fanuc": ({"g43.4", "g43.5", "yok"}, {"g68.2", "yok"}),
    "haas": ({"g43.4", "g43.5", "yok"}, {"g68.2", "yok"}),
    "grbl": ({"yok"}, {"yok"}),
}


def jsonla(d: dict) -> dict:
    """JSON metnine yazıp geri okur (gidiş-dönüş gerçek JSON üzerinden olsun)."""
    return json.loads(json.dumps(d))


# ---------------------------------------------------------------- takımlar, yollar


def freze() -> Tool:
    return Tool(id=1, name="freze6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)


def torna_takimi() -> LatheTool:
    return LatheTool(id=11, name="CNMG", kind=LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=95.0, eps_r=80.0)


def kartezyen_yol(moves=None, **kw) -> Toolpath:
    """XY'de kare parçası; freze, kartezyen."""
    if moves is None:
        moves = [
            Move(G1, (0.0, 0.0, -1.0), feed=200.0),
            Move(G1, (10.0, 0.0, -1.0), feed=500.0),
            Move(G1, (10.0, 10.0, -1.0), feed=500.0),
            Move(G0, (10.0, 10.0, 5.0)),
        ]
    args = dict(name="kare", tool=freze(), start=(0.0, 0.0, 5.0), moves=moves, rpm=10000.0)
    args.update(kw)
    return Toolpath(**args)


def polar_yol(moves=None, **kw) -> Toolpath:
    """Alın frezeleme: parça çerçevesinde (x, y, z), coord = polar."""
    if moves is None:
        moves = [
            Move(G1, (20.0, 0.0, -1.0), feed=200.0),
            Move(G1, (0.0, 20.0, -1.0), feed=400.0),
            Move(G1, (-20.0, 0.0, -1.0), feed=400.0),
        ]
    args = dict(name="alin", tool=freze(), start=(20.0, 0.0, 2.0), moves=moves, rpm=6000.0, coord="polar")
    args.update(kw)
    return Toolpath(**args)


def silindirik_yol(moves=None, **kw) -> Toolpath:
    """Silindir yüzeyinde kanal: nokta = (s, z, r), r_ref = 30 mm."""
    if moves is None:
        moves = [
            Move(G1, (0.0, -10.0, 28.0), feed=150.0),
            Move(G1, (47.1, -10.0, 28.0), feed=300.0),
            Move(G1, (47.1, -25.0, 28.0), feed=300.0),
        ]
    args = dict(
        name="kanal",
        tool=freze(),
        start=(0.0, -10.0, 32.0),
        moves=moves,
        rpm=6000.0,
        coord="silindirik",
        cyl_r=30.0,
    )
    args.update(kw)
    return Toolpath(**args)


def torna_yolu(moves=None, **kw) -> Toolpath:
    """Torna yolu: LatheTool, ZX, y = 0, devir başı ilerleme."""
    if moves is None:
        moves = [Move(G1, (20.0, 0.0, -30.0), feed=0.2), Move(G1, (25.0, 0.0, -30.0), feed=0.2)]
    args = dict(
        name="dis",
        tool=torna_takimi(),
        start=(20.0, 0.0, 5.0),
        moves=moves,
        rpm=3000.0,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
    )
    args.update(kw)
    return Toolpath(**args)


def egik_yol(**kw) -> Toolpath:
    """Eş zamanlı 5 eksen benzeri yol: her harekette +z dışı takım ekseni."""
    moves = [
        Move(G1, (0.0, 0.0, -1.0), feed=200.0, axis=EGIK),
        Move(G1, (10.0, 0.0, -1.0), feed=500.0, axis=EGIK),
    ]
    return kartezyen_yol(moves, **kw)


# ---------------------------------------------------------------- profiller


def ac_kinematik() -> Kinematics:
    """Masa-masa A/C (uydurma DMU benzeri)."""
    return Kinematics(
        rotary=(
            RotaryAxis("A", "masa", (1.0, 0.0, 0.0), min=-30.0, max=110.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0)),
        )
    )


def b_kafa() -> Kinematics:
    """NTX tipi B eksenli freze kafası."""
    return Kinematics(rotary=(RotaryAxis("B", "kafa", (0.0, 1.0, 0.0), min=-30.0, max=210.0),))


def freze_profili(controller: str = "sinumerik", **kw) -> MachineProfile:
    args = dict(
        name="ORNEK-DMU",
        controller=controller,
        x=AxisLimits(-300.0, 300.0),
        y=AxisLimits(-250.0, 250.0),
        z=AxisLimits(-500.0, 0.0),
        rpm_max=18000.0,
        feed_max=20000.0,
    )
    args.update(kw)
    return MachineProfile(**args)


def taretler() -> tuple[Turret, ...]:
    """İki taret: üstte canlı radyal + eksenel istasyon, altta bir canlı istasyon."""
    return (
        Turret(
            "UST",
            (
                TurretStation(1, live=True, direction="radyal"),
                TurretStation(2),
                TurretStation(3, live=True, direction="eksenel"),
                TurretStation(4, direction="eksenel"),
            ),
            live_rpm_max=12000.0,
        ),
        Turret("ALT", (TurretStation(1), TurretStation(2, live=True)), live_rpm_max=6000.0),
    )


def ntx(controller: str = "sinumerik", **kw) -> MachineProfile:
    """Geçerli uydurma torna-freze profili (C, Y, iki taret, B kafa); X kursu çap."""
    args = dict(
        name="ORNEK-NTX",
        controller=controller,
        kind="millturn",
        x=AxisLimits(0.0, 660.0),
        y=AxisLimits(-105.0, 105.0),
        z=AxisLimits(-1500.0, 0.0),
        rpm_max=4000.0,
        feed_max=10000.0,
        c_axis=CAxis(index_step=0.001, rpm_max=2000.0, m_on="M45", m_off="M46"),
        turrets=taretler(),
        kinematics=b_kafa(),
    )
    args.update(kw)
    return MachineProfile(**args)


def torna_profili(**kw) -> MachineProfile:
    args = dict(
        name="ORNEK-TORNA",
        controller="fanuc",
        kind="lathe",
        x=AxisLimits(0.0, 300.0),
        z=AxisLimits(-500.0, 0.0),
        rpm_max=4000.0,
        feed_max=6000.0,
    )
    args.update(kw)
    return MachineProfile(**args)


# ================================================================ K1 geriye uyum


@pytest.mark.parametrize("dosya", sorted(PROFIL_KLASORU.glob("*.json")), ids=lambda p: p.stem)
def test_k1_existing_profiles_load(dosya):
    m = MachineProfile.from_dict(json.loads(dosya.read_text(encoding="utf-8")))
    m.validate()
    assert m.c_axis is None
    assert tuple(m.turrets) == ()
    assert m.multiaxis is None


def test_k1_profile_dir_not_empty():
    assert list(PROFIL_KLASORU.glob("*.json"))


def test_k1_defaults():
    m = freze_profili()
    assert m.c_axis is None
    assert m.turrets == ()
    assert m.multiaxis is None
    m.validate()
    tp = kartezyen_yol()
    assert tp.coord == "kartezyen"
    assert tp.cyl_r is None
    assert tp.station is None
    assert tp.meta is None
    assert all(mv.c is None for mv in tp.moves)
    tp.validate()


def test_k1_profile_to_dict_has_new_keys():
    d = freze_profili().to_dict()
    assert d["c_axis"] is None
    assert list(d["turrets"]) == []
    assert d["multiaxis"] is None
    assert MachineProfile.from_dict(jsonla(d)) == freze_profili()


def test_k1_profile_old_dict_loads():
    d = freze_profili().to_dict()
    for k in ("c_axis", "turrets", "multiaxis"):
        del d[k]
    m = MachineProfile.from_dict(jsonla(d))
    assert m == freze_profili()


def test_k1_toolpath_to_dict_has_new_keys():
    d = kartezyen_yol().to_dict()
    assert d["coord"] == "kartezyen"
    assert d["cyl_r"] is None
    assert d["station"] is None
    assert d["meta"] is None
    assert all("c" in m and m["c"] is None for m in d["moves"])
    tp = Toolpath.from_dict(jsonla(d))
    assert tp.to_dict() == d


def test_k1_toolpath_old_dict_loads():
    d = kartezyen_yol().to_dict()
    for k in ("coord", "cyl_r", "station", "meta"):
        del d[k]
    for m in d["moves"]:
        del m["c"]
    tp = Toolpath.from_dict(jsonla(d))
    assert tp.coord == "kartezyen"
    assert tp.cyl_r is None and tp.station is None and tp.meta is None
    assert all(mv.c is None for mv in tp.moves)
    assert tp.to_dict() == kartezyen_yol().to_dict()


def test_k1_lathe_path_still_valid():
    torna_yolu().validate()


# ================================================================ K2 CAxis, TurretStation, Turret


def test_k2_caxis_defaults():
    c = CAxis()
    assert c.continuous is True
    assert c.index_step == pytest.approx(0.001)
    assert c.rpm_max is None and c.m_on is None and c.m_off is None


def test_k2_caxis_positioning_only():
    assert CAxis(continuous=False, index_step=1.0).continuous is False


@pytest.mark.parametrize("step", [0.0, -0.001, NAN, INF])
def test_k2_caxis_bad_index_step(step):
    with pytest.raises(CamError):
        ntx(c_axis=CAxis(index_step=step)).validate()


@pytest.mark.parametrize("rpm", [NAN, INF])
def test_k7_caxis_rpm_max_finite(rpm):
    with pytest.raises(CamError):
        ntx(c_axis=CAxis(rpm_max=rpm)).validate()


def test_k2_station_defaults():
    s = TurretStation(5)
    assert s.no == 5
    assert s.live is False
    assert s.direction == "radyal"


@pytest.mark.parametrize("direction", ["radyal", "eksenel"])
@pytest.mark.parametrize("live", [False, True])
def test_k2_station_valid(direction, live):
    s = TurretStation(2, live=live, direction=direction)
    assert s.direction == direction  # canlı olmayanda da yön saklanır


@pytest.mark.parametrize("no", [0, -1])
def test_k2_station_bad_no(no):
    with pytest.raises(CamError):
        TurretStation(no)


@pytest.mark.parametrize("direction", ["", "radial", "axial", "Radyal", "teğet"])
def test_k2_station_bad_direction(direction):
    with pytest.raises(CamError):
        TurretStation(1, direction=direction)


def test_k2_turret_valid():
    t = Turret("T1", (TurretStation(1), TurretStation(2, live=True)), live_rpm_max=8000.0)
    assert len(t.stations) == 2
    assert Turret("T2", (TurretStation(1), TurretStation(2))).live_rpm_max is None


def test_k2_turret_duplicate_station_no():
    with pytest.raises(CamError):
        Turret("T1", (TurretStation(1), TurretStation(1, live=True)), live_rpm_max=8000.0)


def test_k2_turret_live_without_rpm():
    with pytest.raises(CamError):
        Turret("T1", (TurretStation(1), TurretStation(2, live=True)))


@pytest.mark.parametrize("rpm", [0.0, -100.0, NAN, INF])
def test_k2_turret_live_bad_rpm(rpm):
    with pytest.raises(CamError):
        Turret("T1", (TurretStation(1, live=True),), live_rpm_max=rpm)


def test_k2_parts_roundtrip():
    c = CAxis(continuous=False, index_step=0.5, rpm_max=100.0, m_on="M45", m_off="M46")
    assert CAxis.from_dict(jsonla(c.to_dict())) == c
    s = TurretStation(3, live=True, direction="eksenel")
    assert TurretStation.from_dict(jsonla(s.to_dict())) == s
    t = taretler()[0]
    assert Turret.from_dict(jsonla(t.to_dict())) == t


# ================================================================ K3 millturn profili


@pytest.mark.parametrize("controller", ["sinumerik", "fanuc"])
def test_k3_ntx_valid_roundtrip(controller):
    m = ntx(controller)
    m.validate()
    m2 = MachineProfile.from_dict(jsonla(m.to_dict()))
    assert m2 == m
    assert m2.kind == "millturn"
    assert m2.c_axis == m.c_axis
    assert tuple(m2.turrets) == m.turrets


def test_k3_ntx_minimal_valid():
    # Y yok, kinematik yok, X/Z kursu yok: tek taret, tek canlı istasyon
    ntx(
        y=None,
        x=None,
        z=None,
        kinematics=None,
        c_axis=CAxis(),
        turrets=(Turret("T", (TurretStation(1, live=True),), live_rpm_max=5000.0),),
    ).validate()


def test_k3_millturn_requires_c_axis():
    with pytest.raises(CamError):
        ntx(c_axis=None).validate()


def test_k3_millturn_requires_turret():
    with pytest.raises(CamError):
        ntx(turrets=()).validate()


def test_k3_millturn_requires_live_station():
    olu = (Turret("T", (TurretStation(1), TurretStation(2, direction="eksenel"))),)
    with pytest.raises(CamError):
        ntx(turrets=olu).validate()


@pytest.mark.parametrize("controller", ["grbl", "haas", "heidenhain"])
def test_k3_millturn_controller(controller):
    with pytest.raises(CamError):
        ntx(controller).validate()


@pytest.mark.parametrize(
    "rotary",
    [
        pytest.param((RotaryAxis("B", "masa", (0.0, 1.0, 0.0)),), id="B-masa"),
        pytest.param((RotaryAxis("A", "kafa", (1.0, 0.0, 0.0)),), id="A-kafa"),
        pytest.param((RotaryAxis("C", "kafa", (0.0, 0.0, 1.0)),), id="C-kafa"),
        pytest.param((RotaryAxis("C", "masa", (0.0, 0.0, 1.0)),), id="C-masa"),
        pytest.param(
            (RotaryAxis("B", "kafa", (0.0, 1.0, 0.0)), RotaryAxis("C", "masa", (0.0, 0.0, 1.0))),
            id="B-kafa+C-masa",
        ),
    ],
)
def test_k3_millturn_only_b_head(rotary):
    with pytest.raises(CamError):
        ntx(kinematics=Kinematics(rotary=rotary)).validate()


@pytest.mark.parametrize("kw", [{"x": None}, {"z": None}])
def test_k3_millturn_x_z_together(kw):
    with pytest.raises(CamError):
        ntx(**kw).validate()


def test_k3_millturn_y_free():
    ntx(y=None).validate()
    ntx(y=AxisLimits(-50.0, 50.0)).validate()


def test_k3_mill_rejects_c_axis():
    with pytest.raises(CamError):
        freze_profili(c_axis=CAxis()).validate()


def test_k3_mill_rejects_turrets():
    with pytest.raises(CamError):
        freze_profili(turrets=taretler()).validate()


def test_k3_lathe_rules_unchanged():
    torna_profili().validate()
    for kw in ({"controller": "sinumerik"}, {"y": AxisLimits(-50.0, 50.0)}, {"kinematics": b_kafa()}):
        with pytest.raises(CamError):
            torna_profili(**kw).validate()


@pytest.mark.parametrize("kind", ["", "torna-freze", "MILLTURN", "mill_turn"])
def test_k3_unknown_kind(kind):
    with pytest.raises(CamError):
        ntx(kind=kind).validate()


@pytest.mark.parametrize(
    ("key", "value"),
    [("c_axis", None), ("turrets", []), ("controller", "haas"), ("x", None)],
)
def test_k3_from_dict_validates(key, value):
    d = ntx().to_dict()
    d[key] = value
    with pytest.raises(CamError):
        MachineProfile.from_dict(d)


# ================================================================ K4 MultiAxisPost


def test_k4_multiaxis_defaults():
    p = MultiAxisPost("traori", "cycle800")
    assert p.vector is False
    assert p.swivel_data is None


@pytest.mark.parametrize(("tcp", "swivel"), [("TRAORI", "yok"), ("yok", "cycle"), ("rtcp", "yok"), ("", "")])
def test_k4_unknown_modes(tcp, swivel):
    with pytest.raises(CamError):
        freze_profili(kinematics=ac_kinematik(), multiaxis=MultiAxisPost(tcp, swivel)).validate()


@pytest.mark.parametrize(("tcp", "swivel"), list(itertools.product(TCP, SWIVEL)))
@pytest.mark.parametrize("controller", list(DIL_UYUMU))
def test_k4_dialect_table_mill(controller, tcp, swivel):
    m = freze_profili(controller, kinematics=ac_kinematik(), multiaxis=MultiAxisPost(tcp, swivel))
    izinli_tcp, izinli_swivel = DIL_UYUMU[controller]
    if tcp in izinli_tcp and swivel in izinli_swivel:
        m.validate()
    else:
        with pytest.raises(CamError):
            m.validate()


@pytest.mark.parametrize(("tcp", "swivel"), list(itertools.product(TCP, SWIVEL)))
@pytest.mark.parametrize("controller", ["sinumerik", "fanuc"])
def test_k4_dialect_table_millturn(controller, tcp, swivel):
    m = ntx(controller, multiaxis=MultiAxisPost(tcp, swivel))
    izinli_tcp, izinli_swivel = DIL_UYUMU[controller]
    if tcp in izinli_tcp and swivel in izinli_swivel:
        m.validate()
    else:
        with pytest.raises(CamError):
            m.validate()


def test_k4_millturn_multiaxis_without_kinematics():
    # multiaxis millturn'de döner eksen olmadan da verilebilir
    ntx("fanuc", kinematics=None, multiaxis=MultiAxisPost("g43.4", "g68.2")).validate()


def test_k4_mill_without_rotary_rejects_multiaxis():
    with pytest.raises(CamError):
        freze_profili(multiaxis=MultiAxisPost("yok", "yok")).validate()
    with pytest.raises(CamError):
        freze_profili(kinematics=Kinematics(), multiaxis=MultiAxisPost("yok", "yok")).validate()


def test_k4_vector_and_swivel_data_roundtrip():
    p = MultiAxisPost("traori", "cycle800", vector=True, swivel_data="_TC")
    assert MultiAxisPost.from_dict(jsonla(p.to_dict())) == p
    m = freze_profili(kinematics=ac_kinematik(), multiaxis=p)
    m.validate()
    assert MachineProfile.from_dict(jsonla(m.to_dict())) == m


# ================================================================ K5 Toolpath.coord, Move.c


def test_k5_valid_paths():
    polar_yol().validate()
    silindirik_yol().validate()
    tp = kartezyen_yol(station=3)
    tp.validate()
    assert tp.station == 3


@pytest.mark.parametrize("coord", ["", "Polar", "kutupsal", "cylindrical"])
def test_k5_unknown_coord(coord):
    with pytest.raises(CamError):
        kartezyen_yol(coord=coord).validate()


@pytest.mark.parametrize("yol", [polar_yol, silindirik_yol], ids=["polar", "silindirik"])
def test_k5_frame_rejected(yol):
    with pytest.raises(CamError):
        yol(frame=Frame((0.0, 0.0, 0.0), I3)).validate()


def test_k5_polar_axis_rejected():
    moves = [Move(G1, (20.0, 0.0, -1.0), feed=200.0), Move(G1, (0.0, 20.0, -1.0), feed=400.0, axis=EGIK)]
    with pytest.raises(CamError):
        polar_yol(moves).validate()


def test_k5_polar_zx_rejected():
    with pytest.raises(CamError):
        polar_yol(plane=Plane.ZX).validate()


@pytest.mark.parametrize("yol", [polar_yol, silindirik_yol], ids=["polar", "silindirik"])
def test_k5_lathe_tool_rejected(yol):
    with pytest.raises(CamError):
        yol(tool=torna_takimi()).validate()


@pytest.mark.parametrize("r", [None, 0.0, -30.0, NAN, INF])
def test_k5_cylindrical_bad_cyl_r(r):
    with pytest.raises(CamError):
        silindirik_yol(cyl_r=r).validate()


@pytest.mark.parametrize("arc", [G2, G3])
def test_k5_cylindrical_arc_rejected(arc):
    moves = [
        Move(G1, (0.0, -10.0, 28.0), feed=150.0),
        Move(arc, (20.0, -10.0, 28.0), feed=300.0, center=(10.0, -10.0)),
    ]
    with pytest.raises(CamError):
        silindirik_yol(moves).validate()


@pytest.mark.parametrize("yol", [kartezyen_yol, polar_yol], ids=["kartezyen", "polar"])
def test_k5_cyl_r_only_cylindrical(yol):
    with pytest.raises(CamError):
        yol(cyl_r=30.0).validate()


def test_k5_move_c_cartesian_valid():
    moves = [
        Move(G0, (25.0, 0.0, 2.0), c=0.0),
        Move(G1, (25.0, 0.0, -2.0), feed=200.0, c=0.0),
        Move(G0, (25.0, 0.0, 2.0), c=90.0),
        Move(G1, (25.0, 0.0, -2.0), feed=200.0, c=90.0),
    ]
    tp = kartezyen_yol(moves)
    tp.validate()
    assert [mv.c for mv in tp.moves] == [0.0, 0.0, 90.0, 90.0]


@pytest.mark.parametrize("c", [NAN, INF, -INF])
def test_k5_move_c_finite(c):
    with pytest.raises(CamError):
        kartezyen_yol([Move(G1, (0.0, 0.0, -1.0), feed=200.0, c=c)]).validate()


@pytest.mark.parametrize("yol", [polar_yol, silindirik_yol], ids=["polar", "silindirik"])
def test_k5_move_c_rejected_in_polar_cylindrical(yol):
    tp = yol()
    son = tp.moves[-1]
    moves = tp.moves[:-1] + [Move(son.type, son.end, feed=son.feed, c=45.0)]
    with pytest.raises(CamError):
        yol(moves).validate()


def test_k5_move_c_rejected_on_lathe_path():
    moves = [Move(G1, (20.0, 0.0, -30.0), feed=0.2, c=0.0)]
    with pytest.raises(CamError):
        torna_yolu(moves).validate()


@pytest.mark.parametrize("yol", [polar_yol, silindirik_yol], ids=["polar", "silindirik"])
def test_k5_roundtrip(yol):
    tp = yol(station=2)
    d = tp.to_dict()
    tp2 = Toolpath.from_dict(jsonla(d))
    assert tp2.coord == tp.coord
    assert tp2.cyl_r == tp.cyl_r
    assert tp2.station == 2
    assert tp2.to_dict() == d


def test_k5_move_c_roundtrip():
    tp = kartezyen_yol([Move(G1, (25.0, 0.0, -2.0), feed=200.0, c=-37.5)])
    tp2 = Toolpath.from_dict(jsonla(tp.to_dict()))
    assert tp2.moves[0].c == pytest.approx(-37.5)


# ================================================================ K6 PathMeta


def test_k6_meta_defaults():
    m = PathMeta("kaba")
    assert m.axis_mode == "3"
    assert m.allowance == 0.0
    assert m.allowance_z is None and m.ap is None and m.ae is None


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_k6_strategies(strategy):
    assert PathMeta(strategy).strategy == strategy


@pytest.mark.parametrize("axis_mode", AXIS_MODES)
def test_k6_axis_modes(axis_mode):
    assert PathMeta("kaba", axis_mode=axis_mode).axis_mode == axis_mode


@pytest.mark.parametrize("strategy", ["", "Kaba", "finish", "cep", "yari-ince"])
def test_k6_unknown_strategy(strategy):
    with pytest.raises(CamError):
        PathMeta(strategy)


@pytest.mark.parametrize("axis_mode", ["", "4", "3 + 2", "3+1", "Torna", "5x"])
def test_k6_unknown_axis_mode(axis_mode):
    with pytest.raises(CamError):
        PathMeta("kaba", axis_mode=axis_mode)


@pytest.mark.parametrize(
    "kw",
    [
        {"allowance": -0.1},
        {"allowance": NAN},
        {"allowance": INF},
        {"allowance_z": NAN},
        {"ap": 0.0},
        {"ap": -1.0},
        {"ap": NAN},
        {"ae": 0.0},
        {"ae": -2.0},
        {"ae": INF},
    ],
)
def test_k6_bad_numbers(kw):
    with pytest.raises(CamError):
        PathMeta("kaba", **kw)


def test_k6_valid_numbers():
    m = PathMeta("kaba", allowance=0.5, allowance_z=0.2, ap=2.0, ae=3.5)
    assert (m.allowance, m.allowance_z, m.ap, m.ae) == (0.5, 0.2, 2.0, 3.5)


def test_k6_meta_roundtrip():
    m = PathMeta("yanak", axis_mode="5", allowance=0.3, allowance_z=0.1, ap=12.0, ae=0.8)
    assert PathMeta.from_dict(jsonla(m.to_dict())) == m
    tp = egik_yol(meta=m)
    tp.validate()
    tp2 = Toolpath.from_dict(jsonla(tp.to_dict()))
    assert tp2.meta == m


def test_k6_meta_does_not_change_geometry():
    a = kartezyen_yol()
    b = kartezyen_yol(meta=PathMeta("ince", allowance=0.0))
    b.validate()
    assert a.length() == pytest.approx(b.length())
    assert [mv.end for mv in a.moves] == [mv.end for mv in b.moves]


def test_k6_axis_mode_5_requires_axis():
    egik_yol(meta=PathMeta("yanak", axis_mode="5")).validate()
    with pytest.raises(CamError):
        kartezyen_yol(meta=PathMeta("yanak", axis_mode="5")).validate()


def test_k6_axis_mode_3_forbids_axis():
    kartezyen_yol(meta=PathMeta("kaba", axis_mode="3")).validate()
    with pytest.raises(CamError):
        egik_yol(meta=PathMeta("kaba", axis_mode="3")).validate()


def test_k6_torna_iff_lathe_tool():
    torna_yolu(meta=PathMeta("kaba", axis_mode="torna")).validate()
    with pytest.raises(CamError):
        torna_yolu(meta=PathMeta("kaba", axis_mode="3")).validate()
    with pytest.raises(CamError):
        kartezyen_yol(meta=PathMeta("kaba", axis_mode="torna")).validate()


@pytest.mark.parametrize("mod", ["polar", "silindirik"])
def test_k6_coord_iff_axis_mode(mod):
    yol = polar_yol if mod == "polar" else silindirik_yol
    diger = "silindirik" if mod == "polar" else "polar"
    yol(meta=PathMeta("kanal", axis_mode=mod)).validate()
    # coord var, axis_mode başka
    for am in ("3", "c_indeks", diger):
        with pytest.raises(CamError):
            yol(meta=PathMeta("kanal", axis_mode=am)).validate()
    # axis_mode var, coord kartezyen
    with pytest.raises(CamError):
        kartezyen_yol(meta=PathMeta("kanal", axis_mode=mod)).validate()


def test_k6_c_indeks_with_move_c():
    moves = [Move(G0, (25.0, 0.0, 2.0), c=0.0), Move(G1, (25.0, 0.0, -2.0), feed=200.0, c=120.0)]
    kartezyen_yol(moves, meta=PathMeta("delik", axis_mode="c_indeks")).validate()


# ================================================================ K8 yazıcı koruması


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["grbl", "fanuc"])
def test_k8_writer_plain_path_still_written(dialect):
    assert write([kartezyen_yol()], dialect)


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["grbl", "fanuc"])
@pytest.mark.parametrize("c", [0.0, 90.0])
def test_k8_writer_rejects_move_c(dialect, c):
    moves = [Move(G1, (0.0, 0.0, -1.0), feed=200.0), Move(G1, (10.0, 0.0, -1.0), feed=500.0, c=c)]
    with pytest.raises(CamError):
        write([kartezyen_yol(moves)], dialect)


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["grbl", "fanuc"])
@pytest.mark.parametrize("yol", [polar_yol, silindirik_yol], ids=["polar", "silindirik"])
def test_k8_writer_rejects_non_cartesian(dialect, yol):
    with pytest.raises(CamError):
        write([yol()], dialect)


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["grbl", "fanuc"])
def test_k8_writer_rejects_in_second_op(dialect):
    with pytest.raises(CamError):
        write([kartezyen_yol(), polar_yol()], dialect)
