"""SPEC 67b — emniyet katsayısı ve parça dayanımı köprüsü (K16, K17, parca_dayanimi hataları).

Testler sadece specs/67-fem-genisletme.md (67b) metninden ve analiz/dayanim.py arayüzünden (modül
docstring'indeki biçim kuralları) yazıldı; gövde okunmadı.
    n_i = Rp0.2 / σ_vM,i  (σ_vM düğüm gerilmesi, SPEC 13);  σ_vM,i = 0 → n_i = +inf
`emniyet` testleri OCCT'siz (Kuhn kutu ağı, tests/benchmarks/tet_ag.py): düzgün çekmede tet4 tamdır,
her düğümde σ_vM = F/A. `parca_dayanimi` testleri gmsh + OCCT ister; malzeme B2 Malzeme'nin ördek tipiyle
(tests/benchmarks/yuk_ag.py `SahteMalzeme`) verilir. K17 SPEC 66'nın 1.0577 (S355J2) kaydını ister; malzeme
kütüphanesi main'e girene kadar "uygulanmamış".
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from analiz import Dayanim, emniyet, parca_dayanimi
from core.model import BC, Material, ModelError
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi, yuzey_cekmesi
from tests.benchmarks.yuk_ag import SahteMalzeme, dugum_bul

E, NU = 210_000.0, 0.3
CELIK = Material("celik", E, NU, 7.85e-9)
L, A_K = 100.0, 10.0  # 10 × 10 × 100 çubuk
F_CEKME = 10_000.0  # N → σ = 100 MPa


def _cubuk(k: int = 1, malzemeler=None):
    """x = 0 yüzü u_x = 0 (+ uyumlu yanal mesnet), x = L yüzüne F/A çekmesi; düzgün σ_xx = 100 MPa."""
    m = kutu_agi(L, A_K, A_K, 4 * k, k, k, CELIK)
    if malzemeler is not None:
        m.materials = list(malzemeler.values())
        for e in m.elements:
            xc = np.mean([m.node(n).x for n in e.nodes])
            e.material = "a" if xc < L / 2 else "b"
    for n in m.nodes:
        if abs(n.x) <= 1e-9:
            m.bcs.append(BC(n.id, "ux"))
    o = dugum_bul(m, (0, 0, 0))
    m.bcs += [
        BC(o, "uy"),
        BC(o, "uz"),
        BC(dugum_bul(m, (0, A_K, 0)), "uz"),
        BC(dugum_bul(m, (0, 0, A_K)), "uy"),
    ]
    m.loads += yuzey_cekmesi(m, 0, L, (F_CEKME / A_K**2, 0.0, 0.0))
    return m, solve(m).u


# ---------- K16 emniyet ----------


def test_uniform_tension_every_node():
    """σ = 10000 / 100 = 100 MPa, Rp02 = 355 → her düğümde n = 3.55 (göreli 1e-6), n_min ≤ 3.55."""
    m, u = _cubuk()
    d = emniyet(m, u, 355.0)
    assert isinstance(d, Dayanim)
    assert np.shape(d.n) == (len(m.nodes),)
    np.testing.assert_allclose(d.n, 3.55, rtol=1e-6)
    assert d.n_min <= 3.55 * (1 + 1e-6)
    assert d.sigma_vM_maks == pytest.approx(100.0, rel=1e-6)
    assert d.gevrek is False
    i = [n.id for n in m.nodes].index(d.dugum)
    assert d.n[i] == pytest.approx(d.n_min, rel=1e-12)
    np.testing.assert_allclose(d.konum, m.node(d.dugum).xyz, atol=1e-12)


def test_n_min_node_is_minimum():
    """Eğilmeli durumda n_min düğümü gerçekten en küçük n'li düğümdür; konum o düğümün koordinatı."""
    m = kutu_agi(L, A_K, A_K, 8, 2, 2, CELIK)
    for n in m.nodes:
        if abs(n.x) <= 1e-9:
            m.bcs += [BC(n.id, "ux"), BC(n.id, "uy"), BC(n.id, "uz")]
    m.loads += yuzey_cekmesi(m, 0, L, (0.0, 0.0, -1.0))
    u = solve(m).u
    d = emniyet(m, u, 355.0)
    assert d.n_min == pytest.approx(float(np.min(d.n)), rel=1e-12)
    i = [n.id for n in m.nodes].index(d.dugum)
    assert d.n[i] == d.n_min
    np.testing.assert_allclose(d.konum, m.node(d.dugum).xyz, atol=1e-12)
    assert d.sigma_vM_maks == pytest.approx(355.0 / d.n_min, rel=1e-9)


