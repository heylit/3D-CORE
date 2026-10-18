"""SPEC 26 K13 — bağımlılık kuralı, AST taraması (SPEC 24 test_bagimlilik.py'nin genişletmesi).

- `sketch` `geometry`'yi import etmez.
- Hiçbir paket (`sketch` dahil) `tezgah`'ı import etmez.
- `geometry/extrude.py` `sketch`'ten yalnızca `sketch.model`'i import eder.
- `tezgah/ifade.py`, `tezgah/modelleme.py`, `tezgah/model_kopru.py` web bağımlılığı olmadan çalışır.

SPEC 24'ün test dosyası değiştirilmez (SPEC 26: "SPEC 02, 17, 23, 24 testleri değişmeden geçiyor").
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
PAKETLER = ("sketch", "cam", "assy", "geometry", "core", "viz", "fileio", "mesh")
WEB = ("fastapi", "uvicorn", "starlette")


def _importlar(dosya: Path) -> list[tuple[str, int]]:
    """(modül, satır); `from x import y` için hem `x` hem `x.y` döner (alt modül importu olabilir)."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    sonuc = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            sonuc += [(a.name, d.lineno) for a in d.names]
        elif isinstance(d, ast.ImportFrom) and d.level == 0 and d.module:
            sonuc.append((d.module, d.lineno))
            sonuc += [(f"{d.module}.{a.name}", d.lineno) for a in d.names]
    return sonuc


def _py(paket: str) -> list[Path]:
    return sorted((KOK / paket).rglob("*.py"))


def test_sketch_geometry_import_etmez():
    ihlal = [
        f"{f.relative_to(KOK)}:{n} {m}"
        for f in _py("sketch")
        for m, n in _importlar(f)
        if m.split(".")[0] == "geometry"
    ]
    assert not ihlal, ihlal


@pytest.mark.parametrize("paket", PAKETLER)
def test_hicbir_paket_tezgah_import_etmez(paket):
    ihlal = [
        f"{f.relative_to(KOK)}:{n} {m}"
        for f in _py(paket)
        for m, n in _importlar(f)
        if m.split(".")[0] == "tezgah"
    ]
    assert not ihlal, ihlal


def test_extrude_sketch_ten_yalniz_model():
    f = KOK / "geometry" / "extrude.py"
    assert f.is_file()
    sk = {m for m, _ in _importlar(f) if m.split(".")[0] == "sketch"}
    # `from sketch.model import X` → {"sketch.model", "sketch.model.X"}; başka sketch modülü olamaz
    assert sk, "extrude.py sketch.model'i kullanmalı (Plane, SketchRegion)"
    assert all(m == "sketch.model" or m.startswith("sketch.model.") for m in sk), sorted(sk)


@pytest.mark.parametrize("modul", ["ifade.py", "modelleme.py", "model_kopru.py"])
def test_model_modulleri_web_bagimsiz(modul):
    f = KOK / "tezgah" / modul
    ihlal = [f"{n} {m}" for m, n in _importlar(f) if m.split(".")[0] in WEB]
    assert not ihlal, ihlal


def test_ifade_eval_kullanmaz():
    """İfade dili ast ağacı yürünerek değerlendirilir; eval / exec / compile çağrısı yok."""
    agac = ast.parse((KOK / "tezgah" / "ifade.py").read_text(encoding="utf-8"))
    cagri = {
        d.func.id
        for d in ast.walk(agac)
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Name)
        and d.func.id in {"eval", "exec", "compile"}
    }
    assert not cagri, cagri
