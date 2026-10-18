"""SPEC 59 — takım ömrü, freze ve öneri testleri (K1–K4, K8–K10).

Testler yalnız specs/59-takim-omru.md'deki teori, arayüz ve örneklerden yazıldı; cam/omur.py gövdesi okunmadı.
Uydurma malzeme kaydı C45, karbur için Taylor(C = 300, n = 0.25) → T(Vc) = (300 / Vc)^4 dk.
Uydurma yollar ve simülasyon sonuçları tests/cam/omur_ref.py'de (adım süreleri elle verilir).
B2 (malzeme/model.py) uygulanana kadar Taylor / Malzeme kurulumu NotImplementedError verir: testler
"uygulanmamış" görünür.
"""

from __future__ import annotations

import json
import math

import pytest

from cam.cutting import effective_diameter
from cam.model import CamError, ToolKind, ToolLibrary
from cam.omur import ChangeAdvice, StepWear, ToolWear, advise, mill_wear, tool_life
from malzeme.model import Taylor
from tests.cam.omur_ref import (
    MODEL_HATASI,
    T_taylor,
    freze,
    freze_programi,
    malzeme,
    rpm_for,
)

KARBUR = {3: "karbur"}
N150 = rpm_for(150.0, 10.0)  # D = 10 düz uçta Vc = 150 m/dk (SPEC: n = 4774.65)
N300 = rpm_for(300.0, 10.0)


def _wear_by_id(wear: list[ToolWear]) -> dict[int, ToolWear]:
    d = {w.tool_id: w for w in wear}
    assert len(d) == len(wear), "takım başına tek ToolWear"
    return d


# ---------- K1 Taylor ----------


@pytest.mark.parametrize(("Vc", "T"), [(150.0, 16.0), (200.0, 5.0625), (300.0, 1.0)])
def test_tool_life_taylor(Vc, T):
    """T = (C / Vc)^(1/n), C = 300, n = 0.25 (SPEC Teori örneği)."""
    assert tool_life(Taylor(300.0, 0.25), Vc) == pytest.approx(T, rel=1e-12)


@pytest.mark.parametrize("Vc", [0.0, -1.0, math.inf])
def test_tool_life_invalid_speed(Vc):
    with pytest.raises(MODEL_HATASI):
        tool_life(Taylor(300.0, 0.25), Vc)


# ---------- K2 Sabit hız ----------


def test_constant_speed_D():
    """D = 10 düz uç, Vc = 150 → T = 16 dk; 3 dk kesme → D = 3 / 16 = 0.1875."""
    ops, res, loads = freze_programi([(freze(), N150, [("G1", 3.0, "kesme", 2.0)])])
    wear = mill_wear(ops, res, loads, malzeme(), KARBUR)
    assert len(wear) == 1
    w = wear[0]
    assert w.tool_id == 3 and w.tool_material == "karbur"
    assert w.D == pytest.approx(0.1875, abs=1e-9)
    assert w.t_cut == pytest.approx(3.0, abs=1e-9)
    assert w.Vc_max == pytest.approx(150.0, rel=1e-12)
    kesen = [s for s in w.steps if s.D > 0]
    assert len(kesen) == 1
    s = kesen[0]
    assert (s.k, s.op, s.tool_id) == (0, 0, 3)
    assert s.t == pytest.approx(3.0, abs=1e-12)
    assert s.Vc_min == pytest.approx(150.0, rel=1e-12) and s.Vc_max == pytest.approx(150.0, rel=1e-12)
    assert s.D == pytest.approx(0.1875, abs=1e-9)


def test_constant_speed_split_into_steps():
    """Aynı 3 dk üç adıma bölünmüş: D aynı, adım katkılarının toplamı D."""
    ops, res, loads = freze_programi(
        [(freze(), N150, [("G1", 1.0, "kesme", 2.0), ("G1", 0.5, "kesme", 2.0), ("G1", 1.5, "kesme", 2.0)])]
    )
    w = mill_wear(ops, res, loads, malzeme(), KARBUR)[0]
    assert w.D == pytest.approx(0.1875, abs=1e-9)
    assert sum(s.D for s in w.steps) == pytest.approx(w.D, rel=1e-12)
    assert sum(s.t for s in w.steps) == pytest.approx(3.0, rel=1e-12)


