"""
A3 — Tezgah ekran kaydı (specs/24a-ekran-kaydi.md). Ortak arayüz: değişikliği ayrı PR + kullanıcı onayı.

Her ekran bu paketin altında kendi modülündedir (`tezgah/ekranlar/<ad>.py`) ve `EKRAN: Ekran` dışa verir.
Kabuk (`tezgah/sunucu.py`) ekranları `ekranlar()` ile bulur; yeni ekran eklemek yalnız yeni dosya eklemektir.

Uçlar: ekranın `router`'ı öneksiz yazılır, kabuk `/api/ekran/<ad>` altına bağlar. SPEC 24'ün uçları
(`/api/isler`, `/api/is/{ad}/...`) kabuğun iş deposu uçları olarak aynen kalır.
"""

from __future__ import annotations

import copy
import importlib
import pkgutil
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI

from core.model import ModelError

# Kabuğa ait klavye kısayolları: ekranlar bunları kaydedemez (§3).
KABUK_KISAYOLLARI = ("Ctrl+K", "Ctrl+Z", "Ctrl+Shift+Z", "Ctrl+Y", "Ctrl+S", "Ctrl+Shift+S", "Ctrl+O")

# Ekran uçlarının öneki: /api/ekran/<ad>/...
ONEK = "/api/ekran"

_AD = re.compile(r"[a-z][a-z0-9_]*")
_TUS = re.compile(r"[0-9]")

