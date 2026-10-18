"""
SPEC 62 §4 — artımlı yeniden hesap: önbellekli `modelleme.insa` + `cam.plan` freze planı.

Katı önbelleği: k. adımdan sonraki kurulum durumu (parça, eskizler, rapor). Anahtar = parametrelerin ve ilk
k adımın kanonik JSON'unun SHA-256 özeti. Ölçü değişince önbellekteki en uzun ön ekten kurulum sürer.
Plan önbelleği: anahtar = tanınan özelliklerin (SPEC 27 `recognize`) kanonik özeti + stok + kütüphane +
malzeme + seçenekler; özellikler aynıysa plan yeniden kurulmaz. Sıra ve takım değişimi birleştirmesi
plan_mill_features içindedir, her plan kurulumunda baştan yapılır.

Değişmez (K6): `insa_ve_planla` sonucu önbelleksiz `insa(model)` + `plan_mill(part, stok, kutuphane,
malzeme)` ile birebir aynı (`summary()`, her işlemin hareketleri, süreler). Model kurulamazsa (Rapor.hata)
ya da katı yoksa GeometryError; başarısız adımın durumu önbelleğe girmez.
"""

from __future__ import annotations

from cam.model import Stock, ToolLibrary
from cam.plan import MillPlan
from geometry.part import Part
from tezgah.modelleme import Rapor


class Onbellek:
    """En son kullanılan `boyut` katı durumu ve `boyut` planı tutar (LRU)."""

    def __init__(self, boyut: int = 64) -> None:
        raise NotImplementedError("SPEC 62: Onbellek")

    def insa(self, model: dict) -> tuple[Part | None, Rapor]:
        """Önbellekli `modelleme.insa(model)`; parça ve rapor önbelleksiz kurulumla aynı."""
        raise NotImplementedError("SPEC 62: Onbellek.insa")

    def insa_ve_planla(
        self, model: dict, stok: Stock, kutuphane: ToolLibrary, malzeme: str, **kw
    ) -> tuple[Part, MillPlan, Rapor]:
        """Önbellekli insa + plan_mill(part, stok, kutuphane, malzeme, **kw)."""
        raise NotImplementedError("SPEC 62: Onbellek.insa_ve_planla")

    def istatistik(self) -> dict:
        """{"adim_isabet", "adim_kacirma", "plan_isabet", "plan_kacirma"}: önbellekten gelen / kurulan adım
        ve plan sayıları (oluşturulduğundan ya da temizle()'den beri)."""
        raise NotImplementedError("SPEC 62: Onbellek.istatistik")

    def temizle(self) -> None:
        """Önbelleği ve sayaçları boşaltır."""
        raise NotImplementedError("SPEC 62: Onbellek.temizle")


def olcu_degistir(model: dict, adim: str, olcu: str, deger: float | str) -> dict:
    """Modelin derin kopyası; kimliği `adim` olan adımın `olcu` yolundaki değeri `deger` olur.

    olcu: adımın doğrudan anahtarı ("mesafe", "d", "derinlik", "csk_d", …) ya da eskiz ölçüsü
    "olculer/<kısıt sırası>". Bilinmeyen adım, adımda olmayan ölçü yolu, bool / sonlu olmayan sayı ya da boş
    ifade → GeometryError; girdi modeli değişmez.
    """
    raise NotImplementedError("SPEC 62: olcu_degistir")
