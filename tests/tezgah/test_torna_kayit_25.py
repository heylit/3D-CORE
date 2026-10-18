"""
SPEC 25 — torna işinin A3 iş deposuna kaydı (specs/24a-ekran-kaydi.md `is_kaydet`, koordinatör notu 13:31).

`tezgah.ekranlar.torna` içe aktarılınca `depo.kaydedici_ekle(TornaIsi, ...)` ile torna türünü kaydeder:
`is_kaydet(ad, TornaIsi)` işi `tezgah.torna.hareketler` ile doğrular (geçersiz → CamError, depo değişmez),
torna deposuna koyar; iş /api/isler'de freze işlerinden sonra (kademeli_mil dahil) görünür. Torna ekranının
uçları (/api/ekran/torna/is/{ad}[/noktalar|/sim]) örnek işi bulamazsa dinamik işi sunar (`#/torna?is=<ad>`);
kabuğun /api/is/{ad} uçları yalnız freze içindir (404). POST /api/sifirla dinamik torna işlerini siler.

Ekran modülleri yoksa testler NotImplementedError ile "uygulanmamış" kalır (atlanmaz).
"""

from __future__ import annotations

import dataclasses
import importlib
import json

import pytest

from cam.model import CamError
from tests.tezgah import torna_ornekleri as o
from tezgah import torna
from tezgah.ekranlar import is_kaydet
from tezgah.isler import ORNEK_ISLER

AD = "t25-dinamik"


def _istemci():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    try:
        torna_ekrani = importlib.import_module("tezgah.ekranlar.torna")
        montaj_ekrani = importlib.import_module("tezgah.ekranlar.montaj")
    except ModuleNotFoundError as e:
        raise NotImplementedError(f"SPEC 25: ekran modülü henüz yok ({e.name})") from e
    return TestClient(uygulama(None, ekranlar=[torna_ekrani.EKRAN, montaj_ekrani.EKRAN]))


def _lathe():
    pytest.importorskip("cam.gcode.lathe", reason="SPEC 21 (cam.gcode.lathe) henüz yok")
    pytest.importorskip("cam.sim.lathe", reason="SPEC 22 (cam.sim.simulate_lathe) henüz yok")


def _json_tur(x):
    return json.loads(json.dumps(x, allow_nan=False))


def _dinamik(**degisen) -> torna.TornaIsi:
    return dataclasses.replace(o.kucuk_torna(), ad=AD, **degisen)


def _isler(ist) -> list[str]:
    r = ist.get("/api/isler")
    assert r.status_code == 200
    return r.json()["isler"]


@pytest.fixture
def kur():
    """İstemci kuran fonksiyon (NotImplementedError test gövdesinde çıksın diye); sonda POST /api/sifirla."""
    istemciler = []

    def f():
        istemciler.append(_istemci())
        return istemciler[-1]

    yield f
    for i in istemciler:
        i.post("/api/sifirla")


def test_sample_lathe_job_listed_after_milling(kur):
    """kademeli_mil /api/isler'de freze işlerinden sonra; /api/is/kademeli_mil freze ucu değil (404)."""
    ist = kur()
    L = _isler(ist)
    assert L[: len(ORNEK_ISLER)] == list(ORNEK_ISLER)
    assert "kademeli_mil" in L[len(ORNEK_ISLER) :]
    assert ist.get("/api/is/kademeli_mil").status_code == 404


def test_registered_lathe_job_served_by_lathe_screen(kur):
    """is_kaydet(TornaIsi) → /api/isler'de; torna ekranı uçları köprünün çıktısını verir; kabuk ucu 404."""
    ist = kur()
    _lathe()
    tanim = _dinamik()
    is_kaydet(AD, tanim)
    L = _isler(ist)
    assert L.count(AD) == 1 and L.index(AD) >= len(ORNEK_ISLER)
    r = ist.get(f"/api/ekran/torna/is/{AD}")
    assert r.status_code == 200
    assert r.json() == _json_tur(torna.is_json(tanim))
    assert r.json()["tur"] == "torna"
    assert ist.get(f"/api/ekran/torna/is/{AD}/noktalar").content == torna.noktalar_ikili(tanim)
    assert ist.get(f"/api/ekran/torna/is/{AD}/sim").content == torna.sim_ikili(tanim)
    for yol in ("", "/noktalar", "/sim"):
        assert ist.get(f"/api/is/{AD}{yol}").status_code == 404


def test_same_name_replaces(kur):
    ist = kur()
    _lathe()
    is_kaydet(AD, _dinamik())
    t2 = dataclasses.replace(o.kucuk_torna(), ad=AD, islemler=o.kucuk_torna().islemler[:1])
    is_kaydet(AD, t2)
    assert _isler(ist).count(AD) == 1
    assert ist.get(f"/api/ekran/torna/is/{AD}").json() == _json_tur(torna.is_json(t2))


def test_invalid_lathe_job_cam_error_store_unchanged(kur):
    """İşlemsiz TornaIsi → CamError (tezgah.torna.hareketler); liste ve aynı adlı eski iş değişmez."""
    ist = kur()
    _lathe()
    once = _isler(ist)
    with pytest.raises(CamError):
        is_kaydet("t25-gecersiz", _dinamik(islemler=[]))
    assert _isler(ist) == once
    assert ist.get("/api/ekran/torna/is/t25-gecersiz").status_code == 404

    is_kaydet(AD, _dinamik())
    J = ist.get(f"/api/ekran/torna/is/{AD}").json()
    with pytest.raises(CamError):
        is_kaydet(AD, _dinamik(islemler=[]))
    assert ist.get(f"/api/ekran/torna/is/{AD}").json() == J


def test_reset_removes_dynamic_lathe_jobs(kur):
    """POST /api/sifirla dinamik torna işini siler; kademeli_mil kalır."""
    ist = kur()
    _lathe()
    is_kaydet(AD, _dinamik())
    assert AD in _isler(ist)
    assert ist.post("/api/sifirla").status_code == 200
    L = _isler(ist)
    assert AD not in L and "kademeli_mil" in L
    assert ist.get(f"/api/ekran/torna/is/{AD}").status_code == 404