def test_unloaded_model_infinite():
    """Yüksüz modelde σ_vM = 0: bütün n = inf, n_min = inf, dugum en küçük id."""
    m = kutu_agi(L, A_K, A_K, 2, 1, 1, CELIK)
    d = emniyet(m, np.zeros(m.n_dof), 355.0)
    assert d.n_min == math.inf
    assert np.all(np.isinf(d.n)) and np.all(d.n > 0)
    assert d.dugum == min(n.id for n in m.nodes)
    assert d.sigma_vM_maks == 0.0


def test_brittle_flag_carried():
    m, u = _cubuk()
    assert emniyet(m, u, 355.0, gevrek=True).gevrek is True


def test_rp02_mapping_uses_minimum_at_shared_nodes():
    """İki malzeme (aynı E): x < 50 'a' (Rp02 355), x > 50 'b' (Rp02 235).
    x = 50'deki ortak düğüm en küçüğü alır."""
    mats = {"a": Material("a", E, NU), "b": Material("b", E, NU)}
    m, u = _cubuk(1, mats)
    d = emniyet(m, u, {"a": 355.0, "b": 235.0})
    for i, n in enumerate(m.nodes):
        beklenen = 3.55 if n.x < L / 2 - 1e-9 else 2.35
        assert d.n[i] == pytest.approx(beklenen, rel=1e-6)
    assert d.n_min == pytest.approx(2.35, rel=1e-6)


@pytest.mark.parametrize("Rp02", [{"a": 355.0}, 0.0, -10.0], ids=["eksik-malzeme", "sifir", "negatif"])
def test_bad_rp02_raises(Rp02):
    mats = {"a": Material("a", E, NU), "b": Material("b", E, NU)}
    m, u = _cubuk(1, mats)
    with pytest.raises(ModelError):
        emniyet(m, u, Rp02)


def test_thermal_strain_subtracted():
    """Eksenel tutulu çubuk, ΔT = 50, α = 1.2e-5: σ_xx = −126 → σ_vM = 126, n = 355/126 her düğümde."""
    m = kutu_agi(L, A_K, A_K, 4, 1, 1, CELIK)
    for n in m.nodes:
        if abs(n.x) <= 1e-9 or abs(n.x - L) <= 1e-9:
            m.bcs.append(BC(n.id, "ux"))
    o = dugum_bul(m, (0, 0, 0))
    m.bcs += [
        BC(o, "uy"),
        BC(o, "uz"),
        BC(dugum_bul(m, (0, A_K, 0)), "uz"),
        BC(dugum_bul(m, (0, 0, A_K)), "uy"),
    ]
    from core import yukler

    T = {n.id: 70.0 for n in m.nodes}
    yukler.add_loads(m, yukler.thermal_loads(m, T, 20.0, 1.2e-5))
    u = solve(m).u
    d = emniyet(m, u, 355.0, T=T, T_ref=20.0, alpha=1.2e-5)
    np.testing.assert_allclose(d.n, 355.0 / 126.0, rtol=1e-9)
    with pytest.raises(ModelError):
        emniyet(m, u, 355.0, T=T, T_ref=20.0)  # alpha yok


def test_emniyet_does_not_change_model():
    m, u = _cubuk()
    once = m.to_dict()
    emniyet(m, u, 355.0)
    assert m.to_dict() == once


# ---------- parca_dayanimi (gmsh + OCCT) ----------


def _gmsh():
    pytest.importorskip("gmsh")
    pytest.importorskip("build123d")


