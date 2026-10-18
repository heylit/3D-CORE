"""SPEC 54 §5 — kabukta otomatik kayıt: zamanlama, kurtarma dosyasının yeri, temizlik, açılışta öneri ve
seçimler (Kararlar 5–8) ve REST uçları `GET/POST /api/proje/kurtarma`.

Testler yalnız specs/54-saglamlik.md'den ("Arayüz ayrıntıları") ve iskelet imzalarından yazıldı; SPEC 54 kodu
okunmadı. Sahte ekranlar SPEC 37 kabuk testlerinden alınır. Saat: `kurtarma_adimi(simdi=…)` ile ileri alınır.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fileio import kurtarma as kr  # noqa: E402
from fileio.proje import ProjeError, ac, bos_proje, kaydet, uygula  # noqa: E402
from tests.tezgah.test_kabuk import _durumlar, _router, _sahteler, _yama  # noqa: E402
from tezgah.ekranlar import kabuk as kabuk_mod  # noqa: E402

UZAK = 1e6  # s; T'yi kesin dolduran ileri bir an


def _kabuk(klasor: Path, ayar=None, s=None):
    if s is None:
        s, _ = _sahteler()
    if ayar is None:
        ayar = kr.KurtarmaAyari(T=60.0, K=100)
    k = kabuk_mod.Kabuk([x.ekran() for x in s.values()], kurtarma=ayar, klasor=klasor)
    return s, k


def _yaz(k) -> None:
    """Zamanı ileri alıp kurtarma yazımını başlatır ve bitmesini bekler."""
    assert k.kurtarma_adimi(simdi=time.time() + UZAK) is True
    assert k.kurtarma_bekle(10.0) is True


def _kurtarma_dosyalari(kok: Path) -> list[Path]:
    return sorted(p for p in kok.rglob("*") if p.is_file() and p.name.endswith(".kurtarma"))


def _sha(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _kirli_kayitli(tmp_path: Path):
    """P'ye kaydedilmiş, sonra üç değişiklik yapılmış ve kurtarması yazılmış kabuk."""
    s, k = _kabuk(tmp_path / "projeler")
    P = tmp_path / "is" / "yatak.3dc"
    P.parent.mkdir()
    k.kaydet(P)
    k.degistir(_yama("kok", 2.0), "d1")
    k.degistir(_yama("orta", 20.0), "d2")
    k.degistir(_yama("yan", 3.0), "d3")
    _yaz(k)
    return s, k, P


# ---------------------------------------------------------------- zamanlama ve yer


def test_disabled_without_settings(tmp_path):
    s, _ = _sahteler()
    k = kabuk_mod.Kabuk([x.ekran() for x in s.values()])  # kurtarma=None → kapalı
    k.degistir(_yama("kok", 2.0), "d1")
    assert k.kurtarma_adimi(simdi=time.time() + UZAK) is False
    assert k.kurtarma_bekle(1.0) is True
    assert _kurtarma_dosyalari(tmp_path) == []


def test_clean_project_is_not_written(tmp_path):
    _, k = _kabuk(tmp_path)
    assert k.kurtarma_adimi(simdi=time.time() + UZAK) is False
    assert _kurtarma_dosyalari(tmp_path) == []


def test_unsaved_project_location(tmp_path):
    klasor = tmp_path / "projeler"
    _, k = _kabuk(klasor)
    k.degistir(_yama("kok", 2.0), "d1")
    _yaz(k)
    dosyalar = _kurtarma_dosyalari(tmp_path)
    assert len(dosyalar) == 1
    ad = k.durum()["ad"]
    assert dosyalar[0].parent == klasor / ".kurtarma"
    assert dosyalar[0].name.startswith(f"{ad}-") and dosyalar[0].name.endswith(".3dc.kurtarma")
    assert len(dosyalar[0].name) == len(f"{ad}-") + 8 + len(".3dc.kurtarma")
    assert dosyalar[0].with_name(dosyalar[0].name + ".json").is_file()
    assert str(dosyalar[0]) in k.kurtarma_durumu()["adsizlar"]


