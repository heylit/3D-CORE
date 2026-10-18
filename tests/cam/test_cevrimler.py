"""SPEC 04b — punta, havşa ve kılavuz hesapları, op'lar ve kanonik açılım (K1–K7).

Testler yalnız SPEC 04b metninden (Teori, Arayüz, Kabul kriterleri, Örnek A / B) ve A0 arayüz ekinden
yazıldı; `cam/cevrimler.py` uygulaması okunmadı.

Formüller (Teori):
    punta   h_s = (d_s / 2) · cot(σ / 2)                 0 < d_s ≤ D
    havşa   h_c = (D_h − d_t) / 2 · cot(α / 2)           |α − α_h| ≤ 1e-9°, D_h ≤ D, d_t < d, D_h > d
    kılavuz h_t = t_d + lead · P;  F = S · P, S = round(rpm), S·P·10^fd tam sayı olmalı
Açılım: G82 = G81 hareketleri; G84 = G0 xy → G0 r → G1 z → G1 r (aynı F) → G0 z_dön; sıfır boylu hareket yok.
Gruplama: delikler giriş sırası korunarak (z_top, h) ile gruplanır, op adı `<ad>-<k>` (k 1 tabanlı).
Varsayım (SPEC'te açık değil): "mesajda delik sırası" 1 tabanlıdır (op adlarındaki k gibi).
"""

from __future__ import annotations

import dataclasses
import math
import re

import numpy as np
import pytest

from cam.cevrimler import (
    DwellDrillOp,
    TapOp,
    chamfer_depth,
    chamfer_ops,
    spot_depth,
    spot_ops,
    tap_depth,
    tap_feed,
    tap_ops,
    tap_rpm,
)
from cam.gcode import DrillOp
from cam.model import CamError
from geometry.part import Hole
from tests.cam.cevrimler_ortak import (
    G0,
    G1,
    HOLES3,
    START,
    assert_moves,
    disli,
    duz,
    egik,
    freze,
    havsa,
    havsali,
    kilavuz,
    matkap,
    ornek_a,
    ornek_b,
    punta,
)

REL = 1e-12

# ISO 261 / ISO 724 kaba hatve (SPEC 23 THREADS_COARSE ile aynı olmalı; OCCT'li testte karşılaştırılır)
ISO_KABA = {
    "M3": 0.5,
    "M4": 0.7,
    "M5": 0.8,
    "M6": 1.0,
    "M8": 1.25,
    "M10": 1.5,
    "M12": 1.75,
    "M14": 2.0,
    "M16": 2.0,
    "M20": 2.5,
    "M24": 3.0,
}


def sira_var(mesaj: str, n: int) -> bool:
    """Mesajda `n` ayrı bir sayı olarak geçiyor mu (12 içindeki 2 sayılmaz)."""
    return re.search(rf"(?<![\d.]){n}(?![\d.])", mesaj) is not None


# ---------------------------------------------------------------- K1: punta derinliği


def test_K1_spot_depth_90():
    """K1: σ = 90°, d_s = 6 → h_s = 3."""
    assert spot_depth(punta(90.0), 6.0) == pytest.approx(3.0, rel=REL)


def test_K1_spot_depth_120():
    """K1: σ = 120°, d_s = 6 → h_s = 3·cot 60° = √3."""
    assert spot_depth(punta(120.0), 6.0) == pytest.approx(math.sqrt(3.0), rel=REL)


def test_K1_spot_depth_full_diameter():
    """Sınır: d_s = D geçer (iz takımın konisine tam sığar), σ = 90° → D/2."""
    assert spot_depth(punta(90.0, D=10.0), 10.0) == pytest.approx(5.0, rel=REL)


@pytest.mark.parametrize("d_s", [10.0001, 12.0, 0.0, -1.0, math.nan, math.inf])
def test_K1_spot_depth_bad_diameter(d_s):
    """K1: d_s > D, d_s ≤ 0, nan / inf → CamError."""
    with pytest.raises(CamError):
        spot_depth(punta(90.0, D=10.0), d_s)


@pytest.mark.parametrize("yap", [matkap, freze, havsa, kilavuz], ids=["DRILL", "FLAT", "CHAMFER", "TAP"])
def test_K1_spot_depth_wrong_tool(yap):
    """K1: SPOT olmayan takım → CamError."""
    with pytest.raises(CamError):
        spot_depth(yap(), 3.0)


# ---------------------------------------------------------------- K2: havşa derinliği


def test_K2_chamfer_depth_90():
    """K2: α = 90°, D_h = 12, d_t = 2 → h_c = (12 − 2)/2 · cot 45° = 5."""
    assert chamfer_depth(havsa(90.0, tip_d=2.0), 12.0, 90.0, 6.6) == pytest.approx(5.0, rel=REL)