def _cubuk_parca(L_=L, b=A_K):
    """[0, L] × [0, b] × [0, b] kutu; FaceRef("cubuk", "x0") ve ("cubuk", "xL") uç yüzleri."""
    from build123d import Align, Box

    from geometry.part import FaceRef, Part

    sekil = Box(L_, b, b, align=(Align.MIN, Align.MIN, Align.MIN))
    gecici = Part(sekil)
    adlar = {}
    for f in gecici.planar_faces():
        if abs(f.normal[0]) > 0.5:
            adlar[FaceRef("cubuk", "xL" if f.normal[0] > 0 else "x0")] = (f.index,)
    return Part(sekil, name="cubuk", names=adlar)


def _r(ad):
    from geometry.part import FaceRef

    return FaceRef("cubuk", ad)


@pytest.mark.occt
@pytest.mark.parametrize("order", [1, 2])
def test_parca_dayanimi_bar_tension(order):
    """Çubuk: x0 sabit, xL'ye toplam (10000, 0, 0) N, alanla dağıtılmış (Σ = F); orta bölgede n ≈ 3.55."""
    _gmsh()
    part = _cubuk_parca()
    pm, u, d = parca_dayanimi(
        part, 5.0, SahteMalzeme(), order=order, sabit=[_r("x0")], kuvvet=[(_r("xL"), (F_CEKME, 0, 0))]
    )
    m = pm.model
    assert np.shape(u) == (m.n_dof,)
    Fx = sum(ld.value for ld in m.loads if ld.dof == "ux")
    assert Fx == pytest.approx(F_CEKME, rel=1e-12)
    sabit = set(pm.nodes(part, _r("x0")))
    tutulu = {(bc.node, bc.dof) for bc in m.bcs}
    assert {(n, dof) for n in sabit for dof in ("ux", "uy", "uz")} <= tutulu
    orta = [i for i, n in enumerate(m.nodes) if 40.0 <= n.x <= 60.0]
    np.testing.assert_allclose(d.n[orta], 3.55, rtol=1e-2)
    assert d.n_min <= 3.55 * (1 + 1e-2)
    assert d.gevrek is False


@pytest.mark.occt
def test_parca_dayanimi_brittle_group():
    _gmsh()
    part = _cubuk_parca()
    _, _, d = parca_dayanimi(
        part,
        5.0,
        SahteMalzeme(grup="dokme_demir"),
        order=1,
        sabit=[_r("x0")],
        kuvvet=[(_r("xL"), (F_CEKME, 0, 0))],
    )
    assert d.gevrek is True


@pytest.mark.occt
def test_parca_dayanimi_pressure_equals_force():
    """xL'ye p = −100 MPa (çekme) basınç, 10000 N kuvvetle aynı çözümü verir (aynı ağ)."""
    _gmsh()
    part = _cubuk_parca()
    _, u1, _ = parca_dayanimi(
        part, 5.0, SahteMalzeme(), order=1, sabit=[_r("x0")], kuvvet=[(_r("xL"), (F_CEKME, 0, 0))]
    )
    _, u2, _ = parca_dayanimi(
        part, 5.0, SahteMalzeme(), order=1, sabit=[_r("x0")], basinc=[(_r("xL"), -100.0)]
    )
    np.testing.assert_allclose(u2, u1, rtol=1e-9, atol=1e-12)


@pytest.mark.occt
def test_parca_dayanimi_gravity_only():
    """Yalnız yerçekimi, x0 sabit: toplam yük −m g (m = ρ V), n_min sonlu."""
    _gmsh()
    part = _cubuk_parca()
    mal = SahteMalzeme()
    pm, _, d = parca_dayanimi(part, 5.0, mal, order=1, sabit=[_r("x0")], g=(0.0, 0.0, -9810.0))
    Fz = sum(ld.value for ld in pm.model.loads if ld.dof == "uz")
    assert Fz == pytest.approx(-mal.rho * L * A_K * A_K * 9810.0, rel=1e-12)
    assert math.isfinite(d.n_min)


