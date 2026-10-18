"""SPEC 54 §2–§3 — hata kartı, hata günlüğü (K3) ve hatadan sonra geri al (K4).

Testler yalnız specs/54-saglamlik.md'den ("Arayüz ayrıntıları") ve iskelet imzalarından yazıldı; SPEC 54 kodu
okunmadı. Sahte ekranlar SPEC 37 kabuk testlerinden (`tests/tezgah/test_kabuk.py`) alınır.
"""

from __future__ import annotations

import json
import traceback

import pytest

pytest.importorskip("fastapi")

from fastapi import APIRouter, HTTPException  # noqa: E402

from assy.model import AssyError  # noqa: E402
from cam.model import CamError  # noqa: E402
from core.model import ModelError  # noqa: E402
from fileio.proje import ProjeError, kanonik  # noqa: E402
from geometry.part import GeometryError  # noqa: E402
from sketch.model import SketchError  # noqa: E402
from tests.tezgah.test_kabuk import _durumlar, _kabuk, _Sahte, _sahteler, _yama  # noqa: E402
from tests.tezgah.test_kabuk import _router as sahte_router  # noqa: E402
from tezgah import hata  # noqa: E402
from tezgah.ekranlar import kabuk as kabuk_mod  # noqa: E402

ALANLAR = {"sinif", "nesne", "ne_oldu", "oneri", "teknik"}
BICIMLI = "uc / hesap: takım yolu kurulamadı (r = 0 mm) — kok değerini 99'dan farklı seçin"


def _firlat(e: BaseException, neden: BaseException | None = None) -> BaseException:
    """İstisnayı gerçekten fırlatıp yakalar (izi olsun diye)."""
    try:
        if neden is None:
            raise e
        try:
            raise neden
        except BaseException as n:
            raise e from n
    except BaseException as yakalanan:  # noqa: BLE001
        return yakalanan


# ---------------------------------------------------------------- hata_karti (saf)


@pytest.mark.parametrize("sinif", [ModelError, GeometryError, CamError, AssyError, SketchError, ProjeError])
def test_card_fields(sinif):
    e = _firlat(sinif("yatak.step / gövde: fillet yapılamadı (r = 8 mm) — yarıçapı 5 mm'nin altına indirin"))
    k = hata.hata_karti(e)
    assert set(k) == ALANLAR
    assert k["sinif"] == sinif.__name__
    assert k["nesne"] == "yatak.step / gövde"
    assert k["ne_oldu"] == "fillet yapılamadı (r = 8 mm)"
    assert k["oneri"] == "yarıçapı 5 mm'nin altına indirin"


def test_card_first_dash_splits():
    """`ne oldu` en kısa eşleşme: ilk ' — ' ayırır; öneride ' — ' kalabilir; çok satırlı öneri (DOTALL)."""
    e = _firlat(GeometryError("blok: kesim boş — a'yı küçültün — ya da b'yi taşıyın\nikinci satır"))
    k = hata.hata_karti(e)
    assert k["nesne"] == "blok"
    assert k["ne_oldu"] == "kesim boş"
    assert k["oneri"] == "a'yı küçültün — ya da b'yi taşıyın\nikinci satır"


def test_card_unformatted_message():
    e = _firlat(CamError("uc hesaplanamadı (test)"))
    k = hata.hata_karti(e)
    assert k == {**k, "sinif": "CamError", "nesne": "", "ne_oldu": "uc hesaplanamadı (test)", "oneri": ""}


def test_card_keyerror_uses_argument():
    e = _firlat(KeyError("bölüm 'parca': yok — projeyi yeniden açın"))
    k = hata.hata_karti(e)
    assert k["sinif"] == "KeyError"
    assert (k["nesne"], k["ne_oldu"], k["oneri"]) == ("bölüm 'parca'", "yok", "projeyi yeniden açın")


def test_card_technical_detail():
    e = _firlat(GeometryError(BICIMLI), neden=RuntimeError("StdFail_NotDone: BRep_API: command not done"))
    k = hata.hata_karti(e)
    assert k["teknik"] == "\n".join(traceback.format_exception(e)[-hata.TEKNIK_SATIR :])
    assert "StdFail_NotDone" in k["teknik"]  # neden teknik ayrıntıda kalır
    assert "StdFail_NotDone" not in k["ne_oldu"] + k["oneri"]


