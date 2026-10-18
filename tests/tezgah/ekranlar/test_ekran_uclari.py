"""
SPEC 47 — ekran uçları (`/api/ekran/<ad>/...`). Bu dosyanın şimdiki kısmı 47a Plan ekranıdır:
K1 (plan kaydı ve örnek listesi), K6 (freze / tornada aç), K7 (plan hataları), K21 (sıfırlama), ayrıca
`GET /{ad}`, `/ag`, `/ne_olurdu`, `/dogrula` uçlarının köprüyle aynı yanıtı vermesi. (47b / 47c kendi
kısımlarını bu dosyaya ekler.)

Uçlar A3 kabuğuyla (`tezgah.sunucu.uygulama`, `tezgah.ekranlar`) test edilir; `[web]` ya da A3 yoksa atlanır.
Beklenen yanıtlar köprü (`_plan_kopru.PlanOturumu`) ve doğrudan SPEC 29 çağrılarıyla (`plan_ortak.planla`)
kurulur.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="[web] kurulu değil (pip install -e .[web])")
pytest.importorskip("httpx", reason="[web] kurulu değil (pip install -e .[web])")
plan_ekrani = pytest.importorskip(
    "tezgah.ekranlar.plan", reason="A3 ekran kaydı (tezgah.ekranlar.Ekran) henüz yok", exc_type=ImportError
)

from cam.model import CamError  # noqa: E402
from tests.tezgah.ekranlar import plan_ortak as o  # noqa: E402
from tezgah import kopru  # noqa: E402

pk = pytest.importorskip("tezgah.ekranlar._plan_kopru", reason="47a iskeleti (_plan_kopru) yok")
po = pytest.importorskip("tezgah.ekranlar._plan_ornekler", reason="47a iskeleti (_plan_ornekler) yok")

P = o.PLAN
OCTET = "application/octet-stream"
PARAMETRE_ADLARI = {"D", "F", "rpm", "a_p", "stepover"}


def _occt() -> bool:
    import importlib.util

    return importlib.util.find_spec("build123d") is not None


class _Uygulanmamis:
    """A3 iskeletiyken (NotImplementedError) hata testin içinde doğsun: "uygulanmamış" sayılır (conftest)."""

    def __init__(self, e: NotImplementedError):
        self.e = e

    def __getattr__(self, ad):
        raise self.e


@pytest.fixture
def istemci():
    """Keşifle kurulan kabuk (A3); her test başlangıç durumundan başlar (`POST /api/sifirla`)."""
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    try:
        c = TestClient(uygulama(dist=None))
        assert c.post("/api/sifirla").status_code == 200
    except NotImplementedError as e:
        yield _Uygulanmamis(e)
        return
    yield c
    c.post("/api/sifirla")


def _taze(ad: str) -> dict:
    """Başlangıç durumundaki örneğin `Plan`'ı (köprüden, sunucusuz)."""
    return o.jt(pk.PlanOturumu(po.ornek(ad)).json())


# ---------------------------------------------------------------- K1: kayıt ve örnek listesi


