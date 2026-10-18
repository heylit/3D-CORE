"""
SPEC 47 K22 — bağımlılık kuralı, AST taraması (SPEC 24 K9'un ekran modüllerine genişlemesi).

Her ekranın kısmı ayrı fonksiyonlardadır (47a Plan, 47b Çok eksen, 47c Analiz alt PR'ları).
Genel kural (hiçbir paket `tezgah`'ı import etmez) SPEC 24 `tests/tezgah/test_bagimlilik.py`'dedir.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[3]
EKRANLAR = KOK / "tezgah" / "ekranlar"
TS_EKRANLAR = KOK / "tezgah" / "arayuz" / "src" / "ekranlar"

# SPEC 24 K9 + SPEC 47 "Mimari ve dosyalar": tezgah'ın kullanabileceği paketler.
IZINLI_PAKETLER = ("cam", "assy", "geometry", "mesh", "core", "fileio")
WEB = ("fastapi", "uvicorn", "starlette", "pydantic")
UCUNCU = ("numpy", "scipy")
# Çok eksen ekranının çekirdek modülleri: modül düzeyinde import edilmez (yokken kabuk açılmalı, K1).
COK_EKSEN_CEKIRDEK = (
    "cam.multiaxis",
    "cam.sim.tridexel",
    "cam.sim.simulate5",
    "cam.sim.raymesh",
)


def _importlar(dosya: Path, tip_denetimi_dahil: bool = True) -> list[tuple[str, list[str], int, int]]:
    """(modül, adlar, satır, düzey). Göreli importlar `tezgah.ekranlar` altına çözülür.
    `tip_denetimi_dahil=False` → `if TYPE_CHECKING:` blokları atlanır."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    atla: set[int] = set()
    if not tip_denetimi_dahil:
        for d in ast.walk(agac):
            if isinstance(d, ast.If) and "TYPE_CHECKING" in ast.unparse(d.test):
                for alt in d.body:
                    atla |= {id(x) for x in ast.walk(alt)}
    sonuc = []
    for d in ast.walk(agac):
        if id(d) in atla:
            continue
        if isinstance(d, ast.Import):
            sonuc += [(a.name, [], d.lineno, 0) for a in d.names]
        elif isinstance(d, ast.ImportFrom):
            if d.level:
                taban = "tezgah.ekranlar" if d.level == 1 else "tezgah"
                modul = f"{taban}.{d.module}" if d.module else taban
            else:
                modul = d.module or ""
            sonuc.append((modul, [a.name for a in d.names], d.lineno, d.level))
    return sonuc


