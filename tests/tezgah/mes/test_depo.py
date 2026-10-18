"""SPEC 64 K8 — saklama: atomik yazım, bozuk dosya → MES uçları 503 (dosya değişmez), yerel_parcalar/
repoda yok.

Atomik yazım sınaması yöntemden bağımsızdır: dosya sistemi "yer değiştirme" çağrıları (os.replace,
os.rename, Path.replace, Path.rename, shutil.move) hata verdirilir. Atomik yazım (geçici dosya + yer
değiştirme) bu durumda eski dosyayı sağlam bırakır; doğrudan üzerine yazan bir uygulama dosyayı bozar ve test
kırmızı olur.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("pydantic")  # [web]: fastapi + pydantic

from tests.tezgah.mes.ortak import API, DEPO, govde
from tezgah.mes import depo as mdepo
from tezgah.mes.sema import IsEmri

KOK = Path(__file__).resolve().parents[3]


def _patlat(*a, **k):
    raise OSError("yazım ortasında hata (test)")


def test_bos_depo(calisma):
    d = mdepo.yukle(DEPO)
    assert mdepo.degisenler(d, 0) == []
    assert not DEPO.exists()  # dosya ilk yazımda oluşur


def test_kanonik_json(calisma):
    d = mdepo.yukle(DEPO)
    mdepo.koy(d, IsEmri(**govde()))
    a = DEPO.read_bytes()
    json.loads(a.decode("utf-8"))
    # aynı içerik yeniden yazılınca aynı baytlar (kanonik)
    d2 = mdepo.yukle(DEPO)
    mdepo.kaydet(d2)
    assert DEPO.read_bytes() == a


def test_atomik_yazim(calisma, monkeypatch):
    d = mdepo.yukle(DEPO)
    mdepo.koy(d, IsEmri(**govde(mes_id="IE-8001")))
    once = DEPO.read_bytes()
    for hedef, ad in ((os, "replace"), (os, "rename"), (Path, "replace"), (Path, "rename"), (shutil, "move")):
        monkeypatch.setattr(hedef, ad, _patlat)
    d = mdepo.yukle(DEPO)
    with pytest.raises(OSError):
        mdepo.koy(d, IsEmri(**govde(mes_id="IE-8002")))
    monkeypatch.undo()
    assert DEPO.read_bytes() == once
    d = mdepo.yukle(DEPO)
    assert [k.is_emri.mes_id for k in mdepo.degisenler(d, 0)] == ["IE-8001"]


@pytest.mark.parametrize("icerik", [b"{bozuk", b"", b"[1, 2]", "çöp".encode()])
def test_bozuk_dosya_503(calisma, ornek_is, icerik):
    """Bozuk depo: Tezgah açılır, MES uçları 503 + mesaj, dosya değişmez (sessizce sıfırlanmaz)."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    DEPO.parent.mkdir(parents=True, exist_ok=True)
    DEPO.write_bytes(icerik)
    with pytest.raises(mdepo.MesBozuk):
        mdepo.yukle(DEPO)
    with TestClient(uygulama(dist=None), raise_server_exceptions=True) as c:
        assert c.get("/api/openapi.json").status_code == 200  # uygulama açılıyor
        for r in (
            c.get(f"{API}/is-emirleri"),
            c.get(f"{API}/is-emirleri/IE-1001"),
            c.put(f"{API}/is-emirleri/IE-1001", json=govde()),
            c.post(f"{API}/is-emirleri/IE-1001/iptal", json={"gerekce": "x"}),
            c.get(f"{API}/is-emirleri/IE-1001/program"),
        ):
            assert r.status_code == 503, r.text
            assert isinstance(r.json()["detail"], str) and r.json()["detail"]
    assert DEPO.read_bytes() == icerik


def test_yerel_parcalar_repoda_yok():
    r = subprocess.run(
        ["git", "ls-files", "--", "yerel_parcalar"], cwd=KOK, capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        pytest.skip("git yok")
    assert r.stdout.strip() == ""
    gi = (KOK / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert any(s.strip().rstrip("/") == "yerel_parcalar" for s in gi)


def test_izinli_kokenler(calisma):
    """ayar.json yoksa boş liste; varsa izinli_kokenler listesi."""
    assert mdepo.izinli_kokenler(Path("yerel_parcalar/mes/ayar.json")) == []
    yol = Path("yerel_parcalar/mes/ayar.json")
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps({"izinli_kokenler": ["http://127.0.0.1:3000"]}), encoding="utf-8")
    assert mdepo.izinli_kokenler(yol) == ["http://127.0.0.1:3000"]
