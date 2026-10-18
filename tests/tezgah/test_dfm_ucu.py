"""SPEC 61 K11 — Tezgah DFM ucu: `GET /api/ekran/model/dfm`.

Testler SPEC 61 K11 metninden, Karar 2'den (seçili kütüphane yoksa örnek kütüphane + uyarı) ve iskeletin
arayüzünden (`tezgah/ekranlar/dfm.py`: YOL, EKRAN, kur) yazıldı; `model_dfm` gövdesi okunmadı.
Beklenen yanıt: {"bulgular": [Bulgu alanları], "tamam": bool, "sure_s": float, "uyarilar": [metin]}.
Model ekranının durumu `PUT /api/ekran/model/` ile değiştirilir; `POST /api/sifirla` örnek modele
(`tezgah.modelleme.ornek_model()`, flanş: keskin köşeli kör cep + 4 × Ø6.6 boydan delik) döndürür.
Örnek kütüphanede (`examples/takim_kutuphanesi.json`) Ø6.6 matkap yok → delik bilgisi; cep köşesi keskin →
iç köşe hatası. Sunucu testleri `[web]` (fastapi + httpx) ve OCCT kurulu değilse atlanır.
"""

from __future__ import annotations

import copy
import json
import math

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from atolye.dfm import DERECELER, TURLER  # noqa: E402
from tezgah.ekranlar import sekme_mi  # noqa: E402
from tezgah.modelleme import ornek_model  # noqa: E402

occt = pytest.mark.occt

YOL = "/api/ekran/model/dfm"
ALANLAR = {"tur", "derece", "yuzler", "nokta", "olculen", "sinir", "mesaj", "oneri", "kural"}
ORNEK_UYARI = "örnek kütüphaneyle denetlendi"


def _istemci():
    """Model + DFM ekranlı uygulama; durum sıfırlanmış (model = ornek_model())."""
    from fastapi.testclient import TestClient

    from tezgah.ekranlar import dfm, model
    from tezgah.sunucu import uygulama

    c = TestClient(uygulama(None, ekranlar=[model.EKRAN, dfm.EKRAN]))
    y = c.post("/api/sifirla")
    assert y.status_code == 200, y.text
    return c


def _sonlu_json(metin: str):
    """nan / inf içeren JSON'u reddeder (Python json'u NaN, Infinity sabitlerini kabul eder)."""

    def red(sabit):
        raise AssertionError(f"JSON'da sonlu olmayan sayı: {sabit}")

    return json.loads(metin, parse_constant=red)


def _rapor(c) -> dict:
    y = c.get(YOL)
    assert y.status_code == 200, y.text
    return _sonlu_json(y.text)


def _model_yaz(c, m: dict) -> None:
    y = c.put("/api/ekran/model/", json=m)
    assert y.status_code == 200, y.text


# ---------------------------------------------------------------- kayıt (OCCT'siz)


def test_ekran_kaydi():
    from tezgah.ekranlar import dfm

    assert dfm.YOL == YOL
    e = dfm.EKRAN
    assert e.ad == "dfm"
    assert e.baslik == "DFM denetimi"
    assert e.sira == 71
    assert e.bagimli == ("model",)
    assert e.kur is not None
    assert e.router is None and e.tus is None and e.bolum is None
    assert not sekme_mi(e)  # sekme değil


def test_kesifte_var_sekme_listesinde_yok():
    from fastapi.testclient import TestClient

    from tezgah.ekranlar import ekranlar
    from tezgah.sunucu import uygulama

    assert "dfm" in [e.ad for e in ekranlar()]
    c = TestClient(uygulama(None))
    y = c.get("/api/ekranlar")
    assert y.status_code == 200, y.text
    assert "dfm" not in [s["ad"] for s in y.json()["ekranlar"]]
    yollar = {getattr(r, "path", None) for r in c.app.routes}
    assert YOL in yollar


# ---------------------------------------------------------------- yanıt (OCCT)


