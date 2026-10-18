"""SPEC 68b K2–K6, K9 (geçici ısıl kısmı), K10: θ-yöntemiyle geçici ısı iletimi.

Testler yalnız SPEC metninden ve arayüzden yazıldı; uygulama kodu okunmadı.

Birimler: ρcp mJ/(mm³·K), k mW/(mm·K), h mW/(mm²·K), zaman s, enerji mJ.

Testlerin metnin biçim vermediği yerlerde seçtiği varsayımlar:
- `kaydet=None` → her adım kaydedilir: `t = [0, Δt, 2Δt, …, t_end]`, `T[0]` başlangıç alanıdır.
  Testlerde `t_end` her zaman `Δt`'nin tam katıdır.
- K2 "ortalama T": kapasite ağırlıklı ortalama `Σ m_i T_i / Σ m_i`, `m_i = Σ_e ρcp V_e / 4`.
- K2 yakınsama oranı: hata, aynı ağın çok küçük adımlı (θ=1/2, Δt=τ/1600) çözümüne göre ölçülür; analitik
  topaklı çözümle ağ arasındaki küçük Bi farkı (≈1e-5) oranı bozmasın diye.
- K4: `1ᵀC` tutarlı ve topaklı kapasitede aynıdır (satır toplamları eşit), bu yüzden depolanan enerji
  `U_n = Σ m_i T_i`; denge `U_n − U_0 = E_in[n]` (E_in parçaya giren birikimli net ısı, tutulu düğüm
  tepkileri dahil) olarak sınanır.
- K6: tek düğümlü ODE, çok düğümlü ağ için cebirsel olarak tam değildir (yüzey/kapasite oranı düğümden
  düğüme değişir). Bu yüzden "elde adım adım" çözüm, SPEC 56 matrisleriyle (Σ ke, Hh, fh) ve tet4.ct ile
  test içinde kurulan aynı θ özyinelemesidir (abs 1e-9). Tek düğümlü ODE ayrıca gevşek toleransla
  (0.05 °C) karşılaştırılır.
- K5: kararlı çözüm SPEC 56 K3'ün kapalı formülüdür (tet4 doğrusal alanı tam üretir).
"""

from __future__ import annotations

import ast
import functools
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from core.elements import tet4
from core.isil import Convection, HeatFlux, Temperature, conductivity_matrix
from core.isil_gecici import TransientResult, solve_transient
from core.model import Material, Model, ModelError
from tests.benchmarks.tet_ag import kutu_agi, sinir_ucgenleri, yuz_dugumleri

# ---------------------------------------------------------------- malzemeler ve ağlar

# Alüminyum küp (K2): k = 200, ρ = 2.7e-9, cp = 9.0e8, h = 0.01 → τ = 405 s, Bi = 8e-5
K_AL = 200.0
RHO_CP_AL = 2.7e-9 * 9.0e8
H_HAVA = 0.01
TAU = RHO_CP_AL * 1000.0 / (H_HAVA * 600.0)

# Çelik (K3, K5): k = 50, ρ = 7.85e-9, cp = 4.6e8 → a = 13.85 mm²/s
K_CELIK = 50.0
RHO_CP_CELIK = 7.85e-9 * 4.6e8
A_CELIK = K_CELIK / RHO_CP_CELIK


def kup() -> Model:
    """10 mm küp, 2×2×2 Kuhn ağı."""
    return kutu_agi(10.0, 10.0, 10.0, 2, 2, 2, Material("al", 70_000.0, 0.33))


def cubuk() -> Model:
    """100 × 5 × 5 çelik çubuk, x yönünde 1 mm."""
    return kutu_agi(100.0, 5.0, 5.0, 100, 1, 1, Material("celik", 210_000.0, 0.3))


def tum_yuzler(model: Model, L: tuple[float, float, float]) -> np.ndarray:
    ucgenler = []
    for eksen in range(3):
        for deger in (0.0, L[eksen]):
            ucgenler += sinir_ucgenleri(model, eksen, deger)
    return np.array(ucgenler, dtype=int)