def test_saved_project_location_and_cleanup(tmp_path):
    _, k, P = _kirli_kayitli(tmp_path)
    yol = P.parent / ".yatak.3dc.kurtarma"
    assert yol.is_file() and yol.with_name(yol.name + ".json").is_file()
    once = P.read_bytes()
    assert _durumlar_ac(yol) == _durumlar_ac_kabuk(k)
    assert P.read_bytes() == once
    k.kaydet()  # Karar 5: P'ye başarılı kayıt temizler
    assert not yol.exists() and not yol.with_name(yol.name + ".json").exists()


def test_unsaved_recovery_removed_on_first_save(tmp_path):
    klasor = tmp_path / "projeler"
    _, k = _kabuk(klasor)
    k.degistir(_yama("kok", 2.0), "d1")
    _yaz(k)
    assert len(_kurtarma_dosyalari(klasor)) == 1
    k.kaydet(tmp_path / "ilk.3dc")
    assert _kurtarma_dosyalari(klasor) == []


def test_new_or_other_project_keeps_recovery(tmp_path):
    """Karar 5: kaydetmeden yeni proje / başka proje açmak kurtarma dosyasını silmez."""
    _, k, P = _kirli_kayitli(tmp_path)
    yol = P.parent / ".yatak.3dc.kurtarma"
    baska = tmp_path / "baska.3dc"
    kaydet(bos_proje("baska"), baska)
    k.yeni("temiz")
    assert yol.is_file()
    k.ac(baska)
    assert yol.is_file()


def test_count_trigger_after_changes(tmp_path):
    """K kayıt sonra yazım kendiliğinden başlar (başarılı degistir sonrası çağrılır)."""
    _, k = _kabuk(tmp_path / "projeler", kr.KurtarmaAyari(T=60.0, K=3))
    k.degistir(_yama("kok", 2.0), "d1")
    k.degistir(_yama("kok", 3.0), "d2")
    assert k.kurtarma_bekle(10.0)
    assert _kurtarma_dosyalari(tmp_path) == []
    k.degistir(_yama("kok", 4.0), "d3")
    assert k.kurtarma_bekle(10.0)
    assert len(_kurtarma_dosyalari(tmp_path)) == 1


def test_preview_does_not_count(tmp_path):
    _, k = _kabuk(tmp_path / "projeler", kr.KurtarmaAyari(T=60.0, K=2))
    k.degistir(_yama("kok", 2.0), "d1")
    k.degistir(_yama("kok", 3.0), "ön", onizle=True)
    k.degistir(_yama("kok", 3.0), "ön 2", onizle=True)
    assert k.kurtarma_bekle(10.0)
    assert _kurtarma_dosyalari(tmp_path) == []


def test_error_does_not_write(tmp_path):
    s, k = _kabuk(tmp_path / "projeler", kr.KurtarmaAyari(T=60.0, K=1))
    s["uc"].hata_v = 99.0
    with pytest.raises(Exception):  # noqa: B017 — sınıf SPEC 37'nin işi
        k.degistir(_yama("kok", 99.0), "hata")
    assert k.kurtarma_bekle(10.0)
    assert _kurtarma_dosyalari(tmp_path) == []


def _durumlar_ac(yol: Path):
    p = ac(yol)
    return dict(p.bolumler), [k["etiket"] for k in p.gecmis.kayitlar], p.gecmis.konum


def _durumlar_ac_kabuk(k):
    p = k.proje
    return dict(p.bolumler), [x["etiket"] for x in p.gecmis.kayitlar], p.gecmis.konum


# ---------------------------------------------------------------- açılışta öneri


def test_open_offers_recovery(tmp_path):
    s1, k1, P = _kirli_kayitli(tmp_path)
    once = P.read_bytes()
    s2, k2 = _kabuk(tmp_path / "projeler")
    k2.ac(P)  # P her zaman normal açılır
    assert k2.durum()["kirli"] is False
    assert dict(k2.proje.bolumler) == dict(ac(P).bolumler)
    d = k2.kurtarma_durumu()
    assert set(d) == {"bulunan", "adsizlar", "uyarilar"}
    b = d["bulunan"]
    assert b["yol"] == str(P.parent / ".yatak.3dc.kurtarma")
    assert b["okunur"] is True and b["kaynak_tutuyor"] is True and b["farkli"] is True
    assert P.read_bytes() == once


