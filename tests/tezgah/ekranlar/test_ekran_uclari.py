"""
SPEC 47 — ekran uçları (`/api/ekran/<ad>/...`) ve A3 kaydı: K1, K6, K7, K13, K20, K21.

Her ekranın kısmı ayrı fonksiyonlardadır (47a Plan, 47b Çok eksen, 47c Analiz alt PR'ları).
`[web]` (fastapi + httpx) yoksa atlanır. Beklenen yanıtlar köprü ve örnek fonksiyonlarından ayrıca hesaplanır.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from tests.tezgah.ekranlar.cok_eksen_ortak import CEKIRDEK, cekirdek, json_tur, moduller

OCTET = "application/octet-stream"


def _web():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")


# ================================================================ 47b Çok eksen

COK = "/api/ekran/cok_eksen"


def _cok_eksen_ekrani():
    _web()
    from tezgah.ekranlar.cok_eksen import EKRAN

    return EKRAN


def _cok_istemci():
    """Yalnız çok eksen ekranı bağlı, statik dosyasız uygulama; ekran başlangıç durumunda."""
    EKRAN = _cok_eksen_ekrani()
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    EKRAN.sifirla()
    return TestClient(uygulama(dist=None, ekranlar=[EKRAN]))


def _cekirdek_var() -> bool:
    for modul, _ in CEKIRDEK:
        try:
            importlib.import_module(modul)
        except ImportError:
            return False
    return True


def _kesif(ekranlar):
    """A3 keşfi; keşfin bu testte import ettiği başka ekran modülleri sonra `sys.modules`'tan silinir
    (A3 testlerinin sahte paket keşfi eski modül nesnelerini görmesin)."""
    onceki = set(sys.modules)
    try:
        return ekranlar()
    finally:
        for k in list(sys.modules):
            if k.startswith("tezgah.ekranlar.") and k not in onceki:
                del sys.modules[k]
        importlib.invalidate_caches()


def test_kayit_cok_eksen():
    """K1 (çok eksen): A3 kaydı; çekirdek yokken `hazir` nedeni eksik modülleri sayar."""
    EKRAN = _cok_eksen_ekrani()
    from tezgah.ekranlar import Ekran, ekranlar

    assert isinstance(EKRAN, Ekran)
    assert (EKRAN.ad, EKRAN.tus, EKRAN.sira) == ("cok_eksen", "5", 50)
    assert EKRAN.baslik == "Çok eksen"
    assert EKRAN.router is not None and callable(EKRAN.hazir) and callable(EKRAN.sifirla)
    liste = _kesif(ekranlar)
    kayit = [e for e in liste if e.ad == "cok_eksen"]
    assert len(kayit) == 1 and kayit[0].tus == "5"
    # Yardımcı modüller ayrı ekran olarak listelenmez.
    assert not [e.ad for e in liste if "cok_eksen" in e.ad and e.ad != "cok_eksen"]

    neden = EKRAN.hazir()
    eksik = []
    for modul, spec in CEKIRDEK:
        try:
            importlib.import_module(modul)
        except ImportError:
            eksik.append((modul, spec))
    if not eksik:
        assert neden is None
    else:
        assert isinstance(neden, str) and neden
        for modul, spec in eksik:
            assert modul in neden and spec in neden


def test_cok_eksen_hazir_degil_503():
    """K1: çekirdek yokken kabuk açılır, ekran listede kullanılamaz görünür, uçları 503 ve neden metni."""
    if _cekirdek_var():
        pytest.skip("SPEC 41–44 kurulu: ekran hazır")
    istemci = _cok_istemci()
    EKRAN = _cok_eksen_ekrani()
    r = istemci.get("/api/ekranlar")
    assert r.status_code == 200
    satir = [e for e in r.json()["ekranlar"] if e["ad"] == "cok_eksen"]
    assert len(satir) == 1
    assert satir[0]["hazir"] is False and satir[0]["neden"] == EKRAN.hazir()
    r = istemci.get(f"{COK}/ornekler")
    assert r.status_code == 503
    assert r.json()["detail"] == EKRAN.hazir()


def test_cok_eksen_uclar():
    """Uçlar köprünün çıktısını aynen verir (JSON ve ikili)."""
    cekirdek()
    kopru, orn = moduller()
    istemci = _cok_istemci()

    r = istemci.get(f"{COK}/ornekler")
    assert r.status_code == 200
    J = r.json()
    assert J["sema"] == 1
    assert [o["ad"] for o in J["ornekler"]] == list(orn.ORNEKLER)
    for o in J["ornekler"]:
        is_ = orn.ornek(o["ad"])
        assert (o["tur"], o["profil"]) == (is_.tur, is_.profil)

    for ad in orn.ORNEKLER:
        is_ = orn.ornek(ad)
        r = istemci.get(f"{COK}/{ad}")
        assert r.status_code == 200
        assert r.json() == json_tur(kopru.cok_json(is_))
        ikililer = {u: getattr(kopru, f"{u}_ikili") for u in ("noktalar", "pozlar", "sapma")}
        for uc, fn in ikililer.items():
            r = istemci.get(f"{COK}/{ad}/{uc}")
            assert r.status_code == 200, uc
            assert r.headers["content-type"].startswith(OCTET)
            assert r.content == fn(is_), (ad, uc)
        # Simülasyon yokken dexel yok.
        assert istemci.get(f"{COK}/{ad}/dexel").status_code == 409
        for g in kopru.cok_json(is_)["tezgah"]["govdeler"]:
            r = istemci.get(f"{COK}/{ad}/govde/{g['ad']}")
            assert r.status_code == 200
            assert r.content == kopru.govde_ikili(is_.model, g["ad"])
        r = istemci.get(f"{COK}/{ad}/govde/olmayan_govde")
        assert 400 <= r.status_code < 500

    assert istemci.get(f"{COK}/olmayan_ornek").status_code == 404
    assert istemci.get(f"{COK}/olmayan_ornek/noktalar").status_code == 404


def test_cok_eksen_parametre():
    """K13: `tilt` değişince yeni iş ve `sure_farki` iki işin ayrı hesaplanan sürelerinin farkı;
    sunucu durumu yeni işte kalır."""
    cekirdek()
    kopru, orn = moduller()
    istemci = _cok_istemci()
    ad = "kubbe_5eksen"
    eski = orn.ornek(ad)
    yeni = orn.ornek(ad, tilt=15.0)

    r = istemci.post(f"{COK}/{ad}/parametre", json={"anahtar": "tilt", "deger": 15.0})
    assert r.status_code == 200
    J = r.json()
    assert J["sema"] == 1
    assert J["is"] == json_tur(kopru.cok_json(yeni))
    assert J["is"]["parametreler"]["tilt"] == 15.0
    assert J["sure_farki"] == pytest.approx(kopru.sure(yeni) - kopru.sure(eski), rel=1e-12, abs=1e-12)
    # Sunucu durumu yeni işte.
    assert istemci.get(f"{COK}/{ad}").json() == J["is"]
    assert istemci.get(f"{COK}/{ad}/noktalar").content == kopru.noktalar_ikili(yeni)


@pytest.mark.parametrize(("anahtar", "deger"), [("tol_p", 0.0), ("tol_p", -1e-3), ("L", 0.0), ("L", -10.0)])
def test_cok_eksen_hatalar(anahtar, deger):
    """K13: geçersiz parametre → 422 ve çekirdeğin metni; iş değişmez."""
    cekirdek()
    kopru, orn = moduller()
    from cam.model import CamError

    istemci = _cok_istemci()
    ad = "kubbe_5eksen"
    with pytest.raises(CamError) as hata:
        orn.ornek(ad, **{anahtar: deger})
    once = istemci.get(f"{COK}/{ad}").json()
    r = istemci.post(f"{COK}/{ad}/parametre", json={"anahtar": anahtar, "deger": deger})
    assert r.status_code == 422
    assert r.json()["detail"] == str(hata.value)
    assert istemci.get(f"{COK}/{ad}").json() == once


def test_cok_eksen_hatalar_anahtar():
    """K13: bilinmeyen parametre anahtarı → 422."""
    cekirdek()
    istemci = _cok_istemci()
    r = istemci.post(f"{COK}/kubbe_5eksen/parametre", json={"anahtar": "olmayan", "deger": 1.0})
    assert r.status_code == 422


def test_cok_eksen_hatalar_kuresel_olmayan_takim():
    """K13: küresel olmayan takımla `finish5` çekirdekte CamError; ekranın ucu bunu 422 + metinle verir."""
    cekirdek()
    kopru, orn = moduller()
    from cam.model import CamError, Tool, ToolKind
    from cam.ops3d import Raster

    is_ = orn.ornek("kubbe_5eksen", "ac_besik")
    from cam.multiaxis.toolpath5 import Orientation, finish5

    duz = Tool(id=99, name="duz6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)
    raster = Raster(
        xmin=-10, xmax=10, ymin=-10, ymax=10, stepover=2, ds=1, tol=0.01, ds_min=0.1,
        feed=1000, plunge_feed=300, rpm=8000, z_safe=50,
    )  # fmt: skip
    with pytest.raises(CamError) as hata:
        finish5(is_.part, duz, raster, Orientation("normal", lead=0.0, tilt=10.0))
    metin = str(hata.value)

    # Köprü çekirdek hatasını geçirir: parametre uygulanırken çekirdek CamError fırlatırsa uç 422 + metin.
    import tezgah.ekranlar.cok_eksen as ekran_modulu

    def sahte(*_a, **_k):
        raise CamError(metin)

    istemci = _cok_istemci()
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(kopru, "parametre_uygula", sahte)
        if hasattr(ekran_modulu, "parametre_uygula"):
            mp.setattr(ekran_modulu, "parametre_uygula", sahte)
        r = istemci.post(f"{COK}/kubbe_5eksen/parametre", json={"anahtar": "tilt", "deger": 12.0})
    finally:
        mp.undo()
    assert r.status_code == 422
    assert r.json()["detail"] == metin


@pytest.mark.slow
def test_onbellek_sifirla_cok_eksen(monkeypatch):
    """K21 (çok eksen): aynı girdiyle ikinci `simule` çekirdeği yeniden çağırmaz ve aynı yanıtı verir;
    girdi değişince yeniden hesaplar; `POST /api/sifirla` örnekleri başlangıca döndürür.
    K12: `/simule` ve `/dexel` uçları."""
    cekirdek()
    kopru, orn = moduller()
    import tezgah.ekranlar.cok_eksen as ekran_modulu

    sayac = {"n": 0}
    gercek = kopru.simule

    def sayan(*a, **k):
        sayac["n"] += 1
        return gercek(*a, **k)

    monkeypatch.setattr(kopru, "simule", sayan)
    if hasattr(ekran_modulu, "simule") and ekran_modulu.simule is gercek:
        monkeypatch.setattr(ekran_modulu, "simule", sayan)

    istemci = _cok_istemci()
    ad = "egik_yuz_3arti2"
    is_ = orn.ornek(ad)
    sims = gercek(is_)
    beklenen = json_tur(kopru.cok_json(is_, sims))

    r1 = istemci.post(f"{COK}/{ad}/simule")
    assert r1.status_code == 200
    assert r1.json() == beklenen
    assert r1.json()["sim"] is not None
    assert sayac["n"] == 1
    r2 = istemci.post(f"{COK}/{ad}/simule")
    assert r2.json() == r1.json()
    assert sayac["n"] == 1
    # Simülasyon sonrası GET /{ad} sim dolu, /dexel işlem sonu görüntüleri.
    assert istemci.get(f"{COK}/{ad}").json() == beklenen
    r = istemci.get(f"{COK}/{ad}/dexel")
    assert r.status_code == 200
    assert r.content == kopru.dexel_ikili([s.tridexel for s in sims])

    # Girdi değişince yeniden hesaplar.
    r = istemci.post(f"{COK}/{ad}/parametre", json={"anahtar": "clearance", "deger": 1.0})
    assert r.status_code == 200
    istemci.post(f"{COK}/{ad}/simule")
    assert sayac["n"] == 2

    # Sıfırlama: parametre başlangıçta, simülasyon yok.
    assert istemci.post("/api/sifirla").status_code == 200
    J = istemci.get(f"{COK}/{ad}").json()
    assert J == json_tur(kopru.cok_json(orn.ornek(ad)))
    assert J["parametreler"]["clearance"] == orn.CLEARANCE
    assert J["sim"] is None
    assert istemci.get(f"{COK}/{ad}/dexel").status_code == 409