def test_rapid_air_and_skipped_steps_do_not_count():
    """G0, hava kesmesi ("hava") ve "atlandi" adımları 0 katkı: D ve t_cut değişmez (SPEC: yalnız kesme)."""
    ops, res, loads = freze_programi(
        [
            (
                freze(),
                N150,
                [
                    ("G0", 0.1, "hava", 0.0),
                    ("G1", 1.0, "hava", 0.0),
                    ("G1", 3.0, "kesme", 2.0),
                    ("G1", 2.0, "atlandi", 0.0),
                    ("G0", 0.1, "hava", 0.0),
                ],
            )
        ]
    )
    w = mill_wear(ops, res, loads, malzeme(), KARBUR)[0]
    assert w.D == pytest.approx(0.1875, abs=1e-9)
    assert w.t_cut == pytest.approx(3.0, abs=1e-9)
    kesme_k = {ld.k for ld in loads if ld.kind == "kesme"}
    assert all(s.D == 0 for s in w.steps if s.k not in kesme_k)


# ---------- K3 Miner iki hız ----------


def _iki_hiz(ters: bool):
    a = (freze(), N150, [("G1", 4.0, "kesme", 2.0)])
    b = (freze(), N300, [("G1", 0.5, "kesme", 2.0)])
    return freze_programi([b, a] if ters else [a, b])


@pytest.mark.parametrize("ters", [False, True])
def test_miner_two_speeds(ters):
    """4 dk 150 m/dk + 0.5 dk 300 m/dk → D = 4/16 + 0.5/1 = 0.75; adım sırası sonucu değiştirmez."""
    ops, res, loads = _iki_hiz(ters)
    wear = mill_wear(ops, res, loads, malzeme(), KARBUR)
    w = _wear_by_id(wear)[3]
    assert w.D == pytest.approx(0.75, rel=1e-12)
    assert w.t_cut == pytest.approx(4.5, rel=1e-12)
    assert w.Vc_max == pytest.approx(300.0, rel=1e-12)
    katki = sorted(s.D for s in w.steps if s.D > 0)
    assert katki == pytest.approx([0.25, 0.5], rel=1e-12)


def test_two_tools_separate():
    """İki takım ayrı toplanır: T3 Vc = 150'de 3 dk (0.1875), T4 Vc = 300'de 0.25 dk (0.25)."""
    t4 = freze(4)
    ops, res, loads = freze_programi(
        [(freze(), N150, [("G1", 3.0, "kesme", 2.0)]), (t4, N300, [("G1", 0.25, "kesme", 2.0)])]
    )
    w = _wear_by_id(mill_wear(ops, res, loads, malzeme(), {3: "karbur", 4: "karbur"}))
    assert set(w) == {3, 4}
    assert w[3].D == pytest.approx(0.1875, rel=1e-12)
    assert w[4].D == pytest.approx(0.25, rel=1e-12)
    assert all(s.tool_id == 3 and s.op == 0 for s in w[3].steps)
    assert all(s.tool_id == 4 and s.op == 1 for s in w[4].steps)


# ---------- K4 Etkin çap ----------


def test_effective_diameter_ball():
    """Küresel uç D = 10 (r = 5), ap = 1: D_eff = SPEC 14 effective_diameter (= 6); Vc = π D_eff n / 1000."""
    top = freze(kind=ToolKind.BALL, corner_r=5.0)
    rpm = 6000.0
    ops, res, loads = freze_programi([(top, rpm, [("G1", 2.0, "kesme", 1.0)])])
    w = mill_wear(ops, res, loads, malzeme(), KARBUR)[0]
    D_eff = effective_diameter(top, 1.0)
    assert D_eff == pytest.approx(6.0, rel=1e-12)
    Vc = math.pi * D_eff * rpm / 1000.0
    s = next(s for s in w.steps if s.D > 0)
    assert s.Vc_min == pytest.approx(Vc, rel=1e-12) and s.Vc_max == pytest.approx(Vc, rel=1e-12)
    assert w.D == pytest.approx(2.0 / T_taylor(Vc), rel=1e-12)


def test_effective_diameter_D_grows_with_ap():
    top = freze(kind=ToolKind.BALL, corner_r=5.0)
    D = []
    for ap in (0.5, 1.0, 2.0, 4.0):
        ops, res, loads = freze_programi([(top, 6000.0, [("G1", 2.0, "kesme", ap)])])
        D.append(mill_wear(ops, res, loads, malzeme(), KARBUR)[0].D)
    assert all(b > a for a, b in zip(D, D[1:], strict=False))


# ---------- K8 Öneri ----------


