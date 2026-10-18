"""
SPEC 25 — Torna ve montaj uçları (A3 ekran kaydı: specs/24a-ekran-kaydi.md). Router'lar öneksiz yazılır;
`tezgah/ekranlar/torna.py` ve `montaj.py` bunları `EKRAN.router` olarak verir, kabuk
`/api/ekran/<ad>` altına bağlar.
İki ekranın parametreleri tek yerdedir: `DEPO` (tezgah.iplik.Depo); ekranlar birbirini import etmez.

Torna (/api/ekran/torna): `ad` örnek torna işi ya da `kaydet` ile eklenen dinamik iş (A3 is_kaydet)
    GET  /is/{ad}[/noktalar|/sim]               → torna `Is` / ikili diziler (tezgah.torna)
    POST /is/{ad}/parametre                     gövde {"islem", "anahtar", "deger"} (müfettiş, SPEC 24 biçimi)
                                                → {"sema", "is", "sure_farki"}
Montaj (/api/ekran/montaj):
    GET  /montajlar                             → {"sema": 1, "montajlar": [ad, ...]}
    GET  /{ad}                                  → Montaj JSON
    GET  /{ad}/ag/{parca}                       → ikili parça ağı
    GET  /{ad}/ag/girisim/{i}                   → ikili kesişim ağı
    POST /{ad}/parametre                        gövde {"is", "anahtar", "deger"}
                                                → {"montaj", "is", "sure_farki"}
    GET  /{ad}/oneri?is=&anahtar=&cift=a,b      → {"deger", "hacim"} | {"deger": None, "neden"}
Çekirdek hataları (CamError, AssyError, GeometryError, ModelError) → 422 (kabuğun işleyicisi);
bilinmeyen torna işi, montaj, parça ya da girişim indisi → 404 (burada; kabuk KeyError'ı 422 yapar).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from cam.model import CamError
from tezgah import SEMA, torna
from tezgah.iplik import Depo
from tezgah.montaj import girisim_agi, parca_agi

IKILI = "application/octet-stream"

DEPO = Depo()  # süreç başına tek: torna ekranının "torna_isleri" bölümü; montaj bağları bunu yazar
KILIT = threading.RLock()  # depo (parametreler + önbellek) tek tek
DINAMIK: dict[
    str, torna.TornaIsi
] = {}  # is_kaydet ile eklenen torna işleri (ör. otomatik plan); proje dosyasına girmez


class IslemParametre(BaseModel):
    islem: int
    anahtar: str
    deger: float


class BagParametre(BaseModel):
    is_ad: str = Field(alias="is")
    anahtar: str
    deger: float


def _metin(e: Exception) -> str:
    return str(e.args[0]) if e.args else str(e)


def _calistir(f: Callable[[], object], bilinmeyen: tuple[type[Exception], ...] = (KeyError,)):
    """Kilit altında çalıştırır; bilinmeyen ad / parça / indis → 404. Çekirdek hataları kabuğa (422) gider."""
    with KILIT:
        try:
            return f()
        except bilinmeyen as e:
            raise HTTPException(404, _metin(e)) from None


def _tanim(depo: Depo, ad: str) -> torna.TornaIsi:
    """Örnek torna işi (parametreli, `depo`) ya da `kaydet` ile eklenmiş dinamik torna işi.

    Hiçbiri değilse KeyError (→ 404).
    """
    from tezgah.ornekler_25 import TORNA_ISLERI

    with KILIT:
        if ad in DINAMIK:
            return DINAMIK[ad]
    if ad in TORNA_ISLERI:
        return depo.torna_isi(ad)
    raise KeyError(f"Bilinmeyen torna işi: {ad!r}")


def kaydet(ad: str, tanim: torna.TornaIsi) -> None:
    """Dinamik torna işi (A3 `is_kaydet` → kabuğun `depo.kaydedici_ekle` kancası). Aynı ad varsa yerine geçer.

    Geçersiz tanım → CamError, depo değişmez. Örnek işin adı kullanılamaz (parametreleri depodadır).
    """
    from tezgah.ornekler_25 import TORNA_ISLERI

    if not isinstance(tanim, torna.TornaIsi):
        raise CamError(f"'{ad}' için torna iş tanımı bekleniyordu, {type(tanim).__name__} verildi")
    if not ad:
        raise CamError("İş adı boş olamaz")
    if ad in TORNA_ISLERI:
        raise CamError(f"'{ad}' örnek torna işinin adı; dinamik iş başka ad almalı")
    if not tanim.islemler:
        raise CamError(f"'{ad}' işinde işlem yok")
    torna.hareketler(tanim)  # op doğrulaması (CamError)
    with KILIT:
        DINAMIK.pop(ad, None)  # yeniden eklenen ad listenin sonuna gider
        DINAMIK[ad] = tanim


def adlar() -> list[str]:
    """Torna işleri: örnekler, ardından dinamik işler (ekleniş sırası)."""
    from tezgah.ornekler_25 import TORNA_ISLERI

    with KILIT:
        return list(TORNA_ISLERI) + list(DINAMIK)


def _is_json(depo: Depo, ad: str) -> dict:
    with KILIT:
        dinamik = ad in DINAMIK
    return torna.is_json(_tanim(depo, ad)) if dinamik else depo.is_json(ad)


def torna_router(depo: Depo = DEPO) -> APIRouter:
    r = APIRouter()

    @r.get("/is/{ad}")
    def torna_is(ad: str) -> dict:
        return _calistir(lambda: _is_json(depo, ad))

    @r.get("/is/{ad}/noktalar")
    def torna_noktalar(ad: str) -> Response:
        return Response(_calistir(lambda: torna.noktalar_ikili(_tanim(depo, ad))), media_type=IKILI)

    @r.get("/is/{ad}/sim")
    def torna_sim(ad: str) -> Response:
        return Response(_calistir(lambda: torna.sim_ikili(_tanim(depo, ad))), media_type=IKILI)

    @r.post("/is/{ad}/parametre")
    def torna_parametre(ad: str, p: IslemParametre) -> dict:
        Y = _calistir(lambda: depo.islem_ayarla(ad, p.islem, p.anahtar, p.deger))
        return {"sema": SEMA, **Y}

    return r


def montaj_router(depo: Depo = DEPO) -> APIRouter:
    r = APIRouter()

    @r.get("/montajlar")
    def montajlar() -> dict:
        from tezgah.ornekler_25 import MONTAJLAR

        return {"sema": SEMA, "montajlar": list(MONTAJLAR)}

    @r.get("/{ad}")
    def montaj(ad: str) -> dict:
        return _calistir(lambda: depo.montaj_json(ad))

    @r.get("/{ad}/ag/girisim/{i}")
    def girisim_agi_uc(ad: str, i: int) -> Response:
        ag = _calistir(lambda: girisim_agi(depo.montaj(ad), i), (KeyError, IndexError))
        return Response(ag, media_type=IKILI)

    @r.get("/{ad}/ag/{parca}")
    def parca_agi_uc(ad: str, parca: str) -> Response:
        return Response(_calistir(lambda: parca_agi(depo.montaj(ad), parca)), media_type=IKILI)

    @r.post("/{ad}/parametre")
    def parametre(ad: str, p: BagParametre) -> dict:
        return _calistir(lambda: depo.ayarla(ad, p.is_ad, p.anahtar, p.deger))

    @r.get("/{ad}/oneri")
    def oneri(ad: str, anahtar: str, cift: str, is_ad: str = Query(alias="is")) -> dict:
        parcalar = tuple(cift.split(","))
        if len(parcalar) != 2 or not all(parcalar):
            raise HTTPException(422, f"cift 'a,b' biçiminde iki yaprak yolu olmalı: {cift!r}")
        o = _calistir(lambda: depo.oneri(ad, is_ad, anahtar, parcalar))
        if o.deger is None:
            return {"deger": None, "neden": o.neden}
        return {"deger": o.deger, "hacim": o.hacim}

    return r


def sifirla(depo: Depo = DEPO) -> None:
    """POST /api/sifirla (kabuk): örnek parametreleri başlangıç değerlerine, dinamik torna işleri silinir."""
    with KILIT:
        depo.sifirla()
        DINAMIK.clear()
