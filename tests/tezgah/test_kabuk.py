"""SPEC 37 — kabuk testleri (sahte ekranlarla): sıra, yayılım, etki, önbellek, geri çevirme, önizleme,
değişiklik yakalama, REST uçları ve bağımlılık kuralı (K9–K13, K17).

Testler yalnız specs/37-proje-kabuk.md ve specs/24a-ekran-kaydi.md'den (A3 kaydı) yazıldı;
tezgah/ekranlar/kabuk.py gövdesi okunmadı. Gerçek 24/25/26 ekranlarına bağlı değildir.

Varsayımlar (SPEC'in açık bıraktığı yerler):
- `Kabuk(ekranlar)` kurulurken bölümü olan her ekranın o anki `disa_aktar()` belgesi projenin bölümü olur
  (yama yapılabilmesi için gerekli); kurulumda yapılan `ice_aktar` çağrıları sayılmaz.
- Uygulama A3 `tezgah.sunucu.uygulama(dist=None, ekranlar=[...])` ile, sahte ekranlar + `kabuk.EKRAN` ile
  kurulur; sahte ekranların uçları `/api/ekran/<ad>/...` altındadır (A3 URL kararı).
- Sahte bağımlı ekranlar girdilerini test içinde doğrudan sahte nesneden okur (A3 `paylasilan_bolum` yerine).
- Geri çevirmede ekranlar topolojik sırayla eski belgelerini alır (bağımlı ekran eski girdiyle kurulur).
"""

from __future__ import annotations

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import APIRouter, HTTPException  # noqa: E402

from cam.model import CamError  # noqa: E402
from fileio.proje import ProjeError, ac, kanonik, ozet  # noqa: E402
from tezgah.ekranlar import Ekran  # noqa: E402
from tezgah.ekranlar import kabuk as kabuk_mod  # noqa: E402

KOK = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Sahte ekranlar
#
#   kok → orta → uc,   kok → yan,   ayri (bağımsız)
# (SPEC'teki a → b → c, a → d, e; adlar hata metninde ayırt edilsin diye uzun.)
# ---------------------------------------------------------------------------


class _Sahte:
    """Durumu `{"sema": 1, "v": float}` olan sahte ekran. `toplam` girdilerinden türetilir (belirlenimci)."""

    def __init__(self, ad: str, v: float, gunluk: list[str], bagimli: tuple[str, ...] = ()):
        self.ad = ad
        self.belge = {"sema": 1, "v": v}
        self.gunluk = gunluk
        self.bagimli = bagimli
        self.girdiler: list[_Sahte] = []
        self.alinan: list[tuple[dict, dict]] = []  # (belge, onbellek)
        self.hata_v: float | None = None  # girdi `kok.v` bu değerse ice_aktar CamError
        self.onbellek_ver = False
        self.onbellek_ihlali: list[str] = []

    # türetilmiş
    def toplam(self, belge: dict | None = None) -> float:
        b = self.belge if belge is None else belge
        return b["v"] + sum(g.toplam() for g in self.girdiler)

    def _onbellek_verisi(self, belge: dict) -> bytes:
        return json.dumps([belge, [g.belge for g in self.girdiler]], sort_keys=True).encode()

    # Ekran kancaları
    def disa_aktar(self) -> dict:
        return copy.deepcopy(self.belge)

    def ice_aktar(self, belge: dict, onbellek) -> None:
        self.gunluk.append(self.ad)
        onb = dict(onbellek)
        self.alinan.append((copy.deepcopy(belge), onb))
        for anahtar, veri in onb.items():
            if veri != self._onbellek_verisi(belge):
                self.onbellek_ihlali.append(anahtar)
        if self.hata_v is not None and any(g.belge["v"] == self.hata_v for g in self._tum_girdiler()):
            raise CamError(f"{self.ad} hesaplanamadı (test)")
        if not isinstance(belge.get("v"), (int, float)):
            raise CamError(f"{self.ad}: v sayı değil")
        self.belge = copy.deepcopy(belge)

    def _tum_girdiler(self):
        for g in self.girdiler:
            yield g
            yield from g._tum_girdiler()

    def ozet(self) -> dict:
        t = self.toplam()
        return {"toplam": t, "v": self.belge["v"], "etiket": f"{self.ad}={t}"}

    def onbellek(self) -> dict[str, bytes]:
        if not self.onbellek_ver:
            return {}
        return {f"{self.ad}.sonuc": self._onbellek_verisi(self.belge)}

    def ekran(self, router: APIRouter | None = None) -> Ekran:
        return Ekran(
            ad=self.ad,
            baslik=self.ad.capitalize(),
            router=router,
            bolum=self.ad,
            bagimli=self.bagimli,
            disa_aktar=self.disa_aktar,
            ice_aktar=self.ice_aktar,
            ozet=self.ozet,
            onbellek=self.onbellek,
        )


