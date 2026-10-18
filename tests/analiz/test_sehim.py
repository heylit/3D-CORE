"""
SPEC 45 kesme kuvveti altında sehim testleri (specs/45-modal.md, K13, K14).

Testler yalnız SPEC metninden yazıldı; analiz/ uygulama kodu okunmadı. gmsh / OCCT gerekmez:
ağ SPEC 11 Kuhn kutu ağıdır (tests/benchmarks/tet_ag.py).

Referans (kesmeli Timoshenko konsolu): δ_T = PL³/(3EI) + PL/(κGA), κ = 5/6.
Uyumlu eleman δ'yı alttan verir (δ < δ_T) ve inceltmede artar.
"""

from __future__ import annotations

import copy
import functools

import numpy as np
import pytest

import mesh
from analiz import Sehim, kesme_sehimi, nokta_kuvveti
from core.model import BC, Element, Load, Material, Model, ModelError, Node, Section
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri

E, NU, RHO = 210_000.0, 0.3, 7.85e-9
L, B, H = 100.0, 10.0, 10.0
P = 1000.0
G = E / (2 * (1 + NU))
I_KESIT = B * H**3 / 12.0
DELTA_T = P * L**3 / (3 * E * I_KESIT) + P * L / (5 / 6 * G * B * H)
NOKTA = (L, B / 2, H / 2)
F_KESME = (0.0, 0.0, -P)


def celik() -> Material:
    return Material("celik", E, NU, RHO)


@functools.cache
def _konsol(k: int) -> Model:
    m = kutu_agi(L, B, H, 10 * k, k, k, celik(), name=f"konsol_{k}")
    for n in yuz_dugumleri(m, 0, 0.0):
        m.bcs.extend(BC(n, d) for d in ("ux", "uy", "uz"))
    return m


def konsol(k: int) -> Model:
    """Her çağrıda taze kopya (önbellekteki model testler arasında değişmesin)."""
    return copy.deepcopy(_konsol(k))


def sinir_dugumleri(m: Model) -> set[int]:
    return {int(i) for i in np.asarray(mesh.boundary_triangles(m)).ravel()}


def kucuk_yaricap(k: int) -> float:
    """Yalnız uç yüz merkez düğümü: ızgara aralığının çeyreği."""
    return 0.25 * H / k


# Uç yüzün içine çizilen disk (r = b/2): bir küre uç yüzün köşelerini alırken kenar yüzlerdeki
# x = L − aralık düğümlerini dışarıda bırakamadığı için "uç yüzün tamamı" bu diskle temsil edilir.
BUYUK_YARICAP = B / 2


@functools.cache
def sehim(k: int, yaricap: float) -> Sehim:
    return kesme_sehimi(konsol(k), NOKTA, F_KESME, yaricap)


# --- K13: konsol --------------------------------------------------------------------------


@pytest.mark.parametrize("k", [2, 4, pytest.param(8, marks=pytest.mark.slow)])
def test_kucuk_yaricap_yalniz_merkez_dugum(k):
    m = konsol(k)
    s = sehim(k, kucuk_yaricap(k))
    assert len(s.dugumler) == 1
    np.testing.assert_allclose(m.node(s.dugumler[0]).xyz, NOKTA, atol=1e-12)


@pytest.mark.parametrize("k", [2, 4, pytest.param(8, marks=pytest.mark.slow)])
def test_buyuk_yaricap_uc_yuz_diski(k):
    """r = b/2: seçilen düğümler tam olarak uç yüzdeki diskin düğümleri."""
    m = konsol(k)
    s = sehim(k, BUYUK_YARICAP)
    beklenen = sorted(
        n.id for n in m.nodes if abs(n.x - L) < 1e-9 and np.linalg.norm(n.xyz - NOKTA) <= BUYUK_YARICAP + 1e-9
    )
    assert s.dugumler == beklenen
    assert len(beklenen) > 1


@pytest.mark.parametrize("buyuk", [False, True], ids=["merkez", "uc_yuz"])
@pytest.mark.parametrize("k", [2, 4, pytest.param(8, marks=pytest.mark.slow)])
def test_delta_timoshenko_altinda(k, buyuk):
    r = BUYUK_YARICAP if buyuk else kucuk_yaricap(k)
    s = sehim(k, r)
    assert 0.0 < s.delta < DELTA_T


@pytest.mark.parametrize("buyuk", [False, True], ids=["merkez", "uc_yuz"])
@pytest.mark.parametrize("k1, k2", [(2, 4), pytest.param(4, 8, marks=pytest.mark.slow)])
def test_delta_inceltmede_artar(k1, k2, buyuk):
    r1 = BUYUK_YARICAP if buyuk else kucuk_yaricap(k1)
    r2 = BUYUK_YARICAP if buyuk else kucuk_yaricap(k2)
    assert sehim(k2, r2).delta > sehim(k1, r1).delta


