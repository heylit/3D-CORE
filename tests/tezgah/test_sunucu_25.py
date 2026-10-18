"""
SPEC 25 — torna kanıtları (K7), yeni REST uçları ve tek iplik parametre bağı (K15).

Sunucu testleri `[web]` (fastapi + httpx) kurulu değilse atlanır. Beklenen yanıtlar köprü fonksiyonlarından
(`torna.is_json`, `montaj.montaj_json`, ...) ve örneklerden (`ornekler_25`) hesaplanır; K7'nin hata
değerleri SPEC 22 simülasyonunun çarpışma kayıtlarından. Her test kendi uygulamasını (ve parametre deposunu)
kurar.
"""

from __future__ import annotations

import json

import pytest

from cam.model import CamError
from tests.tezgah import torna_ornekleri as o
from tezgah import torna

OCTET = "application/octet-stream"


def _istemci():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    return TestClient(uygulama(dist=None))


def _lsim():
    pytest.importorskip("cam.sim.lathe", reason="SPEC 22 (cam.sim.simulate_lathe) henüz yok")
    from cam.sim import simulate_lathe

    return simulate_lathe


def _lathe():
    return pytest.importorskip("cam.gcode.lathe", reason="SPEC 21 (cam.gcode.lathe) henüz yok")


def _spec09():
    pytest.importorskip("build123d")
    from geometry.part import Part

    if not (hasattr(Part, "common") and hasattr(Part, "fuse")):
        pytest.skip("SPEC 09 (Part.common / Part.fuse) henüz yok")
    pytest.importorskip("assy.girisim", reason="SPEC 09 (assy.girisim) henüz yok")


def _json_tur(x):
    return json.loads(json.dumps(x, allow_nan=False))


def _kontrol(K: list[dict], kimlik: str) -> dict:
    (k,) = [x for x in K if x["kimlik"] == kimlik]
    return k


KIMLIKLER = {"cakma", "kalan_malzeme", "hizli_carpma", "ayna_carpma", "geri_okuma", "devir_siniri"}


# ---------------------------------------------------------------- K7: torna kanıtları


def _carpma_derinligi(tanim, tur: str) -> float:
    res = _lsim()([isl.op for isl in tanim.islemler], tanim.kurulum, cell=tanim.hucre)
    c = [x for x in res.collisions if x.kind == tur]
    assert c, f"SPEC 22 bu işte {tur} bulmuyor (test işi yanlış kurulmuş)"
    return max(x.depth for x in c)


def test_lathe_checks_ids():
    """K7: kontrol kimlikleri; her biri SPEC etiketli, durum tamam / uyari / hata."""
    _lathe()
    _lsim()
    K = torna.kontroller(o.kucuk_torna())
    assert {k["kimlik"] for k in K} == KIMLIKLER
    for k in K:
        assert k["durum"] in ("tamam", "uyari", "hata")
        assert k["spec"].startswith("SPEC ")
        assert {"baslik", "deger", "birim", "aciklama"} <= set(k)


@pytest.mark.occt
def test_lathe_checks_gouge():
    """K7: profilin altına inen iş (hedef Ø40, paso x = 18) → cakma hata; aynı parçada x ≥ 21 paso → tamam."""
    _lathe()
    _lsim()
    pytest.importorskip("build123d")
    from geometry.features import cylinder

    parca = cylinder(20.0, 60.0, name="hedef")
    k = _kontrol(torna.kontroller(o.cakan_is(parca)), "cakma")
    assert k["durum"] == "hata" and k["deger"] > 0
    assert _kontrol(torna.kontroller(o.temiz_is(parca)), "cakma")["durum"] == "tamam"


def test_lathe_checks_rapid():
    """K7: hızlı hareketi ham malzemeden geçen iş → hizli_carpma hata, değer SPEC 22'nin en derin kaydı."""
    _lathe()
    tanim = o.hizli_carpan_is()
    k = _kontrol(torna.kontroller(tanim), "hizli_carpma")
    assert k["durum"] == "hata"
    assert k["deger"] == pytest.approx(_carpma_derinligi(tanim, "hizli_carpma"), rel=1e-12)
    assert _kontrol(torna.kontroller(o.kucuk_torna()), "hizli_carpma")["durum"] == "tamam"


