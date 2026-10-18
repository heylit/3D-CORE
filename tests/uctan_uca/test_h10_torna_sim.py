"""SPEC 46 H10 — milin torna simülasyonu (SPEC 22). K10.

İşlenen bölge z ∈ [0, 61]: beklenen kaldırılan hacim ΔV₀ = π·12²·61 − V_mil (z < 0 aynada). Tolerans SPEC 22
K7'nin ölçütü: |ΔV − ΔV₀| ≤ P·dz·2π·R; P = alın (12) + profil uzunluğu, R = 12 (çubuk yarıçapı).
"""

from __future__ import annotations

import math

import pytest

from tests.uctan_uca.conftest import CUBUK_D, CUBUK_ZMAX, V_mil, halka, mil_profili

sim = halka("22", "cam.sim", "simulate_lathe", "RadialMap", "part_rmap")
lathe = halka("21", "cam.gcode.lathe", "write_lathe", "read_lathe")

pytestmark = pytest.mark.occt

TC = (50.0, 100.0)


@pytest.fixture(scope="module", params=[0.5, 0.25], ids=["dz0.5", "dz0.25"])
def sonuc(request, torna_ops, mil_stok, mil):
    dz = request.param
    g = sim.RadialMap.from_stock(mil_stok, dz)
    return dz, sim.simulate_lathe(torna_ops, mil_stok, cell=dz, part=sim.part_rmap(mil, g))


def test_k10_carpisma_ve_cakma_yok(sonuc):
    _, r = sonuc
    assert r.collisions == []


def test_k10_kaldirilan_hacim_pappus(sonuc):
    dz, r = sonuc
    R = CUBUK_D / 2
    dV0 = math.pi * R**2 * CUBUK_ZMAX - V_mil()
    P = R + mil_profili().length
    assert abs(r.removed_volume - dV0) <= P * dz * 2 * math.pi * R


def test_k10_okunan_program_ayni_sonuc(torna_ops, mil_stok, kutuphane):
    tools = {t.id: t for t in kutuphane.tools if t.id == 11}
    okunan = lathe.read_lathe(lathe.write_lathe(torna_ops, "M3", TC), tools, spindle="M3")
    a = sim.simulate_lathe(torna_ops, mil_stok, cell=0.5)
    b = sim.simulate_lathe(okunan, mil_stok, cell=0.5)
    assert b.collisions == []
    assert b.removed_volume == pytest.approx(a.removed_volume, rel=1e-4)