def _router(s: _Sahte) -> APIRouter:
    r = APIRouter()

    @r.post("/ayarla")
    def ayarla(govde: dict) -> dict:
        if "v" not in govde:
            raise HTTPException(status_code=400, detail="v yok")
        s.belge = {"sema": 1, "v": float(govde["v"])}
        return s.belge

    @r.get("/durum")
    def durum() -> dict:
        return s.belge

    @r.get("/dokun")
    def dokun() -> dict:
        s.belge = {"sema": 1, "v": s.belge["v"] + 100.0}
        return s.belge

    return r


def _sahteler() -> tuple[dict[str, _Sahte], list[str]]:
    gunluk: list[str] = []
    s = {
        "kok": _Sahte("kok", 1.0, gunluk),
        "orta": _Sahte("orta", 10.0, gunluk, ("kok",)),
        "uc": _Sahte("uc", 100.0, gunluk, ("orta",)),
        "yan": _Sahte("yan", 1000.0, gunluk, ("kok",)),
        "ayri": _Sahte("ayri", 5.0, gunluk),
    }
    s["orta"].girdiler = [s["kok"]]
    s["uc"].girdiler = [s["orta"]]
    s["yan"].girdiler = [s["kok"]]
    return s, gunluk


def _yama(bolum: str, deger, isaretci: str = "/v") -> list[dict]:
    return [{"bolum": bolum, "isaretci": isaretci, "deger": deger}]


def _kabuk(s: dict[str, _Sahte]):
    k = kabuk_mod.Kabuk([x.ekran() for x in s.values()])
    return k


def _kanon(x) -> bytes:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _durumlar(s: dict[str, _Sahte]) -> bytes:
    return _kanon({ad: x.disa_aktar() for ad, x in s.items()})


def _istemci(s: dict[str, _Sahte]):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    ekranlar = [x.ekran(_router(x)) for x in s.values()] + [kabuk_mod.EKRAN]
    return TestClient(uygulama(dist=None, ekranlar=ekranlar))


def _proje_baytlari(c, tmp_path: Path) -> bytes:
    """GET /api/proje/indir → .3dc; bölümler + geçmiş kanonik baytları (önbellek hariç)."""
    r = c.get("/api/proje/indir")
    assert r.status_code == 200
    yol = tmp_path / f"indir_{len(list(tmp_path.iterdir()))}.3dc"
    yol.write_bytes(r.content)
    p = ac(yol)
    return _kanon(
        {
            "bolumler": {k: v for k, v in p.bolumler.items()},
            "gecmis": {"kayitlar": [dict(k) for k in p.gecmis.kayitlar], "konum": p.gecmis.konum},
        }
    )


def _gecmis(c) -> dict:
    r = c.get("/api/proje/gecmis")
    assert r.status_code == 200
    return r.json()


# ---------------------------------------------------------------------------
# Sabitler, girdi özeti
# ---------------------------------------------------------------------------


def test_constants():
    assert kabuk_mod.ONEK == "/api/proje"
    assert kabuk_mod.ETIKET_BASLIGI == "X-Tezgah-Etiket"
    assert kabuk_mod.ONBELLEK_SINIRI == 256 * 1024 * 1024
    assert kabuk_mod.EKRAN.ad == "kabuk"
    assert kabuk_mod.EKRAN.bolum == "kabuk"
    assert kabuk_mod.EKRAN.kur is not None


