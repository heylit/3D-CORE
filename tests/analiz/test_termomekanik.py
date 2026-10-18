"""SPEC 68b K8, K9 (zincir kısmı): tek yönlü termo-mekanik zincir.

Testler yalnız SPEC metninden ve arayüzden yazıldı; uygulama kodu okunmadı.

K8 67b'ye (core.yukler.thermal_loads) bağlıdır; 67b birleşmeden "uygulanmamış" (NotImplementedError) düşer.

Varsayımlar (metin biçim vermiyor):
- `model_mek` mesnetlerini (`model.bcs`) taşır; zincir modele ısıl yükleri ekleyip statik çözer,
  modeli değiştirmez.
- `zamanlar=None` → TransientResult'ın bütün kayıtlı zamanları (`tm.t` = `sicaklik.t`).
- Kararlı `ThermalResult` tek zaman 0.0 sayılır; `zamanlar=[0.0]` ile `alanlar[0.0]` doldurulur.
- `alanlar[t] = (u, σ_vM)`: `u` düğüm başına (ux, uy, uz), `reshape(-1, 3)` ile `Result.u.reshape(-1, 3)`
  ile aynı sırada; `σ_vM` düğüm başına, `max(σ_vM) = sigma_vM_maks`.
- `u_maks` = düğüm yer değiştirme büyüklüğünün en büyüğü `max_i ‖u_i‖`.
- "Serbest çubuk" 3-2-1 mesnetlidir.
"""

from __future__ import annotations

import copy
import functools
import importlib.util

import numpy as np
import pytest

from analiz.termomekanik import TermoMekanik, zincir
from core.isil import Temperature, ThermalResult
from core.isil_gecici import TransientResult, solve_transient
from core.model import BC, Material, Model, ModelError
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri

E, NU, ALFA = 210_000.0, 0.3, 1.2e-5
K_CELIK = 50.0
RHO_CP_CELIK = 7.85e-9 * 4.6e8


def gerekli_67b() -> None:
    if importlib.util.find_spec("core.yukler") is None:
        raise NotImplementedError("SPEC 67b (core.yukler) birleşmeden çalışmaz")


def serbest(model: Model, L: float, b: float) -> Model:
    """3-2-1 mesnet: (0,0,0) tam, (L,0,0) uy uz, (0,b,0) uz."""

    def bul(x, y, z) -> int:
        return next(n.id for n in model.nodes if np.allclose(n.xyz, (x, y, z)))

    A, Bx, Cy = bul(0, 0, 0), bul(L, 0, 0), bul(0, b, 0)
    model.bcs = [BC(A, "ux"), BC(A, "uy"), BC(A, "uz"), BC(Bx, "uy"), BC(Bx, "uz"), BC(Cy, "uz")]
    return model


def cubuk() -> Model:
    return kutu_agi(100.0, 5.0, 5.0, 100, 1, 1, Material("celik", E, NU))


def kisa_cubuk() -> Model:
    return kutu_agi(20.0, 5.0, 5.0, 4, 1, 1, Material("celik", E, NU))


# ---------------------------------------------------------------- K8 geçici geçmiş


T_END, DT_UZUN = 14_440.0, 20.0  # ≈ 20·L²/a: alan düzgünleşir
KAYDET = [0.0, 20.0, 40.0, 100.0, 200.0, 400.0, 1000.0, 2000.0, 5000.0, T_END]


@functools.cache
def uzun_gecmis() -> tuple[TransientResult, TermoMekanik]:
    """Bir kez çözülür; testler önce `gerekli_67b()` çağırır (uygulanmamış, kurulum hatası değil)."""
    model = cubuk()
    sicak = [Temperature(n, 100.0) for n in yuz_dugumleri(model, 0, 0.0)]
    res = solve_transient(
        model,
        K_CELIK,
        RHO_CP_CELIK,
        T0=20.0,
        t_end=T_END,
        dt=DT_UZUN,
        lumped=True,
        temperatures=sicak,
        kaydet=KAYDET,
    )
    mek = serbest(cubuk(), 100.0, 5.0)
    tm = zincir(mek, res, 20.0, ALFA)
    return res, tm


def test_zincir_sonuc_bicimi():
    gerekli_67b()
    res, tm = uzun_gecmis()
    assert isinstance(tm, TermoMekanik)
    np.testing.assert_allclose(tm.t, res.t, rtol=0, atol=1e-9)
    assert tm.sigma_vM_maks.shape == tm.t.shape
    assert tm.u_maks.shape == tm.t.shape
    assert np.all(tm.sigma_vM_maks >= 0)


