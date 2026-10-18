"""SPEC 63 K8 — Tezgah "gönder" ucu: `POST /api/ekran/freze/{is}/gonder`.

Testler yalnız SPEC 63 metninden ve uç sözleşmesinden (proje dosyası dnc-63/tezgah-gonder-ucu.md)
yazıldı; ucun gövdesi okunmadı. Sözleşme:
- Gövde {tezgah, operator, zaman?, program_no, ad?, ezme=false, gerekce=""}; zaman yoksa uç UTC'den üretir.
- `yerel_parcalar/dnc-hedefleri.json` = {"tezgahlar": {<ad>: {"klasor", "profil"}}}; ad ya da dosya yoksa 422
  "dnc-hedefleri.json'da <ad> yok". `profil` hazır profil adı ya da profil dosyası yolu.
- Başarı 200 {"yol", "sonuc", "kayit"}; CamError 422, `detail` metin.
  Kayıt `yerel_parcalar/gonderim-kaydi.jsonl`.

`yerel_parcalar/` yolları göreli olduğundan testler çalışma klasörünü `tmp_path`'e çevirir
(monkeypatch.chdir). Uydurma iş: Tezgah örnek işi "flans-plakasi". Örnek tezgâh profillerinin Z kursu
tutucusuz takımı kabul etmediği için eksen sınırsız uydurma bir Fanuc profili dosyadan verilir.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from cam.model import MachineProfile  # noqa: E402
from cam.post import save_machine  # noqa: E402
from tezgah.sunucu import uygulama  # noqa: E402

IS = "flans-plakasi"
UC = f"/api/ekran/freze/{IS}/gonder"
TEZGAH = "DIK-1"
ZAMAN = "2026-10-18T12:00:00Z"


def profil(verified: bool = False) -> MachineProfile:
    return MachineProfile(
        name="TEST-FANUC",
        controller="fanuc",
        rpm_max=30_000.0,
        feed_max=20_000.0,
        program_no_range=(1, 9999),
        tool_slots=20,
        verified=verified,
    )


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Çalışma klasörü tmp_path; dnc-hedefleri.json'da DIK-1 / DIK-2 → tmp_path/tezgah (uydurma profiller)."""
    monkeypatch.chdir(tmp_path)
    yp = tmp_path / "yerel_parcalar"
    yp.mkdir()
    klasor = tmp_path / "tezgah"
    klasor.mkdir()
    save_machine(profil(), tmp_path / "test-fanuc.json")
    save_machine(profil(verified=True), tmp_path / "test-fanuc-dogrulanmis.json")
    hedefler = {
        "tezgahlar": {
            TEZGAH: {"klasor": str(klasor), "profil": str(tmp_path / "test-fanuc.json")},
            "DIK-2": {"klasor": str(klasor), "profil": str(tmp_path / "test-fanuc-dogrulanmis.json")},
        }
    }
    (yp / "dnc-hedefleri.json").write_text(json.dumps(hedefler), encoding="utf-8")
    return {"kok": tmp_path, "klasor": klasor, "kayit": yp / "gonderim-kaydi.jsonl"}


@pytest.fixture
def istemci() -> TestClient:
    return TestClient(uygulama(dist=None))


def govde(**kw) -> dict:
    d = {"tezgah": TEZGAH, "operator": "operator1", "zaman": ZAMAN, "program_no": 12, "ad": None}
    d.update(kw)
    return d


def liste(klasor: Path) -> list[tuple[str, bytes]]:
    return sorted(
        (str(p.relative_to(klasor)), p.read_bytes() if p.is_file() else b"") for p in klasor.rglob("*")
    )


def detay(r) -> str:
    d = r.json()["detail"]
    return d if isinstance(d, str) else json.dumps(d, ensure_ascii=False)


# ------------------------------------------------------------------ başarı