def test_input_digest():
    s, _ = _sahteler()
    bolumler = {ad: x.disa_aktar() for ad, x in s.items()}
    e = s["orta"].ekran()
    assert kabuk_mod.girdi_ozeti(e, bolumler) == ozet({"orta": bolumler["orta"], "kok": bolumler["kok"]})
    assert kabuk_mod.girdi_ozeti(s["kok"].ekran(), bolumler) == ozet({"kok": bolumler["kok"]})
    # girdisi değişince özet değişir, ilgisiz bölüm değişince değişmez
    b2 = copy.deepcopy(bolumler)
    b2["kok"]["v"] = 2.0
    assert kabuk_mod.girdi_ozeti(e, b2) != kabuk_mod.girdi_ozeti(e, bolumler)
    b3 = copy.deepcopy(bolumler)
    b3["ayri"]["v"] = 2.0
    assert kabuk_mod.girdi_ozeti(e, b3) == kabuk_mod.girdi_ozeti(e, bolumler)


# ---------------------------------------------------------------------------
# K9 Sıra
# ---------------------------------------------------------------------------


def _e(bolum: str, bagimli: tuple[str, ...] = ()) -> Ekran:
    return Ekran(
        ad=f"e_{bolum}",
        baslik=bolum,
        bolum=bolum,
        bagimli=bagimli,
        disa_aktar=lambda: {"sema": 1},
        ice_aktar=lambda b, o: None,
    )


def test_order():
    a, b, c, d = _e("a"), _e("b", ("a",)), _e("c", ("b",)), _e("d", ("a",))
    durumsuz = Ekran(ad="bilgi", baslik="Bilgi")  # bölümsüz ekran sırayı etkilemez
    for liste in ([a, b, c, d], [d, c, b, a], [c, a, durumsuz, d, b]):
        assert kabuk_mod.sira(liste) == ["a", "b", "c", "d"]
        assert kabuk_mod.kapanis(liste, {"a"}) == ["b", "c", "d"]
        assert kabuk_mod.kapanis(liste, {"b"}) == ["c"]
        assert kabuk_mod.kapanis(liste, {"c"}) == []
        assert kabuk_mod.kapanis(liste, {"b", "d"}) == ["c"]
        assert kabuk_mod.kapanis(liste, {"a", "b"}) == ["c", "d"]


def test_order_tie_is_alphabetical():
    # bağımsız bölümler ve eşit durumdaki çocuklar ada göre
    liste = [_e("z"), _e("m"), _e("k", ("z",)), _e("b", ("z",)), _e("a")]
    assert kabuk_mod.sira(liste) == ["a", "m", "z", "b", "k"]
    assert kabuk_mod.kapanis(liste, {"z"}) == ["b", "k"]


def test_order_diamond():
    liste = [_e("a"), _e("b", ("a",)), _e("c", ("a",)), _e("d", ("b", "c"))]
    assert kabuk_mod.sira(liste) == ["a", "b", "c", "d"]
    assert kabuk_mod.kapanis(liste, {"a"}) == ["b", "c", "d"]
    assert kabuk_mod.kapanis(liste, {"c"}) == ["d"]


def test_order_cycle():
    with pytest.raises(ProjeError) as e:
        kabuk_mod.sira([_e("a", ("b",)), _e("b", ("a",)), _e("c")])
    assert "a" in str(e.value) and "b" in str(e.value)
    with pytest.raises(ProjeError) as e:
        kabuk_mod.sira([_e("kok", ("uc",)), _e("orta", ("kok",)), _e("uc", ("orta",))])
    for ad in ("kok", "orta", "uc"):
        assert ad in str(e.value)


def test_order_unknown_dependency():
    with pytest.raises(ProjeError) as e:
        kabuk_mod.sira([_e("a"), _e("b", ("olmayan_bolum",))])
    assert "olmayan_bolum" in str(e.value)


# ---------------------------------------------------------------------------
# K10 Yayılım ve etki
# ---------------------------------------------------------------------------


