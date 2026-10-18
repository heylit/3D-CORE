"""
SPEC 24 — FastAPI sunucusu: REST uçları + derlenmiş ön yüzün (`arayuz/dist/`) statik servisi.

Uçlar:
    GET  /api/isler                 → {"sema": 1, "isler": [ad, ...]}
    GET  /api/is/{ad}               → Is JSON (kopru.is_json)
    GET  /api/is/{ad}/noktalar      → application/octet-stream (kopru.noktalar_ikili)
    GET  /api/is/{ad}/sim           → application/octet-stream (kopru.sim_ikili)
    POST /api/is/{ad}/parametre     gövde {"islem": int, "anahtar": str, "deger": float}
                                    → {"sema": 1, "is": Is, "sure_farki": yeni − eski toplam süre [s]}
    GET  /api/ekranlar              → A3 ekran kaydı (specs/24a-ekran-kaydi.md)
    POST /api/sifirla               → A3: ekranlar ve iş deposu varsayılana
    *    /api/ekran/<ad>/...        → A3: her ekranın kendi uçları
Bilinmeyen iş → 404. Bilinmeyen işlem/anahtar → 422. Çekirdeğin hataları (KeyError, CamError, ModelError,
AssyError, GeometryError, SketchError) → 422, gövde {"detail": hata metni}.
Parametre değişikliği sunucu süreci boyunca o işte kalır.
Sunucu yalnızca 127.0.0.1'de dinler (`__main__`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from assy.model import AssyError
from cam.model import CamError
from core.model import ModelError
from geometry.part import GeometryError
from sketch.model import SketchError
from tezgah import SEMA, depo, kopru
from tezgah import ekranlar as kayit
from tezgah.ekranlar import Ekran

DIST = Path(__file__).parent / "arayuz" / "dist"
IKILI = "application/octet-stream"

# A3 §4: çekirdeğin hata türleri → 422, gövde {"detail": str(e)} (ekrandan bağımsız, tek yerde).
CEKIRDEK_HATALARI: tuple[type[Exception], ...] = (
    KeyError,
    CamError,
    ModelError,
    AssyError,
    GeometryError,
    SketchError,
)


class Parametre(BaseModel):
    islem: int
    anahtar: str
    deger: float


def uygulama(dist: Path | None = DIST, ekranlar: list[Ekran] | None = None) -> FastAPI:
    """FastAPI uygulaması. `dist` varsa `/` altında statik servis edilir; None → yalnızca API.

    `ekranlar` (A3): bağlanacak ekranlar; None → `tezgah.ekranlar.ekranlar()` (keşif). Liste doğrulanır
    (kayıt hatası → ModelError). Kurulan uygulamada örnek işler varsayılan parametrelerle başlar.
    """
    liste = kayit.ekranlar() if ekranlar is None else kayit.dogrula(list(ekranlar))
    kayit.bagla(liste)
    depo.ornekleri_sifirla()
    app = FastAPI(title="Tezgah", docs_url="/api/belgeler", redoc_url=None, openapi_url="/api/openapi.json")

    async def cekirdek_hatasi(istek: Request, e: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=422)

    for tur in CEKIRDEK_HATALARI:
        app.add_exception_handler(tur, cekirdek_hatasi)

    def is_al(ad: str) -> kopru.IsTanimi:
        if not depo.var_mi(ad):
            raise HTTPException(404, f"Bilinmeyen iş: {ad!r}")
        return depo.al(ad)

    @app.get("/api/isler")
    def isler_listesi() -> dict:
        return {"sema": SEMA, "isler": depo.adlar()}

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
        is_al(ad)
        try:
            eski, yeni = depo.parametre(ad, p.islem, p.anahtar, p.deger)
        except KeyError as e:
            raise HTTPException(422, str(e.args[0]) if e.args else str(e)) from None
        j = kopru.is_json(yeni)
        fark = j["sure"]["toplam"] - kopru.is_json(eski)["sure"]["toplam"]
        return {"sema": SEMA, "is": j, "sure_farki": fark}

    @app.get("/api/ekranlar")
    def ekran_listesi() -> dict:
        """A3: {"ekranlar": [{ad, baslik, sira, tus, hazir, neden, bolum, bagimli}]}; yalnız sekmeler."""
        L = []
        for e in liste:
            if not kayit.sekme_mi(e):
                continue
            neden = e.hazir() if e.hazir is not None else None
            L.append(
                {
                    "ad": e.ad,
                    "baslik": e.baslik,
                    "sira": e.sira,
                    "tus": e.tus,
                    "hazir": neden is None,
                    "neden": neden,
                    "bolum": e.bolum,
                    "bagimli": list(e.bagimli),
                }
            )
        return {"ekranlar": L}

    @app.post("/api/sifirla")
    def sifirla() -> dict:
        """A3: her ekranın `sifirla()`'sı; iş deposu varsayılana (dinamik işler silinir)."""
        depo.sifirla()
        for e in liste:
            if e.sifirla is not None:
                e.sifirla()
        return {"sema": SEMA}

    for e in liste:
        if e.router is not None:
            app.include_router(e.router, prefix=f"{kayit.ONEK}/{e.ad}", dependencies=[Depends(_hazir_mi(e))])
    for e in liste:
        if e.kur is not None:
            e.kur(app)

    if dist is not None and (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def kok() -> FileResponse:
            return FileResponse(dist / "index.html")

    return app


def _hazir_mi(e: Ekran):
    """Kullanılamaz ekranın uçları 503, `detail` = neden (A3 §1)."""

    def denetle() -> None:
        neden = e.hazir() if e.hazir is not None else None
        if neden is not None:
            raise HTTPException(503, neden)

    return denetle
