"""SPEC 71 — tornalama lobu ve karar testleri (K1 torna, K3, K4, K8, K9, hatalar).

Testler yalnız SPEC 71 metninden ve iskelet arayüzünden yazıldı; cam/chatter.py gövdeleri okunmadı.
Bağımsız referans: tests/cam/chatter_ref.py (Tlusty tek yönlü, SDOF kapalı form).

- SDOF: k = 2·10⁴ N/mm, ζ = 0.03, f_n = 800 Hz, K_s = 2000 MPa, u = 1.
- En küçük paso a_kr = 2kζ(1 + ζ)/K_s = 0.618 mm; Re G'nin minimumu f_c ≈ f_n √(1 + 2ζ) = 823,650 Hz.
- Lob k: a = −1/(2 K_s Re G), n = 60 f_c/(k + ε/2π), ε = 3π + 2 atan(Re G/Im G).
- Lob k = 0 tabanı ≈ 28 314 dev/dk, k = 1 ≈ 18 001, k = 2 ≈ 13 195 (testte bağımsız hesaplanır).

Varsayımlar (SPEC'te açık değil):
- `Lob.loblar[k]` k numaralı lobdur (k = 0 ilk eleman); dizilerde sonlu olmayan değerler atlanır.
- K4'teki 1e-6 göreli eşitlik noktasal sınanır: lob 0'ın her noktası (n, a) için n'yi veren f_c
  (analitik g ile bulunur) aynı a'yı verir. Taban devri ayrıca bağımsız taban değerine göreli 1e-3 içinde.
- `karar` "kararli" ⇔ ap ≤ pay·a_lim; `oneri_n` verilen ap'yi "kararli" yapan en yakın devirdir.
- Kod ölçülen frekans ızgarasında (veya `FRF.at` ile daha sık) tarama yapar; FRF 0,01 Hz adımla verilir.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.chatter import FRF_GEREKLI, Lob, karar, lob_torna
from cam.frf import frf_modal
from cam.model import CamError, MachineProfile
from tests.cam.chatter_ref import match_rel, sample_idx, sdof_g, torna_n_a

K, ZETA, FN, KS = 2.0e4, 0.03, 800.0, 2000.0
A_KR = 2 * K * ZETA * (1 + ZETA) / KS  # 0.618 mm
F_C = FN * math.sqrt(1 + 2 * ZETA)
N_ARALIK = (5000.0, 35000.0)
F_LO, F_HI = 600.0, 1200.0


def g(f):
    return sdof_g(f, FN, ZETA, K)


def frf_ince():
    return frf_modal([(FN, ZETA, K)], np.linspace(F_LO, F_HI, 60001))  # 0,01 Hz


_LOB: dict[str, Lob] = {}


def lob_k3() -> Lob:
    """K3 lobu (test gövdesinde üretilir, modül önbelleği)."""
    if "k3" not in _LOB:
        _LOB["k3"] = lob_torna(frf_ince(), K_s=KS, n_aralik=N_ARALIK)
    return _LOB["k3"]


def finite(n, a):
    n, a = np.asarray(n, dtype=float), np.asarray(a, dtype=float)
    m = np.isfinite(n) & np.isfinite(a)
    return n[m], a[m]


def ref_bottom_n(k: int) -> float:
    """Lob k tabanının devri, f_c = Re G minimumu (yoğun ızgarada, bağımsız)."""
    f = np.linspace(800.0, 850.0, 500001)
    fc = f[np.argmin(g(f).real)]
    n, _ = torna_n_a(np.array([fc]), g, KS, k)
    return float(n[0])


def test_reference_self_check():
    """Öz denetim: a_kr = 0.618, Re G minimumu f_n √(1 + 2ζ)'da, minimum değeri −1/(2kζ(1+ζ))."""
    assert A_KR == pytest.approx(0.618, abs=1e-12)
    f = np.linspace(800.0, 850.0, 500001)
    G = g(f)
    assert f[np.argmin(G.real)] == pytest.approx(F_C, rel=1e-6)
    assert -1.0 / (2 * KS * G.real.min()) == pytest.approx(A_KR, rel=1e-6)
    assert ref_bottom_n(0) > ref_bottom_n(1) > ref_bottom_n(2)


# ---------------------------------------------------------------- K1: ölçüm zorunluluğu


def test_no_frf_raises_with_message():
    """K1: lob_torna(None, …) → hata, mesaj kullanıcı kararındaki metni içerir."""
    assert FRF_GEREKLI == "Chatter lobu için takım ucunun çekiç testi FRF ölçümü gerekir"
    with pytest.raises(CamError) as e:
        lob_torna(None, K_s=KS, n_aralik=N_ARALIK)
    assert FRF_GEREKLI in str(e.value)


# ---------------------------------------------------------------- K3: SDOF kapalı form


def test_lob_fields():
    """Lob alanları: n artan ızgara, a_lim ve gecerli aynı boyda, en az 3 lob."""
    lob = lob_k3()
    n = np.asarray(lob.n, dtype=float)
    assert n.ndim == 1 and len(n) > 10
    assert np.all(np.diff(n) > 0)
    assert n[0] >= N_ARALIK[0] - 1e-9 and n[-1] <= N_ARALIK[1] + 1e-9
    assert np.shape(lob.a_lim) == n.shape
    assert np.shape(lob.gecerli) == n.shape
    assert np.asarray(lob.gecerli).dtype == bool
    assert len(lob.loblar) >= 3