def test_propagation():
    s, gunluk = _sahteler()
    k = _kabuk(s)
    gunluk.clear()

    once = {ad: x.ozet() for ad, x in s.items()}
    etki = k.degistir(_yama("kok", 2.5), "v 2.5")

    # D'nin sahibi ve aşağı akış, her biri tam bir kez, topolojik sırayla; bağımsız ekran hiç
    assert gunluk == ["kok", "orta", "uc", "yan"]
    assert s["kok"].belge == {"sema": 1, "v": 2.5}
    assert s["ayri"].alinan == []

    assert [(x["bolum"], x["ekran"]) for x in etki] == [
        ("kok", "kok"),
        ("orta", "orta"),
        ("uc", "uc"),
        ("yan", "yan"),
    ]
    for x in etki:
        assert x["once"] == once[x["bolum"]]
        assert x["sonra"] == s[x["bolum"]].ozet()
        assert set(x["fark"]) == {"toplam", "v"}  # metin anahtar ("etiket") farkta yok
        for anahtar, f in x["fark"].items():
            assert f == x["sonra"][anahtar] - x["once"][anahtar]  # tam eşit
    assert etki[0]["fark"]["toplam"] == 1.5
    assert etki[2]["sonra"]["toplam"] == 2.5 + 10.0 + 100.0
    assert etki[0]["once"]["etiket"] != etki[0]["sonra"]["etiket"]

    # Proje bölümleri ekranlarla aynı; geçmişte tek kayıt yalnız değişen bölümle
    p = k.proje
    for ad, x in s.items():
        assert kanonik(dict(p.bolumler)[ad]) == kanonik(x.disa_aktar())
    assert len(p.gecmis.kayitlar) == 1 and p.gecmis.konum == 1
    assert p.gecmis.kayitlar[0]["etiket"] == "v 2.5"
    assert set(p.gecmis.kayitlar[0]["bolumler"]) == {"kok"}
    assert k.kirli


def test_propagation_middle_and_undo():
    s, gunluk = _sahteler()
    k = _kabuk(s)
    k.degistir(_yama("orta", 20.0), "orta 20")
    gunluk.clear()

    etki = k.geri_al()
    assert gunluk == ["orta", "uc"]
    assert s["orta"].belge["v"] == 10.0
    assert [x["bolum"] for x in etki] == ["orta", "uc"]
    assert etki[0]["fark"]["v"] == -10.0

    gunluk.clear()
    etki = k.yinele()
    assert gunluk == ["orta", "uc"]
    assert s["orta"].belge["v"] == 20.0
    assert etki[1]["fark"]["toplam"] == 10.0


def test_propagation_no_change():
    """Değişmeyen değer kayıt eklemez."""
    s, _ = _sahteler()
    k = _kabuk(s)
    k.degistir(_yama("kok", 1.0), "aynı")
    assert len(k.proje.gecmis.kayitlar) == 0


def test_cache_by_input_digest():
    s, _ = _sahteler()
    s["orta"].onbellek_ver = True
    k = _kabuk(s)

    k.degistir(_yama("kok", 2.0), "S1")  # S1: orta'nın önbelleği bu durumda alınır
    k.degistir(_yama("kok", 3.0), "S2")
    s["orta"].alinan.clear()

    k.geri_al()  # S1'e dönülür: orta S1'in kaydını alır
    assert len(s["orta"].alinan) == 1
    belge, onb = s["orta"].alinan[0]
    assert belge["v"] == 10.0
    assert set(onb) == {"orta.sonuc"}

    k.yinele()  # S2
    assert set(s["orta"].alinan[-1][1]) == {"orta.sonuc"}

    # Hiçbir çağrıda girdisi farklı bir durumun kaydı verilmedi; önbellek almayan ekranlara kayıt gitmedi
    assert s["orta"].onbellek_ihlali == []
    for ad in ("kok", "uc", "yan"):
        assert all(onb == {} for _, onb in s[ad].alinan), ad

    # Proje önbelleği yalnız güncel girdinin özetiyle tutulur
    bolumler = {a: dict(k.proje.bolumler)[a] for a in s}
    g = kabuk_mod.girdi_ozeti(s["orta"].ekran(), bolumler)
    assert k.proje.onbellek["orta.sonuc"].girdi_ozeti == g


def test_cache_not_given_for_new_input():
    s, _ = _sahteler()
    s["orta"].onbellek_ver = True
    k = _kabuk(s)
    k.degistir(_yama("kok", 2.0), "S1")
    s["orta"].alinan.clear()
    k.degistir(_yama("kok", 7.0), "S2")  # hiç görülmemiş girdi
    assert [onb for _, onb in s["orta"].alinan] == [{}]


# ---------------------------------------------------------------------------
# K11 Hata geri çevrilir
# ---------------------------------------------------------------------------