def test_K2_chamfer_depth_82():
    """K2: α = 82°, aynı ölçüler → h_c = 5·cot 41° = 5.751842036..."""
    h = chamfer_depth(havsa(82.0, tip_d=2.0), 12.0, 82.0, 6.6)
    assert h == pytest.approx(5.0 / math.tan(math.radians(41.0)), rel=REL)
    assert h == pytest.approx(5.751842036, abs=1e-9)


def test_K2_chamfer_depth_sharp_tip():
    """K2: d_t = 0 sivri uç: h_c = D_h/2 · cot(α/2) = 6 (α = 90°)."""
    assert chamfer_depth(havsa(90.0, tip_d=0.0), 12.0, 90.0, 6.6) == pytest.approx(6.0, rel=REL)


def test_K2_chamfer_angle_within_tolerance():
    """|α − α_h| ≤ 1e-9° kabul edilir."""
    h = chamfer_depth(havsa(90.0, tip_d=2.0), 12.0, 90.0 + 1e-10, 6.6)
    assert h == pytest.approx(5.0, rel=1e-9)


@pytest.mark.parametrize(
    "csk_d, csk_angle, d",
    [
        pytest.param(12.0, 90.5, 6.6, id="aci-farki"),
        pytest.param(12.0, 82.0, 6.6, id="aci-82-takim-90"),
        pytest.param(16.0001, 90.0, 6.6, id="D_h>D"),
        pytest.param(12.0, 90.0, 2.0, id="d_t=d"),
        pytest.param(12.0, 90.0, 1.9, id="d_t>d"),
        pytest.param(6.6, 90.0, 6.6, id="D_h=d"),
        pytest.param(6.0, 90.0, 6.6, id="D_h<d"),
        pytest.param(math.nan, 90.0, 6.6, id="nan"),
    ],
)
def test_K2_chamfer_depth_errors(csk_d, csk_angle, d):
    """K2: açı farkı, D_h > D, d_t ≥ d, D_h ≤ d, nan → CamError (takım D = 16, d_t = 2, α = 90°)."""
    with pytest.raises(CamError):
        chamfer_depth(havsa(90.0, tip_d=2.0, D=16.0), csk_d, csk_angle, d)


def test_K2_chamfer_depth_full_diameter_passes():
    """Sınır: D_h = D geçer: (16 − 2)/2 = 7."""
    assert chamfer_depth(havsa(90.0, tip_d=2.0, D=16.0), 16.0, 90.0, 6.6) == pytest.approx(7.0, rel=REL)


@pytest.mark.parametrize("yap", [punta, matkap, kilavuz], ids=["SPOT", "DRILL", "TAP"])
def test_K2_chamfer_depth_wrong_tool(yap):
    with pytest.raises(CamError):
        chamfer_depth(yap(), 8.0, 90.0, 6.6)


# ---------------------------------------------------------------- K3: kılavuz ilerlemesi ve devri


def test_K3_tap_feed_exact():
    """K3: P = 1.25, S = 500 → F = 625."""
    assert tap_feed(500.0, 1.25, 1) == 625.0


def test_K3_tap_feed_rounds_rpm():
    """S = round(rpm): 500.4 → 500 → F = 625."""
    assert tap_feed(500.4, 1.25, 1) == pytest.approx(625.0, rel=REL)


def test_K3_tap_feed_not_writable():
    """K3: S = 333 → F = 416.25, 1 basamakla yazılamaz → CamError (yuvarlama kabul edilmez)."""
    with pytest.raises(CamError):
        tap_feed(333.0, 1.25, 1)


def test_K3_tap_feed_decimals_parameter():
    """fd = 2'de 416.25 tam yazılır; fd = 0'da 625 yazılır, 415.0 (S = 332) da."""
    assert tap_feed(333.0, 1.25, 2) == pytest.approx(416.25, rel=REL)
    assert tap_feed(332.0, 1.25, 0) == pytest.approx(415.0, rel=REL)
    with pytest.raises(CamError):
        tap_feed(330.0, 1.25, 0)  # 412.5


@pytest.mark.parametrize("rpm, P", [(math.nan, 1.25), (500.0, math.inf), (500.0, math.nan)])
def test_K3_tap_feed_nonfinite(rpm, P):
    with pytest.raises(CamError):
        tap_feed(rpm, P, 1)


def test_K3_tap_rpm_example():
    """K3: tap_rpm(333, 1.25, 1) = 332 (F = 415)."""
    S = tap_rpm(333.0, 1.25, 1)
    assert S == 332
    assert isinstance(S, int)
    assert tap_feed(S, 1.25, 1) == pytest.approx(415.0, rel=REL)


