"""
SPEC 45 modal analiz benchmark'ları (specs/45-modal.md, K3–K11, K16).

Testler yalnız SPEC metninden yazıldı; uygulama kodu okunmadı. Beklenen değerler kapalı formüllerden:
- Ayrık çubuk (eşit N eleman, h = L/N, c² = E/ρ), tam ayrık çözüm:
    tutarlı ωₙ² = 6c²/h² · (1 − cos θₙ)/(2 + cos θₙ),  toplanmış ωₙ² = 4c²/h² · sin²(θₙ/2)
    iki ucu tutulu θₙ = nπ/N (n = 1..N−1), ankastre–serbest θₙ = (2n−1)π/(2N) (n = 1..N)
- Sürekli çubuk ankastre–serbest fₙ = (2n−1) c / (4L)
- Euler–Bernoulli konsol fᵢ = (βᵢL)²/(2πL²) · √(EI/(ρA)), β₁L = 1.875104, β₂L = 4.694091
- Eksenel konsol f_ax = √(E/ρ)/(4L); ilk eğilme modu etkin kütlesi 0.6131 ρV (Blevins Tablo 8-16)

Kuhn ağı tests/benchmarks/tet_ag.py'den (SPEC 11). Birimler N – mm – t – s.
"""

from __future__ import annotations

import functools
import math
from pathlib import Path

import numpy as np
import pytest
import scipy.linalg as sla

from core.assembly import assemble_K, assemble_M
from core.modal import ModalResult, effective_mass, modal, model_mass
from core.model import BC, Element, Material, Model, Node, Section
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri

E, NU, RHO = 210_000.0, 0.3, 7.85e-9
C2 = E / RHO  # c² [mm²/s²]
ORNEK = Path(__file__).resolve().parents[2] / "examples" / "45_modal_cubuk.json"


def celik(rho: float = RHO) -> Material:
    return Material("celik", E, NU, rho)


# --- ortak yardımcılar ----------------------------------------------------------------


def tutulu_maske(model: Model) -> np.ndarray:
    maske = np.zeros(model.n_dof, dtype=bool)
    for bc in model.bcs:
        maske[model.dof_index(bc.node, bc.dof)] = True
    return maske


def tet_M_referans(model: Model, lumped: bool = False) -> np.ndarray:
    """Testin kendi yoğun tet4 kütle matrisi: ρV/20 · (1 + δ_ab) ⊗ I₃ veya ρV/4 · I₁₂."""
    M = np.zeros((model.n_dof, model.n_dof))
    B = np.kron(np.ones((4, 4)) + np.eye(4), np.eye(3)) / 20.0
    for e in model.elements:
        X = np.array([model.node(n).xyz for n in e.nodes])
        rhoV = model.material(e.material).rho * abs(np.linalg.det(X[1:] - X[0])) / 6.0
        d = np.array([model.dof_index(n, a) for n in e.nodes for a in ("ux", "uy", "uz")])
        M[np.ix_(d, d)] += rhoV * (np.eye(12) / 4.0 if lumped else B)
    return M


