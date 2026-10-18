"""SPEC 32 K4, K5, K6 — simülasyon sonucundan hareket başına yük (freze z-haritası, torna radyal dexel).

Beklenen değerler SPEC 32 Teori tablosundan (freze) ve kapalı formlardan (torna). Izgara toleransı
K4'teki gibi Δ = 0.5 mm'de rel ≤ 2Δ/D. Uydurma stok ve malzeme.
"""

from __future__ import annotations

import math

import pytest

from cam.kuvvet import lathe_loads, milling_loads, specific_force, spindle_torque
from cam.model import FeedMode
from cam.sim import simulate
from tests.cam.kuvvet_ref import (
    AP,
    AP_T,
    CELL,
    CELL_T,
    F_T,
    FZ,
    KC11,
    MC,
    N_T,
    R_STOK,
    REL_IZGARA,
    STOCK,
    T_STOCK,
    TABLO,
    VC,
    ZT1,
    ZT2,
    N,
    hex_kapali,
    kanal_programi,
    malzeme,
    torna_programi,
    torna_sim,
    yan_programi,
    yuk,
)


@pytest.fixture(scope="module")
def kanal():
    tp, ix = kanal_programi()
    return tp, ix, simulate([tp], STOCK, cell=CELL)


@pytest.fixture(scope="module")
def yan():
    tp, ix = yan_programi()
    return tp, ix, simulate([tp], STOCK, cell=CELL)


def _tutarlilik(ld, mat) -> None:
    """Kayıt içi tanımlar: kc = kc(h), P = Q·kc/10⁶, M = 60000·P/(2πn)."""
    assert ld.kc == pytest.approx(specific_force(mat, ld.h), rel=1e-12)
    assert ld.P == pytest.approx(ld.Q * ld.kc / 1e6, rel=1e-12)
    assert ld.M == pytest.approx(spindle_torque(ld.P, N), rel=1e-12)


# ------------------------------------------------------------------ K4 kanal


def test_k4_liste_bicimi(kanal):
    mat = malzeme()
    tp, _, res = kanal
    loads = milling_loads([tp], res, mat)
    assert len(loads) == len(res.steps)
    assert [ld.k for ld in loads] == [s.k for s in res.steps]
    assert all(ld.kind in ("kesme", "hava", "atlandi") for ld in loads)
    assert [ld.move for ld in loads] == list(range(len(tp.moves)))  # tek yol, bağlantı adımı yok


def test_k4_kanal_yuku(kanal):
    mat = malzeme()
    tp, ix, res = kanal
    ld = yuk(milling_loads([tp], res, mat), 0, ix["kanal"])
    hm_t, Q_t, P_t, M_t, _ = TABLO[10.0]
    assert ld.kind == "kesme"
    assert ld.ap == pytest.approx(AP, abs=1e-9)
    assert ld.ae == pytest.approx(10.0, rel=REL_IZGARA)
    assert ld.ae <= 10.0 + 1e-12  # ae = min(D, …)
    assert ld.Q == pytest.approx(Q_t, rel=REL_IZGARA)
    assert ld.h == pytest.approx(hm_t, rel=REL_IZGARA)
    assert ld.P == pytest.approx(P_t, rel=REL_IZGARA)
    assert ld.M == pytest.approx(M_t, rel=REL_IZGARA)
    _tutarlilik(ld, mat)
    # Ft_maks = K·kc11·ap·hex^(1−mc); ae ≥ D/2 → hex = fz
    assert ld.F_t == pytest.approx(KC11 * AP * FZ ** (1 - MC), rel=1e-9)


def test_k4_q_tanimi(kanal):
    mat = malzeme()
    # Q_k = ΔV_k / t⁰_k (ivmesiz Machine: adım süresi = t⁰); freze G1'de t⁰ = 60·L/F
    tp, ix, res = kanal
    ld = yuk(milling_loads([tp], res, mat), 0, ix["kanal"])
    s = res.steps[ld.k - 1]
    t0 = 60 * 40.0 / s.feed
    assert ld.Q == pytest.approx(s.removed / t0, rel=1e-9)


def test_k4_hava(kanal):
    mat = malzeme()
    tp, ix, res = kanal
    loads = milling_loads([tp], res, mat)
    for ad in ("inis", "cikis", "hava_g1"):  # G0'lar ve stok üstündeki G1
        ld = yuk(loads, 0, ix[ad])
        assert ld.kind == "hava", ad
        assert ld.P == 0.0 and ld.M == 0.0
        assert ld.h is None