def test_choice_recover(tmp_path):
    s1, k1, P = _kirli_kayitli(tmp_path)
    once = P.read_bytes()
    s2, k2 = _kabuk(tmp_path / "projeler")
    k2.ac(P)
    assert k2.kurtarma_sec("kurtar") is None
    assert _durumlar(s2) == _durumlar(s1)
    d = k2.durum()
    assert d["kirli"] is True and d["yol"] == str(P)
    assert _durumlar_ac_kabuk(k2) == _durumlar_ac_kabuk(k1)
    assert P.read_bytes() == once


def test_choice_ignore(tmp_path):
    s1, k1, P = _kirli_kayitli(tmp_path)
    once = P.read_bytes()
    yol = P.parent / ".yatak.3dc.kurtarma"
    s2, k2 = _kabuk(tmp_path / "projeler")
    k2.ac(P)
    onceki = _durumlar(s2)
    assert k2.kurtarma_sec("yoksay") is None
    assert not yol.exists()
    assert yol.with_name(yol.name + ".eski").is_file()
    assert _durumlar(s2) == onceki and k2.durum()["kirli"] is False
    assert k2.kurtarma_durumu()["bulunan"] is None
    assert P.read_bytes() == once


def test_choice_both(tmp_path):
    s1, k1, P = _kirli_kayitli(tmp_path)
    once = P.read_bytes()
    beklenen = _durumlar_ac(P.parent / ".yatak.3dc.kurtarma")
    s2, k2 = _kabuk(tmp_path / "projeler")
    k2.ac(P)
    kopya = k2.kurtarma_sec("ikisi")
    assert kopya == str(P.parent / "yatak (kurtarılan).3dc")
    assert _durumlar_ac(Path(kopya)) == beklenen
    assert not (P.parent / ".yatak.3dc.kurtarma").exists()
    assert k2.durum()["yol"] == str(P)  # P açık kalır
    assert dict(k2.proje.bolumler) == dict(ac(P).bolumler)
    assert P.read_bytes() == once

    # ikinci kez: (kurtarılan 2)
    k1.degistir(_yama("kok", 5.0), "d4")
    _yaz(k1)
    _, k3 = _kabuk(tmp_path / "projeler")
    k3.ac(P)
    assert k3.kurtarma_sec("ikisi") == str(P.parent / "yatak (kurtarılan 2).3dc")
    assert (P.parent / "yatak (kurtarılan).3dc").is_file()


def test_source_changed_still_offered(tmp_path):
    s1, k1, P = _kirli_kayitli(tmp_path)
    kaydet(uygula(ac(P), "başka", "kok", {"kok": {"sema": 1, "v": 42.0}}), P)  # P başka yerde değişti
    _, k2 = _kabuk(tmp_path / "projeler")
    k2.ac(P)
    b = k2.kurtarma_durumu()["bulunan"]
    assert b["okunur"] is True and b["kaynak_tutuyor"] is False and b["farkli"] is True


def test_same_content_not_offered(tmp_path):
    s1, k = _kabuk(tmp_path / "projeler")
    P = tmp_path / "yatak.3dc"
    k.kaydet(P)
    kr.kurtarma_yaz(ac(P), kr.kurtarma_yolu(P, "yatak", "0" * 64), _sha(P), 1)
    _, k2 = _kabuk(tmp_path / "projeler")
    k2.ac(P)
    b = k2.kurtarma_durumu()["bulunan"]
    assert b is None or b["farkli"] is False
    with pytest.raises(ProjeError):
        k2.kurtarma_sec("kurtar")