def test_card_technical_detail_is_limited():
    """Uzun istisna zinciri: teknik ayrıntı yalnız son 20 parçayı taşır.

    Özyineleme kullanılmaz: Python yinelenen çerçeveleri "[Previous line repeated …]" diye katlar.
    Bunun yerine 25 halkalı `raise … from` zinciri kurulur; her halka ayrı parçalar üretir.
    """
    e: BaseException | None = None
    for i in range(25):
        e = _firlat(RuntimeError(f"halka {i}"), neden=e)
    e = _firlat(ModelError(BICIMLI), neden=e)
    satirlar = traceback.format_exception(e)
    assert len(satirlar) > hata.TEKNIK_SATIR
    k = hata.hata_karti(e)
    assert k["teknik"] == "\n".join(satirlar[-hata.TEKNIK_SATIR :])
    assert "halka 0" not in k["teknik"]  # en eski halka kesildi
    assert hata.TEKNIK_SATIR == 20


def test_internal_error_card(tmp_path):
    gunluk = tmp_path / ".gunluk" / "hatalar.log"
    e = _firlat(ZeroDivisionError("division by zero"))
    k = hata.ic_hata_karti(e, "/api/proje/degistir", gunluk)
    assert set(k) == ALANLAR
    assert k["sinif"] == "IcHata"
    assert k["nesne"] == "/api/proje/degistir"
    assert k["ne_oldu"] == "beklenmeyen hata"
    assert k["oneri"] == f"son değişikliği geri alın; hata kaydı {gunluk} içinde"
    assert "ZeroDivisionError" in k["teknik"]


# ---------------------------------------------------------------- günlük


def _satirlar(yol) -> list[dict]:
    return [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines() if s.strip()]


def test_log_line(tmp_path):
    gunluk = tmp_path / "yok" / ".gunluk" / "hatalar.log"
    e = _firlat(ZeroDivisionError("division by zero"))
    hata.gunluge_yaz(e, "/api/proje/degistir", gunluk)  # klasörü oluşturur
    hata.gunluge_yaz(_firlat(RuntimeError("ikinci")), "/api/ekran/kok/x", gunluk)
    s = _satirlar(gunluk)
    assert len(s) == 2
    assert {"zaman", "uc", "sinif", "mesaj", "teknik"} <= set(s[0])
    assert (s[0]["uc"], s[0]["sinif"], s[0]["mesaj"]) == (
        "/api/proje/degistir",
        "ZeroDivisionError",
        "division by zero",
    )
    assert "ZeroDivisionError" in s[0]["teknik"]
    assert (s[1]["uc"], s[1]["sinif"]) == ("/api/ekran/kok/x", "RuntimeError")


