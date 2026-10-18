"""
SPEC 26 — "Model" ekranı (A3 kaydı): etkileşimli modelleme uçları /api/ekran/model/ altında.

Uçlar (öneksiz yazılır, kabuk /api/ekran/model altına bağlar; SPEC 26 Ek A):
    GET  /                    → Model JSON (tezgah/modelleme.py)
    PUT  /                    Model JSON → {"sema", "rapor", "hacim"} (rapor_json; hacim mm³ | None)
    POST /eskiz/coz           {"eskiz", "olculer"?, "parametreler"?} → SolveResult JSON
    POST /eskiz/surukle       {"eskiz", "nokta", "hedef", "olculer"?, "parametreler"?} → SolveResult JSON
    GET  /ag?k=               application/octet-stream (model_kopru.ag_ikili)
    GET  /yuz/{index}         {sema, plane, outline}
    POST /tezgaha-gonder      SPEC 24 Is JSON; iş "model-<ad>" adıyla depoya eklenir (freze ekranı açar)
Çelişki → 422, gövde {"detail": {"hata": metin, "kisitlar": [sıra]}}; diğer çekirdek hataları 422 ve hata
metni (kabuğun hata işleyicisi). Bölüm: "model" (disa_aktar / ice_aktar, A3 sözleşmesi).
"""

from __future__ import annotations

import copy
import json
import threading
from collections.abc import Mapping

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from sketch.model import SketchError
from tezgah import SEMA, depo, kopru
from tezgah.ekranlar import Ekran

router = APIRouter()


# build123d (geometry/) ilk kullanımda yüklenir: sunucunun açılışı onu beklemez.
def _mk():
    from tezgah import model_kopru

    return model_kopru


def _geometri_hatasi() -> type[ValueError]:
    from geometry.part import GeometryError

    return GeometryError


IKILI = "application/octet-stream"

_kilit = threading.Lock()
_durum: dict = {}  # {"model": Model JSON}


class EskizIstek(BaseModel):
    eskiz: dict
    olculer: dict[str, str | float] | None = None  # {kısıt sırası: ifade}; parametreler modelden
    parametreler: dict[str, str | float] | None = None


class SurukleIstek(EskizIstek):
    nokta: str
    hedef: tuple[float, float]


def _model() -> dict:
    with _kilit:
        if "model" not in _durum:
            from tezgah.modelleme import ornek_model

            _durum["model"] = ornek_model()
        return copy.deepcopy(_durum["model"])


def _dogrula(model: dict) -> dict:
    """Model JSON'u: sözlük, sema = SEMA, adimlar liste, JSON'a çevrilebilir (nan / inf yok)."""
    if not isinstance(model, dict):
        raise _geometri_hatasi()("Model JSON'u sözlük olmalı")
    if model.get("sema") != SEMA:
        raise _geometri_hatasi()(f"Model sürümü {model.get('sema')!r}, beklenen {SEMA}")
    if not isinstance(model.get("adimlar", []), list):
        raise _geometri_hatasi()("Model 'adimlar' alanı liste olmalı")
    try:
        return json.loads(json.dumps(model, allow_nan=False))
    except (TypeError, ValueError) as e:
        raise _geometri_hatasi()(f"Model JSON'a çevrilemiyor: {e}") from None


def _yaz(model: dict) -> None:
    with _kilit:
        _durum["model"] = model


def _celiski(e: SketchError) -> HTTPException:
    return HTTPException(422, {"hata": str(e), "kisitlar": [int(i) for i in e.constraints]})


@router.get("/")
def model_oku() -> dict:
    return _model()


@router.put("/")
def model_yaz(model: dict) -> dict:
    from tezgah.modelleme import insa

    m = _dogrula(model)
    p, r = insa(m)  # adım hatası rapora yazılır, PUT düşmez
    _yaz(m)
    return {"sema": SEMA, "rapor": _mk().rapor_json(r), "hacim": None if p is None else float(p.volume)}


def _parametreler(i: EskizIstek) -> dict:
    return i.parametreler if i.parametreler is not None else _model().get("parametreler", {})


@router.post("/eskiz/coz")
def eskiz_coz(i: EskizIstek) -> dict:
    try:
        return _mk().eskiz_coz(i.eskiz, i.olculer, _parametreler(i))
    except SketchError as e:
        raise _celiski(e) from None


@router.post("/eskiz/surukle")
def eskiz_surukle(i: SurukleIstek) -> dict:
    try:
        return _mk().eskiz_surukle(i.eskiz, i.nokta, i.hedef, i.olculer, _parametreler(i))
    except SketchError as e:
        raise _celiski(e) from None


def _parca(k: int | None):
    from tezgah.modelleme import insa

    p, r = insa(_model(), k)
    if p is None:
        neden = f" ({r.hata.kimlik}: {r.hata.hata})" if r.hata is not None else ""
        raise _geometri_hatasi()(f"Bu adımda katı yok{neden}")
    return p


@router.get("/ag")
def model_ag(k: int | None = None):
    return Response(_mk().ag_ikili(_parca(k)), media_type=IKILI)


@router.get("/yuz/{index}")
def model_yuz(index: int) -> dict:
    return _mk().yuz_json(_parca(None), index)


@router.post("/tezgaha-gonder")
def tezgaha_gonder() -> dict:
    m = _model()
    tanim, uyarilar = _mk().gonder_uyarilari(m)
    tanim.ad = f"model-{m.get('ad', 'model')}"
    depo.kaydet(tanim.ad, tanim)  # freze ekranı bu işi açar (#/freze?is=…)
    J = kopru.is_json(tanim)
    J["kontroller"] = J["kontroller"] + uyarilar
    return J


def disa_aktar() -> dict:
    """ "model" bölümü: güncel Model JSON'u ("sema" alanlı)."""
    return _model()


def ice_aktar(belge: dict, onbellek: Mapping[str, bytes]) -> None:
    """Model JSON'unu yükler ve insa() ile doğrular; hata → durum değişmez (atomik)."""
    from tezgah.modelleme import insa

    m = _dogrula(belge)
    _, r = insa(m)
    if r.hata is not None:
        raise _geometri_hatasi()(f"Model kurulamadı: adım '{r.hata.kimlik}': {r.hata.hata}")
    _yaz(m)


def ozet() -> dict[str, float | str]:
    """Etki kartı: hacim_mm3, adim_sayisi, dof (son eskiz)."""
    from tezgah.modelleme import insa

    m = _model()
    p, r = insa(m)
    eskizler = [a for a in r.adimlar if a.tur == "eskiz" and a.dof is not None]
    return {
        "hacim_mm3": float(p.volume) if p is not None else 0.0,
        "adim_sayisi": float(len(m.get("adimlar", []))),
        "dof": float(eskizler[-1].dof) if eskizler else 0.0,
    }


def sifirla() -> None:
    """Modeli örnek modele (modelleme.ornek_model()) döndürür."""
    from tezgah.modelleme import ornek_model

    _yaz(ornek_model())


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