def test_K3_tap_rpm_already_writable():
    """n koşulu zaten sağlıyorsa n'nin kendisi: tap_rpm(500, 1.25, 1) = 500."""
    assert tap_rpm(500.0, 1.25, 1) == 500


def test_K3_tap_rpm_decimals_zero():
    """fd = 0, P = 0.7: S·0.7 tam sayı ↔ S 10'un katı → tap_rpm(333, 0.7, 0) = 330."""
    assert tap_rpm(333.0, 0.7, 0) == 330


def test_K3_tap_rpm_none():
    """S ≥ 1 yoksa CamError: n < 1."""
    with pytest.raises(CamError):
        tap_rpm(0.5, 1.25, 1)
    with pytest.raises(CamError):
        tap_rpm(3.0, 1.25, 0)  # S ∈ {1, 2, 3}: 1.25, 2.5, 3.75 → hiçbiri tam değil


def _yazilir(S: int, P: float, fd: int) -> bool:
    v = S * P * 10**fd
    return abs(v - round(v)) <= 1e-9


@pytest.mark.parametrize("ad, P", list(ISO_KABA.items()))
def test_K3_iso_coarse_table(ad, P):
    """K3: her ISO kaba hatve için S = tap_rpm(1000, P, 1): 1 ≤ S ≤ 1000, koşul sağlanıyor, en büyük,
    F / S = P (rel 1e-12)."""
    S = tap_rpm(1000.0, P, 1)
    assert isinstance(S, int)
    assert 1 <= S <= 1000
    assert _yazilir(S, P, 1)
    assert not any(_yazilir(s, P, 1) for s in range(S + 1, 1001))  # en büyük
    F = tap_feed(S, P, 1)
    assert F / S == pytest.approx(P, rel=REL)


@pytest.mark.occt
def test_K3_iso_table_matches_spec23():
    """Yukarıdaki tablo SPEC 23 THREADS_COARSE ile aynı."""
    from geometry.holes import THREADS_COARSE

    assert dict(THREADS_COARSE) == ISO_KABA


# ---------------------------------------------------------------- K4: kılavuz derinliği


def test_K4_tap_depth_m8():
    """K4: M8 (P = 1.25, lead = 3), t_d = 12 → h_t = 12 + 3·1.25 = 15.75."""
    assert tap_depth(kilavuz(), 12.0) == pytest.approx(15.75, rel=REL)


@pytest.mark.parametrize("t_d", [0.0, -1.0, math.nan])
def test_K4_tap_depth_bad(t_d):
    with pytest.raises(CamError):
        tap_depth(kilavuz(), t_d)


@pytest.mark.parametrize("yap", [punta, matkap, havsa], ids=["SPOT", "DRILL", "CHAMFER"])
def test_K4_tap_depth_wrong_tool(yap):
    with pytest.raises(CamError):
        tap_depth(yap(), 12.0)


def test_K4_blind_depth_16_passes():
    """K4: kör delik depth = 16 ≥ h_t = 15.75 → op, z = −15.75, r = 2."""
    (op,) = tap_ops([disli(10.0, 10.0, depth=16.0, thread_depth=12.0)], kilavuz(), 500.0, START)
    assert op.z == pytest.approx(-15.75, rel=REL)
    assert op.r == pytest.approx(2.0, rel=REL)


def test_K4_blind_depth_15_7_raises():
    """K4: depth = 15.7 < 15.75 → kılavuz dibe vurur: CamError."""
    with pytest.raises(CamError):
        tap_ops([disli(10.0, 10.0, depth=15.7, thread_depth=12.0)], kilavuz(), 500.0, START)


def test_K4_through_hole_exits_below():
    """K4: boydan boya delikte t_d = depth = 20 → h_t = depth + 3.75 = 23.75."""
    h = disli(10.0, 10.0, depth=20.0, thread_depth=20.0, through=True)
    (op,) = tap_ops([h], kilavuz(), 500.0, START)
    assert op.z == pytest.approx(-(20.0 + 3.75), rel=REL)


def test_K4_tap_longer_than_flutes():
    """Teori: h_t ≤ flute_length (25). Boydan boya t_d = 22 → h_t = 25.75 > 25 → CamError."""
    h = disli(10.0, 10.0, depth=22.0, thread_depth=22.0, through=True)
    with pytest.raises(CamError):
        tap_ops([h], kilavuz(), 500.0, START)


# ---------------------------------------------------------------- K5: delik kaydından op (elle kurulmuş Hole)


