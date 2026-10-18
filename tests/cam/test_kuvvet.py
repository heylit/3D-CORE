"""SPEC 32 K1, K2, K3, K7, K14 — Kienzle, kavrama, güç/tork, iş mili denetimi, malzeme dosyası.

Beklenen değerler SPEC 32 "Teori" kapalı formlarından ve sayısal örneklerinden (kaynak: Kienzle & Victor 1957;
König & Klocke, Fertigungsverfahren 1; Sandvik Coromant, Metal cutting technical guide). Uydurma malzeme.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pytest

from cam.kuvvet import (
    KienzleMaterial,
    Load,
    SpindleLimits,
    check_spindle,
    cutting_power,
    engagement_angle,
    kienzle_force,
    load_materials,
    max_chip_thickness,
    mean_chip_thickness,
    milling_loads,
    specific_force,
    spindle_torque,
    turning_force,
)
from cam.model import CamError
from cam.sim import simulate
from tests.cam.kuvvet_ref import (
    CELL,
    FZ,
    KC11,
    MC,
    REL_IZGARA,
    STOCK,
    TABLO,
    D,
    N,
    kanal_programi,
    malzeme,
    yan_programi,
    yuk,
)

ORNEK = Path(__file__).resolve().parents[2] / "examples" / "kienzle_malzemeler.json"


# ------------------------------------------------------------------ K1 Kienzle


def test_k1_torna_sayisal_ornegi():
    mat = malzeme()
    # SPEC 32 Teori: kc1.1 = 1500, mc = 0.25, ap = 2, f = 0.2, κr = 90° → Fc = 897.2093 N
    Fc = 1500.0 * 2.0 * 0.2 ** (1 - 0.25)
    assert Fc == pytest.approx(897.2093, rel=1e-7)
    assert kienzle_force(mat, 2.0, 0.2) == pytest.approx(Fc, rel=1e-12)
    assert turning_force(mat, 2.0, 0.2) == pytest.approx(Fc, rel=1e-12)
    assert turning_force(mat, 2.0, 0.2, kappa_r=90.0) == pytest.approx(Fc, rel=1e-12)


def test_k1_ozgul_kesme_kuvveti():
    mat = malzeme()
    # kc(h) = K·kc11·h^(−mc); h = 1 mm → kc11
    assert specific_force(mat, 1.0) == pytest.approx(KC11, rel=1e-12)
    assert specific_force(mat, 0.2) == pytest.approx(KC11 * 0.2 ** (-MC), rel=1e-12)
    # numpy dizisi de kabul edilir
    h = np.array([0.05, 0.1, 0.2, 0.5])
    kc = np.asarray(specific_force(mat, h), dtype=float)
    assert kc.shape == h.shape
    np.testing.assert_allclose(kc, KC11 * h ** (-MC), rtol=1e-12)


def test_k1_mc_sifir_dogrusal():
    # mc = 0 → Fc = kc1.1·b·h (A·kc sabit)
    m0 = KienzleMaterial("sabit", 2000.0, 0.0)
    assert kienzle_force(m0, 3.0, 0.25) == pytest.approx(2000.0 * 3.0 * 0.25, rel=1e-12)
    assert specific_force(m0, 0.37) == pytest.approx(2000.0, rel=1e-12)


def test_k1_kappa_45_donusumu():
    mat = malzeme()
    # h = f·sin κr, b = ap/sin κr → Fc = kc11·ap·f^(1−mc)·(sin κr)^(−mc)
    s = math.sin(math.radians(45.0))
    ap, f = 2.0, 0.2
    beklenen = KC11 * (ap / s) * (f * s) ** (1 - MC)
    assert turning_force(mat, ap, f, kappa_r=45.0) == pytest.approx(beklenen, rel=1e-12)
    assert beklenen == pytest.approx(KC11 * ap * f ** (1 - MC) * s ** (-MC), rel=1e-12)
    assert turning_force(mat, ap, f, kappa_r=45.0) == pytest.approx(
        kienzle_force(mat, ap / s, f * s), rel=1e-12
    )


def test_k1_K_carpani_dogrusal():
    mat = malzeme()
    assert kienzle_force(mat, 2.0, 0.2, K=1.2) == pytest.approx(1.2 * kienzle_force(mat, 2.0, 0.2), rel=1e-12)
    assert specific_force(mat, 0.2, K=1.2) == pytest.approx(1.2 * specific_force(mat, 0.2), rel=1e-12)
    assert turning_force(mat, 2.0, 0.2, K=1.2) == pytest.approx(1.2 * turning_force(mat, 2.0, 0.2), rel=1e-12)


# ------------------------------------------------------------------ K2 kavrama


def test_k2_kavrama_acisi():
    assert engagement_angle(D, D) == pytest.approx(math.pi, rel=1e-12)
    assert engagement_angle(D / 2, D) == pytest.approx(math.pi / 2, rel=1e-12)
    assert engagement_angle(1.0, D) == pytest.approx(math.acos(0.8), rel=1e-12)


@pytest.mark.parametrize("ae", [10.0, 5.0, 1.0])
def test_k2_hm_hex_tablo(ae):
    hm_t, _, _, _, hex_t = TABLO[ae]
    phi = math.acos(1 - 2 * ae / D)
    hm = FZ * (2 * ae / D) / phi
    hx = FZ * math.sin(min(phi, math.pi / 2))
    assert mean_chip_thickness(FZ, ae, D) == pytest.approx(hm, rel=1e-12)
    assert max_chip_thickness(FZ, ae, D) == pytest.approx(hx, rel=1e-12)
    # tablo 6–7 anlamlı basamak
    assert mean_chip_thickness(FZ, ae, D) == pytest.approx(hm_t, rel=1e-6)
    assert max_chip_thickness(FZ, ae, D) == pytest.approx(hex_t, rel=1e-12)


def test_k2_hex_yarim_kavrama_ustu_fz():
    # ae ≥ D/2 → hex = fz; değilse hex = 2·fz·√(a(1 − a))
    for ae in (5.0, 6.5, 10.0):
        assert max_chip_thickness(FZ, ae, D) == pytest.approx(FZ, rel=1e-12)
    for ae in (0.3, 1.0, 2.5, 4.9):
        a = ae / D
        assert max_chip_thickness(FZ, ae, D) == pytest.approx(2 * FZ * math.sqrt(a * (1 - a)), rel=1e-12)


@pytest.mark.parametrize("ae", [0.5, 1.0, 2.5, 5.0, 7.5, 10.0])
def test_k2_hm_sayisal_ortalama(ae):
    # hm = ∫₀^φe fz·sin φ dφ / φe, yoğun sayısal ortalama (trapez, 2·10⁵ nokta)
    phi = engagement_angle(ae, D)
    p = np.linspace(0.0, phi, 200_001)
    h = FZ * np.sin(p)
    sayisal = float(np.sum((h[1:] + h[:-1]) / 2 * np.diff(p))) / phi
    assert mean_chip_thickness(FZ, ae, D) == pytest.approx(sayisal, rel=1e-9)


# ------------------------------------------------------------------ K3 güç ve tork


@pytest.mark.parametrize("ae", [10.0, 5.0, 1.0])
def test_k3_guc_tork_tablo(ae):
    mat = malzeme()
    hm_t, Q, P_t, M_t, _ = TABLO[ae]
    kc = specific_force(mat, mean_chip_thickness(FZ, ae, D))
    P = cutting_power(Q, kc)
    assert P == pytest.approx(P_t, rel=1e-6)
    assert spindle_torque(P, N) == pytest.approx(M_t, rel=1e-6)
    # tanımlar: P = Q·kc/10⁶, M = 60000·P/(2πn)
    assert P == pytest.approx(Q * kc / 1e6, rel=1e-12)
    assert spindle_torque(P, N) == pytest.approx(60000 * P / (2 * math.pi * N), rel=1e-12)


def test_k3_torna_guc_esitligi():
    mat = malzeme()
    # Tornada Q = vc·ap·f → Q·kc/10⁶ = Fc·Vc/60000 (Teori: P = 2.99070 kW)
    Vc, ap, f = 200.0, 2.0, 0.2
    Q = Vc * 1000 / 60 * ap * f  # mm³/s
    kc = specific_force(mat, f)  # κr = 90° → h = f
    Fc = turning_force(mat, ap, f)
    assert cutting_power(Q, kc) == pytest.approx(Fc * Vc / 60000, rel=1e-12)
    assert cutting_power(Q, kc) == pytest.approx(2.99070, rel=1e-5)
    # çap 50'de n = 1000·Vc/(π·50) → M = Fc·25/1000 = 22.4302 N·m
    n = 1000 * Vc / (math.pi * 50.0)
    assert spindle_torque(cutting_power(Q, kc), n) == pytest.approx(Fc * 25 / 1000, rel=1e-12)
    assert spindle_torque(cutting_power(Q, kc), n) == pytest.approx(22.4302, rel=1e-5)


# ------------------------------------------------------------------ K7 iş mili denetimi


def _yuk(k: int, P: float, M: float, move: int | None = 0) -> Load:
    return Load(
        k=k, op=0, move=move, kind="kesme", ap=3.0, ae=10.0, h=0.06, kc=3000.0, Q=450.0, P=P, M=M, F_t=800.0
    )


def test_k7_eta_ve_sinir():
    loads = [_yuk(1, 1.2, 4.0), _yuk(2, 0.5, 1.0, move=1)]
    # η = 0.8: istenen P/η = 1.5
    ov = check_spindle(loads, SpindleLimits(P_max=1.4, eta=0.8))
    assert [(o.k, o.kind) for o in ov] == [(1, "guc")]
    assert ov[0].value == pytest.approx(1.2 / 0.8, rel=1e-12)
    assert ov[0].limit == pytest.approx(1.4, rel=1e-12)
    assert ov[0].op == 0 and ov[0].move == 0
    assert check_spindle(loads, SpindleLimits(P_max=1.6, eta=0.8)) == []
    # η = 1 → value = P
    ov = check_spindle(loads, SpindleLimits(P_max=1.0, eta=1.0))
    assert [(o.k, o.kind) for o in ov] == [(1, "guc")]
    assert ov[0].value == pytest.approx(1.2, rel=1e-12)


def test_k7_tork_ve_ikisi_birden():
    loads = [_yuk(1, 1.2, 4.0), _yuk(2, 0.5, 1.0, move=1), _yuk(3, 2.0, 6.0, move=2)]
    ov = check_spindle(loads, SpindleLimits(M_max=3.0, eta=1.0))
    assert [(o.k, o.kind) for o in ov] == [(1, "tork"), (3, "tork")]
    assert ov[1].value == pytest.approx(6.0, rel=1e-12)
    assert ov[1].limit == pytest.approx(3.0, rel=1e-12)
    ov = check_spindle(loads, SpindleLimits(P_max=1.0, M_max=5.0, eta=1.0))
    assert sorted((o.k, o.kind) for o in ov) == [(1, "guc"), (3, "guc"), (3, "tork")]
    assert [o.k for o in ov] == sorted(o.k for o in ov)  # k sırasıyla


def test_k7_none_sinir_denetlenmez():
    loads = [_yuk(1, 100.0, 1000.0)]
    assert check_spindle(loads, SpindleLimits()) == []
    assert check_spindle(loads, SpindleLimits(P_max=None, M_max=None, eta=0.5)) == []
    lim = SpindleLimits()
    assert lim.P_max is None and lim.M_max is None
    assert lim.eta == pytest.approx(0.8)  # onaylı varsayılan


def test_k7_esitlik_kayit_degil():
    # value > limit·(1 + tol) olanlar kaydedilir; tam sınırda kayıt yok
    loads = [_yuk(1, 1.0, 2.0)]
    assert check_spindle(loads, SpindleLimits(P_max=1.0, M_max=2.0, eta=1.0)) == []
    assert check_spindle([_yuk(1, 1.0 + 1e-12, 2.0)], SpindleLimits(P_max=1.0, eta=1.0)) == []
    assert len(check_spindle([_yuk(1, 1.0 + 1e-6, 2.0)], SpindleLimits(P_max=1.0, eta=1.0))) == 1


def test_k7_hava_ve_atlandi_kayit_vermez():
    loads = [
        Load(k=1, op=0, move=0, kind="hava", ap=0.0, ae=None, h=None, kc=None, Q=0.0, P=0.0, M=0.0, F_t=None),
        Load(
            k=2,
            op=1,
            move=None,
            kind="atlandi",
            ap=0.0,
            ae=None,
            h=None,
            kc=None,
            Q=0.0,
            P=0.0,
            M=0.0,
            F_t=None,
        ),
    ]
    assert check_spindle(loads, SpindleLimits(P_max=1e-6, M_max=1e-6, eta=1.0)) == []


def test_k7_kanal_simulasyondan():
    mat = malzeme()
    # K4 kanalı, P_max = 1.0 kW, η = 1 → tek "guc" kaydı (value = 1.343797, limit = 1.0)
    tp, ix = kanal_programi()
    res = simulate([tp], STOCK, cell=CELL)
    loads = milling_loads([tp], res, mat)
    kanal = yuk(loads, 0, ix["kanal"])
    ov = check_spindle(loads, SpindleLimits(P_max=1.0, eta=1.0))
    assert len(ov) == 1
    o = ov[0]
    assert (o.kind, o.op, o.move, o.k) == ("guc", 0, ix["kanal"], kanal.k)
    assert o.value == pytest.approx(kanal.P, rel=1e-12)
    assert o.value == pytest.approx(TABLO[10.0][2], rel=REL_IZGARA)
    assert o.limit == pytest.approx(1.0, rel=1e-12)
    # M_max = 4.0 N·m (kanal M = 4.277439) → tek "tork" kaydı
    ov = check_spindle(loads, SpindleLimits(M_max=4.0, eta=1.0))
    assert [(o.kind, o.move) for o in ov] == [("tork", ix["kanal"])]
    # η = 0.8 değeri P/0.8 yapar
    ov = check_spindle(loads, SpindleLimits(P_max=1.0, eta=0.8))
    o = [o for o in ov if o.move == ix["kanal"]][0]
    assert o.value == pytest.approx(kanal.P / 0.8, rel=1e-12)


def test_k7_yan_ae5_kayit_yok():
    mat = malzeme()
    # K5 ae = 5 pasosu (P = 0.671899) P_max = 1.0'ı aşmaz; programda yalnız kanal kayıt verir
    tp, ix = yan_programi()
    res = simulate([tp], STOCK, cell=CELL)
    loads = milling_loads([tp], res, mat)
    ov = check_spindle(loads, SpindleLimits(P_max=1.0, eta=1.0))
    assert {(o.op, o.move) for o in ov} == {(0, ix["kanal"])}


def test_k7_from_profile():
    # A0 arayüz eki: MachineProfile.spindle_power_kw / spindle_torque_nm (S1, None → denetlenmez)
    import cam.model as cm

    MP = getattr(cm, "MachineProfile", None)
    if MP is None or not {"spindle_power_kw", "spindle_torque_nm"} <= {
        f.name for f in dataclasses.fields(MP)
    }:
        pytest.skip("A0 arayüz eki (MachineProfile.spindle_power_kw / spindle_torque_nm) bu dalda yok")
    p = MP(name="DENEME", controller="fanuc", rpm_max=12000.0, feed_max=10000.0, spindle_power_kw=15.0,
           spindle_torque_nm=95.0)  # fmt: skip
    lim = SpindleLimits.from_profile(p)
    assert lim.P_max == pytest.approx(15.0)
    assert lim.M_max == pytest.approx(95.0)
    assert lim.eta == pytest.approx(0.8)
    assert SpindleLimits.from_profile(p, eta=0.9).eta == pytest.approx(0.9)
    q = MP(name="DENEME", controller="fanuc", rpm_max=12000.0, feed_max=10000.0)
    lim = SpindleLimits.from_profile(q)
    assert lim.P_max is None and lim.M_max is None


# ------------------------------------------------------------------ K14 malzeme dosyası


def test_k14_ornek_dosya():
    mats = load_materials(ORNEK)
    assert len(mats) >= 1
    ham = json.loads(ORNEK.read_text(encoding="utf-8"))["malzemeler"]
    assert set(mats) == {m["name"] for m in ham}
    for ad, m in mats.items():
        assert isinstance(m, KienzleMaterial)
        assert m.name == ad
        assert m.kc11 > 0 and 0 <= m.mc < 1
    assert load_materials(str(ORNEK)).keys() == mats.keys()  # str yol da kabul


def _yaz(tmp_path: Path, veri, ad: str = "m.json") -> Path:
    p = tmp_path / ad
    if isinstance(veri, str):
        p.write_text(veri, encoding="utf-8")
    else:
        p.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return p


def _m(**kw) -> dict:
    d = {"name": "Çelik-ğüş", "kc11": 1700.0, "mc": 0.2, "kaynak": "uydurma, Türkçe karakterli"}
    d.update(kw)
    return d


def test_k14_utf8(tmp_path):
    mats = load_materials(_yaz(tmp_path, {"malzemeler": [_m(), _m(name="İkinci", mc=0.0)]}))
    assert mats["Çelik-ğüş"] == KienzleMaterial("Çelik-ğüş", 1700.0, 0.2)
    assert mats["İkinci"].mc == 0.0


@pytest.mark.parametrize(
    "kayit",
    [
        {k: v for k, v in _m().items() if k != "kaynak"},  # kaynak eksik
        _m(mc=1.0),
        _m(mc=1.5),
        _m(mc=-0.1),
        _m(kc11=0.0),
        _m(kc11=-100.0),
        _m(renk="mavi"),  # bilinmeyen anahtar
        {k: v for k, v in _m().items() if k != "kc11"},
    ],
)
def test_k14_hatali_kayit(tmp_path, kayit):
    with pytest.raises(CamError):
        load_materials(_yaz(tmp_path, {"malzemeler": [kayit]}))


def test_k14_yinelenen_ad(tmp_path):
    with pytest.raises(CamError):
        load_materials(_yaz(tmp_path, {"malzemeler": [_m(), _m(kc11=1800.0)]}))


def test_k14_bozuk_json_ve_dosya_yok(tmp_path):
    with pytest.raises(CamError):
        load_materials(_yaz(tmp_path, '{"malzemeler": [ {"name": "a", '))
    with pytest.raises(CamError):
        load_materials(tmp_path / "yok.json")


def test_k14_gidis_donus():
    m = KienzleMaterial("C45E", 1680.0, 0.14)
    d = m.to_dict()
    assert KienzleMaterial.from_dict(d) == m
    assert KienzleMaterial.from_dict(json.loads(json.dumps(d))) == m
    with pytest.raises(CamError):
        KienzleMaterial.from_dict({**d, "renk": "mavi"})
