"""SPEC 54 §5 — kurtarma dosyasının kitaplık kısmı (`fileio/kurtarma.py`): K5–K8, K12.

Testler yalnız specs/54-saglamlik.md'den ("Arayüz ayrıntıları") ve iskelet imzalarından yazıldı; SPEC 54 kodu
okunmadı. `fileio.proje` (SPEC 37) yalnız genel arayüzüyle kullanılır.

Her test asıl proje dosyası `P`'nin baytlarını işlemlerden önce ve sonra karşılaştırır (K7).
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

from fileio import kurtarma as kr
from fileio.proje import ProjeError, ac, bos_proje, kanonik, kaydet, uygula

KOK = Path(__file__).resolve().parents[2]
SIFIR = "0123456789abcdef" * 4  # uydurma ilk açılış özeti


def _sha(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _proje(ad: str = "yatak", L: float = 40.0):
    p = bos_proje(ad)
    return uygula(p, f"L {L}", "modelleme", {"parca": {"sema": 1, "L": L}})


def _kayitli(tmp_path: Path, ad: str = "yatak") -> tuple[Path, object]:
    """Diske kaydedilmiş P ve onun üstüne 2 değişiklik yapılmış kirli proje."""
    P = tmp_path / f"{ad}.3dc"
    p = _proje(ad)
    kaydet(p, P)
    p = ac(P)
    p = uygula(p, "L 50", "modelleme", {"parca": {"sema": 1, "L": 50.0}})
    p = uygula(p, "delik", "modelleme", {"delik": {"sema": 1, "d": 6.0}})
    return P, p


def _yan(yol: Path) -> Path:
    return yol.with_name(yol.name + ".json")


def _durum(p) -> bytes:
    return kanonik(
        {
            "bolumler": dict(p.bolumler),
            "gecmis": {"kayitlar": [dict(k) for k in p.gecmis.kayitlar], "konum": p.gecmis.konum},
        }
    )


class _Koru:
    """P'nin baytlarını tutar; `denetle()` değişmediğini ve hâlâ var olduğunu doğrular (K7)."""

    def __init__(self, P: Path):
        self.P = P
        self.bayt = P.read_bytes() if P.exists() else None

    def denetle(self) -> None:
        if self.bayt is None:
            assert not self.P.exists()
        else:
            assert self.P.read_bytes() == self.bayt, "asıl proje dosyası değişti"


# ---------------------------------------------------------------- K5 zamanlama


def test_settings_defaults_and_limits():
    a = kr.KurtarmaAyari()
    assert (a.T, a.K) == (60.0, 10)
    kr.KurtarmaAyari(T=10.0, K=1)
    with pytest.raises(ProjeError):
        kr.KurtarmaAyari(T=9.99)
    with pytest.raises(ProjeError):
        kr.KurtarmaAyari(K=0)


# (simdi, son_yazim, yeni_kayit, kirli, T, K) → beklenen
TABLO = [
    (100.0, 99.0, 0, False, 60.0, 10, False),  # temiz: hiçbir zaman
    (1e9, 0.0, 999, False, 60.0, 10, False),  # temiz: T de K de dolsa yazılmaz
    (100.0, None, 0, False, 60.0, 10, False),
    (100.0, None, 0, True, 60.0, 10, True),  # hiç yazılmamış ve kirli
    (100.0, 50.0, 0, True, 60.0, 10, False),  # 50 s < T
    (110.0, 50.0, 0, True, 60.0, 10, True),  # tam T
    (200.0, 50.0, 0, True, 60.0, 10, True),
    (100.0, 99.0, 9, True, 60.0, 10, False),  # K − 1
    (100.0, 99.0, 10, True, 60.0, 10, True),  # tam K
    (100.0, 99.0, 3, True, 60.0, 3, True),  # K = 3 (Karar 7)
    (100.0, 85.0, 0, True, 15.0, 10, True),
]


