"""SPEC 46 H9 — mil torna programı (SPEC 21): Fanuc torna yazımı ve okuma gidiş-dönüşü. K9.

Okunan hareketler, yazılan ondalık basamak hassasiyetinde (`10⁻³` mm; X çap yazıldığından yarıçapta
yarısı) modelle aynı olmalı.
"""

from __future__ import annotations

import numpy as np

from cam.model import MoveType
from tests.uctan_uca.conftest import halka

lathe = halka("21", "cam.gcode.lathe", "write_lathe", "read_lathe")

TC = (50.0, 100.0)  # takım değiştirme noktası (x yarıçap, z), çubuğun önünde ve dışında
TOL = 1e-3
KESME = {MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW}


def kesmeler(ops):
    return [(m.type, np.asarray(m.end, dtype=float)) for tp in ops for m in tp.moves if m.type in KESME]


def test_k9_yaz_oku_ayni_hareketler(torna_ops, kutuphane):
    metin = lathe.write_lathe(torna_ops, "M3", TC)
    tools = {t.id: t for t in kutuphane.tools if t.id == 11}
    okunan = lathe.read_lathe(metin, tools, spindle="M3")
    assert all(tp.tool.id == 11 for tp in okunan)
    a, b = kesmeler(okunan), kesmeler(torna_ops)
    assert [t for t, _ in a] == [t for t, _ in b]
    sapma = max(float(np.abs(p - q).max()) for (_, p), (_, q) in zip(a, b, strict=True))
    assert sapma <= TOL
