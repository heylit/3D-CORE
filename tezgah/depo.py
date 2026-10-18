"""
A3 — kabuğun iş deposu (süreç başına tek): SPEC 24'ün örnek işleri ve `is_kaydet` ile eklenen dinamik işler.

SPEC 24 uçları (`/api/isler`, `/api/is/{ad}/...`) bu depoyu okur ve yazar. Örnek işlerin parametre durumu
freze ekranının `"isler"` bölümüdür (`tezgah/ekranlar/freze.py`). Dinamik işler (ör. otomatik CAM planından)
proje dosyasına girmez; `sifirla()` onları siler.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from cam.model import CamError
from tezgah import kopru
from tezgah.isler import ORNEK_ISLER, ornek_is, parametre_uygula

_kilit = threading.RLock()
_ornek: dict[str, kopru.IsTanimi] = {}  # parametresi değişmiş ya da istenmiş örnek işler
_dinamik: dict[str, kopru.IsTanimi] = {}


@dataclass(frozen=True)
class Kaydedici:
    """Başka bir ekranın iş türü için `is_kaydet` yönlendirmesi (ör. SPEC 25: TornaIsi → torna).

    kaydet: (ad, tanim) → işi o ekranın deposuna ekler; geçersiz tanım → CamError, depo değişmez.
    adlar : o ekranın /api/isler'de listelenecek işleri (örnekler + dinamikler), sıralı.
    """

    kaydet: Callable[[str, object], None]
    adlar: Callable[[], list[str]] | None = None


_kaydediciler: dict[type, Kaydedici] = {}


def kaydedici_ekle(
    tur: type, kaydet: Callable[[str, object], None], adlar: Callable[[], list[str]] | None = None
) -> None:
    """`tur` örneklerini `is_kaydet`'te `kaydet`'e yönlendirir (ekran modülü importta bir kez çağırır).

    `tezgah.kopru.IsTanimi` freze'nindir ve yönlendirilemez; aynı tür ikinci kez → CamError.
    """
    if issubclass(tur, kopru.IsTanimi):
        raise CamError("IsTanimi freze deposunundur; yönlendirilemez")
    with _kilit:
        if tur in _kaydediciler and _kaydediciler[tur].kaydet is not kaydet:
            raise CamError(f"{tur.__name__} için iş kaydedici zaten var")
        _kaydediciler[tur] = Kaydedici(kaydet, adlar)


def adlar() -> list[str]:
    """Örnek işler (sabit sıra), ardından dinamik işler (ekleniş sırası)."""
    with _kilit:
        L = list(ORNEK_ISLER) + [a for a in _dinamik if a not in ORNEK_ISLER]
        diger = [k.adlar for k in _kaydediciler.values() if k.adlar is not None]
    for f in diger:  # diğer ekranların işleri (ör. torna), freze işlerinden sonra
        L += [a for a in f() if a not in L]
    return L


def var_mi(ad: str) -> bool:
    with _kilit:
        return ad in _dinamik or ad in ORNEK_ISLER


def al(ad: str) -> kopru.IsTanimi:
    """İşi döndürür; aynı adlı dinamik iş örneğin yerine geçer. Bilinmeyen iş → KeyError."""
    with _kilit:
        if ad in _dinamik:
            return _dinamik[ad]
        if ad not in ORNEK_ISLER:
            raise KeyError(f"Bilinmeyen iş: {ad!r}")
        if ad not in _ornek:
            _ornek[ad] = ornek_is(ad)
        return _ornek[ad]


def parametre(ad: str, islem: int, anahtar: str, deger: float) -> tuple[kopru.IsTanimi, kopru.IsTanimi]:
    """Örnek işin bir parametresini değiştirir; (eski, yeni). Hata olursa depo değişmez.

    Dinamik işlerin parametresi yoktur (çekirdek çıktısıdır) → KeyError.
    """
    with _kilit:
        if ad in _dinamik:
            raise KeyError(f"'{ad}' dinamik bir iş; parametreleri buradan değiştirilemez")
        eski = al(ad)
        yeni = parametre_uygula(eski, islem, anahtar, deger)
        kopru.is_json(yeni)  # yeni iş hesaplanabilir mi (hata → depo değişmez)
        _ornek[ad] = yeni
        return eski, yeni


def kaydet(ad: str, tanim: object) -> None:
    """Dinamik iş ekler (aynı ad varsa yerine geçer). Geçersiz tanım → CamError, depo değişmez.

    IsTanimi dışındaki türler `kaydedici_ekle` ile kayıtlı ekrana gider (ör. TornaIsi → torna).
    """
    if not isinstance(tanim, kopru.IsTanimi):
        with _kilit:
            k = next((k for t, k in _kaydediciler.items() if isinstance(tanim, t)), None)
        if k is not None:
            k.kaydet(ad, tanim)
            return
        raise CamError(f"'{ad}' için iş tanımı bekleniyordu, {type(tanim).__name__} verildi")
    if not ad:
        raise CamError("İş adı boş olamaz")
    if not tanim.islemler:
        raise CamError(f"'{ad}' işinde işlem yok")
    kopru.hareketler(tanim)  # op doğrulaması ve G-code satır eşlemesi (CamError)
    with _kilit:
        _dinamik.pop(ad, None)  # yeniden eklenen ad listenin sonuna gider
        _dinamik[ad] = tanim


def ornek_parametreleri() -> dict[str, list[dict[str, float]]]:
    """Her örnek işin işlem başına güncel parametreleri."""
    with _kilit:
        return {ad: [dict(i.parametreler) for i in al_ornek(ad).islemler] for ad in ORNEK_ISLER}


def al_ornek(ad: str) -> kopru.IsTanimi:
    with _kilit:
        if ad not in _ornek:
            _ornek[ad] = ornek_is(ad)
        return _ornek[ad]


def ornekleri_ayarla(P: dict[str, list[dict[str, float]]]) -> None:
    """Örnek işleri verilen parametrelerle yeniden kurar. Önce hepsi kurulur; hata → depo değişmez."""
    yeni = {ad: ornek_is(ad, dict(enumerate(p))) for ad, p in P.items()}
    for t in yeni.values():
        kopru.hareketler(t)
    with _kilit:
        _ornek.clear()
        _ornek.update(yeni)


def ornekleri_sifirla() -> None:
    """Örnek işler varsayılan parametrelere döner (dinamik işler kalır)."""
    with _kilit:
        _ornek.clear()


def sifirla() -> None:
    """Depo varsayılana: örnek işler varsayılan parametrelerle, dinamik işler silinir."""
    with _kilit:
        _ornek.clear()
        _dinamik.clear()