def test_kayit(istemci):
    E = plan_ekrani.EKRAN
    assert (E.ad, E.baslik, E.tus) == ("plan", "Plan", "4")
    assert E.router is not None and callable(E.hazir) and callable(E.sifirla)

    import importlib.util

    var29 = importlib.util.find_spec("cam.plan") is not None
    neden = E.hazir()
    if var29:
        assert neden is None
    else:
        assert isinstance(neden, str) and neden.strip()

    r = istemci.get("/api/ekranlar")
    assert r.status_code == 200
    satir = [e for e in r.json()["ekranlar"] if e["ad"] == "plan"]
    assert len(satir) == 1
    assert (satir[0]["tus"], satir[0]["hazir"]) == ("4", neden is None)

    r = istemci.get(f"{P}/ornekler")
    if neden is not None:
        assert r.status_code == 503  # kullanılamaz ekranın uçları (A3)
        pytest.skip(f"Plan ekranı kullanılamaz: {neden}")
    assert r.status_code == 200
    J = r.json()
    assert J["sema"] == 1
    assert list(po.ORNEKLER) == ["plan_blogu", "plan_engelli", "plan_mili"]
    assert [x["ad"] for x in J["ornekler"]] == list(po.ORNEKLER)
    x = {e["ad"]: e for e in J["ornekler"]}
    for ad, tur in (("plan_blogu", "freze"), ("plan_engelli", "freze"), ("plan_mili", "torna")):
        assert {"ad", "tur", "aciklama", "hazir", "neden"} <= set(x[ad]), x[ad]
        assert x[ad]["tur"] == tur
        assert x[ad]["aciklama"].strip()
        assert x[ad]["hazir"] == (po.hazir(ad) is None)
        assert x[ad]["neden"] == po.hazir(ad)
    # OCCT'siz örnek her kurulumda çalışır; OCCT'li örnekler OCCT yokken nedeniyle kapalı
    assert x["plan_engelli"]["hazir"] is True
    assert x["plan_blogu"]["hazir"] is _occt()
    if not _occt():
        for ad in ("plan_blogu", "plan_mili"):
            assert x[ad]["hazir"] is False
            assert "OCCT" in x[ad]["neden"]
    with pytest.raises(KeyError):
        po.ornek("yok")


# ---------------------------------------------------------------- uçlar = köprü


@pytest.mark.parametrize("ad", o.HEPSI)
def test_plan_get(istemci, ad):
    o.girdi(ad)
    r = istemci.get(f"{P}/{ad}")
    assert r.status_code == 200
    assert r.json() == _taze(ad)


def test_plan_ag_yok(istemci):
    """`plan_engelli`'de parça yok (özellik geometrisi çizilir): `/ag` 404."""
    o.girdi("plan_engelli")
    assert istemci.get(f"{P}/plan_engelli/ag").status_code == 404


@pytest.mark.occt
def test_plan_ag(istemci):
    g = o.girdi("plan_blogu")
    r = istemci.get(f"{P}/plan_blogu/ag")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(OCTET)
    V, T = pk.ag_coz(r.content)
    assert V.ndim == 2 and V.shape[1] == 3 and len(V) > 0
    assert T.ndim == 2 and T.shape[1] == 3 and len(T) > 0
    assert int(T.max()) < len(V)
    lo, hi = g.part.bbox
    assert V.min(axis=0) == pytest.approx(lo, abs=1e-4)
    assert V.max(axis=0) == pytest.approx(hi, abs=1e-4)


def test_plan_ne_olurdu_ucu(istemci):
    """`POST /ne_olurdu` köprünün yanıtını verir ve durum kalıcıdır (`GET` yeni planı döner)."""
    g = o.girdi("plan_engelli")
    govde = {"takim_kapat": [11], "secenek": {"rest": False}}
    r = istemci.post(f"{P}/plan_engelli/ne_olurdu", json=govde)
    assert r.status_code == 200
    J = r.json()
    beklenen = o.jt(pk.PlanOturumu(g).ne_olurdu(takim_kapat=[11], secenek={"rest": False}))
    assert J["plan"] == beklenen["plan"]
    assert J["fark"] == beklenen["fark"]
    assert istemci.get(f"{P}/plan_engelli").json() == J["plan"]
    r = istemci.post(f"{P}/plan_engelli/ne_olurdu", json={"takim_ac": [11]})
    assert r.status_code == 200
    assert r.json()["plan"]["secenekler"]["rest"] is False  # seçenek kalıcı, takım yeniden açık
    assert {t["id"]: t["acik"] for t in r.json()["plan"]["takimlar"]}[11] is True


