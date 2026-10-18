"""
SPEC 55 — `kurulum/*.bat` metin denetimleri (K1–K5) ve CRLF kuralı (karar 3).

Betikler Linux'ta çalıştırılamaz; testler yalnızca SPEC metnindeki kuralları dosya içeriğinde denetler.
Dosya henüz yoksa test NotImplementedError ile düşer (yerelde "uygulanmamış", CI'da kırmızı).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
KURULUM = KOK / "kurulum"
BATLAR = ("kur.bat", "baslat.bat", "guncelle.bat", "kaldir.bat")

# Silme komutu: rmdir / rd / del / erase (cmd'de büyük/küçük harf duyarsız).
SILME = re.compile(r"(?i)(?:^|[\s&|(@])(rmdir|rd|del|erase)(?=\s)(.*)$")


def _bayt(ad: str) -> bytes:
    yol = KURULUM / ad
    if not yol.is_file():
        raise NotImplementedError(f"SPEC 55: kurulum/{ad} henüz yok")
    return yol.read_bytes()


def _metin(ad: str) -> str:
    return _bayt(ad).decode("utf-8")


def _komut_satirlari(ad: str) -> list[str]:
    """Yorum (`rem`, `::`) ve boş olmayan satırlar, baştaki boşluk ve `@` atılmış."""
    sonuc = []
    for s in _metin(ad).splitlines():
        s = s.strip().lstrip("@")
        if not s or s.startswith("::") or re.match(r"(?i)rem(\s|$)", s):
            continue
        sonuc.append(s)
    return sonuc


def _silme_hedefleri(ad: str) -> list[tuple[str, str]]:
    """(satır, hedefler) — `echo` satırları komut değildir; bayraklar (/s /q /f) atılır."""
    sonuc = []
    for s in _komut_satirlari(ad):
        if re.match(r"(?i)echo[\s.:]", s):
            continue
        m = SILME.search(s)
        if not m:
            continue
        kalan = re.split(r"\s(?:&&?|\|\|?|>)", m.group(2))[0]
        hedef = " ".join(t for t in kalan.split() if not t.startswith("/"))
        sonuc.append((s, hedef.strip()))
    return sonuc


# ---------------------------------------------------------------- K1


@pytest.mark.parametrize("ad", BATLAR)
def test_bat_header_and_crlf(ad):
    """K1: `@echo off` ile başlar, `setlocal` ve `chcp 65001` içerir, her satır CRLF ile biter."""
    veri = _bayt(ad)
    assert veri, f"{ad} boş"
    ilk = veri.split(b"\r\n", 1)[0].lstrip(b"\xef\xbb\xbf").strip().lower()
    assert ilk == b"@echo off", f"{ad} ilk satırı: {ilk!r}"
    kucuk = veri.lower()
    assert b"setlocal" in kucuk
    assert b"chcp 65001" in kucuk
    assert veri.endswith(b"\r\n"), f"{ad} CRLF ile bitmiyor"
    assert veri.count(b"\n") == veri.count(b"\r\n"), f"{ad}: LF satır sonu var"
    assert b"\r\r" not in veri


def test_gitattributes_keeps_bat_crlf():
    """Karar 3: `* text=auto` yanında `*.bat text eol=crlf` satırı."""
    satirlar = [s.split() for s in (KOK / ".gitattributes").read_text(encoding="utf-8").splitlines()]
    assert ["*.bat", "text", "eol=crlf"] in satirlar


# ---------------------------------------------------------------- K2


@pytest.mark.parametrize("ad", BATLAR)
def test_no_powershell_or_download(ad):
    """K2: powershell, pwsh, ExecutionPolicy, Invoke-WebRequest, curl yok (büyük/küçük harf duyarsız)."""
    kucuk = _metin(ad).lower()
    for yasak in ("powershell", "pwsh", "executionpolicy", "invoke-webrequest", "curl"):
        assert yasak not in kucuk, f"{ad}: {yasak}"


# ---------------------------------------------------------------- K3


def test_kur_finds_uv_local_first_then_where():
    """K3: önce `kurulum\\uv.exe` (betiğin klasörü), sonra `where uv`."""
    kucuk = _metin("kur.bat").lower()
    yerel = [i for i in (kucuk.find("kurulum\\uv.exe"), kucuk.find("%~dp0uv.exe")) if i >= 0]
    assert yerel, "kur.bat kurulum\\uv.exe'yi aramıyor"
    where = kucuk.find("where uv")
    assert where >= 0, "kur.bat 'where uv' kullanmıyor"
    assert min(yerel) < where


def test_kur_python_version_from_env():
    """K3: Python sürümü TEZGAH_PYTHON değişkeninden, varsayılan 3.14; `uv venv` ile."""
    metin = _metin("kur.bat")
    assert "TEZGAH_PYTHON" in metin
    assert re.search(r'(?i)set\s+"?TEZGAH_PYTHON=3\.14"?', metin), "varsayılan 3.14 atanmıyor"
    assert re.search(r"(?im)\bvenv\b[^\r\n]*--python\b", metin), "uv venv --python satırı yok"


def test_kur_never_deletes_venv():
    """K3: `.venv`'i silen rmdir / rd / del yok (tekrar çalıştırmak güvenli)."""
    ihlal = [s for s, h in _silme_hedefleri("kur.bat") if ".venv" in h.lower()]
    assert not ihlal, ihlal


