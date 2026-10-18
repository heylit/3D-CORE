"""
SPEC 25 — Torna ve montaj uçları. `sunucu.uygulama` bunları SPEC 24 uçlarından önce ekler, böylece
`/api/is/kademeli_mil` torna köprüsünden gelir.

Uçlar:
    GET  /api/is/kademeli_mil[/noktalar|/sim]   → torna `Is` / ikili diziler (tezgah.torna)
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

from fastapi import FastAPI, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from tezgah.iplik import Depo

IKILI = "application/octet-stream"


class BagParametre(BaseModel):
    is_ad: str = Field(alias="is")
    anahtar: str
    deger: float


def ekle(app: FastAPI, depo: Depo | None = None) -> Depo:
    """SPEC 25 uçlarını `app`'e ekler; kullanılan parametre deposunu döndürür."""
    depo = depo if depo is not None else Depo()

    @app.get("/api/is/kademeli_mil")
    def torna_is() -> dict:
        raise NotImplementedError("SPEC 25: GET /api/is/kademeli_mil")

    @app.get("/api/is/kademeli_mil/noktalar")
    def torna_noktalar() -> Response:
        raise NotImplementedError("SPEC 25: GET /api/is/kademeli_mil/noktalar")

    @app.get("/api/is/kademeli_mil/sim")
    def torna_sim() -> Response:
        raise NotImplementedError("SPEC 25: GET /api/is/kademeli_mil/sim")

    @app.get("/api/montajlar")
    def montajlar() -> dict:
        raise NotImplementedError("SPEC 25: GET /api/montajlar")

    @app.get("/api/montaj/{ad}")
    def montaj(ad: str) -> dict:
        raise NotImplementedError("SPEC 25: GET /api/montaj/{ad}")

    @app.get("/api/montaj/{ad}/ag/girisim/{i}")
    def girisim_agi(ad: str, i: int) -> Response:
        raise NotImplementedError("SPEC 25: GET /api/montaj/{ad}/ag/girisim/{i}")

    @app.get("/api/montaj/{ad}/ag/{parca}")
    def parca_agi(ad: str, parca: str) -> Response:
        raise NotImplementedError("SPEC 25: GET /api/montaj/{ad}/ag/{parca}")

    @app.post("/api/montaj/{ad}/parametre")
    def parametre(ad: str, p: BagParametre) -> dict:
        raise NotImplementedError("SPEC 25: POST /api/montaj/{ad}/parametre")

    @app.get("/api/montaj/{ad}/oneri")
    def oneri(ad: str, anahtar: str, cift: str, is_ad: str = Query(alias="is")) -> dict:
        raise NotImplementedError("SPEC 25: GET /api/montaj/{ad}/oneri")

    @app.post("/api/sifirla")
    def sifirla() -> dict:
        raise NotImplementedError("SPEC 25: POST /api/sifirla")

    return depo
