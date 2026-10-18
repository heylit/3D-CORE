"""SPEC 37 K14 — gerçek iplik (yatak grubu): örnek proje, palet yaması, torna + montaj etkisi,
geri al / yinele, kaydet → yeni sunucu → aç.

Testler yalnız specs/37-proje-kabuk.md, specs/24a-ekran-kaydi.md ve SPEC 25 taslağındaki uç tablosundan
yazıldı. Gerçek 24/25 ekranlarına bağlıdır (`@slow`, `@occt`); SPEC 25 montaj uçları yoksa test atlanır.

Varsayımlar:
- SPEC 25 montaj uçları A3'ten önce `/api/montaj/...` olarak yazıldı; A3 sonrası ekran uçları
  `/api/ekran/montaj/...` altında olabilir. Test hangisi varsa onu kullanır (A3: "adlar farklı çıkarsa
  A3'ünkiler geçerlidir").
- Etkideki süre ve girişim ölçülerinin anahtar adları SPEC 37'de verilmez: torna satırında farkı SPEC 25
  `sure_farki`'na eşit (rel 1e-12) bir sayısal anahtar, montaj satırında adında "girisim" geçen ve önce > 0,
  sonra 0 olan bir sayısal anahtar aranır.
"""

from __future__ import annotations

import json
import math

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.occt]

IS = "kademeli_mil"
MONTAJ = "yatak_grubu"
YAMA = [{"bolum": "torna_isleri", "isaretci": f"/{IS}/parametreler/L", "deger": 9.5}]


def _istemci():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    return TestClient(uygulama(dist=None))


def _montaj_yolu(c) -> str:
    for onek in ("/api/montaj", "/api/ekran/montaj/montaj"):
        if c.get(f"{onek}/{MONTAJ}").status_code == 200:
            return f"{onek}/{MONTAJ}"
    pytest.skip("SPEC 25 montaj uçları henüz yok")


def _anlik(c, montaj: str) -> bytes:
    """GET /api/is/kademeli_mil ve GET montaj yanıtları (JSON olarak)."""
    r1 = c.get(f"/api/is/{IS}")
    r2 = c.get(montaj)
    assert r1.status_code == 200 and r2.status_code == 200
    return json.dumps([r1.json(), r2.json()], sort_keys=True).encode()


def _satir(etki: list[dict], bolum: str) -> dict:
    s = [x for x in etki if x["bolum"] == bolum]
    assert len(s) == 1, f"etkide {bolum} satırı yok: {[x['bolum'] for x in etki]}"
    return s[0]


def test_bearing_thread(tmp_path):
    from tezgah.ekranlar import ekranlar
    from tezgah.ornekler_37 import ORNEK_PROJELER, ornek_proje

    # kabuk A3 keşfiyle bulunur; örnek proje bellekte kurulur ve iki bölümü taşır
    kayit = ekranlar()
    assert "kabuk" in [e.ad for e in kayit]
    eksik = {"torna_isleri", "montajlar"} - {e.bolum for e in kayit}
    if eksik:
        pytest.skip(f"SPEC 25 ekranları henüz yok (sahipsiz bölümler: {', '.join(sorted(eksik))})")
    assert MONTAJ in ORNEK_PROJELER
    ornek = ornek_proje(MONTAJ)
    assert {"torna_isleri", "montajlar", "isler"} <= set(ornek.bolumler)
    assert dict(ornek.bolumler)["torna_isleri"][IS]["parametreler"]["L"] == 20

    c = _istemci()
    r = c.post(f"/api/proje/ornek/{MONTAJ}")
    assert r.status_code == 200, r.text
    montaj = _montaj_yolu(c)
    once = _anlik(c, montaj)

    r = c.post("/api/proje/degistir", json={"etiket": "L 9.5", "yamalar": YAMA, "onizle": False})
    assert r.status_code == 200, r.text
    etki = r.json()["etki"]
    sonra = _anlik(c, montaj)
    assert sonra != once

    # torna satırı: sayısal farklar; montaj satırı: girişim önce > 0, sonra 0
    torna = _satir(etki, "torna_isleri")
    montaj_satir = _satir(etki, "montajlar")
    assert [x["bolum"] for x in etki].index("torna_isleri") < [x["bolum"] for x in etki].index("montajlar")
    girisim = [
        k
        for k in montaj_satir["once"]
        if "girisim" in k
        and isinstance(montaj_satir["once"][k], (int, float))
        and not isinstance(montaj_satir["once"][k], bool)
    ]
    assert girisim, montaj_satir
    assert any(montaj_satir["once"][k] > 0 and montaj_satir["sonra"][k] == 0 for k in girisim), montaj_satir
    for x in etki:
        for k, f in x["fark"].items():
            assert f == x["sonra"][k] - x["once"][k]

    # geri al → değişiklik öncesi; yinele → değişiklik sonrası (JSON olarak aynı)
    assert c.post("/api/proje/geri-al").status_code == 200
    assert _anlik(c, montaj) == once
    assert c.post("/api/proje/yinele").status_code == 200
    assert _anlik(c, montaj) == sonra

    # kaydet → yeni sunucu → aç → aynı iki yanıt ve aynı geçmiş
    yol = tmp_path / "yatak_grubu.3dc"
    assert c.post("/api/proje/kaydet", json={"yol": str(yol)}).status_code == 200
    gecmis = c.get("/api/proje/gecmis").json()

    c2 = _istemci()
    assert c2.post("/api/proje/ac", json={"yol": str(yol)}).status_code == 200
    montaj2 = _montaj_yolu(c2)
    assert _anlik(c2, montaj2) == sonra
    assert c2.get("/api/proje/gecmis").json() == gecmis

    # SPEC 25 ile aynı değişiklik: süre farkı etkideki torna farkına eşit (rel 1e-12)
    assert c2.post("/api/proje/geri-al").status_code == 200
    assert _anlik(c2, montaj2) == once
    r = c2.post(f"{montaj2}/parametre", json={"is": IS, "anahtar": "L", "deger": 9.5})
    assert r.status_code == 200, r.text
    sure_farki = r.json()["sure_farki"]
    assert sure_farki != 0
    sayisal = [f for f in torna["fark"].values() if isinstance(f, (int, float))]
    assert any(math.isclose(f, sure_farki, rel_tol=1e-12) for f in sayisal), (torna["fark"], sure_farki)
