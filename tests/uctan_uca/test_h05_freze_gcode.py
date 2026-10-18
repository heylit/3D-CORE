"""SPEC 46 H5 — flanş G-code'u (SPEC 04) ve bağımsız yorumlayıcılar (`tests/reference`). K5.

Yazılan program `gcode_ref` (LinuxCNC anlamı, `cam.gcode`'dan bağımsız) ile yürütülür; hareketler CAM
modeliyle aynı, güvenlik denetimleri temiz olmalı. `rs274` kuruluysa aynı karşılaştırma onunla da yapılır.
"""

from __future__ import annotations

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL, read, write
from cam.sim import simulate
from tests.reference.gcode_check import compare, expected, safety
from tests.reference.gcode_ref import RefMachine
from tests.reference.test_gcode_crosscheck import RS274, rs274_moves
from tests.uctan_uca.conftest import STOK_UST

DIALECTS = [pytest.param(GRBL, id="GRBL"), pytest.param(FANUC, id="Fanuc")]
CELL = 0.5


def program(ops, d, setup) -> str:
    return write(ops, d, setup=setup)


@pytest.mark.parametrize("d", DIALECTS)
def test_k5_bagimsiz_yorumlayici_modelle_ayni(d, freze_ops, flans_setup):
    tr = RefMachine(tool_change=d.tool_change, peck_clearance=d.peck_clearance).run(
        program(freze_ops, d, flans_setup)
    )
    errs = compare(expected(freze_ops, d.peck_clearance), tr.moves)
    assert not errs, "\n".join(errs[:20])
    ihlal = safety(tr, STOK_UST, require_tlo=d is FANUC, require_wcs=d is FANUC)
    assert not ihlal, "\n".join(m for _, m in ihlal[:20])


def test_k5_lehceler_ayni_yolu_keser(freze_ops, flans_setup):
    g = RefMachine(tool_change=GRBL.tool_change, peck_clearance=GRBL.peck_clearance).run(
        program(freze_ops, GRBL, flans_setup)
    )
    f = RefMachine(tool_change=FANUC.tool_change, peck_clearance=FANUC.peck_clearance).run(
        program(freze_ops, FANUC, flans_setup)
    )
    errs = compare(g.moves, f.moves)
    assert not errs, "\n".join(errs[:20])


@pytest.mark.occt
@pytest.mark.parametrize("d", DIALECTS)
def test_k5_okunan_program_ayni_talasi_kaldirir(d, freze_ops, flans_setup, flans_stok, kutuphane):
    tools = {t.id: t for t in kutuphane.tools}
    okunan = read(program(freze_ops, d, flans_setup), tools, d)
    dogrudan = simulate(freze_ops, flans_stok, cell=CELL)
    yeniden = simulate(okunan, flans_stok, cell=CELL)
    tol = 10.0 ** (-d.decimals)
    assert np.abs(yeniden.zmap.z - dogrudan.zmap.z).max() <= tol


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 kurulu değil")
@pytest.mark.parametrize("d", DIALECTS)
def test_k5_linuxcnc_rs274_modelle_ayni(d, freze_ops, flans_setup, tmp_path):
    moves = rs274_moves(program(freze_ops, d, flans_setup), tmp_path)
    errs = compare(expected(freze_ops, d.peck_clearance), moves)
    errs = [e for e in errs if "takım" not in e and "devir" not in e]  # bağdaştırıcı takım/devir izlemiyor
    assert not errs, "\n".join(errs[:20])
