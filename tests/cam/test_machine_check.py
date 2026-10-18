"""SPEC 44 K3–K7 — hareket boyunca tezgâh çarpışması, en az boşluk ve eksen sınırı denetimi (`check`).

Testler SPEC 44 metninden ve modül docstring'lerinden yazıldı; `check` gövdesi okunmadı. Senaryolar elle
kuruldu ve beklenen temas anı kapalı formdur. Yollar, istenen eklem değerlerinden SPEC 41
`forward` ile kurulur (uç noktası ve takım ekseni WCS'de).

Kurallar (SPEC 44 + koordinatör yorumu 2026-10-18):
- Adım indeksi k SPEC 05 kuralıyla: tek yolda hareket i (0'dan) → k = i + 1.
- `tezgah_carpma` kaydında a kafa zinciri gövdesi, b masa zinciri / taban gövdesi; masa × taban da denetlenir.
- Kayıt temasın başladığı ilk t (hareket içi kesir); eksen sınırında sınırın aşıldığı an.
- tcp=False: eklemler doğrusal; tcp=True: uç doğrusal, eksen slerp.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from cam.model import (
    AxisLimits,
    Kinematics,
    MachineProfile,
    Move,
    MoveType,
    RotaryAxis,
    Setup,
    Stock,
    Tool,
    ToolHolder,
    ToolKind,
    Toolpath,
    Wcs,
)
from cam.multiaxis.collision import EVENT_KINDS, MachineEvent, check
from cam.multiaxis.indexed import from_normal
from cam.multiaxis.kinematics import forward
from cam.multiaxis.machine import Body, Box, Capsule, MachineModel

ORNEK = Path(__file__).resolve().parents[2] / "examples" / "tezgah_ac_besik.json"
G0, G1, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CCW
L = 100.0  # ölçü noktasından uca takım boyu
KAFA3 = {"X": "kafa", "Y": "kafa", "Z": "kafa"}


def tool(D: float = 10.0) -> Tool:
    return Tool(id=1, name="F", kind=ToolKind.FLAT, D=D, flute_length=30.0)


def profile(kin=None, x=None, y=None, z=None) -> MachineProfile:
    return MachineProfile(
        name="TEST", controller="fanuc", x=x, y=y, z=z, rpm_max=12000, feed_max=10000, kinematics=kin
    )


def a_masa(pivot=(0.0, 0.0, 0.0)) -> Kinematics:
    return Kinematics(rotary=(RotaryAxis("A", "masa", (1.0, 0.0, 0.0), pivot, -120.0, 120.0),))


def path_from_q(kin, qs, wcs: Wcs, t: Tool, feed: float = 500.0) -> Toolpath:
    """Eklem değerleri qs[0] (başlangıç), qs[1:] (hareket sonları) → WCS uç noktaları ve eksenleri (G1)."""
    pts = []
    for q in qs:
        if kin is None:
            tip = np.asarray(q[:3], dtype=float) - L * np.array([0.0, 0.0, 1.0]) - np.array(wcs.origin)
            a = np.array([0.0, 0.0, 1.0])
        else:
            tip, a = forward(kin, q, L, wcs)
        pts.append((tuple(float(v) for v in tip), tuple(float(v) for v in a)))
    moves = [Move(G1, p, feed=feed, axis=a) for p, a in pts[1:]]
    tp = Toolpath(name="yol", tool=t, start=pts[0][0], moves=moves, rpm=8000.0)
    tp.validate()
    return tp


def carpmalar(ev: list[MachineEvent]) -> list[MachineEvent]:
    return [e for e in ev if e.kind == "tezgah_carpma"]


def sinirlar(ev: list[MachineEvent]) -> list[MachineEvent]:
    return [e for e in ev if e.kind == "eksen_siniri"]


def test_olay_turleri():
    assert EVENT_KINDS == ("tezgah_carpma", "eksen_siniri")


# --- K3 düşey temas --------------------------------------------------------------------------------

Z_H, Z_M = 0.0, -80.0  # kafa kutusu alt yüzü (Z = 0'da), masa üst yüzü


def k3_model() -> MachineModel:
    kafa = Body("kafa", "Z", Box(center=(0.0, 0.0, Z_H + 50.0), half=(100.0, 50.0, 50.0)))
    # masa takımın yanında (x ∈ [60, 140]): takım ona değmez, kafa kutusu değer
    masa = Body("masa", "taban", Box(center=(100.0, 0.0, Z_M - 10.0), half=(40.0, 40.0, 10.0)))
    return MachineModel(profile(), dict(KAFA3), [kafa, masa])


def k3_setup() -> Setup:
    return Setup(name="s", wcs=Wcs(), stock=Stock(380.0, -20.0, -300.0, 420.0, 20.0, -250.0))


@pytest.mark.parametrize("tcp", [True, False])
def test_k3_duşey_temas(tcp):
    tp = path_from_q(None, [(0.0, 0.0, 0.0), (0.0, 0.0, -120.0)], Wcs(), tool())
    ev = check(k3_model(), k3_setup(), [tp], L=L, tcp=tcp)
    c = carpmalar(ev)
    assert len(c) == 1
    e = c[0]
    assert (e.a, e.b) == ("kafa", "masa")
    assert e.k == 1
    Z = -120.0 * e.t  # temas anındaki Z eklemi
    assert Z == pytest.approx(Z_M - Z_H, abs=1e-6)
    assert not sinirlar(ev)


def test_k3_bosluk():
    """clearance = 2: kutular 1'er mm büyütülür → temas 2 mm önce (Z = −78)."""
    tp = path_from_q(None, [(0.0, 0.0, 0.0), (0.0, 0.0, -120.0)], Wcs(), tool())
    ev = carpmalar(check(k3_model(), k3_setup(), [tp], L=L, clearance=2.0))
    assert len(ev) == 1
    assert ev[0].k == 1
    assert -120.0 * ev[0].t == pytest.approx(Z_M - Z_H + 2.0, abs=1e-6)


