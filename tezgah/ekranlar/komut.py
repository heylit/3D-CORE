"""
SPEC 62 — "Komut" ekranı (A3 kaydı): komut paleti ve simülasyon sarma uçları /api/ekran/komut/ altında.

Birinci aşama uçları (gövde ve yanıtlar sema: 1):
    POST /cozumle      {metin, secim?} → {sema, adim, aciklama}
                       KomutError → 422 {"detail": {"hata", "oneriler", "okumalar"}}
    GET  /sarma/{is}/{k} → application/octet-stream: uint32 sema, nx, ny, k; float64[6] x0, y0, dx, dy,
                       zmax, zmin; float32[ny·nx] k adımdan sonraki yüzey (tezgah.sarma.Sarici)
İkinci aşama (SPEC 37 / 58 / 72 bekliyor): POST /uygula, POST /surukle.
Ctrl+K kabuğundur (KABUK_KISAYOLLARI); kanca gelene kadar palet "Komut" sekmesinde çalışır.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from tezgah.ekranlar import Ekran

router = APIRouter()
IKILI = "application/octet-stream"


class CozumleIstek(BaseModel):
    metin: str
    secim: dict | None = None


@router.post("/cozumle")
def cozumle(i: CozumleIstek) -> dict:
    raise NotImplementedError("SPEC 62: /cozumle")


@router.get("/sarma/{is_adi}/{k}")
def sarma(is_adi: str, k: int):
    raise NotImplementedError("SPEC 62: /sarma")


EKRAN = Ekran(ad="komut", baslik="Komut", sira=90, router=router)
