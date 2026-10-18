"""
Tek proje dosyası `.3dc` (SPEC 37): adlı JSON bölümleri, önbellek, geri al / yinele geçmişi.

Dosya standart bir zip'tir:
    proje.json                 bildirim (sema, ad, bölüm / önbellek / geçmiş özetleri)
    bolumler/<ad>.json         kanonik JSON
    onbellek/<anahtar>.bin     ikili
    gecmis.json                Gecmis, kanonik JSON
Yazım belirlenimci (aynı proje → aynı bayt) ve atomiktir (tmp + os.replace). Bölümlerin içeriği burada
yorumlanmaz; yalnız kanonik JSON oldukları ve "sema" alanları denetlenir. Yalnız standart kitaplık kullanılır.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

SEMA = 1
UZANTI = ".3dc"
GECMIS_SINIRI = 200


class ProjeError(ValueError):
    """Bozuk ya da geçersiz proje / proje dosyası (sessiz hata yok)."""


@dataclass(frozen=True)
class Onbellek:
    """Pahalı bir sonucun baytları ve onu üreten girdilerin özeti."""

    girdi_ozeti: str
    veri: bytes


@dataclass(frozen=True)
class Gecmis:
    """Doğrusal geri al geçmişi. `konum`: geri alınabilecek kayıt sayısı (0 ≤ konum ≤ len(kayitlar)).

    Kayit = {etiket, ekran, bolumler: {ad: [once | None, sonra | None]}}
    """

    kayitlar: tuple[dict, ...] = ()
    konum: int = 0


@dataclass(frozen=True)
class Proje:
    """Değişmez proje durumu. İşlemler yeni nesne döndürür."""

    ad: str
    bolumler: Mapping[str, dict]
    onbellek: Mapping[str, Onbellek] = field(default_factory=dict)
    gecmis: Gecmis = field(default_factory=Gecmis)
    uyarilar: tuple[dict, ...] = ()  # SPEC 24 Kontrol biçimi; dosyaya yazılmaz


def kanonik(belge: dict) -> bytes:
    """sort_keys, ayırıcısız, ensure_ascii=False, allow_nan=False UTF-8 JSON; nan / inf → ProjeError."""
    raise NotImplementedError


def ozet(belge: dict) -> str:
    """sha256(kanonik(belge)) onaltılık."""
    raise NotImplementedError


def bos_proje(ad: str) -> Proje:
    """Yalnız "kabuk" bölümü olan boş proje."""
    raise NotImplementedError


def uygula(p: Proje, etiket: str, ekran: str, yeni: Mapping[str, dict | None]) -> Proje:
    """Değişen bölümleri tek kayıtla geçmişe ekler (None: bölüm silinir); hiçbiri değişmediyse kayıt yok."""
    raise NotImplementedError


def geri_al(p: Proje) -> Proje:
    """Son kaydı geri alır; konum 0 ise ProjeError."""
    raise NotImplementedError


def yinele(p: Proje) -> Proje:
    """Geri alınan kaydı yineler; yinelenecek kayıt yoksa ProjeError."""
    raise NotImplementedError


def kaydet(p: Proje, yol: str | Path) -> None:
    """Belirlenimci, atomik yazım; uzantı .3dc değilse ya da bölüm geçersizse ProjeError (diske yazılmaz)."""
    raise NotImplementedError


def ac(yol: str | Path) -> Proje:
    """Dosyayı okur ve denetler; bozuk girdi → ProjeError (mesajda girdi adı)."""
    raise NotImplementedError
