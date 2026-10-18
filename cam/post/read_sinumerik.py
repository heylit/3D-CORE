"""
Sinumerik doğal dil okuyucusu (SPEC 31): program metni → Toolpath listesi.

Kabul: G0 G1 G2 G3 G17 G40 G54..G57 G71 G90 G94, M0 M3 M5 M6 M30, T, D, S, F, `; yorum`.
`D` takım değişiminden sonra ve ilk hareketten önce gelmeli; `D0` veya `D`'siz hareket → CamError.
`G70` (inç), `G91`, `CR=`, `AC/IC`, çevrimler, değişkenler → CamError. Mesajlarda 'satır <n>'.
"""

from __future__ import annotations

from cam.model import Tool, Toolpath


def read_sinumerik(text: str, tools: dict[int, Tool], arc_tol: float = 0.005) -> list[Toolpath]:
    raise NotImplementedError("SPEC 31: read_sinumerik")
