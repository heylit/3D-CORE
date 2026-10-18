"""
SPEC 64 Karar 3 — "mes" ekranı (A3 kaydı): ön yüz sayfası yok (router ve tus yok, sekme olmaz); MES uçları
/api/mes/v1 altında kur kancasıyla bağlanır. sunucu.py değişmez.

Hata eşlemesi (yalnız MES hataları): MesYok → 404, MesCakisma → 409, MesBozuk / MesYokBagimlilik → 503.
"""

from __future__ import annotations

import warnings

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tezgah.ekranlar import Ekran

KODLAR = (("MesYok", 404), ("MesCakisma", 409), ("MesBozuk", 503), ("MesYokBagimlilik", 503))


def kur(app: FastAPI) -> None:
    """MES router'ını, hata eşlemesini ve (ayar.json'da izinli köken varsa) CORS ara katmanını bağlar."""
    from fastapi.middleware.cors import CORSMiddleware

    from tezgah.mes import depo
    from tezgah.mes.uclar import router

    for ad, kod in KODLAR:

        async def isleyici(istek: Request, e: Exception, kod: int = kod) -> JSONResponse:
            return JSONResponse({"detail": str(e)}, status_code=kod)

        app.add_exception_handler(getattr(depo, ad), isleyici)
    app.include_router(router)
    try:
        kokenler = depo.izinli_kokenler(depo.AYAR_YOLU)
    except depo.MesBozuk as e:
        warnings.warn(f"{e}; CORS kapalı", stacklevel=1)
        kokenler = []
    if kokenler:
        app.add_middleware(CORSMiddleware, allow_origins=kokenler, allow_methods=["GET", "PUT", "POST"])


EKRAN = Ekran(ad="mes", baslik="MES", sira=900, kur=kur)