def test_k3_temas_yok():
    tp = path_from_q(None, [(0.0, 0.0, 0.0), (0.0, 0.0, -79.0)], Wcs(), tool())
    assert check(k3_model(), k3_setup(), [tp], L=L) == []
    # ikinci harekette temas: k = 2
    tp = path_from_q(None, [(0.0, 0.0, 0.0), (0.0, 0.0, -50.0), (0.0, 0.0, -100.0)], Wcs(), tool())
    ev = carpmalar(check(k3_model(), k3_setup(), [tp], L=L))
    assert [e.k for e in ev] == [2]
    assert -50.0 - 50.0 * ev[0].t == pytest.approx(Z_M - Z_H, abs=1e-6)


# --- K4 dönen fikstür ------------------------------------------------------------------------------

W_KOLON = 60.0  # kolon yüzü y = −60 (A ekseninden uzaklık)
FIKSTUR = Stock(-10.0, -10.0, 0.0, 10.0, 10.0, 100.0)
RHO = math.hypot(10.0, 100.0)  # (y = −10, z = 100) köşesinin A eksenine uzaklığı
PHI0 = math.atan2(10.0, 100.0)  # +z'den −y'ye doğru başlangıç açısı
THETA = math.asin(W_KOLON / RHO) - PHI0  # Rx(θ) ile köşe y = −ρ sin(φ₀ + θ) = −w


def k4_model() -> MachineModel:
    kolon = Body("kolon", "taban", Box(center=(0.0, -130.0, 150.0), half=(100.0, 70.0, 150.0)))
    return MachineModel(profile(a_masa()), dict(KAFA3), [kolon])


def k4_setup() -> Setup:
    return Setup(name="s", wcs=Wcs(), stock=Stock(-5.0, -5.0, 0.0, 5.0, 5.0, 10.0), fixtures=[FIKSTUR])


