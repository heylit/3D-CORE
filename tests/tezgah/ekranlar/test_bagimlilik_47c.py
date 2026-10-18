"""
SPEC 47 K22 — Analiz (47c) kısmı.

Genel AST kuralları (`tezgah`'ı kimse import etmez, ekran modülleri yalnız izinli paketlerin herkese açık
adlarını import eder, ekranlar birbirini import etmez, PR kapsamı) `test_bagimlilik_47.py`'de bütün ekran
modüllerini zaten kapsar. Burada 47c'ye özgü olanlar: modüller var, köprü ve örnekler web kitaplığından
bağımsız, `analiz_yardim.ts` saf.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[3]
EKRANLAR = KOK / "tezgah" / "ekranlar"
WEB = ("fastapi", "starlette", "uvicorn", "pydantic")
DIGER_EKRANLAR = ("plan", "cok_eksen")


def _moduller(dosya: Path) -> list[tuple[str, int]]:
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    out = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            out += [(a.name, d.lineno) for a in d.names]
        elif isinstance(d, ast.ImportFrom):
            out.append(((d.module or "") if not d.level else "." * d.level + (d.module or ""), d.lineno))
    return out


def test_analiz_modulleri_var():
    adlar = {f.stem for f in EKRANLAR.glob("*.py")}
    assert {"analiz", "_analiz_kopru", "_analiz_ornekler"} <= adlar, sorted(adlar)


@pytest.mark.parametrize("modul", ["_analiz_kopru.py", "_analiz_ornekler.py"])
def test_kopru_ve_ornekler_saf(modul):
    ihlal = [f"{n} {m}" for m, n in _moduller(EKRANLAR / modul) if m.lstrip(".").split(".")[0] in WEB]
    assert not ihlal, ihlal


@pytest.mark.parametrize("modul", ["analiz.py", "_analiz_kopru.py", "_analiz_ornekler.py"])
def test_baska_ekrani_import_etmez(modul):
    ihlal = []
    for m, n in _moduller(EKRANLAR / modul):
        son = m.lstrip(".").split(".")[-1].lstrip("_")
        if any(son == e or son.startswith(e + "_") for e in DIGER_EKRANLAR):
            ihlal.append(f"{n} {m}")
    assert not ihlal, ihlal


def test_viz_yok():
    for modul in ("analiz.py", "_analiz_kopru.py", "_analiz_ornekler.py"):
        assert not [m for m, _ in _moduller(EKRANLAR / modul) if m.split(".")[0] == "viz"], modul


def test_analiz_yardim_ts_saf():
    """`analiz_yardim.ts` saf: DOM'a, three.js'e ya da sunucuya (api.ts) bağlı değil."""
    f = KOK / "tezgah" / "arayuz" / "src" / "ekranlar" / "analiz_yardim.ts"
    metin = f.read_text(encoding="utf-8")
    importlar = [s for s in metin.splitlines() if s.lstrip().startswith("import ")]
    assert not [s for s in importlar if "three" in s or "api" in s or "sahne" in s], importlar
    assert "document." not in metin and "window." not in metin and "fetch(" not in metin