def test_K5_spot_ops_grouping_by_top():
    """K5: iki üst yüz (0 ve −5), d_s = 6 → h_s = 3: iki op, giriş sırası korunur."""
    holes = [duz(10, 10, 0.0), duz(20, 20, -5.0), duz(30, 10, 0.0), duz(40, 40, -5.0)]
    ops = spot_ops(holes, punta(), 2000.0, 200.0, START, d_s=6.0)
    assert [op.name for op in ops] == ["punta-1", "punta-2"]
    a, b = ops
    assert all(isinstance(op, DwellDrillOp) for op in ops)
    assert a.holes == [(10.0, 10.0), (30.0, 10.0)]
    assert b.holes == [(20.0, 20.0), (40.0, 40.0)]
    assert (a.z, a.r) == (pytest.approx(-3.0, rel=REL), pytest.approx(2.0, rel=REL))
    assert (b.z, b.r) == (pytest.approx(-8.0, rel=REL), pytest.approx(-3.0, rel=REL))
    for op in ops:
        assert op.kind == "G82"
        assert op.rpm == 2000.0 and op.feed == 200.0
        assert op.dwell == pytest.approx(0.2)  # varsayılan
        assert op.retract == "G98"
        assert tuple(op.start) == START
        op.validate()


def test_K5_spot_default_diameter_is_drill_diameter():
    """d_s = None → her delikte Hole.d: d = 6.6 ve 6.75 → h_s = 3.3 ve 3.375 (σ = 90°), iki grup."""
    holes = [duz(10, 10, d=6.6), duz(20, 10, d=6.75), duz(30, 10, d=6.6)]
    ops = spot_ops(holes, punta(), 2000.0, 200.0, START)
    assert [op.holes for op in ops] == [[(10.0, 10.0), (30.0, 10.0)], [(20.0, 10.0)]]
    assert ops[0].z == pytest.approx(-3.3, rel=REL)
    assert ops[1].z == pytest.approx(-3.375, rel=REL)


def test_K5_spot_default_diameter_too_big():
    """d_s = Hole.d = 12 > D = 10 → CamError."""
    with pytest.raises(CamError):
        spot_ops([duz(10, 10, d=12.0)], punta(D=10.0), 2000.0, 200.0, START)


def test_K5_parameters_passed():
    """r_clear, retract, dwell, name parametreleri op'a geçer."""
    (op,) = spot_ops(
        [duz(10, 10, 1.0)],
        punta(),
        2000.0,
        150.0,
        START,
        d_s=6.0,
        dwell=0.5,
        name="p",
        r_clear=3.0,
        retract="G99",
    )
    assert op.name == "p-1"
    assert op.r == pytest.approx(4.0, rel=REL)
    assert op.z == pytest.approx(-2.0, rel=REL)
    assert op.dwell == 0.5 and op.retract == "G99" and op.feed == 150.0


def test_K5_chamfer_ops():
    """K5: havşa D_h = 12, α = 90°, takım d_t = 2 → h_c = 5: z = −5, r = 2."""
    holes = [havsali(10, 10), havsali(30, 10), havsali(50, 10, z_top=-4.0)]
    ops = chamfer_ops(holes, havsa(), 1500.0, 100.0, START)
    assert [op.name for op in ops] == ["havsa-1", "havsa-2"]
    assert ops[0].holes == [(10.0, 10.0), (30.0, 10.0)]
    assert ops[1].holes == [(50.0, 10.0)]
    assert ops[0].z == pytest.approx(-5.0, rel=REL)
    assert ops[1].z == pytest.approx(-9.0, rel=REL)
    assert ops[1].r == pytest.approx(-2.0, rel=REL)
    for op in ops:
        assert isinstance(op, DwellDrillOp)
        assert op.kind == "G82"
        assert op.dwell == pytest.approx(0.2)
        op.validate()


def test_K5_chamfer_blind_too_shallow():
    """Teori: kör delikte h_c ≤ depth; h_c = 5 > depth = 4 → CamError."""
    with pytest.raises(CamError):
        chamfer_ops([havsali(10, 10, depth=4.0, through=False)], havsa(), 1500.0, 100.0, START)


def test_K5_chamfer_angle_mismatch():
    """Havşa 82°, takım 90° → CamError."""
    with pytest.raises(CamError):
        chamfer_ops([havsali(10, 10, csk_angle=82.0)], havsa(90.0), 1500.0, 100.0, START)


def test_K5_chamfer_hole_without_countersink():
    """K5: havşasız delik (csk_d = 0) → CamError."""
    with pytest.raises(CamError):
        chamfer_ops([havsali(10, 10), duz(30, 10)], havsa(), 1500.0, 100.0, START)


