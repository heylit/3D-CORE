"""
SPEC 47c — Analiz ekranı: A3 kaydı (`EKRAN`) ve uçları (`/api/ekran/analiz` altında).

İnce katman: işi `_analiz_kopru` yapar; burada durum (örnek başına tanım, ağ, çözüm önbelleği) ve
hata eşlemesi vardır. Çekirdek hataları (ModelError, KeyError) kabuğun ortak işleyicisiyle 422 olur;
bilinmeyen örnek 404, çözüm yokken /alan 404.

Uçlar:
    GET    /ornekler              → {"sema", "ornekler": [ad, ...]}
    GET    /{ad}                  → Analiz
    GET    /{ad}/ag               → ikili ag
    GET    /{ad}/alan             → ikili alan (çözüm yoksa 404)
    POST   /{ad}/sec              → {"ucgen": j} | {"silindir": {"nokta", "eksen", "r"}} → Analiz
    POST   /{ad}/kosul            → {"secim", "tur", "deger"} → Analiz
    DELETE /{ad}/kosul/{kimlik}   → Analiz
    POST   /{ad}/ag               → {"h"} → Analiz (yeniden ağ)
    POST   /{ad}/coz              → Analiz (cozum dolu; aynı girdide önbellekten)
    POST   /{ad}/sonda            → {"p0", "p1", "n", "bilesen"} → ikili sonda (çözüm yoksa 422)
    POST   /{ad}/yakinsama        → Analiz (yakinsama dolu)
    GET    /{ad}/inp              → text/plain, Content-Disposition dosya adı "<ad>.inp"
"""

from __future__ import annotations

import importlib.util
import threading
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Response

from core.model import ModelError
from tezgah.ekranlar import Ekran
from tezgah.ekranlar import _analiz_kopru as ak
from tezgah.ekranlar._analiz_ornekler import ORNEKLER

router = APIRouter()
IKILI = "application/octet-stream"


@dataclass
class _Durum:
    """Bir örneğin ekran durumu. Çözüm ve yakınsama yalnız hesaplandıkları tanım nesnesi için geçerlidir."""

    tanim: ak.AnalizTanimi
    cozum: tuple[ak.AnalizTanimi, ak.Cozum] | None = None
    yakin: tuple[ak.AnalizTanimi, list[dict]] | None = None


_kilit = threading.RLock()
_durumlar: dict[str, _Durum] = {}
# Ağ önbelleği: ağ yalnız (örnek, h, max_nodes) ile belirlenir (parça ve inceltme örneğe sabit);
# sıfırlamadan sonra da geçerlidir, bu yüzden sifirla() bunu boşaltmaz.
_aglar: dict[tuple[str, float, int], ak.Ag] = {}


def _durum(ad: str) -> _Durum:
    if ad not in ORNEKLER:
        raise HTTPException(404, f"Bilinmeyen analiz örneği: {ad!r}")
    if ad not in _durumlar:
        _durumlar[ad] = _Durum(ORNEKLER[ad]())
    return _durumlar[ad]


def _ag(ad: str, tanim: ak.AnalizTanimi) -> ak.Ag:
    anahtar = (ad, float(tanim.h), int(tanim.max_nodes))
    if anahtar not in _aglar:
        _aglar[anahtar] = ak.ag_kur(tanim)
    return _aglar[anahtar]


def _cozum(d: _Durum) -> ak.Cozum | None:
    return d.cozum[1] if d.cozum is not None and d.cozum[0] is d.tanim else None


def _yakin(d: _Durum) -> list[dict] | None:
    return d.yakin[1] if d.yakin is not None and d.yakin[0] is d.tanim else None


def _json(ad: str) -> dict:
    d = _durum(ad)
    return ak.analiz_json(d.tanim, _ag(ad, d.tanim), _cozum(d), _yakin(d))


@router.get("/ornekler")
def ornekler() -> dict:
    return {"sema": ak.SEMA, "ornekler": list(ORNEKLER)}


@router.get("/{ad}")
def analiz_al(ad: str) -> dict:
    with _kilit:
        return _json(ad)


@router.get("/{ad}/ag")
def ag(ad: str) -> Response:
    with _kilit:
        d = _durum(ad)
        return Response(ak.ag_ikili(_ag(ad, d.tanim)), media_type=IKILI)