def kapasite_agirliklari(model: Model, rho_cp: float) -> np.ndarray:
    """m_i = Σ_e ρcp V_e / 4, model.nodes sırasında (1ᵀC'nin bileşenleri)."""
    m = np.zeros(len(model.nodes))
    for e in model.elements:
        V = tet4.volume(e, model)
        for nid in e.nodes:
            m[model.node_index(nid)] += rho_cp * V / 4.0
    return m


def ortalama_T(model: Model, rho_cp: float, T: np.ndarray) -> float:
    m = kapasite_agirliklari(model, rho_cp)
    return float(m @ T / m.sum())


def zamanlar_tam(res: TransientResult, t_end: float, dt: float) -> None:
    """Varsayım: kaydet=None → her adım kaydedilir."""
    n = round(t_end / dt)
    assert res.t.shape == (n + 1,)
    assert res.T.shape[0] == n + 1
    assert res.t[0] == 0.0
    assert res.t[-1] == pytest.approx(t_end, rel=1e-12)
    np.testing.assert_allclose(np.diff(res.t), dt, rtol=1e-9)


def enerji_dengesi(model: Model, rho_cp: float, res: TransientResult) -> None:
    """K4: her adımda U_n − U_0 = E_in[n] (göreli 1e-10)."""
    m = kapasite_agirliklari(model, rho_cp)
    U = res.T @ m
    dU = U - U[0]
    olcek = max(np.abs(dU).max(), np.abs(res.E_in).max())
    assert olcek > 0
    assert res.E_in.shape == res.t.shape
    np.testing.assert_allclose(dU, res.E_in, rtol=0, atol=1e-10 * olcek)


def kup_sogumasi(theta: float, dt: float, lumped: bool = False) -> tuple[Model, TransientResult]:
    model = kup()
    conv = [Convection(tum_yuzler(model, (10.0, 10.0, 10.0)), H_HAVA, 20.0)]
    res = solve_transient(
        model, K_AL, RHO_CP_AL, T0=200.0, t_end=TAU, dt=dt, theta=theta, lumped=lumped, convection=conv
    )
    return model, res


def kup_tau_ortalamasi(theta: float, dt: float) -> float:
    model, res = kup_sogumasi(theta, dt)
    assert res.t[-1] == pytest.approx(TAU, rel=1e-12)
    return ortalama_T(model, RHO_CP_AL, res.T[-1])


# ---------------------------------------------------------------- K2 topaklı soğuma


def test_tau_ve_biot_on_kosul():
    assert TAU == pytest.approx(405.0, rel=1e-12)
    assert H_HAVA * (1000.0 / 600.0) / K_AL == pytest.approx(8.333e-5, rel=1e-3)


def test_sonuc_bicimi():
    model, res = kup_sogumasi(1.0, TAU / 100)
    zamanlar_tam(res, TAU, TAU / 100)
    assert res.T.shape == (101, len(model.nodes))
    np.testing.assert_array_equal(res.node_ids, [n.id for n in model.nodes])
    np.testing.assert_allclose(res.T[0], 200.0, rtol=0, atol=0)


def test_topakli_soguma_geri_euler():
    T = kup_tau_ortalamasi(1.0, TAU / 100)
    assert T == pytest.approx(20.0 + 180.0 / math.e, rel=5e-3)


def test_topakli_soguma_crank_nicolson():
    T = kup_tau_ortalamasi(0.5, TAU / 50)
    assert T == pytest.approx(20.0 + 180.0 / math.e, rel=1e-3)


@functools.cache
def referans_tau() -> float:
    """Aynı ağın çok küçük adımlı (θ = 1/2, Δt = τ/1600) çözümü (fixture değil: kurulum hatası olmasın)."""
    return kup_tau_ortalamasi(0.5, TAU / 1600)


def test_yakinsama_orani_geri_euler():
    e1 = abs(kup_tau_ortalamasi(1.0, TAU / 100) - referans_tau())
    e2 = abs(kup_tau_ortalamasi(1.0, TAU / 200) - referans_tau())
    assert 1.8 <= e1 / e2 <= 2.2