def test_K5_tap_ops():
    """K5: iki üst yüz → iki TapOp; z = z_top − 15.75, r = z_top + 2, F = 625."""
    holes = [disli(10, 10, 0.0), disli(20, 20, 3.0), disli(30, 10, 0.0)]
    ops = tap_ops(holes, kilavuz(), 500.0, START)
    assert [op.name for op in ops] == ["kilavuz-1", "kilavuz-2"]
    assert ops[0].holes == [(10.0, 10.0), (30.0, 10.0)]
    assert ops[1].holes == [(20.0, 20.0)]
    assert ops[0].z == pytest.approx(-15.75, rel=REL)
    assert ops[1].z == pytest.approx(3.0 - 15.75, rel=REL)
    assert ops[1].r == pytest.approx(5.0, rel=REL)
    for op in ops:
        assert isinstance(op, TapOp)
        assert op.kind == "G84"
        assert op.rpm == 500.0
        assert op.feed == 625.0
        op.validate()


def test_K5_tap_hole_without_thread():
    with pytest.raises(CamError):
        tap_ops([disli(10, 10), duz(30, 10)], kilavuz(), 500.0, START)


def test_K5_tap_diameter_mismatch():
    """Takım M10 (D = 10, P = 1.5), delik M8 → CamError."""
    with pytest.raises(CamError):
        tap_ops([disli(10, 10)], kilavuz(D=10.0, pitch=1.5, name="M10"), 500.0, START)


def test_K5_tap_pitch_mismatch():
    """Delik M8x1 (P = 1), takım P = 1.25 → CamError."""
    with pytest.raises(CamError):
        tap_ops([disli(10, 10, thread="M8x1", P=1.0)], kilavuz(), 500.0, START)


def test_K5_tap_rpm_not_writable():
    """rpm 333 → F = 416.25 yazılamaz → CamError (op üretiminde veya validate'te)."""
    with pytest.raises(CamError):
        for op in tap_ops([disli(10, 10)], kilavuz(), 333.0, START):
            op.validate()


def _egik_kayit(tur: str) -> Hole:
    """İşlem türüne uygun (havşalı / dişli) ama düşey olmayan delik kaydı: eksen düşeyden 30° yatık."""
    if tur == "spot":
        return egik(30, 10)
    a = math.radians(30.0)
    eksen = (0.0, math.sin(a), -math.cos(a))
    if tur == "chamfer":
        return Hole(
            origin=(30, 10, 0), axis=eksen, d=6.6, depth=20.0, through=True, csk_d=12.0, csk_angle=90.0
        )
    return Hole(
        origin=(30, 10, 0),
        axis=eksen,
        d=6.75,
        depth=16.0,
        through=False,
        thread="M8",
        thread_d=8.0,
        pitch=1.25,
        thread_depth=12.0,
    )


_ISLEM = {
    "spot": (lambda hs: spot_ops(hs, punta(), 2000.0, 200.0, START, d_s=6.0), lambda: duz(10, 10)),
    "chamfer": (lambda hs: chamfer_ops(hs, havsa(), 1500.0, 100.0, START), lambda: havsali(10, 10)),
    "tap": (lambda hs: tap_ops(hs, kilavuz(), 500.0, START), lambda: disli(10, 10)),
}


@pytest.mark.parametrize("tur", list(_ISLEM))
def test_K5_inclined_hole(tur):
    """K5: düşey olmayan delik (2. sırada) → CamError, mesajda delik sırası (1 tabanlı: 2)."""
    fn, duzgun = _ISLEM[tur]
    fn([duzgun()])  # düşey delikle geçer
    with pytest.raises(CamError) as e:
        fn([duzgun(), _egik_kayit(tur), duzgun()])
    assert sira_var(str(e.value), 2), str(e.value)


@pytest.mark.parametrize(
    "fn",
    [
        pytest.param(lambda: spot_ops([], punta(), 2000.0, 200.0, START), id="spot"),
        pytest.param(lambda: chamfer_ops([], havsa(), 1500.0, 100.0, START), id="chamfer"),
        pytest.param(lambda: tap_ops([], kilavuz(), 500.0, START), id="tap"),
    ],
)
def test_K5_empty_list(fn):
    with pytest.raises(CamError):
        fn()


# ---------------------------------------------------------------- K5: OCCT ile üretilmiş delik kayıtları


