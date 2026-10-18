"""SPEC 30 — postprosesör çıktısının bağımsız çapraz kontrolü (K15).

Üç dilin (GRBL, Fanuc, Haas) örnek profilleriyle `post` çıktısı, `cam.gcode` ile kod paylaşmayan
`gcode_ref.RefMachine` ile yürütülür: kesme hareketleri modelle aynı (`compare`) ve tezgâh güvenliği
ihlali yok (`safety`). LinuxCNC `rs274` PATH'te varsa aynı karşılaştırma onunla da yapılır.

Not: `RefMachine` makine koordinatını (`G53`) modellemez. Bu yüzden profillerin `tool_change_z = None`
kopyası kullanılır; G53 satırlarının çıktıya tek fark olarak eklendiği `tests/cam/test_post_iso.py`
(K11) içinde ayrıca sınanır. `@pytest.mark.rs274` işareti pyproject'te kayıtlı olmadığından (ortak
dosya) yalnız `skipif` kullanıldı.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from cam.post import builtin_machines, dialect_for, post
from tests.cam.post_ortak import ortala, sinirla, takim
from tests.reference.gcode_check import compare, expected, safety
from tests.reference.gcode_ref import RefMachine
from tests.reference.test_gcode_crosscheck import RS274, STOCK_TOP, _random_job, retracted_job, rs274_moves

ADLAR = ["ORNEK-GRBL-ROUTER", "ORNEK-FANUC-DIK", "ORNEK-HAAS-DIK"]
L = 100.0  # mm, bütün takımların ölçü boyu


def profil(ad: str):
    return replace(builtin_machines()[ad], tool_change_z=None)


def hazirla(ops, m):
    """Takımlara ölçü boyu ver (aynı id, aynı ad, aynı çap), devri profilin aralığına çek."""
    out = []
    for op in ops:
        t = op.tool
        op = replace(op, tool=replace(takim(t.id, L=L, D=t.D, name=t.name), kind=t.kind))
        out.append(sinirla(op, m))
    return out


IS = {
    "kontur-cep-delik": lambda: retracted_job(),
    "rastgele3": lambda: _random_job(3),
    "rastgele20261018": lambda: _random_job(20261018),
}


@pytest.mark.parametrize("is_ad", list(IS))
@pytest.mark.parametrize("ad", ADLAR)
def test_K15_ref_machine_agrees(ad, is_ad):
    """K15: `compare(expected(ops), trace)` boş ve `safety(...)` boş."""
    m = profil(ad)
    d = dialect_for(m)
    ops = hazirla(IS[is_ad](), m)
    setup = ortala(m, ops, L, z_ek=10.0)
    text = post(ops, m, setup)
    tr = RefMachine(tool_change=d.tool_change, peck_clearance=d.peck_clearance).run(text)
    errs = compare(expected(ops, d.peck_clearance), tr.moves)
    assert not errs, "\n".join(errs[:20])
    fanuc_ailesi = m.controller in ("fanuc", "haas")
    errs = safety(tr, STOCK_TOP, require_tlo=fanuc_ailesi, require_wcs=fanuc_ailesi)
    assert not errs, "\n".join(f"{k}: {msg}" for k, msg in errs[:20])


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 kurulu değil")
@pytest.mark.parametrize("ad", ADLAR)
def test_K15_linuxcnc_rs274_agrees(ad, tmp_path):
    """K15: LinuxCNC'nin kendi yorumlayıcısıyla da aynı kesme yolu (G83 payı LinuxCNC'de farklı:
    Fanuc ailesinde çevrimi tezgâh açtığından yalnız G81 içeren iş)."""
    m = profil(ad)
    d = dialect_for(m)
    ops = retracted_job()
    if m.controller != "grbl":
        ops = [op for op in ops if getattr(op, "kind", "G81") == "G81"]
    ops = hazirla(ops, m)
    setup = ortala(m, ops, L, z_ek=10.0)
    moves = rs274_moves(post(ops, m, setup), tmp_path)
    errs = compare(expected(ops, d.peck_clearance), moves)
    errs = [e for e in errs if "takım" not in e and "devir" not in e]
    assert not errs, "\n".join(errs[:20])
