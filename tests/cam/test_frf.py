"""SPEC 71 — cam/frf.py testleri (K2, K10 frf kısmı).

Testler yalnız SPEC 71 "Teori / Ölçüm girdisi", "Arayüz" ve "Hatalar" bölümlerinden yazıldı;
cam/frf.py gövdeleri okunmadı. Beklenen değerler:
- Modal FRF: G(iω) = Σ 1 / (k_r (1 − r² + 2iζ_r r)),  r = ω/ω_n = f/f_n  (tests/cam/chatter_ref.sdof_g).
- tests/cam/veri/frf_ornek_xx.csv: f_n = 800 Hz, ζ = 0.03, k = 2·10⁴ N/mm SDOF, 400–1200 Hz, 0,5 Hz adım; bu
  formülle üretilip 17 anlamlı basamakla (repr) yazıldı. İlk satır '# birim: mm/N', ikinci satır sütun
  adlarını yorum olarak verir ('# f_Hz, Re, Im').
- FRF.at: ölçüm bandı içinde doğrusal ara değer (Re ve Im ayrı ayrı doğrusal), bant dışı → hata.

Hata sınıfı: cam.model.CamError (SPEC'teki "ModelError"; koordinatör kararı, K10 yalnız cam.model importu).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cam.frf import FRF, TakimFRF, frf_csv, frf_modal
from cam.model import CamError
from tests.cam.chatter_ref import sdof_g

VERI = Path(__file__).parent / "veri"
ORNEK = VERI / "frf_ornek_xx.csv"
FN, ZETA, K = 800.0, 0.03, 2.0e4


def yaz_csv(yol: Path, satirlar: list[tuple[float, float, float]], baslik: str = "# birim: mm/N") -> Path:
    with open(yol, "w", encoding="utf-8") as fh:
        if baslik:
            fh.write(baslik + "\n")
        fh.write("# f_Hz, Re, Im\n")
        for f, re, im in satirlar:
            fh.write(f"{f!r},{re!r},{im!r}\n")
    return yol


def ornek_satirlar(f) -> list[tuple[float, float, float]]:
    G = sdof_g(np.asarray(f, dtype=float), FN, ZETA, K)
    return [(float(fi), float(g.real), float(g.imag)) for fi, g in zip(f, G, strict=True)]


# ---------------------------------------------------------------- frf_modal


def test_frf_modal_sdof_formula():
    """K2 temeli: tek mod, G = 1 / (k (1 − r² + 2iζr)) (göreli 1e-13)."""
    f = np.linspace(100.0, 2000.0, 777)
    frf = frf_modal([(FN, ZETA, K)], f)
    assert isinstance(frf, FRF)
    assert np.array_equal(np.asarray(frf.f, dtype=float), f)
    assert np.allclose(frf.G, sdof_g(f, FN, ZETA, K), rtol=1e-13, atol=0.0)


def test_frf_modal_sum_of_modes():
    """Çok mod: modların G'leri toplanır."""
    f = np.linspace(200.0, 3000.0, 501)
    modlar = [(800.0, 0.03, 2.0e4), (1900.0, 0.05, 6.0e4)]
    exp = sdof_g(f, *modlar[0]) + sdof_g(f, *modlar[1])
    assert np.allclose(frf_modal(modlar, f).G, exp, rtol=1e-13, atol=0.0)


def test_frf_modal_static_and_resonance():
    """Bağımsız sayılar: f → 0'da G → 1/k; f = f_n'de G = 1/(2iζk) = −i/(2ζk)."""
    frf = frf_modal([(FN, ZETA, K)], np.array([1e-6, FN]))
    assert frf.G[0] == pytest.approx(1.0 / K, rel=1e-9)
    assert frf.G[1].real == pytest.approx(0.0, abs=1e-18)
    assert frf.G[1].imag == pytest.approx(-1.0 / (2 * ZETA * K), rel=1e-13)


# ---------------------------------------------------------------- K2: CSV okuma


def test_sample_csv_matches_modal():
    """K2: modal formülden üretilmiş örnek CSV, frf_modal ile 1e-12 içinde aynı G."""
    frf = frf_csv(ORNEK)
    f = np.asarray(frf.f, dtype=float)
    assert len(f) == 1601
    assert f[0] == 400.0 and f[-1] == 1200.0
    assert np.all(np.diff(f) > 0)
    exp = frf_modal([(FN, ZETA, K)], f).G
    assert np.allclose(frf.G, exp, rtol=0.0, atol=1e-12)
    assert np.allclose(frf.G, sdof_g(f, FN, ZETA, K), rtol=1e-12, atol=0.0)


