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


# ------------------------------------------------------------------ SPEC 63 K9

DNC_IZINLI = {"cam.model", "cam.post", "atolye.dogrulama"}


def _dnc_ihlalleri(yol: Path) -> list[str]:
    """dnc.py yalnız stdlib, cam.model, cam.post (dışa açılan adlar) ve atolye.dogrulama içe aktarır."""
    import sys

    import cam.post

    agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
    out = []
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] not in sys.stdlib_module_names and a.name not in DNC_IZINLI:
                    out.append(a.name)
        elif isinstance(n, ast.ImportFrom):
            if n.level != 0 or n.module is None:
                out.append("." * n.level + (n.module or ""))
            elif n.module == "cam.post":
                out += [
                    f"cam.post.{a.name}"
                    for a in n.names
                    if a.name.startswith("_") or not hasattr(cam.post, a.name)
                ]
            elif n.module.split(".")[0] not in sys.stdlib_module_names and n.module not in DNC_IZINLI:
                out.append(n.module)
    return out


def test_dnc_bagimliliklari():
    assert _dnc_ihlalleri(KOK / "atolye" / "dnc.py") == []


def test_dnc_tarayici_yakalar(tmp_path):
    p = tmp_path / "x.py"
    p.write_text(
        "from __future__ import annotations\nimport json, os\nfrom pathlib import Path\n"
        "from cam.model import MachineProfile\nfrom cam.post import post, read_program, _gizli\n"
        "from cam.post.check import check_machine\nimport numpy\nfrom geometry.part import Part\n"
        "from atolye.dogrulama import profil_ozeti\nfrom atolye.is_foyu import JobSheet\nfrom . import x\n"
    )
    assert sorted(_dnc_ihlalleri(p)) == sorted(
        ["cam.post._gizli", "cam.post.check", "numpy", "geometry.part", "atolye.is_foyu", "."]
    )