def _tw(tool_id: int, adimlar: list[tuple[int, float]]) -> ToolWear:
    """Elle ToolWear: adım = (op, D) ; t ve Vc uydurma (öneri yalnız D'ye ve op sınırlarına bakar)."""
    steps = tuple(
        StepWear(k=k, op=op, tool_id=tool_id, t=1.0, Vc_min=150.0, Vc_max=150.0, D=D)
        for k, (op, D) in enumerate(adimlar)
    )
    return ToolWear(
        tool_id=tool_id,
        tool_material="karbur",
        t_cut=float(len(steps)),
        D=sum(s.D for s in steps),
        Vc_max=150.0,
        steps=steps,
    )


def _lib(*tools) -> ToolLibrary:
    return ToolLibrary(list(tools))


@pytest.mark.parametrize(("D_part", "k"), [(0.1875, 4), (0.75, 1), (0.4, 2), (0.8, 1)])
def test_advise_parts_per_edge(D_part, k):
    """k = floor(D_lim / D_parça), D_lim = 0.8 (varsayılan); seri (parts = 20) bir kenarı aşıyor → "kenar"."""
    a = advise([_tw(3, [(0, D_part)])], _lib(freze()), parts=20)
    assert len(a) == 1
    assert a[0].tool_id == 3
    assert a[0].kind == "kenar"
    assert a[0].parts_per_edge == k
    assert a[0].at_op is None and a[0].sister_id is None
    assert a[0].D_part == pytest.approx(D_part, rel=1e-12)


def test_advise_no_change_needed():
    """Varsayım: parts · D_parça ≤ D_lim ise (tüm seri tek kenarla biter) kind = "gerek_yok"."""
    a = advise([_tw(3, [(0, 0.1875)])], _lib(freze()), parts=4)
    assert a[0].kind == "gerek_yok"
    assert a[0].sister_id is None and a[0].at_op is None


def test_advise_D_lim():
    """D_lim = 1 → k = floor(1 / 0.1875) = 5; D_lim = 0.5 → 2."""
    assert advise([_tw(3, [(0, 0.1875)])], _lib(freze()), parts=20, D_lim=1.0)[0].parts_per_edge == 5
    assert advise([_tw(3, [(0, 0.1875)])], _lib(freze()), parts=20, D_lim=0.5)[0].parts_per_edge == 2


@pytest.mark.parametrize(
    ("adimlar", "at_op"),
    [
        # op 0: 0.5, op 1: 0.4 (birikimli 0.9, 0.8'i op 1'de geçer), op 2: 0.3 → D = 1.2; değişim op 1'in başı
        ([(0, 0.5), (1, 0.4), (2, 0.3)], 1),
        # op 0'da 0.3 + 0.3, op 1'de 0.6 → 0.8'e op 1'de ulaşır
        ([(0, 0.3), (0, 0.3), (1, 0.6)], 1),
        # tek op'ta 1.2: o op'un başı
        ([(0, 0.6), (0, 0.6)], 0),
        # op 0 0.2, op 1 0.2, op 2 0.8 (birikimli 1.2): op 2'nin başı
        ([(0, 0.2), (1, 0.2), (2, 0.8)], 2),
    ],
)
def test_advise_in_program_change(adimlar, at_op):
    """k = 0 (tek parça D_lim'i aşıyor): parts_per_edge None, at_op D'nin 0.8'e ulaştığı op'un başı."""
    w = _tw(3, adimlar)
    a = advise([w], _lib(freze()))[0]
    assert a.kind == "kenar"
    assert a.parts_per_edge is None
    assert a.at_op == at_op
    assert a.D_part == pytest.approx(w.D, rel=1e-12)


def test_advise_sister_tool():
    """Kütüphanede aynı kind, D, corner_r, flutes, flute_length'te ikinci takım → "kardes", sister_id dolu."""
    lib = _lib(freze(3), freze(7), freze(9, D=12.0))
    a = advise([_tw(3, [(0, 0.1875)])], lib, parts=20)[0]
    assert a.kind == "kardes"
    assert a.sister_id == 7
    assert a.parts_per_edge == 4


@pytest.mark.parametrize(
    "farkli",
    [
        {"D": 12.0},
        {"corner_r": 1.0},
        {"flutes": 3},
        {"flute_length": 30.0},
        {"kind": ToolKind.BALL, "corner_r": 5.0},
    ],
)
def test_advise_different_geometry_not_sister(farkli):
    lib = _lib(freze(3), freze(7, **farkli))
    a = advise([_tw(3, [(0, 0.1875)])], lib, parts=20)[0]
    assert a.kind == "kenar"
    assert a.sister_id is None