def test_lathe_checks_chuck():
    """K7: takımı çene bölgesine giren iş → ayna_carpma hata (SPEC 22 değeri); güvenli z_son → tamam."""
    _lathe()
    tanim = o.ayna_carpan_is()
    k = _kontrol(torna.kontroller(tanim), "ayna_carpma")
    assert k["durum"] == "hata"
    assert k["deger"] == pytest.approx(_carpma_derinligi(tanim, "ayna_carpma"), rel=1e-12)
    assert _kontrol(torna.kontroller(o.ayna_guvenli_is()), "ayna_carpma")["durum"] == "tamam"


def test_lathe_checks_readback():
    """K7: G-code geri okuma (SPEC 21) temiz işte tamam."""
    _lathe()
    _lsim()
    assert _kontrol(torna.kontroller(o.kucuk_torna()), "geri_okuma")["durum"] == "tamam"


@pytest.mark.occt
def test_lathe_checks_clean_example():
    """K7: temiz kademeli_mil'de bütün kontroller tamam; Is["kontroller"] ile kontroller() aynı."""
    _lathe()
    _lsim()
    from tezgah.ornekler_25 import kademeli_mil

    tanim = kademeli_mil()
    K = torna.kontroller(tanim)
    assert {k["kimlik"] for k in K} == KIMLIKLER
    assert all(k["durum"] == "tamam" for k in K), [
        (k["kimlik"], k["aciklama"]) for k in K if k["durum"] != "tamam"
    ]
    assert _json_tur(torna.is_json(tanim)["kontroller"]) == _json_tur(K)


# ---------------------------------------------------------------- uçlar


@pytest.mark.occt
def test_lathe_job_endpoints():
    """GET /api/is/kademeli_mil torna köprüsünden (`tur: torna`); /noktalar ve /sim ikili diziler."""
    _lathe()
    _lsim()
    from tezgah.ornekler_25 import kademeli_mil

    ist = _istemci()
    tanim = kademeli_mil()
    r = ist.get("/api/is/kademeli_mil")
    assert r.status_code == 200
    J = r.json()
    assert J["tur"] == "torna"
    assert J == _json_tur(torna.is_json(tanim))
    r = ist.get("/api/is/kademeli_mil/noktalar")
    assert r.status_code == 200 and r.headers["content-type"].startswith(OCTET)
    assert r.content == torna.noktalar_ikili(tanim)
    r = ist.get("/api/is/kademeli_mil/sim")
    assert r.status_code == 200 and r.headers["content-type"].startswith(OCTET)
    assert r.content == torna.sim_ikili(tanim)


def test_assembly_list():
    ist = _istemci()
    r = ist.get("/api/montajlar")
    assert r.status_code == 200
    assert r.json() == {"sema": 1, "montajlar": ["yatak_grubu"]}


def test_unknown_assembly_404():
    ist = _istemci()
    assert ist.get("/api/montaj/yok").status_code == 404
    assert ist.get("/api/montaj/yok/ag/plaka").status_code == 404
    assert (
        ist.post(
            "/api/montaj/yok/parametre", json={"is": "kademeli_mil", "anahtar": "L", "deger": 9.5}
        ).status_code
        == 404
    )


def test_assembly_endpoints():
    """GET /api/montaj/yatak_grubu = montaj_json;
    parça ve girişim ağları köprünün baytları; bilinmeyen parça 404."""
    _spec09()
    from tezgah.montaj import girisim_agi, montaj_json, parca_agi
    from tezgah.ornekler_25 import yatak_grubu

    ist = _istemci()
    tanim = yatak_grubu()
    r = ist.get("/api/montaj/yatak_grubu")
    assert r.status_code == 200
    J = r.json()
    assert J == _json_tur(montaj_json(tanim))
    for p in J["parcalar"]:
        r = ist.get(f"/api/montaj/yatak_grubu/ag/{p['kimlik']}")
        assert r.status_code == 200 and r.headers["content-type"].startswith(OCTET)
        assert r.content == parca_agi(tanim, p["kimlik"])
    assert ist.get("/api/montaj/yatak_grubu/ag/yok").status_code == 404
    (g,) = J["girisimler"]
    r = ist.get(g["ag"])
    assert r.status_code == 200 and r.content == girisim_agi(tanim, 0)
    assert ist.get("/api/montaj/yatak_grubu/ag/girisim/7").status_code == 404