def test_broken_recovery_warns_and_opens(tmp_path):
    """Durum 15: bozuk kurtarma dosyası → uyarı, P normal açılır, öneri yok."""
    s1, k1, P = _kirli_kayitli(tmp_path)
    yol = P.parent / ".yatak.3dc.kurtarma"
    yol.write_bytes(yol.read_bytes()[: yol.stat().st_size // 2])
    s2, k2 = _kabuk(tmp_path / "projeler")
    k2.ac(P)
    assert dict(k2.proje.bolumler) == dict(ac(P).bolumler)
    d = k2.kurtarma_durumu()
    assert d["uyarilar"], "bozuk kurtarma dosyası uyarı vermedi"
    assert all(" — " in u for u in d["uyarilar"])
    assert d["bulunan"] is None or d["bulunan"]["okunur"] is False
    with pytest.raises(ProjeError):
        k2.kurtarma_sec("kurtar")


def test_choice_without_pending(tmp_path):
    _, k = _kabuk(tmp_path / "projeler")
    with pytest.raises(ProjeError):
        k.kurtarma_sec("kurtar")


def test_unsaved_recovery_listed_not_opened(tmp_path):
    """Karar 8: adsız projelerin kurtarma dosyası kendiliğinden açılmaz; `yol` ile kurtarılır."""
    klasor = tmp_path / "projeler"
    s1, k1 = _kabuk(klasor)
    k1.degistir(_yama("kok", 2.0), "d1")
    k1.degistir(_yama("ayri", 6.0), "d2")
    _yaz(k1)
    [dosya] = _kurtarma_dosyalari(klasor)

    s2, k2 = _kabuk(klasor)
    bas = _durumlar(s2)
    d = k2.kurtarma_durumu()
    assert d["adsizlar"] == [str(dosya)]
    assert d["bulunan"] is None
    assert _durumlar(s2) == bas  # kendiliğinden açılmadı

    assert k2.kurtarma_sec("kurtar", yol=str(dosya)) is None
    assert _durumlar(s2) == _durumlar(s1)
    assert k2.durum()["kirli"] is True
    assert [x["etiket"] for x in k2.proje.gecmis.kayitlar] == ["d1", "d2"]


def test_invalid_choice(tmp_path):
    s1, k1, P = _kirli_kayitli(tmp_path)
    _, k2 = _kabuk(tmp_path / "projeler")
    k2.ac(P)
    with pytest.raises(ProjeError):
        k2.kurtarma_sec("hepsi")


# ---------------------------------------------------------------- REST


def _istemci(tmp_path, ayar=False):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    s, _ = _sahteler()
    app = uygulama(dist=None, ekranlar=[x.ekran(_router(x)) for x in s.values()] + [kabuk_mod.EKRAN])
    app.state.proje_klasoru = tmp_path / "projeler"
    app.state.kurtarma_ayari = ayar
    return s, TestClient(app, raise_server_exceptions=False)


def test_rest_get_state(tmp_path):
    _, c = _istemci(tmp_path)
    r = c.get("/api/proje/kurtarma")
    assert r.status_code == 200
    assert r.json() == {"bulunan": None, "adsizlar": [], "uyarilar": []}


def test_rest_post_errors(tmp_path):
    _, c = _istemci(tmp_path)
    assert c.post("/api/proje/kurtarma", json={"secim": "kurtar"}).status_code == 409
    assert c.post("/api/proje/kurtarma", json={"secim": "hepsi"}).status_code == 422
    assert c.post("/api/proje/kurtarma", json={}).status_code == 422


def test_rest_recover_flow(tmp_path):
    s1, k1, P = _kirli_kayitli(tmp_path)
    s, c = _istemci(tmp_path)
    assert c.post("/api/proje/ac", json={"yol": str(P)}).status_code == 200
    b = c.get("/api/proje/kurtarma").json()["bulunan"]
    assert b["farkli"] is True and b["kaynak_tutuyor"] is True
    r = c.post("/api/proje/kurtarma", json={"secim": "ikisi"})
    assert r.status_code == 200
    g = r.json()
    assert g["kopya"] == str(P.parent / "yatak (kurtarılan).3dc")
    assert g["proje"]["yol"] == str(P)
    assert c.get("/api/proje/kurtarma").json()["bulunan"] is None


def test_rest_recover_choice(tmp_path):
    s1, k1, P = _kirli_kayitli(tmp_path)
    s, c = _istemci(tmp_path)
    assert c.post("/api/proje/ac", json={"yol": str(P)}).status_code == 200
    r = c.post("/api/proje/kurtarma", json={"secim": "kurtar"})
    assert r.status_code == 200
    assert r.json()["kopya"] is None
    assert r.json()["proje"]["kirli"] is True
    assert _durumlar(s) == _durumlar(s1)