def test_advise_one_per_tool_in_order():
    a = advise([_tw(3, [(0, 0.1875)]), _tw(4, [(1, 0.75)])], _lib(freze(3), freze(4, D=8.0)), parts=20)
    assert [x.tool_id for x in a] == [3, 4]
    assert [x.parts_per_edge for x in a] == [4, 1]


# ---------- K9 Hatalar (freze ve öneri) ----------


def _program():
    return freze_programi([(freze(), N150, [("G1", 3.0, "kesme", 2.0)])])


def test_error_tool_material_missing():
    ops, res, loads = _program()
    with pytest.raises(MODEL_HATASI, match="T3"):
        mill_wear(ops, res, loads, malzeme(), {})


def test_error_tool_material_unknown():
    ops, res, loads = _program()
    with pytest.raises(MODEL_HATASI):
        mill_wear(ops, res, loads, malzeme(), {3: "elmas"})


def test_error_no_taylor_for_tool_material():
    """Kayıtta HSS için Taylor yok → ModelError; mesaj malzeme adını ve takım malzemesini içerir."""
    ops, res, loads = _program()
    with pytest.raises(MODEL_HATASI) as e:
        mill_wear(ops, res, loads, malzeme(), {3: "HSS"})
    assert "C45" in str(e.value) and "HSS" in str(e.value)


@pytest.mark.parametrize("fark", [-1, 1])
def test_error_loads_length(fark):
    ops, res, loads = _program()
    loads = loads[:-1] if fark < 0 else [*loads, loads[-1]]
    with pytest.raises(CamError):
        mill_wear(ops, res, loads, malzeme(), KARBUR)


def test_error_zero_rpm_cutting():
    ops, res, loads = freze_programi([(freze(), 0.0, [("G1", 3.0, "kesme", 2.0)])])
    with pytest.raises(CamError):
        mill_wear(ops, res, loads, malzeme(), KARBUR)


@pytest.mark.parametrize("D_lim", [0.0, -0.1, 1.0001, 2.0, math.nan, math.inf])
def test_error_D_lim(D_lim):
    with pytest.raises(CamError):
        advise([_tw(3, [(0, 0.1875)])], _lib(freze()), parts=20, D_lim=D_lim)


@pytest.mark.parametrize("parts", [0, -1, 1.5])
def test_error_parts(parts):
    with pytest.raises(CamError):
        advise([_tw(3, [(0, 0.1875)])], _lib(freze()), parts=parts)


# ---------- K10 JSON ----------


def _json_gidis_donus(nesne):
    return type(nesne).from_dict(json.loads(json.dumps(nesne.to_dict())))


def test_tool_wear_round_trip():
    ops, res, loads = _iki_hiz(False)
    w = mill_wear(ops, res, loads, malzeme(), KARBUR)[0]
    assert ToolWear.from_dict(w.to_dict()) == w
    assert _json_gidis_donus(w) == w


def test_tool_wear_round_trip_handmade():
    w = _tw(3, [(0, 0.5), (1, 0.4), (2, 0.3)])
    assert _json_gidis_donus(w) == w
    assert all(isinstance(s, StepWear) for s in _json_gidis_donus(w).steps)
    assert _json_gidis_donus(w.steps[0]) == w.steps[0]


@pytest.mark.parametrize(
    "a",
    [
        ChangeAdvice(tool_id=3, kind="kenar", parts_per_edge=4, at_op=None, sister_id=None, D_part=0.1875),
        ChangeAdvice(tool_id=3, kind="kenar", parts_per_edge=None, at_op=1, sister_id=None, D_part=1.2),
        ChangeAdvice(tool_id=3, kind="kardes", parts_per_edge=4, at_op=None, sister_id=7, D_part=0.1875),
        ChangeAdvice(
            tool_id=3, kind="gerek_yok", parts_per_edge=4, at_op=None, sister_id=None, D_part=0.1875
        ),
    ],
)
def test_change_advice_round_trip(a):
    assert ChangeAdvice.from_dict(a.to_dict()) == a
    assert _json_gidis_donus(a) == a


def test_advise_output_round_trip():
    lib = _lib(freze(3), freze(7))
    for a in advise([_tw(3, [(0, 0.1875)]), _tw(7, [(0, 0.6), (1, 0.6)])], lib, parts=20):
        assert _json_gidis_donus(a) == a