def test_uzun_zamanda_gerilmesiz():
    gerekli_67b()
    """t → ∞: alan düzgün (≈100 °C), serbest gövdede σ_vM_maks ≤ 1e-6·E α ΔT."""
    res, tm = uzun_gecmis()
    assert np.ptp(res.T[-1]) < 1e-6
    assert tm.sigma_vM_maks[-1] <= 1e-6 * E * ALFA * 80.0


def test_en_kotu_an_argmax():
    gerekli_67b()
    _, tm = uzun_gecmis()
    assert tm.en_kotu_an == tm.t[int(np.argmax(tm.sigma_vM_maks))]
    assert tm.sigma_vM_maks.max() > tm.sigma_vM_maks[-1]


def test_istenen_zaman_alani():
    gerekli_67b()
    model = cubuk()
    sicak = [Temperature(n, 100.0) for n in yuz_dugumleri(model, 0, 0.0)]
    res = solve_transient(
        model, K_CELIK, RHO_CP_CELIK, T0=20.0, t_end=20.0, dt=1.0, lumped=True, temperatures=sicak
    )
    tm = zincir(serbest(cubuk(), 100.0, 5.0), res, 20.0, ALFA, zamanlar=[20.0])
    assert 20.0 in tm.alanlar
    u, s = tm.alanlar[20.0]
    i = int(np.argmin(np.abs(tm.t - 20.0)))
    assert np.max(s) == pytest.approx(tm.sigma_vM_maks[i], rel=1e-12)
    assert np.linalg.norm(np.asarray(u).reshape(-1, 3), axis=1).max() == pytest.approx(
        tm.u_maks[i], rel=1e-12
    )


# ---------------------------------------------------------------- K8 kararlı sonuç = 67b doğrudan


def test_kararli_sonuc_67b_dogrudan_cozumle_ayni():
    gerekli_67b()
    from core.yukler import add_loads, thermal_loads

    isil = kisa_cubuk()
    ids = np.array([n.id for n in isil.nodes])
    T = np.array([20.0 + 0.8 * n.x + 0.3 * n.y * n.z for n in isil.nodes])  # doğrusal olmayan alan
    thr = ThermalResult(ids, T, np.zeros(len(ids)), 0.0, 0.0, 0.0)

    mek = serbest(kisa_cubuk(), 20.0, 5.0)
    dogrudan = copy.deepcopy(mek)
    add_loads(dogrudan, thermal_loads(dogrudan, thr, 20.0, ALFA))
    u_ref = solve(dogrudan).u.reshape(-1, 3)

    tm = zincir(mek, thr, 20.0, ALFA, zamanlar=[0.0])
    u = np.asarray(tm.alanlar[0.0][0]).reshape(-1, 3)
    olcek = np.abs(u_ref).max()
    assert olcek > 0
    np.testing.assert_allclose(u, u_ref, rtol=0, atol=1e-12 * olcek)
    assert tm.u_maks[0] == pytest.approx(np.linalg.norm(u_ref, axis=1).max(), rel=1e-12)
    assert mek.loads == []  # zincir modeli değiştirmez


# ---------------------------------------------------------------- K9 zincir hataları


def elle_gecmis(model: Model) -> TransientResult:
    ids = np.array([n.id for n in model.nodes])
    x = np.array([n.x for n in model.nodes])
    return TransientResult(
        t=np.array([0.0, 1.0]),
        T=np.vstack([np.full(len(ids), 20.0), 20.0 + 0.5 * x]),
        node_ids=ids,
        E_in=np.array([0.0, 1.0]),
    )


def test_ag_uyusmuyor_hata():
    kup = kutu_agi(10.0, 10.0, 10.0, 2, 2, 2, Material("celik", E, NU))
    with pytest.raises(ModelError):
        zincir(serbest(kisa_cubuk(), 20.0, 5.0), elle_gecmis(kup), 20.0, ALFA)


def test_ag_uyusmuyor_kararli_hata():
    kup = kutu_agi(10.0, 10.0, 10.0, 2, 2, 2, Material("celik", E, NU))
    ids = np.array([n.id for n in kup.nodes])
    thr = ThermalResult(ids, np.full(len(ids), 50.0), np.zeros(len(ids)), 0.0, 0.0, 0.0)
    with pytest.raises(ModelError):
        zincir(serbest(kisa_cubuk(), 20.0, 5.0), thr, 20.0, ALFA)


def test_alpha_eksik_malzeme_hata():
    mek = serbest(kisa_cubuk(), 20.0, 5.0)
    with pytest.raises(ModelError):
        zincir(mek, elle_gecmis(mek), 20.0, {"aluminyum": 2.3e-5})


def test_istenen_zaman_aralik_disi_hata():
    mek = serbest(kisa_cubuk(), 20.0, 5.0)
    with pytest.raises(ModelError):
        zincir(mek, elle_gecmis(mek), 20.0, ALFA, zamanlar=[2.0])