def test_yakinsama_orani_crank_nicolson():
    e1 = abs(kup_tau_ortalamasi(0.5, TAU / 50) - referans_tau())
    e2 = abs(kup_tau_ortalamasi(0.5, TAU / 100) - referans_tau())
    assert 3.5 <= e1 / e2 <= 4.5


def test_topakli_kapasite_ile_de_yakin():
    model, res = kup_sogumasi(1.0, TAU / 100, lumped=True)
    T = ortalama_T(model, RHO_CP_AL, res.T[-1])
    assert T == pytest.approx(20.0 + 180.0 / math.e, rel=5e-3)


# ---------------------------------------------------------------- K3 yarı sonsuz cisim

T_S, T_0 = 100.0, 20.0


def yari_sonsuz(theta: float, lumped: bool, dt: float = 0.05, t_end: float = 20.0):
    model = cubuk()
    sicak = [Temperature(n, T_S) for n in yuz_dugumleri(model, 0, 0.0)]
    res = solve_transient(
        model,
        K_CELIK,
        RHO_CP_CELIK,
        T0=T_0,
        t_end=t_end,
        dt=dt,
        theta=theta,
        lumped=lumped,
        temperatures=sicak,
    )
    return model, res


@functools.cache
def yari_sonsuz_topakli():
    return yari_sonsuz(1.0, True)


def test_yari_sonsuz_erf():
    model, res = yari_sonsuz_topakli()
    zamanlar_tam(res, 20.0, 0.05)
    t = 20.0
    x = np.array([n.x for n in model.nodes])
    T_erf = np.array([T_S + (T_0 - T_S) * math.erf(xi / (2.0 * math.sqrt(A_CELIK * t))) for xi in x])
    secim = x <= 50.0 + 1e-9
    hata = np.abs(res.T[-1][secim] - T_erf[secim])
    assert hata.max() <= 0.02 * 80.0


def test_yari_sonsuz_maksimum_ilkesi():
    _, res = yari_sonsuz_topakli()
    assert res.T.min() >= T_0 - 1e-9
    assert res.T.max() <= T_S + 1e-9


def test_yari_sonsuz_sicak_yuz_tutulur():
    model, res = yari_sonsuz_topakli()
    sicak = [model.node_index(n) for n in yuz_dugumleri(model, 0, 0.0)]
    np.testing.assert_allclose(res.T[1:, sicak], T_S, rtol=0, atol=1e-12)


def test_uyari_tutarli_crank_nicolson_maksimum_ilkesini_bozabilir():
    """UYARI (SPEC K3): tutarlı kapasite + θ = 1/2, süreksiz başlangıçta salınım yapabilir; [20, 100] dışına
    çıkmak burada hata sayılmaz. Yalnız sonucun sonlu ve enerji dengesinin tutarlı olduğu sınanır."""
    model, res = yari_sonsuz(0.5, False)
    assert np.all(np.isfinite(res.T))
    enerji_dengesi(model, RHO_CP_CELIK, res)


# ---------------------------------------------------------------- K4 enerji dengesi


@pytest.mark.parametrize(
    ("theta", "bolum", "lumped"), [(1.0, 100, False), (0.5, 50, False), (1.0, 100, True)]
)
def test_enerji_dengesi_kup(theta, bolum, lumped):
    model, res = kup_sogumasi(theta, TAU / bolum, lumped=lumped)
    enerji_dengesi(model, RHO_CP_AL, res)
    assert res.E_in[0] == 0.0
    assert res.E_in[-1] < 0.0  # soğuma: net ısı çıkışı


def test_enerji_dengesi_yari_sonsuz():
    model, res = yari_sonsuz_topakli()
    enerji_dengesi(model, RHO_CP_CELIK, res)
    assert res.E_in[-1] > 0.0  # ısınma: tutulu yüzden giriş


# ---------------------------------------------------------------- K5 uzun zaman


