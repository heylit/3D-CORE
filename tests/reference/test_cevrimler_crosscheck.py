"""SPEC 04b K12 — G82 / G84 bağımsız çapraz kontrolü.

Örnek A (punta, G82) ve Örnek B (kılavuz, G84) `cam.gcode.write` ile Fanuc'a yazılır ve `cam.gcode` ile
hiçbir kod paylaşmayan `gcode_ref.RefMachine` (LinuxCNC G82 / G84 tanımı, SPEC 04b ek 9) ile yürütülür;
tezgâhın yapacağı hareketler `to_toolpath()` ile karşılaştırılır. Yorumlayıcının kendi G82 / G84 / G4 /
M29 anlamı, önce elle yazılmış programlarla ayrıca sınanır (yazıcıya bağlı değil).

Kaynak: LinuxCNC G-code referansı (G82, G84, G4); Smid, CNC Programming Handbook, Bölüm 22.
"""

from __future__ import annotations

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL
from cam.gcode import write as _write
from cam.model import MoveType, Toolpath
from tests.cam.cevrimler_ortak import HOLES3, ornek_a, ornek_b, spec30_gerekli
from tests.reference.gcode_ref import RefError, RefMachine, run

TOL = 0.5e-3 + 1e-9  # mm, 3 ondalık yuvarlama
KIND = {MoveType.RAPID: "rapid", MoveType.LINEAR: "feed"}


def write(ops, dialect) -> str:
    spec30_gerekli()
    return _write(ops, dialect)


def assert_trace_equals(trace, tp: Toolpath) -> None:
    """İz hareketleri `tp.moves` ile birebir: tür, başlangıç / bitiş (≤ TOL), kesmede F tam."""
    exp_kinds = [KIND[m.type] for m in tp.moves]
    assert [c.kind for c in trace.moves] == exp_kinds
    p0 = np.array(tp.start, dtype=float)
    for i, (c, m) in enumerate(zip(trace.moves, tp.moves, strict=True)):
        p1 = np.array(m.end, dtype=float)
        assert np.max(np.abs(c.p0 - p0)) <= TOL, (i, c.p0, p0)
        assert np.max(np.abs(c.p1 - p1)) <= TOL, (i, c.p1, p1)
        if m.type is MoveType.LINEAR:
            assert c.feed == m.feed, (i, c.feed, m.feed)
        p0 = p1


def olaylar(trace, kind: str):
    return [e for e in trace.events if e.kind == kind]


# ---------------------------------------------------------------- yorumlayıcının G82 / G84 anlamı (elle)

EL_G82 = """\
G21 G90 G17 G94
T3 M6
S2000 M3
G0 X0 Y0 Z5
G98 G82 X10 Y10 Z-3 R2 P0.5 F200
X30
G80
M5
M30
"""

EL_G84 = """\
G21 G90 G17 G94
T5 M6
S500 M3
G0 X0 Y0 Z5
G99 G84 X10 Y10 Z-15.75 R2 F625
X30
G80
M5
M30
"""


def test_ref_g82_moves_and_dwell():
    """LinuxCNC G82 = G81 + dipte P bekleme: delik başına G0 xy, G0 r, G1 z, G0 z0; iki bekleme olayı."""
    tr = run(EL_G82)
    exp = [
        ("rapid", (10, 10, 5)),
        ("rapid", (10, 10, 2)),
        ("feed", (10, 10, -3)),
        ("rapid", (10, 10, 5)),
        ("rapid", (30, 10, 5)),
        ("rapid", (30, 10, 2)),
        ("feed", (30, 10, -3)),
        ("rapid", (30, 10, 5)),
    ]
    assert [(c.kind, tuple(c.p1)) for c in tr.moves] == exp
    d = olaylar(tr, "dwell")
    assert [e.data["p"] for e in d] == [0.5, 0.5]
    assert [tuple(e.pos) for e in d] == [(10, 10, -3), (30, 10, -3)]


def test_ref_g84_moves_and_spindle_reversal():
    """LinuxCNC G84 (G99): G1 dibe, iş mili ters, G1 R'ye (aynı F), iş mili ileri; G99'da R'de kalır."""
    tr = run(EL_G84)
    exp = [
        ("rapid", (10, 10, 5)),
        ("rapid", (10, 10, 2)),
        ("feed", (10, 10, -15.75)),
        ("feed", (10, 10, 2)),
        ("rapid", (30, 10, 2)),
        ("feed", (30, 10, -15.75)),
        ("feed", (30, 10, 2)),
    ]
    assert [(c.kind, tuple(c.p1)) for c in tr.moves] == exp
    assert all(c.feed == 625 for c in tr.moves if c.kind == "feed")
    assert len(olaylar(tr, "spindle_reverse")) == len(olaylar(tr, "spindle_forward")) == 2


