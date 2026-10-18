"""SPEC 54 K1 — bozuk girdi koleksiyonu: her durum beklenen çekirdek hata sınıfıyla düşer.

Başka istisna (`Exception`, `IndexError`, OCCT `StdFail_*` …), `nan` ya da yarım sonuç yok; mesajda beklenen
`<nesne>` var. Durum 12 (Tezgah ucuna `nan`) ve 15 (bozuk kurtarma dosyası) ayrı testlerdir.

Testler yalnız specs/54-saglamlik.md'den ve iskelet imzalarından yazıldı; SPEC 54 kodu okunmadı.
"""

from __future__ import annotations

import json
import math
import re

import pytest

from tests.saglamlik.durumlar import DURUMLAR, Durum, calistir, param
from tests.saglamlik.durumlar import _gecerli_3dc as gecerli_3dc


def _sinif_zinciri(e: BaseException) -> list[str]:
    return [k.__name__ for k in type(e).__mro__]


@pytest.mark.parametrize("d", [param(d, "core_error") for d in DURUMLAR])
def test_broken_input_raises_core_error(d: Durum, tmp_path):
    e = calistir(d, tmp_path)
    assert e is not None, f"durum {d.kimlik} ({d.aciklama}): hata çıkmadı"
    assert d.sinif in _sinif_zinciri(e), (
        f"durum {d.kimlik} ({d.aciklama}): {d.sinif} bekleniyordu, {type(e).__name__}: {e}"
    )
    metin = str(e)
    if d.model_py:
        return  # Karar 4: mesaj model.py'de; nesne ve biçim test_mesaj_bicimi'nde (xfail)
    assert "nan" not in re.findall(r"[a-z]+", metin.lower()), f"durum {d.kimlik}: mesajda nan: {metin}"
    for parca in d.nesne:
        assert parca in metin, f"durum {d.kimlik}: mesajda {parca!r} yok: {metin}"
    for kalip in d.ek:
        assert re.search(kalip, metin, re.IGNORECASE), f"durum {d.kimlik}: mesajda /{kalip}/ yok: {metin}"


# ---------------------------------------------------------------- 12 Tezgah ucuna nan


def _istemci(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tests.tezgah.test_kabuk import _router, _sahteler
    from tezgah.ekranlar import kabuk as kabuk_mod
    from tezgah.sunucu import uygulama

    s, _ = _sahteler()
    app = uygulama(dist=None, ekranlar=[x.ekran(_router(x)) for x in s.values()] + [kabuk_mod.EKRAN])
    app.state.proje_klasoru = tmp_path
    app.state.kurtarma_ayari = False
    return s, TestClient(app, raise_server_exceptions=False)


def _nan_var(x) -> bool:
    if isinstance(x, float):
        return math.isnan(x) or math.isinf(x)
    if isinstance(x, dict):
        return any(_nan_var(v) for v in x.values())
    if isinstance(x, list):
        return any(_nan_var(v) for v in x)
    return False


@pytest.mark.parametrize("deger", ["NaN", float("nan"), float("inf")], ids=["metin", "nan", "inf"])
def test_nan_parameter_is_rejected(deger, tmp_path):
    """Durum 12: `"L": "NaN"` benzeri girdi 422 ile reddedilir; nan hiçbir bölüme yazılmaz; kart var."""
    s, c = _istemci(tmp_path)
    once = {ad: x.disa_aktar() for ad, x in s.items()}
    govde = json.dumps(
        {"etiket": "L nan", "yamalar": [{"bolum": "kok", "isaretci": "/v", "deger": deger}], "onizle": False},
        allow_nan=True,
    )
    r = c.post("/api/proje/degistir", content=govde, headers={"content-type": "application/json"})
    assert r.status_code == 422, r.text
    yanit = r.json()
    assert "detail" in yanit
    assert set(yanit["hata"]) == {"sinif", "nesne", "ne_oldu", "oneri", "teknik"}
    assert {ad: x.disa_aktar() for ad, x in s.items()} == once
    d = c.get("/api/proje")
    assert d.status_code == 200
    assert not _nan_var(json.loads(d.text, parse_constant=lambda _s: float("nan")))
    assert c.get("/api/proje/gecmis").json()["kayitlar"] == []


# ---------------------------------------------------------------- 15 bozuk kurtarma dosyası


def test_broken_recovery_file_does_not_block_open(tmp_path):
    """Durum 15: kurtarma dosyasının yarısı → okunamaz diye işaretlenir, asıl dosya yine açılır."""
    from fileio import kurtarma as kr
    from fileio.proje import ac, uygula

    P = gecerli_3dc(tmp_path, "yatak")
    once = P.read_bytes()
    p = uygula(ac(P), "L 50", "modelleme", {"parca": {"sema": 1, "L": 50.0}})
    yol = kr.kurtarma_yolu(P, "yatak", "0" * 64)
    kr.kurtarma_yaz(p, yol, kr_ozet(P), 1)
    yol.write_bytes(yol.read_bytes()[: yol.stat().st_size // 2])

    b = kr.kurtarma_bul(P)
    assert b is not None
    assert b["okunur"] is False
    assert b["neden"]
    assert P.read_bytes() == once
    assert dict(ac(P).bolumler)["parca"]["L"] == 40.0


def kr_ozet(P) -> str:
    import hashlib

    return hashlib.sha256(P.read_bytes()).hexdigest()
