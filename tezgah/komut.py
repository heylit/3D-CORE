"""
SPEC 62 — komut paleti: normalleştirme, belirlenimci dilbilgisi, öneri (yapay zekâ yok).

Tanınmayan ya da iki anlamlı komut tahmin edilmez: KomutError (öneri ve okumalarla). FastAPI'siz test edilir.

Çıktı adımı (Cozum.adim) SPEC 26 adım sözlüğünün yerleşimsiz çekirdeğidir; sayılar float, adet int:
    delik : {tur: "delik", cesit: "duz", d, derinlik}            derinlik None = boydan boya
            + {tolerans: "H7", d_hedef}                          tolerans verilirse (tezgah.tolerans)
            cesit "dis"   : + {thread: "M8" | "M8x1"}, d = kılavuz matkabı d_n − P (M8 → 6.8, M8x1 → 7.0)
            cesit "havsa" : + {csk_d, csk_angle}                 "havşa 12x90"; açı yoksa 90
            cesit "lamba" : + {cbore_d, cbore_depth}             "lamba Ø15 derin 9"
    cep   : {tur: "cep", w, l, r, derinlik}                      "cep 40x20 derin 5" → r = 0.0
    pah   : {tur: "pah", d, aci}                                 açı yoksa 45.0
    fillet: {tur: "fillet", r}
    kanal : {tur: "kanal", genislik, derinlik}
    ortak nitelikler: {adet: int, aralik: float} (dizi), {yuz: ad}; verilmeyen nitelik sözlükte yoktur.

Yerleşim (hangi yüz, hangi nokta) `yerlestir` ile ayrı yapılır: cozumle yerleşimsiz adımı verir (K1),
yerlestir seçili yüz / noktayla SPEC 26 model adımlarını üretir (K3); seçim yoksa "Önce bir yüz seçin".
"""

from __future__ import annotations

from dataclasses import dataclass, field


class KomutError(ValueError):
    """Çözülemeyen komut. oneriler: en yakın anahtar sözcükler; okumalar: iki anlamlılıkta olası okumalar."""

    def __init__(self, mesaj: str, oneriler: tuple[str, ...] = (), okumalar: tuple[str, ...] = ()):
        super().__init__(mesaj)
        self.oneriler = tuple(oneriler)
        self.okumalar = tuple(okumalar)


@dataclass(frozen=True)
class Cozum:
    """adim: yerleşimsiz SPEC 26 adım çekirdeği (modül açıklaması); aciklama: insan okunur geri bildirim."""

    adim: dict = field(default_factory=dict)
    aciklama: str = ""


def normallestir(metin: str) -> str:
    """Türkçe kurallı küçük harf, Ø / çap, ondalık virgül, x, derin eşanlamlıları, tek boşluk (SPEC 62 §1)."""
    raise NotImplementedError("SPEC 62: normallestir")


def cozumle(metin: str, secim: dict | None = None) -> Cozum:
    """Komut → Cozum. Hata → KomutError. secim yalnız aciklama içindir; yerleşim yerlestir'dedir."""
    raise NotImplementedError("SPEC 62: cozumle")


def yerlestir(adim: dict, secim: dict | None, model: dict) -> list[dict]:
    """Yerleşimsiz adım + seçim → modele eklenecek SPEC 26 adımları ([eskiz, delik]).

    secim = {"duzlem": SPEC 26 Duzlem sözlüğü, "nokta": [u, v]} (düzlem koordinatı, mm).
    secim None → KomutError("Önce bir yüz seçin"). İlk sürüm yalnız delik adımını yerleştirir; cep, pah,
    fillet ve kanal için SPEC 26'da adım olmadığından KomutError (ikinci aşama).
    """
    raise NotImplementedError("SPEC 62: yerlestir")


def ornekler() -> list[tuple[str, dict]]:
    """Paletin yardım listesi: (komut, beklenen adım). K1 tablosuyla aynı kaynak."""
    raise NotImplementedError("SPEC 62: ornekler")