def test_uzun_zaman_kararli_cozume_gider():
    L = 100.0
    model = kutu_agi(L, 50.0, 50.0, 4, 2, 2, Material("celik", 210_000.0, 0.3))
    T1, T2 = 100.0, 20.0
    tutulu = [Temperature(n, T1) for n in yuz_dugumleri(model, 0, 0.0)]
    tutulu += [Temperature(n, T2) for n in yuz_dugumleri(model, 0, L)]
    t_end = 20.0 * L**2 / A_CELIK
    res = solve_transient(
        model, K_CELIK, RHO_CP_CELIK, T0=20.0, t_end=t_end, dt=t_end / 100, temperatures=tutulu
    )
    x = np.array([n.x for n in model.nodes])
    np.testing.assert_allclose(res.T[-1], T1 + (T2 - T1) * x / L, rtol=0, atol=1e-6)


# ---------------------------------------------------------------- K6 zaman fonksiyonu


def rampa(t: float) -> float:
    """T∞(t) çarpanı: 0 → 1, 0–100 s; sonra 1."""
    return min(t / 100.0, 1.0)


def ucgen_alani(model: Model, tri) -> float:
    a, b, c = (model.node(n).xyz for n in tri)
    return 0.5 * float(np.linalg.norm(np.cross(b - a, c - a)))


def el_ile_theta(model, k, rho_cp, T0, t_end, dt, theta, lumped, fluxes, convection, zaman) -> np.ndarray:
    """SPEC 56 matrisleri ve tet4.ct ile aynı θ özyinelemesi, yoğun numpy (test içi el hesabı).

    K = Σ ke + Σ Hh, F(t) = Σ f_r(t)·(fq ya da fh); kayıt sırası fluxes + convection (temperatures yok).
    """
    n = len(model.nodes)
    idx = model.node_index
    K = conductivity_matrix(model, k).toarray()
    C = np.zeros((n, n))
    for e in model.elements:
        ii = [idx(nid) for nid in e.nodes]
        C[np.ix_(ii, ii)] += tet4.ct(e, model, rho_cp, lumped=lumped)
    yukler = []  # (çarpan fonksiyonu, yük vektörü)
    kayitlar = list(fluxes) + list(convection)
    for r, kayit in enumerate(kayitlar):
        f = np.zeros(n)
        for tri in np.asarray(kayit.tris):
            A = ucgen_alani(model, tri)
            ii = [idx(int(nid)) for nid in tri]
            if isinstance(kayit, HeatFlux):
                f[ii] += kayit.q * A / 3.0
            else:
                K[np.ix_(ii, ii)] += kayit.h * A / 12.0 * (np.ones((3, 3)) + np.eye(3))
                f[ii] += kayit.h * kayit.T_inf * A / 3.0
        carpan = (zaman or {}).get(r, lambda t: 1.0)
        yukler.append((carpan, f))

    def F(t: float) -> np.ndarray:
        return sum(c(t) * f for c, f in yukler)

    sol = C / dt + theta * K
    sag = C / dt - (1.0 - theta) * K
    T = np.full(n, T0)
    gecmis = [T.copy()]
    for s in range(round(t_end / dt)):
        t0, t1 = s * dt, (s + 1) * dt
        T = np.linalg.solve(sol, sag @ T + theta * F(t1) + (1.0 - theta) * F(t0))
        gecmis.append(T.copy())
    return np.array(gecmis)


@pytest.mark.parametrize("theta", [1.0, 0.5])
def test_zaman_fonksiyonu_tasinim_rampasi(theta):
    model = kup()
    conv = [Convection(tum_yuzler(model, (10.0, 10.0, 10.0)), H_HAVA, 100.0)]
    dt, t_end = 5.0, 150.0
    res = solve_transient(
        model,
        K_AL,
        RHO_CP_AL,
        T0=0.0,
        t_end=t_end,
        dt=dt,
        theta=theta,
        lumped=True,
        convection=conv,
        zaman={0: rampa},
    )
    zamanlar_tam(res, t_end, dt)
    el = el_ile_theta(model, K_AL, RHO_CP_AL, 0.0, t_end, dt, theta, True, [], conv, {0: rampa})
    np.testing.assert_allclose(res.T, el, rtol=0, atol=1e-9)
    enerji_dengesi(model, RHO_CP_AL, res)


