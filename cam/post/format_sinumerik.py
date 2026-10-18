"""
Siemens Sinumerik 840D sl / 828D doğal dil biçimleyicisi (SPEC 31).

`plan()`'ın bloklarını biçimler; karar vermez. Farklar (Fanuc'a göre): `G71` metrik, noktasız sayı
(`10`, `-2.5`), `; yorum`, `T<n> M6` sonra ayrı satırda `D1` (G43 yok; D takımın kesici ağzıdır, Siemens
varsayılanı; "flat D number" (MD18102) açık tezgâhlarda D = T gerekir, desteklenmiyor), satır numarası yok,
`%` / `O` yok. Yorumlar başlık satırından önce yazılır.
İş sıfırı `G54..G57`; `G58` / `G59` Siemens'te eksen ofsetidir → CamError.
Delik op'ları kanonik açılımla (canned_cycles = False). Kaynak: SINUMERIK 840D sl / 828D Fundamentals
Programming Manual (6FC5398-1BP40).
"""

from __future__ import annotations

from cam.gcode.dialect import Dialect
from cam.gcode.modal import fmt
from cam.model import CamError
from cam.post.blocks import (
    Block,
    Comment,
    Cycle,
    CycleEnd,
    Dwell,
    MachineZ,
    RigidTap,
    Start,
    ToolChange,
    ToolLength,
)
from cam.post.format_iso import _Formatter

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


def sayi(v: float, decimals: int) -> str:
    """Noktasız sayı: 10 → '10', -2.5 → '-2.5', 0 → '0' (fmt'nin sondaki noktası atılır)."""
    return fmt(v, decimals).rstrip(".")


class _SinumerikFormatter(_Formatter):
    """ISO biçimleyicisinin G kelimesi ve eksen kuralları; sayı, yorum, takım ve iş sıfırı Siemens'e göre."""

    def c(self, v: float) -> str:
        return sayi(v, self.d.decimals)

    def feed(self, F: float | None) -> list[str]:
        return [] if F is None else [f"F{sayi(F, self.d.feed_decimals)}"]

    baslik: Start | None = None  # başlık satırı yorumlardan sonra yazılır (dosya başı yorumla açılır)

    def block(self, b: Block) -> None:
        if isinstance(b, Start):
            if b.wcs not in WCS_SINUMERIK:
                raise CamError(
                    f"Sinumerik: iş sıfırı {b.wcs} yazılamaz; G58 / G59 Siemens'te eksen ofsetidir "
                    f"(iş sıfırı {', '.join(WCS_SINUMERIK)})"
                )
            self.baslik = b
            return
        if isinstance(b, Comment):
            self.emit([f"; {b.text}"])
            return
        if self.baslik is not None:
            self.start(self.baslik)
            self.baslik = None
        if isinstance(b, ToolChange):
            self.emit([f"T{b.tool}", self.d.tool_change])
            self.emit(["D1"])  # takımın 1. kesici ağzı: boy ve yarıçap ofseti (G43 yok)
        elif isinstance(b, MachineZ):
            raise CamError(
                "Sinumerik: makine koordinatında takım değişim Z'si (tool_change_z) SPEC 31'de tanımlı değil"
            )
        elif isinstance(b, (ToolLength, Cycle, CycleEnd, RigidTap, Dwell)):
            raise CamError(f"Sinumerik: {type(b).__name__} bloğu yazılamaz (SPEC 31: kanonik açılım)")
        else:
            super().block(b)


def format_sinumerik(blocks: list[Block], dialect: Dialect = SINUMERIK) -> str:
    """Blok listesi → Sinumerik program metni ('\\n' ile biten)."""
    f = _SinumerikFormatter(dialect)
    for b in blocks:
        f.block(b)
    return "\n".join(f.lines) + "\n"
