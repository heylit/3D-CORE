"""
SPEC 62 — "Komut" ekranı (A3 kaydı): komut paleti ve simülasyon sarma uçları /api/ekran/komut/ altında.

Birinci aşama uçları (gövde ve yanıtlar sema: 1):
    POST /cozumle      {metin, secim?} → {sema, adim, aciklama}
                       KomutError → 422 {"detail", "oneriler", "okumalar"}
    GET  /sarma/{is}/{k} → application/octet-stream, SPEC 24 `kopru.sim_ikili` biçimi: k adımdan sonraki
                       yüzey, başlangıç yüzeyinden (z_ust) farklı her hücrede tek olay (olay k'si = k).
                       `kopru.sim_yuzey(veri, k)` / ön yüzde `yuzeyAt` bu yüzeyi verir. Bilinmeyen iş → 404,
                       k ∉ 0..n → 422.
İkinci aşama (SPEC 37 / 58 / 72 bekliyor): POST /uygula, POST /surukle.
Ctrl+K kabuğundur (KABUK_KISAYOLLARI); kanca gelene kadar palet "Komut" sekmesinde çalışır.
"""

from __future__ import annotations

import struct
import threading
import weakref

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from core.model import ModelError
from tezgah import SEMA, depo, kopru
from tezgah.ekranlar import Ekran
from tezgah.komut import KomutError
from tezgah.komut import cozumle as _cozumle
from tezgah.sarma import Sarici

router = APIRouter()
IKILI = "application/octet-stream"

_kilit = threading.Lock()
_SARICI: dict[int, Sarici] = {}  # id(tanim) → Sarici; tanım silinince temizlenir


class CozumleIstek(BaseModel):
    metin: str
    secim: dict | None = None


@router.post("/cozumle")
def cozumle(i: CozumleIstek):
    try:
        c = _cozumle(i.metin, i.secim)
    except KomutError as e:
        govde = {"detail": str(e), "oneriler": list(e.oneriler), "okumalar": list(e.okumalar)}
        return JSONResponse(govde, status_code=422)
    return {"sema": SEMA, "adim": c.adim, "aciklama": c.aciklama}


def _sarici(tanim: kopru.IsTanimi) -> Sarici:
    with _kilit:
        s = _SARICI.get(id(tanim))
        if s is None:
            s = _SARICI[id(tanim)] = Sarici.sonuctan(kopru._simule(tanim))
            weakref.finalize(tanim, _SARICI.pop, id(tanim), None)
        return s


def sarma_ikili(s: Sarici, k: int) -> bytes:
    """k anındaki yüzey, `kopru.sim_ikili` biçiminde (z_ust'ten farklı hücre başına bir olay)."""
    g = s._sim.zmap
    z = s.durum(k).ravel().astype(np.float32)
    degisen = np.flatnonzero(z != np.float32(g.zmax))
    ofset = np.zeros(g.nx * g.ny + 1, dtype=np.uint32)
    ofset[degisen + 1] = 1
    ofset = np.cumsum(ofset, dtype=np.uint32)
    m = len(degisen)
    return b"".join(
        [
            struct.pack("<IIII", SEMA, g.nx, g.ny, m),
            kopru._blok(np.array([g.x0, g.y0, g.dx, g.dy, g.zmax, g.zmin], dtype=np.float64)),
            kopru._blok(ofset),
            kopru._blok(np.full(m, k, dtype=np.int32)),
            kopru._blok(z[degisen]),
            kopru._blok(np.zeros(m, dtype=np.int16)),
        ]
    )


@router.get("/sarma/{is_adi}/{k}")
def sarma(is_adi: str, k: int) -> Response:
    if not depo.var_mi(is_adi):
        raise HTTPException(404, f"Bilinmeyen iş: {is_adi!r}")
    tanim = depo.al(is_adi)
    if not isinstance(tanim, kopru.IsTanimi):
        raise HTTPException(422, f"'{is_adi}' bir freze işi değil; sarma ilk sürümde yalnız freze z-haritası")
    s = _sarici(tanim)
    try:
        veri = sarma_ikili(s, k)
    except ModelError as e:
        raise HTTPException(422, str(e)) from None
    return Response(veri, media_type=IKILI)


def _sifirla() -> None:
    with _kilit:
        _SARICI.clear()


EKRAN = Ekran(ad="komut", baslik="Komut", sira=90, router=router, sifirla=_sifirla)
