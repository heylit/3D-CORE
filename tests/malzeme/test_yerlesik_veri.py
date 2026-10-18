"""SPEC 66 — yerleşik malzeme verisi testleri (K1, K2, K3, K10).

Testler yalnız specs/66-malzeme-kutuphanesi.md (onaylı metin) ve B2 arayüzünden (malzeme/model.py) yazıldı;
malzeme/kutuphane.py gövdesi okunmadı. Değerler değil, liste tablosu, zorunlu alanlar ve fiziksel olarak makul
aralıklar denetlenir (SPEC: "SPEC sayı içermez").

Birimler N – mm – MPa – s – t (B2): rho t/mm³, k mW/(mm·K), cp mJ/(t·K), Vc m/dk.
Kod henüz yokken (NotImplementedError) testler kök conftest.py ile "uygulanmamış" sayılır.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assy.model import Assembly
from malzeme.kutuphane import yerlesik
from malzeme.model import Malzeme

KOK = Path(__file__).resolve().parents[2]
ORNEK = KOK / "examples" / "66_montaj_malzemeli.json"

# SPEC 66 "Yerleşik malzeme listesi": id → (standart parçaları, grup, iso513)
LISTE = {
    "1.0038": (("EN 10025-2",), "celik", "P"),
    "1.0577": (("EN 10025-2",), "celik", "P"),
    "1.0503": (("EN 10083-2",), "celik", "P"),
    "1.7225": (("EN 10083-3",), "celik", "P"),
    "1.2312": (("EN ISO 4957",), "celik", "P"),
    "1.4301": (("EN 10088-3",), "paslanmaz", "M"),
    "1.4404": (("EN 10088-3",), "paslanmaz", "M"),
    "EN-GJL-250": (("EN 1561",), "dokme_demir", "K"),
    "EN-AW-6061-T6": (("EN 573-3", "EN 755-2"), "aluminyum", "N"),
    "EN-AW-6082-T6": (("EN 573-3", "EN 755-2"), "aluminyum", "N"),
    "EN-AW-7075-T6": (("EN 573-3", "EN 755-2"), "aluminyum", "N"),
    "CW614N": (("EN 12164",), "bakir", "N"),
    "Ti-6Al-4V": (("ASTM B348",), "titanyum", "S"),
    "POM-C": ((), "plastik", None),
}
METAL = [i for i, (_, g, _) in LISTE.items() if g != "plastik"]
TALASLI = [i for i, (_, g, _) in LISTE.items() if g in ("celik", "paslanmaz", "dokme_demir", "aluminyum")]
ZORUNLU = ("E", "nu", "rho", "Rp02", "Rm", "k", "cp", "alpha")


def kayit(id: str) -> Malzeme:
    return yerlesik().get(id)


def ids_grup(*gruplar: str) -> list[str]:
    return [i for i, (_, g, _) in LISTE.items() if g in gruplar]


# ---------------------------------------------------------------- K1 yükleme


def test_K1_on_dort_kayit_birebir():
    kut = yerlesik()
    assert len(kut) == 14
    assert {m.id for m in kut} == set(LISTE)


@pytest.mark.parametrize("id", list(LISTE))
def test_K1_kayit_kaynakli_ve_yerlesik(id):
    m = kayit(id)
    assert isinstance(m, Malzeme)
    assert m.id == id
    assert isinstance(m.kaynak, str) and m.kaynak.strip()
    assert m.kullanici is False


@pytest.mark.parametrize("id", list(LISTE))
def test_K1_liste_tablosu(id):
    standartlar, grup, iso = LISTE[id]
    m = kayit(id)
    assert m.grup == grup
    assert m.iso513 == iso
    for s in standartlar:
        assert s in m.standart


def test_K1_dosya_bicimi():
    # yerleşik dosya kullanıcı dosyasıyla aynı biçimde: {"surum": 1, "malzemeler": [...]}
    kut = yerlesik()
    d = json.loads((KOK / "malzeme" / "yerlesik.json").read_text(encoding="utf-8"))
    assert d["surum"] == 1
    assert len(d["malzemeler"]) == 14
    assert sorted((Malzeme.from_dict(x) for x in d["malzemeler"]), key=lambda m: m.id) == list(kut)


# ---------------------------------------------------------------- K2 zorunlu alanlar


@pytest.mark.parametrize("alan", ZORUNLU)
@pytest.mark.parametrize("id", METAL)
def test_K2_zorunlu_alan_dolu(id, alan):
    assert getattr(kayit(id), alan) is not None


@pytest.mark.parametrize("id", list(LISTE))
def test_K2_fiyat_bos(id):
    # D7: kaynaklı, tarihli çubuk fiyatı yok; atölye fiyatı kullanıcı dosyasında
    assert kayit(id).fiyat is None


@pytest.mark.parametrize("id", METAL)
def test_K2_iso513_dolu(id):
    assert kayit(id).iso513 is not None


@pytest.mark.parametrize("id", TALASLI)
def test_K2_kienzle_ve_karbur_onerisi(id):
    m = kayit(id)
    assert m.kc11 is not None and m.mc is not None
    assert "karbur" in m.kesme


# ---------------------------------------------------------------- K3 makul aralık

ARALIK: list[tuple[tuple[str, ...], str, float, float]] = [
    (("celik", "paslanmaz"), "E", 190_000.0, 215_000.0),
    (("celik", "paslanmaz"), "rho", 7.7e-9, 8.1e-9),
    (("celik", "paslanmaz"), "k", 12.0, 60.0),
    (("celik", "paslanmaz"), "alpha", 1.0e-5, 1.8e-5),
    (("celik", "paslanmaz"), "cp", 4.2e8, 5.2e8),
    (("aluminyum",), "E", 68_000.0, 73_000.0),
    (("aluminyum",), "rho", 2.6e-9, 2.85e-9),
    (("aluminyum",), "k", 110.0, 210.0),
    (("aluminyum",), "alpha", 2.1e-5, 2.5e-5),
    (("titanyum",), "E", 105_000.0, 120_000.0),
    (("titanyum",), "rho", 4.3e-9, 4.5e-9),
    (("dokme_demir",), "E", 80_000.0, 140_000.0),
    (("plastik",), "E", 1000.0, 4000.0),
    (("plastik",), "rho", 1.1e-9, 1.5e-9),
]
ARALIK_PARAM = [
    pytest.param(id, alan, lo, hi, id=f"{id}-{alan}")
    for gruplar, alan, lo, hi in ARALIK
    for id in ids_grup(*gruplar)
]


@pytest.mark.parametrize("id, alan, lo, hi", ARALIK_PARAM)
def test_K3_grup_araligi(id, alan, lo, hi):
    v = getattr(kayit(id), alan)
    assert v is not None, f"{id}: {alan} yok"
    assert lo <= v <= hi, f"{id}: {alan} = {v} ∉ [{lo}, {hi}]"


@pytest.mark.parametrize("id", list(LISTE))
def test_K3_kienzle_araligi(id):
    m = kayit(id)
    if m.kc11 is not None:
        assert 300.0 <= m.kc11 <= 3500.0
    if m.mc is not None:
        assert 0.1 <= m.mc <= 0.45


@pytest.mark.parametrize("id", list(LISTE))
def test_K3_kesme_hizi_araligi(id):
    for takim, oneri in kayit(id).kesme.items():
        assert 20.0 <= oneri.Vc <= 2000.0, f"{id} / {takim}: Vc = {oneri.Vc} m/dk"


# ---------------------------------------------------------------- K10 örnek dosya


def test_K10_ornek_montaj_malzemeli():
    if not ORNEK.exists():
        raise NotImplementedError("SPEC 66: examples/66_montaj_malzemeli.json henüz yok")
    asm = Assembly.from_dict(json.loads(ORNEK.read_text(encoding="utf-8")))
    kut = yerlesik()
    assert asm.components
    for c in asm.components:
        assert c.material is not None, f"bileşen {c.name!r}: material yok"
        assert c.material in kut, f"bileşen {c.name!r}: {c.material!r} yerleşik kütüphanede yok"