@pytest.mark.parametrize("simdi, son, yeni, kirli, T, K, beklenen", TABLO)
def test_schedule(simdi, son, yeni, kirli, T, K, beklenen):
    a = kr.KurtarmaAyari(T=T, K=K)
    assert kr.yazmali_mi(simdi, son, yeni, kirli, a) is beklenen


# ---------------------------------------------------------------- yol


def test_recovery_path_saved_project(tmp_path):
    P = tmp_path / "alt klasör" / "yatak.3dc"
    assert kr.kurtarma_yolu(P, "yatak", SIFIR) == P.parent / ".yatak.3dc.kurtarma"


def test_recovery_path_unsaved_project(tmp_path, monkeypatch):
    klasor = tmp_path / "kurtarmalar"
    assert kr.kurtarma_yolu(None, "taslak", SIFIR, klasor) == klasor / "taslak-01234567.3dc.kurtarma"
    # klasör verilmezse çağrı anındaki ev dizini
    monkeypatch.setenv("HOME", str(tmp_path / "ev"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "ev"))
    beklenen = Path.home() / "3D-CORE projeleri" / ".kurtarma" / "taslak-01234567.3dc.kurtarma"
    assert kr.kurtarma_yolu(None, "taslak", SIFIR) == beklenen


# ---------------------------------------------------------------- K6 gidiş-dönüş


def test_round_trip(tmp_path):
    P, p = _kayitli(tmp_path)
    koru = _Koru(P)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p, yol, _sha(P), 7)
    koru.denetle()

    geri = ac(yol)  # SPEC 37 ac ile açılır
    assert _durum(geri) == _durum(p)
    assert len(geri.gecmis.kayitlar) == 3 and geri.gecmis.konum == 3
    assert dict(geri.onbellek) == {}

    yan = json.loads(_yan(yol).read_text(encoding="utf-8"))
    assert yan == {"kaynak": "yatak", "kaynak_ozet": _sha(P), "sayac": 7}


def test_round_trip_drops_cache(tmp_path):
    from fileio.proje import Onbellek

    P, p = _kayitli(tmp_path)
    p = type(p)(
        ad=p.ad,
        bolumler=p.bolumler,
        onbellek={"modelleme.sonuc": Onbellek("a" * 64, b"\x00\x01agir sonuc")},
        gecmis=p.gecmis,
    )
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p, yol, _sha(P), 1)
    assert dict(ac(yol).onbellek) == {}
    with zipfile.ZipFile(yol) as z:
        assert not [a for a in z.namelist() if a.startswith("onbellek/")]


def test_round_trip_unsaved_project(tmp_path):
    p = _proje("taslak")
    yol = kr.kurtarma_yolu(None, "taslak", SIFIR, tmp_path / ".kurtarma")
    kr.kurtarma_yaz(p, yol, None, 1)  # klasörü kendisi oluşturur
    assert yol.is_file()
    assert _durum(ac(yol)) == _durum(p)
    assert json.loads(_yan(yol).read_text(encoding="utf-8"))["kaynak_ozet"] is None


def test_rewrite_replaces_previous(tmp_path):
    P, p = _kayitli(tmp_path)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p, yol, _sha(P), 1)
    p2 = uygula(p, "L 60", "modelleme", {"parca": {"sema": 1, "L": 60.0}})
    kr.kurtarma_yaz(p2, yol, _sha(P), 2)
    assert _durum(ac(yol)) == _durum(p2)
    assert json.loads(_yan(yol).read_text(encoding="utf-8"))["sayac"] == 2


# ---------------------------------------------------------------- K7 asıl dosya korunur


def _tmp_kalmadi(klasor: Path) -> None:
    kalan = [a.name for a in klasor.rglob("*") if a.name.endswith(".tmp")]
    assert kalan == [], f".tmp kaldı: {kalan}"


