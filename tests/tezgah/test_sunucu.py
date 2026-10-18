"""
SPEC 24 — sunucu (`tezgah/sunucu.py`, K4) ve kanıt paneli kontrolleri (`kopru.kontroller`, K5).

Sunucu testleri `[web]` (fastapi + httpx) kurulu değilse atlanır. Uçların beklenen yanıtları köprü ve
örnek iş fonksiyonlarının kendisinden (`kopru.is_json`, `isler.ornek_is`) hesaplanır. Sunucu durumu
(parametre değişikliği süreç boyunca işte kalır) testler arasında paylaşılabileceği için beklenen iş her
seferinde sunucunun o anki parametrelerinden kurulur.

K5 kontrolleri SPEC 05'e (`cam.sim`) bağlıdır; `cam.sim` yoksa atlanır.
"""

from __future__ import annotations

import json

import pytest

from cam.model import CamError
from core.model import ModelError
from tests.tezgah import ornekler as o
from tezgah import SEMA
from tezgah.isler import ORNEK_ISLER, ornek_is
from tezgah.kopru import is_json, kontroller, noktalar_ikili, sim_ikili

AD = "flans-plakasi"
OCTET = "application/octet-stream"


def _sim():
    return pytest.importorskip("cam.sim", reason="SPEC 05 (cam.sim) henüz yok")


