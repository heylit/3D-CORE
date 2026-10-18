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


# ---------------------------------------------------------------- SPEC 48 K10

DOGRULAMA_IZINLI = ("cam.model", "cam.post", "atolye.is_foyu")


def _ust_importlar(yol: Path) -> list[str]:
    """Modülün mutlak import adları (göreli import '.'-önekli)."""
    agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
    out = []
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            out.append("." * n.level + (n.module or ""))
    return out


def _izinli(ad: str) -> bool:
    import sys

    if ad == "__future__" or ad.split(".")[0] in sys.stdlib_module_names:
        return True
    return any(ad == p or ad.startswith(p + ".") for p in DOGRULAMA_IZINLI)


def test_dogrulama_yalniz_izinli_importlar():
    """SPEC 48 K10: atolye/dogrulama.py yalnız stdlib, cam.model, cam.post ve atolye.is_foyu."""
    yol = KOK / "atolye" / "dogrulama.py"
    assert yol.is_file()
    ihlal = [a for a in _ust_importlar(yol) if not _izinli(a)]
    assert ihlal == []


def test_dogrulama_tarayicisi():
    assert _izinli("json") and _izinli("hashlib") and _izinli("html.parser") and _izinli("__future__")
    assert (
        _izinli("cam.model")
        and _izinli("cam.post")
        and _izinli("cam.post.machine")
        and _izinli("atolye.is_foyu")
    )
    for ad in ("numpy", "cam.gcode", "cam.sim", "atolye.html", "atolye", "geometry", ".is_foyu", "tezgah"):
        assert not _izinli(ad), ad
