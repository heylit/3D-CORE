"""SPEC 66 — malzeme/kutuphane.py testleri: Kutuphane, yerleşik, kullanıcı dosyası (K4, K5).

Testler yalnız specs/66-malzeme-kutuphanesi.md (onaylı metin) ve B2 arayüzünden (malzeme/model.py) yazıldı;
malzeme/kutuphane.py gövdesi okunmadı. Kutuphane davranışı önce uydurma kayıtlarla (veriden bağımsız),
sonra K4'ün istediği yerleşik kayıtlarla denetlenir.

JSON biçimi (SPEC 66): {"surum": 1, "malzemeler": [Malzeme.to_dict(), ...]}.
Hata sınıfı: malzeme.model.ModelError (B2 kararı).
Kod henüz yokken (NotImplementedError) testler kök conftest.py ile "uygulanmamış" sayılır.
"""

from __future__ import annotations

import json

import pytest

from malzeme.kutuphane import Kutuphane, kullanici_oku, kullanici_yaz, kutuphane, yerlesik
from malzeme.model import KesmeOnerisi, Malzeme, ModelError


def mk(id: str, name: str = "", grup: str = "celik", standart: str = "EN 0000", **kw) -> Malzeme:
    """Uydurma kayıt (gerçek veri değil): çelik benzeri sabitler, test kaynağı."""
    alanlar = dict(E=200_000.0, nu=0.3, rho=7.8e-9)
    alanlar.update(kw)
    return Malzeme(
        id=id, name=name or id, standart=standart, grup=grup, kaynak="test: uydurma kayıt", **alanlar
    )


def ornek() -> Kutuphane:
    return Kutuphane(
        [
            mk("Z-3", "Zeta celigi", standart="EN 9999-1"),
            mk("A-1", "Alfa alasimi", grup="aluminyum", standart="EN 573-3", E=70_000.0, rho=2.7e-9),
            mk("M-2", "Mu paslanmaz", grup="paslanmaz", standart="EN 10088-3"),
        ]
    )


def kullanici_kaydi(id: str = "1.0503-atolye", **kw) -> Malzeme:
    alanlar = dict(fiyat=1.5, kesme={"karbur": KesmeOnerisi(Vc=180.0, fz=0.08)})
    alanlar.update(kw)
    return mk(id, "C45 atolye", standart="EN 10083-2", kullanici=True, **alanlar)


# ---------------------------------------------------------------- Kutuphane (uydurma kayıtlarla)


class TestKutuphane:
    def test_get_contains_len(self):
        kut = ornek()
        assert len(kut) == 3
        assert kut.get("A-1").name == "Alfa alasimi"
        assert "M-2" in kut
        assert "B-9" not in kut

    def test_iter_id_sirasiyla(self):
        assert [m.id for m in ornek()] == ["A-1", "M-2", "Z-3"]

    def test_yinelenen_id(self):
        with pytest.raises(ModelError):
            Kutuphane([mk("A-1"), mk("A-1", "baska")])

    def test_bilinmeyen_id_yakin_eslesme(self):
        with pytest.raises(ModelError, match="Z-3"):
            ornek().get("Z-4")

    def test_ara_buyuk_kucuk_harf_duyarsiz(self):
        kut = ornek()
        assert [m.id for m in kut.ara("ALFA")] == ["A-1"]  # name
        assert [m.id for m in kut.ara("m-2")] == ["M-2"]  # id
        assert [m.id for m in kut.ara("10088")] == ["M-2"]  # standart
        assert {m.id for m in kut.ara("en ")} == {"A-1", "M-2", "Z-3"}
        assert kut.ara("yok-boyle-bir-sey") == []

    def test_grup(self):
        kut = ornek()
        assert [m.id for m in kut.grup("aluminyum")] == ["A-1"]
        assert kut.grup("nikel") == []  # B2 GRUPLAR içinde ama kayıt yok
        with pytest.raises(ModelError):
            kut.grup("tahta")

    def test_ekle_yeni_kutuphane(self):
        kut = ornek()
        yeni = kut.ekle(kullanici_kaydi("K-1"))
        assert isinstance(yeni, Kutuphane) and yeni is not kut
        assert len(kut) == 3 and "K-1" not in kut  # eskisi değişmez
        assert len(yeni) == 4 and yeni.get("K-1").kullanici is True
        assert [m.id for m in yeni.kullanici_kayitlari()] == ["K-1"]
        assert kut.kullanici_kayitlari() == []

    def test_ekle_kullanici_olmayan_kayit(self):
        with pytest.raises(ModelError):
            ornek().ekle(mk("K-1"))  # kullanici False

    def test_ekle_id_cakismasi(self):
        with pytest.raises(ModelError):
            ornek().ekle(kullanici_kaydi("A-1"))


