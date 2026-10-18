"""SPEC 65b — Tezgah'ta gerçekçi malzeme görünümü (PBR): tezgah/gorunum.py ve GET /api/gorunum (K1–K4, K10).

Testler yalnız onaylı SPEC metninden (specs/65b-pbr-gorunum.md) ve iskeletin arayüzünden yazıldı; fonksiyon
gövdeleri okunmadı. Saf Python, OCCT gerekmez. Uydurma malzeme kayıtları (id "DENEME-…") yalnız çözümleme
sırasını sınar; gerçek kayıtlar (C45 = "1.0503", "EN-AW-6061-T6", "POM-C") SPEC 66 kütüphanesinden okunur.

Bağımlılıklar henüz yokken testler atlanmaz, "uygulanmamış" düşer (NotImplementedError; CI'da kırmızı):
- B2 `Malzeme` kurulumu iskelette NotImplementedError verir.
- SPEC 66 `malzeme.kutuphane` yoksa `_kutuphane()` NotImplementedError verir.
- `/api/gorunum` ucu uygulamada yoksa `_istemci()` NotImplementedError verir.

Varsayımlar (metinde açık değil):
- Kullanıcı tablosu dosyası (on_ayarlar(yol)) {anahtar: Gorunum.to_dict()} biçiminde JSON'dur; clearcoat ve
  anisotropy verilmezse 0.
- Varsayılan gri tablodan gelmez (anahtar biçimleri yalnız grup:/id:/bitim:):
  coz(None, tablo={}) == coz(None).
- Tabloda "bitim:" anahtarı yokken coz(m, bitim) == bitim_uygula(coz(m), bitim).
- montaj sözlüğü Assembly.to_dict biçimindedir ("components" listesi, bileşende "name", "material");
  yüz bitimi bileşende "gorunum": {"bitim": {"<FaceRef str>": bitim}}. Yanıtta "yuzler" yalnız bitimi
  olan yüzleri str(FaceRef) anahtarıyla taşır; bitimsiz bileşende {}.
- Uç: GET /api/gorunum?montaj=ornek Görünüm sekmesinin örnek montajını döndürür; bileşen adları
  "govde" (1.0503), "kapak" (EN-AW-6061-T6, tam bir yüzü eloksal), "blok" (POM-C). Bilinmeyen montaj → 404.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

import tezgah.gorunum as gm
from core.model import ModelError
from malzeme.model import GRUPLAR, Malzeme
from tezgah.gorunum import BITIMLER, Gorunum, bitim_uygula, coz, montaj_gorunumu, on_ayarlar

KOK = Path(__file__).resolve().parents[2]
RENK = re.compile(r"#[0-9a-fA-F]{6}")
METALLER = ("celik", "paslanmaz", "dokme_demir", "aluminyum", "bakir", "titanyum", "nikel")
ALANLAR = {"renk", "metalness", "roughness", "clearcoat", "anisotropy"}

C45, AL6061, POM = "1.0503", "EN-AW-6061-T6", "POM-C"

# Uydurma görünümler (çözümleme sırasını ayırt etmek için hepsi farklı)


def G_GRUP() -> Gorunum:
    return Gorunum("#404040", 1.0, 0.5)


def G_ID() -> Gorunum:
    return Gorunum("#a0a0b0", 1.0, 0.3)


def G_GECERSIZ() -> Gorunum:
    return Gorunum("#c03020", 0.0, 0.4, clearcoat=0.5)


def malzeme(id: str, grup: str) -> Malzeme:
    """Uydurma, yalnız id ve grubu anlamlı kayıt."""
    return Malzeme(
        id=id,
        name=f"Deneme {id}",
        standart="",
        grup=grup,
        kaynak="uydurma test kaydı",
        iso513=None if grup == "plastik" else "P",
    )


def tablo() -> dict[str, Gorunum]:
    return {"grup:celik": G_GRUP(), "id:DENEME-ID": G_ID()}


def _kutuphane():
    """SPEC 66 kütüphanesi; yoksa NotImplementedError (test "uygulanmamış")."""
    try:
        from malzeme.kutuphane import kutuphane
    except ImportError as e:
        raise NotImplementedError("SPEC 66: malzeme.kutuphane henüz yok") from e
    return kutuphane()


def _gri_mi(g: Gorunum) -> bool:
    r, gg, b = (int(g.renk[i : i + 2], 16) for i in (1, 3, 5))
    return r == gg == b


# ---------- Gorunum ----------


def test_bitimler():
    assert BITIMLER == ("ham", "frezelenmis", "taslanmis", "parlatilmis", "eloksal", "boyali", "kumlanmis")


def test_model_error_disa_acik():
    assert gm.ModelError is ModelError


def test_gorunum_varsayilanlar_ve_to_dict():
    g = Gorunum("#112233", 1.0, 0.25)
    assert g.clearcoat == 0.0 and g.anisotropy == 0.0
    d = g.to_dict()
    assert set(d) == ALANLAR
    assert d == {"renk": "#112233", "metalness": 1.0, "roughness": 0.25, "clearcoat": 0.0, "anisotropy": 0.0}
    assert json.loads(json.dumps(d)) == d
    assert Gorunum(**d) == g


def test_gorunum_dondurulmus_ve_hash():
    g = Gorunum("#112233", 1.0, 0.25)
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.roughness = 0.1  # type: ignore[misc]
    assert hash(g) == hash(Gorunum("#112233", 1.0, 0.25))


@pytest.mark.parametrize(
    "kw",
    [
        {"renk": "#fff"},
        {"renk": "kirmizi"},
        {"renk": "112233"},
        {"renk": "#11223g"},
        {"metalness": 1.5},
        {"metalness": -0.1},
        {"roughness": 1.01},
        {"roughness": math.nan},
        {"clearcoat": 2.0},
        {"anisotropy": -1.0},
        {"anisotropy": math.inf},
    ],
)
def test_gorunum_dogrulama(kw):
    """Renk 7 karakterli onaltılık; sayılar sonlu ve [0, 1] içinde; değilse ModelError."""
    alanlar = {"renk": "#808080", "metalness": 0.0, "roughness": 0.5, "clearcoat": 0.0, "anisotropy": 0.0}
    alanlar.update(kw)
    with pytest.raises(ModelError):
        Gorunum(**alanlar)


def test_gorunum_sinir_degerleri_gecerli():
    Gorunum("#000000", 0.0, 0.0, clearcoat=0.0, anisotropy=0.0)
    Gorunum("#FFFFFF", 1.0, 1.0, clearcoat=1.0, anisotropy=1.0)


# ---------- K1 ön ayar tablosu ----------


def test_k1_her_grup_icin_on_ayar():
    t = on_ayarlar()
    for g in GRUPLAR:
        assert f"grup:{g}" in t, g
        assert isinstance(t[f"grup:{g}"], Gorunum)


def test_k1_anahtar_bicimi_ve_degerler_aralikta():
    t = on_ayarlar()
    for anahtar, g in t.items():
        tur, _, ad = anahtar.partition(":")
        assert tur in ("grup", "id", "bitim") and ad, anahtar
        if tur == "grup":
            assert ad in GRUPLAR, anahtar
        if tur == "bitim":
            assert ad in BITIMLER, anahtar
        assert isinstance(g, Gorunum)
        assert RENK.fullmatch(g.renk), (anahtar, g.renk)
        for alan in ("metalness", "roughness", "clearcoat", "anisotropy"):
            v = getattr(g, alan)
            assert math.isfinite(v) and 0.0 <= v <= 1.0, (anahtar, alan, v)


def test_k1_metal_ve_plastik():
    t = on_ayarlar()
    for g in METALLER:
        assert t[f"grup:{g}"].metalness == 1.0, g
    assert t["grup:plastik"].metalness == 0.0


# ---------- K2 çözümleme sırası ----------


def test_k2_malzemesiz_varsayilan_gri():
    g = coz(None)
    assert isinstance(g, Gorunum)
    assert _gri_mi(g)
    assert coz(None, tablo={}) == g
    assert coz(None, tablo=tablo()) == g


def test_k2_grup_on_ayari():
    assert coz(malzeme("DENEME-GRUP", "celik"), tablo=tablo()) == G_GRUP()


def test_k2_id_grubu_ezer():
    assert coz(malzeme("DENEME-ID", "celik"), tablo=tablo()) == G_ID()


def test_k2_grup_yoksa_gri():
    """Ne id ne grup ön ayarı olan malzeme varsayılan griye düşer."""
    assert coz(malzeme("DENEME-BAKIR", "bakir"), tablo=tablo()) == coz(None, tablo=tablo())


def test_k2_gecersiz_kilma_ikisini_de_ezer():
    t = tablo()
    assert coz(malzeme("DENEME-ID", "celik"), gecersiz=G_GECERSIZ(), tablo=t) == G_GECERSIZ()
    assert coz(malzeme("DENEME-GRUP", "celik"), gecersiz=G_GECERSIZ(), tablo=t) == G_GECERSIZ()
    assert coz(None, gecersiz=G_GECERSIZ(), tablo=t) == G_GECERSIZ()


def test_k2_bitim_en_son():
    t = tablo()
    m = malzeme("DENEME-ID", "celik")
    for b in BITIMLER:
        assert coz(m, b, tablo=t) == bitim_uygula(G_ID(), b), b
        assert coz(m, b, G_GECERSIZ(), tablo=t) == bitim_uygula(G_GECERSIZ(), b), b
    assert coz(None, "ham", tablo=t) == bitim_uygula(coz(None, tablo=t), "ham")


def test_k2_bilinmeyen_bitim():
    with pytest.raises(ModelError):
        coz(None, "krom")
    with pytest.raises(ModelError):
        coz(malzeme("DENEME-ID", "celik"), "krom", tablo=tablo())
    with pytest.raises(ModelError):
        bitim_uygula(G_GRUP(), "krom")


def test_k2_varsayilan_tablo_on_ayarlar():
    """tablo verilmezse on_ayarlar() kullanılır."""
    t = on_ayarlar()
    m = malzeme("DENEME-YOK", "aluminyum")
    assert coz(m) == t["grup:aluminyum"]


def test_k2_kullanici_tablosu_anahtar_bazinda_ezer(tmp_path):
    yerlesik = on_ayarlar()
    yol = tmp_path / "gorunum.json"
    yeni_celik = Gorunum("#123456", 1.0, 0.15, anisotropy=0.2)
    yeni_id = Gorunum("#654321", 0.0, 0.9)
    yol.write_text(
        json.dumps({"grup:celik": yeni_celik.to_dict(), "id:DENEME-ATOLYE": yeni_id.to_dict()}),
        encoding="utf-8",
    )
    t = on_ayarlar(yol)
    assert t["grup:celik"] == yeni_celik
    assert t["id:DENEME-ATOLYE"] == yeni_id
    for anahtar, g in yerlesik.items():
        if anahtar != "grup:celik":
            assert t[anahtar] == g, anahtar
    assert set(t) == set(yerlesik) | {"id:DENEME-ATOLYE"}
    # yerleşik tablo değişmedi
    assert on_ayarlar() == yerlesik
    assert coz(malzeme("DENEME-ATOLYE", "celik"), tablo=t) == yeni_id
    assert coz(malzeme("DENEME-X", "celik"), tablo=t) == yeni_celik


def test_k2_kullanici_tablosu_eksik_alanlar_varsayilan(tmp_path):
    yol = tmp_path / "gorunum.json"
    yol.write_text(json.dumps({"grup:plastik": {"renk": "#eeeeee", "metalness": 0.0, "roughness": 0.7}}))
    assert on_ayarlar(yol)["grup:plastik"] == Gorunum("#eeeeee", 0.0, 0.7)


@pytest.mark.parametrize(
    "icerik",
    [
        "{bozuk json",
        json.dumps({"renk:celik": {"renk": "#808080", "metalness": 1.0, "roughness": 0.5}}),
        json.dumps({"grup:tahta": {"renk": "#808080", "metalness": 0.0, "roughness": 0.5}}),
        json.dumps({"bitim:krom": {"renk": "#808080", "metalness": 1.0, "roughness": 0.1}}),
        json.dumps({"grup:celik": {"renk": "#808080", "metalness": 1.0, "roughness": 1.5}}),
        json.dumps({"grup:celik": {"renk": "gri", "metalness": 1.0, "roughness": 0.5}}),
    ],
)
def test_k2_kullanici_tablosu_hatali(tmp_path, icerik):
    """Bozuk dosya, bilinmeyen anahtar biçimi veya aralık dışı değer → ModelError."""
    yol = tmp_path / "gorunum.json"
    yol.write_text(icerik, encoding="utf-8")
    with pytest.raises(ModelError):
        on_ayarlar(yol)


# ---------- K3 bitim dönüşümleri ----------


def celik() -> Gorunum:
    return on_ayarlar()["grup:celik"]


def test_k3_puruzluluk_sirasi():
    g = celik()
    t, f, h = (bitim_uygula(g, b).roughness for b in ("taslanmis", "frezelenmis", "ham"))
    assert t < f < h
    p = bitim_uygula(g, "parlatilmis").roughness
    for b in BITIMLER:
        if b != "parlatilmis":
            assert p < bitim_uygula(g, b).roughness, b


def test_k3_eloksal_clearcoat():
    assert bitim_uygula(celik(), "eloksal").clearcoat == 1.0
    assert bitim_uygula(on_ayarlar()["grup:aluminyum"], "eloksal").clearcoat == 1.0


def test_k3_metindeki_degerler():
    """Arayüz yorumundaki değerler (çelik temel üstünde)."""
    g = celik()
    assert bitim_uygula(g, "ham").roughness == pytest.approx(0.6)
    fr = bitim_uygula(g, "frezelenmis")
    assert (fr.roughness, fr.anisotropy) == (pytest.approx(0.35), pytest.approx(0.3))
    ta = bitim_uygula(g, "taslanmis")
    assert (ta.roughness, ta.anisotropy) == (pytest.approx(0.2), pytest.approx(0.6))
    assert bitim_uygula(g, "parlatilmis").roughness == pytest.approx(0.05)
    el = bitim_uygula(g, "eloksal")
    assert el.metalness == pytest.approx(0.6)
    bo = bitim_uygula(g, "boyali")
    assert (bo.metalness, bo.clearcoat) == (0.0, pytest.approx(0.5))
    assert bitim_uygula(g, "kumlanmis").roughness == pytest.approx(0.8)


def test_k3_belirlenimci():
    g = celik()
    for b in BITIMLER:
        a = bitim_uygula(g, b)
        assert isinstance(a, Gorunum)
        assert a == bitim_uygula(g, b) == bitim_uygula(Gorunum(**g.to_dict()), b), b
    assert g == celik()  # temel değişmedi


# ---------- K4 montaj görünümü ve API ----------


def ornek_montaj() -> dict:
    return {
        "name": "ornek",
        "components": [
            {"name": "govde", "part": "govde.step", "T": _I4, "fixed": True, "material": C45},
            {
                "name": "kapak",
                "part": "kapak.step",
                "T": _I4,
                "fixed": False,
                "material": AL6061,
                "gorunum": {"bitim": {"kapak:ust": "eloksal"}},
            },
            {"name": "pim", "part": "pim.step", "T": _I4, "fixed": False},
        ],
        "mates": [],
    }


_I4 = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def test_k4_montaj_gorunumu():
    kut = _kutuphane()
    c45, al = kut.get(C45), kut.get(AL6061)
    beklenen = {
        "govde": {"gorunum": coz(c45).to_dict(), "yuzler": {}},
        "kapak": {"gorunum": coz(al).to_dict(), "yuzler": {"kapak:ust": coz(al, "eloksal").to_dict()}},
        "pim": {"gorunum": coz(None).to_dict(), "yuzler": {}},
    }
    sonuc = montaj_gorunumu(ornek_montaj())
    assert sonuc == beklenen
    assert json.loads(json.dumps(sonuc)) == beklenen
    # metal gövde metal, eloksal yüz clearcoat 1
    assert sonuc["govde"]["gorunum"]["metalness"] == 1.0
    assert sonuc["kapak"]["yuzler"]["kapak:ust"]["clearcoat"] == 1.0


def test_k4_montaj_gorunumu_kullanici_tablosu():
    kut = _kutuphane()
    t = dict(on_ayarlar())
    t[f"id:{C45}"] = G_ID()
    sonuc = montaj_gorunumu(ornek_montaj(), tablo=t)
    assert sonuc["govde"]["gorunum"] == G_ID().to_dict()
    assert sonuc["kapak"]["gorunum"] == coz(kut.get(AL6061), tablo=t).to_dict()


def test_k4_bilinmeyen_malzeme_id():
    _kutuphane()
    m = ornek_montaj()
    m["components"][0]["material"] = "DENEME-KAYITTA-YOK"
    with pytest.raises(ModelError):
        montaj_gorunumu(m)


def test_k4_bilinmeyen_bitim():
    _kutuphane()
    m = ornek_montaj()
    m["components"][1]["gorunum"]["bitim"]["kapak:ust"] = "krom"
    with pytest.raises(ModelError):
        montaj_gorunumu(m)


def _istemci():
    """GET /api/gorunum'lu test istemcisi. [web] yoksa atlanır; uç yoksa "uygulanmamış"."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    app = uygulama(dist=None)
    if "/api/gorunum" not in {getattr(r, "path", None) for r in app.routes}:
        raise NotImplementedError("SPEC 65b: GET /api/gorunum ucu henüz yok")
    return TestClient(app)


