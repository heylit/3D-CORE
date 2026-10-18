"""
SPEC 64 §3 — MES uçları: /api/mes/v1/... (A3'te sayfasız "mes" ekranının kur kancasıyla bağlanır).

Hatalar: bilinmeyen kayıt 404, durum çakışması 409, şema dışı gövde 422 (pydantic), çekirdek hataları 422
(kabuğun SPEC 24 işleyicisi), depo dosyası bozuk 503, SPEC 58 yokken sure / maliyet 503. Hiçbir uç 500 vermez.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from tezgah.mes.sema import (
    MES_ID_DESENI,
    Durum,
    GonderimKaydi,
    IptalIstek,
    IsEmri,
    IsEmriDurumu,
    Maliyet,
    Saglik,
    Sure,
    Takim,
)

router = APIRouter(prefix="/api/mes/v1", tags=["mes"])

MesId = Annotated[str, Path(pattern=MES_ID_DESENI)]


@router.get("/saglik")
def saglik() -> Saglik:
    raise NotImplementedError


@router.put("/is-emirleri/{mes_id}")
def is_emri_koy(mes_id: MesId, e: IsEmri) -> IsEmriDurumu:
    """Oluşturur ya da yeni revizyon; eş-etkili. Yoldaki mes_id gövdedekiyle aynı olmalı (değilse 422)."""
    raise NotImplementedError


@router.get("/is-emirleri")
def is_emirleri(durum: Durum | None = None, sonra: Annotated[int, Query(ge=0)] = 0) -> list[IsEmriDurumu]:
    raise NotImplementedError


@router.get("/is-emirleri/{mes_id}")
def is_emri(mes_id: MesId) -> IsEmriDurumu:
    raise NotImplementedError


@router.post("/is-emirleri/{mes_id}/iptal")
def is_emri_iptal(mes_id: MesId, istek: IptalIstek) -> IsEmriDurumu:
    raise NotImplementedError


@router.get("/is-emirleri/{mes_id}/program", response_class=PlainTextResponse)
def program(mes_id: MesId) -> PlainTextResponse:
    """Dondurulmuş NC programı (text/plain), başlık X-Sha256; yalnız hazir / gonderildi, değilse 409."""
    raise NotImplementedError


@router.get("/is-emirleri/{mes_id}/takimlar")
def takimlar(mes_id: MesId) -> list[Takim]:
    raise NotImplementedError


@router.get("/is-emirleri/{mes_id}/sure")
def sure(mes_id: MesId) -> Sure:
    raise NotImplementedError


@router.get("/is-emirleri/{mes_id}/maliyet")
def maliyet(mes_id: MesId) -> Maliyet:
    raise NotImplementedError


@router.get("/is-emirleri/{mes_id}/is-foyu.html", response_class=HTMLResponse)
def is_foyu(mes_id: MesId) -> HTMLResponse:
    raise NotImplementedError


@router.get("/gonderimler")
def gonderimler(sonra: Annotated[int, Query(ge=0)] = 0) -> list[GonderimKaydi]:
    raise NotImplementedError