@pytest.mark.slow
@pytest.mark.occt
def test_plan_dogrula_ucu(istemci):
    g = o.girdi("plan_blogu")
    r1 = istemci.post(f"{P}/plan_blogu/dogrula")
    assert r1.status_code == 200
    J = r1.json()
    assert J["dogrulama"] is not None
    assert J == o.jt(pk.PlanOturumu(g).dogrula())
    r2 = istemci.post(f"{P}/plan_blogu/dogrula")
    assert r2.json() == J


# ---------------------------------------------------------------- K6: freze / tornada aç


def _hareket_anahtari(hs: list[dict]) -> list[tuple]:
    return [(h["g"], h["a"], h["b"], h.get("c"), h["F"], h["islem"]) for h in hs]


def _beklenen_is(g, plan, bag: int, ad: str) -> kopru.IsTanimi:
    """Bağlama `bag`'ın işlemleri sırasıyla (SPEC 47 "Freze ekranında aç"); hareketler parametresiz."""
    ops = [op for op in plan.ops if op.setup == bag]
    assert [op.op for op in ops] == plan.ops_for(bag)
    return kopru.IsTanimi(
        ad=ad,
        kurulum=plan.setups[bag],
        malzeme=g.malzeme,
        islemler=[kopru.Islem(anahtar=op.kind, ad=op.name, op=op.op) for op in ops],
    )


def _ac_ve_denetle(istemci, g, plan, bag: int) -> dict:
    ad = f"{g.ad}-{bag + 1}"
    r = istemci.post(f"{P}/{g.ad}/ac", json={"bag": bag})
    assert r.status_code == 200
    assert r.json()["adres"] == f"#/freze?is={ad}"
    assert ad in istemci.get("/api/isler").json()["isler"]
    r = istemci.get(f"/api/is/{ad}")
    assert r.status_code == 200
    J = r.json()
    beklenen = _beklenen_is(g, plan, bag, ad)
    assert _hareket_anahtari(J["hareketler"]) == _hareket_anahtari(o.jt(kopru.hareketler(beklenen)))
    ops = [op for op in plan.ops if op.setup == bag]
    assert [i["ad"] for i in J["islemler"]] == [op.name for op in ops]
    assert [i["anahtar"] for i in J["islemler"]] == [op.kind for op in ops]
    for i, op in zip(J["islemler"], ops, strict=True):
        assert set(i["parametreler"]) <= PARAMETRE_ADLARI
        assert i["parametreler"]["D"] == g.lib.get(op.tool_id).D
    s = plan.setups[bag]
    assert J["kurulum"]["wcs"] == s.wcs.code
    stok = J["kurulum"]["stok"]
    st = s.stock
    assert (stok["x0"], stok["x1"], stok["y0"], stok["y1"], stok["z0"], stok["z1"]) == (
        st.xmin,
        st.xmax,
        st.ymin,
        st.ymax,
        st.zmin,
        st.zmax,
    )
    return J


def test_plan_ac_engelli(istemci):
    """OCCT'siz: `plan_engelli` bağlama 1'i freze iş deposuna girer, hareketleri `ops_for(0)` ile birebir."""
    g = o.girdi("plan_engelli")
    _ac_ve_denetle(istemci, g, o.planla(g), 0)


@pytest.mark.occt
def test_plan_ac(istemci):
    """`plan_blogu`: iki bağlama iki iş; hedef parça ağı geçer → SPEC 24 `cakma` kontrolü `tamam`."""
    g = o.girdi("plan_blogu")
    plan = o.planla(g)
    assert len(plan.setups) == 2
    J = _ac_ve_denetle(istemci, g, plan, 0)
    cakma = [k for k in J["kontroller"] if k["kimlik"] == "cakma"]
    assert len(cakma) == 1 and cakma[0]["durum"] == "tamam", cakma
    _ac_ve_denetle(istemci, g, plan, 1)


@pytest.mark.occt
def test_plan_ac_torna(istemci):
    """`plan_mili`: torna planı torna ekranında açılır (`#/torna?is=...`) ve iş listesinde görünür."""
    o.girdi("plan_mili")
    r = istemci.post(f"{P}/plan_mili/ac", json={"bag": 0})
    assert r.status_code == 200
    adres = r.json()["adres"]
    assert adres == "#/torna?is=plan_mili-1"
    assert "plan_mili-1" in istemci.get("/api/isler").json()["isler"]


