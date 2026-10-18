"""
SPEC 26 — "Model" ekranı (A3 kaydı): etkileşimli modelleme uçları /api/ekran/model/ altında.

Uçlar (öneksiz yazılır, kabuk /api/ekran/model altına bağlar; SPEC 26 Ek A):
    GET  /                    → Model JSON (tezgah/modelleme.py)
    PUT  /                    Model JSON → {"sema", "rapor"} (model_kopru.rapor_json)
    POST /eskiz/coz           {"eskiz"} → SolveResult JSON
    POST /eskiz/surukle       {"eskiz", "nokta", "hedef"} → SolveResult JSON
    GET  /ag?k=               application/octet-stream (model_kopru.ag_ikili)
    GET  /yuz/{index}         {sema, plane, outline}
    POST /tezgaha-gonder      SPEC 24 Is JSON
Çelişki → 422, gövde {"detail": {"hata": metin, "kisitlar": [sıra]}}; diğer çekirdek hataları 422 ve hata
metni (kabuğun hata işleyicisi). Bölüm: "model" (disa_aktar / ice_aktar, A3 sözleşmesi).
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter
from pydantic import BaseModel

from tezgah.ekranlar import Ekran

router = APIRouter()


class EskizIstek(BaseModel):
    eskiz: dict


class SurukleIstek(BaseModel):
    eskiz: dict
    nokta: str
    hedef: tuple[float, float]


@router.get("/")
def model_oku() -> dict:
    raise NotImplementedError("SPEC 26: GET /api/ekran/model/")


@router.put("/")
def model_yaz(model: dict) -> dict:
    raise NotImplementedError("SPEC 26: PUT /api/ekran/model/")


@router.post("/eskiz/coz")
def eskiz_coz(i: EskizIstek) -> dict:
    raise NotImplementedError("SPEC 26: POST /api/ekran/model/eskiz/coz")


@router.post("/eskiz/surukle")
def eskiz_surukle(i: SurukleIstek) -> dict:
    raise NotImplementedError("SPEC 26: POST /api/ekran/model/eskiz/surukle")


@router.get("/ag")
def model_ag(k: int | None = None):
    raise NotImplementedError("SPEC 26: GET /api/ekran/model/ag")


@router.get("/yuz/{index}")
def model_yuz(index: int) -> dict:
    raise NotImplementedError("SPEC 26: GET /api/ekran/model/yuz/{index}")


@router.post("/tezgaha-gonder")
def tezgaha_gonder() -> dict:
    raise NotImplementedError("SPEC 26: POST /api/ekran/model/tezgaha-gonder")


def disa_aktar() -> dict:
    """ "model" bölümü: güncel Model JSON'u ("sema" alanlı)."""
    raise NotImplementedError("SPEC 26: disa_aktar")


def ice_aktar(belge: dict, onbellek: Mapping[str, bytes]) -> None:
    """Model JSON'unu yükler ve insa() ile doğrular; hata → durum değişmez (atomik)."""
    raise NotImplementedError("SPEC 26: ice_aktar")


def ozet() -> dict[str, float | str]:
    """Etki kartı: hacim_mm3, adim_sayisi, dof (son eskiz)."""
    raise NotImplementedError("SPEC 26: ozet")


def sifirla() -> None:
    """Modeli örnek modele (modelleme.ornek_model()) döndürür."""
    raise NotImplementedError("SPEC 26: sifirla")


EKRAN = Ekran(
    ad="model",
    baslik="Model",
    sira=70,
    tus="7",
    router=router,
    sifirla=sifirla,
    bolum="model",
    disa_aktar=disa_aktar,
    ice_aktar=ice_aktar,
    ozet=ozet,
)