@pytest.mark.parametrize("theta", [1.0, 0.5])
def test_zaman_fonksiyonu_tek_dugum_odesine_yakin(theta):
    """Topaklı küp ≈ tek düğüm: C_top Ṫ = hA (T∞(t) − T), aynı θ ve Δt.

    Gevşek tolerans: varsayım listesine bakın."""
    model = kup()
    conv = [Convection(tum_yuzler(model, (10.0, 10.0, 10.0)), H_HAVA, 100.0)]
    dt, t_end = 5.0, 150.0
    res = solve_transient(
        model,
        K_AL,
        RHO_CP_AL,
        T0=0.0,
        t_end=t_end,
        dt=dt,
        theta=theta,
        lumped=True,
        convection=conv,
        zaman={0: rampa},
    )
    C_top, hA = RHO_CP_AL * 1000.0, H_HAVA * 600.0
    T, tek = 0.0, [0.0]
    for s in range(round(t_end / dt)):
        t0, t1 = s * dt, (s + 1) * dt
        sag = (C_top / dt - (1 - theta) * hA) * T + hA * 100.0 * (theta * rampa(t1) + (1 - theta) * rampa(t0))
        T = sag / (C_top / dt + theta * hA)
        tek.append(T)
    ortalama = [ortalama_T(model, RHO_CP_AL, Ti) for Ti in res.T]
    np.testing.assert_allclose(ortalama, tek, rtol=0, atol=0.05)


def test_zaman_anahtari_sinir_kaydi_sirasi():
    """`zaman` anahtarı temperatures + fluxes + convection sırasındaki indekstir: burada 0 = akı (sabit),
    1 = taşınım (rampa)."""
    model = kup()
    ust = np.array(sinir_ucgenleri(model, 2, 10.0), dtype=int)
    aki = [HeatFlux(ust, 0.5)]
    conv = [Convection(tum_yuzler(model, (10.0, 10.0, 10.0)), H_HAVA, 100.0)]
    dt, t_end = 5.0, 150.0
    res = solve_transient(
        model,
        K_AL,
        RHO_CP_AL,
        T0=0.0,
        t_end=t_end,
        dt=dt,
        lumped=True,
        fluxes=aki,
        convection=conv,
        zaman={1: rampa},
    )
    el = el_ile_theta(model, K_AL, RHO_CP_AL, 0.0, t_end, dt, 1.0, True, aki, conv, {1: rampa})
    np.testing.assert_allclose(res.T, el, rtol=0, atol=1e-9)


def test_sabit_sicaklik_zaman_fonksiyonu():
    """T̄(t) = 100 · rampa(t): tutulu düğümler her kayıtlı anda bu değeri alır."""
    model = cubuk()
    sicak_id = yuz_dugumleri(model, 0, 0.0)
    sicak = [Temperature(n, 100.0) for n in sicak_id]
    zaman = {i: rampa for i in range(len(sicak))}
    res = solve_transient(
        model, K_CELIK, RHO_CP_CELIK, T0=0.0, t_end=50.0, dt=1.0, lumped=True, temperatures=sicak, zaman=zaman
    )
    ii = [model.node_index(n) for n in sicak_id]
    for s in range(1, len(res.t)):
        np.testing.assert_allclose(res.T[s, ii], 100.0 * rampa(res.t[s]), rtol=0, atol=1e-9)


# ---------------------------------------------------------------- kaydet ve TransientResult.at


def test_kaydet_istenen_zamanlar():
    model = kup()
    conv = [Convection(tum_yuzler(model, (10.0, 10.0, 10.0)), H_HAVA, 20.0)]
    tam = solve_transient(model, K_AL, RHO_CP_AL, T0=200.0, t_end=100.0, dt=5.0, convection=conv)
    secili = solve_transient(
        model, K_AL, RHO_CP_AL, T0=200.0, t_end=100.0, dt=5.0, convection=conv, kaydet=[0.0, 50.0, 100.0]
    )
    np.testing.assert_allclose(secili.t, [0.0, 50.0, 100.0], rtol=0, atol=1e-9)
    np.testing.assert_allclose(secili.T, tam.T[[0, 10, 20]], rtol=0, atol=1e-12)
    np.testing.assert_allclose(secili.E_in, tam.E_in[[0, 10, 20]], rtol=0, atol=1e-9)