def test_ref_g84_requires_spindle():
    with pytest.raises(RefError, match=r"satır 5\b"):
        run(EL_G84.replace("S500 M3", "S500"))


def test_ref_g84_peck_refused():
    with pytest.raises(RefError, match=r"satır 5\b"):
        run(EL_G84.replace("R2 F625", "R2 Q3 F625"))


def test_ref_g82_requires_p():
    with pytest.raises(RefError, match=r"satır 5\b"):
        run(EL_G82.replace(" P0.5", ""))


def test_ref_g4_and_m29():
    tr = run("G21 G90\nT1 M6\nM29 S500\nS500 M3\nG0 X0 Y0 Z5\nG4 P0.25\nM5\nM30\n")
    assert [e.data["rpm"] for e in olaylar(tr, "rigid_tap")] == [500]
    assert [e.data["p"] for e in olaylar(tr, "dwell")] == [0.25]
    assert tr.moves == []


# ---------------------------------------------------------------- K12: yazıcı çıktısı ↔ to_toolpath()


OPS = [
    pytest.param(lambda: ornek_a(), id="A"),
    pytest.param(lambda: ornek_b(), id="B"),
    pytest.param(lambda: ornek_a("G99", holes=HOLES3), id="A-3-G99"),
    pytest.param(lambda: ornek_b("G99", holes=HOLES3), id="B-3-G99"),
]


def _bitis_geri_cekme(tp: Toolpath, z_safe: float) -> Toolpath:
    """SPEC 04 Ek B: program sonunda güvenli Z'nin altındaysa yazıcı `G0 Z<z_safe>` ekler."""
    from cam.model import Move

    x, y, z = tp.points()[-1]
    if round(z, 3) >= round(z_safe, 3):
        return tp
    return Toolpath(tp.name, tp.tool, tp.start, [*tp.moves, Move(MoveType.RAPID, (x, y, z_safe))], tp.rpm)


@pytest.mark.parametrize("make", OPS)
def test_K12_fanuc_output_on_reference_machine(make):
    """K12: Fanuc çıktısı RefMachine'de yürütülünce iz `to_toolpath()` ile aynı; takım, devir, G43 ve
    iş mili durumu doğru."""
    op = make()
    text = write([op], FANUC)
    tr = RefMachine(tool_change=FANUC.tool_change, peck_clearance=FANUC.peck_clearance).run(text)
    assert_trace_equals(tr, _bitis_geri_cekme(op.to_toolpath(FANUC), op.start[2]))
    for c in tr.moves:
        assert c.tool == op.tool.id
        assert c.rpm == op.rpm
        assert c.tlo == op.tool.id
        assert c.spindle_on


def test_K12_fanuc_spot_dwell_events():
    """K12: Örnek A: her delikte bir bekleme, P500 (Fanuc milisaniye = 0.5 s), dipte."""
    op = ornek_a()
    tr = RefMachine().run(write([op], FANUC))
    d = olaylar(tr, "dwell")
    assert [e.data["p"] for e in d] == [500.0, 500.0]
    assert [tuple(e.pos) for e in d] == [(x, y, op.z) for x, y in op.holes]


def test_K12_fanuc_tap_rigid_mode_before_cycle():
    """K12: Örnek B: `M29 S500` G84'ten önce; iş mili her delikte bir kez ters ve ileri döner."""
    op = ornek_b(holes=HOLES3)
    tr = RefMachine().run(write([op], FANUC))
    rt = olaylar(tr, "rigid_tap")
    assert [e.data["rpm"] for e in rt] == [500.0]
    ilk_kesme = next(c.line for c in tr.moves if c.kind == "feed")
    assert rt[0].line < ilk_kesme
    assert len(olaylar(tr, "spindle_reverse")) == len(olaylar(tr, "spindle_forward")) == 3


def test_K12_grbl_expanded_spot_on_reference_machine():
    """K12 ek: GRBL açılımı (G0/G1 + G4) RefMachine'de aynı iz ve iki bekleme (P0.5 saniye)."""
    op = ornek_a()
    tr = RefMachine(tool_change=GRBL.tool_change, peck_clearance=GRBL.peck_clearance).run(write([op], GRBL))
    assert_trace_equals(tr, op.to_toolpath(GRBL))
    assert [e.data["p"] for e in olaylar(tr, "dwell")] == [0.5, 0.5]
