"""
SPEC 37 — Kabuk ekranı: proje dosyası, ekranlar arası tek geri al / yinele, yayılım ve etki.

Kabuk hesap yapmaz: hangi bölümün kimden etkilendiğini (Ekran.bolum / Ekran.bagimli) bilir, yeniden hesabı
sırayla sahibi ekrana (`ice_aktar`) yaptırır ve önce / sonra `ozet()`'lerini karşılaştırır.

Uçlar `/api/proje/...` altındadır (A3 §URL kararı: kabuğun kendi uçları); `kur(app)` ile bağlanır, ayrıca
ekranların durum değiştiren isteklerini yakalayan ara katmanı kurar.

    Etki = [{bolum, ekran, once: Ozet, sonra: Ozet, fark: {anahtar: sonra − once}}]
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI

from fileio.proje import Proje
from tezgah.ekranlar import Ekran

AD = "kabuk"
BOLUM = "kabuk"
ONEK = "/api/proje"
ETIKET_BASLIGI = "X-Tezgah-Etiket"
ONBELLEK_SINIRI = 256 * 1024 * 1024  # bellekteki önbellek, bayt


def sira(ekranlar: Sequence[Ekran]) -> list[str]:
    """Bölümlerin topolojik sırası; eşitlikte ad. Döngü / bilinmeyen bölüme bağımlılık → ProjeError."""
    raise NotImplementedError


def kapanis(ekranlar: Sequence[Ekran], degisen: set[str]) -> list[str]:
    """`degisen`'in aşağı akış kapanışı (değişenler hariç), topolojik sırayla."""
    raise NotImplementedError


def girdi_ozeti(ekran: Ekran, bolumler: dict[str, dict]) -> str:
    """ozet({b: bolumler[b] for b in (ekran.bolum,) + ekran.bagimli})."""
    raise NotImplementedError


class Kabuk:
    """Tek kullanıcılı proje durumu: güncel Proje, dosya yolu, kirli bayrağı, son Etki."""

    def __init__(self, ekranlar: Sequence[Ekran]) -> None:
        raise NotImplementedError

    @property
    def proje(self) -> Proje:
        raise NotImplementedError

    @property
    def kirli(self) -> bool:
        raise NotImplementedError

    def durum(self) -> dict:
        """GET /api/proje yanıtı."""
        raise NotImplementedError

    def degistir(self, yamalar: list[dict], etiket: str, onizle: bool = False) -> list[dict]:
        """JSON Pointer yamalarını uygular, yayar, Etki döndürür; hata → bütün geri çevirme."""
        raise NotImplementedError

    def yakala(self, etiket: str, ekran: str) -> list[dict] | None:
        """Bir ekranın kendi ucundan sonra: disa_aktar farklarını kaydeder ve aşağı akışa yayar."""
        raise NotImplementedError

    def geri_al(self) -> list[dict]:
        raise NotImplementedError

    def yinele(self) -> list[dict]:
        raise NotImplementedError

    def yeni(self, ad: str) -> None:
        raise NotImplementedError

    def ac(self, yol: str | Path) -> None:
        raise NotImplementedError

    def ac_bayt(self, veri: bytes) -> None:
        raise NotImplementedError

    def kaydet(self, yol: str | Path | None = None) -> Path:
        raise NotImplementedError

    def bayt(self) -> bytes:
        """GET /api/proje/indir: güncel projenin .3dc baytları."""
        raise NotImplementedError


def kur(app: FastAPI) -> None:
    """`/api/proje` router'ını ve yakalama ara katmanını uygulamaya bağlar (A3 Ekran.kur)."""
    raise NotImplementedError


def _disa_aktar() -> dict:
    raise NotImplementedError


def _ice_aktar(belge: dict, onbellek: dict[str, bytes]) -> None:
    raise NotImplementedError


EKRAN = Ekran(
    ad=AD,
    baslik="Proje",
    sira=0,
    bolum=BOLUM,
    disa_aktar=_disa_aktar,
    ice_aktar=_ice_aktar,
    kur=kur,
)