def test_k4_api_ornek_montaj():
    """Görünüm sekmesinin örnek montajı: C45 gövde, bir yüzü eloksal 6061 kapak, POM blok."""
    istemci = _istemci()
    kut = _kutuphane()
    r = istemci.get("/api/gorunum", params={"montaj": "ornek"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"govde", "kapak", "blok"}
    for ad in d:
        assert set(d[ad]) == {"gorunum", "yuzler"}, ad
    assert d["govde"]["gorunum"] == coz(kut.get(C45)).to_dict()
    assert d["blok"]["gorunum"] == coz(kut.get(POM)).to_dict()
    al = kut.get(AL6061)
    assert d["kapak"]["gorunum"] == coz(al).to_dict()
    yuzler = d["kapak"]["yuzler"]
    assert len(yuzler) == 1
    (ref, g), *_ = yuzler.items()
    assert ":" in ref  # str(FaceRef) "özellik:ad"
    assert g == coz(al, "eloksal").to_dict()
    assert g["clearcoat"] == 1.0
    assert d["govde"]["gorunum"]["metalness"] == 1.0
    assert d["blok"]["gorunum"]["metalness"] == 0.0


def test_k4_api_bilinmeyen_montaj():
    r = _istemci().get("/api/gorunum", params={"montaj": "boyle-bir-montaj-yok"})
    assert r.status_code == 404


def sema_yolu(ref: str) -> list[str]:
    return ref.removeprefix("#/").split("/")


def _alt_semalar(sema, belge: dict, gorulen: set[str]):
    """Şemanın içinden geçen tüm alt şemalar ($ref'ler çözülerek)."""
    if isinstance(sema, dict):
        if "$ref" in sema and sema["$ref"] not in gorulen:
            gorulen.add(sema["$ref"])
            hedef = belge
            for parca in sema_yolu(sema["$ref"]):
                hedef = hedef[parca]
            yield from _alt_semalar(hedef, belge, gorulen)
        yield sema
        for v in sema.values():
            yield from _alt_semalar(v, belge, gorulen)
    elif isinstance(sema, list):
        for v in sema:
            yield from _alt_semalar(v, belge, gorulen)


def test_k4_openapi_semasi():
    """Uç ve Gorunum alanları OpenAPI'de tipli görünür (MES tip üretimi için)."""
    belge = _istemci().get("/api/openapi.json").json()
    uc = belge["paths"]["/api/gorunum"]["get"]
    assert any(p["name"] == "montaj" and p["in"] == "query" for p in uc.get("parameters", []))
    sema = uc["responses"]["200"]["content"]["application/json"]["schema"]
    ozellikler = [set(s.get("properties", {})) for s in _alt_semalar(sema, belge, set())]
    assert any(ALANLAR <= o for o in ozellikler), "Gorunum alanları yanıt şemasında yok"


# ---------- K10 bağımlılık ----------


def test_k10_occt_yuklemez():
    """import tezgah.gorunum OCCT / build123d yüklemez (saf Python)."""
    kod = (
        "import sys, tezgah.gorunum\n"
        "kok = {m.split('.')[0] for m in sys.modules}\n"
        "yasak = sorted(kok & {'build123d', 'OCP', 'pyvista', 'matplotlib'})\n"
        "print(','.join(yasak))\n"
    )
    r = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, check=True, cwd=KOK)
    assert r.stdout.strip() == ""