def _modul_duzeyi(dosya: Path) -> list[str]:
    """Modül gövdesinde (fonksiyon / sınıf içinde değil, TYPE_CHECKING dışında) import edilen modüller."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    sonuc = []

    def gez(govde):
        for d in govde:
            if isinstance(d, ast.Import):
                sonuc.extend(a.name for a in d.names)
            elif isinstance(d, ast.ImportFrom) and d.level == 0 and d.module:
                sonuc.append(d.module)
            elif isinstance(d, ast.If) and "TYPE_CHECKING" not in ast.unparse(d.test):
                gez(d.body)
                gez(d.orelse)
            elif isinstance(d, ast.Try):
                gez(d.body)

    gez(agac.body)
    return sonuc


# ================================================================ 47b Çok eksen


def _cok_eksen_dosyalari() -> list[Path]:
    return sorted(set(EKRANLAR.glob("cok_eksen*.py")) | set(EKRANLAR.glob("_cok_eksen*.py")))


def _cok_eksen_mi(modul: str) -> bool:
    son = modul.rsplit(".", 1)[-1]
    return modul.startswith("tezgah.ekranlar.") and son.lstrip("_").startswith("cok_eksen")


def test_cok_eksen_dosyalari_var():
    adlar = {f.name for f in _cok_eksen_dosyalari()}
    assert "cok_eksen.py" in adlar
    assert any(a.lstrip("_") == "cok_eksen_kopru.py" for a in adlar)
    assert any(a.lstrip("_") == "cok_eksen_ornekler.py" for a in adlar)
    assert (TS_EKRANLAR / "cok_eksen.ts").is_file()
    assert (TS_EKRANLAR / "cok_eksen_yardim.ts").is_file()


def test_cok_eksen_yalniz_izinli_importlar():
    """Ekran modülleri yalnız stdlib, numpy/scipy, web (yalnız `cok_eksen.py`), izinli paketlerin herkese açık
    adları, A3 kabuğu (`tezgah.ekranlar`) ve kendi yardımcılarını import eder; `viz` yok."""
    stdlib = sys.stdlib_module_names
    ihlal = []
    for f in _cok_eksen_dosyalari():
        for m, adlar, n, _ in _importlar(f):
            yer = f"{f.relative_to(KOK)}:{n} {m}"
            kok = m.split(".")[0]
            if kok in stdlib or kok in UCUNCU or m == "__future__":
                continue
            if kok in WEB:
                if f.name != "cok_eksen.py":
                    ihlal.append(f"{yer} (web bağımlılığı yalnız cok_eksen.py'de)")
                continue
            if kok in IZINLI_PAKETLER:
                if any(p.startswith("_") for p in m.split(".")[1:]):
                    ihlal.append(f"{yer} (iç modül)")
                ihlal += [f"{yer}.{a} (özel ad)" for a in adlar if a.startswith("_")]
                continue
            if m == "tezgah.ekranlar":
                if f.name != "cok_eksen.py" and set(adlar) - {"Ekran"}:
                    ihlal.append(f"{yer} (yardımcı modül kabuktan yalnız tip alır)")
                continue
            if _cok_eksen_mi(m):
                continue
            if m == "tezgah" and set(adlar) <= {"SEMA"}:
                continue
            ihlal.append(f"{yer} (izinsiz)")
    assert not ihlal, ihlal


def test_cok_eksen_diger_ekranlari_import_etmez():
    """Ekran modülleri birbirini import etmez: çok eksen modülleri başka ekranı, başka modüller çok ekseni."""
    ihlal = []
    for f in sorted(EKRANLAR.glob("*.py")):
        cok = f in _cok_eksen_dosyalari()
        for m, _, n, _ in _importlar(f):
            if not m.startswith("tezgah.ekranlar.") and not (m == "tezgah.ekranlar"):
                continue
            if m == "tezgah.ekranlar":
                continue
            if cok and not _cok_eksen_mi(m):
                ihlal.append(f"{f.relative_to(KOK)}:{n} {m} (başka ekran)")
            if not cok and _cok_eksen_mi(m):
                ihlal.append(f"{f.relative_to(KOK)}:{n} {m} (çok eksen modülü)")
    for f in sorted((KOK / "tezgah").rglob("*.py")):
        if f.parent == EKRANLAR:
            continue
        for m, _, n, _ in _importlar(f):
            if _cok_eksen_mi(m):
                ihlal.append(f"{f.relative_to(KOK)}:{n} {m} (kabuk ekranı import etmez; keşif A3'te)")
    assert not ihlal, ihlal


def test_cok_eksen_cekirdek_tembel_import():
    """SPEC 41–44 modülleri modül düzeyinde import edilmez: onlar yokken ekran importu başarılı, `hazir` metni
    verir (K1). Fonksiyon içinde ve `TYPE_CHECKING` altında serbest."""
    ihlal = []
    for f in _cok_eksen_dosyalari():
        for m in _modul_duzeyi(f):
            if any(m == c or m.startswith(c + ".") for c in COK_EKSEN_CEKIRDEK):
                ihlal.append(f"{f.relative_to(KOK)} {m}")
    assert not ihlal, ihlal


def test_cok_eksen_ts_bagimliliklari():
    """Ön yüz: `cok_eksen_yardim.ts` saf (import yok ya da yalnız tip); `cok_eksen.ts` başka ekranın
    dosyasını import etmez."""
    import re

    desen = re.compile(r"""^\s*import\s+(type\s+)?[^'"]*?from\s+['"]([^'"]+)['"]""", re.M)
    yardim = (TS_EKRANLAR / "cok_eksen_yardim.ts").read_text(encoding="utf-8")
    for tip, kaynak in desen.findall(yardim):
        assert tip, f"cok_eksen_yardim.ts saf olmalı: {kaynak}"
    ekran = (TS_EKRANLAR / "cok_eksen.ts").read_text(encoding="utf-8")
    for _, kaynak in desen.findall(ekran):
        if kaynak.startswith("./"):
            ad = kaynak[2:].removesuffix(".ts")
            assert ad in ("tip", "kayit") or ad.startswith("cok_eksen"), kaynak