@pytest.mark.occt
def test_K5_from_spec23_part():
    """K5: SPEC 23 `tapped_hole` + `countersink_hole` ile iki uydurma blokta (üst yüz 20 ve 12):
    punta, havşa ve kılavuz op'ları beklenen z, r, XY ve gruplamayı veriyor (sıra korunmuş)."""
    from geometry.features import block
    from geometry.holes import countersink_hole, tapped_hole

    p1 = tapped_hole(block(100.0, 60.0, 20.0), 20.0, 20.0, "M8", depth=16.0, thread_depth=12.0)
    p1 = countersink_hole(p1, 50.0, 20.0, d=6.6, csk_d=12.0, csk_angle=90.0)
    p1 = tapped_hole(p1, 70.0, 40.0, "M8", depth=16.0, thread_depth=12.0)
    p2 = tapped_hole(block(100.0, 60.0, 12.0), 30.0, 30.0, "M8")  # boydan boya, t_d = 12
    p2 = countersink_hole(p2, 60.0, 30.0, d=6.6, csk_d=12.0, csk_angle=90.0)
    t1a, c1, t1b = p1.holes
    t2, c2 = p2.holes
    assert t1a.origin[2] == pytest.approx(20.0) and t2.origin[2] == pytest.approx(12.0)

    # punta: tüm delikler, d_s = 6 → h_s = 3; sıra t1a, t2, c1, c2, t1b
    # → grup üst 20: t1a, c1, t1b; üst 12: t2, c2
    ops = spot_ops([t1a, t2, c1, c2, t1b], punta(), 2000.0, 200.0, (0.0, 0.0, 30.0), d_s=6.0)
    assert [op.name for op in ops] == ["punta-1", "punta-2"]
    assert ops[0].holes == [(20.0, 20.0), (50.0, 20.0), (70.0, 40.0)]
    assert ops[1].holes == [(30.0, 30.0), (60.0, 30.0)]
    assert ops[0].z == pytest.approx(17.0, rel=REL) and ops[0].r == pytest.approx(22.0, rel=REL)
    assert ops[1].z == pytest.approx(9.0, rel=REL) and ops[1].r == pytest.approx(14.0, rel=REL)

    # havşa: c1, c2 → h_c = 5
    ops = chamfer_ops([c2, c1], havsa(), 1500.0, 100.0, (0.0, 0.0, 30.0))
    assert [op.holes for op in ops] == [[(60.0, 30.0)], [(50.0, 20.0)]]
    assert ops[0].z == pytest.approx(7.0, rel=REL) and ops[1].z == pytest.approx(15.0, rel=REL)

    # kılavuz: t1a, t1b kör (depth 16 ≥ 15.75), t2 boydan boya (h_t = 12 + 3.75)
    ops = tap_ops([t1a, t2, t1b], kilavuz(), 500.0, (0.0, 0.0, 30.0))
    assert [op.holes for op in ops] == [[(20.0, 20.0), (70.0, 40.0)], [(30.0, 30.0)]]
    assert ops[0].z == pytest.approx(20.0 - 15.75, rel=REL)
    assert ops[1].z == pytest.approx(12.0 - 15.75, rel=REL)
    assert all(op.feed == 625.0 for op in ops)

    # havşasız delikte chamfer_ops, dişsiz delikte tap_ops → CamError
    with pytest.raises(CamError):
        chamfer_ops([c1, t1a], havsa(), 1500.0, 100.0, (0.0, 0.0, 30.0))
    with pytest.raises(CamError):
        tap_ops([t1a, c1], kilavuz(), 500.0, (0.0, 0.0, 30.0))


@pytest.mark.occt
def test_K5_spec23_inclined_hole():
    """K5: SPEC 23 `inclined_hole` kaydı → spot_ops CamError."""
    from geometry.features import block
    from geometry.holes import inclined_hole

    p = inclined_hole(
        block(100.0, 60.0, 20.0), (50.0, 30.0, 20.0), (0.0, 0.5, -math.sqrt(0.75)), d=6.0, depth=10.0
    )
    with pytest.raises(CamError):
        spot_ops(list(p.holes), punta(), 2000.0, 200.0, (0.0, 0.0, 30.0), d_s=6.0)


# ---------------------------------------------------------------- K6: kanonik açılım


def test_K6_g82_single_hole():
    """K6: G82 tek delik: G1 sayısı 1, toplam G1 boyu r − z = 5; hareketler G81'inkiyle aynı."""
    tp = ornek_a(holes=[(10.0, 10.0)]).to_toolpath()
    exp = [
        (G0, (10.0, 10.0, 5.0)),
        (G0, (10.0, 10.0, 2.0)),
        (G1, (10.0, 10.0, -3.0)),
        (G0, (10.0, 10.0, 5.0)),
    ]
    assert_moves(tp, exp, feed=200.0)
    g1 = [m for m in tp.moves if m.type is G1]
    assert len(g1) == 1
    assert tp.rpm == 2000.0
    assert tuple(tp.start) == START
    assert tp.tool == punta()


