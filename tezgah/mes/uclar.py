"""
SPEC 64 §3 — MES uçları: /api/mes/v1/... (A3'te sayfasız "mes" ekranının kur kancasıyla bağlanır).

Hatalar: bilinmeyen kayıt 404, durum çakışması 409, şema dışı gövde 422 (pydantic), çekirdek hataları 422
(kabuğun SPEC 24 işleyicisi), depo dosyası bozuk 503, SPEC 58 yokken sure / maliyet 503. Hiçbir uç 500 vermez.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
from pathlib import Path as Yol
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from tezgah.mes import depo
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
ANLIK_GORUNTU = Yol(__file__).resolve().parents[2] / "docs" / "mes-openapi-v1.json"


def _guncel() -> depo.MesDepo:
    """Depo dosyasının güncel hâli; gönderim kaydı eşitlenmiş, hazir kayıtlar tazelenmiş."""
    d = depo.yukle(depo.DEPO_YOLU)
    depo.esitle(d, depo.GONDERIM_KAYDI)
    for mes_id in list(d.kayitlar):
        depo.tazele(d, mes_id)
    return d


def _surum() -> str:
    try:
        return importlib.metadata.version("3d-core")
    except importlib.metadata.PackageNotFoundError:
        return "kurulmamis"


@router.get("/saglik")
def saglik() -> Saglik:
    try:
        ozet = hashlib.sha256(ANLIK_GORUNTU.read_bytes()).hexdigest()
    except OSError as e:
        raise depo.MesBozuk(f"Şema anlık görüntüsü okunamıyor: {ANLIK_GORUNTU} ({e})") from None
    return Saglik(tezgah_surum=_surum(), sema_ozeti=ozet)


@router.put("/is-emirleri/{mes_id}")
def is_emri_koy(mes_id: MesId, e: IsEmri) -> IsEmriDurumu:
    """Oluşturur ya da yeni revizyon; eş-etkili. Yoldaki mes_id gövdedekiyle aynı olmalı (değilse 422)."""
    if e.mes_id != mes_id:
        raise HTTPException(422, f"Yoldaki mes_id {mes_id!r} gövdedekiyle ({e.mes_id!r}) aynı değil")
    with depo.kilit:
        return depo.koy(_guncel(), e)


@router.get("/is-emirleri")
def is_emirleri(durum: Durum | None = None, sonra: Annotated[int, Query(ge=0)] = 0) -> list[IsEmriDurumu]:
    with depo.kilit:
        L = depo.degisenler(_guncel(), sonra)
    return [k for k in L if durum is None or k.durum == durum]


@router.get("/is-emirleri/{mes_id}")
def is_emri(mes_id: MesId) -> IsEmriDurumu:
    with depo.kilit:
        return depo.al(_guncel(), mes_id)


@router.post("/is-emirleri/{mes_id}/iptal")
def is_emri_iptal(mes_id: MesId, istek: IptalIstek) -> IsEmriDurumu:
    with depo.kilit:
        return depo.iptal(_guncel(), mes_id, istek.gerekce)


@router.get("/is-emirleri/{mes_id}/program", response_class=PlainTextResponse)
def program(mes_id: MesId) -> PlainTextResponse:
    """Dondurulmuş NC programı (text/plain), başlık X-Sha256; yalnız hazir / gonderildi, değilse 409."""
    with depo.kilit:
        metin = depo.program_metni(_guncel(), mes_id)
    ozet = hashlib.sha256(metin.encode("utf-8")).hexdigest()
    return PlainTextResponse(metin, headers={"X-Sha256": ozet})


@router.get("/is-emirleri/{mes_id}/takimlar")
def takimlar(mes_id: MesId) -> list[Takim]:
    with depo.kilit:
        return depo.takim_listesi(_guncel(), mes_id)


def _spec58(mes_id: str) -> None:
    with depo.kilit:
        depo.al(_guncel(), mes_id)  # bilinmeyen → 404 önce
    if importlib.util.find_spec("atolye.maliyet") is None:
        raise depo.MesYokBagimlilik("Süre ve maliyet SPEC 58'e (atolye.maliyet) dayanır; bu kurulumda yok")
    raise depo.MesYokBagimlilik("SPEC 58 bağlantısı bu sürümde henüz yok (durum/64-mes-baglantisi.md)")


@router.get("/is-emirleri/{mes_id}/sure")
def sure(mes_id: MesId) -> Sure:
    _spec58(mes_id)


@router.get("/is-emirleri/{mes_id}/maliyet")
def maliyet(mes_id: MesId) -> Maliyet:
    _spec58(mes_id)


@router.get("/is-emirleri/{mes_id}/is-foyu.html", response_class=HTMLResponse)
def is_foyu(mes_id: MesId) -> HTMLResponse:
    with depo.kilit:
        return HTMLResponse(depo.foy_html(_guncel(), mes_id))


@router.get("/gonderimler")
def gonderimler(sonra: Annotated[int, Query(ge=0)] = 0) -> list[GonderimKaydi]:
    with depo.kilit:
        d = _guncel()
    kayitlar = depo.gonderim_kayitlari(depo.GONDERIM_KAYDI)
    sonuc = []
    for sira, r in enumerate(kayitlar, start=1):
        if sira > sonra:
            mes_id = depo.mes_id_bul(d, depo._program_ozeti(r))
            sonuc.append(GonderimKaydi.model_validate({**r, "sira": sira, "mes_id": mes_id}))
    return sonuc