def test_envelope_minimum_equals_a_kr():
    """K3: lob zarfının (geçerli noktalar) en küçük değeri a_kr = 0.618 mm'ye göreli %0,5 içinde."""
    lob = lob_k3()
    ok = np.asarray(lob.gecerli)
    assert ok.sum() > 10
    a_min = float(np.min(np.asarray(lob.a_lim, dtype=float)[ok]))
    assert a_min == pytest.approx(A_KR, rel=5e-3)
    assert a_min >= A_KR * (1 - 1e-9)  # kapalı formdan küçük olamaz


@pytest.mark.parametrize("k", [0, 1, 2])
def test_each_lobe_bottom(k):
    """K3: her lobun dibi a_kr'de ve f_c ≈ f_n √(1+2ζ)'da: taban devri bağımsız değere ±%0,5."""
    n, a = finite(*lob_k3().loblar[k])
    assert len(n) > 10
    i = int(np.argmin(a))
    assert a[i] == pytest.approx(A_KR, rel=5e-3)
    assert n[i] == pytest.approx(ref_bottom_n(k), rel=5e-3)


# ---------------------------------------------------------------- K4: devir kuralı


def test_lobe0_points_follow_phase_rule():
    """K4: lob 0'ın her örnek noktası (n, a) faz kuralına uyar: n'yi veren f_c'de a = −1/(2K_s Re G)
    (göreli 1e-6; f_c analitik g ile ikiye bölmeyle bulunur)."""
    n, a = finite(*lob_k3().loblar[0])
    curve = lambda f: torna_n_a(f, g, KS, 0)  # noqa: E731
    for i in sample_idx(len(n), 40):
        assert match_rel(n[i], a[i], [curve], FN + 1e-6, F_HI) <= 1e-6, (n[i], a[i])


def test_lobe0_bottom_speed():
    """K4: k = 0 lobunun tabanındaki devir, f_c ve faz formülünden bağımsız hesaplanan değere eşit
    (taban konumu frekans çözünürlüğüyle sınırlı: göreli 1e-3)."""
    n, a = finite(*lob_k3().loblar[0])
    assert n[int(np.argmin(a))] == pytest.approx(ref_bottom_n(0), rel=1e-3)


def test_speed_decreases_with_lobe_number():
    """K4: lob k arttıkça devir küçülür (taban devirleri azalan)."""
    lob = lob_k3()
    bottoms = []
    for k in range(4):
        n, a = finite(*lob.loblar[k])
        bottoms.append(n[int(np.argmin(a))])
    assert all(bottoms[i] > bottoms[i + 1] for i in range(3))


def test_u_scales_depth():
    """Yön katsayısı u: G_or = u G ⇒ a_lim 1/u ile ölçeklenir (aynı devir ızgarasında)."""
    frf = frf_ince()
    l1 = lob_torna(frf, K_s=KS, n_aralik=N_ARALIK)
    l2 = lob_torna(frf, K_s=KS, u=0.5, n_aralik=N_ARALIK)
    ok = np.asarray(l1.gecerli) & np.asarray(l2.gecerli)
    assert np.array_equal(np.asarray(l1.n), np.asarray(l2.n))
    assert ok.sum() > 10
    assert np.allclose(np.asarray(l2.a_lim)[ok], 2.0 * np.asarray(l1.a_lim)[ok], rtol=1e-9)


# ---------------------------------------------------------------- K8: ölçüm bandı