# Son kurulan uygulamanın ekranları (paylasilan_bolum bunlardan okur); None → keşif.
_bagli: list[Ekran] | None = None


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

    `_` ile başlayan ve `EKRAN` tanımlamayan (yardımcı) modüller atlanır. Importu hata veren modül kabuğu
    çökertmez: modül adıyla, `hazir` hata metnini dönen kapalı bir yer tutucu listelenir (yardımcı modüller
    import hatasında da yer tutucu üretmesin diye adları `_` ile başlamalı). Kayıt hataları (geçersiz ad,
    çift ad / tuş, kabuk tuşu, iki sahipli bölüm, sahipsiz `bagimli`, bağımlılık döngüsü, bölüm sahibinde
    `disa_aktar` / `ice_aktar` eksik) → ModelError.
    """
    liste: list[Ekran] = []
    for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if m.name.startswith("_"):
            continue
        try:
            modul = importlib.import_module(f"{__name__}.{m.name}")
        except Exception as e:  # noqa: BLE001 — eksik isteğe bağlı paket vb. kabuğu çökertmez
            liste.append(_yer_tutucu(m.name, e))
            continue
        if not hasattr(modul, "EKRAN"):
            continue  # yardımcı modül (ör. bir ekranın köprüsü): ekran değil
        e = modul.EKRAN
        if not isinstance(e, Ekran):
            raise ModelError(f"tezgah.ekranlar.{m.name}.EKRAN bir Ekran değil ({type(e).__name__})")
        liste.append(e)
    return dogrula(liste)


def _yer_tutucu(modul: str, hata: Exception) -> Ekran:
    """Importu başarısız ekran: kapalı sekme, ipucu hata metni. Uçsuz ama sekme listesinde kalır."""
    neden = f"{modul} yüklenemedi: {type(hata).__name__}: {hata}"
    baslik = modul.replace("_", " ").title()
    return Ekran(ad=modul, baslik=baslik, sira=1000, router=APIRouter(), hazir=lambda: neden)


def sekme_mi(e: Ekran) -> bool:
    """Sekme listesine (/api/ekranlar) girer mi: uçsuz ve tuşsuz ekran (ör. kabuk) sekme değildir."""
    return e.router is not None or e.tus is not None


def dogrula(liste: list[Ekran]) -> list[Ekran]:
    """`ekranlar()`'ın kayıt doğrulaması (verilen listeye de uygulanır); sıralı listeyi döndürür.

    Hata → ModelError.
    """
    adlar: set[str] = set()
    tuslar: dict[str, str] = {}
    sahip: dict[str, Ekran] = {}
    for e in liste:
        if not isinstance(e.ad, str) or not _AD.fullmatch(e.ad):
            raise ModelError(f"Geçersiz ekran adı {e.ad!r}: küçük harf ascii, harfle başlar [a-z][a-z0-9_]*")
        if e.ad in adlar:
            raise ModelError(f"Ekran adı iki kez kayıtlı: {e.ad!r}")
        adlar.add(e.ad)
        if e.tus is not None:
            if e.tus in KABUK_KISAYOLLARI:
                raise ModelError(f"'{e.ad}': {e.tus} kabuğa ait kısayol")
            if not _TUS.fullmatch(e.tus):
                raise ModelError(f"'{e.ad}': sekme tuşu tek rakam olmalı, {e.tus!r} verildi")
            if e.tus in tuslar:
                raise ModelError(f"Sekme tuşu {e.tus!r} iki ekranda: {tuslar[e.tus]!r} ve {e.ad!r}")
            tuslar[e.tus] = e.ad
        if e.bolum is not None:
            if e.bolum in sahip:
                raise ModelError(f"'{e.bolum}' bölümünün iki sahibi var: {sahip[e.bolum].ad!r} ve {e.ad!r}")
            if e.disa_aktar is None or e.ice_aktar is None:
                raise ModelError(f"'{e.ad}' '{e.bolum}' bölümünün sahibi; disa_aktar ve ice_aktar gerekli")
            sahip[e.bolum] = e
    for e in liste:
        for b in e.bagimli:
            if b not in sahip:
                raise ModelError(f"'{e.ad}' sahibi olmayan '{b}' bölümüne bağımlı")
    _dongu_yok(sahip)
    return sorted(liste, key=lambda e: (e.sira, e.ad))


def _dongu_yok(sahip: dict[str, Ekran]) -> None:
    """Bölüm bağımlılık çizgesinde (bölüm → bagimli bölümler) döngü → ModelError."""
    renk: dict[str, int] = {}  # 1: yolda, 2: bitti

    def gez(b: str, yol: list[str]) -> None:
        renk[b] = 1
        for c in sahip[b].bagimli:
            if renk.get(c) == 1:
                halka = " → ".join([*yol[yol.index(c) :], c]) if c in yol else f"{b} → {c}"
                raise ModelError(f"Bölüm bağımlılığında döngü: {halka}")
            if c not in renk:
                gez(c, [*yol, c])
        renk[b] = 2

    for b in sahip:
        if b not in renk:
            gez(b, [b])


def bagla(liste: list[Ekran]) -> None:
    """Kabuk: uygulamanın kurulduğu (doğrulanmış) ekranlar; `paylasilan_bolum` bunlardan okur."""
    global _bagli
    _bagli = list(liste)


def paylasilan_bolum(ad: str) -> dict:
    """`ad` bölümünün sahibi ekranın güncel `disa_aktar()` belgesi (derin kopya). Sahipsiz → KeyError."""
    for e in _bagli if _bagli is not None else ekranlar():
        if e.bolum == ad and e.disa_aktar is not None:
            return copy.deepcopy(e.disa_aktar())
    raise KeyError(f"Sahibi olmayan bölüm: {ad!r}")


def is_kaydet(ad: str, tanim: object) -> None:
    """Dinamik işi iş deposuna ekler: `tezgah.kopru.IsTanimi` → freze ("isler"), SPEC 25 torna iş tanımı →
    torna ("torna_isleri"). İş /api/isler'de görünür, #/freze?is=<ad> / #/torna?is=<ad> ile açılır.
    Aynı ad varsa yerine geçer. Geçersiz tanım → CamError, depo değişmez."""
    from tezgah import depo  # döngüsel import olmasın diye (depo → kopru → cam)

    depo.kaydet(ad, tanim)
