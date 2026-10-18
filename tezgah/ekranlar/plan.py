"""
SPEC 47a — Plan ekranı: A3 `Ekran` kaydı ve `/api/ekran/plan` uçları (ince katman; hesap _plan_kopru'da).

Uçlar (öneksiz; kabuk /api/ekran/plan altına bağlar):
    GET  /ornekler            → {"sema": 1, "ornekler": [{ad, tur, aciklama, hazir, neden}]}
    GET  /{ad}                → Plan
    GET  /{ad}/ag             → ikili parça ağı; parça yoksa 404
    POST /{ad}/ne_olurdu      gövde {takim_kapat?, takim_ac?, secenek?} → {"plan": Plan, "fark": Fark}
    POST /{ad}/dogrula        → Plan (dogrulama dolu)
    POST /{ad}/ac             gövde {bag} → {"adres": "#/freze?is=..."}
Bilinmeyen örnek → 404; çekirdek hataları kabuğun ortak işleyicisiyle 422.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from tezgah.ekranlar import Ekran

router = APIRouter()


class NeOlurdu(BaseModel):
    takim_kapat: list[int] = []
    takim_ac: list[int] = []
    secenek: dict[str, float | bool | None] = {}


class Ac(BaseModel):
    bag: int


@router.get("/ornekler")
def ornekler() -> dict:
    raise NotImplementedError("SPEC 47a: GET /ornekler")


@router.get("/{ad}")
def plan(ad: str) -> dict:
    raise NotImplementedError("SPEC 47a: GET /{ad}")


@router.get("/{ad}/ag")
def ag(ad: str):
    raise NotImplementedError("SPEC 47a: GET /{ad}/ag")


@router.post("/{ad}/ne_olurdu")
def ne_olurdu(ad: str, g: NeOlurdu) -> dict:
    raise NotImplementedError("SPEC 47a: POST /{ad}/ne_olurdu")


@router.post("/{ad}/dogrula")
def dogrula(ad: str) -> dict:
    raise NotImplementedError("SPEC 47a: POST /{ad}/dogrula")


@router.post("/{ad}/ac")
def ac(ad: str, g: Ac) -> dict:
    raise NotImplementedError("SPEC 47a: POST /{ad}/ac")


def _hazir() -> str | None:
    """SPEC 29 kodu yoksa neden metni."""
    raise NotImplementedError("SPEC 47a: hazir")


def _sifirla() -> None:
    """Bütün örnek oturumlarını başlangıca döndürür (kapalı takım yok, seçenekler örnek varsayılanı)."""
    raise NotImplementedError("SPEC 47a: sifirla")


EKRAN = Ekran(
    ad="plan",
    baslik="Plan",
    sira=40,
    tus="4",
    router=router,
    hazir=_hazir,
    sifirla=_sifirla,
)