def test_rollback_on_error(tmp_path):
    s, _ = _sahteler()
    s["uc"].hata_v = 99.0
    c = _istemci(s)
    c.post("/api/proje/degistir", json={"etiket": "v 2", "yamalar": _yama("kok", 2.0), "onizle": False})
    once_durum = _durumlar(s)
    once_proje = _proje_baytlari(c, tmp_path)
    once_uzunluk = len(_gecmis(c)["kayitlar"])

    r = c.post("/api/proje/degistir", json={"etiket": "v 99", "yamalar": _yama("kok", 99.0), "onizle": False})
    assert r.status_code == 422
    govde = json.dumps(r.json(), ensure_ascii=False)
    assert (
        "uc hesaplanamadı (test)" in govde
    )  # hata metni; hatayı veren bölüm ("uc") metinde ya da ayrı alanda

    assert _durumlar(s) == once_durum
    assert _proje_baytlari(c, tmp_path) == once_proje
    assert len(_gecmis(c)["kayitlar"]) == once_uzunluk


def test_rollback_on_error_class():
    s, _ = _sahteler()
    s["uc"].hata_v = 99.0
    k = _kabuk(s)
    once_durum = _durumlar(s)
    once_proje = kanonik({a: dict(k.proje.bolumler)[a] for a in k.proje.bolumler})
    with pytest.raises(CamError):
        k.degistir(_yama("kok", 99.0), "v 99")
    assert _durumlar(s) == once_durum
    assert kanonik({a: dict(k.proje.bolumler)[a] for a in k.proje.bolumler}) == once_proje
    assert len(k.proje.gecmis.kayitlar) == 0


# ---------------------------------------------------------------------------
# K12 Önizleme iz bırakmaz
# ---------------------------------------------------------------------------


def test_preview_is_pure(tmp_path):
    s, _ = _sahteler()
    c = _istemci(s)
    once_durum = _durumlar(s)
    once_proje = _proje_baytlari(c, tmp_path)
    once_kirli = c.get("/api/proje").json()["kirli"]

    govde = {"etiket": "v 4", "yamalar": _yama("kok", 4.0), "onizle": True}
    r = c.post("/api/proje/degistir", json=govde)
    assert r.status_code == 200
    on_etki = r.json()["etki"]

    assert _durumlar(s) == once_durum
    assert _proje_baytlari(c, tmp_path) == once_proje
    assert c.get("/api/proje").json()["kirli"] == once_kirli
    assert _gecmis(c)["kayitlar"] == []

    r = c.post("/api/proje/degistir", json={**govde, "onizle": False})
    assert r.status_code == 200
    assert _kanon(r.json()["etki"]) == _kanon(on_etki)
    assert [x["bolum"] for x in on_etki] == ["kok", "orta", "uc", "yan"]
    assert s["kok"].belge["v"] == 4.0
    assert c.get("/api/proje").json()["kirli"] is True


def test_preview_class():
    s, _ = _sahteler()
    k = _kabuk(s)
    once = _durumlar(s), _kanon({a: dict(k.proje.bolumler)[a] for a in k.proje.bolumler}), k.kirli
    e1 = k.degistir(_yama("yan", 3.0), "yan 3", onizle=True)
    assert (_durumlar(s), _kanon({a: dict(k.proje.bolumler)[a] for a in k.proje.bolumler}), k.kirli) == once
    assert len(k.proje.gecmis.kayitlar) == 0
    e2 = k.degistir(_yama("yan", 3.0), "yan 3")
    assert _kanon(e1) == _kanon(e2)


# ---------------------------------------------------------------------------
# K13 Yakalama
# ---------------------------------------------------------------------------


def test_capture_labelled():
    s, gunluk = _sahteler()
    c = _istemci(s)
    gunluk.clear()
    r = c.post("/api/ekran/kok/ayarla", json={"v": 5.0}, headers={"X-Tezgah-Etiket": "Kok: v 1 -> 5"})
    assert r.status_code == 200
    g = _gecmis(c)
    assert g["konum"] == 1
    assert g["kayitlar"] == [{"etiket": "Kok: v 1 -> 5", "ekran": "kok", "bolumler": ["kok"]}]
    # ekran kendi durumunu kurdu: yalnız aşağı akış dolaşılır
    assert gunluk == ["orta", "uc", "yan"]
    assert c.get("/api/proje").json()["geri_al"] == "Kok: v 1 -> 5"