def test_log_rotates_at_limit(tmp_path):
    gunluk = tmp_path / ".gunluk" / "hatalar.log"
    gunluk.parent.mkdir(parents=True)
    eski = gunluk.with_name("hatalar.log.1")
    eski.write_text("çok eski\n", encoding="utf-8")
    dolu = ("x" * 1023 + "\n") * (hata.GUNLUK_SINIRI // 1024)  # tam sınır
    gunluk.write_text(dolu, encoding="utf-8")
    assert gunluk.stat().st_size == hata.GUNLUK_SINIRI

    hata.gunluge_yaz(_firlat(RuntimeError("yeni")), "/api/proje/degistir", gunluk)
    assert eski.read_text(encoding="utf-8") == dolu  # eskisinin üstüne döndü
    s = _satirlar(gunluk)
    assert len(s) == 1 and s[0]["mesaj"] == "yeni"
    assert gunluk.stat().st_size <= hata.GUNLUK_SINIRI


def test_log_never_exceeds_limit(tmp_path):
    gunluk = tmp_path / "hatalar.log"
    gunluk.write_text("y" * (hata.GUNLUK_SINIRI - 10), encoding="utf-8")
    hata.gunluge_yaz(_firlat(RuntimeError("sığmaz")), "/x", gunluk)
    assert gunluk.stat().st_size <= hata.GUNLUK_SINIRI
    assert gunluk.with_name("hatalar.log.1").stat().st_size == hata.GUNLUK_SINIRI - 10
    assert hata.GUNLUK_SINIRI == 5 * 1024 * 1024


# ---------------------------------------------------------------- REST: 422 / 500 gövdesi


class _BicimliSahte(_Sahte):
    """Girdi zincirinde v = 99 olunca §1 biçimli CamError veren sahte ekran."""

    def ice_aktar(self, belge: dict, onbellek) -> None:
        if any(g.belge["v"] == 99.0 for g in self._tum_girdiler()):
            self.gunluk.append(self.ad)
            raise CamError(BICIMLI)
        super().ice_aktar(belge, onbellek)


def _patlak_router(s: _Sahte) -> APIRouter:
    r = sahte_router(s)

    @r.post("/geometri")
    def geometri() -> dict:
        raise GeometryError("blok.step: katı bulunamadı — dosyayı katı olarak yeniden dışa aktarın")

    @r.post("/sarili")
    def sarili() -> dict:
        try:
            raise GeometryError("blok.step: katı bulunamadı — dosyayı katı olarak yeniden dışa aktarın")
        except GeometryError:
            raise HTTPException(status_code=422, detail="katı bulunamadı") from None

    @r.post("/coker")
    def coker() -> dict:
        return {"x": 1 / 0}

    return r


def _sahteler_bicimli():
    s, gunluk = _sahteler()
    uc = _BicimliSahte("uc", 100.0, gunluk, ("orta",))
    uc.girdiler = [s["orta"]]
    s["uc"] = uc
    return s


def _istemci(s, tmp_path):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    ekranlar = [x.ekran(_patlak_router(x)) for x in s.values()] + [kabuk_mod.EKRAN]
    app = uygulama(dist=None, ekranlar=ekranlar)
    app.state.proje_klasoru = tmp_path
    app.state.kurtarma_ayari = False
    return TestClient(app, raise_server_exceptions=False)


def _degistir(c, etiket: str, v: float, bolum: str = "kok"):
    return c.post("/api/proje/degistir", json={"etiket": etiket, "yamalar": _yama(bolum, v), "onizle": False})


def _gunluk(tmp_path):
    return tmp_path / ".gunluk" / "hatalar.log"


def test_rest_422_card(tmp_path):
    s = _sahteler_bicimli()
    c = _istemci(s, tmp_path)
    assert _degistir(c, "v 2", 2.0).status_code == 200
    once = _durumlar(s)
    r = _degistir(c, "v 99", 99.0)
    assert r.status_code == 422
    g = r.json()
    assert "detail" in g  # SPEC 37 / A3 alanı korunur
    assert BICIMLI in json.dumps(g["detail"], ensure_ascii=False)
    assert set(g["hata"]) == ALANLAR
    assert g["hata"]["sinif"] == "CamError"
    assert (g["hata"]["nesne"], g["hata"]["ne_oldu"], g["hata"]["oneri"]) == (
        "uc / hesap",
        "takım yolu kurulamadı (r = 0 mm)",
        "kok değerini 99'dan farklı seçin",
    )
    assert _durumlar(s) == once  # SPEC 37 K11
    assert not _gunluk(tmp_path).exists()  # çekirdek hata günlüğe yazılmaz


def test_rest_422_card_unformatted(tmp_path):
    s, _ = _sahteler()
    s["uc"].hata_v = 99.0
    c = _istemci(s, tmp_path)
    r = _degistir(c, "v 99", 99.0)
    assert r.status_code == 422
    k = r.json()["hata"]
    assert k["sinif"] == "CamError"
    assert k["ne_oldu"] == "uc hesaplanamadı (test)" and k["nesne"] == "" and k["oneri"] == ""


def test_rest_422_project_error_card(tmp_path):
    s, _ = _sahteler()
    c = _istemci(s, tmp_path)
    bozuk = tmp_path / "bozuk.3dc"
    bozuk.write_bytes(b"zip degil")
    r = c.post("/api/proje/ac", json={"yol": str(bozuk)})
    assert r.status_code == 422
    assert r.json()["hata"]["sinif"] == "ProjeError"


def test_rest_screen_core_error_card(tmp_path):
    s, _ = _sahteler()
    c = _istemci(s, tmp_path)
    r = c.post("/api/ekran/kok/geometri")
    assert r.status_code == 422
    k = r.json()["hata"]
    assert k["sinif"] == "GeometryError"
    assert (k["nesne"], k["ne_oldu"]) == ("blok.step", "katı bulunamadı")


def test_rest_screen_http_422_card_from_context(tmp_path):
    """Ekran ucunun HTTPException(422)'si: kart istisnanın __context__'indeki çekirdek hatasından kurulur."""
    s, _ = _sahteler()
    c = _istemci(s, tmp_path)
    r = c.post("/api/ekran/kok/sarili")
    assert r.status_code == 422
    g = r.json()
    assert g["detail"] == "katı bulunamadı"
    assert g["hata"]["sinif"] == "GeometryError"
    assert g["hata"]["oneri"] == "dosyayı katı olarak yeniden dışa aktarın"


def test_rest_500_internal_error(tmp_path):
    s, _ = _sahteler()
    c = _istemci(s, tmp_path)
    assert _degistir(c, "v 2", 2.0).status_code == 200
    once = _durumlar(s)
    r = c.post("/api/ekran/kok/coker")
    assert r.status_code == 500
    g = r.json()
    assert g["detail"] == "beklenmeyen hata"
    k = g["hata"]
    assert set(k) == ALANLAR
    assert k["sinif"] == "IcHata" and k["ne_oldu"] == "beklenmeyen hata"
    assert "coker" in k["nesne"]
    assert str(_gunluk(tmp_path)) in k["oneri"]
    assert "ZeroDivisionError" in k["teknik"]
    s_log = _satirlar(_gunluk(tmp_path))
    assert len(s_log) == 1 and s_log[0]["sinif"] == "ZeroDivisionError"
    assert _durumlar(s) == once
    assert c.get("/api/proje").json()["geri_al"] == "v 2"


def test_rest_500_internal_error_in_shell(tmp_path):
    """Kabuk yayılımında çekirdek dışı istisna: 500 IcHata, proje ve ekranlar değişmez, günlükte bir satır."""
    s, _ = _sahteler()

    def bozuk_ice_aktar(belge, onbellek, _asil=s["yan"].ice_aktar):
        if belge.get("v") == 7.0 or any(g.belge["v"] == 7.0 for g in s["yan"].girdiler):
            raise IndexError("list index out of range")
        _asil(belge, onbellek)

    s["yan"].ice_aktar = bozuk_ice_aktar
    c = _istemci(s, tmp_path)
    once = _durumlar(s)
    r = _degistir(c, "v 7", 7.0)
    assert r.status_code == 500
    assert r.json()["hata"]["sinif"] == "IcHata"
    assert len(_satirlar(_gunluk(tmp_path))) == 1
    assert _durumlar(s) == once
    assert c.get("/api/proje/gecmis").json()["kayitlar"] == []


# ---------------------------------------------------------------- K4 hatadan sonra geri al


def test_undo_after_error():
    """A (başarılı), B (hata), C (hata) → geri_al: proje A'dan önceki halle kanonik olarak eşit."""
    s, _ = _sahteler()
    s["uc"].hata_v = 99.0
    k = _kabuk(s)
    bas_durum = _durumlar(s)
    bas_proje = kanonik(dict(k.proje.bolumler))

    k.degistir(_yama("kok", 2.0), "A")
    assert len(k.proje.gecmis.kayitlar) == 1
    with pytest.raises(CamError):
        k.degistir(_yama("kok", 99.0), "B")
    with pytest.raises(CamError):
        k.degistir(_yama("orta", 99.0), "C")
    assert len(k.proje.gecmis.kayitlar) == 1
    assert k.durum()["geri_al"] == "A"

    k.geri_al()
    assert kanonik(dict(k.proje.bolumler)) == bas_proje
    assert _durumlar(s) == bas_durum
    assert k.proje.gecmis.konum == 0


def test_undo_after_many_errors_rest(tmp_path):
    """Ardışık k hata ve sonra geri al = hiç hata olmamış gibi geri al (REST, biçimli hata)."""
    s = _sahteler_bicimli()
    c = _istemci(s, tmp_path)
    bas = _durumlar(s)
    assert _degistir(c, "A", 3.0).status_code == 200
    sonra_a = _durumlar(s)
    for i in range(4):
        assert _degistir(c, f"hata {i}", 99.0).status_code == 422
        assert _durumlar(s) == sonra_a
    assert c.get("/api/proje").json()["geri_al"] == "A"
    assert len(c.get("/api/proje/gecmis").json()["kayitlar"]) == 1
    assert c.post("/api/proje/geri-al").status_code == 200
    assert _durumlar(s) == bas
    assert c.get("/api/proje").json()["geri_al"] is None
