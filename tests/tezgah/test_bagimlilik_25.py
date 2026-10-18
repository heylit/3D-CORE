"""
SPEC 25 K20 — bağımlılık kuralı yeni modülleri de kapsar.

SPEC 24 K9 testi (`test_bagimlilik.py`) bütün `tezgah/*.py` dosyalarını tarar; burada ek olarak:
- SPEC 25 köprüleri (`torna`, `montaj`, `iplik`, `ornekler_25`) web bağımlılığı olmadan çalışır (FastAPI /
  uvicorn / starlette yalnız `sunucu*.py`'de),
- yeni modüller dosya olarak vardır ve diğer paketlerin yalnız herkese açık adlarını kullanır,
- köprüler `viz`'e ve birbirlerinin `sunucu` modüllerine bağlı değildir.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
WEB = ("fastapi", "uvicorn", "starlette", "pydantic")
KOPRULER = ("torna.py", "montaj.py", "iplik.py", "ornekler_25.py")
DIGER_PAKETLER = ("cam", "assy", "geometry", "core", "viz", "fileio", "mesh", "sketch")


def _importlar(dosya: Path) -> list[tuple[str, list[str], int]]:
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    sonuc = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            sonuc += [(a.name, [], d.lineno) for a in d.names]
        elif isinstance(d, ast.ImportFrom) and d.level == 0 and d.module:
            sonuc.append((d.module, [a.name for a in d.names], d.lineno))
    return sonuc


@pytest.mark.parametrize("modul", [*KOPRULER, "sunucu_25.py"])
def test_new_modules_exist(modul):
    assert (KOK / "tezgah" / modul).is_file()


@pytest.mark.parametrize("modul", KOPRULER)
def test_bridges_have_no_web_dependency(modul):
    ihlal = [f"{n} {m}" for m, _, n in _importlar(KOK / "tezgah" / modul) if m.split(".")[0] in WEB]
    assert not ihlal, ihlal


@pytest.mark.parametrize("modul", KOPRULER)
def test_bridges_do_not_import_server_or_viz(modul):
    ihlal = [
        f"{n} {m}"
        for m, _, n in _importlar(KOK / "tezgah" / modul)
        if m.startswith("tezgah.sunucu") or m.split(".")[0] == "viz"
    ]
    assert not ihlal, ihlal


@pytest.mark.parametrize("modul", [*KOPRULER, "sunucu_25.py"])
def test_new_modules_use_public_names(modul):
    ihlal = []
    for m, adlar, n in _importlar(KOK / "tezgah" / modul):
        parca = m.split(".")
        if parca[0] not in DIGER_PAKETLER:
            continue
        if any(p.startswith("_") for p in parca[1:]):
            ihlal.append(f"{n} {m} (iç modül)")
        ihlal += [f"{n} {m}.{a} (özel ad)" for a in adlar if a.startswith("_")]
    assert not ihlal, ihlal


def test_bridges_import_without_web():
    """Köprü modülleri FastAPI kurulu olmasa da içe aktarılabilir (import sırasında web modülü yüklenmez)."""
    import subprocess
    import sys

    kod = (
        "import sys, importlib\n"
        "for m in ('tezgah.torna', 'tezgah.montaj', 'tezgah.iplik', 'tezgah.ornekler_25'):\n"
        "    importlib.import_module(m)\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in ('fastapi', 'uvicorn', 'starlette')]\n"
        "assert not bad, bad\n"
    )
    r = subprocess.run([sys.executable, "-c", kod], cwd=KOK, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