def test_csv_accepts_str_path():
    """Yol str de olabilir."""
    assert len(frf_csv(str(ORNEK)).f) == 1601


def test_csv_written_roundtrip(tmp_path):
    """Kendi yazdığımız 3 satırlık dosya aynen okunur (birim çevirisi yok)."""
    rows = [(10.0, 1e-4, -2e-5), (20.0, -3e-4, -1e-4), (35.5, 2.5e-6, 0.0)]
    frf = frf_csv(yaz_csv(tmp_path / "a.csv", rows))
    assert np.array_equal(np.asarray(frf.f, dtype=float), [10.0, 20.0, 35.5])
    assert np.array_equal(frf.G, np.array([complex(r[1], r[2]) for r in rows]))


@pytest.mark.parametrize("baslik", ["# birim: m/N", "# birim: um/N", "# birim: mm/kN"])
def test_csv_wrong_unit_raises(tmp_path, baslik):
    """K2: başlıkta mm/N dışında birim → hata; mesaj kullanıcıya mm/N'e çevirmesini söyler."""
    yol = yaz_csv(tmp_path / "b.csv", ornek_satirlar([500.0, 600.0, 700.0]), baslik=baslik)
    with pytest.raises(CamError, match="mm/N"):
        frf_csv(yol)


def test_csv_wrong_unit_message_says_multiply_by_1000(tmp_path):
    """Karar 1: m/N için mesaj "1000 ile çarpıp mm/N olarak kaydedin" der."""
    yol = yaz_csv(tmp_path / "c.csv", ornek_satirlar([500.0, 600.0]), baslik="# birim: m/N")
    with pytest.raises(CamError, match="1000"):
        frf_csv(yol)


def test_csv_missing_unit_header_raises(tmp_path):
    """Birim başlığı zorunlu: yoksa hata."""
    yol = yaz_csv(tmp_path / "d.csv", ornek_satirlar([500.0, 600.0, 700.0]), baslik="")
    with pytest.raises(CamError):
        frf_csv(yol)


@pytest.mark.parametrize("f", [[500.0, 450.0, 700.0], [500.0, 600.0, 600.0], [900.0, 800.0, 700.0]])
def test_csv_non_increasing_frequency_raises(tmp_path, f):
    """K2: artan olmayan frekans (azalan veya tekrar eden) → hata."""
    with pytest.raises(CamError):
        frf_csv(yaz_csv(tmp_path / "e.csv", ornek_satirlar(f)))


@pytest.mark.parametrize("bozuk", [(float("nan"), -1e-5), (1e-5, float("inf")), (float("-inf"), 0.0)])
def test_csv_non_finite_g_raises(tmp_path, bozuk):
    """Hatalar: |G| sonlu değil → hata."""
    rows = ornek_satirlar([500.0, 600.0, 700.0])
    rows[1] = (600.0, *bozuk)
    with pytest.raises(CamError):
        frf_csv(yaz_csv(tmp_path / "f.csv", rows))


# ---------------------------------------------------------------- K2: at (bant içi ara değer, bant dışı hata)


def ucgen_frf() -> FRF:
    return FRF(f=np.array([100.0, 200.0, 400.0]), G=np.array([1.0 - 2.0j, 3.0 + 0.0j, -1.0 + 4.0j]))


def test_at_linear_interpolation():
    """Bant içinde doğrusal ara değer; uçlar ve düğümler aynen."""
    frf = ucgen_frf()
    got = frf.at(np.array([100.0, 150.0, 200.0, 250.0, 400.0]))
    exp = np.array([1.0 - 2.0j, 2.0 - 1.0j, 3.0 + 0.0j, 2.0 + 1.0j, -1.0 + 4.0j])
    assert np.allclose(got, exp, rtol=0.0, atol=1e-15)


def test_at_on_modal_grid_is_exact():
    """Izgara noktalarında at, G'nin kendisi."""
    f = np.linspace(400.0, 1200.0, 81)
    frf = frf_modal([(FN, ZETA, K)], f)
    assert np.array_equal(frf.at(f[10:20]), frf.G[10:20])


@pytest.mark.parametrize("q", [[99.999], [400.001], [150.0, 1000.0], [0.0]])
def test_at_outside_band_raises(q):
    """K2 / K8: bant dışı at → hata (ekstrapolasyon yok)."""
    with pytest.raises(CamError):
        ucgen_frf().at(np.array(q))


def test_takim_frf_defaults():
    """TakimFRF: çapraz terimler isteğe bağlı (None)."""
    frf = ucgen_frf()
    t = TakimFRF(xx=frf, yy=frf)
    assert t.xy is None and t.yx is None
