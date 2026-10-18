"""SPEC 46 H2 — bağlama ve takım kütüphanesi (SPEC 14). K2."""

from __future__ import annotations

from cam import cutting
from cam.gcode import DrillOp
from cam.library import check_tools, load_library, save_library
from cam.setups import check_setup
from tests.uctan_uca.conftest import MALZEME


def test_k2_kutuphane_json_gidis_donus(kutuphane, tmp_path):
    yol = tmp_path / "kutuphane.json"
    save_library(kutuphane, yol)
    assert load_library(yol) == kutuphane


def test_k2_takimlar_ve_baglama_denetimi(kutuphane, flans_setup, freze_ops):
    check_tools(kutuphane, freze_ops)
    check_setup(flans_setup, freze_ops)  # çarpma, stok altı, kesici boy: hata yok


def test_k2_devir_ve_ilerleme_kutuphaneden(freze_ops):
    for op in freze_ops:
        sf = cutting.milling(op.tool, MALZEME)
        assert op.rpm == sf.n
        if isinstance(op, DrillOp):
            assert op.feed == sf.F
