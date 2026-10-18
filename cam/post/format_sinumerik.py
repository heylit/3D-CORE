"""
Siemens Sinumerik 840D sl / 828D doğal dil biçimleyicisi (SPEC 31).

`plan()`'ın bloklarını biçimler; karar vermez. Farklar (Fanuc'a göre): `G71` metrik, noktasız sayı
(`10`, `-2.5`), `; yorum`, `T1 M6` sonra ayrı satırda `D1` (G43 yok), satır numarası yok, `%` / `O` yok.
İş sıfırı `G54..G57`; `G58` / `G59` Siemens'te eksen ofsetidir → CamError.
Delik op'ları kanonik açılımla (canned_cycles = False). Kaynak: SINUMERIK 840D sl / 828D Fundamentals
Programming Manual (6FC5398-1BP40).
"""

from __future__ import annotations

from cam.gcode.dialect import Dialect
from cam.post.blocks import Block

__all__ = ["SINUMERIK", "format_sinumerik"]

SINUMERIK = Dialect(
    name="Sinumerik",
    decimals=3,
    feed_decimals=1,
    line_numbers=False,
    line_step=10,
    header=("G71 G90 G17 G94 G40 G54",),
    footer=("M5", "M30"),
    tool_change="M6",
    canned_cycles=False,
    peck_clearance=0.5,
)

WCS_SINUMERIK = ("G54", "G55", "G56", "G57")


def format_sinumerik(blocks: list[Block], dialect: Dialect = SINUMERIK) -> str:
    """Blok listesi → Sinumerik program metni ('\\n' ile biten)."""
    raise NotImplementedError("SPEC 31: format_sinumerik")
