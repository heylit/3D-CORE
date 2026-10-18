"""SPEC 38 — İş föyünün HTML çıktısı ve dosyaya yazımı (§8)."""

from __future__ import annotations

from pathlib import Path

from atolye.is_foyu import JobSheet


def render_html(job: JobSheet) -> str:
    """Tek dosyalık, dış kaynaksız, yazdırılabilir HTML; aynı girdi → bayt bayt aynı çıktı."""
    raise NotImplementedError("SPEC 38: render_html")


def write_job_sheet(job: JobSheet, folder: str | Path) -> Path:
    """`folder`'a is-foyu.html ve baglama-<i>.svg yazar; HTML'in yolunu döndürür."""
    raise NotImplementedError("SPEC 38: write_job_sheet")
