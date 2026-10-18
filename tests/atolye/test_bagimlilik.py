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
