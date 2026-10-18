"""
SPEC 24 K9 — bağımlılık kuralı, AST taraması.

- `cam`, `assy`, `geometry`, `core`, `viz`, `fileio`, `mesh` içinden hiçbir modül `tezgah`'ı import etmez.
- `tezgah`, başka paketlerin iç (özel, `_` ile başlayan) modüllerini ya da adlarını import etmez; yalnızca
  `model.py` arayüzlerini ve herkese açık fonksiyonları kullanır. `viz/`'e bağımlı olamaz (CLAUDE.md).
- Köprü ve örnek işler web bağımlılığı olmadan çalışır: `kopru.py` ve `isler.py` FastAPI / uvicorn /
  starlette import etmez.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
DIGER_PAKETLER = ("cam", "assy", "geometry", "core", "viz", "fileio", "mesh")
WEB = ("fastapi", "uvicorn", "starlette")


def _importlar(dosya: Path) -> list[tuple[str, list[str], int]]:
    """(modül, içe alınan adlar, satır). Göreli importlar tezgah içi sayılır ve atlanır."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    sonuc = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            for a in d.names:
                sonuc.append((a.name, [], d.lineno))
        elif isinstance(d, ast.ImportFrom) and d.level == 0 and d.module:
            sonuc.append((d.module, [a.name for a in d.names], d.lineno))
    return sonuc


def _py(paket: str) -> list[Path]:
    return sorted((KOK / paket).rglob("*.py"))


def test_tezgah_package_exists():
    assert (KOK / "tezgah" / "kopru.py").is_file()
    assert _py("tezgah")


@pytest.mark.parametrize("paket", DIGER_PAKETLER)
def test_no_package_imports_tezgah(paket):
    ihlal = [
        f"{f.relative_to(KOK)}:{n} {m}"
        for f in _py(paket)
        for m, _, n in _importlar(f)
        if m == "tezgah" or m.startswith("tezgah.")
    ]
    assert not ihlal, ihlal


def test_tezgah_uses_only_public_interfaces():
    ihlal = []
    for f in _py("tezgah"):
        for m, adlar, n in _importlar(f):
            parca = m.split(".")
            if parca[0] not in DIGER_PAKETLER:
                continue
            yer = f"{f.relative_to(KOK)}:{n} {m}"
            if parca[0] == "viz":
                ihlal.append(f"{yer} (viz'e bağımlılık yasak)")
            if any(p.startswith("_") for p in parca[1:]):
                ihlal.append(f"{yer} (iç modül)")
            ihlal += [f"{yer}.{a} (özel ad)" for a in adlar if a.startswith("_")]
    assert not ihlal, ihlal


@pytest.mark.parametrize("modul", ["kopru.py", "isler.py", "__init__.py"])
def test_bridge_has_no_web_dependency(modul):
    f = KOK / "tezgah" / modul
    ihlal = [f"{n} {m}" for m, _, n in _importlar(f) if m.split(".")[0] in WEB]
    assert not ihlal, ihlal
