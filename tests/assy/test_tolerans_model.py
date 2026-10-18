"""A1a — assy/model.py Distribution ve Tolerance testleri.

Testler yalnız onaylı A1 arayüz metninden yazıldı (arayuz/A1-eklem-tolerans-onerisi.md, bölüm 2); uygulama
kodu okunmadı. lower / upper nominale göre sapmadır; T = (upper − lower) / 2.
σ: NORMAL T / sigma_level, UNIFORM (düzgün) T / √3, TRIANGULAR (üçgen) T / √6.
"""

from __future__ import annotations

import dataclasses
import json
import math

import pytest

from assy.model import AssyError, Distribution, Tolerance

# ---------------------------------------------------------------- Distribution


def test_distribution_degerleri():
    """JSON'da kullanılan Türkçe değerler."""
    assert Distribution.NORMAL.value == "normal"
    assert Distribution.UNIFORM.value == "duzgun"
    assert Distribution.TRIANGULAR.value == "ucgen"
    assert {d.value for d in Distribution} == {"normal", "duzgun", "ucgen"}


# ---------------------------------------------------------------- varsayılanlar ve dönüşüm


def test_varsayilanlar():
    """Tolerance(nominal): sapma 0, NORMAL, sigma_level 3, ad boş."""
    t = Tolerance(10.0)
    assert t.lower == 0.0 and t.upper == 0.0
    assert t.distribution is Distribution.NORMAL
    assert t.sigma_level == 3.0
    assert t.name == ""
    assert t.mean == pytest.approx(10.0)
    assert t.half_width == 0.0
    assert t.sigma == 0.0


@pytest.mark.parametrize(
    ("deger", "beklenen"),
    [("normal", Distribution.NORMAL), ("duzgun", Distribution.UNIFORM), ("ucgen", Distribution.TRIANGULAR)],
)
def test_distribution_dizeden_cevrilir(deger, beklenen):
    t = Tolerance(5.0, -0.1, 0.1, deger)
    assert t.distribution is beklenen
    assert t == Tolerance(5.0, -0.1, 0.1, beklenen)


def test_bilinmeyen_dagilim_dizesi_hata():
    with pytest.raises((AssyError, ValueError)):
        Tolerance(5.0, -0.1, 0.1, "lognormal")


