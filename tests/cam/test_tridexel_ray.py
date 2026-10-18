"""SPEC 43 K2, K5, K6 — ışın–takım kesişimi, sabit eksenli süpürme, değişen eksen.

Testler SPEC 43 "Takım katısı" ve "Hareketin süpürmesi" bölümlerinden yazıldı; cam.sim.tridexel / simulate5
kodu okunmadı. Referanslar tests/cam/tridexref.py'de (formüller orada):
- K2: üyelik fonksiyonu + ikiye bölme (dışbükey kesen kısım; dik ışında gövde basamağı).
- K5: süpürme = takım ⊕ [p₀, p₁]; giriş s₀(t) dışbükey, çıkış s₁(t) içbükey → yoğun örnek + üçe bölme.
- K6: uç sabit, eksen slerp; yoğun açısal örnekle (20 001) birleşim. SPEC: sapma ≤ σ/2.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import Move, MoveType, Stock, Tool, ToolHolder, ToolKind, Toolpath
from cam.sim import ray_tool, simulate5
from tests.cam import tridexref as tr
from tests.cam.simref import ball, bull, flat

A = np.array(tr.unit(0.3, -0.2, 0.9))
TIP = np.array([1.0, 2.0, 3.0])

TOOLS = {
    "duz": flat(D=6.0, Lf=20.0),
    "kuresel": ball(D=6.0, Lf=20.0),
    "koseli": bull(D=6.0, rc=1.5, Lf=20.0),
}


def _rt(tool, o, u, T, a, part="kesen"):
    r = ray_tool(tool, tuple(o), tuple(u), tuple(T), tuple(a), part=part)
    return None if r is None else (float(r[0]), float(r[1]))


# ------------------------------------------------------------------ K2


@pytest.mark.parametrize("ad", list(TOOLS))
def test_K2_kesen_egik_eksen(ad):
    """Takımın içinden geçen rastgele ışınlar: aralık uçları ikiye bölme referansıyla 1e-9."""
    tool = TOOLS[ad]
    rng = np.random.default_rng(43)
    B = tr.basis(A)
    for _ in range(60):
        r_ic = rng.uniform(0.0, 2.6)
        phi = rng.uniform(0, 2 * math.pi)
        q = TIP + B @ np.array([r_ic * math.cos(phi), r_ic * math.sin(phi), rng.uniform(2.0, 18.0)])
        u = rng.normal(size=3)
        u /= np.linalg.norm(u)
        o = q - 7.0 * u
        ref = tr.bisect_interval(lambda P, tool=tool: tr.member_cutter(tool, P, TIP, A), o, u)
        got = _rt(tool, o, u, TIP, A)
        assert got is not None
        assert got[0] == pytest.approx(ref[0], abs=1e-9)
        assert got[1] == pytest.approx(ref[1], abs=1e-9)


@pytest.mark.parametrize("ad", list(TOOLS))
def test_K2_uc_bolgesi(ad):
    """Uca yakın (profilin eğri kısmı) ışınlar: eksene dik ve eksene paralel."""
    tool = TOOLS[ad]
    B = tr.basis(A)
    for r_ic, zeta in [(0.0, 0.3), (2.2, 1.0), (2.8, 2.0), (1.0, 0.05)]:
        q = TIP + B @ np.array([r_ic, 0.0, zeta])
        for u in (B[:, 1], B[:, 0], A, tr.unit(*(B[:, 0] + 0.4 * A))):
            u = np.asarray(u)
            if not tr.member_cutter(tool, q[None, :], TIP, A)[0]:
                continue
            o = q - 9.0 * u
            ref = tr.bisect_interval(lambda P, tool=tool: tr.member_cutter(tool, P, TIP, A), o, u)
            got = _rt(tool, o, u, TIP, A)
            assert got == (pytest.approx(ref[0], abs=1e-9), pytest.approx(ref[1], abs=1e-9))


@pytest.mark.parametrize("ad", list(TOOLS))
def test_K2_iskalayan_isin(ad):
    tool = TOOLS[ad]
    B = tr.basis(A)
    u = B[:, 1]
    for q in (TIP + B @ np.array([5.0, 0.0, 10.0]), TIP - 2.0 * A, TIP + 25.0 * A):
        assert _rt(tool, q - 10 * u, u, TIP, A) is None


def test_K2_kapali_form_silindir_kure():
    """Bilinen değerler: eksene dik, eksenden b uzaklıkta ışın; düz takımda kiriş 2√(R² − b²)."""
    B = tr.basis(A)
    u = B[:, 1]
    b = 1.8
    q = TIP + B @ np.array([b, 0.0, 10.0])
    got = _rt(TOOLS["duz"], q - 10 * u, u, TIP, A)
    w = math.sqrt(9.0 - b * b)
    assert got == (pytest.approx(10 - w, abs=1e-9), pytest.approx(10 + w, abs=1e-9))
    # küresel uçta küre merkezinden geçen dik ışın: kiriş 2R
    q = TIP + 3.0 * A
    got = _rt(TOOLS["kuresel"], q - 10 * u, u, TIP, A)
    assert got == (pytest.approx(7.0, abs=1e-9), pytest.approx(13.0, abs=1e-9))
    # eksen boyunca ışın: düz takımda [0, L_f] (uçtan iş miline)
    got = _rt(TOOLS["duz"], TIP - 5 * A, A, TIP, A)
    assert got == (pytest.approx(5.0, abs=1e-9), pytest.approx(25.0, abs=1e-9))


GOVDE = Tool(
    5,
    "govde",
    ToolKind.FLAT,
    6.0,
    10.0,
    shank_d=8.0,
    stickout=20.0,
    holder=ToolHolder("silindir", 60.0, ((0.0, 12.0), (40.0, 12.0))),
)
GOVDE_STEPS = [(4.0, 10.0), (12.0, 20.0)]  # sap (shank/2, L_f), tutucu (r, stickout)


@pytest.mark.parametrize("zeta, b", [(15.0, 0.0), (15.0, 3.0), (25.0, 0.0), (25.0, 9.5), (45.0, 11.0)])
def test_K2_govde_basamaklari(zeta, b):
    """Eksene dik ışın, uçtan ζ yükseklikte, eksenden b: sap bölgesinde ρ = 4, tutucu bölgesinde ρ = 12."""
    B = tr.basis(A)
    u = B[:, 1]
    q = TIP + B @ np.array([b, 0.0, zeta])
    o = q - 30 * u
    ref = tr.bisect_interval(lambda P: tr.member_body(GOVDE_STEPS, P, TIP, A), o, u)
    rho = 4.0 if zeta < 20.0 else 12.0
    w = math.sqrt(rho * rho - b * b)
    assert ref == (pytest.approx(30 - w, abs=1e-9), pytest.approx(30 + w, abs=1e-9))
    got = _rt(GOVDE, o, u, TIP, A, part="govde")
    assert got == (pytest.approx(ref[0], abs=1e-9), pytest.approx(ref[1], abs=1e-9))


def test_K2_govde_kesen_bolgede_yok():
    """Uçtan 5 mm yukarıda (L_f = 10 altında) eksene dik ışın gövdeye değmez; kesen kısma değer."""
    B = tr.basis(A)
    u = B[:, 1]
    q = TIP + 5.0 * A
    assert _rt(GOVDE, q - 30 * u, u, TIP, A, part="govde") is None
    assert _rt(GOVDE, q - 30 * u, u, TIP, A, part="kesen") is not None


# ------------------------------------------------------------------ K5 sabit eksenli süpürme

S_STOK = Stock(0.0, 0.0, 0.0, 30.0, 20.0, 20.0)
S_EKSEN = tr.unit(0.35, -0.25, 0.9)
S_P0 = (6.0, 6.0, 12.0)
S_P1 = (24.0, 15.0, 9.0)


def _karsilastir(td, tool, stock, cell, ref_fn, n_aile=30, en_az=0.5, tol=1e-6, seed=5):
    """Her aileden rastgele ışınlarda: beklenen = stok aralığı − referans süpürme aralığı."""
    rng = np.random.default_rng(seed)
    toplam = 0
    for aile in ("x", "y", "z"):
        isinlar = tr.rays(stock, cell, aile)
        secilen = 0
        for idx in rng.permutation(len(isinlar)):
            i, j, o, u, (lo, hi) = isinlar[idx]
            ref = ref_fn(np.array(o), np.array(u))
            if ref is None or ref[1] - ref[0] < en_az or ref[1] <= lo or ref[0] >= hi:
                continue
            beklenen = tr.fark([(lo, hi)], *ref)
            got = td.intervals(aile, i, j)
            assert len(got) == len(beklenen), (aile, i, j, got, beklenen)
            np.testing.assert_allclose(
                np.array(got, dtype=float).reshape(-1, 2), np.array(beklenen).reshape(-1, 2), rtol=0, atol=tol
            )
            secilen += 1
            if secilen >= n_aile:
                break
        assert secilen >= 10, aile
        toplam += secilen
    return toplam


@pytest.mark.parametrize("ad", ["duz", "kuresel"])
def test_K5_egik_eksenli_kanal(ad):
    tool = {"duz": flat(D=6.0, Lf=20.0), "kuresel": ball(D=6.0, Lf=20.0)}[ad]
    yol = tr.tilted_path(tool, S_EKSEN, [S_P0, S_P1])
    res = simulate5([yol], S_STOK, cell=1.0)
    a = np.array(S_EKSEN)
    _karsilastir(res.tridexel, tool, S_STOK, 1.0, lambda o, u: tr.sweep_ref(tool, o, u, S_P0, S_P1, a))


# ------------------------------------------------------------------ K6 değişen eksen

R_STOK = Stock(0.0, 0.0, 0.0, 40.0, 20.0, 30.0)
R_TIP = (15.0, 10.0, 5.0)
R_A1 = tr.axis_xz(30.0)


def _donen_program(tool):
    """Uç sabit; önce +Z eksenle sıfır boylu hareket, sonra eksen 0° → 30° (XZ düzleminde, +X'e)."""
    mv = [Move(MoveType.LINEAR, R_TIP, 300.0), Move(MoveType.LINEAR, R_TIP, 300.0, axis=R_A1)]
    return Toolpath("donen", tool, R_TIP, mv, 1000.0)


def _donen_hata(sigma: float) -> float:
    """Y ışınlarında (dönme düzlemine dik) boşluk uçlarının referanstan en büyük sapması.

    Seçim: uca göre x ∈ [−2, 12], z ∈ [3, 20] (her açıda 0 < ζ < L_f, kapaklar uçları belirlemez) ve
    referans yarı kirişi ≥ 0.8R (yan yüzey eğimi |dw/dq| = q/w ≤ 0.75 → sapma ≤ σ/2)."""
    tool = flat(D=10.0, Lf=30.0)
    res = simulate5([_donen_program(tool)], R_STOK, cell=1.0, sigma=sigma)
    td = res.tridexel
    hata = 0.0
    n = 0
    for i, k, o, u, (lo, hi) in tr.rays(R_STOK, 1.0, "y"):
        dx, dz = o[0] - R_TIP[0], o[2] - R_TIP[2]
        if not (-2.0 <= dx <= 12.0 and 3.0 <= dz <= 20.0):
            continue
        ref = tr.rotate_ref(
            tool, np.array(o), np.array(u), np.array(R_TIP), np.array([0.0, 0.0, 1.0]), np.array(R_A1)
        )
        if ref is None or (ref[1] - ref[0]) / 2 < 0.8 * 5.0:
            continue
        got = td.intervals("y", i, k)
        assert len(got) == 2, (i, k, got)
        assert got[0][0] == pytest.approx(lo) and got[1][1] == pytest.approx(hi)
        hata = max(hata, abs(got[0][1] - ref[0]), abs(got[1][0] - ref[1]))
        n += 1
    assert n >= 30
    return hata


def test_K6_degisen_eksen_sigma():
    h1 = _donen_hata(0.5)
    h2 = _donen_hata(0.25)
    assert h1 <= 0.5 / 2 + 1e-9
    assert h2 <= 0.25 / 2 + 1e-9
    assert h2 <= h1 + 1e-12  # σ yarıya inince hata azalıyor (artmıyor)
