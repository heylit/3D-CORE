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

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from tezgah import SEMA
from tezgah.ekranlar import Ekran
from tezgah.ekranlar import _cok_eksen_kopru as kopru
from tezgah.ekranlar import _cok_eksen_ornekler as orn

OCTET = "application/octet-stream"

router = APIRouter()

# Bellekteki durum: örnek adı → güncel iş (parametre değişiklikleri), parmak izi → simülasyon sonuçları.
_isler: dict[str, object] = {}
_simler: dict[str, list] = {}


class Parametre(BaseModel):
    anahtar: str
    deger: float


def hazir() -> str | None:
    """None → SPEC 41–44 modüllerinin hepsi var; yoksa eksikleri sayan neden metni."""
    eksik = kopru.eksik_moduller()
    if not eksik:
        return None
    return "Çok eksen çekirdeği eksik: " + ", ".join(eksik)


def _is(ad: str):
    """Örneğin güncel işi (ilk istekte varsayılan girdilerle kurulur); bilinmeyen örnek → 404."""
    if ad not in orn.ORNEKLER:
        raise HTTPException(404, f"Bilinmeyen örnek: {ad}")
    if ad not in _isler:
        _isler[ad] = orn.ornek(ad)
    return _isler[ad]


def sifirla() -> None:
    """Örnek işleri ve simülasyon önbelleğini başlangıç değerine döndürür."""
    _isler.clear()
    _simler.clear()


@router.get("/ornekler")
def ornekler() -> dict:
    return {
        "sema": SEMA,
        "ornekler": [
            {"ad": ad, "tur": tur, "profil": profil} for ad, (tur, profil) in orn.VARSAYILAN.items()
        ],
    }


@router.get("/{ad}")
def is_getir(ad: str) -> dict:
    is_ = _is(ad)
    return kopru.cok_json(is_, _simler.get(kopru.parmak_izi(is_)))


@router.get("/{ad}/noktalar")
def noktalar(ad: str) -> Response:
    return Response(kopru.noktalar_ikili(_is(ad)), media_type=OCTET)


@router.get("/{ad}/pozlar")
def pozlar(ad: str) -> Response:
    return Response(kopru.pozlar_ikili(_is(ad)), media_type=OCTET)


@router.get("/{ad}/sapma")
def sapma(ad: str) -> Response:
    return Response(kopru.sapma_ikili(_is(ad)), media_type=OCTET)


@router.get("/{ad}/dexel")
def dexel(ad: str) -> Response:
    sim = _simler.get(kopru.parmak_izi(_is(ad)))
    if sim is None:
        raise HTTPException(409, "Simülasyon yok: önce POST /simule")
    return Response(kopru.dexel_ikili([r.tridexel for r in sim]), media_type=OCTET)


@router.get("/{ad}/govde/{govde}")
def govde(ad: str, govde: str) -> Response:
    try:
        veri = kopru.govde_ikili(_is(ad).model, govde)
    except KeyError:
        raise HTTPException(404, f"Bilinmeyen gövde: {govde}") from None
    return Response(veri, media_type=OCTET)


@router.post("/{ad}/parametre")
def parametre(ad: str, p: Parametre) -> dict:
    eski = _is(ad)
    yeni = kopru.parametre_uygula(eski, p.anahtar, p.deger)
    _isler[ad] = yeni
    return {
        "sema": SEMA,
        "is": kopru.cok_json(yeni, _simler.get(kopru.parmak_izi(yeni))),
        "sure_farki": kopru.sure(yeni) - kopru.sure(eski),
    }


@router.post("/{ad}/simule")
def simule(ad: str) -> dict:
    is_ = _is(ad)
    anahtar = kopru.parmak_izi(is_)
    if anahtar not in _simler:
        _simler[anahtar] = kopru.simule(is_)
    return kopru.cok_json(is_, _simler[anahtar])


EKRAN = Ekran(
    ad="cok_eksen",
    baslik="Çok eksen",
    sira=50,
    tus="5",
    router=router,
    hazir=hazir,
    sifirla=sifirla,
)
