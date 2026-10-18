"""
SPEC 47 K22 — bağımlılık kuralı (SPEC 24 K9 AST taraması yeni ekran modüllerini kapsar) ve PR kapsamı.

- Hiçbir paket `tezgah`'ı import etmez (SPEC 24 testi; burada ekran paketi için yeniden).
- Ekran modülleri (`tezgah/ekranlar/<ekran>*.py`) yalnız standart kitaplığı, numpy / scipy'yi, izinli
  paketlerin (`cam`, `assy`, `geometry`, `mesh`, `core`, `fileio`) herkese açık adlarını ve `tezgah` kabuğunu
  import eder;
  `viz` yasak; iç (`_` ile başlayan) modül ya da ad yok.
- Ekran modülleri birbirini import etmez: `plan*.py` yalnız kendi ekranının modüllerini (`plan_kopru`,
  `plan_ornekler`) import edebilir, `cok_eksen*` / `analiz*` modüllerini değil.
- Köprü ve örnek modülleri saf: FastAPI / Starlette / Uvicorn / Pydantic yalnız `<ekran>.py` (router) içinde.
- PR kapsamı: bu dalın kendi commit'leri `tezgah/ekranlar/`, `tests/tezgah/ekranlar/`,
  `tezgah/arayuz/src/ekranlar/`, `tezgah/arayuz/tests/ekranlar/` ve `durum/47-*.md` dışında dosya
  değiştirmez (git yoksa ya da `origin/main` bilinmiyorsa atlanır; başka bir uzak dalda da bulunan
  commit'ler — ör. üstüne kurulan A3 / SPEC 29 dalları — bu dalın değil o dalın sayılır).

Şimdilik 47a (Plan) modülleri vardır; 47b / 47c modülleri eklenince aynı kurallar onları da kapsar.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[3]
EKRANLAR = KOK / "tezgah" / "ekranlar"
DIGER_PAKETLER = ("cam", "assy", "geometry", "core", "viz", "fileio", "mesh")
IZINLI = ("cam", "assy", "geometry", "core", "fileio", "mesh")
UCUNCU = ("numpy", "scipy")
WEB = ("fastapi", "starlette", "uvicorn", "pydantic")
EKRAN_ADLARI = ("plan", "cok_eksen", "analiz")
IZINLI_YOLLAR = (
    "tezgah/ekranlar/",
    "tests/tezgah/ekranlar/",
    "tezgah/arayuz/src/ekranlar/",
    "tezgah/arayuz/tests/ekranlar/",
)


def _importlar(dosya: Path) -> list[tuple[str, list[str], int]]:
    """(modül, içe alınan adlar, satır). Göreli import `tezgah.ekranlar` içine çözülür."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    sonuc = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            for a in d.names:
                sonuc.append((a.name, [], d.lineno))
        elif isinstance(d, ast.ImportFrom):
            if d.level:
                taban = ".".join(["tezgah", "ekranlar"][: 3 - d.level]) if d.level <= 2 else ""
                m = ".".join(p for p in (taban, d.module or "") if p)
            else:
                m = d.module or ""
            sonuc.append((m, [a.name for a in d.names], d.lineno))
    return sonuc


def _ekran(dosya_adi: str) -> str | None:
    """Modülün ait olduğu ekran: "plan_kopru" → "plan"; ekran modülü değilse None."""
    for e in sorted(EKRAN_ADLARI, key=len, reverse=True):
        if dosya_adi == e or dosya_adi.startswith(e + "_"):
            return e
    return None


def _ekran_modulleri() -> list[Path]:
    return sorted(f for f in EKRANLAR.glob("*.py") if _ekran(f.stem) is not None)


def test_plan_modulleri_var():
    adlar = {f.stem for f in _ekran_modulleri()}
    assert {"plan", "plan_kopru", "plan_ornekler"} <= adlar


@pytest.mark.parametrize("paket", DIGER_PAKETLER)
def test_hicbir_paket_tezgahi_import_etmez(paket):
    ihlal = [
        f"{f.relative_to(KOK)}:{n} {m}"
        for f in sorted((KOK / paket).rglob("*.py"))
        for m, _, n in _importlar(f)
        if m == "tezgah" or m.startswith("tezgah.")
    ]
    assert not ihlal, ihlal


