"""
SPEC 62 — "Komut" ekranı (A3 kaydı): komut paleti ve simülasyon sarma uçları /api/ekran/komut/ altında.

Birinci aşama uçları (gövde ve yanıtlar sema: 1):
    POST /cozumle      {metin, secim?} → {sema, adim, aciklama}
                       KomutError → 422 {"detail", "oneriler", "okumalar"}
    GET  /sarma/{is}/{k} → application/octet-stream, SPEC 24 `kopru.sim_ikili` biçimi: k adımdan sonraki
                       yüzey, başlangıç yüzeyinden (z_ust) farklı her hücrede tek olay (olay k'si = k).
                       `kopru.sim_yuzey(veri, k)` / ön yüzde `yuzeyAt` bu yüzeyi verir. Bilinmeyen iş → 404,
                       k ∉ 0..n → 422.
İkinci aşama:
    POST /uygula   {model_adi, adim, secim?} → {sema, model, fark}
                   `adim` cozumle'nin yerleşimsiz adımı; `komut.yerlestir(adim, secim, model)` ile model
                   ekranının ("model" bölümü) modeline eklenir, A3 `ice_aktar` ile yazılır. Geri al: SPEC 37
                   kabuğunun ara katmanı isteği yakalar (etiket = X-Tezgah-Etiket başlığı).
                   fark = `fark.fark_json(plan_farki(eski, yeni, süreler))`. model_adi güncel modelin adı
                   değilse 404; KomutError → 422 (cozumle gibi); model kurulamazsa 422, model değişmez.
    POST /surukle  {model_adi, adim, olcu, deger, sira} → {sema, fark, sira}
                   Önizleme, modeli değiştirmez. `adim` adım kimliği; `olcu` o adımdaki ölçü yolu ("mesafe",
                   "d", "derinlik", "olculer/<kısıt sırası>"); `deger` sayı ya da ifade. Bırakınca ön yüz
                   modeli /api/ekran/model/ PUT ile yazar (geri al oradan). Bilinmeyen adım / ölçü → 422.
    Plan ve süre: `artimli.Onbellek` (ekran başına bir), stok = parça kutusu + STOK_PAYI (alt 0),
    kütüphane KUTUPHANE, malzeme MALZEME, süre `fark.islem_sureleri` (72'ye kadar), maliyet yok (58).
Ctrl+K kabuğundur (KABUK_KISAYOLLARI); kancayla palet her ekranda açılır.
"""

from __future__ import annotations

import struct
import threading
import weakref
from pathlib import Path

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
KUTUPHANE = Path(__file__).resolve().parents[2] / "examples" / "takim_kutuphanesi.json"
MALZEME = "AlMg3"
STOK_PAYI = 1.0  # mm, XY ve üst stok payı (alt 0)

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


class UygulaIstek(BaseModel):
    model_adi: str
    adim: dict
    secim: dict | None = None


class SurukleIstek(BaseModel):
    model_adi: str
    adim: str
    olcu: str
    deger: float | str
    sira: int


@router.post("/uygula")
def uygula(i: UygulaIstek) -> dict:
    raise NotImplementedError("SPEC 62: /uygula")


@router.post("/surukle")
def surukle(i: SurukleIstek) -> dict:
    raise NotImplementedError("SPEC 62: /surukle")


def _sifirla() -> None:
    with _kilit:
        _SARICI.clear()


EKRAN = Ekran(ad="komut", baslik="Komut", sira=90, router=router, sifirla=_sifirla)
