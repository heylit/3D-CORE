"""
Heidenhain Klartext okuyucusu (SPEC 31): program metni → Toolpath listesi.

Kabul: BEGIN PGM, END PGM, TOOL CALL n Z S, L, CC, C, CP IPA IZ, FMAX, F, R0, DR±, M3 M5 M30 M91,
CYCL DEF 247 … Q339, `; yorum`. Blok numaraları 0'dan ardışık (değilse CamError). FMAX bloğu modal
F'yi değiştirmez. RL/RR, IX gibi artımsal koordinat, LP, CT, RND, CHF, diğer çevrimler, FN / Q
parametreleri, END PGM'siz program → CamError. Mesajlarda 'satır <n>'.
"""

from __future__ import annotations

from cam.model import Tool, Toolpath


def read_heidenhain(text: str, tools: dict[int, Tool], arc_tol: float = 0.005) -> list[Toolpath]:
    raise NotImplementedError("SPEC 31: read_heidenhain")
