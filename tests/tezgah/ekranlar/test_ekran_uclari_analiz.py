"""
SPEC 47c — Analiz ekranının uçları (`/api/ekran/analiz/...`): K1 (analiz kaydı, gmsh yokken kabuk açılır),
K15–K17 uç hataları (422), K20 `.inp` dışa aktarımı, K21 çözüm önbelleği ve sıfırlama.

(SPEC'teki `test_ekran_uclari.py`'nin analiz kısmı; 47a ile aynı dosyada birleşme çakışması olmasın diye
ayrı dosyadır.) Uçlar A3 kabuğuyla (`tezgah.sunucu.uygulama`) test edilir; beklenen yanıtlar köprüden
(`_analiz_kopru`) ve SPEC 12 / 13 / `fileio.calculix` çağrılarından kurulur.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

pytest.importorskip("fastapi", reason="[web] kurulu değil (pip install -e .[web])")
pytest.importorskip("httpx", reason="[web] kurulu değil (pip install -e .[web])")

from core.model import ModelError  # noqa: E402
from tests.tezgah.ekranlar import analiz_ortak as o  # noqa: E402
from tezgah.ekranlar import _analiz_kopru as ak  # noqa: E402
from tezgah.ekranlar import analiz as analiz_ekrani  # noqa: E402

A = o.ANALIZ
OCTET = "application/octet-stream"


class _Uygulanmamis:
    """A3 / 47c iskeletiyken NotImplementedError kurulumda değil testte doğsun ("uygulanmamış", conftest)."""

    def __init__(self, e: NotImplementedError):
        self.e = e

    def __getattr__(self, ad):
        raise self.e


def _istemci_kur():
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    c = TestClient(uygulama(dist=None))
    assert c.post("/api/sifirla").status_code == 200
    return c


@pytest.fixture
def istemci():
    """Keşifle kurulan kabuk (A3); her test başlangıç durumundan (`POST /api/sifirla`)."""
    try:
        c = _istemci_kur()
    except NotImplementedError as e:
        yield _Uygulanmamis(e)
        return
    yield c
    c.post("/api/sifirla")


def _taze(ad: str) -> dict:
    t = o.ornek(ad)
    return o.jt(ak.analiz_json(t, ak.ag_kur(t)))


def _x_ucgeni(J_ag: dict, x: float) -> int:
    """İkili ağda üç köşesi de x düzleminde olan ilk sınır üçgeninin indeksi."""
    X, U = J_ag["dugum"], J_ag["ucgen"]
    for j, tr in enumerate(U):
        if np.all(np.abs(X[tr.astype(int), 0] - x) <= 1e-4):
            return j
    raise AssertionError(f"x = {x} yüzünde üçgen yok")


# ---------------------------------------------------------------- K1: kayıt


def test_kayit():
    E = analiz_ekrani.EKRAN
    assert (E.ad, E.baslik, E.tus) == ("analiz", "Analiz", "6")
    assert E.router is not None and callable(E.hazir) and callable(E.sifirla)


@pytest.mark.occt
def test_hazir(istemci):
    pytest.importorskip("gmsh", reason="gmsh kurulu değil (pip install -e .[mesh])")
    assert analiz_ekrani.EKRAN.hazir() is None
    satir = [e for e in istemci.get("/api/ekranlar").json()["ekranlar"] if e["ad"] == "analiz"]
    assert len(satir) == 1 and satir[0]["tus"] == "6" and satir[0]["hazir"] is True
    r = istemci.get(f"{A}/ornekler")
    assert r.status_code == 200
    J = r.json()
    assert J["sema"] == 1
    adlar = [x if isinstance(x, str) else x["ad"] for x in J["ornekler"]]
    assert adlar == list(o.ORNEK_ADLARI)


def test_gmsh_yokken(monkeypatch):
    """gmsh yokken `hazir()` metni "gmsh" içerir; kabuk yine açılır, ekran kullanılamaz (uçlar 503)."""
    monkeypatch.setitem(sys.modules, "gmsh", None)  # import gmsh → ImportError, find_spec → None
    neden = analiz_ekrani.EKRAN.hazir()
    assert isinstance(neden, str) and "gmsh" in neden
    c = _istemci_kur()
    satir = [e for e in c.get("/api/ekranlar").json()["ekranlar"] if e["ad"] == "analiz"]
    assert len(satir) == 1 and satir[0]["hazir"] is False and "gmsh" in satir[0]["neden"]
    assert c.get(f"{A}/ornekler").status_code == 503
    assert c.get("/api/isler").status_code == 200  # kabuğun diğer uçları çalışır


# ---------------------------------------------------------------- uçlar = köprü


@pytest.mark.occt
def test_analiz_ve_ag(istemci):
    J = _taze("delikli_plaka")
    r = istemci.get(f"{A}/delikli_plaka")
    assert r.status_code == 200
    assert r.json() == J
    r = istemci.get(f"{A}/delikli_plaka/ag")
    assert r.status_code == 200 and r.headers["content-type"].startswith(OCTET)
    t = o.ornek("delikli_plaka")
    beklenen = ak.ag_coz(ak.ag_ikili(ak.ag_kur(t)))
    gelen = ak.ag_coz(r.content)
    for k in ("dugum", "ucgen", "kimlik"):
        assert np.array_equal(gelen[k], beklenen[k]), k
    assert istemci.get(f"{A}/delikli_plaka/alan").status_code == 404  # çözüm yok


@pytest.mark.occt
def test_sec_kosul_coz(istemci):
    """Seç → koşul ekle → çöz → alan → sonda → koşul sil; her yanıt `Analiz` (ya da ikili)."""
    J0 = istemci.get(f"{A}/delikli_plaka").json()
    ag = ak.ag_coz(istemci.get(f"{A}/delikli_plaka/ag").content)
    j = _x_ucgeni(ag, 200.0)
    r = istemci.post(f"{A}/delikli_plaka/sec", json={"ucgen": j})
    assert r.status_code == 200
    J1 = r.json()
    assert len(J1["secimler"]) == len(J0["secimler"]) + 1
    yeni = J1["secimler"][-1]
    assert yeni["tur"] == "duzlem" and yeni["alan"] == pytest.approx(500.0, rel=1e-9)

    r = istemci.post(
        f"{A}/delikli_plaka/kosul", json={"secim": yeni["kimlik"], "tur": "basinc", "deger": 0.0}
    )
    assert r.status_code == 200
    J2 = r.json()
    assert len(J2["kosullar"]) == len(J0["kosullar"]) + 1
    k = J2["kosullar"][-1]

    r = istemci.post(f"{A}/delikli_plaka/coz")
    assert r.status_code == 200
    J3 = r.json()
    assert J3["cozum"] is not None
    assert o.kontrol(J3["kontroller"], "denge")["durum"] == "tamam"
    assert J3["cozum"]["yuk"][0] == pytest.approx(100.0 * 500.0, rel=1e-9)  # basınç 0: yük değişmez

    r = istemci.get(f"{A}/delikli_plaka/alan")
    assert r.status_code == 200 and r.headers["content-type"].startswith(OCTET)
    alan = ak.alan_coz(r.content)
    assert float(alan["vm"].max()) == pytest.approx(J3["cozum"]["vm_max"], rel=1e-6)
    assert len(alan["u"]) == J3["ag"]["dugum"]

    govde = {"p0": [100.0, 55.5, 2.5], "p1": [100.0, 99.5, 2.5], "n": 45, "bilesen": "sxx"}
    r = istemci.post(f"{A}/delikli_plaka/sonda", json=govde)
    assert r.status_code == 200 and r.headers["content-type"].startswith(OCTET)
    S = ak.sonda_coz(r.content)
    assert len(S["s"]) == 45 and S["iceride"].tolist() == [1] * 45
    # θ = 90° doğrultusunda σxx delikten uzaklaştıkça uygulanan çekmeye (100 MPa) yaklaşır
    assert S["deger"][0] > S["deger"][-1] > 0.0

    r = istemci.delete(f"{A}/delikli_plaka/kosul/{k['kimlik']}")
    assert r.status_code == 200
    J4 = r.json()
    assert J4["kosullar"] == J1["kosullar"]
    assert J4["cozum"] is None  # koşullar değişince çözüm düşer
    assert istemci.get(f"{A}/delikli_plaka/alan").status_code == 404


@pytest.mark.occt
@pytest.mark.parametrize(
    "govde",
    [
        {"ucgen": 10**9},
        {"ucgen": -1},
        {"silindir": {"nokta": [100.0, 50.0, 0.0], "eksen": [0.0, 0.0, 0.0], "r": 5.0}},
        {"silindir": {"nokta": [100.0, 50.0, 0.0], "eksen": [0.0, 0.0, 1.0], "r": 0.0}},
    ],
    ids=["ucgen_buyuk", "ucgen_negatif", "sifir_eksen", "sifir_r"],
)
def test_sec_hatalar(istemci, govde):
    once = istemci.get(f"{A}/delikli_plaka").json()
    r = istemci.post(f"{A}/delikli_plaka/sec", json=govde)
    assert r.status_code == 422
    assert r.json()["detail"]
    assert istemci.get(f"{A}/delikli_plaka").json() == once


@pytest.mark.occt
def test_kosul_hatalar(istemci):
    J = istemci.get(f"{A}/delikli_plaka").json()
    secim = J["secimler"][0]["kimlik"]
    for govde in (
        {"secim": "yok", "tur": "mesnet", "deger": ["ux"]},
        {"secim": secim, "tur": "tork", "deger": [1.0]},
        {"secim": secim, "tur": "cekme", "deger": [1.0, 2.0]},
    ):
        r = istemci.post(f"{A}/delikli_plaka/kosul", json=govde)
        assert r.status_code == 422, govde
    kilitli = J["kosullar"][0]["kimlik"]
    assert istemci.delete(f"{A}/delikli_plaka/kosul/{kilitli}").status_code == 422
    assert istemci.delete(f"{A}/delikli_plaka/kosul/k999").status_code in (404, 422)
    assert istemci.get(f"{A}/delikli_plaka").json() == J


@pytest.mark.occt
def test_yeniden_ag(istemci):
    """`POST /ag {h}`: yeni ağ, seçimler tanımlarından yeniden uygulanır, çözüm düşer; h ≤ 0 → 422."""
    J0 = istemci.get(f"{A}/konsol_kiris").json()
    assert istemci.post(f"{A}/konsol_kiris/ag", json={"h": 0.0}).status_code == 422
    assert istemci.post(f"{A}/konsol_kiris/ag", json={"h": -2.0}).status_code == 422
    h = J0["ag"]["h"] * 1.5
    r = istemci.post(f"{A}/konsol_kiris/ag", json={"h": h})
    assert r.status_code == 200
    J = r.json()
    assert J["ag"]["h"] == h and J["cozum"] is None
    assert [s["kimlik"] for s in J["secimler"]] == [s["kimlik"] for s in J0["secimler"]]
    assert [s["alan"] for s in J["secimler"]] == pytest.approx([s["alan"] for s in J0["secimler"]], rel=1e-9)


@pytest.mark.occt
def test_sonda_hatalar(istemci):
    p = {"p0": [100.0, 55.5, 2.5], "p1": [100.0, 99.5, 2.5], "n": 10, "bilesen": "vm"}
    assert istemci.post(f"{A}/delikli_plaka/sonda", json=p).status_code == 422  # çözüm yok
    assert istemci.post(f"{A}/delikli_plaka/coz").status_code == 200
    for degisik in ({"n": 2001}, {"p1": p["p0"]}, {"bilesen": "tau"}):
        r = istemci.post(f"{A}/delikli_plaka/sonda", json={**p, **degisik})
        assert r.status_code == 422, degisik
        assert r.json()["detail"]


def test_bilinmeyen_ornek(istemci):
    pytest.importorskip("gmsh", reason="gmsh kurulu değil (pip install -e .[mesh])")
    for yontem, yol, govde in (
        ("get", "/yok", None),
        ("get", "/yok/ag", None),
        ("get", "/yok/alan", None),
        ("get", "/yok/inp", None),
        ("post", "/yok/coz", None),
        ("post", "/yok/yakinsama", None),
        ("post", "/yok/sec", {"ucgen": 0}),
    ):
        r = getattr(istemci, yontem)(f"{A}{yol}", **({} if govde is None else {"json": govde}))
        assert r.status_code == 404, yol


@pytest.mark.slow
@pytest.mark.occt
def test_yakinsama_ucu(istemci):
    r = istemci.post(f"{A}/konsol_kiris/yakinsama")
    assert r.status_code == 200
    J = r.json()
    assert len(J["yakinsama"]) == 3
    t = o.ornek("konsol_kiris")
    assert J["yakinsama"] == o.jt(ak.yakinsama(t))
    assert "yakinsama" in o.kimlikler(J["kontroller"])


# ---------------------------------------------------------------- K20: dışa aktarım


@pytest.mark.occt
def test_inp(istemci):
    from fileio.calculix import to_inp

    t = o.ornek("delikli_plaka")
    ag = ak.ag_kur(t)
    r = istemci.get(f"{A}/delikli_plaka/inp")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "delikli_plaka.inp" in r.headers["content-disposition"]
    assert r.text == to_inp(ak.model_kur(t, ag))


# ---------------------------------------------------------------- K21: önbellek ve sıfırlama


@pytest.mark.occt
def test_coz_onbellek(istemci, monkeypatch):
    """Aynı girdiyle ikinci `coz` çözücüyü yeniden çağırmaz ve aynı yanıtı verir; girdi değişince yeniden."""
    import core.solver

    gercek = core.solver.solve
    cagri: list[int] = []

    def say(model):
        cagri.append(len(model.nodes))
        return gercek(model)

    monkeypatch.setattr(core.solver, "solve", say)
    monkeypatch.setattr(ak, "solve", say, raising=False)
    monkeypatch.setattr(analiz_ekrani, "solve", say, raising=False)

    r1 = istemci.post(f"{A}/konsol_kiris/coz")
    r2 = istemci.post(f"{A}/konsol_kiris/coz")
    assert r1.status_code == r2.status_code == 200
    assert len(cagri) == 1
    assert r1.json() == r2.json()

    J = r1.json()
    secim = J["secimler"][-1]["kimlik"]
    assert (
        istemci.post(
            f"{A}/konsol_kiris/kosul", json={"secim": secim, "tur": "basinc", "deger": 0.5}
        ).status_code
        == 200
    )
    assert istemci.post(f"{A}/konsol_kiris/coz").status_code == 200
    assert len(cagri) == 2


@pytest.mark.occt
def test_sifirla(istemci):
    """`POST /api/sifirla` sonrası örnek başlangıç değerinde: eklenen seçim ve koşul yok, çözüm yok, ilk h."""
    J0 = istemci.get(f"{A}/konsol_kiris").json()
    secim = J0["secimler"][0]["kimlik"]
    assert (
        istemci.post(
            f"{A}/konsol_kiris/kosul", json={"secim": secim, "tur": "basinc", "deger": 1.0}
        ).status_code
        == 200
    )
    assert istemci.post(f"{A}/konsol_kiris/ag", json={"h": J0["ag"]["h"] * 1.5}).status_code == 200
    assert istemci.post(f"{A}/konsol_kiris/coz").status_code == 200
    assert istemci.post("/api/sifirla").status_code == 200
    J = istemci.get(f"{A}/konsol_kiris").json()
    assert J == J0
    assert J["cozum"] is None


def test_hata_eslemesi_modelerror():
    """Köprünün ModelError'ı ekran uçlarında 422'dir (A3 ortak işleyicisi); burada köprü düzeyi ön koşul."""
    with pytest.raises(ModelError):
        ak.kirsch_sxx(100.0, 5.0, 1.0)