def test_band_limits_validity():
    """K8: FRF 400–1200 Hz: lob 0'ın tepesi ≈ 36 400 dev/dk; 50 000 dev/dk'nın üstü ölçülen banda karşılık
    gelmez → gecerli = False ve karar "bilinmiyor"; lob 0 tabanında (≈ 28 300) gecerli = True."""
    frf = frf_modal([(FN, ZETA, K)], np.linspace(400.0, 1200.0, 80001))
    lob = lob_torna(frf, K_s=KS, n_aralik=(5000.0, 60000.0))
    n = np.asarray(lob.n, dtype=float)
    ok = np.asarray(lob.gecerli)
    n_max_ref = float(np.nanmax(torna_n_a(np.linspace(FN + 1e-6, 1200.0, 200001), g, KS, 0)[0]))
    assert n_max_ref < 40000.0  # öz denetim
    hi = n > 50000.0
    assert hi.any() and not ok[hi].any()
    for ni in n[hi][:: max(1, hi.sum() // 10)]:
        assert karar(lob, float(ni), 0.1)["durum"] == "bilinmiyor"
    i = int(np.argmin(np.abs(n - ref_bottom_n(0))))
    assert ok[i]
    assert karar(lob, float(n[i]), 0.1)["durum"] != "bilinmiyor"


def test_band_without_negative_real_part_gives_unknown():
    """K8: bant tümüyle f_n'nin altında (Re G > 0, lob yok): hiçbir devir geçerli değil,
    karar "bilinmiyor"."""
    frf = frf_modal([(FN, ZETA, K)], np.linspace(300.0, 700.0, 4001))
    lob = lob_torna(frf, K_s=KS, n_aralik=N_ARALIK)
    assert not np.asarray(lob.gecerli).any()
    assert karar(lob, 20000.0, 0.1)["durum"] == "bilinmiyor"


# ---------------------------------------------------------------- K9: karar


def peak_and_trough(lob: Lob) -> tuple[int, int]:
    """Lob 0 ile 1 arasındaki zarf tepesi (18 000–28 000 içinde en büyük) ve lob 0 çukuru (en küçük)."""
    n = np.asarray(lob.n, dtype=float)
    a = np.asarray(lob.a_lim, dtype=float)
    ok = np.asarray(lob.gecerli)
    win = ok & (n > 18500.0) & (n < 27500.0)
    ip = int(np.flatnonzero(win)[np.argmax(a[win])])
    win = ok & (n > 27500.0)
    it = int(np.flatnonzero(win)[np.argmin(a[win])])
    return ip, it


def test_karar_peak_stable_trough_unstable():
    """K9: aynı ap, lob tepesinin altında "kararli", çukurda "kararsiz"."""
    lob = lob_k3()
    a = np.asarray(lob.a_lim, dtype=float)
    n = np.asarray(lob.n, dtype=float)
    ip, it = peak_and_trough(lob)
    ap = 0.5 * a[ip]
    assert ap > 1.2 * a[it]  # öz denetim: tepe çukurdan belirgin yüksek
    r = karar(lob, float(n[ip]), ap)
    assert r["durum"] == "kararli"
    assert r["a_lim"] == pytest.approx(a[ip], rel=1e-12)
    assert karar(lob, float(n[it]), ap)["durum"] == "kararsiz"


def test_karar_borderline_band():
    """K9: sinirda ⇔ pay·a_lim < ap ≤ a_lim (pay = 0.8 varsayılan; pay = 0.5 ile de)."""
    lob = lob_k3()
    a = np.asarray(lob.a_lim, dtype=float)
    n = np.asarray(lob.n, dtype=float)
    ip, _ = peak_and_trough(lob)
    ni, ai = float(n[ip]), float(a[ip])
    assert karar(lob, ni, 0.79 * ai)["durum"] == "kararli"
    assert karar(lob, ni, 0.81 * ai)["durum"] == "sinirda"
    assert karar(lob, ni, ai)["durum"] == "sinirda"
    assert karar(lob, ni, 1.01 * ai)["durum"] == "kararsiz"
    assert karar(lob, ni, 0.6 * ai, pay=0.5)["durum"] == "sinirda"
    assert karar(lob, ni, 0.4 * ai, pay=0.5)["durum"] == "kararli"


def test_karar_suggests_nearest_stable_speed():
    """K9: çukurda kararsız ap için oneri_n aralık içinde, ap'yi kararlı yapar ve kullanıcı devrine
    en yakındır (ızgarada bir adımdan daha yakın kararlı devir yok)."""
    lob = lob_k3()
    a = np.asarray(lob.a_lim, dtype=float)
    n = np.asarray(lob.n, dtype=float)
    ok = np.asarray(lob.gecerli)
    ip, it = peak_and_trough(lob)
    ap = 0.5 * a[ip]
    n_u = float(n[it])
    r = karar(lob, n_u, ap)
    assert r["durum"] == "kararsiz"
    on = float(r["oneri_n"])
    assert N_ARALIK[0] <= on <= N_ARALIK[1]
    assert karar(lob, on, ap)["durum"] == "kararli"
    dn = float(np.max(np.diff(n)))
    closer = ok & (np.abs(n - n_u) < abs(on - n_u) - dn)
    assert not np.any(ap <= 0.8 * a[closer])


# ---------------------------------------------------------------- hatalar


def test_missing_cutting_coefficient_raises():
    """Hatalar: K_s yok ve malzeme yok → hata."""
    with pytest.raises(CamError):
        lob_torna(frf_ince(), n_aralik=N_ARALIK)


@pytest.mark.parametrize("aralik", [(35000.0, 5000.0), (20000.0, 20000.0)])
def test_bad_speed_range_raises(aralik):
    """Hatalar: n_aralik ters (veya boş) → hata."""
    with pytest.raises(CamError):
        lob_torna(frf_ince(), K_s=KS, n_aralik=aralik)


def test_speed_range_above_machine_profile_raises():
    """Hatalar: n_aralik tezgâh profilinin (SPEC 30) rpm_max'ını aşıyor → hata; aşmıyorsa kabul."""
    prof = MachineProfile(name="TORNA1", controller="fanuc", kind="lathe", rpm_max=30000.0, feed_max=5000.0)
    with pytest.raises(CamError):
        lob_torna(frf_ince(), K_s=KS, n_aralik=N_ARALIK, profil=prof)
    lob = lob_torna(frf_ince(), K_s=KS, n_aralik=(5000.0, 30000.0), profil=prof)
    assert isinstance(lob, Lob)