# ---------------------------------------------------------------- K4 yerleşik: arama ve hata


class TestK4:
    def test_yerlesik_onbellekli(self):
        assert yerlesik() is yerlesik()

    def test_get_c45(self):
        assert yerlesik().get("1.0503").name.startswith("C45")

    def test_ara_6061_tek_kayit(self):
        bulunan = yerlesik().ara("6061")
        assert [m.id for m in bulunan] == ["EN-AW-6061-T6"]

    def test_ara_buyuk_kucuk_harf(self):
        ids = {m.id for m in yerlesik().ara("c45")}
        assert "1.0503" in ids
        assert ids == {m.id for m in yerlesik().ara("C45")}

    def test_bilinmeyen_id_mesajinda_yakin_eslesme(self):
        with pytest.raises(ModelError) as e:
            yerlesik().get("1.0505")
        assert "1.0503" in str(e.value)

    def test_bilinmeyen_grup(self):
        with pytest.raises(ModelError):
            yerlesik().grup("tahta")

    def test_grup_aluminyum(self):
        assert {m.id for m in yerlesik().grup("aluminyum")} == {
            "EN-AW-6061-T6",
            "EN-AW-6082-T6",
            "EN-AW-7075-T6",
        }


# ---------------------------------------------------------------- K5 kullanıcı dosyası


class TestK5:
    def test_gidis_donus(self, tmp_path):
        yol = tmp_path / "atolye.json"
        kayitlar = [
            kullanici_kaydi("1.0503-atolye"),
            kullanici_kaydi("POM-C-atolye", grup="plastik", E=2800.0),
        ]
        kullanici_yaz(yol, kayitlar)
        assert kullanici_oku(yol) == kayitlar
        assert kullanici_oku(str(yol)) == kayitlar  # str yol da kabul

    def test_dosya_bicimi(self, tmp_path):
        yol = tmp_path / "atolye.json"
        k = kullanici_kaydi()
        kullanici_yaz(yol, [k])
        d = json.loads(yol.read_text(encoding="utf-8"))
        assert d["surum"] == 1
        assert [Malzeme.from_dict(x) for x in d["malzemeler"]] == [k]

    def test_kutuphane_yerlesik_arti_kullanici(self, tmp_path):
        yol = tmp_path / "atolye.json"
        kullanici_yaz(yol, [kullanici_kaydi()])
        kut = kutuphane(yol)
        assert len(kut) == 15
        assert "1.0503-atolye" in kut and "1.0503" in kut
        assert [m.id for m in kut.kullanici_kayitlari()] == ["1.0503-atolye"]

    def test_kutuphane_dosyasiz(self):
        assert len(kutuphane()) == 14
        assert len(kutuphane(None)) == 14

    def test_yerlesik_id_ile_cakisma(self, tmp_path):
        # D5: kullanıcı dosyası yerleşik kaydı gölgeleyemez
        yol = tmp_path / "atolye.json"
        kullanici_yaz(yol, [kullanici_kaydi("1.0503")])
        with pytest.raises(ModelError):
            kutuphane(yol)

    def test_kullanici_false_kayit(self, tmp_path):
        yol = tmp_path / "atolye.json"
        d = {"surum": 1, "malzemeler": [kullanici_kaydi().to_dict(), mk("X-1").to_dict()]}
        yol.write_text(json.dumps(d), encoding="utf-8")
        with pytest.raises(ModelError):
            kullanici_oku(yol)

    def test_bilinmeyen_surum(self, tmp_path):
        yol = tmp_path / "atolye.json"
        yol.write_text(
            json.dumps({"surum": 2, "malzemeler": [kullanici_kaydi().to_dict()]}), encoding="utf-8"
        )
        with pytest.raises(ModelError):
            kullanici_oku(yol)