def test_k4_donen_fikstur_kolona_carpar():
    kin = a_masa()
    tp = path_from_q(
        kin, [(0.0, 0.0, 510.0, 0.0), (0.0, 0.0, 500.0, 0.0), (0.0, 0.0, 500.0, 90.0)], Wcs(), tool()
    )
    ev = carpmalar(check(k4_model(), k4_setup(), [tp], L=L, tcp=False))
    c = [e for e in ev if {e.a, e.b} == {"fikstur_0", "kolon"}]
    assert len(c) == 1
    assert c[0].k == 2
    theta = math.radians(90.0 * c[0].t)
    # ikiye bölme 1e-6 mm → açıda 1e-6/ρ rad
    assert abs(theta - THETA) <= 1.5e-6 / RHO
    # ham malzeme köşeleri eksene ≤ 11.2 mm: kolona hiç ulaşmaz
    assert not [e for e in ev if "ham_malzeme" in (e.a, e.b)]


def test_k4_ornekleme_sigma():
    """σ büyüse de ince olmayan gövdede temas kaçırılmaz; ikiye bölme yine 1e-6 mm'ye indirir."""
    kin = a_masa()
    tp = path_from_q(
        kin, [(0.0, 0.0, 510.0, 0.0), (0.0, 0.0, 500.0, 0.0), (0.0, 0.0, 500.0, 90.0)], Wcs(), tool()
    )
    ev = carpmalar(check(k4_model(), k4_setup(), [tp], L=L, tcp=False, sigma=5.0))
    c = [e for e in ev if {e.a, e.b} == {"fikstur_0", "kolon"}]
    assert len(c) == 1
    assert abs(math.radians(90.0 * c[0].t) - THETA) <= 1.5e-6 / RHO


def test_k4_temas_oncesi_durur():
    kin = a_masa()
    durus = math.degrees(THETA) - 1.0
    tp = path_from_q(
        kin, [(0.0, 0.0, 510.0, 0.0), (0.0, 0.0, 500.0, 0.0), (0.0, 0.0, 500.0, durus)], Wcs(), tool()
    )
    assert carpmalar(check(k4_model(), k4_setup(), [tp], L=L, tcp=False)) == []


# --- K5 TCP modu -----------------------------------------------------------------------------------
# Uç WCS'de (0, 0, 50)'de sabit, eksen +z'den A = 90°'ye döner. tcp=True: ölçü noktası A ekseni
# etrafında 50 yarıçaplı yay (merkez (0, 0, 100)); tcp=False: (0, 0, 150) → (0, −50, 100) kirişi.
# "uc" küresi ölçü noktasından x = 100 uzakta; "engel" kirişin ortasında → yalnız tcp=False çarpar
# (yayın engele uzaklığı 50 − 25√2 ≈ 14.6 > 4).


def k5_model() -> MachineModel:
    uc = Body("uc", "is_mili", Capsule(p=(100.0, 0.0, 0.0), q=(100.0, 0.0, 0.0), r=2.0))
    engel = Body("engel", "taban", Capsule(p=(100.0, -25.0, 125.0), q=(100.0, -25.0, 125.0), r=2.0))
    return MachineModel(profile(a_masa()), dict(KAFA3), [uc, engel])


def k5_path() -> Toolpath:
    kin = a_masa()
    return path_from_q(
        kin, [(0.0, 0.0, 160.0, 0.0), (0.0, 0.0, 150.0, 0.0), (0.0, -50.0, 100.0, 90.0)], Wcs(), tool()
    )


def test_k5_yol_kurulumu():
    """Ön koşul: ikinci harekette uç WCS'de sabit (0, 0, 50), eksen +z → +y."""
    tp = k5_path()
    np.testing.assert_allclose(tp.moves[0].end, (0.0, 0.0, 50.0), atol=1e-12)
    np.testing.assert_allclose(tp.moves[1].end, (0.0, 0.0, 50.0), atol=1e-12)
    np.testing.assert_allclose(tp.moves[1].axis, (0.0, 1.0, 0.0), atol=1e-12)


