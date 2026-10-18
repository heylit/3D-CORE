"""
Heidenhain TNC 640 / 620 / 530 Klartext biçimleyicisi (SPEC 31).

`plan()`'ın bloklarını biçimler; karar vermez.
- Blok numarası 0'dan ardışık; `0 BEGIN PGM <ad> MM` … `<n> END PGM <ad> MM`.
- `L X+10 Y-2.5 R0 F300`: işaretli sayı, sondaki sıfırlar atılır; her `L`'de `R0`; yalnız değişen eksenler.
- `FMAX` yalnız o blokta geçerli; kesme `F`'si modaldır (FMAX'tan sonra tekrar yazılmaz).
- Yay: `CC X Y` (her yayda) sonra `C X Y DR± R0 F`; helis `CP IPA±<derece, 4 ondalık> IZ±<dz> DR± R0 F`.
- Takım `TOOL CALL n Z S<rpm>`; `M3` ilk hareket bloğunda, `M5` geri çekme bloğunda.
- İş sıfırı: `presets` eşlemesiyle `CYCL DEF 247 DATUM SETTING ~ Q339=+<n>`; eşleme yoksa CamError.
- Makine Z'si (`tool_change_z`): `L Z+<v> R0 FMAX M91`. Program sonu `L Z+<safe_z> R0 FMAX M30`.
Delik op'ları kanonik açılımla. Kaynak: HEIDENHAIN TNC 640 Klartext User's Manual (ID 892903).
"""

from __future__ import annotations

from cam.gcode.dialect import Dialect
from cam.post.blocks import Block

__all__ = ["HEIDENHAIN", "format_heidenhain"]

HEIDENHAIN = Dialect(
    name="Heidenhain",
    decimals=3,
    feed_decimals=1,
    line_numbers=False,
    line_step=1,
    header=(),
    footer=(),
    tool_change="M6",
    canned_cycles=False,
    peck_clearance=0.5,
)

IPA_DECIMALS = 4  # helis açısı ondalığı (derece)


def format_heidenhain(
    blocks: list[Block], presets: dict[str, int], dialect: Dialect = HEIDENHAIN, program_name: str = "1"
) -> str:
    """Blok listesi → Klartext program metni ('\\n' ile biten). `presets`: G54..G59 → ön ayar numarası."""
    raise NotImplementedError("SPEC 31: format_heidenhain")
