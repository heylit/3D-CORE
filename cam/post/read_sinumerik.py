"""
Sinumerik doğal dil okuyucusu (SPEC 31): program metni → Toolpath listesi.

Kabul: G0 G1 G2 G3 G17 G40 G54..G57 G71 G90 G94, M0 M3 M5 M6 M30, T, D, S, F, `; yorum`.
`D` takım değişiminden sonra ve ilk hareketten önce gelmeli; `D0` veya `D`'siz hareket → CamError.
`G70` (inç), `G91`, `CR=`, `AC/IC`, çevrimler, değişkenler → CamError. Mesajlarda 'satır <n>'.

Satır, beyaz listeden geçince ISO okuyucusunun (`cam.gcode.reader._Reader`) satırı olarak yürütülür
(`G71` → `G21`); modal durum, yay denetimi ve yol bölme kuralları ISO okuyucusuyla aynıdır.
"""

from __future__ import annotations

import re

from cam.gcode.reader import _Reader
from cam.model import CamError, Tool, Toolpath
from cam.post.format_sinumerik import SINUMERIK

_WORD = re.compile(r"([A-Z])([+-]?(?:\d+\.?\d*|\.\d+))")
G_OK = {0, 1, 2, 3, 17, 40, 54, 55, 56, 57, 71, 90, 94}
M_OK = {0, 3, 5, 6, 30}
LETTERS = set("GMXYZIJFSTD")
G_REFUSED = {
    70: "G70 (inç) desteklenmiyor; birim dönüşümü yapılmaz",
    91: "G91 (artımsal) desteklenmiyor",
    58: "G58 Siemens'te eksen ofsetidir, iş sıfırı değil",
    59: "G59 Siemens'te eksen ofsetidir, iş sıfırı değil",
}


def _parse(raw: str) -> tuple[list[int], list[int], dict[str, float]] | None:
    """Yorumsuz satır → (G, M, kelimeler); boş satırda None. Beyaz liste dışı her şey CamError."""
    s = raw.split(";", 1)[0].strip().upper()
    if not s:
        return None
    if "=" in s or "(" in s or ")" in s:
        raise CamError(f"desteklenmeyen ifade '{s}' (CR=, AC/IC, değişken, çevrim yok)")
    gs: list[int] = []
    ms: list[int] = []
    w: dict[str, float] = {}
    for tok in s.split():
        m = _WORD.fullmatch(tok)
        if m is None or m.group(1) not in LETTERS:
            raise CamError(f"bilinmeyen kelime '{tok}'")
        letter, v = m.group(1), float(m.group(2))
        if letter in "GM":
            if not v.is_integer():
                raise CamError(f"bilinmeyen {letter} kodu '{tok}'")
            code = int(v)
            if letter == "G":
                if code in G_REFUSED:
                    raise CamError(G_REFUSED[code])
                if code not in G_OK:
                    raise CamError(f"bilinmeyen G kodu G{code}")
                gs.append(21 if code == 71 else code)
            else:
                if code not in M_OK:
                    raise CamError(f"bilinmeyen M kodu M{code}")
                ms.append(code)
        elif letter in w:
            raise CamError(f"'{letter}' kelimesi satırda iki kez var")
        else:
            w[letter] = v
    return gs, ms, w


class _SinumerikReader(_Reader):
    """ISO okuyucusu + `D` kuralı: takım değişiminden sonra ilk hareketten önce `D<n>` (n ≥ 1)."""

    def __init__(self, tools: dict[int, Tool], arc_tol: float) -> None:
        super().__init__(tools, SINUMERIK, arc_tol)
        self.d_ok = False

    def line(self, gs: list[int], ms: list[int], w: dict[str, float]) -> None:
        if "T" in w:
            self.d_ok = False
        if "D" in w:
            D = w.pop("D")
            if not D.is_integer() or D < 1:
                raise CamError(f"D{D:g}: takım boyu telafisi kapalı (D ≥ 1 olmalı)")
            if any(k in w for k in "XYZIJ"):
                raise CamError("D aynı satırda hareketle yazılmamalı (takım değişiminden sonra ayrı satır)")
            self.d_ok = True
        if any(k in w for k in "XYZIJ") and not self.d_ok:
            raise CamError("D'siz hareket: takım değişiminden sonra D<n> yok (telafisiz takım boyu)")
        super().line(gs, ms, w)


def read_sinumerik(text: str, tools: dict[int, Tool], arc_tol: float = 0.005) -> list[Toolpath]:
    rd = _SinumerikReader(tools, arc_tol)
    for n, raw in enumerate(text.splitlines(), start=1):
        try:
            parsed = _parse(raw)
            if parsed is not None:
                rd.line(*parsed)
        except CamError as e:
            raise CamError(f"satır {n}: {e}") from None
    return rd.finish()