def test_k4_K_carpani(kanal):
    mat = malzeme()
    tp, ix, res = kanal
    a = yuk(milling_loads([tp], res, mat), 0, ix["kanal"])
    b = yuk(milling_loads([tp], res, mat, K=1.2), 0, ix["kanal"])
    assert b.P == pytest.approx(1.2 * a.P, rel=1e-12)
    assert b.M == pytest.approx(1.2 * a.M, rel=1e-12)


# ------------------------------------------------------------------ K5 yan frezeleme


@pytest.mark.parametrize("ad,ae", [("ae5", 5.0), ("ae1", 1.0)])
def test_k5_yan_paso(yan, ad, ae):
    mat = malzeme()
    tp, ix, res = yan
    ld = yuk(milling_loads([tp], res, mat), 0, ix[ad])
    hm_t, Q_t, P_t, M_t, _ = TABLO[ae]
    assert ld.kind == "kesme"
    assert ld.ap == pytest.approx(AP, abs=1e-9)
    assert ld.ae == pytest.approx(ae, rel=REL_IZGARA)
    assert ld.Q == pytest.approx(Q_t, rel=REL_IZGARA)
    assert ld.h == pytest.approx(hm_t, rel=REL_IZGARA)
    assert ld.P == pytest.approx(P_t, rel=REL_IZGARA)
    assert ld.M == pytest.approx(M_t, rel=REL_IZGARA)
    _tutarlilik(ld, mat)
    # h = hm(ölçülen ae); F_t = kc11·ap·hex(ölçülen ae)^(1−mc)
    phi = math.acos(1 - 2 * ld.ae / 10.0)
    assert ld.h == pytest.approx(FZ * (2 * ld.ae / 10.0) / phi, rel=1e-9)
    assert ld.F_t == pytest.approx(KC11 * AP * hex_kapali(FZ, ld.ae) ** (1 - MC), rel=1e-9)


def test_k5_kanal_yan_pasolardan_etkilenmez(yan, kanal):
    mat = malzeme()
    tp, ix, res = yan
    tp0, ix0, res0 = kanal
    a = yuk(milling_loads([tp], res, mat), 0, ix["kanal"])
    b = yuk(milling_loads([tp0], res0, mat), 0, ix0["kanal"])
    assert a.P == pytest.approx(b.P, rel=1e-12)


# ------------------------------------------------------------------ K6 torna


def _halka_Q(v_f: float) -> float:
    """Kararlı boyuna paso: Q = π(R² − r²)·v_f [mm³/s], r = R − ap (kesilen halka)."""
    return math.pi * (R_STOK**2 - (R_STOK - AP_T) ** 2) * v_f


REL_T = 2 * CELL_T / abs(ZT2 - ZT1)  # z ızgarası: rel ≤ 2Δz/L


def test_k6_g95_sabit_devir():
    mat = malzeme()
    simulate_lathe = torna_sim()
    tp = torna_programi()
    res = simulate_lathe([tp], T_STOCK, cell=CELL_T)
    loads = lathe_loads([tp], res, mat)
    assert len(loads) == len(res.steps)
    ld = yuk(loads, 0, 1)
    assert ld.kind == "kesme"
    # Teori torna örneği (Vc = 200 çap 50'de, n = 1273.24): h = f·sin κr = 0.2, Fc = 897.2093 N.
    # Teori P = Fc·Vc/60000 = 2.99070 kW Vc'yi dış çapta alır (Q = vc·ap·f); simülasyonun Q'su halka hacminden
    # gelir: Q = π(R² − r²)·f·n/60 = 2π·r_m·ap·f·n/60, r_m = R − ap/2 → P = Fc·Vc(r_m)/60000 = 2.99070·r_m/R,
    # M = Fc·r_m/1000 = 22.4302·r_m/R.
    v_f = F_T * N_T / 60
    kc = KC11 * F_T ** (-MC)
    P = _halka_Q(v_f) * kc / 1e6
    r_m = R_STOK - AP_T / 2
    assert P == pytest.approx(2.99070 * r_m / R_STOK, rel=1e-5)
    assert ld.h == pytest.approx(F_T, rel=1e-12)
    assert ld.kc == pytest.approx(kc, rel=1e-12)
    assert ld.Q == pytest.approx(_halka_Q(v_f), rel=REL_T)
    assert ld.P == pytest.approx(P, rel=REL_T)
    assert ld.M == pytest.approx(60000 * P / (2 * math.pi * N_T), rel=REL_T)
    assert ld.M == pytest.approx(22.4302 * r_m / R_STOK, rel=REL_T)
    assert ld.M == pytest.approx(60000 * ld.P / (2 * math.pi * N_T), rel=1e-9)
    # bilgi: ap_k = Q·60/(1000·vc_k·f), vc_k = 2π·r_k·n_e/1000, r_k = 25
    vc_k = 2 * math.pi * R_STOK * N_T / 1000
    assert ld.ap == pytest.approx(ld.Q * 60 / (1000 * vc_k * F_T), rel=1e-9)
    # G0 çıkışlar hava
    for j in (2, 3):
        h = yuk(loads, 0, j)
        assert h.kind == "hava" and h.P == 0.0 and h.M == 0.0 and h.h is None