def test_dondurulmus():
    """frozen dataclass: alan atanamaz."""
    t = Tolerance(1.0, -0.1, 0.1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.nominal = 2.0  # type: ignore[misc]


# ---------------------------------------------------------------- mean, half_width, sigma


def test_h7_ornegi():
    """Ø20 H7 = 20 +0.021/0: ortalama 20.0105, T = 0.0105, σ = T / 3 = 0.0035."""
    t = Tolerance(20.0, 0.0, 0.021)
    assert t.mean == pytest.approx(20.0105, abs=1e-12)
    assert t.half_width == pytest.approx(0.0105, abs=1e-12)
    assert t.sigma == pytest.approx(0.0035, abs=1e-12)


def test_asimetrik_bant():
    """30 −0.2/+0.05: ortalama 30 + (−0.15)/2 = 29.925, T = 0.125."""
    t = Tolerance(30.0, -0.2, 0.05)
    assert t.mean == pytest.approx(29.925, abs=1e-12)
    assert t.half_width == pytest.approx(0.125, abs=1e-12)


def test_iki_sapma_ayni_tarafta():
    """Mil: 25 −0.040/−0.020 → ortalama 24.97, T = 0.01."""
    t = Tolerance(25.0, -0.040, -0.020)
    assert t.mean == pytest.approx(24.97, abs=1e-12)
    assert t.half_width == pytest.approx(0.01, abs=1e-12)


def test_sigma_normal_sigma_level():
    """NORMAL: σ = T / sigma_level."""
    assert Tolerance(50.0, -0.3, 0.3).sigma == pytest.approx(0.1)
    assert Tolerance(50.0, -0.3, 0.3, sigma_level=6.0).sigma == pytest.approx(0.05)
    assert Tolerance(50.0, -0.3, 0.3, sigma_level=1.5).sigma == pytest.approx(0.2)


def test_sigma_duzgun():
    """Düzgün dağılım [−T, T]: σ = T / √3."""
    t = Tolerance(50.0, -0.3, 0.3, Distribution.UNIFORM)
    assert t.sigma == pytest.approx(0.3 / math.sqrt(3.0), rel=1e-12)


def test_sigma_ucgen():
    """Simetrik üçgen dağılım [−T, T]: σ = T / √6."""
    t = Tolerance(50.0, -0.3, 0.3, Distribution.TRIANGULAR)
    assert t.sigma == pytest.approx(0.3 / math.sqrt(6.0), rel=1e-12)


def test_sigma_level_duzgun_ve_ucgende_etkisiz():
    """sigma_level yalnız NORMAL'de kullanılır."""
    for dist, bolen in ((Distribution.UNIFORM, math.sqrt(3.0)), (Distribution.TRIANGULAR, math.sqrt(6.0))):
        t = Tolerance(0.0, -0.6, 0.6, dist, sigma_level=6.0)
        assert t.sigma == pytest.approx(0.6 / bolen, rel=1e-12)


def test_sigma_asimetrik_bantta_yari_genislikten():
    """σ yarı bant genişliğinden hesaplanır, sapmaların kendisinden değil."""
    t = Tolerance(20.0, 0.0, 0.021, Distribution.UNIFORM)
    assert t.sigma == pytest.approx(0.0105 / math.sqrt(3.0), rel=1e-12)


@pytest.mark.parametrize("dist", list(Distribution))
def test_sifir_bant_sigma_sifir(dist):
    """T = 0 → σ = 0 (her dağılımda)."""
    t = Tolerance(12.0, 0.05, 0.05, dist)
    assert t.half_width == 0.0
    assert t.sigma == 0.0
    assert t.mean == pytest.approx(12.05)


def test_aci_toleransi():
    """Açı toleransı da aynı kayıt: 90° ± 0.5°."""
    t = Tolerance.symmetric(90.0, 0.5, name="aci")
    assert t.mean == pytest.approx(90.0)
    assert t.half_width == pytest.approx(0.5)


# ---------------------------------------------------------------- symmetric


def test_symmetric():
    """50 ± 0.1: lower = −0.1, upper = +0.1."""
    t = Tolerance.symmetric(50.0, 0.1)
    assert t.nominal == 50.0
    assert t.lower == pytest.approx(-0.1)
    assert t.upper == pytest.approx(0.1)
    assert t.distribution is Distribution.NORMAL
    assert t.sigma_level == 3.0
    assert t.mean == pytest.approx(50.0)
    assert t.half_width == pytest.approx(0.1)
    assert t == Tolerance(50.0, -0.1, 0.1)


def test_symmetric_ek_argumanlar():
    t = Tolerance.symmetric(10.0, 0.2, Distribution.UNIFORM, sigma_level=4.0, name="L1")
    assert t.distribution is Distribution.UNIFORM
    assert t.sigma_level == 4.0
    assert t.name == "L1"
    assert t.sigma == pytest.approx(0.2 / math.sqrt(3.0))


def test_symmetric_sifir_t():
    t = Tolerance.symmetric(10.0, 0.0)
    assert t.lower == 0.0 and t.upper == 0.0
    assert t.sigma == 0.0


def test_symmetric_negatif_t_hata():
    with pytest.raises(AssyError):
        Tolerance.symmetric(10.0, -0.1)


# ---------------------------------------------------------------- doğrulama


def test_lower_upper_den_buyuk_hata():
    with pytest.raises(AssyError):
        Tolerance(10.0, 0.1, -0.1)


def test_lower_esit_upper_gecerli():
    Tolerance(10.0, 0.02, 0.02)


@pytest.mark.parametrize("kotu", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("alan", ["nominal", "lower", "upper", "sigma_level"])
def test_sonlu_olmayan_hata(alan, kotu):
    args = {"nominal": 10.0, "lower": -0.1, "upper": 0.1, "sigma_level": 3.0}
    args[alan] = kotu
    with pytest.raises(AssyError):
        Tolerance(**args)


@pytest.mark.parametrize("seviye", [0.0, -3.0])
def test_sigma_level_pozitif_olmali(seviye):
    with pytest.raises(AssyError):
        Tolerance(10.0, -0.1, 0.1, sigma_level=seviye)


# ---------------------------------------------------------------- to_dict / from_dict


def test_to_dict_dagilim_degeri():
    """distribution dizesi .value olarak yazılır; sözlük JSON'a dökülebilir."""
    t = Tolerance(20.0, 0.0, 0.021, Distribution.TRIANGULAR, 3.0, "delik")
    d = t.to_dict()
    assert d["distribution"] == "ucgen"
    assert type(d["distribution"]) is str
    assert d["nominal"] == 20.0
    assert d["lower"] == 0.0
    assert d["upper"] == 0.021
    assert d["sigma_level"] == 3.0
    assert d["name"] == "delik"
    json.dumps(d)


@pytest.mark.parametrize("dist", list(Distribution))
def test_gidis_donus(dist):
    t = Tolerance(33.3, -0.05, 0.12, dist, 4.5, "x")
    t2 = Tolerance.from_dict(t.to_dict())
    assert t2 == t
    assert t2.distribution is dist


def test_json_uzerinden_gidis_donus():
    t = Tolerance.symmetric(50.0, 0.1, Distribution.UNIFORM, name="L")
    t2 = Tolerance.from_dict(json.loads(json.dumps(t.to_dict())))
    assert t2 == t
    assert t2.sigma == pytest.approx(t.sigma)


def test_from_dict_dogrular():
    """from_dict de __post_init__ doğrulamasından geçer."""
    d = Tolerance(10.0, -0.1, 0.1).to_dict()
    d["lower"], d["upper"] = 0.1, -0.1
    with pytest.raises(AssyError):
        Tolerance.from_dict(d)