def test_capture_default_label():
    s, _ = _sahteler()
    c = _istemci(s)
    assert c.post("/api/ekran/yan/ayarla", json={"v": 7.0}).status_code == 200
    k = _gecmis(c)["kayitlar"]
    assert len(k) == 1
    assert k[0]["etiket"] == "POST /api/ekran/yan/ayarla"
    assert k[0]["ekran"] == "yan"


def test_capture_ignores_get_and_errors():
    s, _ = _sahteler()
    c = _istemci(s)
    assert c.get("/api/ekran/kok/durum").status_code == 200
    assert c.post("/api/ekran/kok/ayarla", json={}).status_code == 400
    assert _gecmis(c)["kayitlar"] == []
    # durum değiştiren GET bile kayıt üretmez
    assert c.get("/api/ekran/ayri/dokun").status_code == 200
    assert _gecmis(c)["kayitlar"] == []


def test_capture_no_op_post():
    """Durumu değiştirmeyen başarılı POST kayıt eklemez."""
    s, _ = _sahteler()
    c = _istemci(s)
    assert c.post("/api/ekran/kok/ayarla", json={"v": 1.0}).status_code == 200
    assert _gecmis(c)["kayitlar"] == []


def test_capture_undo_redo():
    s, _ = _sahteler()
    c = _istemci(s)
    assert c.post("/api/proje/geri-al").status_code == 409
    assert c.post("/api/proje/yinele").status_code == 409

    c.post("/api/ekran/kok/ayarla", json={"v": 5.0}, headers={"X-Tezgah-Etiket": "v 5"})
    s["kok"].alinan.clear()

    r = c.post("/api/proje/geri-al")
    assert r.status_code == 200
    assert set(r.json()) >= {"etki", "proje"}
    assert [b for b, _ in s["kok"].alinan] == [{"sema": 1, "v": 1.0}]
    assert s["kok"].disa_aktar() == {"sema": 1, "v": 1.0}
    assert c.get("/api/ekran/kok/durum").json() == {"sema": 1, "v": 1.0}
    assert r.json()["etki"][0]["fark"]["v"] == -4.0
    assert c.post("/api/proje/geri-al").status_code == 409
    d = c.get("/api/proje").json()
    assert d["geri_al"] is None and d["yinele"] == "v 5"

    r = c.post("/api/proje/yinele")
    assert r.status_code == 200
    assert s["kok"].disa_aktar() == {"sema": 1, "v": 5.0}
    assert c.post("/api/proje/yinele").status_code == 409
    assert _gecmis(c)["konum"] == 1


def test_capture_undo_is_not_captured():
    """Kabuğun kendi uçları (/api/proje) kayıt üretmez."""
    s, _ = _sahteler()
    c = _istemci(s)
    c.post("/api/ekran/kok/ayarla", json={"v": 5.0})
    c.post("/api/proje/geri-al")
    c.post("/api/proje/yinele")
    c.post("/api/proje/degistir", json={"etiket": "x", "yamalar": _yama("yan", 2.0), "onizle": True})
    g = _gecmis(c)
    assert len(g["kayitlar"]) == 1 and g["konum"] == 1


# ---------------------------------------------------------------------------
# REST uçları (SPEC 37 "REST uçları" tablosu)
# ---------------------------------------------------------------------------


def test_rest_state_fields():
    s, _ = _sahteler()
    c = _istemci(s)
    d = c.get("/api/proje").json()
    assert {"sema", "ad", "yol", "kirli", "geri_al", "yinele", "bolumler", "uyarilar", "son_etki"} <= set(d)
    assert d["sema"] == 1
    assert d["kirli"] is False and d["geri_al"] is None and d["yinele"] is None
    assert {"kok", "orta", "uc", "yan", "ayri"} <= set(d["bolumler"])
    g = _gecmis(c)
    assert g == {"konum": 0, "kayitlar": []}

    r = c.post("/api/proje/degistir", json={"etiket": "v 2", "yamalar": _yama("kok", 2.0), "onizle": False})
    assert r.status_code == 200
    assert set(r.json()) >= {"etki", "proje"}
    d = c.get("/api/proje").json()
    assert d["kirli"] is True and d["geri_al"] == "v 2"
    assert [x["bolum"] for x in d["son_etki"]] == ["kok", "orta", "uc", "yan"]
    assert _gecmis(c)["kayitlar"] == [{"etiket": "v 2", "ekran": "kok", "bolumler": ["kok"]}]