@pytest.mark.slow
def test_k8_uc_yuz_delta_orani():
    """k = 8, uç yüz: δ / δ_T ≥ 0.90 (SPEC ön hesabı 0.930)."""
    assert sehim(8, BUYUK_YARICAP).delta / DELTA_T >= 0.90


@pytest.mark.parametrize("buyuk", [False, True], ids=["merkez", "uc_yuz"])
@pytest.mark.parametrize("k", [2, 4])
def test_elle_yuk_ve_solve_ile_ayni(k, buyuk):
    """Aynı düğüm yükleri elle eklenip solve ile çözülen modelle δ ve u aynı (rel 1e-12)."""
    yaricap = BUYUK_YARICAP if buyuk else kucuk_yaricap(k)
    s = sehim(k, yaricap)
    m = konsol(k)
    S = s.dugumler
    for n in S:
        m.loads.append(Load(n, "uz", -P / len(S)))
    r = solve(m)
    np.testing.assert_allclose(s.u, r.u, rtol=1e-12, atol=1e-12 * np.abs(r.u).max())
    U = np.array([[r.u[m.dof_index(n, d)] for d in ("ux", "uy", "uz")] for n in S])
    u_p = U.mean(axis=0)
    np.testing.assert_allclose(s.u_nokta, u_p, rtol=1e-12, atol=1e-12 * np.abs(u_p).max())
    F = np.array(F_KESME)
    assert s.delta == pytest.approx(F @ u_p / np.linalg.norm(F), rel=1e-12)


@pytest.mark.parametrize("k", [2, 4])
def test_is_eslenigi_ve_rijitlik(k):
    """Fᵀu = |F| δ (düğüm yükleri üzerinden), k = |F| / δ, u_maks = en büyük düğüm yer değiştirmesi."""
    s = sehim(k, BUYUK_YARICAP)
    m = konsol(k)
    F_dugum = np.zeros(m.n_dof)
    for n in s.dugumler:
        F_dugum[m.dof_index(n, "uz")] = -P / len(s.dugumler)
    assert F_dugum @ s.u == pytest.approx(P * s.delta, rel=1e-12)
    assert s.k == pytest.approx(P / s.delta, rel=1e-12)
    assert s.u.shape == (m.n_dof,)
    assert s.u_nokta.shape == (3,)
    U = s.u.reshape(-1, 3)
    assert s.u_maks == pytest.approx(np.linalg.norm(U, axis=1).max(), rel=1e-12)


def test_verilen_model_degismez():
    m = konsol(2)
    once = copy.deepcopy(m)
    kesme_sehimi(m, NOKTA, F_KESME, BUYUK_YARICAP)
    assert m.loads == []
    assert m == once


def test_egik_kuvvet_delta_izdusum():
    """F eğik olduğunda δ = F̂ · u_p (bileşenler toplanmaz)."""
    m = konsol(2)
    F = np.array([200.0, -300.0, -600.0])
    s = kesme_sehimi(m, NOKTA, F, BUYUK_YARICAP)
    assert s.delta == pytest.approx(F @ s.u_nokta / np.linalg.norm(F), rel=1e-12)
    assert s.delta > 0.0
    assert s.k == pytest.approx(np.linalg.norm(F) / s.delta, rel=1e-12)


# --- K14: nokta_kuvveti -----------------------------------------------------------------------


def test_nokta_kuvveti_bileske_ve_sira():
    m = konsol(2)
    F = np.array([120.0, 0.0, -450.0])
    S = nokta_kuvveti(m, NOKTA, F, BUYUK_YARICAP)
    assert S == sorted(S)
    toplam = np.zeros(3)
    for ld in m.loads:
        toplam[("ux", "uy", "uz").index(ld.dof)] += ld.value
    np.testing.assert_allclose(toplam, F, atol=1e-12 * np.linalg.norm(F))
    # düğüm id'si artan, ux, uy, uz sırası, tam sıfır bileşen yok, her biri F/|S|
    beklenen = [(n, d, F[i] / len(S)) for n in S for i, d in enumerate(("ux", "uy", "uz")) if F[i] != 0.0]
    assert [(ld.node, ld.dof) for ld in m.loads] == [(n, d) for n, d, _ in beklenen]
    for ld, (_, _, v) in zip(m.loads, beklenen, strict=True):
        assert ld.value == pytest.approx(v, rel=1e-12)


def test_nokta_kuvveti_yerinde_ekler():
    """Model yerinde değişir; mevcut yükler korunur, yenileri eklenir."""
    m = konsol(2)
    m.loads.append(Load(1, "ux", 5.0))
    S = nokta_kuvveti(m, NOKTA, F_KESME, kucuk_yaricap(2))
    assert m.loads[0] == Load(1, "ux", 5.0)
    assert len(m.loads) == 1 + len(S)