def test_K6_g84_single_hole():
    """K6: G84 tek delik: G1 sayısı 2, toplam G1 boyu 2 (r − z) = 35.5; ikinci G1 yukarı, aynı F = 625."""
    tp = ornek_b().to_toolpath()
    exp = [
        (G0, (10.0, 10.0, 5.0)),
        (G0, (10.0, 10.0, 2.0)),
        (G1, (10.0, 10.0, -15.75)),
        (G1, (10.0, 10.0, 2.0)),
        (G0, (10.0, 10.0, 5.0)),
    ]
    assert_moves(tp, exp, feed=625.0)
    pts = tp.points()
    boy = sum(float(np.linalg.norm(pts[i + 1] - pts[i])) for i, m in enumerate(tp.moves) if m.type is G1)
    assert boy == pytest.approx(2 * (2.0 + 15.75), rel=REL)
    assert tp.rpm == 500.0


def test_K6_g84_duration():
    """Teori: G84'ün G1 süresi 2 (r − z) / (S·P) dk = 35.5 / 625."""
    op = ornek_b()
    pts = op.to_toolpath().points()
    t = sum(
        float(np.linalg.norm(pts[i + 1] - pts[i])) / m.feed
        for i, m in enumerate(op.to_toolpath().moves)
        if m.type is G1
    )
    assert t == pytest.approx(35.5 / 625.0, rel=REL)


G82_G98 = [
    (G0, (10.0, 10.0, 5.0)),
    (G0, (10.0, 10.0, 2.0)),
    (G1, (10.0, 10.0, -3.0)),
    (G0, (10.0, 10.0, 5.0)),
    (G0, (30.0, 10.0, 5.0)),
    (G0, (30.0, 10.0, 2.0)),
    (G1, (30.0, 10.0, -3.0)),
    (G0, (30.0, 10.0, 5.0)),
    (G0, (30.0, 25.0, 5.0)),
    (G0, (30.0, 25.0, 2.0)),
    (G1, (30.0, 25.0, -3.0)),
    (G0, (30.0, 25.0, 5.0)),
]

# G99: z_dön = r = 2; sonraki deliğin R'ye inişi sıfır boylu, yazılmaz
G82_G99 = [
    (G0, (10.0, 10.0, 5.0)),
    (G0, (10.0, 10.0, 2.0)),
    (G1, (10.0, 10.0, -3.0)),
    (G0, (10.0, 10.0, 2.0)),
    (G0, (30.0, 10.0, 2.0)),
    (G1, (30.0, 10.0, -3.0)),
    (G0, (30.0, 10.0, 2.0)),
    (G0, (30.0, 25.0, 2.0)),
    (G1, (30.0, 25.0, -3.0)),
    (G0, (30.0, 25.0, 2.0)),
]

G84_G98 = [
    (G0, (10.0, 10.0, 5.0)),
    (G0, (10.0, 10.0, 2.0)),
    (G1, (10.0, 10.0, -15.75)),
    (G1, (10.0, 10.0, 2.0)),
    (G0, (10.0, 10.0, 5.0)),
    (G0, (30.0, 10.0, 5.0)),
    (G0, (30.0, 10.0, 2.0)),
    (G1, (30.0, 10.0, -15.75)),
    (G1, (30.0, 10.0, 2.0)),
    (G0, (30.0, 10.0, 5.0)),
    (G0, (30.0, 25.0, 5.0)),
    (G0, (30.0, 25.0, 2.0)),
    (G1, (30.0, 25.0, -15.75)),
    (G1, (30.0, 25.0, 2.0)),
    (G0, (30.0, 25.0, 5.0)),
]

# G99: yukarı G1 R'de biter; G0 (x, y, r) sıfır boylu, yazılmaz
G84_G99 = [
    (G0, (10.0, 10.0, 5.0)),
    (G0, (10.0, 10.0, 2.0)),
    (G1, (10.0, 10.0, -15.75)),
    (G1, (10.0, 10.0, 2.0)),
    (G0, (30.0, 10.0, 2.0)),
    (G1, (30.0, 10.0, -15.75)),
    (G1, (30.0, 10.0, 2.0)),
    (G0, (30.0, 25.0, 2.0)),
    (G1, (30.0, 25.0, -15.75)),
    (G1, (30.0, 25.0, 2.0)),
]


@pytest.mark.parametrize("retract, exp", [("G98", G82_G98), ("G99", G82_G99)])
def test_K6_g82_three_holes(retract, exp):
    """K6: 3 delikli G82, elle yazılmış liste."""
    assert_moves(ornek_a(retract, holes=HOLES3).to_toolpath(), exp, feed=200.0)


