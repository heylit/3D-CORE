"""SPEC 52 K2–K4 — torna diş çekme simülasyonu ve simüle yüzeyden ölçüm (ISO 68-1).

Testler SPEC 52 "Senkron helis süpürmesi", "ISO 68-1 temel profil" ve "Ölçüm" bölümlerinden yazıldı;
cam.sim kodu okunmadı. Referans: tests/cam/threadref.py.

Kaynaklar (SPEC 52 ve ISO 68-1):
- H = (√3/2)·P; d₂ = d − 0.649519·P; dış diş dibi d₃ = d − 1.226869·P (h = 17/24·H, r_ε = H/6);
  iç D₁ = d − 1.082532·P.
- Senkron kesim: z_c(θ) = z₀ + P·(θ − θ₀)/360 + k·P; r_dış ← min(r_dış, r_profil(z − z_c));
  pasolar aynı θ₀'dan;
  starts = n → θ₀ + j·360/n. Faz (z₀,
  θ₀) SPEC'te sayıyla verilmediği için testler fazı veriden bulur (fit_helix).
- Ölçüm: büyük çap / diş dibi = 2·max / 2·min; böğür çapı dolu oranı ½;
  lead_err = max|r(θ, z) − r(0, z − P·θ/360)|.
- Pappus: helis yivinin bir turdaki hacmi = kesit alanı · 2π·r_c (helisel kayma hacmi korur).
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from cam.lathe import tip_offset
from cam.lathe_ops import iso_thread_depth
from cam.model import MoveType
from cam.sim import PolarMap, simulate_thread, thread_measure
from tests.cam.threadref import (
    MIL_Z,
    D1_iso,
    H_iso,
    d2_iso,
    d3_iso,
    dis_kalemi,
    fit_helix,
    groove_volume_per_turn,
    helix_outer,
    mil_rmap,
    torna_disi,
    wrap,
)

DZ = 0.05
OLCUM = (-19.0, -5.0)  # ölçüm bölgesi: tam çaplı milin içinde, uçlardan ≥ 3 mm


def _sentetik(n_theta: int, n_z: int, z0: float, r_in, r_out) -> PolarMap:
    return PolarMap(z0, DZ, n_theta, n_z, np.asarray(r_in, dtype=float), np.asarray(r_out, dtype=float))


def _xc(tp) -> float:
    """En derin G1'in burun merkezi x'i: C = P − q_T (T = 8: q = (0, −r))."""
    q = tip_offset(8, tp.tool.nose_r)
    return min(m.end[0] for m in tp.moves if m.type is MoveType.LINEAR) - q[1]


# ------------------------------------------------------------------ ölçüm: kapalı formlu sentetik helis


def test_K2_olcum_sentetik_dis_dis():
    """M20×2.5 ISO dış profil (r_ε = H/6, h = 17/24·H) z ∈ [−20, 0] helis olarak;
    ölçüm ISO değerlerini verir."""
    P, H = 2.5, H_iso(2.5)
    th = (np.arange(360) + 0.5) * 1.0
    zs = -20.0 + (np.arange(400) + 0.5) * DZ
    r_out = helix_outer(th, zs, 0.37, P, 1, 10.0 - 17 / 24 * H + H / 6, H / 6, np.full(400, 10.0))
    m = _sentetik(360, 400, -20.0, np.zeros((360, 400)), r_out)
    s = thread_measure(m, "dis", (-17.0, -3.0))
    assert s.P == pytest.approx(P, abs=1e-3)
    assert s.d == pytest.approx(20.0, abs=1e-9)
    assert s.d2 == pytest.approx(d2_iso(20.0, P), abs=DZ)
    assert s.d_root == pytest.approx(d3_iso(20.0, P), abs=DZ)
    assert 0.0 <= s.lead_err <= DZ


def test_K2_olcum_sentetik_ic_dis():
    """M8×1.25 ISO iç temel profil: sivri tepe D/2 + H/8 (dipte P/8 düzlük, r = D/2), tepe D₁/2 (delik).
    Ölçüm: d = 2·max = 8, d_root = 2·min = D₁, d₂ = 8 − 0.649519·1.25 (iç ve dış aynı temel profil)."""
    P, H, D = 1.25, H_iso(1.25), 8.0
    th = (np.arange(360) + 0.5) * 1.0
    zs = -12.0 + (np.arange(240) + 0.5) * DZ
    u = wrap(zs[None, :] - 0.11 - P * th[:, None] / 360.0, P)
    r_in = np.maximum(D1_iso(D, P) / 2, np.minimum(D / 2, D / 2 + H / 8 - np.abs(u) * math.sqrt(3)))
    m = _sentetik(360, 240, -12.0, r_in, np.full((360, 240), 10.0))
    s = thread_measure(m, "ic", (-10.0, -2.0))
    assert s.P == pytest.approx(P, abs=1e-3)
    assert s.d == pytest.approx(D, abs=1e-9)
    assert s.d_root == pytest.approx(D1_iso(D, P), abs=1e-9)
    assert s.d2 == pytest.approx(d2_iso(D, P), abs=DZ)
    assert 0.0 <= s.lead_err <= DZ


# ------------------------------------------------------------------ K2 M20×2.5 torna dişi


@functools.cache
def _m20(z_st=None, z_en=None):
    # fixture değil: simülasyon test gövdesinde çağrılsın (uygulanmamış kod "uygulanmamış" sayılsın)
    P = 2.5
    kalem = dis_kalemi(H_iso(P) / 6)
    kw = {} if z_st is None else {"z_st": z_st, "z_en": z_en}
    tp = torna_disi(20.0, P, kalem, iso_thread_depth(P), **kw)
    bas = PolarMap.from_radial(mil_rmap(20.0, 7.0, DZ), dtheta_deg=1.0)
    return tp, bas, simulate_thread([tp], bas)


def _pencere(m: PolarMap, a: float, b: float) -> np.ndarray:
    z = m.centers()
    return (z > a) & (z < b)


def test_K2_m20_olcum():
    _tp, _bas, m = _m20()
    s = thread_measure(m, "dis", OLCUM)
    assert s.P == pytest.approx(2.5, abs=1e-3)
    assert s.d == pytest.approx(20.0, abs=DZ)
    assert s.d2 == pytest.approx(20.0 - 0.649519 * 2.5, abs=DZ)
    assert s.d_root == pytest.approx(20.0 - 1.226869 * 2.5, abs=DZ)
    assert s.lead_err <= DZ


def test_K2_m20_yuzey_helis_kapali_form():
    """Mil bölgesinde her hücre r_dış = min(10, V_profil(sar(z − c − P·θ/360))) (tek faz c, en derin paso);
    hücre ortası örneklemesi kesin olduğundan hata ≤ 1e-6."""
    tp, _bas, m = _m20()
    w = _pencere(m, MIL_Z[0] + 2.0, MIL_Z[1] - 2.0)
    zs = m.centers()[w]
    _c, hata = fit_helix(
        np.asarray(m.r_out)[:, w], m.thetas(), zs, 2.5, 1, _xc(tp), tp.tool.nose_r, np.full(len(zs), 10.0)
    )
    assert hata <= 1e-6
    np.testing.assert_allclose(np.asarray(m.r_in), 0.0, atol=0)


def test_K2_initial_degismez():
    _tp, bas, m = _m20()
    ilk = PolarMap.from_radial(mil_rmap(20.0, 7.0, DZ), dtheta_deg=1.0)
    np.testing.assert_array_equal(np.asarray(bas.r_out), np.asarray(ilk.r_out))
    np.testing.assert_array_equal(np.asarray(bas.r_in), np.asarray(ilk.r_in))
    assert m.volume() < bas.volume()


# ------------------------------------------------------------------ K3 ince hatve, ters yön, çok ağız


def test_K3_m12x1_ince_hatve():
    P = 1.0
    kalem = dis_kalemi(H_iso(P) / 6)
    tp = torna_disi(12.0, P, kalem, iso_thread_depth(P))
    m = simulate_thread([tp], PolarMap.from_radial(mil_rmap(12.0, 4.5, DZ), dtheta_deg=1.0))
    s = thread_measure(m, "dis", OLCUM)
    assert s.P == pytest.approx(P, abs=1e-3)
    assert s.d2 == pytest.approx(d2_iso(12.0, P), abs=DZ)
    assert s.d_root == pytest.approx(d3_iso(12.0, P), abs=DZ)
    assert s.lead_err <= DZ


def test_K3_ters_yon_ayni_olcum():
    """Paso kanaldan boyuna doğru (z_end > z_start). İş mili yönü Toolpath'te yok; helis yönü iki işaretle de
    denenir (biri tutmalı), ölçümler aynı."""
    tp, _bas, m = _m20(-24.0, -0.5)
    assert tp.moves[2].end[2] > tp.moves[1].end[2]  # ilk G1 +Z yönünde
    s = thread_measure(m, "dis", OLCUM)
    assert s.P == pytest.approx(2.5, abs=1e-3)
    assert s.d2 == pytest.approx(d2_iso(20.0, 2.5), abs=DZ)
    assert s.d_root == pytest.approx(d3_iso(20.0, 2.5), abs=DZ)
    w = _pencere(m, MIL_Z[0] + 2.0, MIL_Z[1] - 2.0)
    zs = m.centers()[w]
    hatalar = [
        fit_helix(
            np.asarray(m.r_out)[:, w],
            m.thetas(),
            zs,
            2.5,
            1,
            _xc(tp),
            tp.tool.nose_r,
            np.full(len(zs), 10.0),
            sign=sg,
        )[1]
        for sg in (1, -1)
    ]
    assert min(hatalar) <= 1e-6


def test_K3_iki_agizli_dis():
    """starts = 2, hatve P = 2.5, hatve boyu L = 5 (feed = L): yivler P aralıklı, helis L ile tutarlı."""
    P, L = 2.5, 5.0
    kalem = dis_kalemi(H_iso(P) / 6)
    tp = torna_disi(20.0, P, kalem, iso_thread_depth(P), lead=L)
    assert all(m.feed == L for m in tp.moves if m.type is MoveType.LINEAR)
    m = simulate_thread([tp], PolarMap.from_radial(mil_rmap(20.0, 7.0, DZ), dtheta_deg=1.0), starts=2)
    s = thread_measure(m, "dis", OLCUM)
    assert s.P == pytest.approx(P, abs=1e-3)
    assert s.d2 == pytest.approx(d2_iso(20.0, P), abs=DZ)
    assert s.d_root == pytest.approx(d3_iso(20.0, P), abs=DZ)
    w = _pencere(m, MIL_Z[0] + 2.0, MIL_Z[1] - 2.0)
    zs = m.centers()[w]
    _c, hata = fit_helix(
        np.asarray(m.r_out)[:, w], m.thetas(), zs, L, 2, _xc(tp), tp.tool.nose_r, np.full(len(zs), 10.0)
    )
    assert hata <= 1e-6


# ------------------------------------------------------------------ K4 kaldırılan hacim (Pappus)


def test_K4_sivri_profil_hacim():
    """r_ε = 0, h = 17/24·H, M20×2.5: yiv üçgeni A = h²·tan 30°,
    r_c = 10 − h/3. Mil bölgesi 20 mm = 8 tam tur;
    boyun ve kanalda malzeme diş dibinin altında olduğundan kaldırılan hacim = 8·A·2π·r_c.
    Tolerans O(Δθ² + Δz): rel (Δθ[rad])² + (Δz/h)²."""
    P = 2.5
    h = iso_thread_depth(P)
    tp = torna_disi(20.0, P, dis_kalemi(0.0), h)
    bas = PolarMap.from_radial(mil_rmap(20.0, 7.0, DZ), dtheta_deg=1.0)
    m = simulate_thread([tp], bas)
    n_tur = (MIL_Z[1] - MIL_Z[0]) / P
    assert n_tur == 8.0
    beklenen = n_tur * groove_volume_per_turn(h, 10.0)
    tol = math.radians(1.0) ** 2 + (DZ / h) ** 2
    assert bas.volume() - m.volume() == pytest.approx(beklenen, rel=tol)
