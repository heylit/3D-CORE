"""
SPEC 68a doğrusal burkulma benchmark'ları, tet4 aşaması (specs/68a-burkulma.md, K3 tet4 maddesi, K5, K6, K9).

Testler yalnız SPEC metninden ve arayüzden yazıldı; core/burkulma.py gövdesi okunmadı.

Konsol: 10 × 10 × 200 mm kare kesit (eksen z), alt yüz (z = 0) tam tutulu,
üst yüze toplam P = 1000 N düzgün basma.
    Euler ankastre–serbest: P_cr = π² E I / (4 L²), I = b⁴/12 → 10 794.88 N.
tet4 eğilmede kilitlendiği için λ₁ P_cr'yi yukarıdan, ağ inceldikçe azalarak yaklaşır.
Kuhn ağında tet4 λ₁ ve λ₂ ayrışır (SPEC 45 modal'daki gibi);
λ₁ ≈ λ₂ ve %1 değer maddeleri tet10 aşamasındadır (67a).
"""

from __future__ import annotations

import ast
import functools
import math
from pathlib import Path

import numpy as np
import pytest

from core.assembly import assemble_K, assemble_Kg
from core.burkulma import BucklingResult, buckling
from core.elements import tet4
from core.model import BC, Element, Load, Material, Model, ModelError, Node, Section
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri, yuzey_cekmesi

E, NU = 210_000.0, 0.3
B, L, P = 10.0, 200.0, 1000.0
I_KESIT = B**4 / 12.0
P_CR = math.pi**2 * E * I_KESIT / (4 * L**2)
KOK = Path(__file__).resolve().parents[2]


def celik() -> Material:
    return Material("celik", E, NU)


def konsol_modeli(k: int, basma: bool = True) -> Model:
    """k × k × 20k Kuhn ağı, alt yüz tam tutulu, üst yüzde toplam ∓P eksenel yük."""
    m = kutu_agi(B, B, L, k, k, 20 * k, celik(), name=f"burkulma_{k}")
    for n in yuz_dugumleri(m, 2, 0.0):
        m.bcs.extend(BC(n, d) for d in ("ux", "uy", "uz"))
    t = -P / B**2 if basma else P / B**2
    m.loads = yuzey_cekmesi(m, 2, L, (0.0, 0.0, t))
    return m


@functools.cache
def konsol(k: int, basma: bool = True) -> tuple[Model, BucklingResult]:
    m = konsol_modeli(k, basma)
    return m, buckling(m, 4)


def tutulu_maske(m: Model) -> np.ndarray:
    maske = np.zeros(m.n_dof, dtype=bool)
    for bc in m.bcs:
        maske[m.dof_index(bc.node, bc.dof)] = True
    return maske


def test_referans_deger():
    """SPEC'teki sayısal örnek (testin kendi aritmetiği)."""
    assert P_CR == pytest.approx(10_794.88, abs=0.01)


# --- K3 (tet4): yukarıdan yakınsama ------------------------------------------------------

SLOW = pytest.mark.slow
K_LISTESI = [2, 4, pytest.param(8, marks=SLOW)]


@pytest.mark.parametrize("k", K_LISTESI)
def test_konsol_lambda1_yukaridan(k):
    _, r = konsol(k)
    assert r.lam[0] * P > P_CR


@pytest.mark.parametrize("k1, k2", [(2, 4), pytest.param(4, 8, marks=SLOW)])
def test_konsol_lambda1_inceltmede_azalir(k1, k2):
    assert konsol(k2)[1].lam[0] < konsol(k1)[1].lam[0]


@pytest.mark.parametrize("k", [2, 4])
def test_konsol_sonuc_bicimi(k):
    """lam (4,) |λ| artan, basmada pozitif; modes (n_dof, 4), max |φ| = 1, tutulu DOF'larda 0."""
    m, r = konsol(k)
    assert r.lam.shape == (4,)
    assert r.modes.shape == (m.n_dof, 4)
    assert r.u0.shape == (m.n_dof,)
    assert np.all(np.isfinite(r.lam)) and np.all(np.isfinite(r.modes))
    assert np.all(np.diff(np.abs(r.lam)) >= 0.0)
    assert np.all(r.lam > 0.0)
    np.testing.assert_allclose(np.abs(r.modes).max(axis=0), 1.0, rtol=1e-12)
    assert np.all(r.modes[tutulu_maske(m)] == 0.0)


@pytest.mark.parametrize("k", [2, 4])
def test_konsol_u0_statik_cozum(k):
    """u0 referans yük altındaki statik çözümdür (solve ile aynı)."""
    m, r = konsol(k)
    u = solve(m).u
    np.testing.assert_allclose(r.u0, u, rtol=0, atol=1e-10 * np.abs(u).max())