def test_never_touches_project(tmp_path, monkeypatch):
    """Her kurtarma işlemi P'yi aynı bırakır; yazım yarıda kesilince eski kurtarma aynı, .tmp yok."""
    P, p = _kayitli(tmp_path)
    koru = _Koru(P)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)

    kr.kurtarma_yaz(p, yol, _sha(P), 1)
    koru.denetle()
    kr.kurtarma_bul(P)
    koru.denetle()
    assert kr.kurtarma_eskit(P).is_file()
    koru.denetle()
    kr.kurtarma_yaz(p, yol, _sha(P), 2)
    kr.kurtarma_temizle(P)
    koru.denetle()
    kr.kurtarma_temizle(P)  # yoksa sessizce geçer
    koru.denetle()
    _tmp_kalmadi(tmp_path)

    # yeniden yaz, sonra yarıda kes (atomik yer değiştirme başarısız)
    kr.kurtarma_yaz(p, yol, _sha(P), 3)
    eski_3dc, eski_json = yol.read_bytes(), _yan(yol).read_bytes()
    p2 = uygula(p, "L 70", "modelleme", {"parca": {"sema": 1, "L": 70.0}})

    def kes(*a, **k):
        raise OSError(28, "No space left on device (test)")

    monkeypatch.setattr(os, "replace", kes)
    with pytest.raises(OSError):
        kr.kurtarma_yaz(p2, yol, _sha(P), 4)
    monkeypatch.undo()
    assert yol.read_bytes() == eski_3dc
    assert _yan(yol).read_bytes() == eski_json
    _tmp_kalmadi(tmp_path)
    koru.denetle()


def test_interrupted_first_write_leaves_nothing(tmp_path, monkeypatch):
    P, p = _kayitli(tmp_path)
    koru = _Koru(P)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)

    def kes(*a, **k):
        raise OSError(13, "Permission denied (test)")

    monkeypatch.setattr(os, "replace", kes)
    with pytest.raises(OSError):
        kr.kurtarma_yaz(p, yol, _sha(P), 1)
    monkeypatch.undo()
    assert not yol.exists()
    _tmp_kalmadi(tmp_path)
    assert kr.kurtarma_bul(P) is None
    koru.denetle()


# ---------------------------------------------------------------- K8 açılış kararı


def test_find_none(tmp_path):
    P, _ = _kayitli(tmp_path)
    koru = _Koru(P)
    assert kr.kurtarma_bul(P) is None
    koru.denetle()


def test_find_same_content(tmp_path):
    P, _ = _kayitli(tmp_path)
    koru = _Koru(P)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(ac(P), yol, _sha(P), 1)
    b = kr.kurtarma_bul(P)
    assert b == {"yol": str(yol), "okunur": True, "kaynak_tutuyor": True, "farkli": False, "neden": None}
    koru.denetle()


def test_find_different_source_matches(tmp_path):
    P, p = _kayitli(tmp_path)
    koru = _Koru(P)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p, yol, _sha(P), 2)
    b = kr.kurtarma_bul(P)
    assert b == {"yol": str(yol), "okunur": True, "kaynak_tutuyor": True, "farkli": True, "neden": None}
    koru.denetle()


def test_find_different_history_only(tmp_path):
    """Bölümler aynı, geçmiş farklı → farklı (geri alınmış değişiklik)."""
    from fileio.proje import geri_al

    P = tmp_path / "yatak.3dc"
    p = _proje()
    kaydet(p, P)
    p2 = uygula(ac(P), "L 50", "modelleme", {"parca": {"sema": 1, "L": 50.0}})
    p2 = geri_al(p2)
    assert dict(p2.bolumler) == dict(ac(P).bolumler)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p2, yol, _sha(P), 1)
    assert kr.kurtarma_bul(P)["farkli"] is True


def test_find_different_source_changed(tmp_path):
    P, p = _kayitli(tmp_path)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p, yol, _sha(P), 2)
    # P başka yerde değişti (başka bir kayıt)
    kaydet(uygula(ac(P), "başka", "modelleme", {"parca": {"sema": 1, "L": 45.0}}), P)
    koru = _Koru(P)
    b = kr.kurtarma_bul(P)
    assert b["okunur"] is True
    assert b["kaynak_tutuyor"] is False
    assert b["farkli"] is True
    koru.denetle()