@pytest.mark.occt
@pytest.mark.parametrize(
    "malzeme, kw",
    [
        (SahteMalzeme(), {"kuvvet": [("xL", (F_CEKME, 0, 0))]}),  # sabit boş, hacim / ısıl yük yok
        (SahteMalzeme(), {"sabit": ["yok"], "kuvvet": [("xL", (F_CEKME, 0, 0))]}),  # bulunamayan ref
        (SahteMalzeme(Rp02=None), {"sabit": ["x0"], "kuvvet": [("xL", (F_CEKME, 0, 0))]}),  # Rp02 yok
        (SahteMalzeme(rho=None), {"sabit": ["x0"], "g": (0.0, 0.0, -9810.0)}),  # g var, rho yok
        (SahteMalzeme(rho=None), {"sabit": ["x0"], "omega": 100.0, "eksen": ((0, 0, 0), (1, 0, 0))}),
        (SahteMalzeme(alpha=None), {"sabit": ["x0"], "T": {}}),  # T var, alpha yok
        (SahteMalzeme(), {"sabit": ["x0"], "omega": 100.0}),  # omega var, eksen yok
    ],
    ids=["sabit-bos", "ref-yok", "rp02-yok", "rho-yok-g", "rho-yok-omega", "alpha-yok", "eksen-yok"],
)
def test_parca_dayanimi_errors(malzeme, kw):
    _gmsh()
    part = _cubuk_parca()
    kw = dict(kw)
    for anahtar in ("sabit",):
        if anahtar in kw:
            kw[anahtar] = [_r(a) for a in kw[anahtar]]
    for anahtar in ("kuvvet", "basinc"):
        if anahtar in kw:
            kw[anahtar] = [(_r(a), v) for a, v in kw[anahtar]]
    if "T" in kw:
        kw["T"] = _HER_DUGUM_70
    with pytest.raises(ModelError):
        parca_dayanimi(part, 5.0, malzeme, order=1, **kw)


class _HerDugum70(dict):
    """Her düğüm id'si için 70 °C (ağ önceden bilinmediği için)."""

    def __missing__(self, key):
        return 70.0

    def __contains__(self, key):
        return True

    def get(self, key, default=None):
        return 70.0


_HER_DUGUM_70 = _HerDugum70()


# ---------- K17 uçtan uca delikli plaka (SPEC 13 + SPEC 66 1.0577) ----------

PL, PB, PT, PR = 200.0, 100.0, 2.0, 5.0  # 200 × 100 × 2, d = 10 delik
P_UC = 20.0  # MPa, karşı yüze basınç (uzak alan σ_nom = 20)
H_PLAKA = 2.0  # parca_dayanimi'de Refine yok; delik çevresi ≈ 16 eleman (varsayım)


def kt_heywood(d_W: float) -> float:
    return (2.0 + (1.0 - d_W) ** 3) / (1.0 - d_W)


def _s355j2():
    try:
        from malzeme.kutuphane import yerlesik
    except ImportError:
        raise NotImplementedError("SPEC 66: malzeme.kutuphane (1.0577 kaydı) henüz yok") from None
    return yerlesik().get("1.0577")


@pytest.mark.occt
@pytest.mark.slow
def test_end_to_end_holed_plate():
    """n_min = Rp02 / (Kt_g σ_nom) %3 içinde (Kt_g = 3.032, d/W = 0.1); n_min düğümü delik kenarında."""
    _gmsh()
    mal = _s355j2()
    from build123d import Align, Box, Cylinder, Pos

    from geometry.part import FaceRef, Part

    sekil = Box(PL, PB, PT, align=(Align.CENTER, Align.CENTER, Align.MIN)) - Pos(0, 0, PT / 2) * Cylinder(
        PR, 3 * PT
    )
    gecici = Part(sekil)
    adlar = {}
    for f in gecici.planar_faces():
        if abs(f.normal[0]) > 0.5:
            adlar[FaceRef("plaka", "sag" if f.normal[0] > 0 else "sol")] = (f.index,)
    part = Part(sekil, name="plaka", names=adlar)
    pm, _, d = parca_dayanimi(
        part,
        H_PLAKA,
        mal,
        order=2,
        sabit=[FaceRef("plaka", "sol")],
        basinc=[(FaceRef("plaka", "sag"), P_UC)],
    )
    hedef = mal.iste("Rp02") / (kt_heywood(2 * PR / PB) * P_UC)
    assert kt_heywood(0.1) == pytest.approx(3.032, abs=5e-4)
    assert d.n_min == pytest.approx(hedef, rel=0.03)
    x, y, _ = d.konum
    assert abs(math.hypot(x, y) - PR) <= 1e-6
