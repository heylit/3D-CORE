"""
A3 — iş deposu yönlendirme kancası: `depo.kaydedici_ekle(tur, kaydet, adlar=None)`.

Davranış (koordinatör notu, 13:31): `is_kaydet`, `IsTanimi` olmayan bir tanımı türü için kayıtlı
`kaydet`'e verir (ör. SPEC 25: TornaIsi → torna); kayıtsız tür → CamError, depo değişmez.
`adlar()` kayıtlı ekranların işlerini freze işlerinden sonra ekler (yinelenen ad bir kez);
`/api/is/{ad}*` yalnız freze işleridir, öteki adlar 404. `IsTanimi` yönlendirilemez; aynı tür başka bir
`kaydet` ile ikinci kez → CamError.

Her test kendi uydurma türünü tanımlar (kayıtlar birbirine karışmaz); `adlar` geri çağrısı test sonunda boş
listeye döner, böylece kalıcı kayıt öteki testlerin /api/isler listesini etkilemez.
"""

from __future__ import annotations

import dataclasses

import pytest

from cam.model import CamError
from tests.tezgah import ornekler as o
from tezgah import depo
from tezgah.ekranlar import is_kaydet
from tezgah.isler import ORNEK_ISLER


def _kaydedici_ekle():
    f = getattr(depo, "kaydedici_ekle", None)
    if f is None:
        raise NotImplementedError("A3: tezgah.depo.kaydedici_ekle henüz yok")
    return f


@pytest.fixture
def ekran():
    """Uydurma bir ekranın deposu: kaydet çağrılarını kaydeder, adlar() listesini döner;
    test sonunda boşalır."""
    durum = {"kayitlar": [], "adlar": []}
    yield durum
    durum["kayitlar"].clear()
    durum["adlar"].clear()
    depo.sifirla()


def _yeni_tur(ad: str = "SahteIs") -> type:
    return type(ad, (), {})


def _kur(ekran, tur, adlar: bool = True):
    def kaydet(ad: str, tanim: object) -> None:
        if getattr(tanim, "bozuk", False):
            raise CamError(f"'{ad}': bozuk tanım")
        ekran["kayitlar"].append((ad, tanim))
        if ad not in ekran["adlar"]:
            ekran["adlar"].append(ad)

    _kaydedici_ekle()(tur, kaydet, (lambda: list(ekran["adlar"])) if adlar else None)
    return kaydet


def test_routes_to_registered_type(ekran):
    """is_kaydet kayıtlı türün tanımını o türün kaydet'ine (ad, tanım) ile verir; freze deposu değişmez."""
    tur = _yeni_tur()
    _kur(ekran, tur)
    t = tur()
    once = depo.adlar()
    is_kaydet("a3-sahte", t)
    assert ekran["kayitlar"] == [("a3-sahte", t)]
    assert not depo.var_mi("a3-sahte")
    assert depo.adlar() == once + ["a3-sahte"]


def test_names_listed_after_milling_jobs(ekran):
    """adlar(): örnek freze işleri, dinamik freze işleri, sonra kayıtlı ekranın işleri;
    yinelenen ad bir kez."""
    tur = _yeni_tur()
    _kur(ekran, tur)
    freze = "a3-freze-dinamik"
    is_kaydet(freze, dataclasses.replace(o.kucuk_is(), ad=freze))
    ekran["adlar"].extend(["s1", "s2", ORNEK_ISLER[0]])
    assert depo.adlar() == list(ORNEK_ISLER) + [freze, "s1", "s2"]


def test_names_none_lists_nothing(ekran):
    tur = _yeni_tur()
    _kur(ekran, tur, adlar=False)
    is_kaydet("a3-gorunmez", tur())
    assert [a for a in depo.adlar() if a == "a3-gorunmez"] == []
    assert ekran["kayitlar"] and ekran["kayitlar"][0][0] == "a3-gorunmez"


def test_api_lists_routed_jobs_but_job_endpoints_are_milling_only(ekran):
    """/api/isler routed işi gösterir; /api/is/{ad}, /noktalar, /sim, /parametre o ad için 404."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    tur = _yeni_tur()
    _kur(ekran, tur)
    ist = TestClient(uygulama(dist=None, ekranlar=[]))
    is_kaydet("a3-sahte", tur())
    L = ist.get("/api/isler").json()["isler"]
    assert L[: len(ORNEK_ISLER)] == list(ORNEK_ISLER) and L[-1] == "a3-sahte"
    for yol in ("", "/noktalar", "/sim"):
        assert ist.get(f"/api/is/a3-sahte{yol}").status_code == 404
    r = ist.post("/api/is/a3-sahte/parametre", json={"islem": 0, "anahtar": "D", "deger": 8.0})
    assert r.status_code == 404


def test_routed_cam_error_propagates_store_unchanged(ekran):
    """Kayıtlı kaydet'in CamError'ı is_kaydet'ten çıkar; ad listesi değişmez."""
    tur = _yeni_tur()
    _kur(ekran, tur)
    once = depo.adlar()
    bozuk = tur()
    bozuk.bozuk = True
    with pytest.raises(CamError):
        is_kaydet("a3-bozuk", bozuk)
    assert depo.adlar() == once
    assert ekran["kayitlar"] == []


def test_unregistered_type_cam_error_store_unchanged(ekran):
    _kaydedici_ekle()
    once = depo.adlar()
    with pytest.raises(CamError):
        is_kaydet("a3-kayitsiz", _yeni_tur("KayitsizIs")())
    assert depo.adlar() == once
    assert not depo.var_mi("a3-kayitsiz")


def test_milling_type_cannot_be_routed():
    from tezgah.kopru import IsTanimi

    with pytest.raises(CamError):
        _kaydedici_ekle()(IsTanimi, lambda ad, t: None)


def test_second_registration_of_type(ekran):
    """Aynı tür başka bir kaydet ile → CamError; aynı kaydet ile yeniden
    (modülün yeniden içe aktarılması) sorun değil."""
    tur = _yeni_tur()
    kaydet = _kur(ekran, tur)
    _kaydedici_ekle()(tur, kaydet, lambda: list(ekran["adlar"]))
    with pytest.raises(CamError):
        _kaydedici_ekle()(tur, lambda ad, t: None)
    is_kaydet("a3-sahte", tur())
    assert [a for a, _ in ekran["kayitlar"]] == ["a3-sahte"]