def test_find_project_missing(tmp_path):
    P, p = _kayitli(tmp_path)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p, yol, _sha(P), 2)
    P.unlink()
    b = kr.kurtarma_bul(P)
    assert b["okunur"] is True and b["kaynak_tutuyor"] is True and b["farkli"] is True
    assert not P.exists()


@pytest.mark.parametrize("hangisi", ["3dc_yarim", "3dc_cop", "json_cop", "json_yok"])
def test_find_broken(hangisi, tmp_path):
    P, p = _kayitli(tmp_path)
    koru = _Koru(P)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p, yol, _sha(P), 2)
    if hangisi == "3dc_yarim":
        yol.write_bytes(yol.read_bytes()[: yol.stat().st_size // 2])
    elif hangisi == "3dc_cop":
        yol.write_bytes(b"zip degil")
    elif hangisi == "json_cop":
        _yan(yol).write_text("{yarım", encoding="utf-8")
    else:
        _yan(yol).unlink()
    b = kr.kurtarma_bul(P)
    assert b is not None
    assert b["yol"] == str(yol)
    assert b["okunur"] is False and b["kaynak_tutuyor"] is False and b["farkli"] is False
    assert isinstance(b["neden"], str)
    assert " — " in b["neden"] and ": " in b["neden"], f"neden §1 biçiminde değil: {b['neden']!r}"
    koru.denetle()
    assert dict(ac(P).bolumler)["parca"]["L"] == 40.0  # P yine açılır


# ---------------------------------------------------------------- temizle / eskit


def test_clean(tmp_path):
    P, p = _kayitli(tmp_path)
    koru = _Koru(P)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p, yol, _sha(P), 1)
    eski = kr.kurtarma_eskit(P)
    kr.kurtarma_yaz(p, yol, _sha(P), 2)
    kr.kurtarma_temizle(P)
    assert not yol.exists() and not _yan(yol).exists()
    assert eski.exists() and _yan(eski).exists()  # .eski dokunulmaz
    assert kr.kurtarma_bul(P) is None
    kr.kurtarma_temizle(P)
    koru.denetle()


def test_age(tmp_path):
    P, p = _kayitli(tmp_path)
    koru = _Koru(P)
    yol = kr.kurtarma_yolu(P, "yatak", SIFIR)
    kr.kurtarma_yaz(p, yol, _sha(P), 1)
    ilk = yol.read_bytes()
    eski = kr.kurtarma_eskit(P)
    assert eski == yol.with_name(yol.name + ".eski")
    assert eski.read_bytes() == ilk
    assert eski.with_name(eski.name + ".json").is_file()
    assert not yol.exists() and not _yan(yol).exists()
    assert kr.kurtarma_bul(P) is None

    # ikinci "Yok say" eskisinin üstüne yazar
    p2 = uygula(p, "L 80", "modelleme", {"parca": {"sema": 1, "L": 80.0}})
    kr.kurtarma_yaz(p2, yol, _sha(P), 2)
    ikinci = yol.read_bytes()
    assert kr.kurtarma_eskit(P) == eski
    assert eski.read_bytes() == ikinci
    koru.denetle()

    with pytest.raises(ProjeError):
        kr.kurtarma_eskit(P)
    koru.denetle()


# ---------------------------------------------------------------- K12 bağımlılık


def test_imports():
    agac = ast.parse((KOK / "fileio" / "kurtarma.py").read_text(encoding="utf-8"))
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar = [a.name for a in d.names]
        elif isinstance(d, ast.ImportFrom):
            assert d.level == 0, "göreli import"
            adlar = [d.module]
        else:
            continue
        for ad in adlar:
            kok = ad.split(".")[0]
            assert kok == "__future__" or kok in sys.stdlib_module_names or ad == "fileio.proje", (
                f"fileio/kurtarma.py → {ad}"
            )