@occt
def test_ornek_model_raporu():
    c = _istemci()
    J = _rapor(c)
    assert set(J) >= {"bulgular", "tamam", "sure_s", "uyarilar"}
    assert isinstance(J["tamam"], bool)
    assert isinstance(J["sure_s"], int | float) and math.isfinite(J["sure_s"]) and J["sure_s"] >= 0
    assert isinstance(J["uyarilar"], list) and all(isinstance(u, str) for u in J["uyarilar"])
    B = J["bulgular"]
    assert isinstance(B, list) and len(B) >= 1
    for b in B:
        assert set(b) == ALANLAR
        assert b["derece"] in DERECELER
        if J["tamam"]:
            assert b["tur"] in TURLER
        assert isinstance(b["yuzler"], list) and all(isinstance(i, int) for i in b["yuzler"])
        assert b["nokta"] is None or (
            len(b["nokta"]) == 3 and all(isinstance(v, int | float) for v in b["nokta"])
        )
        assert isinstance(b["olculen"], int | float) and isinstance(b["sinir"], int | float)
        assert isinstance(b["mesaj"], str) and b["mesaj"]
        assert isinstance(b["oneri"], str) and isinstance(b["kural"], str)
    # derece sırası: hata → bilgi
    sira = [DERECELER.index(b["derece"]) for b in B]
    assert sira == sorted(sira)
    turler = {(b["tur"], b["derece"]) for b in B}
    assert ("ic_kose", "hata") in turler  # keskin köşeli kör cep
    assert ("delik", "bilgi") in turler  # Ø6.6 matkap örnek kütüphanede yok


@occt
def test_ornek_kutuphane_uyarisi():
    c = _istemci()
    assert ORNEK_UYARI in _rapor(c)["uyarilar"]


@occt
def test_yuzler_model_yuz_ucuyla_acilir():
    c = _istemci()
    yuzler = sorted({i for b in _rapor(c)["bulgular"] for i in b["yuzler"]})
    assert yuzler  # en az bir bulgu bir yüze bağlı
    for i in yuzler:
        y = c.get(f"/api/ekran/model/yuz/{i}")
        assert y.status_code == 200, (i, y.text)


@occt
def test_belirlenimci():
    c = _istemci()
    a, b = _rapor(c)["bulgular"], _rapor(c)["bulgular"]
    assert a == b


@occt
def test_guncel_modeli_okur():
    # Yalnız plaka (cep ve delik adımları yok) → iç köşe ve delik bulgusu düşer
    c = _istemci()
    m = ornek_model()
    m["adimlar"] = [a for a in m["adimlar"] if a["kimlik"] in ("plaka_eskizi", "plaka")]
    _model_yaz(c, m)
    turler = {b["tur"] for b in _rapor(c)["bulgular"]}
    assert "ic_kose" not in turler and "delik" not in turler

    # sıfırlayınca örnek modele döner, bulgular geri gelir
    assert c.post("/api/sifirla").status_code == 200
    turler = {b["tur"] for b in _rapor(c)["bulgular"]}
    assert {"ic_kose", "delik"} <= turler


# ---------------------------------------------------------------- 422


def _bos_model() -> dict:
    m = ornek_model()
    m["adimlar"] = []
    return m


def _ilk_adimi_bozuk_model() -> dict:
    m = ornek_model()
    m["adimlar"] = copy.deepcopy(m["adimlar"][:2])
    m["adimlar"][1]["eskiz"] = "olmayan_eskiz"  # ekstrüzyon yok bir eskize bağlı → katı kurulamaz
    return m


@occt
@pytest.mark.parametrize("kur", [_bos_model, _ilk_adimi_bozuk_model], ids=["adimsiz", "bozuk-ilk-adim"])
def test_kati_yoksa_422(kur):
    c = _istemci()
    _model_yaz(c, kur())
    y = c.get(YOL)
    assert y.status_code == 422, y.text