@pytest.mark.parametrize("k", [2, 4])
def test_konsol_ozdeger_artigi(k):
    """(K + λ Kg(σ0)) φ = 0 serbest DOF'larda; σ0 = tet4.stress(u0) (testin kendi kurduğu Kg)."""
    m, r = konsol(k)
    sigma0 = {e.id: tet4.stress(e, m, r.u0) for e in m.elements}
    f = np.flatnonzero(~tutulu_maske(m))
    K = assemble_K(m)[f][:, f]
    Kg = assemble_Kg(m, sigma0)[f][:, f]
    for i, lam in enumerate(r.lam):
        phi = r.modes[f, i]
        Kphi = K @ phi
        assert np.linalg.norm(Kphi + lam * (Kg @ phi)) <= 1e-6 * np.linalg.norm(Kphi)


@pytest.mark.parametrize("k", [2, 4])
def test_konsol_birinci_mod_enine(k):
    """Birinci mod eğilmedir: enine yer değiştirme baskın, uçta eksenel bileşen küçük, tabandan uca artar."""
    m, r = konsol(k)
    phi = r.modes[:, 0]
    U = np.array([[phi[m.dof_index(n.id, d)] for d in ("ux", "uy", "uz")] for n in m.nodes])
    enine = np.hypot(U[:, 0], U[:, 1])
    assert np.abs(U[:, 2]).max() < 0.2 * enine.max()
    z = np.array([n.z for n in m.nodes])
    uc, orta = enine[np.abs(z - L) < 1e-9].mean(), enine[np.abs(z - L / 2) < 1e-9].mean()
    assert uc > orta > 0.0


# --- K5: işaret ------------------------------------------------------------------------------


@pytest.mark.parametrize("k", [2, 4])
def test_cekmede_tum_lambda_negatif(k):
    """Yük çekmeye çevrilince bütün λ negatif; atılmaz, raporlanır; simetri: λ_çekme = −λ_basma."""
    _, basma = konsol(k)
    _, cekme = konsol(k, basma=False)
    assert cekme.lam.shape == (4,)
    assert np.all(cekme.lam < 0.0)
    np.testing.assert_allclose(cekme.lam, -basma.lam, rtol=1e-6)


# --- K6: hatalar -----------------------------------------------------------------------------------


def kucuk_konsol() -> Model:
    m = kutu_agi(2.0, 2.0, 10.0, 1, 1, 5, celik(), name="kucuk")
    for n in yuz_dugumleri(m, 2, 0.0):
        m.bcs.extend(BC(n, d) for d in ("ux", "uy", "uz"))
    m.loads = yuzey_cekmesi(m, 2, 10.0, (0.0, 0.0, -10.0))
    return m


def test_kucuk_konsol_calisir():
    """Hata testlerinin tabanı geçerli bir model (yalnız hatayı ekleyen değişiklik düşürür)."""
    r = buckling(kucuk_konsol(), 2)
    assert r.lam.shape == (2,)
    assert np.all(r.lam > 0)


def test_hata_yuk_yok():
    m = kucuk_konsol()
    m.loads = []
    with pytest.raises(ModelError):
        buckling(m)


@pytest.mark.parametrize("n_modes", [0, -1])
def test_hata_gecersiz_mod_sayisi(n_modes):
    with pytest.raises(ModelError):
        buckling(kucuk_konsol(), n_modes)


def test_hata_mesnet_yok():
    m = kucuk_konsol()
    m.bcs = []
    with pytest.raises(ModelError):
        buckling(m)


def test_hata_serbest_dof_yok():
    m = kucuk_konsol()
    m.bcs = [BC(n.id, d) for n in m.nodes for d in ("ux", "uy", "uz")]
    with pytest.raises(ModelError):
        buckling(m, 1)


def test_hata_gerilmesiz_model():
    """Yük yalnız tutulu DOF'larda: u0 = 0, σ0 = 0, bütün λ sonsuz → ModelError."""
    m = kucuk_konsol()
    taban = yuz_dugumleri(m, 2, 0.0)
    m.loads = [Load(taban[0], "uz", -100.0)]
    with pytest.raises(ModelError):
        buckling(m, 1)


def test_hata_kg_saglamayan_eleman():
    """bar1d kg sağlamaz → ModelError."""
    m = Model(
        dim=1,
        nodes=[Node(i + 1, 10.0 * i) for i in range(4)],
        elements=[Element(i + 1, "bar1d", [i + 1, i + 2], "celik", "s") for i in range(3)],
        materials=[celik()],
        sections=[Section("s", 10.0)],
        bcs=[BC(1, "ux")],
        loads=[Load(4, "ux", -100.0)],
    )
    with pytest.raises(ModelError):
        buckling(m, 1)


# --- K9: bağımlılık ----------------------------------------------------------------------------------


def test_burkulma_bagimliliklari():
    """core/burkulma.py yalnız numpy, scipy, core ve standart kütüphane modüllerini import eder."""
    kaynak = (KOK / "core" / "burkulma.py").read_text(encoding="utf-8")
    izinli_ust = {"numpy", "scipy", "core", "__future__", "dataclasses", "typing", "math", "collections"}
    for dugum in ast.walk(ast.parse(kaynak)):
        if isinstance(dugum, ast.Import):
            adlar = [a.name for a in dugum.names]
        elif isinstance(dugum, ast.ImportFrom):
            assert dugum.level == 0, "göreli import"
            adlar = [dugum.module or ""]
        else:
            continue
        for ad in adlar:
            assert ad.split(".")[0] in izinli_ust, ad
