"""SPEC 64 K10 — `docs/mes-baglantisi.md` uç listesi `docs/mes-openapi-v1.json`'daki yollarla aynı küme.

Metin taraması: belgede geçen `/api/mes/v1/...` yolları (sorgu dizgisi ve sondaki noktalama atılır) ile anlık
görüntünün `paths` anahtarları karşılaştırılır.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[3]
BELGE = KOK / "docs" / "mes-baglantisi.md"
ANLIK = KOK / "docs" / "mes-openapi-v1.json"
_YOL = re.compile(r"/api/mes/v1/[A-Za-z0-9_\-./{}]*")


def _oku(p: Path) -> str:
    if not p.is_file():
        raise NotImplementedError(f"SPEC 64: {p.relative_to(KOK)} henüz yok")
    return p.read_text(encoding="utf-8")


def belge_yollari(metin: str) -> set[str]:
    return {m.group(0).rstrip(".,;:)") for m in _YOL.finditer(metin)}


def test_tarayici():
    m = "GET `/api/mes/v1/is-emirleri?sonra=3` ve /api/mes/v1/is-emirleri/{mes_id}/is-foyu.html."
    assert belge_yollari(m) == {"/api/mes/v1/is-emirleri", "/api/mes/v1/is-emirleri/{mes_id}/is-foyu.html"}


def test_belge_yollari():
    anlik = json.loads(_oku(ANLIK))
    yollar = {p for p in anlik["paths"] if p.startswith("/api/mes/v1/")}
    assert yollar
    metin = _oku(BELGE)
    assert belge_yollari(metin) == yollar
    assert "openapi-typescript" in metin  # MES tarafı tip üretimi
