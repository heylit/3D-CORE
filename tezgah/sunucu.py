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

SPEC 26 modelleme uçları (tezgah/model_kopru.py, tezgah/modelleme.py):
    POST /api/model/eskiz/coz       {"eskiz"} → SolveResult JSON
    POST /api/model/eskiz/surukle   {"eskiz", "nokta", "hedef"} → SolveResult JSON
    GET  /api/model · PUT /api/model   Model JSON; PUT → {"sema", "rapor"}
    GET  /api/model/ag?k=           application/octet-stream (model_kopru.ag_ikili)
    GET  /api/model/yuz/{index}     {plane, outline}
    POST /api/model/tezgaha-gonder  Is JSON
Çelişki → 422, gövde {"detail": {"hata": metin, "kisitlar": [sıra]}}; diğer SketchError / GeometryError /
IfadeError → 422 ve hata metni.
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
from geometry.part import GeometryError
from sketch.model import SketchError
from tezgah import SEMA, kopru, model_kopru, modelleme
from tezgah.ifade import IfadeError
from tezgah.isler import ORNEK_ISLER, ornek_is, parametre_uygula

DIST = Path(__file__).parent / "arayuz" / "dist"
IKILI = "application/octet-stream"


class Parametre(BaseModel):
    islem: int
    anahtar: str
    deger: float


class EskizIstek(BaseModel):
    eskiz: dict


class SurukleIstek(BaseModel):
    eskiz: dict
    nokta: str
    hedef: tuple[float, float]


def _cekirdek_hatasi(e: Exception) -> HTTPException:
    if isinstance(e, SketchError) and e.constraints:
        return HTTPException(422, {"hata": str(e), "kisitlar": list(e.constraints)})
    return HTTPException(422, str(e))


def uygulama(dist: Path | None = DIST) -> FastAPI:
    """FastAPI uygulaması. `dist` varsa `/` altında statik servis edilir; None → yalnızca API."""
    app = FastAPI(title="Tezgah", docs_url="/api/belgeler", redoc_url=None, openapi_url="/api/openapi.json")
    isler: dict[str, kopru.IsTanimi] = {}
    kilit = threading.Lock()  # iş sözlüğü ve parametre değişikliği tek tek

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

    # --- SPEC 26: modelleme ---
    durum: dict = {}

    def model_al() -> dict:
        with kilit:
            if "model" not in durum:
                durum["model"] = modelleme.ornek_model()
            return durum["model"]

    def parca(k: int | None = None):
        p, _ = modelleme.insa(model_al(), k)
        if p is None:
            raise HTTPException(422, "Modelde katı yok")
        return p

    HATALAR = (SketchError, GeometryError, IfadeError, CamError, ModelError)

    @app.post("/api/model/eskiz/coz")
    def eskiz_coz(i: EskizIstek) -> dict:
        try:
            return model_kopru.eskiz_coz(i.eskiz)
        except HATALAR as e:
            raise _cekirdek_hatasi(e) from None

    @app.post("/api/model/eskiz/surukle")
    def eskiz_surukle(i: SurukleIstek) -> dict:
        try:
            return model_kopru.eskiz_surukle(i.eskiz, i.nokta, i.hedef)
        except HATALAR as e:
            raise _cekirdek_hatasi(e) from None

    @app.get("/api/model")
    def model_oku() -> dict:
        return model_al()

    @app.put("/api/model")
    def model_yaz(model: dict) -> dict:
        try:
            _, rapor = modelleme.insa(model)
        except HATALAR as e:
            raise _cekirdek_hatasi(e) from None
        with kilit:
            durum["model"] = model
        return {"sema": SEMA, "rapor": model_kopru.rapor_json(rapor)}

    @app.get("/api/model/ag")
    def model_ag(k: int | None = None) -> Response:
        try:
            return Response(model_kopru.ag_ikili(parca(k)), media_type=IKILI)
        except HATALAR as e:
            raise _cekirdek_hatasi(e) from None

    @app.get("/api/model/yuz/{index}")
    def model_yuz(index: int) -> dict:
        try:
            return model_kopru.yuz_json(parca(), index)
        except HATALAR as e:
            raise _cekirdek_hatasi(e) from None

    @app.post("/api/model/tezgaha-gonder")
    def tezgaha_gonder() -> dict:
        try:
            return kopru.is_json(model_kopru.tezgaha_gonder(model_al()))
        except HATALAR as e:
            raise _cekirdek_hatasi(e) from None

    if dist is not None and (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def kok() -> FileResponse:
            return FileResponse(dist / "index.html")

    return app