def test_nokta_kuvveti_yalniz_sinir_dugumleri():
    """Yarıçap iç düğümleri de kapsıyor; yalnız sınır düğümleri seçilir, sınırdakilerin hepsi seçilir."""
    m = konsol(4)
    p = np.array([L, B / 2, H / 2])
    r = 3.0  # aralık 2.5: x = 97.5'teki iç düğüm (97.5, 5, 5) yarıçap içinde
    ic = [n.id for n in m.nodes if np.linalg.norm(n.xyz - p) <= r and n.id not in sinir_dugumleri(m)]
    assert ic  # testin kendi güvencesi
    S = nokta_kuvveti(m, p, F_KESME, r)
    sinir = sinir_dugumleri(m)
    beklenen = sorted(n.id for n in m.nodes if n.id in sinir and np.linalg.norm(n.xyz - p) <= r)
    assert S == beklenen
    assert not set(ic) & set(S)


def test_nokta_kuvveti_kenar_yuzunde():
    """Üst yüzde (z = h) bir nokta: seçim yarıçaptaki sınır düğümleri, bileşke F."""
    m = konsol(2)
    p = np.array([60.0, 5.0, H])
    S = nokta_kuvveti(m, p, (0.0, 0.0, -100.0), 5.5)
    sinir = sinir_dugumleri(m)
    assert S == sorted(n.id for n in m.nodes if n.id in sinir and np.linalg.norm(n.xyz - p) <= 5.5)
    assert sum(ld.value for ld in m.loads) == pytest.approx(-100.0, rel=1e-12)


def test_hata_yaricapta_dugum_yok():
    m = konsol(2)
    with pytest.raises(ModelError):
        nokta_kuvveti(m, (50.0, 5.0, 5.0), F_KESME, 1.0)  # kutunun ortası: yakında sınır düğümü yok
    with pytest.raises(ModelError):
        nokta_kuvveti(m, (500.0, 5.0, 5.0), F_KESME, 3.0)


@pytest.mark.parametrize("F", [(0.0, 0.0, 0.0), (0.0, -0.0, 0.0)])
def test_hata_sifir_kuvvet(F):
    with pytest.raises(ModelError):
        nokta_kuvveti(konsol(2), NOKTA, F, BUYUK_YARICAP)
    with pytest.raises(ModelError):
        kesme_sehimi(konsol(2), NOKTA, F, BUYUK_YARICAP)


@pytest.mark.parametrize("yaricap", [0.0, -1.0, float("nan"), float("inf")])
def test_hata_yaricap(yaricap):
    with pytest.raises(ModelError):
        nokta_kuvveti(konsol(2), NOKTA, F_KESME, yaricap)


def test_hata_boyut_3_degil():
    m = Model(
        dim=1,
        nodes=[Node(1, 0.0), Node(2, 10.0)],
        elements=[Element(1, "bar1d", [1, 2], "celik", "s")],
        materials=[celik()],
        sections=[Section("s", 1.0)],
        bcs=[BC(1, "ux")],
    )
    with pytest.raises(ModelError):
        nokta_kuvveti(m, (10.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1.0)
    with pytest.raises(ModelError):
        kesme_sehimi(m, (10.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1.0)


@pytest.mark.parametrize(
    "nokta, F",
    [
        ((L, 5.0, float("nan")), F_KESME),
        ((L, 5.0), F_KESME),
        ((L, 5.0, 5.0, 0.0), F_KESME),
        (NOKTA, (0.0, float("inf"), -1.0)),
        (NOKTA, (0.0, -1.0)),
        (NOKTA, (0.0, float("nan"), -1.0)),
    ],
)
def test_hata_sonlu_olmayan_veya_bicimsiz_girdi(nokta, F):
    with pytest.raises(ModelError):
        nokta_kuvveti(konsol(2), nokta, F, BUYUK_YARICAP)
    with pytest.raises(ModelError):
        kesme_sehimi(konsol(2), nokta, F, BUYUK_YARICAP)


def test_hata_kesme_sehimi_dolu_yukler():
    """Karışık yük sessizce toplanmaz."""
    m = konsol(2)
    m.loads.append(Load(1, "uz", 1.0))
    with pytest.raises(ModelError):
        kesme_sehimi(m, NOKTA, F_KESME, BUYUK_YARICAP)


def test_hata_mekanizma():
    """Mesnetsiz model: çözücü hatası aynen ModelError."""
    m = konsol(2)
    m.bcs = []
    with pytest.raises(ModelError):
        kesme_sehimi(m, NOKTA, F_KESME, BUYUK_YARICAP)