@router.get("/{ad}/alan")
def alan(ad: str) -> Response:
    with _kilit:
        c = _cozum(_durum(ad))
        if c is None:
            raise HTTPException(404, "Çözüm yok: önce POST /coz")
        return Response(ak.alan_ikili(c), media_type=IKILI)


@router.post("/{ad}/sec")
def sec(ad: str, govde: dict) -> dict:
    with _kilit:
        d = _durum(ad)
        a = _ag(ad, d.tanim)
        if "ucgen" in govde:
            s = ak.ucgen_secimi(d.tanim, a, govde["ucgen"])
        elif "silindir" in govde and isinstance(govde["silindir"], dict):
            c = govde["silindir"]
            s = ak.silindir_secimi(d.tanim, a, c["nokta"], c["eksen"], c["r"])
        else:
            raise ModelError('Seçim gövdesi {"ucgen": j} ya da {"silindir": {nokta, eksen, r}} olmalı')
        d.tanim = ak.secim_ekle(d.tanim, s)
        return _json(ad)


@router.post("/{ad}/kosul")
def kosul(ad: str, govde: dict) -> dict:
    with _kilit:
        d = _durum(ad)
        d.tanim = ak.kosul_ekle(d.tanim, govde["secim"], govde["tur"], govde["deger"])
        return _json(ad)


@router.delete("/{ad}/kosul/{kimlik}")
def kosul_sil(ad: str, kimlik: str) -> dict:
    with _kilit:
        d = _durum(ad)
        d.tanim = ak.kosul_sil(d.tanim, kimlik)
        return _json(ad)


@router.post("/{ad}/ag")
def yeniden_ag(ad: str, govde: dict) -> dict:
    with _kilit:
        d = _durum(ad)
        yeni = ak.h_degistir(d.tanim, govde["h"])
        _ag(ad, yeni)  # ağ kurulamazsa (max_nodes) durum değişmez
        d.tanim = yeni
        return _json(ad)


@router.post("/{ad}/coz")
def coz(ad: str) -> dict:
    with _kilit:
        d = _durum(ad)
        if _cozum(d) is None:
            d.cozum = (d.tanim, ak.coz(d.tanim, _ag(ad, d.tanim)))
        return _json(ad)


@router.post("/{ad}/sonda")
def sonda(ad: str, govde: dict) -> Response:
    with _kilit:
        d = _durum(ad)
        c = _cozum(d)
        if c is None:
            raise ModelError("Sonda için önce çözüm gerekli (POST /coz)")
        degerler = ak.bilesen_degerleri(c, govde.get("bilesen", "vm"))
        model = _ag(ad, d.tanim).model
        s, deger, iceride = ak.sonda_degerleri(model, degerler, govde["p0"], govde["p1"], govde["n"])
        return Response(ak.sonda_ikili(s, deger, iceride), media_type=IKILI)


@router.post("/{ad}/yakinsama")
def yakinsama(ad: str) -> dict:
    with _kilit:
        d = _durum(ad)
        if _yakin(d) is None:
            d.yakin = (d.tanim, ak.yakinsama(d.tanim))
        return _json(ad)


@router.get("/{ad}/inp")
def inp(ad: str) -> Response:
    with _kilit:
        d = _durum(ad)
        metin = ak.inp(d.tanim, _ag(ad, d.tanim))
    return Response(
        metin,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ad}.inp"'},
    )


def hazir() -> str | None:
    """gmsh ya da OCCT yoksa neden metni ("gmsh kurulu değil: pip install -e .[mesh]"), aksi None.

    Her çağrıda yeniden denetlenir (önbellek yok): kurulum sonradan değişebilir.
    """
    try:
        import gmsh  # noqa: F401
    except ImportError:
        return "gmsh kurulu değil: pip install -e .[mesh]"
    if importlib.util.find_spec("build123d") is None:
        return "OCCT (build123d) kurulu değil: pip install -e .[cad]"
    return None


def sifirla() -> None:
    """Bütün örnekleri başlangıç tanımına döndürür; çözüm ve yakınsama düşer (ağ önbelleği kalır)."""
    with _kilit:
        _durumlar.clear()


EKRAN = Ekran(ad="analiz", baslik="Analiz", sira=60, tus="6", router=router, hazir=hazir, sifirla=sifirla)