def test_k6_kappa_r():
    mat = malzeme()
    simulate_lathe = torna_sim()
    tp = torna_programi()
    tp.tool.kappa_r = 75.0
    tp.tool.eps_r = 80.0
    res = simulate_lathe([tp], T_STOCK, cell=CELL_T)
    ld = yuk(lathe_loads([tp], res, mat), 0, 1)
    h = F_T * math.sin(math.radians(75.0))
    assert ld.h == pytest.approx(h, rel=1e-12)
    assert ld.kc == pytest.approx(KC11 * h ** (-MC), rel=1e-12)


def test_k6_g96_sabit_kesme_hizi():
    mat = malzeme()
    simulate_lathe = torna_sim()
    tp = torna_programi(css=VC, rpm=3000.0)
    res = simulate_lathe([tp], T_STOCK, cell=CELL_T)
    ld = yuk(lathe_loads([tp], res, mat), 0, 1)
    # n_e = min(1000·Vc/(2π·r_k), rpm), r_k = kesilen aralığın dış yarıçapı = 25
    n_e = min(1000 * VC / (2 * math.pi * R_STOK), 3000.0)
    assert n_e == pytest.approx(N_T, rel=1e-12)
    # süre SPEC 22: n(x) = 1000·Vc/(2π|x|), x = 23 (program x'i) → v_f = F·n(x)/60
    n_x = min(1000 * VC / (2 * math.pi * (R_STOK - AP_T)), 3000.0)
    P = _halka_Q(F_T * n_x / 60) * KC11 * F_T ** (-MC) / 1e6
    assert ld.h == pytest.approx(F_T, rel=1e-12)
    assert ld.P == pytest.approx(P, rel=REL_T)
    assert ld.M == pytest.approx(60000 * ld.P / (2 * math.pi * n_e), rel=1e-9)
    vc_k = 2 * math.pi * R_STOK * n_e / 1000
    assert ld.ap == pytest.approx(ld.Q * 60 / (1000 * vc_k * F_T), rel=1e-9)


def test_k6_g96_devir_siniri():
    mat = malzeme()
    # rpm sınırı 1000 < 1000·Vc/(2π·25) → n_e = 1000
    simulate_lathe = torna_sim()
    tp = torna_programi(css=VC, rpm=1000.0)
    res = simulate_lathe([tp], T_STOCK, cell=CELL_T)
    ld = yuk(lathe_loads([tp], res, mat), 0, 1)
    assert ld.M == pytest.approx(60000 * ld.P / (2 * math.pi * 1000.0), rel=1e-9)
    P = _halka_Q(F_T * 1000.0 / 60) * KC11 * F_T ** (-MC) / 1e6
    assert ld.P == pytest.approx(P, rel=REL_T)


def test_k6_g94():
    mat = malzeme()
    # G94: f = F/n_e; F = 0.2·n → aynı talaş kalınlığı ve güç
    simulate_lathe = torna_sim()
    F = F_T * N_T
    tp = torna_programi(feed_mode=FeedMode.PER_MIN, feed=F)
    res = simulate_lathe([tp], T_STOCK, cell=CELL_T)
    ld = yuk(lathe_loads([tp], res, mat), 0, 1)
    assert ld.h == pytest.approx(F / N_T, rel=1e-12)
    P = _halka_Q(F / 60) * KC11 * (F / N_T) ** (-MC) / 1e6
    assert ld.P == pytest.approx(P, rel=REL_T)
    assert ld.M == pytest.approx(60000 * ld.P / (2 * math.pi * N_T), rel=1e-9)
