"""SPEC 54 K9 (çökme benzetimi) ve K10 (kurtarma yazımı arka planda; disk hatası bir kez uyarı).

Testler yalnız specs/54-saglamlik.md'den ("Arayüz ayrıntıları", Karar 7) ve iskelet imzalarından yazıldı;
SPEC 54 kodu okunmadı. Yazıcı, kabuğun kullandığı `fileio.kurtarma.kurtarma_yaz` monkeypatch'lenerek
yavaşlatılır / bozulur.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fileio import kurtarma as kr  # noqa: E402
from tests.tezgah.test_kabuk import _durumlar, _kanon, _sahteler, _yama  # noqa: E402
from tezgah.ekranlar import kabuk as kabuk_mod  # noqa: E402

KOK = Path(__file__).resolve().parents[2]
UZAK = 1e6


def _kabuk(klasor: Path, ayar=None):
    s, _ = _sahteler()
    ayar = ayar or kr.KurtarmaAyari(T=60.0, K=100)
    return s, kabuk_mod.Kabuk([x.ekran() for x in s.values()], kurtarma=ayar, klasor=klasor)


# ---------------------------------------------------------------- K9 çökme benzetimi

COCUK = textwrap.dedent(
    """
    import json, sys, time
    from pathlib import Path

    sys.path.insert(0, sys.argv[1])
    from fileio.kurtarma import KurtarmaAyari
    from tests.tezgah.test_kabuk import _durumlar, _sahteler, _yama
    from tezgah.ekranlar.kabuk import Kabuk

    P, klasor = Path(sys.argv[2]), Path(sys.argv[3])
    s, _ = _sahteler()
    k = Kabuk([x.ekran() for x in s.values()], kurtarma=KurtarmaAyari(T=60.0, K=3), klasor=klasor)
    k.kaydet(P)
    k.degistir(_yama("kok", 2.0), "d1")
    k.degistir(_yama("orta", 20.0), "d2")
    k.degistir(_yama("yan", 3.0), "d3")
    assert k.kurtarma_bekle(30.0)
    print(json.dumps({"durumlar": _durumlar(s).decode()}), flush=True)
    time.sleep(600)
    """
)


@pytest.mark.slow
def test_crash_recovery(tmp_path):
    """Alt süreç 3 değişiklik yapar, K = 3 ile kurtarma yazılır, süreç öldürülür; yeni kabukta 'Kurtar'."""
    P = tmp_path / "is" / "yatak.3dc"
    P.parent.mkdir()
    klasor = tmp_path / "projeler"
    betik = tmp_path / "cocuk.py"
    betik.write_text(COCUK, encoding="utf-8")
    p = subprocess.Popen(
        [sys.executable, str(betik), str(KOK), str(P), str(klasor)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=str(tmp_path),
    )
    try:
        satir = p.stdout.readline()
        if not satir:
            p.wait(30)
            hata = p.stderr.read()
            if "NotImplementedError" in hata:
                raise NotImplementedError(hata.strip().splitlines()[-1])
            pytest.fail(f"alt süreç kurtarma yazmadan çıktı:\n{hata}")
        cocuk = json.loads(satir)
        assert (P.parent / ".yatak.3dc.kurtarma").is_file()
    finally:
        p.kill()  # çökme: temizlik şansı yok
        p.wait(30)
        p.stdout.close()
        p.stderr.close()

    assert (P.parent / ".yatak.3dc.kurtarma").is_file()
    b = kr.kurtarma_bul(P)
    assert b["okunur"] is True and b["kaynak_tutuyor"] is True and b["farkli"] is True

    s2, k2 = _kabuk(klasor)
    k2.ac(P)
    assert k2.kurtarma_durumu()["bulunan"]["farkli"] is True
    k2.kurtarma_sec("kurtar")
    assert _durumlar(s2).decode() == cocuk["durumlar"]
    assert [x["etiket"] for x in k2.proje.gecmis.kayitlar] == ["d1", "d2", "d3"]
    assert k2.durum()["kirli"] is True
    k2.geri_al()
    assert s2["yan"].belge["v"] == 1000.0  # geçmiş de geri geldi


# ---------------------------------------------------------------- K10 arka plan


def test_background(tmp_path, monkeypatch):
    """Yazım sürerken kabuk yanıt verir; ikinci adım yeni yazım başlatmaz; yazım bitince dosya yerinde."""
    asil = kr.kurtarma_yaz
    basladi, birak = threading.Event(), threading.Event()
    yazilan = []

    def yavas(p, yol, kaynak_ozet, sayac):
        basladi.set()
        assert birak.wait(20.0), "test yazıcıyı bırakmadı"
        yazilan.append(_kanon(dict(p.bolumler)))
        asil(p, yol, kaynak_ozet, sayac)

    monkeypatch.setattr(kr, "kurtarma_yaz", yavas)
    s, k = _kabuk(tmp_path / "projeler")
    k.degistir(_yama("kok", 2.0), "d1")
    anlik = _kanon(dict(k.proje.bolumler))

    t0 = time.monotonic()
    assert k.kurtarma_adimi(simdi=time.time() + UZAK) is True
    assert time.monotonic() - t0 < 2.0, "kurtarma_adimi yazımı beklememeli"
    assert basladi.wait(10.0)
    try:
        # yazım sürüyor: kabuk çalışmaya devam eder
        assert k.kurtarma_bekle(0.2) is False
        assert k.durum()["kirli"] is True
        k.degistir(_yama("kok", 3.0), "d2")
        assert s["kok"].belge["v"] == 3.0
        assert k.kurtarma_adimi(simdi=time.time() + UZAK) is False  # yazım sürerken yenisi yok
    finally:
        birak.set()
    assert k.kurtarma_bekle(10.0) is True
    assert yazilan == [anlik]  # yazım başladığı andaki anlık görüntü
    assert len(list((tmp_path / "projeler" / ".kurtarma").glob("*.3dc.kurtarma"))) == 1


def test_background_rest_stays_responsive(tmp_path, monkeypatch):
    """REST yolunda da kurtarma yazımı sürerken uçlar yanıt verir."""
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tests.tezgah.test_kabuk import _router
    from tezgah.sunucu import uygulama

    basladi, birak = threading.Event(), threading.Event()
    asil = kr.kurtarma_yaz

    def yavas(*a):
        basladi.set()
        birak.wait(20.0)
        asil(*a)

    monkeypatch.setattr(kr, "kurtarma_yaz", yavas)
    s, _ = _sahteler()
    app = uygulama(dist=None, ekranlar=[x.ekran(_router(x)) for x in s.values()] + [kabuk_mod.EKRAN])
    app.state.proje_klasoru = tmp_path / "projeler"
    app.state.kurtarma_ayari = kr.KurtarmaAyari(T=60.0, K=1)
    c = TestClient(app, raise_server_exceptions=False)
    try:
        t0 = time.monotonic()
        r = c.post(
            "/api/proje/degistir", json={"etiket": "d1", "yamalar": _yama("kok", 2.0), "onizle": False}
        )
        assert r.status_code == 200
        assert basladi.wait(10.0)
        assert c.get("/api/proje").status_code == 200
        r = c.post(
            "/api/proje/degistir", json={"etiket": "d2", "yamalar": _yama("kok", 3.0), "onizle": False}
        )
        assert r.status_code == 200
        assert time.monotonic() - t0 < 10.0
    finally:
        birak.set()
        k = app.state.kabuk
        assert k.kurtarma_bekle(10.0)
        k.zamanlayici_durdur()


def test_disk_error_warns_once(tmp_path, monkeypatch):
    asil = kr.kurtarma_yaz
    durum = {"bozuk": True}

    def bazen(*a):
        if durum["bozuk"]:
            raise OSError(28, "No space left on device (test)")
        asil(*a)

    monkeypatch.setattr(kr, "kurtarma_yaz", bazen)
    s, k = _kabuk(tmp_path / "projeler")
    k.degistir(_yama("kok", 2.0), "d1")

    for _ in range(3):
        assert k.kurtarma_adimi(simdi=time.time() + UZAK) is True
        assert k.kurtarma_bekle(10.0)
    assert len(k.kurtarma_uyarilari) == 1
    u = k.kurtarma_uyarilari[0]
    assert ": " in u and " — " in u, f"uyarı §1 biçiminde değil: {u!r}"

    # uygulama sürer
    k.degistir(_yama("kok", 3.0), "d2")
    assert s["kok"].belge["v"] == 3.0
    assert k.kurtarma_durumu()["uyarilar"] == k.kurtarma_uyarilari

    # başarılı yazımdan sonra yeni bir hata yeniden bir kez uyarır
    durum["bozuk"] = False
    assert k.kurtarma_adimi(simdi=time.time() + UZAK) is True
    assert k.kurtarma_bekle(10.0)
    durum["bozuk"] = True
    k.degistir(_yama("kok", 4.0), "d3")
    for _ in range(2):
        assert k.kurtarma_adimi(simdi=time.time() + UZAK) is True
        assert k.kurtarma_bekle(10.0)
    assert len(k.kurtarma_uyarilari) == 2


def test_timer_start_stop(tmp_path):
    """Zamanlayıcı başlatılıp durdurulabilir; durdurulduktan sonra iş parçacığı kalmaz."""
    _, k = _kabuk(tmp_path / "projeler")
    once = threading.active_count()
    k.zamanlayici_baslat(aralik=0.05)
    time.sleep(0.2)
    k.zamanlayici_durdur()
    k.kurtarma_bekle(5.0)
    son = time.monotonic() + 5.0
    while threading.active_count() > once and time.monotonic() < son:
        time.sleep(0.05)
    assert threading.active_count() <= once