def test_basarili_gonderim(ortam, istemci):
    r = istemci.post(UC, json=govde())
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j) >= {"yol", "sonuc", "kayit"}
    assert j["sonuc"] == "yazildi"
    yol = Path(j["yol"])
    assert yol == ortam["klasor"] / "O0012"
    b = yol.read_bytes()
    assert b.startswith(b"%\r\n") and b.endswith(b"%\r\n")  # Fanuc kuralı (SPEC 63 §2)
    k = j["kayit"]
    assert k["zaman"] == ZAMAN and k["operator"] == "operator1"
    assert k["sonuc"] == "yazildi" and k["program"]["program_no"] == 12
    assert k["dogrulanmis"] is False  # onay penceresi "DOĞRULANMAMIŞ PROFİL" uyarısını buradan alır
    # kayıt yerel_parcalar/gonderim-kaydi.jsonl'a eklendi ve yanıttaki kayıtla aynı
    satirlar = ortam["kayit"].read_text(encoding="utf-8").splitlines()
    assert [json.loads(s) for s in satirlar] == [k]


def test_ikinci_ayni_gonderim_ayni(ortam, istemci):
    assert istemci.post(UC, json=govde()).status_code == 200
    r = istemci.post(UC, json=govde(zaman="2026-10-18T12:05:00Z"))
    assert r.status_code == 200, r.text
    assert r.json()["sonuc"] == "ayni"
    assert len(ortam["kayit"].read_text(encoding="utf-8").splitlines()) == 2


def test_dogrulanmis_profil(ortam, istemci):
    r = istemci.post(UC, json=govde(tezgah="DIK-2"))
    assert r.status_code == 200, r.text
    assert r.json()["kayit"]["dogrulanmis"] is True


def test_zaman_verilmezse_ucta_uretilir(ortam, istemci):
    g = govde()
    del g["zaman"]
    r = istemci.post(UC, json=g)
    assert r.status_code == 200, r.text
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r.json()["kayit"]["zaman"])


# ------------------------------------------------------------------ ezme


def test_ezme_onaysiz_422_onayla_ezildi(ortam, istemci):
    hedef = ortam["klasor"] / "O0012"
    hedef.write_bytes(b"%\r\nO0012\r\nM30\r\n%\r\n")  # tezgâhta duran başka bir O0012
    once = liste(ortam["klasor"])

    r = istemci.post(UC, json=govde())
    assert r.status_code == 422
    assert "var ve farklı" in detay(r)
    r = istemci.post(UC, json=govde(ezme=True, gerekce=""))
    assert r.status_code == 422
    assert liste(ortam["klasor"]) == once
    assert not ortam["kayit"].exists()

    r = istemci.post(UC, json=govde(ezme=True, gerekce="rev B"))
    assert r.status_code == 200, r.text
    assert r.json()["sonuc"] == "ezildi"
    assert r.json()["kayit"]["gerekce"] == "rev B"
    assert hedef.read_bytes() != b"%\r\nO0012\r\nM30\r\n%\r\n"
    assert list((ortam["klasor"] / ".3dcore-yedek").iterdir())


# ------------------------------------------------------------------ ön koşul hatası


def test_on_kosul_hatasi_422_metin(ortam, istemci):
    once = liste(ortam["klasor"])
    r = istemci.post(UC, json=govde(program_no=99999))  # Ö3: profil aralığı [1, 9999] dışında
    assert r.status_code == 422
    assert "99999" in detay(r)
    assert liste(ortam["klasor"]) == once
    assert not ortam["kayit"].exists()


# ------------------------------------------------------------------ tanımsız tezgâh


def test_tanimsiz_tezgah_422(ortam, istemci):
    r = istemci.post(UC, json=govde(tezgah="YOK-TEZGAH"))
    assert r.status_code == 422
    assert "dnc-hedefleri.json'da YOK-TEZGAH yok" in detay(r)
    assert liste(ortam["klasor"]) == []


def test_hedefler_dosyasi_yoksa_422(ortam, istemci):
    (ortam["kok"] / "yerel_parcalar" / "dnc-hedefleri.json").unlink()
    r = istemci.post(UC, json=govde())
    assert r.status_code == 422
    assert f"dnc-hedefleri.json'da {TEZGAH} yok" in detay(r)
