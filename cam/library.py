"""
Takım kütüphanesi dosyası ve işlemleri. SPEC 14.

Dosya UTF-8 JSON: `ToolLibrary.to_dict()`, takımlar id sırasıyla, girintili; aynı kütüphane her
kayıtta aynı baytı verir.
"""

from __future__ import annotations

import json
from pathlib import Path

from cam.model import CamError, LatheTool, Tool, ToolLibrary, Toolpath


def load_library(path: str | Path) -> ToolLibrary:
    """JSON dosyasından kütüphane; dosya yok, bozuk JSON veya geçersiz takım → CamError."""
    path = Path(path)
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise CamError(f"Takım kütüphanesi '{path}' okunamadı: {e}") from None
    except json.JSONDecodeError as e:
        raise CamError(f"Takım kütüphanesi '{path}': bozuk JSON ({e})") from None
    try:
        return ToolLibrary.from_dict(d)
    except (CamError, TypeError, AttributeError, KeyError, ValueError) as e:
        raise CamError(f"Takım kütüphanesi '{path}': {e}") from None


def save_library(lib: ToolLibrary, path: str | Path) -> None:
    """Kütüphaneyi doğrulayıp JSON olarak yazar (takımlar id sırasıyla)."""
    lib.validate()
    d = ToolLibrary(sorted(lib.tools, key=lambda t: t.id)).to_dict()
    Path(path).write_text(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )  # Windows'ta da LF: dosya biçimi platformdan bağımsız


def find_tools(
    lib: ToolLibrary, kind=None, D: float | None = None, material: str | None = None
) -> list[Tool | LatheTool]:
    """Türe, çapa (freze) ve kesme verisi olan malzemeye göre takımlar, id sırasıyla."""
    out = []
    for t in lib.tools:
        if kind is not None and t.kind != kind:
            continue
        if D is not None and not (isinstance(t, Tool) and abs(t.D - D) <= 1e-9):
            continue
        if material is not None and material not in t.cutting:
            continue
        out.append(t)
    return sorted(out, key=lambda t: t.id)


def remove_tool(lib: ToolLibrary, id: int) -> None:
    """Takımı kütüphaneden çıkarır; yoksa CamError."""
    lib.tools.remove(lib.get(id))


def materials(lib: ToolLibrary) -> list[str]:
    """Kütüphanede kesme verisi olan malzemeler, sıralı."""
    return sorted({m for t in lib.tools for m in t.cutting})


def check_tools(lib: ToolLibrary, ops: list[Toolpath]) -> None:
    """Her op'un takımı kütüphanede aynı id ve aynı tanımla olmalı; aksi CamError."""
    for op in ops:
        n = op.tool.id
        if not any(t.id == n for t in lib.tools):
            raise CamError(f"Op '{op.name}': T{n} '{op.tool.name}' kütüphanede yok")
        t = lib.get(n)
        if t.to_dict() != op.tool.to_dict():
            raise CamError(f"Op '{op.name}': T{n} '{op.tool.name}' kütüphanedekiyle aynı değil")
