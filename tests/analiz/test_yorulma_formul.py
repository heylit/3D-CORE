"""SPEC 68d K1, K2, K3, K8 (malzeme/Marin kısmı), K9 — saf formüller (OCCT ve FEM yok).

Testler yalnız specs/68d-yorulma.md metninden ve analiz/yorulma.py arayüzünden yazıldı;
fonksiyon gövdeleri okunmadı.
Beklenen değerler SPEC'in sayısal örneğinden ve kapalı formlardan (Shigley 10. baskı, bölüm 6).
Uydurma malzeme.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
import pytest

from analiz.yorulma import MARIN_VARSAYILAN, YUZEYLER, Marin, dayanim_siniri, goodman, omur
from tests.analiz.yorulma_ref import (
    F_SN,
    HATALAR,
    KA_AB,
    KC,
    KE,
    RM,
    N_kapali,
    aluminyum,
    celik,
    ka,
    kb,
    nf_kapali,
    se_ussu,
)

# SPEC sayısal örneği: Rm = 600, talaşlı işlenmiş, d = 20, eğme, %99 güvenilirlik
ORNEK = Marin(yuzey="islenmis", d=20.0, yuk="egme", guvenilirlik=99)
SE_ORNEK = 181.938


def _carpim(k: dict[str, float]) -> float:
    return k["ka"] * k["kb"] * k["kc"] * k["kd"] * k["ke"]


# ------------------------------------------------------------------ K1 Marin


def test_k1_sayisal_ornek():
    k = ORNEK.katsayilar(RM)
    assert set(k) == {"ka", "kb", "kc", "kd", "ke"}
    assert k["ka"] == pytest.approx(0.827878, rel=1e-5)
    assert k["kb"] == pytest.approx(0.899936, rel=1e-5)
    assert k["kc"] == pytest.approx(1.0, rel=1e-12)
    assert k["kd"] == pytest.approx(1.0, rel=1e-12)
    assert k["ke"] == pytest.approx(0.814, rel=1e-12)
    Se = dayanim_siniri(celik(), ORNEK)
    assert Se == pytest.approx(SE_ORNEK, rel=1e-5)
    assert Se == pytest.approx(_carpim(k) * 0.5 * RM, rel=1e-12)


def test_k1_yuzeyler():
    assert YUZEYLER == ("taslanmis", "islenmis", "sicak_haddelenmis", "dovme")
    for yuzey, (a, b) in KA_AB.items():
        for Rm in (400.0, 600.0, 1100.0):
            assert Marin(yuzey=yuzey).katsayilar(Rm)["ka"] == pytest.approx(a * Rm**b, rel=1e-12), yuzey


@pytest.mark.parametrize("d", [2.79, 10.0, 20.0, 51.0, 51.5, 100.0, 254.0])
def test_k1_boyut(d):
    assert Marin(d=d).katsayilar(RM)["kb"] == pytest.approx(kb(d), rel=1e-12)


def test_k1_boyut_yok_kb_1():
    assert Marin().katsayilar(RM)["kb"] == 1.0
    assert Marin(d=None).katsayilar(RM)["kb"] == 1.0


@pytest.mark.parametrize("yuk,kc", list(KC.items()))
def test_k1_yuk_tipi(yuk, kc):
    assert Marin(yuk=yuk).katsayilar(RM)["kc"] == pytest.approx(kc, rel=1e-12)


@pytest.mark.parametrize("g,ke", list(KE.items()))
def test_k1_guvenilirlik(g, ke):
    assert Marin(guvenilirlik=g).katsayilar(RM)["ke"] == pytest.approx(ke, rel=1e-12)


def test_k1_sicaklik():
    assert Marin(kd=0.9).katsayilar(RM)["kd"] == pytest.approx(0.9, rel=1e-12)
    a = dayanim_siniri(celik(), Marin(kd=0.9))
    b = dayanim_siniri(celik(), Marin())
    assert a == pytest.approx(0.9 * b, rel=1e-12)


def test_k1_varsayilan():
    m = MARIN_VARSAYILAN
    assert (m.yuzey, m.d, m.yuk, m.kd, m.guvenilirlik) == ("islenmis", None, "birlesik", 1.0, 50)
    k = m.katsayilar(RM)
    assert k["kb"] == 1.0 and k["kc"] == 1.0 and k["kd"] == 1.0 and k["ke"] == 1.0
    assert k["ka"] == pytest.approx(ka("islenmis", RM), rel=1e-12)


@pytest.mark.parametrize("d", [300.0, 254.5, 2.0, 0.0, -5.0, math.nan])
def test_k1_boyut_aralik_disi(d):
    with pytest.raises(HATALAR):
        Marin(d=d).katsayilar(RM)


def test_k1_bilinmeyen_yuzey():
    with pytest.raises(HATALAR):
        Marin(yuzey="kumlu").katsayilar(RM)


# ------------------------------------------------------------------ K2 Se'


def test_k2_sigma_f_kullanilir():
    m = Marin()
    k = m.katsayilar(RM)
    assert dayanim_siniri(celik(sigma_f=275.0), m) == pytest.approx(_carpim(k) * 275.0, rel=1e-12)
    # sigma_f, Rm kuralından önce gelir
    assert dayanim_siniri(celik(sigma_f=275.0), m) != pytest.approx(dayanim_siniri(celik(), m), rel=1e-6)


@pytest.mark.parametrize("Rm", [400.0, 1000.0, 1400.0, 1600.0, 2000.0])
@pytest.mark.parametrize("grup", ["celik", "paslanmaz"])
def test_k2_celik_kurali(Rm, grup):
    m = Marin()
    k = m.katsayilar(Rm)
    assert dayanim_siniri(celik(Rm=Rm, grup=grup), m) == pytest.approx(_carpim(k) * se_ussu(Rm), rel=1e-12)


def test_k2_rm_1600_700():
    m = Marin(yuzey="taslanmis")
    assert dayanim_siniri(celik(Rm=1600.0), m) / _carpim(m.katsayilar(1600.0)) == pytest.approx(
        700.0, rel=1e-12
    )


def test_k2_aluminyum_sigma_f_yok():
    with pytest.raises(HATALAR, match="dayanım sınırı"):
        dayanim_siniri(aluminyum(), Marin())


def test_k2_aluminyum_sigma_f_var():
    m = Marin()
    k = m.katsayilar(290.0)
    assert dayanim_siniri(aluminyum(sigma_f=96.0), m) == pytest.approx(_carpim(k) * 96.0, rel=1e-12)


# ------------------------------------------------------------------ K3 Goodman ve ömür


def test_k3_sayisal_ornek():
    Se = dayanim_siniri(celik(), ORNEK)
    nf = np.asarray(goodman(150.0, 200.0, Se, RM), dtype=float)
    assert float(nf) == pytest.approx(0.863715, rel=1e-4)
    assert float(nf) == pytest.approx(nf_kapali(150.0, 200.0, Se, RM), rel=1e-12)
    # σar = 150/(1 − 200/600) = 225; a = 1602.74, b = −0.157490
    a = (F_SN * RM) ** 2 / Se
    b = -(1 / 3) * math.log10(F_SN * RM / Se)
    assert a == pytest.approx(1602.74, rel=1e-5)
    assert b == pytest.approx(-0.157490, rel=1e-5)
    N = float(np.asarray(omur(150.0, 200.0, Se, RM), dtype=float))
    assert N == pytest.approx(2.5953e5, rel=1e-4)
    assert N == pytest.approx((225.0 / a) ** (1 / b), rel=1e-10)


def test_k3_dogrunun_uclari():
    Se = dayanim_siniri(celik(), ORNEK)
    # σar = Se'de N = 1e6, σar = 0.9 Rm'de N = 1e3. Sınırların hemen içinden (σar ≤ Se → inf kuralı ile
    # σar ≥ f Rm düşük çevrim kuralı uçları kendine alır), göreli 1e-12 kaydırma N'yi < 1e-10 değiştirir.
    N6 = float(np.asarray(omur(Se * (1 + 1e-12), 0.0, Se, RM), dtype=float))
    N3 = float(np.asarray(omur(0.9 * RM * (1 - 1e-12), 0.0, Se, RM), dtype=float))
    assert N6 == pytest.approx(1e6, rel=1e-10)
    assert N3 == pytest.approx(1e3, rel=1e-10)


def test_k3_sonsuz_omur():
    Se = dayanim_siniri(celik(), ORNEK)
    for sa in (0.5 * Se, 0.999 * Se, Se):
        assert np.isinf(np.asarray(omur(sa, 0.0, Se, RM), dtype=float))
    # ortalamalı: σar = σa/(1 − σm/Rm) < Se
    assert np.isinf(np.asarray(omur(100.0, 100.0, Se, RM), dtype=float))


def test_k3_f_parametresi():
    Se = dayanim_siniri(celik(), ORNEK)
    N = float(np.asarray(omur(300.0, 0.0, Se, RM, f=0.8), dtype=float))
    assert N == pytest.approx(N_kapali(300.0, 0.0, Se, RM, f=0.8), rel=1e-10)


def test_k3_basma_ortalamasi():
    Se = dayanim_siniri(celik(), ORNEK)
    nf = float(np.asarray(goodman(150.0, -100.0, Se, RM), dtype=float))
    assert nf == pytest.approx(Se / 150.0, rel=1e-12)


def test_k3_genlik_sifir():
    Se = dayanim_siniri(celik(), ORNEK)
    assert np.isinf(np.asarray(goodman(0.0, 200.0, Se, RM), dtype=float))
    assert np.isinf(np.asarray(goodman(0.0, 0.0, Se, RM), dtype=float))
    assert np.isinf(np.asarray(omur(0.0, 200.0, Se, RM), dtype=float))


def test_k3_vektorel():
    Se = 200.0
    sa = np.array([0.0, 100.0, 150.0, 150.0, 300.0])
    sm = np.array([0.0, 0.0, 200.0, -100.0, 50.0])
    nf = np.asarray(goodman(sa, sm, Se, RM), dtype=float)
    N = np.asarray(omur(sa, sm, Se, RM), dtype=float)
    assert nf.shape == sa.shape and N.shape == sa.shape
    for i in range(sa.size):
        assert nf[i] == pytest.approx(nf_kapali(sa[i], sm[i], Se, RM), rel=1e-12)
        if sm[i] >= 0:
            assert N[i] == pytest.approx(N_kapali(sa[i], sm[i], Se, RM), rel=1e-10)
    assert not np.any(np.isnan(N))


def test_k3_dusuk_cevrim_nan_degil():
    # σar ≥ f Rm: kapsam dışı ama sessiz nan yok; 0 < N ≤ 1e3 (K6 kırpması)
    Se = dayanim_siniri(celik(), ORNEK)
    N = np.asarray(omur(np.array([560.0, 600.0, 900.0]), 0.0, Se, RM), dtype=float)
    assert not np.any(np.isnan(N))
    assert np.all(N > 0) and np.all(N <= 1e3 * (1 + 1e-12))


# ------------------------------------------------------------------ K8 hatalar (malzeme, Marin)


def test_k8_rm_eksik():
    with pytest.raises(HATALAR):
        dayanim_siniri(celik(Rm=None), Marin())


@pytest.mark.parametrize("g", [95, 0, 100, 99.99])
def test_k8_guvenilirlik(g):
    with pytest.raises(HATALAR):
        Marin(guvenilirlik=g).katsayilar(RM)


def test_k8_gecersiz_yuk_tipi():
    with pytest.raises(HATALAR):
        Marin(yuk="kesme").katsayilar(RM)


# ------------------------------------------------------------------ K9 bağımlılık


def test_k9_yeni_bagimlilik_yok():
    kaynak = Path(__file__).resolve().parents[2] / "analiz" / "yorulma.py"
    agac = ast.parse(kaynak.read_text(encoding="utf-8"))
    kokler: set[str] = set()
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            kokler |= {a.name.split(".")[0] for a in dugum.names}
        elif isinstance(dugum, ast.ImportFrom) and dugum.level == 0 and dugum.module:
            kokler.add(dugum.module.split(".")[0])
    standart = {"__future__", "collections", "dataclasses", "typing", "math", "functools", "itertools"}
    proje = {"core", "malzeme", "analiz", "mesh", "geometry"}
    assert kokler <= standart | proje | {"numpy"}, kokler - standart - proje
