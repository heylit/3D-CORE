"""
SPEC 24 — FastAPI sunucusu: REST uçları + derlenmiş ön yüzün (`arayuz/dist/`) statik servisi.

Uçlar:
    GET  /api/isler                 → {"sema": 1, "isler": [ad, ...]}
    GET  /api/is/{ad}               → Is JSON (kopru.is_json)
    GET  /api/is/{ad}/noktalar      → application/octet-stream (kopru.noktalar_ikili)
    GET  /api/is/{ad}/sim           → application/octet-stream (kopru.sim_ikili)
    POST /api/is/{ad}/parametre     gövde {"islem": int, "anahtar": str, "deger": float}
                                    → {"sema": 1, "is": Is, "sure_farki": yeni − eski toplam süre [s]}
Bilinmeyen iş → 404. Bilinmeyen işlem/anahtar → 422. Çekirdeğin `CamError` / `ModelError`'ı → 422,
gövde {"detail": hata metni}. Parametre değişikliği sunucu süreci boyunca o işte kalır.
Sunucu yalnızca 127.0.0.1'de dinler (`__main__`).
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cam.model import CamError
from core.model import ModelError
from tezgah import SEMA, kopru, sunucu_25
from tezgah.isler import ORNEK_ISLER, ornek_is, parametre_uygula

DIST = Path(__file__).parent / "arayuz" / "dist"
IKILI = "application/octet-stream"


class Parametre(BaseModel):
    islem: int
    anahtar: str
    deger: float


def uygulama(dist: Path | None = DIST) -> FastAPI:
    """FastAPI uygulaması. `dist` varsa `/` altında statik servis edilir; None → yalnızca API."""
    app = FastAPI(title="Tezgah", docs_url="/api/belgeler", redoc_url=None, openapi_url="/api/openapi.json")
    isler: dict[str, kopru.IsTanimi] = {}
    kilit = threading.Lock()  # iş sözlüğü ve parametre değişikliği tek tek
    sunucu_25.ekle(app)  # SPEC 25 torna ve montaj uçları; SPEC 24 uçlarından önce eşleşir

    def is_al(ad: str) -> kopru.IsTanimi:
        if ad not in ORNEK_ISLER:
            raise HTTPException(404, f"Bilinmeyen iş: {ad!r}")
        with kilit:
            if ad not in isler:
                isler[ad] = ornek_is(ad)
            return isler[ad]

    @app.get("/api/isler")
    def isler_listesi() -> dict:
        return {"sema": SEMA, "isler": list(ORNEK_ISLER)}

    @app.get("/api/is/{ad}")
    def is_json(ad: str) -> dict:
        return kopru.is_json(is_al(ad))

    @app.get("/api/is/{ad}/noktalar")
    def noktalar(ad: str) -> Response:
        return Response(kopru.noktalar_ikili(is_al(ad)), media_type=IKILI)

    @app.get("/api/is/{ad}/sim")
    def sim(ad: str) -> Response:
        return Response(kopru.sim_ikili(is_al(ad)), media_type=IKILI)

    @app.post("/api/is/{ad}/parametre")
    def parametre(ad: str, p: Parametre) -> dict:
        eski = is_al(ad)
        try:
            yeni = parametre_uygula(eski, p.islem, p.anahtar, p.deger)
            j = kopru.is_json(yeni)
        except KeyError as e:
            raise HTTPException(422, str(e.args[0]) if e.args else str(e)) from None
        except (CamError, ModelError) as e:
            raise HTTPException(422, str(e)) from None
        with kilit:
            isler[ad] = yeni
        fark = j["sure"]["toplam"] - kopru.is_json(eski)["sure"]["toplam"]
        return {"sema": SEMA, "is": j, "sure_farki": fark}

    if dist is not None and (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def kok() -> FileResponse:
            return FileResponse(dist / "index.html")

    return app