def serbest_KM(model: Model, lumped: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(serbest DOF indeksleri, K_ff, M_ff) yoğun."""
    f = np.flatnonzero(~tutulu_maske(model))
    K = assemble_K(model).toarray()
    M = assemble_M(model, lumped=lumped).toarray()
    return f, K[np.ix_(f, f)], M[np.ix_(f, f)]


def dogrula(model: Model, r: ModalResult, rijit: int = 0) -> None:
    """K6: diklik, artık, tutulu DOF'larda sıfır, işaret kuralı, ω / f tutarlılığı.

    rijit: başta ω ≈ 0 olan mod sayısı; onların artığı ‖K φ‖ ölçeğiyle değil ω²_maks ölçeğiyle sınanır.
    """
    k = len(r.omega2)
    assert r.modes.shape == (model.n_dof, k)
    assert r.omega.shape == r.f.shape == (k,)
    assert np.all(np.isfinite(r.modes)) and np.all(np.isfinite(r.omega2))
    assert np.all(r.omega2 >= 0.0)
    assert np.all(np.diff(r.omega2) >= 0.0)
    np.testing.assert_allclose(r.omega, np.sqrt(r.omega2), rtol=1e-12, atol=0)
    np.testing.assert_allclose(r.f, r.omega / (2 * np.pi), rtol=1e-12, atol=0)

    tutulu = tutulu_maske(model)
    assert np.all(r.modes[tutulu] == 0.0)

    f, K, M = serbest_KM(model, lumped=r.lumped)
    P = r.modes[f]
    np.testing.assert_allclose(P.T @ M @ P, np.eye(k), atol=1e-9)
    w2_maks = r.omega2.max()
    np.testing.assert_allclose(P.T @ K @ P, np.diag(r.omega2), atol=1e-8 * w2_maks)
    for i in range(k):
        phi = P[:, i]
        Kphi = K @ phi
        artik = np.linalg.norm(Kphi - r.omega2[i] * (M @ phi))
        if i < rijit:
            assert artik <= 1e-8 * w2_maks * np.linalg.norm(M @ phi)
        else:
            assert artik <= 1e-8 * np.linalg.norm(Kphi)
        # işaret kuralı: mutlak değeri en büyük bileşen pozitif
        v = r.modes[:, i]
        assert v.max() >= (1.0 - 1e-9) * np.abs(v).max()


# --- çubuk modelleri ---------------------------------------------------------------------


def cubuk(N: int, L: float = 100.0, A: float = 10.0, iki_uc: bool = False) -> Model:
    """Eşit N elemanlı çubuk, x = 0 tutulu (iki_uc ise x = L de)."""
    m = Model(
        dim=1,
        nodes=[Node(i + 1, L * i / N) for i in range(N + 1)],
        elements=[Element(i + 1, "bar1d", [i + 1, i + 2], "celik", "s") for i in range(N)],
        materials=[celik()],
        sections=[Section("s", A)],
        bcs=[BC(1, "ux")],
    )
    if iki_uc:
        m.bcs.append(BC(N + 1, "ux"))
    return m


def ayrik_cubuk_omega2(N: int, L: float, iki_uc: bool, lumped: bool) -> np.ndarray:
    h = L / N
    n = np.arange(1, N) if iki_uc else np.arange(1, N + 1)
    theta = n * np.pi / N if iki_uc else (2 * n - 1) * np.pi / (2 * N)
    if lumped:
        return 4 * C2 / h**2 * np.sin(theta / 2) ** 2
    return 6 * C2 / h**2 * (1 - np.cos(theta)) / (2 + np.cos(theta))


# --- K3: tek eleman ----------------------------------------------------------------------


def test_cubuk_tek_eleman_tutarli():
    L = 250.0
    r = modal(cubuk(1, L=L), 1)
    assert r.omega2[0] == pytest.approx(3 * E / (RHO * L**2), rel=1e-12)
    assert r.lumped is False


def test_cubuk_tek_eleman_toplanmis():
    L = 250.0
    r = modal(cubuk(1, L=L), 1, lumped=True)
    assert r.omega2[0] == pytest.approx(2 * E / (RHO * L**2), rel=1e-12)
    assert r.lumped is True


def test_cubuk_tek_eleman_mod_sekli():
    """Tek serbest DOF: φ = 1/√m₂₂ (pozitif), tutulu düğümde 0."""
    L, A = 250.0, 10.0
    m = cubuk(1, L=L, A=A)
    r = modal(m, 1)
    assert r.mode(m, 0, 2, "ux") == pytest.approx(1 / math.sqrt(RHO * A * L / 3), rel=1e-12)
    assert r.mode(m, 0, 1) == 0.0


# --- K4: ayrık çubuk tam çözümü --------------------------------------------------------------


@pytest.mark.parametrize("iki_uc", [False, True], ids=["ankastre_serbest", "iki_ucu_tutulu"])
@pytest.mark.parametrize("lumped", [False, True], ids=["tutarli", "toplanmis"])
def test_cubuk_ayrik_tam_cozum(iki_uc, lumped):
    N, L = 10, 100.0
    m = cubuk(N, L=L, iki_uc=iki_uc)
    beklenen = ayrik_cubuk_omega2(N, L, iki_uc, lumped)
    r = modal(m, len(beklenen), lumped=lumped)
    np.testing.assert_allclose(r.omega2, beklenen, rtol=1e-10)
    dogrula(m, r)


@pytest.mark.parametrize("iki_uc", [False, True], ids=["ankastre_serbest", "iki_ucu_tutulu"])
def test_cubuk_ayrik_mod_sekli_sinus(iki_uc):
    """Tam ayrık çözüm sinüs modlarıdır: φₙ(xⱼ) ∝ sin(θₙ j); izdüşüm testinden bağımsız ölçü."""
    N, L = 10, 100.0
    m = cubuk(N, L=L, iki_uc=iki_uc)
    beklenen = ayrik_cubuk_omega2(N, L, iki_uc, False)
    r = modal(m, len(beklenen))
    j = np.arange(N + 1)
    for i in range(len(beklenen)):
        n = i + 1
        theta = n * np.pi / N if iki_uc else (2 * n - 1) * np.pi / (2 * N)
        s = np.sin(theta * j)
        phi = r.modes[:, i]
        cos_aci = abs(s @ phi) / (np.linalg.norm(s) * np.linalg.norm(phi))
        assert cos_aci == pytest.approx(1.0, abs=1e-10)


# --- K5: sürekli çubuğa yakınsama ------------------------------------------------------------


def test_cubuk_surekli_yakinsama():
    N, L = 100, 100.0
    m = cubuk(N, L=L)
    tam = np.array([(2 * n - 1) * math.sqrt(C2) / (4 * L) for n in (1, 2, 3)])
    rt = modal(m, 3)
    rk = modal(m, 3, lumped=True)
    assert np.all(rt.f >= tam)
    assert np.all(rk.f <= tam)
    np.testing.assert_allclose(rt.f / tam, 1.0, atol=1e-3)
    np.testing.assert_allclose(rk.f / tam, 1.0, atol=1e-3)
    dogrula(m, rt)
    dogrula(m, rk)


# --- K16: örnek dosya ------------------------------------------------------------------------


def test_ornek_45_modal_cubuk():
    m = Model.from_json(ORNEK)
    r = modal(m, 3)
    np.testing.assert_allclose(r.omega2, ayrik_cubuk_omega2(10, 100.0, False, False)[:3], rtol=1e-10)
    dogrula(m, r)


# --- K11: etkin kütle --------------------------------------------------------------------------


@pytest.mark.parametrize("lumped", [False, True])
def test_etkin_kutle_cubuk_tum_modlar(lumped):
    N = 10
    m = cubuk(N)
    r = modal(m, N, lumped=lumped)
    me = effective_mass(m, r)
    assert me.shape == (N, 1)
    assert np.all(me >= 0.0)
    f, _, M = serbest_KM(m, lumped=lumped)
    rd = np.ones(len(f))
    assert me[:, 0].sum() == pytest.approx(rd @ M @ rd, rel=1e-9)


def test_etkin_kutle_cubuk_ilk_mod_baskin():
    """Ankastre–serbest çubukta ilk modun etkin kütlesi ≈ 8/π² ρAL (süreklide), en büyüktür."""
    m = cubuk(100)
    me = effective_mass(m, modal(m, 3))
    assert me[0, 0] / model_mass(m) == pytest.approx(8 / np.pi**2, rel=2e-3)
    assert me[0, 0] > me[1, 0] > me[2, 0]


def kucuk_konsol(rho: float = RHO) -> Model:
    m = kutu_agi(4.0, 2.0, 1.0, 2, 1, 1, celik(rho), name="kucuk_konsol")
    sabitle(m)
    return m


def sabitle(m: Model) -> None:
    for n in yuz_dugumleri(m, 0, 0.0):
        m.bcs.extend(BC(n, d) for d in ("ux", "uy", "uz"))


@pytest.mark.parametrize("lumped", [False, True])
def test_etkin_kutle_tet_tum_modlar(lumped):
    m = kucuk_konsol()
    n_f = int((~tutulu_maske(m)).sum())
    r = modal(m, n_f, lumped=lumped)
    me = effective_mass(m, r)
    assert me.shape == (n_f, 3)
    assert np.all(me >= 0.0)
    f, _, M = serbest_KM(m, lumped=lumped)
    for d, ad in enumerate(("ux", "uy", "uz")):
        rd = np.array([1.0 if i % 3 == d else 0.0 for i in f])
        assert me[:, d].sum() == pytest.approx(rd @ M @ rd, rel=1e-9), ad
    dogrula(m, r)


# --- K7: yoğun ve Lanczos yolları -------------------------------------------------------------


@functools.cache
def orta_konsol() -> Model:
    """12 x 2 x 2 Kuhn konsolu, n_f = 324 > 300 (Lanczos yolu)."""
    m = kutu_agi(100.0, 10.0, 10.0, 12, 2, 2, celik(), name="orta_konsol")
    sabitle(m)
    assert (~tutulu_maske(m)).sum() > 300
    return m


def izdusum(P: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Mod uzayı izdüşümü Φ Φᵀ M (taban seçiminden bağımsız)."""
    return P @ P.T @ M


@pytest.mark.parametrize("lumped", [False, True])
def test_lanczos_yogun_ayni(lumped):
    m = orta_konsol()
    f = np.flatnonzero(~tutulu_maske(m))
    K = assemble_K(m).toarray()[np.ix_(f, f)]
    M = tet_M_referans(m, lumped=lumped)[np.ix_(f, f)]
    w2, V = sla.eigh(K, M)
    r = modal(m, 6, lumped=lumped)
    np.testing.assert_allclose(r.f, np.sqrt(w2[:6]) / (2 * np.pi), rtol=1e-8)
    assert w2[6] > 1.1 * w2[5]  # izdüşümün tanımlı olması için boşluk (testin güvencesi)
    fark = izdusum(r.modes[f], M) - izdusum(V[:, :6], M)
    assert np.abs(fark).max() <= 1e-6
    dogrula(m, r)


def test_lanczos_yogun_tek_mod_yogun_yol():
    """n_modes > n_f − 2 → yoğun yol; aynı modelin ilk 6 frekansı Lanczos sonucuyla aynı."""
    m = orta_konsol()
    n_f = int((~tutulu_maske(m)).sum())
    hepsi = modal(m, n_f - 1)
    alti = modal(m, 6)
    np.testing.assert_allclose(hepsi.f[:6], alti.f, rtol=1e-8)


# --- K8: mesnetsiz kutu ---------------------------------------------------------------------------


@functools.cache
def serbest_kutu() -> tuple[Model, ModalResult]:
    m = kutu_agi(30.0, 15.0, 15.0, 6, 3, 3, celik(), name="serbest_kutu")
    assert m.n_dof > 300
    return m, modal(m, 7)


def rijit_cisim_tabani(m: Model) -> np.ndarray:
    """3 öteleme + 3 dönme (ağırlık merkezi etrafında), (n_dof, 6)."""
    X = np.array([n.xyz for n in m.nodes])
    X = X - X.mean(axis=0)
    R = np.zeros((m.n_dof, 6))
    for d in range(3):
        R[d::3, d] = 1.0
    for j, ekse in enumerate(np.eye(3)):
        R[:, 3 + j] = np.cross(ekse, X).ravel()
    return R


def test_serbest_kutu_rijit_modlar():
    m, r = serbest_kutu()
    assert r.omega2[6] > 0.0
    assert np.all(r.omega2[:6] <= 1e-8 * r.omega2[6])
    M = tet_M_referans(m)
    R = rijit_cisim_tabani(m)
    P_rijit = R @ np.linalg.solve(R.T @ M @ R, R.T @ M)
    fark = izdusum(r.modes[:, :6], M) - P_rijit
    assert np.abs(fark).max() <= 1e-6


def test_serbest_kutu_diklik():
    m, r = serbest_kutu()
    dogrula(m, r, rijit=6)


# --- K10: değişmezlikler ------------------------------------------------------------------------------


def degismez_kutu(rho: float = RHO, s: float = 1.0, R: np.ndarray | None = None) -> Model:
    m = kutu_agi(8.0 * s, 2.0 * s, 2.0 * s, 4, 1, 1, celik(rho), name="degismez")
    sabitle(m)
    if R is not None:
        for n in m.nodes:
            n.x, n.y, n.z = (R @ n.xyz).tolist()
    return m


def test_degismez_yogunluk():
    f1 = modal(degismez_kutu(), 6).f
    f4 = modal(degismez_kutu(rho=4 * RHO), 6).f
    np.testing.assert_allclose(f4, f1 / 2, rtol=1e-9)


@pytest.mark.parametrize("s", [3.0, 0.25])
def test_degismez_olcek(s):
    f1 = modal(degismez_kutu(), 6).f
    fs = modal(degismez_kutu(s=s), 6).f
    np.testing.assert_allclose(fs, f1 / s, rtol=1e-9)


@pytest.mark.parametrize("tohum", [1, 7])
def test_degismez_dondurme(tohum):
    rng = np.random.default_rng(tohum)
    Q, Rm = np.linalg.qr(rng.normal(size=(3, 3)))
    Q = Q * np.sign(np.diag(Rm))
    if np.linalg.det(Q) < 0:
        Q[:, 0] = -Q[:, 0]
    f1 = modal(degismez_kutu(), 6).f
    m = degismez_kutu(R=Q)
    r = modal(m, 6)
    np.testing.assert_allclose(r.f, f1, rtol=1e-9)
    dogrula(m, r)


# --- K9: konsol kiriş -------------------------------------------------------------------------------

KL, KB, KH = 100.0, 10.0, 10.0
I_KESIT = KB * KH**3 / 12.0
A_KESIT = KB * KH


def euler_bernoulli(betaL: float) -> float:
    return betaL**2 / (2 * np.pi * KL**2) * math.sqrt(E * I_KESIT / (RHO * A_KESIT))


F1_EB = euler_bernoulli(1.875104)  # ≈ 835.52 Hz
F_AX = math.sqrt(E / RHO) / (4 * KL)  # ≈ 12930 Hz


def test_konsol_referans_degerleri():
    """Teori tablosundaki kapalı formül değerleri (testin kendi aritmetiği)."""
    assert F1_EB == pytest.approx(835.52, abs=0.01)
    assert euler_bernoulli(4.694091) == pytest.approx(5236.1, abs=0.1)
    assert F_AX == pytest.approx(12930, abs=1)


@functools.cache
def konsol(k: int) -> Model:
    m = kutu_agi(KL, KB, KH, 10 * k, k, k, celik(), name=f"konsol_{k}")
    sabitle(m)
    return m


@functools.cache
def konsol_modal(k: int, lumped: bool = False) -> ModalResult:
    return modal(konsol(k), 8, lumped=lumped)


SLOW = pytest.mark.slow
K_LISTESI = [2, 4, pytest.param(8, marks=SLOW)]


@pytest.mark.parametrize("k", K_LISTESI)
def test_konsol_rayleigh_alt_sinir(k):
    """Her k'da f₁ ≥ 0.99 · f₁,EB (tutarlı kütle Rayleigh–Ritz üst sınırı)."""
    assert konsol_modal(k).f[0] >= 0.99 * F1_EB


@pytest.mark.parametrize("k1, k2", [(2, 4), pytest.param(4, 8, marks=SLOW)])
def test_konsol_inceltmede_azalir(k1, k2):
    kaba, ince = konsol_modal(k1), konsol_modal(k2)
    assert ince.f[0] < kaba.f[0]
    assert ince.f[1] < kaba.f[1]


@pytest.mark.parametrize("k1, k2", [(2, 4), pytest.param(4, 8, marks=SLOW)])
def test_konsol_yakinsama_hizi(k1, k2):
    """e_k = f₁/f₁,EB − 1: e_2 / e_4 ≥ 2.5 ve e_4 / e_8 ≥ 2.5."""
    e = {k: konsol_modal(k).f[0] / F1_EB - 1 for k in (k1, k2)}
    assert e[k1] / e[k2] >= 2.5


@SLOW
def test_konsol_k8_yakinsama_degeri():
    r = konsol_modal(8)
    assert r.f[0] / F1_EB <= 1.04
    assert r.f[1] / F1_EB <= 1.06


def test_konsol_eksenel_mod():
    """k = 4: ilk 8 mod içinde x etkin kütlesi en büyük mod eksenel moddur, |f/f_ax − 1| ≤ 0.01."""
    m, r = konsol(4), konsol_modal(4)
    me = effective_mass(m, r)
    i = int(np.argmax(me[:, 0]))
    assert abs(r.f[i] / F_AX - 1) <= 0.01


def test_konsol_egilme_etkin_kutle():
    """k = 4: ilk iki modun y etkin kütleleri toplamı / ρV = 0.6131 ± 0.005."""
    m, r = konsol(4), konsol_modal(4)
    me = effective_mass(m, r)
    rhoV = RHO * KL * KB * KH
    assert model_mass(m) == pytest.approx(rhoV, rel=1e-12)
    assert abs(me[:2, 1].sum() / rhoV - 0.6131) <= 0.005


@pytest.mark.parametrize("k", K_LISTESI)
def test_konsol_toplanmis_tutarlinin_altinda(k):
    assert konsol_modal(k, lumped=True).f[0] <= konsol_modal(k).f[0]


@pytest.mark.parametrize("k", [2, 4])
def test_konsol_diklik(k):
    dogrula(konsol(k), konsol_modal(k))


def test_konsol_mode_erisimi():
    """ModalResult.mode(model, i, düğüm, dof) = modes[dof_index, i]; uç düğümde birinci mod sıfır değil."""
    m, r = konsol(2), konsol_modal(2)
    uc = max(m.nodes, key=lambda n: (n.x, n.y, n.z)).id
    for i in range(3):
        for dof in ("ux", "uy", "uz"):
            assert r.mode(m, i, uc, dof) == r.modes[m.dof_index(uc, dof), i]
    assert r.mode(m, 0, uc) == r.modes[m.dof_index(uc, "ux"), 0]  # varsayılan dof = "ux"
    assert math.hypot(r.mode(m, 0, uc, "uy"), r.mode(m, 0, uc, "uz")) > 0.0