@pytest.mark.parametrize("retract, exp", [("G98", G84_G98), ("G99", G84_G99)])
def test_K6_g84_three_holes(retract, exp):
    """K6: 3 delikli G84, elle yazılmış liste (G99'da sıfır boylu hareket yok)."""
    assert_moves(ornek_b(retract, holes=HOLES3).to_toolpath(), exp, feed=625.0)


@pytest.mark.parametrize("retract", ["G98", "G99"])
def test_K6_no_zero_length(retract):
    for op in (ornek_a(retract, holes=HOLES3), ornek_b(retract, holes=HOLES3)):
        pts = op.to_toolpath().points()
        assert np.all(np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9)


def test_K6_start_above_first_hole():
    """Başlangıç ilk deliğin üstündeyse ilk G0 (x, y, z_akım) sıfır boylu, yazılmaz."""
    op = dataclasses.replace(ornek_b(), start=(10.0, 10.0, 5.0))
    assert_moves(op.to_toolpath(), G84_G98[1:5], feed=625.0)


@pytest.mark.parametrize("retract", ["G98", "G99"])
def test_K6_g82_equals_g81(retract):
    """Teori: G82 `to_toolpath()` G81 açılımının aynısı (SPEC 04 DrillOp ile)."""
    a = ornek_a(retract, holes=HOLES3)
    d = DrillOp(a.name, matkap(), a.rpm, a.start, list(a.holes), a.z, a.r, a.feed, "G81", None, retract)
    got, exp = a.to_toolpath(), d.to_toolpath()
    assert [m.type for m in got.moves] == [m.type for m in exp.moves]
    np.testing.assert_allclose(got.points(), exp.points(), rtol=0, atol=1e-12)


def test_K6_tap_feed_property():
    """TapOp.feed = tap_feed(rpm, pitch, feed_decimals) = 625."""
    assert ornek_b().feed == 625.0


# ---------------------------------------------------------------- K7: validate()


def test_K7_valid_ops_pass():
    ornek_a().validate()
    ornek_b().validate()
    for yap in (punta, havsa, matkap):  # G82: SPOT, CHAMFER, DRILL
        dataclasses.replace(ornek_a(), tool=yap()).validate()


DWELL_INVALID = [
    ("dwell = 0", {"dwell": 0.0}),
    ("dwell < 0", {"dwell": -0.2}),
    ("dwell 0.5 ms", {"dwell": 0.0005}),
    ("dwell 1.5 ms", {"dwell": 0.0015}),
    ("dwell nan", {"dwell": math.nan}),
    ("takım FLAT", {"tool": "freze"}),
    ("takım TAP", {"tool": "kilavuz"}),
    ("z = r", {"z": 2.0}),
    ("z > r", {"z": 3.0}),
    ("r > start_z", {"r": 5.5, "z": -3.0}),
    ("rpm = 0", {"rpm": 0.0}),
    ("feed = 0", {"feed": 0.0}),
    ("feed < 0", {"feed": -1.0}),
    ("delik yok", {"holes": []}),
    ("dönüş G97", {"retract": "G97"}),
]

TAP_INVALID = [
    ("takım SPOT", {"tool": "punta"}),
    ("takım DRILL", {"tool": "matkap"}),
    ("z = r", {"z": 2.0}),
    ("z > r", {"z": 3.0}),
    ("r > start_z", {"r": 5.5}),
    ("yazılamayan F (S = 333)", {"rpm": 333.0}),
    ("rpm = 0", {"rpm": 0.0}),
    ("delik yok", {"holes": []}),
    ("dönüş G97", {"retract": "G97"}),
]

_TAKIM = {"freze": freze, "kilavuz": kilavuz, "punta": punta, "matkap": matkap}


def _uygula(op, kw: dict):
    kw = {k: (_TAKIM[v]() if k == "tool" else v) for k, v in kw.items()}
    return dataclasses.replace(op, **kw)


@pytest.mark.parametrize("kw", [k for _, k in DWELL_INVALID], ids=[a for a, _ in DWELL_INVALID])
def test_K7_dwell_drill_invalid(kw):
    """K7: DwellDrillOp her hata durumu ayrı ayrı → CamError."""
    with pytest.raises(CamError):
        _uygula(ornek_a(), kw).validate()


def test_K7_dwell_ms_multiple_passes():
    """1 ms'nin katı bekleme geçer: 0.001, 0.25, 2.0."""
    for w in (0.001, 0.25, 2.0):
        dataclasses.replace(ornek_a(), dwell=w).validate()


@pytest.mark.parametrize("kw", [k for _, k in TAP_INVALID], ids=[a for a, _ in TAP_INVALID])
def test_K7_tap_invalid(kw):
    """K7: TapOp her hata durumu ayrı ayrı → CamError."""
    with pytest.raises(CamError):
        _uygula(ornek_b(), kw).validate()
