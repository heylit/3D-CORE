"""
SPEC 65b — "Görünüm" ekranı (A3 kaydı): örnek montajı gerçekçi malzeme görünümüyle (PBR) gösterir.

Uçlar:
    GET /api/gorunum?montaj=ornek|<montaj.json>
        → {bileşen: {"gorunum", "yuzler"}} (tezgah.gorunum.montaj_gorunumu)
    GET /api/ekran/gorunum/
        → örnek montaj: bileşenler, konumlar, görünümler, yüz grupları
    GET /api/ekran/gorunum/ag/{bilesen}
        → application/octet-stream (model_kopru.ag_ikili; yüz index'li)
/api/gorunum kabuğun kur() kancasıyla doğrudan uygulamaya bağlanır (sunucu.py değişmez).
Hatalar: bilinmeyen bileşen / montaj dosyası → 404; çekirdeğin ModelError / AssyError / GeometryError'ı → 422.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from assy.model import Assembly, Component, transform
from geometry.part import FaceRef, Part
from tezgah import SEMA, model_kopru
from tezgah.ekranlar import Ekran
from tezgah.gorunum import montaj_gorunumu

router = APIRouter()
IKILI = "application/octet-stream"
ORNEK = "ornek"

_kilit = threading.Lock()
_parcalar: dict[str, Part] = {}


class GorunumSema(BaseModel):
    """tezgah.gorunum.Gorunum.to_dict() (OpenAPI şeması için)."""

    renk: str
    metalness: float
    roughness: float
    clearcoat: float
    anisotropy: float


class BilesenGorunumSema(BaseModel):
    gorunum: GorunumSema
    yuzler: dict[str, GorunumSema]  # FaceRef ("özellik:ad") → görünüm


def _ust_yuz(p: Part) -> int:
    """Parçanın en yüksek, +Z bakan düzlemsel yüzünün indeksi."""
    return max((f for f in p.planar_faces() if f.normal[2] > 0.99), key=lambda f: f.origin[2]).index


def _kati(p: Part, names=None) -> Part:
    """build123d alt sınıfını (ör. Box) düz Solid'e çevirir; yüz sırası aynı kalır (ag_ikili için)."""
    import build123d as bd

    return Part(bd.Solid(p.shape.wrapped), name=p.name, names=names)


def _ornek() -> tuple[Assembly, dict[str, Part]]:
    """C45 gövde, üst yüzü eloksal 6061 kapak, POM-C blok (uydurma geometri)."""
    from geometry.features import block, hole

    with _kilit:
        if not _parcalar:
            govde = hole(block(80.0, 60.0, 30.0, name="govde"), 20.0, 30.0, 12.0)
            kapak = block(80.0, 60.0, 6.0, name="kapak")
            kapak = _kati(kapak, names={FaceRef("kapak", "ust"): (_ust_yuz(kapak),)})
            blok = _kati(block(40.0, 40.0, 30.0, name="blok"))
            _parcalar.update(govde=govde, kapak=kapak, blok=blok)
        parcalar = dict(_parcalar)
    montaj = Assembly(
        "gorunum_ornek",
        [
            Component("govde", "govde", fixed=True, material="1.0503"),
            Component("kapak", "kapak", T=transform(None, (0.0, 0.0, 30.0)), material="EN-AW-6061-T6"),
            Component("blok", "blok", T=transform(None, (100.0, 10.0, 0.0)), material="POM-C"),
        ],
    )
    return montaj, parcalar


def _ornek_dict() -> dict:
    """Örnek montaj sözlüğü; kapağın üst yüzü eloksal (bileşen JSON'unda "gorunum": {"bitim": …})."""
    montaj, _ = _ornek()
    d = montaj.to_dict()
    for c in d["components"]:
        if c["name"] == "kapak":
            c["gorunum"] = {"bitim": {"kapak:ust": "eloksal"}}
    return d


def _montaj_oku(montaj: str) -> dict:
    if montaj == ORNEK:
        return _ornek_dict()
    yol = Path(montaj)
    if yol.suffix.lower() != ".json" or not yol.is_file():
        raise HTTPException(404, f"Montaj bulunamadı: {montaj!r} ('ornek' ya da bir montaj .json dosyası)")
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(422, f"Montaj dosyası okunamadı: {e}") from None


def gorunum_ucu(montaj: str = ORNEK) -> dict[str, BilesenGorunumSema]:
    """Her bileşen ve bitimli yüz için görünüm (SPEC 65b K4)."""
    return montaj_gorunumu(_montaj_oku(montaj))


@router.get("/")
def ornek_sahne() -> dict:
    """{"sema", "bilesenler": [{"ad", "T", "gorunum", "yuzler": {FaceRef: {"gorunum", "indeksler"}}}]}."""
    d = _ornek_dict()
    _, parcalar = _ornek()
    G = montaj_gorunumu(d)
    bilesenler = []
    for c in d["components"]:
        p = parcalar[c["part"]]
        g = G[c["name"]]
        yuzler = {
            ref: {"gorunum": yg, "indeksler": list(p.find(FaceRef.parse(ref)))}
            for ref, yg in g["yuzler"].items()
        }
        bilesenler.append({"ad": c["name"], "T": c["T"], "gorunum": g["gorunum"], "yuzler": yuzler})
    return {"sema": SEMA, "bilesenler": bilesenler}


@router.get("/ag/{bilesen}")
def ornek_ag(bilesen: str) -> Response:
    _, parcalar = _ornek()
    if bilesen not in parcalar:
        raise HTTPException(404, f"Bilinmeyen bileşen: {bilesen!r}")
    return Response(model_kopru.ag_ikili(parcalar[bilesen]), media_type=IKILI)


def kur(app: FastAPI) -> None:
    app.add_api_route(
        "/api/gorunum",
        gorunum_ucu,
        methods=["GET"],
        response_model=dict[str, BilesenGorunumSema],
        summary="SPEC 65b: montajın bileşen ve yüz görünümleri",
    )


EKRAN = Ekran(ad="gorunum", baslik="Görünüm", sira=90, router=router, kur=kur)
