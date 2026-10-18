"""SPEC 38 K11 — bağımlılık kuralı: hiçbir paket `atolye`'yi import etmez (AST taraması)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
PAKETLER = ("core", "cam", "geometry", "assy", "sketch", "mesh", "fileio", "viz")


def _atolye_importlari(yol: Path) -> list[str]:
    agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
    out = []
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names if a.name == "atolye" or a.name.startswith("atolye.")]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            if n.module == "atolye" or n.module.startswith("atolye."):
                out.append(n.module)
    return out


@pytest.mark.parametrize("paket", PAKETLER)
def test_paket_atolyeyi_import_etmez(paket):
    klasor = KOK / paket
    if not klasor.is_dir():
        pytest.skip(f"{paket}/ yok")
    ihlal = {str(p.relative_to(KOK)): m for p in sorted(klasor.rglob("*.py")) if (m := _atolye_importlari(p))}
    assert ihlal == {}


def test_tarayici_yakalar(tmp_path):
    """Tarayıcının kendisi: import biçimlerinin hepsini görür."""
    p = tmp_path / "x.py"
    p.write_text("import atolye\nfrom atolye.html import render_html\nimport atolyex\nfrom . import atolye\n")
    assert _atolye_importlari(p) == ["atolye", "atolye.html"]


def test_atolye_paketi_var():
    assert (KOK / "atolye" / "__init__.py").is_file()


# ---------------------------------------------------------------- SPEC 58 K11

SPEC58_DOSYALAR = ("atolye/maliyet.py", "atolye/teklif.py")
SPEC58_IZINLI = ("cam.model", "malzeme.model", "malzeme.kutuphane", "atolye.is_foyu")
# Varsayım: teklif.py kendi SPEC'inin `atolye.maliyet` modülünü (Maliyet, Kalem) okuyabilir;
# Ek 4'ün isteğe bağlı SPEC 72 / 59 türleri (`cam.sim.cevrim`, `cam.omur`) de izinlidir.
SPEC58_EK_IZINLI = ("atolye.maliyet", "cam.sim.cevrim", "cam.omur")


def _ice_aktarilanlar(yol: Path) -> list[str]:
    agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
    out = []
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                out.append("." * n.level + (n.module or ""))
            elif n.module:
                out.append(n.module)
    return out


def _izinli(modul: str) -> bool:
    import sys

    if modul == "__future__" or modul.split(".")[0] in sys.stdlib_module_names:
        return True
    return modul in SPEC58_IZINLI or modul in SPEC58_EK_IZINLI


@pytest.mark.parametrize("dosya", SPEC58_DOSYALAR)
def test_spec58_maliyet_teklif_bagimliligi(dosya):
    yol = KOK / dosya
    assert yol.is_file()
    ihlal = [m for m in _ice_aktarilanlar(yol) if not _izinli(m)]
    assert ihlal == []


def test_spec58_tarayici_yakalar(tmp_path):
    p = tmp_path / "x.py"
    p.write_text(
        "import json\nfrom cam.model import Stock\nfrom malzeme.baglanti import x\n"
        "import numpy\nfrom . import y\n"
    )
    assert [m for m in _ice_aktarilanlar(p) if not _izinli(m)] == ["malzeme.baglanti", "numpy", "."]