@pytest.mark.parametrize(
    "yamalar",
    [
        _yama("olmayan", 1.0),
        _yama("kok", 1.0, "/yok/derin"),
        _yama("kok", 1.0, "v"),  # JSON Pointer '/' ile başlar
        _yama("kok", "metin"),  # ekran reddeder (çekirdek hatası)
    ],
    ids=["bolum_yok", "yol_yok", "isaretci_bicimi", "cekirdek_hatasi"],
)
def test_rest_bad_patch(tmp_path, yamalar):
    s, _ = _sahteler()
    c = _istemci(s)
    once = _durumlar(s), _proje_baytlari(c, tmp_path)
    r = c.post("/api/proje/degistir", json={"etiket": "x", "yamalar": yamalar, "onizle": False})
    assert r.status_code == 422
    assert "detail" in r.json()
    assert (_durumlar(s), _proje_baytlari(c, tmp_path)) == once


def test_rest_save_open(tmp_path):
    s, _ = _sahteler()
    c = _istemci(s)
    assert c.post("/api/proje/kaydet", json={}).status_code == 422  # yol yok, son yol yok
    assert c.post("/api/proje/kaydet", json={"yol": str(tmp_path / "x.json")}).status_code == 422
    assert not (tmp_path / "x.json").exists()

    c.post("/api/proje/degistir", json={"etiket": "v 2", "yamalar": _yama("kok", 2.0), "onizle": False})
    c.post("/api/proje/degistir", json={"etiket": "v 3", "yamalar": _yama("kok", 3.0), "onizle": False})
    c.post("/api/proje/geri-al")
    yol = tmp_path / "deneme.3dc"
    assert c.post("/api/proje/kaydet", json={"yol": str(yol)}).status_code == 200
    assert yol.exists()
    d = c.get("/api/proje").json()
    assert d["kirli"] is False and d["yol"] == str(yol)
    gecmis_once = _gecmis(c)

    # son yola yeniden kayıt
    c.post("/api/proje/degistir", json={"etiket": "v 4", "yamalar": _yama("yan", 4.0), "onizle": False})
    assert c.get("/api/proje").json()["kirli"] is True
    assert c.post("/api/proje/kaydet", json={}).status_code == 200
    assert c.get("/api/proje").json()["kirli"] is False

    # yeni sunucu, yeni sahte ekranlar: aç → ekranlar sırayla ice_aktar alır
    s2, gunluk2 = _sahteler()
    c2 = _istemci(s2)
    gunluk2.clear()
    assert c2.post("/api/proje/ac", json={"yol": str(yol)}).status_code == 200
    assert _durumlar(s2) == _durumlar(s)
    assert [a for a in gunluk2 if a in s2] == ["ayri", "kok", "orta", "uc", "yan"]
    g2 = _gecmis(c2)
    assert g2["konum"] == 2
    assert [k["etiket"] for k in g2["kayitlar"]] == ["v 2", "v 4"]
    assert gecmis_once["konum"] == 1
    assert c2.post("/api/proje/geri-al").status_code == 200
    assert s2["yan"].belge["v"] == 1000.0
    assert c2.post("/api/proje/geri-al").status_code == 200
    assert s2["kok"].belge["v"] == 1.0


def test_rest_download_upload(tmp_path):
    s, _ = _sahteler()
    c = _istemci(s)
    c.post("/api/proje/degistir", json={"etiket": "v 2", "yamalar": _yama("orta", 2.0), "onizle": False})
    r = c.get("/api/proje/indir")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert ".3dc" in r.headers.get("content-disposition", "")

    s2, _ = _sahteler()
    c2 = _istemci(s2)
    assert c2.post("/api/proje/yukle", content=r.content).status_code == 200
    assert _durumlar(s2) == _durumlar(s)
    assert _gecmis(c2)["konum"] == 1
    assert c2.post("/api/proje/yukle", content=b"zip degil").status_code == 422
    assert _durumlar(s2) == _durumlar(s)  # bozuk dosya hiçbir şeyi değiştirmez


