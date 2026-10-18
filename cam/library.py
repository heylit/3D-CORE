"""
Takım kütüphanesi dosyası ve işlemleri. SPEC 14.

Dosya UTF-8 JSON: `ToolLibrary.to_dict()`, takımlar id sırasıyla, girintili; aynı kütüphane her
kayıtta aynı baytı verir.
"""

from __future__ import annotations

from pathlib import Path

from cam.model import LatheTool, Tool, ToolLibrary, Toolpath


def load_library(path: str | Path) -> ToolLibrary:
    """JSON dosyasından kütüphane; dosya yok, bozuk JSON veya geçersiz takım → CamError."""
    raise NotImplementedError


def save_library(lib: ToolLibrary, path: str | Path) -> None:
    """Kütüphaneyi doğrulayıp JSON olarak yazar."""
    raise NotImplementedError


def find_tools(
    lib: ToolLibrary, kind=None, D: float | None = None, material: str | None = None
) -> list[Tool | LatheTool]:
    """Türe, çapa (freze) ve kesme verisi olan malzemeye göre takımlar, id sırasıyla."""
    raise NotImplementedError


def remove_tool(lib: ToolLibrary, id: int) -> None:
    """Takımı kütüphaneden çıkarır; yoksa CamError."""
    raise NotImplementedError


def materials(lib: ToolLibrary) -> list[str]:
    """Kütüphanede kesme verisi olan malzemeler, sıralı."""
    raise NotImplementedError


def check_tools(lib: ToolLibrary, ops: list[Toolpath]) -> None:
    """Her op'un takımı kütüphanede aynı id ve aynı tanımla olmalı; aksi CamError."""
    raise NotImplementedError
