"""
SPEC 25 — Torna ve montaj uçları. `sunucu.uygulama` bunları SPEC 24 uçlarından önce ekler, böylece
`/api/is/kademeli_mil` torna köprüsünden gelir.

Uçlar:
    GET  /api/is/kademeli_mil[/noktalar|/sim]   → torna `Is` / ikili diziler (tezgah.torna)
    POST /api/is/kademeli_mil/parametre         gövde {"islem", "anahtar", "deger"} (müfettiş, SPEC 24 biçimi)
                                                → {"sema", "is", "sure_farki"}
    GET  /api/montajlar                         → {"sema": 1, "montajlar": [ad, ...]}
    GET  /api/montaj/{ad}                       → Montaj JSON
    GET  /api/montaj/{ad}/ag/{parca}            → ikili parça ağı
    GET  /api/montaj/{ad}/ag/girisim/{i}        → ikili kesişim ağı
    POST /api/montaj/{ad}/parametre             gövde {"is", "anahtar", "deger"}
                                                → {"montaj", "is", "sure_farki"}
    GET  /api/montaj/{ad}/oneri?is=&anahtar=&cift=a,b → {"deger", "hacim"} | {"deger": None, "neden"}
    POST /api/sifirla                           → örnekleri başlangıç değerlerine döndürür
Çekirdek hataları (CamError, AssyError, GeometryError, ModelError) → 422; bilinmeyen ad → 404.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from assy.model import AssyError
from cam.model import CamError
from core.model import ModelError
from geometry.part import GeometryError
from tezgah import SEMA, torna
from tezgah.iplik import Depo
from tezgah.montaj import girisim_agi, parca_agi

IKILI = "application/octet-stream"
CEKIRDEK_HATALARI = (CamError, AssyError, GeometryError, ModelError)
TORNA_IS = "kademeli_mil"


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


def ekle(app: FastAPI, depo: Depo | None = None) -> Depo:
    """SPEC 25 uçlarını `app`'e ekler; kullanılan parametre deposunu döndürür."""
    depo = depo if depo is not None else Depo()
    kilit = threading.Lock()  # depo (parametreler + önbellek) tek tek

    def calistir(f: Callable[[], object], bilinmeyen: tuple[type[Exception], ...] = (KeyError,)):
        """Çekirdek hataları → 422 (gövde hata metni); bilinmeyen ad / parça / indis → 404."""
        with kilit:
            try:
                return f()
            except CEKIRDEK_HATALARI as e:
                raise HTTPException(422, str(e)) from None
            except bilinmeyen as e:
                raise HTTPException(404, _metin(e)) from None

    @app.get("/api/is/kademeli_mil")
    def torna_is() -> dict:
        return calistir(lambda: depo.is_json(TORNA_IS))

    @app.get("/api/is/kademeli_mil/noktalar")
    def torna_noktalar() -> Response:
        return Response(calistir(lambda: torna.noktalar_ikili(depo.torna_isi(TORNA_IS))), media_type=IKILI)

    @app.get("/api/is/kademeli_mil/sim")
    def torna_sim() -> Response:
        return Response(calistir(lambda: torna.sim_ikili(depo.torna_isi(TORNA_IS))), media_type=IKILI)

    @app.post("/api/is/kademeli_mil/parametre")
    def torna_parametre(p: IslemParametre) -> dict:
        Y = calistir(lambda: depo.islem_ayarla(TORNA_IS, p.islem, p.anahtar, p.deger))
        return {"sema": SEMA, **Y}

    @app.get("/api/montajlar")
    def montajlar() -> dict:
        from tezgah.ornekler_25 import MONTAJLAR

        return {"sema": SEMA, "montajlar": list(MONTAJLAR)}

    @app.get("/api/montaj/{ad}")
    def montaj(ad: str) -> dict:
        return calistir(lambda: depo.montaj_json(ad))

    @app.get("/api/montaj/{ad}/ag/girisim/{i}")
    def girisim_agi_uc(ad: str, i: int) -> Response:
        ag = calistir(lambda: girisim_agi(depo.montaj(ad), i), (KeyError, IndexError))
        return Response(ag, media_type=IKILI)

    @app.get("/api/montaj/{ad}/ag/{parca}")
    def parca_agi_uc(ad: str, parca: str) -> Response:
        return Response(calistir(lambda: parca_agi(depo.montaj(ad), parca)), media_type=IKILI)

    @app.post("/api/montaj/{ad}/parametre")
    def parametre(ad: str, p: BagParametre) -> dict:
        return calistir(lambda: depo.ayarla(ad, p.is_ad, p.anahtar, p.deger))

    @app.get("/api/montaj/{ad}/oneri")
    def oneri(ad: str, anahtar: str, cift: str, is_ad: str = Query(alias="is")) -> dict:
        parcalar = tuple(cift.split(","))
        if len(parcalar) != 2 or not all(parcalar):
            raise HTTPException(422, f"cift 'a,b' biçiminde iki yaprak yolu olmalı: {cift!r}")
        o = calistir(lambda: depo.oneri(ad, is_ad, anahtar, parcalar))
        if o.deger is None:
            return {"deger": None, "neden": o.neden}
        return {"deger": o.deger, "hacim": o.hacim}

    @app.post("/api/sifirla")
    def sifirla() -> dict:
        with kilit:
            depo.sifirla()
        return {"sema": SEMA}

    return depo
