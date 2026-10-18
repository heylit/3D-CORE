"""
SPEC 47b — Çok eksen ekranı: A3 kaydı (`EKRAN`) ve uçları (`/api/ekran/cok_eksen` altında).

İnce katman: hesap `_cok_eksen_kopru`'dadır, örnekler `_cok_eksen_ornekler`'dedir. Çekirdek hataları
(`CamError`, `ModelError` …) kabuğun ortak işleyicisiyle 422 olur (A3); bilinmeyen örnek → 404.

Uçlar:
    GET  /ornekler                       → {"sema": 1, "ornekler": [{"ad", "tur", "profil"}]}
    GET  /{ad}                           → CokEksen (son simülasyon önbellekteyse "sim" dolu)
    GET  /{ad}/noktalar | /pozlar | /sapma | /dexel   → application/octet-stream
                                           (/dexel simülasyon yokken 409)
    GET  /{ad}/govde/{govde}             → application/octet-stream (kopru.govde_ikili)
    POST /{ad}/parametre                 gövde {"anahtar", "deger"}
                                         → {"sema": 1, "is": CokEksen, "sure_farki"}
    POST /{ad}/simule                    → CokEksen ("sim" dolu); parmak izine göre önbellekli (K21)

Durum (bellekte, tek kullanıcı): örnek başına güncel `CokEksenIsi` ve simülasyon önbelleği.
`sifirla()` ikisini de başlangıca döndürür (POST /api/sifirla).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from tezgah.ekranlar import Ekran

OCTET = "application/octet-stream"

router = APIRouter()


class Parametre(BaseModel):
    anahtar: str
    deger: float


def hazir() -> str | None:
    """None → SPEC 41–44 modüllerinin hepsi var; yoksa eksikleri sayan neden metni."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def sifirla() -> None:
    """Örnek işleri ve simülasyon önbelleğini başlangıç değerine döndürür."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


@router.get("/ornekler")
def ornekler() -> dict:
    raise NotImplementedError("SPEC 47b: uygulanmadı")


@router.get("/{ad}")
def is_getir(ad: str) -> dict:
    raise NotImplementedError("SPEC 47b: uygulanmadı")


@router.get("/{ad}/noktalar")
def noktalar(ad: str) -> Response:
    raise NotImplementedError("SPEC 47b: uygulanmadı")


@router.get("/{ad}/pozlar")
def pozlar(ad: str) -> Response:
    raise NotImplementedError("SPEC 47b: uygulanmadı")


@router.get("/{ad}/sapma")
def sapma(ad: str) -> Response:
    raise NotImplementedError("SPEC 47b: uygulanmadı")


@router.get("/{ad}/dexel")
def dexel(ad: str) -> Response:
    raise NotImplementedError("SPEC 47b: uygulanmadı")


@router.get("/{ad}/govde/{govde}")
def govde(ad: str, govde: str) -> Response:
    raise NotImplementedError("SPEC 47b: uygulanmadı")


@router.post("/{ad}/parametre")
def parametre(ad: str, p: Parametre) -> dict:
    raise NotImplementedError("SPEC 47b: uygulanmadı")


@router.post("/{ad}/simule")
def simule(ad: str) -> dict:
    raise NotImplementedError("SPEC 47b: uygulanmadı")


EKRAN = Ekran(
    ad="cok_eksen",
    baslik="Çok eksen",
    sira=50,
    tus="5",
    router=router,
    hazir=hazir,
    sifirla=sifirla,
)
