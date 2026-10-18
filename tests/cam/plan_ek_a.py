"""SPEC 29 Ek A — uydurma test takımları ve ortak yardımcılar (test_plan*.py için).

Ek A tablosunda olmayan tek ek: GRBL G-code'u (§8) `cam.tool_length.length_offsets` ile ölçü boyu ister;
bu yüzden freze takımlarına ortak bir tutucu (`gauge_length = 60`) ve `stickout = flute_length + 10` verildi.
Torna takımlarının uç numaraları ve açıları SPEC 20 doğrulamasından olduğu gibi geçer (değişiklik yok).
SPEC 22 simülasyonu kesici kenar boyu (`edge_len`) ister; Ek A'da yok. Ek A son paragrafı gereği ISO uç
geometrisine en yakın değerler verildi: T21 CNMG 12.. (kenar 12.9) → 12, T22 DNMG 11.. (11.6) → 11,
T23 3 mm kanal ucu dalma kapasitesi → 8, T24 CCMT 06.. (6.4) → 6. K13 işlemleriyle (alın, kaba, finiş, kanal)
simülasyonda çarpışma yok; kalan / kaldırılan hacim 6–12 arası değerlerde değişmiyor.
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import (
    CuttingData,
    LatheTool,
    LatheToolKind,
    Tool,
    ToolHolder,
    ToolKind,
    ToolLibrary,
    Toolpath,
)
from cam.profile import Arc, Line, Profile

MALZEME = "al"
TUTUCU = ToolHolder("tutucu-ek-a", gauge_length=60.0, profile=((0.0, 20.0), (40.0, 20.0)))


def _freze(id: int, ad: str, kind: ToolKind, D: float, L: float, z: int, **cd) -> Tool:
    return Tool(
        id=id,
        name=ad,
        kind=kind,
        D=D,
        flute_length=L,
        flutes=z,
        stickout=L + 10.0,
        holder=TUTUCU,
        cutting={MALZEME: CuttingData(**cd)},
    )


def freze_takimlari(ae1: float = 6.0) -> list[Tool]:
    """Ek A freze + matkap takımları. `ae1`: T1'in ae'si (K7 için değiştirilebilir)."""
    F, M = ToolKind.FLAT, ToolKind.DRILL
    return [
        _freze(1, "freze16", F, 16, 30, 3, Vc=300, fz=0.08, ap=4, ae=ae1),
        _freze(2, "freze10", F, 10, 25, 3, Vc=250, fz=0.05, ap=3, ae=4),
        _freze(3, "freze6", F, 6, 18, 3, Vc=200, fz=0.04, ap=2, ae=2.5),
        _freze(4, "freze4", F, 4, 12, 2, Vc=150, fz=0.03, ap=1, ae=1.5),
        _freze(5, "freze3-veri-yok", F, 3, 8, 2, Vc=120, fz=0.02),
        _freze(11, "matkap8", M, 8, 40, 2, Vc=80, fz=0.1),
        _freze(12, "matkap6.6", M, 6.6, 35, 2, Vc=80, fz=0.08),
        _freze(13, "matkap6.8", M, 6.8, 35, 2, Vc=80, fz=0.08),
        _freze(14, "matkap4", M, 4, 25, 2, Vc=70, fz=0.05),
    ]


def freze_lib(ae1: float = 6.0) -> ToolLibrary:
    return ToolLibrary(freze_takimlari(ae1))


def torna_lib() -> ToolLibrary:
    def cd(**k):
        return {MALZEME: CuttingData(**k)}

    K = LatheToolKind
    return ToolLibrary(
        [
            LatheTool(
                21, "dis-kaba", K.TURN, 0.8, 3, 93, 80, cutting=cd(Vc=250, fn=0.25, ap=2), edge_len=12.0
            ),
            LatheTool(22, "dis-finis", K.TURN, 0.4, 3, 93, 55, cutting=cd(Vc=300, fn=0.1), edge_len=11.0),
            LatheTool(
                23, "kanal3", K.GROOVE, 0.2, 3, 90, 90, width=3, cutting=cd(Vc=150, fn=0.05), edge_len=8.0
            ),
            LatheTool(24, "ic-kaba", K.BORE, 0.4, 2, 95, 80, cutting=cd(Vc=200, fn=0.15, ap=1), edge_len=6.0),
        ]
    )


# ---------------------------------------------------------------- geometri


def yuvarlak_dikdortgen(cx: float, cy: float, w: float, l: float, r: float) -> Profile:  # noqa: E741
    """Merkezi (cx, cy), w × l, köşe yarıçapı r > 0 olan CCW halka."""
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - l / 2, cy + l / 2
    return Profile(
        [
            Line((x0 + r, y0), (x1 - r, y0)),
            Arc((x1 - r, y0), (x1, y0 + r), (x1 - r, y0 + r), True),
            Line((x1, y0 + r), (x1, y1 - r)),
            Arc((x1, y1 - r), (x1 - r, y1), (x1 - r, y1 - r), True),
            Line((x1 - r, y1), (x0 + r, y1)),
            Arc((x0 + r, y1), (x0, y1 - r), (x0 + r, y1 - r), True),
            Line((x0, y1 - r), (x0, y0 + r)),
            Arc((x0, y0 + r), (x0 + r, y0), (x0 + r, y0 + r), True),
        ],
        True,
    )


def dikdortgen(cx: float, cy: float, w: float, l: float) -> Profile:  # noqa: E741
    return Profile.rectangle(cx - w / 2, cy - l / 2, w, l)


def cizgi(*noktalar) -> Profile:
    """Açık çokgen profil (torna yarı kesiti, (u, v) = (z, x))."""
    return Profile.polygon(noktalar, closed=False)


def kose_artigi(r: float, n_kose: int, H: float, R_c: float = 0.0, phi: float = math.pi / 2) -> float:
    """§3: n köşede V = n·(r² − R_c²)·(tan(φ/2) − φ/2)·H."""
    return n_kose * (r * r - R_c * R_c) * (math.tan(phi / 2) - phi / 2) * H


# ---------------------------------------------------------------- karşılaştırma


def yol(tp: Toolpath) -> dict:
    """Takım yolunun adı dışındaki her şeyi (adı plan verir)."""
    d = tp.to_dict()
    d.pop("name")
    return d


def kesme_hareketleri(tp: Toolpath) -> list:
    """G1/G2/G3 hareketleri (hızlı hareketler yaklaşma stoğuna bağlıdır)."""
    return [m for m in tp.to_dict()["moves"] if m["type"] != "G0"]


def yakin(a, b, tol: float = 1e-9) -> bool:
    return bool(np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float), rtol=tol, atol=tol))
