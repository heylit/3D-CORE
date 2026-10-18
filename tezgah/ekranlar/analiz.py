"""
SPEC 47c — Analiz ekranı: A3 kaydı (`EKRAN`) ve uçları (`/api/ekran/analiz` altında).

İnce katman: işi `_analiz_kopru` yapar; burada durum (örnek başına tanım, ağ, çözüm önbelleği) ve
hata eşlemesi (ModelError / CamError → 422, bilinmeyen örnek → 404, çözüm yokken /alan → 404) vardır.

Uçlar:
    GET    /ornekler              → {"sema", "ornekler": [ad, ...]}
    GET    /{ad}                  → Analiz
    GET    /{ad}/ag               → ikili ag
    GET    /{ad}/alan             → ikili alan (çözüm yoksa 404)
    POST   /{ad}/sec              → {"ucgen": j} | {"silindir": {"nokta", "eksen", "r"}} → Analiz
    POST   /{ad}/kosul            → {"secim", "tur", "deger"} → Analiz
    DELETE /{ad}/kosul/{kimlik}   → Analiz
    POST   /{ad}/ag               → {"h"} → Analiz (yeniden ağ)
    POST   /{ad}/coz              → Analiz (cozum dolu; aynı girdide önbellekten)
    POST   /{ad}/sonda            → {"p0", "p1", "n", "bilesen"} → ikili sonda (çözüm yoksa 422)
    POST   /{ad}/yakinsama        → Analiz (yakinsama dolu)
    GET    /{ad}/inp              → text/plain, Content-Disposition dosya adı "<ad>.inp"
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from tezgah.ekranlar import Ekran

router = APIRouter()


def _yok() -> None:
    raise NotImplementedError("SPEC 47c: uygulanmadı")


@router.get("/ornekler")
def ornekler() -> dict:
    _yok()


@router.get("/{ad}")
def analiz_al(ad: str) -> dict:
    _yok()


@router.get("/{ad}/ag")
def ag(ad: str) -> Response:
    _yok()


@router.get("/{ad}/alan")
def alan(ad: str) -> Response:
    _yok()


@router.post("/{ad}/sec")
def sec(ad: str, govde: dict) -> dict:
    _yok()


@router.post("/{ad}/kosul")
def kosul(ad: str, govde: dict) -> dict:
    _yok()


@router.delete("/{ad}/kosul/{kimlik}")
def kosul_sil(ad: str, kimlik: str) -> dict:
    _yok()


@router.post("/{ad}/ag")
def yeniden_ag(ad: str, govde: dict) -> dict:
    _yok()


@router.post("/{ad}/coz")
def coz(ad: str) -> dict:
    _yok()


@router.post("/{ad}/sonda")
def sonda(ad: str, govde: dict) -> Response:
    _yok()


@router.post("/{ad}/yakinsama")
def yakinsama(ad: str) -> dict:
    _yok()


@router.get("/{ad}/inp")
def inp(ad: str) -> Response:
    _yok()


def hazir() -> str | None:
    """gmsh ya da OCCT yoksa neden metni ("gmsh kurulu değil: pip install -e .[mesh]"), aksi None."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def sifirla() -> None:
    """Bütün örnekleri başlangıç tanımına döndürür; önbellekleri boşaltır."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


EKRAN = Ekran(ad="analiz", baslik="Analiz", sira=60, tus="6", router=router, hazir=hazir, sifirla=sifirla)