def test_rest_open_bad_file(tmp_path):
    s, _ = _sahteler()
    c = _istemci(s)
    bozuk = tmp_path / "bozuk.3dc"
    bozuk.write_bytes(b"zip degil")
    once = _durumlar(s)
    r = c.post("/api/proje/ac", json={"yol": str(bozuk)})
    assert r.status_code == 422
    assert _durumlar(s) == once


def test_rest_open_rolls_back_on_screen_error(tmp_path):
    """Açılan projede bir ekranın ice_aktar'ı hata verirse hiçbir ekran değişmez (yarım açılmış proje yok)."""
    s, _ = _sahteler()
    c = _istemci(s)
    c.post("/api/proje/degistir", json={"etiket": "v 99", "yamalar": _yama("kok", 99.0), "onizle": False})
    yol = tmp_path / "hata.3dc"
    assert c.post("/api/proje/kaydet", json={"yol": str(yol)}).status_code == 200

    s2, _ = _sahteler()
    s2["uc"].hata_v = 99.0
    c2 = _istemci(s2)
    once = _durumlar(s2)
    r = c2.post("/api/proje/ac", json={"yol": str(yol)})
    assert r.status_code == 422
    assert _durumlar(s2) == once


def test_rest_new_project():
    s, _ = _sahteler()
    c = _istemci(s)
    c.post("/api/proje/degistir", json={"etiket": "v 2", "yamalar": _yama("kok", 2.0), "onizle": False})
    assert c.post("/api/proje/yeni", json={"ad": "temiz"}).status_code == 200
    d = c.get("/api/proje").json()
    assert d["ad"] == "temiz"
    assert d["geri_al"] is None and d["yinele"] is None
    assert _gecmis(c) == {"konum": 0, "kayitlar": []}


def test_rest_examples_listed():
    s, _ = _sahteler()
    c = _istemci(s)
    r = c.get("/api/proje/ornekler")
    assert r.status_code == 200
    assert "yatak_grubu" in json.dumps(r.json())
    assert c.post("/api/proje/ornek/olmayan_ornek").status_code in (404, 422)


# ---------------------------------------------------------------------------
# K17 Bağımlılık kuralı (AST)
# ---------------------------------------------------------------------------


def _importlar(yol: Path) -> list[str]:
    """Dosyanın import ettiği modül adları; `from p import x` için `p` ve (alt modülse) `p.x`."""
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    adlar: list[str] = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar += [a.name for a in d.names]
        elif isinstance(d, ast.ImportFrom):
            assert d.level == 0, f"{yol}: göreli import"
            adlar.append(d.module)
            for a in d.names:
                alt = KOK / Path(*f"{d.module}.{a.name}".split("."))
                if alt.with_suffix(".py").exists() or (alt / "__init__.py").exists():
                    adlar.append(f"{d.module}.{a.name}")
    return adlar


def test_imports():
    # fileio/proje.py: yalnız standart kitaplık
    for ad in _importlar(KOK / "fileio" / "proje.py"):
        kok_ad = ad.split(".")[0]
        assert kok_ad == "__future__" or kok_ad in sys.stdlib_module_names, f"fileio/proje.py → {ad}"

    # tezgah/ekranlar/kabuk.py: A3 kaydı, fileio.proje, */model.py hata sınıfları, kendi örnekleri, FastAPI
    izinli_proje = {
        "tezgah.ekranlar",
        "tezgah.ornekler_37",
        "fileio.proje",
        "fileio.kurtarma",
        "tezgah.hata",
        "cam.model",
        "core.model",
        "assy.model",
        "sketch.model",
        "geometry.part",
    }
    ucuncu = {"fastapi", "starlette", "pydantic"}
    for ad in _importlar(KOK / "tezgah" / "ekranlar" / "kabuk.py"):
        kok_ad = ad.split(".")[0]
        if kok_ad == "__future__" or kok_ad in sys.stdlib_module_names or kok_ad in ucuncu:
            continue
        assert ad in izinli_proje, f"tezgah/ekranlar/kabuk.py → {ad}"

    # hiçbir paket tezgah'ı import etmez
    for paket in ("core", "cam", "assy", "geometry", "sketch", "fileio", "mesh", "viz"):
        for dosya in sorted((KOK / paket).rglob("*.py")) if (KOK / paket).exists() else []:
            for ad in _importlar(dosya):
                assert ad.split(".")[0] != "tezgah", f"{dosya.relative_to(KOK)} → {ad}"