def _istemci(dist=None):
    """Yalnızca API'li uygulama için test istemcisi; `[web]` yoksa test atlanır."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    return TestClient(uygulama(dist=dist))


def _json_tur(x):
    return json.loads(json.dumps(x, allow_nan=False))


def _parametreler(J: dict) -> dict[int, dict[str, float]]:
    return {isl["i"]: dict(isl["parametreler"]) for isl in J["islemler"]}


def _beklenen(J_once: dict, islem: int | None = None, anahtar: str | None = None, deger: float | None = None):
    """Sunucunun o anki parametreleri (+ isteğe bağlı tek değişiklik) ile kurulan iş."""
    p = _parametreler(J_once)
    if islem is not None:
        p[islem][anahtar] = deger
    return ornek_is(J_once["ad"], p)


# ---------------------------------------------------------------- K4: uçlar


def test_list_jobs():
    """Örnek freze işleri listenin başında; A3 ile diğer ekranların işleri (ör. torna) arkadan gelebilir."""
    istemci = _istemci()
    r = istemci.get("/api/isler")
    assert r.status_code == 200
    J = r.json()
    assert set(J) == {"sema", "isler"}
    assert J["sema"] == SEMA
    assert J["isler"][: len(ORNEK_ISLER)] == list(ORNEK_ISLER)
    assert len(J["isler"]) == len(set(J["isler"]))


def test_get_job():
    istemci = _istemci()
    _sim()
    r = istemci.get(f"/api/is/{AD}")
    assert r.status_code == 200
    J = r.json()
    assert J["sema"] == SEMA
    assert J["ad"] == AD
    assert J == _json_tur(is_json(_beklenen(J)))


def test_get_points_and_sim_binary():
    istemci = _istemci()
    _sim()
    J = istemci.get(f"/api/is/{AD}").json()
    tanim = _beklenen(J)
    r = istemci.get(f"/api/is/{AD}/noktalar")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(OCTET)
    assert r.content == noktalar_ikili(tanim)
    r = istemci.get(f"/api/is/{AD}/sim")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(OCTET)
    assert r.content == sim_ikili(tanim)


@pytest.mark.parametrize("yol", ["", "/noktalar", "/sim"])
def test_unknown_job_404(yol):
    istemci = _istemci()
    assert istemci.get(f"/api/is/olmayan-is{yol}").status_code == 404


def test_unknown_job_parameter_404():
    istemci = _istemci()
    r = istemci.post("/api/is/olmayan-is/parametre", json={"islem": 0, "anahtar": "D", "deger": 8.0})
    assert r.status_code == 404


def test_parameter_returns_new_job_and_time_difference():
    """K4: POST sonrası `sure_farki`, iki işin ayrı ayrı hesaplanan toplam sürelerinin farkı."""
    istemci = _istemci()
    _sim()
    J0 = istemci.get(f"/api/is/{AD}").json()
    D0 = J0["islemler"][2]["parametreler"]["D"]
    D1 = 8.0 if D0 != 8.0 else 6.0
    r = istemci.post(f"/api/is/{AD}/parametre", json={"islem": 2, "anahtar": "D", "deger": D1})
    assert r.status_code == 200
    Y = r.json()
    assert set(Y) == {"sema", "is", "sure_farki"}
    assert Y["sema"] == SEMA

    eski = is_json(_beklenen(J0))
    yeni = is_json(_beklenen(J0, 2, "D", D1))
    assert Y["is"] == _json_tur(yeni)
    assert Y["is"]["islemler"][2]["parametreler"]["D"] == D1
    assert Y["sure_farki"] == pytest.approx(
        yeni["sure"]["toplam"] - eski["sure"]["toplam"], rel=1e-12, abs=1e-12
    )

    # Değişiklik süreç boyunca işte kalır; sonraki fark yeni durumdan ölçülür.
    J1 = istemci.get(f"/api/is/{AD}").json()
    assert J1 == Y["is"]
    r = istemci.post(f"/api/is/{AD}/parametre", json={"islem": 2, "anahtar": "D", "deger": D0})
    assert r.status_code == 200
    assert r.json()["sure_farki"] == pytest.approx(-Y["sure_farki"], rel=1e-12, abs=1e-12)
    assert r.json()["is"] == J0


@pytest.mark.parametrize(
    "islem, anahtar, deger",
    [(2, "D", 0.0), (2, "D", 500.0), (0, "D", -1.0), (1, "F", 0.0)],
)
def test_invalid_parameter_422_with_core_message(islem, anahtar, deger):
    """K4: geçersiz değer → 422, gövde {"detail": çekirdeğin hata metni}; iş değişmez."""
    istemci = _istemci()
    _sim()
    J0 = istemci.get(f"/api/is/{AD}").json()
    with pytest.raises((CamError, ModelError)) as e:
        _beklenen(J0, islem, anahtar, deger)
    r = istemci.post(f"/api/is/{AD}/parametre", json={"islem": islem, "anahtar": anahtar, "deger": deger})
    assert r.status_code == 422
    assert r.json()["detail"] == str(e.value)
    assert istemci.get(f"/api/is/{AD}").json() == J0


@pytest.mark.parametrize(
    "govde", [{"islem": 9, "anahtar": "D", "deger": 8.0}, {"islem": 2, "anahtar": "yok", "deger": 1.0}]
)
def test_unknown_op_or_key_422(govde):
    istemci = _istemci()
    assert istemci.post(f"/api/is/{AD}/parametre", json=govde).status_code == 422


def test_static_files_served_from_dist(tmp_path):
    """`dist` verilirse `/` derlenmiş ön yüzü (index.html) servis eder; None → yalnızca API."""
    (tmp_path / "index.html").write_text("<!doctype html><title>Tezgah deneme</title>", encoding="utf-8")
    r = _istemci(tmp_path).get("/")
    assert r.status_code == 200
    assert "Tezgah deneme" in r.text
    assert _istemci(tmp_path).get("/api/isler").status_code == 200
    assert _istemci(None).get("/").status_code == 404


# ---------------------------------------------------------------- K5: kanıtlar gerçek


KIMLIKLER = {"cakma", "hizli_carpma", "sap", "tutucu", "gcode_geri_okuma"}
KONTROL_ALANLARI = {"kimlik", "baslik", "deger", "birim", "durum", "aciklama", "spec"}


def _kontrol_sozlugu(K: list[dict]) -> dict[str, dict]:
    for k in K:
        assert set(k) == KONTROL_ALANLARI
        assert k["durum"] in {"tamam", "uyari", "hata"}
        assert k["spec"].startswith("SPEC ")
        assert isinstance(k["baslik"], str) and k["baslik"]
    ids = [k["kimlik"] for k in K]
    assert len(ids) == len(set(ids))
    assert KIMLIKLER <= set(ids)
    _json_tur(K)
    return {k["kimlik"]: k for k in K}


def test_checks_clean_sample_all_ok():
    """K5: temiz örnek işte (flanş plakası) bütün kontroller `tamam`."""
    _sim()
    K = _kontrol_sozlugu(kontroller(ornek_is(AD)))
    assert {k: v["durum"] for k, v in K.items()} == dict.fromkeys(K, "tamam")


def test_checks_small_clean_job_ok():
    """K5: elle kurulmuş temiz iş (kanal + G83): hiçbir kontrol `hata` değil, geri okuma `tamam`."""
    _sim()
    K = _kontrol_sozlugu(kontroller(o.kucuk_is()))
    assert all(v["durum"] != "hata" for v in K.values())
    assert K["gcode_geri_okuma"]["durum"] == "tamam"
    assert K["hizli_carpma"]["durum"] == "tamam"


def test_checks_gouge_is_error():
    """K5: yol CAD parçasının üst yüzünün 0.2 mm altına iner → `cakma` `hata`."""
    _sim()
    K = _kontrol_sozlugu(kontroller(o.cakma_is()))
    assert K["cakma"]["durum"] == "hata"
    assert K["hizli_carpma"]["durum"] == "tamam"


def test_checks_no_gouge_above_part_ok():
    """K5 (karşıt durum): aynı parça, yol üst yüzün 0.5 mm üstünde → `cakma` `tamam`."""
    _sim()
    K = _kontrol_sozlugu(kontroller(o.cakmayan_is()))
    assert K["cakma"]["durum"] == "tamam"


def test_checks_rapid_through_material_is_error():
    """K5: G0 stokun içinden geçer → `hizli_carpma` `hata`."""
    _sim()
    K = _kontrol_sozlugu(kontroller(o.hizli_carpma_is()))
    assert K["hizli_carpma"]["durum"] == "hata"
    assert K["gcode_geri_okuma"]["durum"] == "tamam"


def test_checks_in_job_json():
    """`Is["kontroller"]` = `kopru.kontroller` çıktısı."""
    _sim()
    tanim = o.hizli_carpma_is()
    assert is_json(tanim)["kontroller"] == _json_tur(kontroller(tanim))


def test_checks_served_with_job():
    istemci = _istemci()
    _sim()
    J = istemci.get(f"/api/is/{AD}").json()
    assert J["kontroller"] == _json_tur(kontroller(_beklenen(J)))
