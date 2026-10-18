"""SPEC 30 — gidiş-dönüş `read_program(post(...))` üç dilin örnek profilleriyle (K14).

SPEC 04 K4'ün rastgele yolları (sabit tohum, `safe_z` verilerek) kullanılır; yol, profilin
kurslarına sığsın diye iş sıfırı yolun sınır kutusunu kursların ortasına koyacak biçimde seçilir,
takıma ölçü boyu verilir ve devir profilin aralığına çekilir. Toleranslar SPEC 04 K4 ile aynı:
uç ≤ 0.5·10⁻³ mm (koordinat başına), merkez ≤ 1e-2 mm.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from cam.post import builtin_machines, post, read_program
from tests.cam.post_ortak import ortala, takim
from tests.cam.test_gcode_roundtrip import SEED, as_written, assert_paths_close, random_path, safe_z_of

ADLAR = ["ORNEK-GRBL-ROUTER", "ORNEK-FANUC-DIK", "ORNEK-HAAS-DIK"]
L = 100.0  # mm, takım ölçü boyu
RPM = 6000.0  # üç profilin de devir aralığında


@pytest.mark.parametrize("seed", [SEED, 1, 3])
@pytest.mark.parametrize("ad", ADLAR)
def test_K14_random_roundtrip(ad, seed):
    """K14: hareket tipleri aynı, uçlar ≤ 0.5e-3 mm, merkez ≤ 1e-2 mm; takım ve devir aynı."""
    m = builtin_machines()[ad]
    tp0, _ = random_path(seed)
    tp = replace(tp0, tool=takim(1, L=L), rpm=RPM)
    z_s = safe_z_of(tp)
    setup = ortala(m, [tp], L, z_ek=z_s)
    got = read_program(post([tp], m, setup, safe_z=z_s), m, {1: tp.tool})
    assert len(got) == 1
    g = got[0]
    g.validate()
    assert g.tool == tp.tool
    assert g.rpm == RPM
    assert_paths_close(g, as_written(tp, z_s))
