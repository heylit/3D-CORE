"""SPEC 46 H15 — tezgâh profiliyle postprosesör (SPEC 30). K15.

Yerleşik örnek profiller (GRBL router, Fanuc ve Haas dik işlem) için flanş programı: iş sıfırı kursun
ortasına yerleştirilir, `post` denetimlerden geçer; program bağımsız yorumlayıcıda modelle aynı hareketleri
verir ve profilin okuyucusuyla okununca H4 ile aynı talaşı kaldırır. İş sıfırı stok kursun dışına taşacak
yere kaydırılınca `CamError`.

`G53 G0 Z…` (makine koordinatında takım değişimi çekilmesi) `gcode_ref`'te yok: karşılaştırmadan önce
bu satırlar atılır; yolun geri kalanı modelle karşılaştırılır (fazladan güvenli çekilmeye izin var).
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from cam.model import CamError, Setup, Wcs
from cam.sim import simulate
from tests.reference.gcode_check import compare, expected, safety
from tests.reference.gcode_ref import RefMachine
from tests.uctan_uca.conftest import STOK_UST, A, B, halka

post = halka("30", "cam.post", "post", "builtin_machines", "dialect_for", "read_program")

CELL = 0.5
ISO_DILLER = ("grbl", "fanuc", "haas")  # gcode_ref yalnız ISO dilini okur (Sinumerik / Heidenhain SPEC 31)
# Torna profili (SPEC 40 Ek E2) freze yolunu yazmaz; burada yalnız freze profilleri
MAKINELER = sorted(
    n for n, m in post.builtin_machines().items() if m.controller in ISO_DILLER and m.kind == "mill"
)


L_MAX = 110.0  # en uzun takımın ölçü boyu: tutucu 60 + matkap sarkması 50 (conftest)


def kurs_ortasi(m) -> Wcs:
    """Stoğu X / Y kursunun ortasına, ölçü hattının Z gezintisini Z kursunun ortasına koyan iş sıfırı."""
    ox = (m.x.min + m.x.max) / 2 - A / 2 if m.x else 0.0
    oy = (m.y.min + m.y.max) / 2 - B / 2 if m.y else 0.0
    oz = (m.z.min + m.z.max) / 2 - (STOK_UST / 2 + L_MAX) if m.z else 0.0
    return Wcs("G54", (ox, oy, oz))


@pytest.fixture(params=MAKINELER)
def makine(request):
    return post.builtin_machines()[request.param]


def g53siz(metin: str) -> str:
    return "\n".join(s for s in metin.splitlines() if not re.search(r"\bG53\b", s))


def test_k15_post_bagimsiz_yorumlayicida_modelle_ayni(makine, freze_ops, flans_stok):
    setup = Setup("flans", kurs_ortasi(makine), flans_stok)
    metin = post.post(freze_ops, makine, setup)
    d = post.dialect_for(makine)
    tr = RefMachine(tool_change=d.tool_change, peck_clearance=d.peck_clearance).run(g53siz(metin))
    errs = compare(expected(freze_ops, d.peck_clearance), tr.moves)
    assert not errs, "\n".join(errs[:20])
    ihlal = [m for k, m in safety(tr, STOK_UST) if k in ("rapid", "tc_z", "cut_spindle", "end")]
    assert not ihlal, "\n".join(ihlal[:20])


@pytest.mark.occt
def test_k15_okunan_program_ayni_talasi_kaldirir(makine, freze_ops, flans_stok, kutuphane):
    setup = Setup("flans", kurs_ortasi(makine), flans_stok)
    tools = {t.id: t for t in kutuphane.tools}
    okunan = post.read_program(post.post(freze_ops, makine, setup), makine, tools)
    dogrudan = simulate(freze_ops, flans_stok, cell=CELL)
    yeniden = simulate(okunan, flans_stok, cell=CELL)
    assert np.abs(yeniden.zmap.z - dogrudan.zmap.z).max() <= 10.0 ** (-makine.decimals)


def test_k15_kurs_disi_stok_hata(makine, freze_ops, flans_stok):
    if makine.x is None:
        pytest.skip("profilde X kursu yok")
    o = kurs_ortasi(makine).origin
    disari = Wcs("G54", (makine.x.max - A / 2, o[1], o[2]))  # stoğun yarısı X kursunun dışında
    with pytest.raises(CamError):
        post.post(freze_ops, makine, Setup("flans", disari, flans_stok))


def test_k15_en_uzun_takim_olcu_boyu(kutuphane):
    assert max(t.gauge_length for t in kutuphane.tools if t.id < 10) == pytest.approx(L_MAX)
