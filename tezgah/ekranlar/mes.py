"""
SPEC 64 Karar 3 — "mes" ekranı (A3 kaydı): ön yüz sayfası yok (router ve tus yok, sekme olmaz); MES uçları
/api/mes/v1 altında kur kancasıyla bağlanır. sunucu.py değişmez.
"""

from __future__ import annotations

from fastapi import FastAPI

from tezgah.ekranlar import Ekran


def kur(app: FastAPI) -> None:
    """MES router'ını ve (ayar.json'da izinli köken varsa) CORS ara katmanını bağlar."""
    from tezgah.mes.uclar import router

    app.include_router(router)


EKRAN = Ekran(ad="mes", baslik="MES", sira=900, kur=kur)