def test_k5_tcp_ve_eklem_modu_farkli():
    s = Setup(name="s", wcs=Wcs(), stock=Stock(-5.0, -5.0, 0.0, 5.0, 5.0, 40.0))
    tp = k5_path()
    assert carpmalar(check(k5_model(), s, [tp], L=L, tcp=True)) == []
    ev = carpmalar(check(k5_model(), s, [tp], L=L, tcp=False))
    assert len(ev) == 1
    assert (ev[0].a, ev[0].b) == ("uc", "engel")
    assert ev[0].k == 2
    # kirişte uc küresi engele t = 0.5'te tam merkezden geçer; temas |t − 0.5|·|kiriş| = 4'te başlar
    kiris = math.hypot(50.0, 50.0)
    assert ev[0].t == pytest.approx(0.5 - 4.0 / kiris, abs=1e-6 / kiris * 1.5)


# --- K6 eksen sınırı -------------------------------------------------------------------------------


def k6_model(kin=None) -> MachineModel:
    return MachineModel(profile(kin, x=AxisLimits(-300.0, 300.0)), dict(KAFA3), [])


def k6_setup() -> Setup:
    return Setup(name="s", wcs=Wcs(), stock=Stock(-5.0, -5.0, 0.0, 5.0, 5.0, 10.0))


def test_k6_doner_sinir_eklem_modu():
    kin = a_masa()
    qs = [(0.0, 0.0, 300.0, 0.0), (0.0, 0.0, 300.0, 100.0), (0.0, 0.0, 300.0, 121.0)]
    ev = check(k6_model(kin), k6_setup(), [path_from_q(kin, qs, Wcs(), tool())], L=L, tcp=False)
    s = sinirlar(ev)
    assert len(s) == 1
    assert s[0].a == "A"
    assert s[0].k == 2
    assert s[0].t == pytest.approx(20.0 / 21.0, abs=1e-6)
    assert not carpmalar(ev)


def test_k6_doner_sinir_tcp_modu():
    kin = a_masa()
    qs = [(0.0, 0.0, 300.0, 0.0), (0.0, 0.0, 300.0, 100.0), (0.0, 0.0, 300.0, 121.0)]
    s = sinirlar(check(k6_model(kin), k6_setup(), [path_from_q(kin, qs, Wcs(), tool())], L=L, tcp=True))
    assert [(e.a, e.k) for e in s] == [("A", 2)]
    assert 0.0 < s[0].t <= 1.0


def test_k6_dogrusal_sinir():
    qs = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (310.0, 0.0, 0.0)]
    s = sinirlar(check(k6_model(), k6_setup(), [path_from_q(None, qs, Wcs(), tool())], L=L, tcp=False))
    assert len(s) == 1
    assert s[0].a == "X"
    assert s[0].k == 2
    assert s[0].t == pytest.approx(200.0 / 210.0, abs=1e-6)


@pytest.mark.parametrize("tcp", [True, False])
def test_k6_sinir_icinde_kayit_yok(tcp):
    kin = a_masa()
    qs = [(0.0, 0.0, 300.0, 0.0), (299.0, 0.0, 300.0, 100.0), (-299.0, 0.0, 300.0, 119.0)]
    assert check(k6_model(kin), k6_setup(), [path_from_q(kin, qs, Wcs(), tool())], L=L, tcp=tcp) == []


# --- K7 örnek tezgâhta temiz program ve tutucu × fikstür -------------------------------------------

S30, C30 = 0.5, math.sqrt(3.0) / 2.0
WCS_ORNEK = Wcs(origin=(0.0, 0.0, -350.0))  # C tablası üst yüzü merkezi


def ornek_model() -> MachineModel:
    return MachineModel.from_dict(json.loads(ORNEK.read_text(encoding="utf-8")))