def elle_sonuc() -> TransientResult:
    return TransientResult(
        t=np.array([0.0, 1.0, 3.0]),
        T=np.array([[0.0, 10.0], [2.0, 20.0], [6.0, 0.0]]),
        node_ids=np.array([1, 2]),
        E_in=np.array([0.0, 1.0, 2.0]),
    )


def test_at_dogrusal_aradegerleme():
    r = elle_sonuc()
    np.testing.assert_allclose(r.at(0.0), [0.0, 10.0], atol=1e-15)
    np.testing.assert_allclose(r.at(0.5), [1.0, 15.0], atol=1e-15)
    np.testing.assert_allclose(r.at(2.0), [4.0, 10.0], atol=1e-15)
    np.testing.assert_allclose(r.at(3.0), [6.0, 0.0], atol=1e-15)


@pytest.mark.parametrize("t", [-1e-6, 3.0001, 100.0, float("nan")])
def test_at_aralik_disi_hata(t):
    with pytest.raises(ModelError):
        elle_sonuc().at(t)


# ---------------------------------------------------------------- K9 hatalar


def kucuk_cagri(**kw):
    model = kup()
    conv = [Convection(tum_yuzler(model, (10.0, 10.0, 10.0)), H_HAVA, 20.0)]
    args = {"T0": 200.0, "t_end": 10.0, "dt": 1.0, "convection": conv} | kw
    return solve_transient(model, K_AL, args.pop("rho_cp", RHO_CP_AL), **args)


@pytest.mark.parametrize("dt", [0.0, -1.0, float("nan")])
def test_dt_gecersiz(dt):
    with pytest.raises(ModelError):
        kucuk_cagri(dt=dt)


def test_t_end_dt_den_kucuk():
    with pytest.raises(ModelError):
        kucuk_cagri(t_end=0.5, dt=1.0)


@pytest.mark.parametrize("theta", [0.3, 0.0, 0.49, 1.01, float("nan")])
def test_theta_kararlilik_bolgesi_disi(theta):
    with pytest.raises(ModelError):
        kucuk_cagri(theta=theta)


@pytest.mark.parametrize("theta", [0.5, 0.75, 1.0])
def test_theta_sinirlar_gecerli(theta):
    res = kucuk_cagri(theta=theta)
    assert np.all(np.isfinite(res.T))


@pytest.mark.parametrize("rho_cp", [0.0, -1.0])
def test_rho_cp_gecersiz(rho_cp):
    with pytest.raises(ModelError):
        kucuk_cagri(rho_cp=rho_cp)


def test_rho_cp_malzeme_adina_gore():
    a = kucuk_cagri(rho_cp=RHO_CP_AL)
    b = kucuk_cagri(rho_cp={"al": RHO_CP_AL})
    np.testing.assert_allclose(a.T, b.T, rtol=1e-12, atol=0)


def test_rho_cp_eksik_malzeme():
    with pytest.raises(ModelError):
        kucuk_cagri(rho_cp={"celik": RHO_CP_CELIK})


# ---------------------------------------------------------------- K10 bağımlılık


def test_isil_gecici_ithalatlari():
    """core/isil_gecici.py yalnız numpy, scipy, math (ve standart kütüphane) ile core'u içe aktarır."""
    kaynak = Path(__file__).resolve().parents[2] / "core" / "isil_gecici.py"
    agac = ast.parse(kaynak.read_text(encoding="utf-8"))
    izinli = {"numpy", "scipy", "math", "core", "__future__"}
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            adlar = [a.name for a in dugum.names]
        elif isinstance(dugum, ast.ImportFrom) and dugum.level == 0:
            adlar = [dugum.module or ""]
        else:
            continue
        for ad in adlar:
            kok = ad.split(".")[0]
            assert kok in izinli or kok in sys.stdlib_module_names, f"izinsiz içe aktarma: {ad}"