@pytest.mark.parametrize("dosya", _ekran_modulleri(), ids=lambda f: f.name)
def test_ekran_yalniz_izinli_import(dosya):
    benim = _ekran(dosya.stem)
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    ihlal = []
    for m, adlar, n in _importlar(dosya):
        parca = m.split(".")
        yer = f"{dosya.relative_to(KOK)}:{n} {m}"
        kok = parca[0]
        if kok in stdlib or kok in UCUNCU:
            continue
        if kok in WEB:
            if dosya.stem != benim:
                ihlal.append(f"{yer} (web bağımlılığı yalnız {benim}.py router'ında)")
            continue
        if kok == "tezgah":
            if len(parca) >= 3 and parca[1] == "ekranlar":
                diger = _ekran(parca[2])
                if diger is not None and diger != benim:
                    ihlal.append(f"{yer} (ekran modülleri birbirini import etmez)")
            for a in adlar:
                if parca[1:] == ["ekranlar"] and _ekran(a) not in (None, benim):
                    ihlal.append(f"{yer}.{a} (ekran modülleri birbirini import etmez)")
            continue
        if kok not in IZINLI:
            ihlal.append(f"{yer} (izinli değil: {kok})")
            continue
        if any(p.startswith("_") for p in parca[1:]):
            ihlal.append(f"{yer} (iç modül)")
        ihlal += [f"{yer}.{a} (özel ad)" for a in adlar if a.startswith("_")]
    assert not ihlal, ihlal


@pytest.mark.parametrize("modul", ["plan_kopru.py", "plan_ornekler.py"])
def test_kopru_ve_ornekler_saf(modul):
    f = EKRANLAR / modul
    ihlal = [f"{n} {m}" for m, _, n in _importlar(f) if m.split(".")[0] in WEB]
    assert not ihlal, ihlal


def test_plan_yardim_ts_saf():
    """`plan_yardim.ts` saf: DOM'a, three.js'e ya da sunucuya (api.ts) bağlı değil."""
    f = KOK / "tezgah" / "arayuz" / "src" / "ekranlar" / "plan_yardim.ts"
    metin = f.read_text(encoding="utf-8")
    importlar = [s for s in metin.splitlines() if s.lstrip().startswith("import ")]
    assert not [s for s in importlar if "three" in s or "api" in s or "sahne" in s], importlar
    assert "document." not in metin and "window." not in metin and "fetch(" not in metin


# ---------------------------------------------------------------- PR kapsamı


def _git(*arg: str) -> str:
    return subprocess.run(
        ["git", *arg], cwd=KOK, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def _kendi_dosyalar() -> list[str]:
    """Bu dalın kendi (başka uzak dalda bulunmayan, merge olmayan) commit'lerinin değiştirdiği dosyalar."""
    try:
        _git("rev-parse", "--verify", "--quiet", "origin/main")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git ya da origin/main yok")
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        pytest.skip("sığ klon: commit geçmişi eksik")
    try:
        dal = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    except subprocess.CalledProcessError:
        pytest.skip("HEAD çözülemedi")
    kendi_uzak = f"refs/remotes/origin/{dal}"
    diger = [
        r
        for r in _git("for-each-ref", "--format=%(refname)", "refs/remotes").split()
        if r != kendi_uzak and not r.endswith("/HEAD")
    ]
    cikti = _git("log", "--no-merges", "--name-only", "--format=", "HEAD", "--not", *diger)
    return sorted({s.strip() for s in cikti.splitlines() if s.strip()})


def _izinli(yol: str) -> bool:
    if yol.startswith(IZINLI_YOLLAR):
        return True
    return yol.startswith("durum/47-") and yol.endswith(".md")


def test_pr_kapsami():
    disarida = [y for y in _kendi_dosyalar() if not _izinli(y)]
    assert not disarida, (
        "SPEC 47 PR'ı yalnız ekran klasörlerine ve durum/47-*.md'ye yazar. Bu dosyalar dışarıda "
        "(üstüne kurulan bir dalın commit'iyse `git fetch origin <dal>` ile o dalı tanıt): "
        + ", ".join(disarida)
    )