@pytest.mark.parametrize("bag", [1, 5, -1])
def test_plan_ac_bilinmeyen_baglama(istemci, bag):
    """`plan_engelli` tek bağlamalı: bilinmeyen bağlama → 422, iş eklenmez."""
    g = o.girdi("plan_engelli")
    assert len(o.planla(g).setups) == 1
    once = istemci.get("/api/isler").json()["isler"]
    r = istemci.post(f"{P}/plan_engelli/ac", json={"bag": bag})
    assert r.status_code == 422
    assert istemci.get("/api/isler").json()["isler"] == once


# ---------------------------------------------------------------- K7: plan hataları


def _cam_hatasi(f) -> str:
    with pytest.raises(CamError) as e:
        f()
    return str(e.value)


@pytest.mark.parametrize(
    "secenek",
    [{"n_max": 0}, {"n_max": -100.0}, {"plunge_ratio": 0}, {"strict": True}],
    ids=["n_max0", "n_max_negatif", "plunge0", "strict"],
)
def test_plan_hatalar_secenek(istemci, secenek):
    """Geçersiz seçenek ve `strict` + planlanamayan → 422, metin çekirdeğin `CamError`'ı; durum değişmez."""
    g = o.girdi("plan_engelli")
    once = istemci.get(f"{P}/plan_engelli").json()
    metin = _cam_hatasi(lambda: o.planla(g, secenekler=secenek))
    r = istemci.post(f"{P}/plan_engelli/ne_olurdu", json={"secenek": secenek})
    assert r.status_code == 422
    assert r.json()["detail"] == metin
    assert istemci.get(f"{P}/plan_engelli").json() == once


def test_plan_hatalar_takim(istemci):
    g = o.girdi("plan_engelli")
    once = istemci.get(f"{P}/plan_engelli").json()
    metin = _cam_hatasi(lambda: pk.kutuphane_suz(g.lib, frozenset({999})))
    r = istemci.post(f"{P}/plan_engelli/ne_olurdu", json={"takim_kapat": [999]})
    assert r.status_code == 422
    assert r.json()["detail"] == metin
    assert istemci.get(f"{P}/plan_engelli").json() == once


@pytest.mark.parametrize(
    "yontem, yol, govde",
    [
        ("get", "/yok", None),
        ("get", "/yok/ag", None),
        ("post", "/yok/ne_olurdu", {}),
        ("post", "/yok/dogrula", None),
        ("post", "/yok/ac", {"bag": 0}),
    ],
)
def test_plan_bilinmeyen_ornek(istemci, yontem, yol, govde):
    o.spec29()
    r = getattr(istemci, yontem)(f"{P}{yol}", **({} if govde is None else {"json": govde}))
    assert r.status_code == 404


# ---------------------------------------------------------------- K21: sıfırlama


def test_plan_sifirla(istemci):
    """`POST /api/sifirla` sonrası örnek başlangıçta: kapatılan takım açık, seçenekler örnekteki gibi."""
    g = o.girdi("plan_engelli")
    r = istemci.post(f"{P}/plan_engelli/ne_olurdu", json={"takim_kapat": [11], "secenek": {"rest": False}})
    assert r.status_code == 200
    assert istemci.post(f"{P}/plan_engelli/ac", json={"bag": 0}).status_code == 200
    assert istemci.post("/api/sifirla").status_code == 200
    J = istemci.get(f"{P}/plan_engelli").json()
    assert J == _taze("plan_engelli")
    assert all(t["acik"] for t in J["takimlar"])
    for k, v in g.secenekler.items():
        assert J["secenekler"][k] == v
    assert "plan_engelli-1" not in istemci.get("/api/isler").json()["isler"]  # dinamik iş silinir (A3)