def cep_yolu() -> Toolpath:
    """SPEC 41 K8: 30° eğik yüzde (yerel çerçeve) 40 × 20 dikdörtgen cep, köşeler r = 5 yaylı."""
    fr = from_normal((0.0, 0.0, 20.0), (0.0, -S30, C30), (1.0, 0.0, 0.0))
    z, zg, f = -2.0, 5.0, 600.0
    moves = [
        Move(G1, (-15.0, -10.0, z), feed=200.0),
        Move(G1, (15.0, -10.0, z), feed=f),
        Move(G3, (20.0, -5.0, z), feed=f, center=(15.0, -5.0)),
        Move(G1, (20.0, 5.0, z), feed=f),
        Move(G3, (15.0, 10.0, z), feed=f, center=(15.0, 5.0)),
        Move(G1, (-15.0, 10.0, z), feed=f),
        Move(G3, (-20.0, 5.0, z), feed=f, center=(-15.0, 5.0)),
        Move(G1, (-20.0, -5.0, z), feed=f),
        Move(G3, (-15.0, -10.0, z), feed=f, center=(-15.0, -5.0)),
        Move(G0, (-15.0, -10.0, zg)),
    ]
    t = Tool(id=1, name="F6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)
    tp = Toolpath(name="cep", tool=t, start=(-15.0, -10.0, zg), moves=moves, rpm=8000.0, frame=fr)
    tp.validate()
    return tp


@pytest.mark.parametrize("tcp", [True, False])
def test_k7_temiz_3arti2_cep(tcp):
    s = Setup(
        name="s",
        wcs=WCS_ORNEK,
        stock=Stock(-40.0, -30.0, 0.0, 40.0, 30.0, 10.0),
        fixtures=[Stock(130.0, -20.0, 0.0, 150.0, 20.0, 20.0)],
    )
    assert check(ornek_model(), s, [cep_yolu()], L=L, tcp=tcp) == []


def tutuculu_takim() -> Tool:
    """Silindirik tutucu (r = 20, ağızdan 60 mm), taşma 40: tek tutucu basamağı → 'tutucu_0'."""
    h = ToolHolder(name="T20", gauge_length=60.0, profile=((0.0, 20.0), (60.0, 20.0)))
    return Tool(id=2, name="F6T", kind=ToolKind.FLAT, D=6.0, flute_length=20.0, stickout=40.0, holder=h)


def test_k7_tutucu_fikstur_tek_kayit():
    """x = 45'te dikey iniş (A = C = 0): takım ve sap (r = 3) fikstüre (x ≥ 50) ve ham malzemeye (x ≤ 40)
    değmez; tutucu kapsülü (r = 20, ekseni uç + 40 … uç + 100) fikstürün üst kenarına (50, y, 60) iner.
    Temas: √(5² + (z_uc + 40 − 60)²) = 20 → z_uc = 20 + √375. Ham malzeme teması z_uc = √375'te olurdu;
    iniş z_uc = 30'da biter."""
    s = Setup(
        name="s",
        wcs=WCS_ORNEK,
        stock=Stock(-40.0, -30.0, 0.0, 40.0, 30.0, 40.0),
        fixtures=[Stock(50.0, -30.0, 0.0, 70.0, 30.0, 60.0)],
    )
    t = tutuculu_takim()
    tp = Toolpath(
        name="carp",
        tool=t,
        start=(45.0, 0.0, 80.0),
        moves=[Move(G1, (45.0, 0.0, 30.0), feed=500.0)],
        rpm=8000.0,
    )
    tp.validate()
    for tcp in (True, False):
        ev = check(ornek_model(), s, [tp], L=t.gauge_length, tcp=tcp)
        assert len(ev) == 1
        e = ev[0]
        assert e.kind == "tezgah_carpma"
        assert (e.a, e.b) == ("tutucu_0", "fikstur_0")
        assert e.k == 1
        z_uc = 80.0 - 50.0 * e.t
        assert z_uc == pytest.approx(20.0 + math.sqrt(375.0), abs=1.5e-6)