def test_kur_installs_extras_and_falls_back_to_web():
    """Bölüm 2: `.[web,cad]` ile kurar; cad yoksa `.[web]` ile yeniden dener."""
    metin = _metin("kur.bat")
    assert ".[web,cad]" in metin
    assert re.search(r"\.\[web\]", metin)
    assert "kontrol.py" in metin


# ---------------------------------------------------------------- K4


def test_kaldir_deletes_only_install_artifacts():
    """K4: her silme komutunun hedefi yalnızca .venv, masaüstü Tezgah.bat ya da kurulum.log kalıbı."""
    hedefler = _silme_hedefleri("kaldir.bat")
    assert hedefler, "kaldir.bat hiçbir şey silmiyor"
    for satir, hedef in hedefler:
        h = hedef.strip('"').lower().rstrip("\\")
        izinli = h.endswith(".venv") or h.endswith("tezgah.bat") or re.search(r"kurulum\.log[*.\d]*$", h)
        assert izinli, f"izinsiz silme hedefi: {satir!r}"
        for yasak in ("projeleri", "yerel_parcalar", ".3dc"):
            assert yasak not in h, f"{yasak}: {satir!r}"
    kucuk = " ".join(h.lower() for _, h in hedefler)
    assert ".venv" in kucuk and "tezgah.bat" in kucuk and "kurulum.log" in kucuk


def test_kaldir_asks_confirmation():
    """Bölüm 6: silmeden önce onay sorar (E/H)."""
    satirlar = _komut_satirlari("kaldir.bat")
    soru = [i for i, s in enumerate(satirlar) if re.match(r"(?i)(choice\b|set\s+/p\b)", s)]
    sil = [i for i, s in enumerate(satirlar) if SILME.search(s) and not re.match(r"(?i)echo", s)]
    assert soru, "onay sorusu (choice / set /p) yok"
    assert min(soru) < min(sil)


# ---------------------------------------------------------------- K5


def test_guncelle_fast_forward_only():
    """K5: `git pull --ff-only`; reset, stash, checkout --, clean yok."""
    kucuk = _metin("guncelle.bat").lower()
    assert "git pull --ff-only" in kucuk
    komutlar = " \n".join(_komut_satirlari("guncelle.bat")).lower()
    for yasak in (r"\breset\b", r"\bstash\b", r"checkout\s+--", r"\bclean\b"):
        assert not re.search(yasak, komutlar), yasak


def test_guncelle_reruns_kur_silently():
    """Bölüm 6: sonra `kur.bat /sessiz` adımlarını yeniden çalıştırır."""
    assert re.search(r"(?i)kur\.bat\"?\s+/sessiz", _metin("guncelle.bat"))


# ---------------------------------------------------------------- başlatıcı, belge


def test_launcher_runs_tezgah_module():
    """Bölüm 4: başlatıcı depo kökünde `.venv\\Scripts\\python.exe -m tezgah` çalıştırır, başlık Tezgah."""
    metin = _metin("baslat.bat")
    assert re.search(r"(?i)cd\s+/d\b", metin)
    assert re.search(r"(?i)\.venv\\Scripts\\python\.exe\"?\s+-m\s+tezgah", metin)
    assert re.search(r"(?i)title\s+Tezgah", metin)
    assert "127.0.0.1:8724" in metin


def test_operator_readme_exists():
    yol = KURULUM / "BENIOKU.md"
    if not yol.is_file():
        raise NotImplementedError("SPEC 55: kurulum/BENIOKU.md henüz yok")
    assert "kur.bat" in yol.read_text(encoding="utf-8")
