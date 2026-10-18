"""SPEC 68d K7 — parça köprüsü (OCCT + gmsh): delikli plakada döngüsel çekme, R = 0.1.

Testler yalnız specs/68d-yorulma.md metninden ve analiz/yorulma.py arayüzünden yazıldı;
fonksiyon gövdeleri okunmadı.
Köprü dili 67b `parca_dayanimi` ile aynı varsayıldı: `sabit` FaceRef dizisi (ankastre), `yuk_A` yüze
toplam kuvvet `[(FaceRef, (Fx, Fy, Fz))]` (67b `kuvvet` biçimi).

Plaka 200 × 100 × 2, merkezde d = 10 delik (SPEC 13). Heywood (brüt kesit): d/W = 0.1 → Kt_g = 3.032.
σ_nom = F/(W t), σ_max = Kt_g σ_nom; delik kenarında gerilme tek eksenli → σvM = σ_max.
R = 0.1: σa = (1 − R)/2 · σ_max, σm = (1 + R)/2 · σ_max, n_f = 1/(σa/Se + σm/Rm).
67b (analiz.dayanim, mesh.mesh_part) bu dalda yoksa test NotImplementedError ile "uygulanmamış" düşer.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from analiz.yorulma import Marin, dayanim_siniri, parca_yorulmasi
from tests.analiz.yorulma_ref import RM, celik

pytestmark = [pytest.mark.occt, pytest.mark.slow]

LX, W, T = 200.0, 100.0, 2.0
D_DELIK = 10.0
F_NOM = 40.0 * W * T  # σ_nom = 40 MPa
R_ORAN = 0.1


def kt_heywood(d_W: float) -> float:
    return (2.0 + (1.0 - d_W) ** 3) / (1.0 - d_W)


def _67b_gerekli() -> None:
    if importlib.util.find_spec("analiz.dayanim") is None:
        raise NotImplementedError("SPEC 67b (analiz.dayanim, parça köprüsü) bu dalda yok")


def _plaka():
    import build123d as bd

    from geometry.part import FaceRef, Part

    sekil = bd.Box(LX, W, T, align=(bd.Align.MIN,) * 3) - bd.Pos(LX / 2, W / 2, T / 2) * bd.Cylinder(
        D_DELIK / 2, 3 * T
    )
    ham = Part(sekil, name="delikli_plaka")
    sol = [f.index for f in ham.planar_faces() if np.allclose(f.normal, (-1, 0, 0), atol=1e-9)]
    sag = [f.index for f in ham.planar_faces() if np.allclose(f.normal, (1, 0, 0), atol=1e-9)]
    assert len(sol) == 1 and len(sag) == 1
    ref_sol, ref_sag = FaceRef("plaka", "sol"), FaceRef("plaka", "sag")
    return Part(sekil, name="delikli_plaka", names={ref_sol: (sol[0],), ref_sag: (sag[0],)}), ref_sol, ref_sag


def test_k7_delikli_plaka():
    pytest.importorskip("gmsh")
    _67b_gerekli()
    part, sol, sag = _plaka()
    mat = celik()
    marin = Marin(yuzey="islenmis")
    y = parca_yorulmasi(
        part, 2.5, mat, marin=marin, sabit=[sol], yuk_A=[(sag, (F_NOM, 0.0, 0.0))], R=R_ORAN, order=2
    )
    Se = dayanim_siniri(mat, marin)
    s_max = kt_heywood(D_DELIK / W) * F_NOM / (W * T)
    sa, sm = (1 - R_ORAN) / 2 * s_max, (1 + R_ORAN) / 2 * s_max
    nf_el = 1.0 / (sa / Se + sm / RM)
    assert y.n_f_min == pytest.approx(nf_el, rel=0.03)
    # n_f_min düğümü delik kenarında: eksene uzaklık ≈ r, yük yönüne dik (θ = 90°) bölgede
    p = np.asarray(y.konum, dtype=float)
    r = np.hypot(p[0] - LX / 2, p[1] - W / 2)
    assert abs(r - D_DELIK / 2) < 0.5
    assert abs(p[0] - LX / 2) < 1.5
    assert y.Se == pytest.approx(Se, rel=1e-12)
    assert "ön değerlendirme" in y.not_
