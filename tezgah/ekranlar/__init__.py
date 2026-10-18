"""
A3 — Tezgah ekran kaydı (specs/24a-ekran-kaydi.md). Ortak arayüz: değişikliği ayrı PR + kullanıcı onayı.

Her ekran bu paketin altında kendi modülündedir (`tezgah/ekranlar/<ad>.py`) ve `EKRAN: Ekran` dışa verir.
Kabuk (`tezgah/sunucu.py`) ekranları `ekranlar()` ile bulur; yeni ekran eklemek yalnız yeni dosya eklemektir.

Uçlar: ekranın `router`'ı öneksiz yazılır, kabuk `/api/ekran/<ad>` altına bağlar. SPEC 24'ün uçları
(`/api/isler`, `/api/is/{ad}/...`) kabuğun iş deposu uçları olarak aynen kalır.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI

# Kabuğa ait klavye kısayolları: ekranlar bunları kaydedemez (§3).
KABUK_KISAYOLLARI = ("Ctrl+K", "Ctrl+Z", "Ctrl+Shift+Z", "Ctrl+Y", "Ctrl+S", "Ctrl+Shift+S", "Ctrl+O")

# Ekran uçlarının öneki: /api/ekran/<ad>/...
ONEK = "/api/ekran"


@dataclass(frozen=True)
class Ekran:
    """Bir Tezgah ekranının kaydı.

    ad        : küçük harf ascii kimlik ([a-z][a-z0-9_]*); URL'de /api/ekran/<ad>
    baslik    : sekmede görünen ad
    sira      : sekme sırası (küçük önce, eşitse ad)
    tus       : sekme kısayolu, tek rakam ("1".."9") ya da None
    router    : ekranın uçları (öneksiz); None → uç yok
    hazir     : None dönerse ekran kullanılabilir; metin dönerse neden (sekme kapalı, uçlar 503)
    sifirla   : POST /api/sifirla'da çağrılır (ekran durumu varsayılana)
    bolum     : sahip olunan proje bölümü (yalnız bu ekran yazar)
    bagimli   : girdi alınan bölümler (paylasilan_bolum ile okunur)
    disa_aktar: bölümün güncel belgesi ("sema" alanlı, JSON'a çevrilebilir, nan/inf yok)
    ice_aktar : (belge, onbellek) yükler ve türetilmiş durumu kurar; ATOMİK (hata → durum değişmez)
    ozet      : etki kartı ölçüleri (sonlu sayı ya da metin)
    onbellek  : isteğe bağlı ikili önbellek (proje dosyasına yazılır)
    kur       : uygulama kurulurken bir kez çağrılır (ör. kabuğun ara katmanı)
    """

    ad: str
    baslik: str
    sira: int = 100
    tus: str | None = None
    router: APIRouter | None = None
    hazir: Callable[[], str | None] | None = None
    sifirla: Callable[[], None] | None = None
    bolum: str | None = None
    bagimli: tuple[str, ...] = ()
    disa_aktar: Callable[[], dict] | None = None
    ice_aktar: Callable[[dict, Mapping[str, bytes]], None] | None = None
    ozet: Callable[[], dict[str, float | str]] | None = None
    onbellek: Callable[[], dict[str, bytes]] | None = None
    kur: Callable[[FastAPI], None] | None = None


def ekranlar() -> list[Ekran]:
    """Paketteki modülleri (pkgutil) bulur, her birinin `EKRAN`'ını `sira`, sonra `ad` ile sıralı döndürür.

    Importu hata veren modül kabuğu çökertmez: modül adıyla, `hazir` hata metnini dönen kapalı bir yer tutucu
    listelenir. Kayıt hataları (geçersiz ad, çift ad / tuş, kabuk tuşu, iki sahipli bölüm, sahipsiz `bagimli`,
    bağımlılık döngüsü, bölüm sahibinde `disa_aktar` / `ice_aktar` eksik) → ModelError.
    """
    raise NotImplementedError("A3: uygulanmadı")


def dogrula(liste: list[Ekran]) -> list[Ekran]:
    """`ekranlar()`'ın kayıt doğrulaması (verilen listeye de uygulanır); sıralı listeyi döndürür.

    Hata → ModelError.
    """
    raise NotImplementedError("A3: uygulanmadı")


def paylasilan_bolum(ad: str) -> dict:
    """`ad` bölümünün sahibi ekranın güncel `disa_aktar()` belgesi (derin kopya). Sahipsiz → KeyError."""
    raise NotImplementedError("A3: uygulanmadı")


def is_kaydet(ad: str, tanim: object) -> None:
    """Dinamik işi iş deposuna ekler: `tezgah.kopru.IsTanimi` → freze ("isler"), SPEC 25 torna iş tanımı →
    torna ("torna_isleri"). İş /api/isler'de görünür, #/freze?is=<ad> / #/torna?is=<ad> ile açılır.
    Aynı ad varsa yerine geçer. Geçersiz tanım → CamError, depo değişmez."""
    raise NotImplementedError("A3: uygulanmadı")
