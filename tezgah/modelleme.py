"""
SPEC 26 — model geçmişi: doğrusal adım listesi, her değişiklikte baştan kurulur (saf, deterministik).

    Model = {sema: 1, ad, parametreler: {ad: ifade}, adimlar: [Adim]}
    Adim  = {kimlik, tur: "eskiz", duzlem: Duzlem, eskiz: Sketch.to_dict(), olculer: {kisit_sirasi: ifade}}
          | {kimlik, tur: "ekstruzyon", eskiz: kimlik, bolgeler: [i] | "hepsi", mesafe: ifade,
             yon: "ileri" | "geri" | "simetrik", islem: "yeni" | "ekle" | "kes",
             bitis: "mesafe" | "boydan_boya"}
          | {kimlik, tur: "delik", eskiz: kimlik, noktalar: [nokta kimliği],
             cesit: "duz" | "havsa" | "lamba" | "dis", d: ifade, derinlik: ifade | None, ...}
    Duzlem = {tur: "XY" | "XZ" | "YZ", ofset: ifade}
           | {tur: "yuz", adim: kimlik, yuz: index, plane: Plane.to_dict()}

Kontrol sözlükleri SPEC 24 biçimindedir (tezgah/kopru.py). FastAPI'siz test edilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from geometry.part import Part


@dataclass
class AdimRaporu:
    """Bir adımın sonucu. eskiz: dof, freedom, celiski; ekstrüzyon: alanlar, dV; hata: çekirdeğin metni."""

    kimlik: str
    tur: str
    hata: str | None = None
    dof: int | None = None
    freedom: dict[str, int] = field(default_factory=dict)
    celiski: tuple[int, ...] = ()
    alanlar: tuple[float, ...] = ()  # seçilen bölgelerin alanları, mm²
    dV: float | None = None  # hacim değişimi, mm³


@dataclass
class Rapor:
    adimlar: list[AdimRaporu] = field(default_factory=list)
    kontroller: list[dict] = field(default_factory=list)

    @property
    def hata(self) -> AdimRaporu | None:
        """İlk başarısız adım (yoksa None)."""
        return next((a for a in self.adimlar if a.hata is not None), None)


def insa(model: dict, k: int | None = None) -> tuple[Part | None, Rapor]:
    """Modeli baştan kurar; k verilirse ilk k adımda durur.

    Parametreleri değerlendirir, ölçüleri eskizlere yazar, SPEC 17 ile çözer, bölgeleri çıkarır, katı
    işlemleri sırayla uygular. Bir adım başarısızsa kurulum orada durur, hata adım kimliğiyle Rapor'a
    yazılır ve önceki adımların parçası döner. Yüze bağlı eskizin düzlemi önceki parçanın bir yüzüyle
    çakışmıyorsa Kontrol(durum="uyari", kimlik="eskiz_duzlemi_kopuk").
    """
    raise NotImplementedError("SPEC 26: insa")


def ornek_model(ad: str = "flans") -> dict:
    """Uydurma örnek model. "flans": dış dikdörtgen plaka, ortada 8 mm kör cep, 4 boydan boya delik (K8)."""
    raise NotImplementedError("SPEC 26: ornek_model")