def test_suggestion_endpoint():
    """GET /api/montaj/yatak_grubu/oneri → {deger, hacim}; girişimsiz durumda {deger: null, neden}."""
    _spec09()
    ist = _istemci()
    (g,) = ist.get("/api/montaj/yatak_grubu").json()["girisimler"]
    q = {"is": "kademeli_mil", "anahtar": "L", "cift": f"{g['a']},{g['b']}"}
    r = ist.get("/api/montaj/yatak_grubu/oneri", params=q)
    assert r.status_code == 200
    oneri = r.json()
    assert abs(oneri["deger"] - 10.0) <= 1e-3 and oneri["hacim"] == 0.0
    assert (
        ist.post(
            "/api/montaj/yatak_grubu/parametre", json={"is": "kademeli_mil", "anahtar": "L", "deger": 9.5}
        ).status_code
        == 200
    )
    oneri = ist.get("/api/montaj/yatak_grubu/oneri", params=q).json()
    assert oneri["deger"] is None and oneri["neden"]


# ---------------------------------------------------------------- K15: parametre bağı


def test_param_link():
    """K15: L = 9.5 → girişim yok; dönen `is` = ardından gelen GET; sure_farki = yeni − eski süre;
    POST /api/sifirla sonrası L = 20."""
    _spec09()
    _lathe()
    _lsim()
    from tezgah.ornekler_25 import kademeli_mil

    ist = _istemci()
    eski = ist.get("/api/is/kademeli_mil").json()
    r = ist.post(
        "/api/montaj/yatak_grubu/parametre", json={"is": "kademeli_mil", "anahtar": "L", "deger": 9.5}
    )
    assert r.status_code == 200
    Y = r.json()
    assert set(Y) == {"montaj", "is", "sure_farki"}
    assert Y["montaj"]["girisimler"] == []
    (bag,) = Y["montaj"]["baglar"]
    assert bag["parametre"]["deger"] == 9.5
    assert Y["is"] == ist.get("/api/is/kademeli_mil").json()
    assert Y["is"] == _json_tur(torna.is_json(kademeli_mil({"L": 9.5})))
    t_yeni = torna.is_json(kademeli_mil({"L": 9.5}))["sure"]["toplam"]
    t_eski = torna.is_json(kademeli_mil({"L": 20.0}))["sure"]["toplam"]
    assert eski["sure"]["toplam"] == pytest.approx(t_eski, rel=1e-12)
    assert Y["sure_farki"] == pytest.approx(t_yeni - t_eski, rel=1e-9, abs=1e-9)
    assert Y["sure_farki"] != 0.0  # uç boyu değişince G-code ve süre değişir
    assert Y["is"]["gcode"] != eski["gcode"]
    r = ist.post("/api/sifirla")
    assert r.status_code == 200
    J = ist.get("/api/montaj/yatak_grubu").json()
    assert J["baglar"][0]["parametre"]["deger"] == 20.0
    assert len(J["girisimler"]) == 1
    assert ist.get("/api/is/kademeli_mil").json() == eski


@pytest.mark.parametrize("deger", [0.0, -1.0, 4.0, 31.0])
def test_param_link_invalid_422(deger):
    """K15: geçersiz değer (L ≤ 0, aralık dışı) → 422, gövde çekirdeğin metni; parametre değişmez."""
    pytest.importorskip("build123d")
    from tezgah.ornekler_25 import kademeli_mil

    ist = _istemci()
    with pytest.raises(CamError) as e:
        kademeli_mil({"L": deger})
    r = ist.post(
        "/api/montaj/yatak_grubu/parametre", json={"is": "kademeli_mil", "anahtar": "L", "deger": deger}
    )
    assert r.status_code == 422
    assert r.json()["detail"] == str(e.value)


@pytest.mark.parametrize(
    "govde",
    [{"is": "yok", "anahtar": "L", "deger": 9.5}, {"is": "kademeli_mil", "anahtar": "yok", "deger": 9.5}],
)
def test_param_link_unknown_422(govde):
    """Bağ olmayan iş / anahtar → 422."""
    ist = _istemci()
    assert ist.post("/api/montaj/yatak_grubu/parametre", json=govde).status_code == 422


def test_reset_endpoint():
    ist = _istemci()
    r = ist.post("/api/sifirla")
    assert r.status_code == 200


def test_depot_out_of_range_camerror():
    """Depo.ayarla aralık dışı → CamError (sunucunun 422'si bunun metnidir)."""
    pytest.importorskip("build123d")
    from tezgah.iplik import Depo

    depo = Depo()
    depo.sifirla()
    with pytest.raises(CamError):
        depo.ayarla("yatak_grubu", "kademeli_mil", "L", 31.0)
    assert depo.parametreler["kademeli_mil"]["L"] == 20.0
