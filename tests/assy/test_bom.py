"""SPEC 07 — assy/bom.py testleri: malzeme listesi, kütle ve ağırlık merkezi (K4–K6).

Testler sadece specs/07-montaj-agaci.md'deki teori ve arayüzden yazıldı; assy/bom.py gövdesi okunmadı.
- Düz BOM: q_p = parçanın yaprak sayısı, M_p = q_p m_p, M = Σ q_p m_p.
- Üst seviye BOM: kökün doğrudan çocukları tanıma göre; alt montajın birim kütlesi içindeki
  yaprakların toplamı.
- m = ρ V (birimler N–mm–MPa: ρ [t/mm³], m [t]).
- Ağırlık merkezi (Beer & Johnston, Statics, Bölüm 5): x̄ = Σ m_i (R_i c_i + t_i) / Σ m_i.
assy/bom.py parçayı sadece .volume ve .center_of_mass'tan okur; OCCT'siz testler sahte parça kullanır.

`Node` main'e arayüz PR'ıyla gelene kadar testler "uygulanmamış" (NotImplementedError) sayılır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pytest

from assy.bom import BomLine, bom, mass_center, total_mass, unit_masses
from assy.model import AssyError, rot_x, rot_z, transform


def _uygulanmamis(*_a, **_k):
    raise NotImplementedError("assy.model.Node henüz yok (SPEC 07 arayüz PR'ı)")


try:
    from assy.model import Node
except ImportError:  # arayüz PR'ı gelene kadar testler "uygulanmamış" sayılır
    Node = _uygulanmamis

RHO_CELIK = 7.85e-9  # t/mm³

# Birim kütleler [t]
M_VIDA = 1.2e-5
M_PLAKA = 2.4e-3
M_GOVDE = 3.1e-2
KUTLE = {"vida": M_VIDA, "plaka": M_PLAKA, "govde": M_GOVDE}


@dataclass
class SahteParca:
    """Part yerine: sadece hacim ve yerel ağırlık merkezi."""

    volume: float
    center_of_mass: np.ndarray


def alt(ad: str, T: np.ndarray) -> Node:
    """Paylaşımlı 'alt' tanımı: 4 vida + 1 plaka (vidaların arasında plaka; ilk görülme sırası için)."""
    return Node(
        ad,
        T=T,
        ref="alt",
        children=[
            Node("vida_1", T=transform(None, (10.0, 10.0, 0.0)), part="vida"),
            Node("plaka", part="plaka"),
            Node("vida_2", T=transform(None, (-10.0, 10.0, 0.0)), part="vida"),
            Node("vida_3", T=transform(None, (-10.0, -10.0, 0.0)), part="vida"),
            Node("vida_4", T=transform(None, (10.0, -10.0, 0.0)), part="vida"),
        ],
    )


def ornek_agac() -> Node:
    """2 alt montaj × (4 vida + 1 plaka) + 1 gövde. Sıra: alt_a, govde, alt_b."""
    return Node(
        "montaj",
        children=[
            alt("alt_a", transform(rot_z(90), (0.0, 0.0, 30.0))),
            Node("govde", part="govde"),
            alt("alt_b", transform(rot_x(180), (0.0, 0.0, -30.0))),
        ],
    )


# ---------------------------------------------------------------- K4 düz BOM


def test_k4_duz_bom_adet_ve_sira():
    satirlar = bom(ornek_agac())
    assert [(s.item, s.kind, s.qty) for s in satirlar] == [
        ("vida", "parca", 8),
        ("plaka", "parca", 2),
        ("govde", "parca", 1),
    ]
    assert all(isinstance(s, BomLine) for s in satirlar)


def test_k4_duz_bom_varsayilan_flat():
    root = ornek_agac()
    assert bom(root) == bom(root, flat=True)


def test_k4_kutlesiz_bom_none():
    for s in bom(ornek_agac()):
        assert s.unit_mass is None
        assert s.total_mass is None


def test_k4_kutleli_duz_bom():
    satirlar = {s.item: s for s in bom(ornek_agac(), unit_mass=KUTLE)}
    for item, q in (("vida", 8), ("plaka", 2), ("govde", 1)):
        assert satirlar[item].unit_mass == pytest.approx(KUTLE[item], rel=1e-12)
        assert satirlar[item].total_mass == pytest.approx(q * KUTLE[item], rel=1e-12)


def test_k4_total_mass():
    M = 8 * M_VIDA + 2 * M_PLAKA + 1 * M_GOVDE
    assert total_mass(ornek_agac(), KUTLE) == pytest.approx(M, rel=1e-12)


def test_k4_total_mass_satir_toplami():
    root = ornek_agac()
    toplam = sum(s.total_mass for s in bom(root, unit_mass=KUTLE))
    assert total_mass(root, KUTLE) == pytest.approx(toplam, rel=1e-12)


def test_k4_tek_seviye_tekrarli_parca():
    """Alt montajsız kökte aynı parça üç kez: adet 3, sıra ilk görülme."""
    root = Node(
        "duz",
        children=[
            Node("p1", part="pim"),
            Node("b", part="burc"),
            Node("p2", T=transform(None, (5.0, 0.0, 0.0)), part="pim"),
            Node("p3", T=transform(None, (9.0, 0.0, 0.0)), part="pim"),
        ],
    )
    assert [(s.item, s.qty) for s in bom(root)] == [("pim", 3), ("burc", 1)]


# ---------------------------------------------------------------- K5 üst seviye BOM


def test_k5_ust_seviye_bom():
    satirlar = bom(ornek_agac(), flat=False)
    assert [(s.item, s.kind, s.qty) for s in satirlar] == [("alt", "montaj", 2), ("govde", "parca", 1)]
    for s in satirlar:
        assert s.unit_mass is None and s.total_mass is None


def test_k5_ust_seviye_bom_kutleli():
    satirlar = bom(ornek_agac(), unit_mass=KUTLE, flat=False)
    m_alt = 4 * M_VIDA + M_PLAKA
    assert satirlar[0].item == "alt"
    assert satirlar[0].unit_mass == pytest.approx(m_alt, rel=1e-12)
    assert satirlar[0].total_mass == pytest.approx(2 * m_alt, rel=1e-12)
    assert satirlar[1].item == "govde"
    assert satirlar[1].unit_mass == pytest.approx(M_GOVDE, rel=1e-12)
    assert satirlar[1].total_mass == pytest.approx(M_GOVDE, rel=1e-12)


def test_k5_ref_siz_alt_montaj_tanimi_ad():
    root = Node(
        "montaj",
        children=[Node("grup", children=[Node("pim", part="pim")]), Node("govde", part="govde")],
    )
    assert [(s.item, s.kind, s.qty) for s in bom(root, flat=False)] == [
        ("grup", "montaj", 1),
        ("govde", "parca", 1),
    ]


# ---------------------------------------------------------------- K4–K6 hatalar


def test_bom_gecersiz_agac_hata():
    root = ornek_agac()
    root.children.append(Node("govde", part="govde"))  # yinelenen kardeş adı
    with pytest.raises(AssyError):
        bom(root)


@pytest.mark.parametrize("flat", [True, False])
def test_k6_eksik_birim_kutle_hata(flat):
    kutle = {"vida": M_VIDA, "govde": M_GOVDE}  # plaka yok
    with pytest.raises(AssyError):
        bom(ornek_agac(), unit_mass=kutle, flat=flat)


@pytest.mark.parametrize("m", [0.0, -1e-3, math.nan, math.inf])
def test_k6_gecersiz_birim_kutle_hata(m):
    with pytest.raises(AssyError):
        bom(ornek_agac(), unit_mass={**KUTLE, "plaka": m})


def test_k6_total_mass_eksik_kutle_hata():
    with pytest.raises(AssyError):
        total_mass(ornek_agac(), {"vida": M_VIDA, "plaka": M_PLAKA})


# ---------------------------------------------------------------- K6 unit_masses


def test_k6_unit_masses_tek_rho_sahte_parca():
    parcalar = {
        "blok": SahteParca(6000.0, np.zeros(3)),
        "pim": SahteParca(150.0, np.zeros(3)),
    }
    m = unit_masses(parcalar, RHO_CELIK)
    assert set(m) == {"blok", "pim"}
    assert m["blok"] == pytest.approx(RHO_CELIK * 6000.0, rel=1e-12)
    assert m["pim"] == pytest.approx(RHO_CELIK * 150.0, rel=1e-12)


def test_k6_unit_masses_rho_sozluk():
    rho_al = 2.7e-9
    parcalar = {"blok": SahteParca(6000.0, np.zeros(3)), "pim": SahteParca(150.0, np.zeros(3))}
    m = unit_masses(parcalar, {"blok": rho_al, "pim": RHO_CELIK})
    assert m["blok"] == pytest.approx(rho_al * 6000.0, rel=1e-12)
    assert m["pim"] == pytest.approx(RHO_CELIK * 150.0, rel=1e-12)


def test_k6_unit_masses_rho_sozlukte_eksik_hata():
    parcalar = {"blok": SahteParca(6000.0, np.zeros(3)), "pim": SahteParca(150.0, np.zeros(3))}
    with pytest.raises(AssyError):
        unit_masses(parcalar, {"blok": RHO_CELIK})


@pytest.mark.parametrize("rho", [0.0, -7.85e-9, math.nan, math.inf])
def test_k6_unit_masses_gecersiz_rho_hata(rho):
    parcalar = {"blok": SahteParca(6000.0, np.zeros(3))}
    with pytest.raises(AssyError):
        unit_masses(parcalar, rho)
    with pytest.raises(AssyError):
        unit_masses(parcalar, {"blok": rho})


@pytest.mark.occt
def test_k6_unit_masses_gercek_blok():
    bd = pytest.importorskip("build123d")
    from geometry.part import Part

    a, b, c = 100.0, 60.0, 30.0
    m = unit_masses({"blok": Part(bd.Box(a, b, c), name="blok")}, RHO_CELIK)
    assert m["blok"] == pytest.approx(RHO_CELIK * a * b * c, rel=1e-6)


# ---------------------------------------------------------------- K6 mass_center


def iki_kutleli_agac() -> Node:
    """Kök Rz90 + (0, 0, 10); 'a' blok (10, 0, 0)'da; 'g' alt montajı Rx90 + (0, 20, 0),
    içinde 'b' silindir."""
    return Node(
        "montaj",
        T=transform(rot_z(90), (0.0, 0.0, 10.0)),
        children=[
            Node("a", T=transform(None, (10.0, 0.0, 0.0)), part="blok"),
            Node("g", T=transform(rot_x(90), (0.0, 20.0, 0.0)), children=[Node("b", part="silindir")]),
        ],
    )


IKI_PARCA = {
    "blok": SahteParca(1000.0, np.array([5.0, 2.0, 1.0])),
    "silindir": SahteParca(500.0, np.array([0.0, 0.0, 30.0])),
}
IKI_KUTLE = {"blok": 2.0, "silindir": 1.0}


def test_k6_mass_center_el_hesabi():
    """a: R = Rz90, t = Rz90 (10, 0, 0) + (0, 0, 10) = (0, 10, 10); c = Rz90 (5, 2, 1) + t = (−2, 15, 11).
    b: R = Rz90 Rx90 = [[0,0,1],[1,0,0],[0,1,0]], t = Rz90 (0, 20, 0) + (0, 0, 10) = (−20, 0, 10);
       c = R (0, 0, 30) + t = (30, 0, 0) + t = (10, 0, 10).
    x̄ = (2 (−2, 15, 11) + 1 (10, 0, 10)) / 3 = (2, 10, 32/3)."""
    x = mass_center(iki_kutleli_agac(), IKI_PARCA, IKI_KUTLE)
    assert np.shape(x) == (3,)
    np.testing.assert_allclose(x, [2.0, 10.0, 32.0 / 3.0], rtol=0, atol=1e-12)


def test_k6_mass_center_tekrarli_parca():
    """Aynı parça iki kez, simetrik konumda: x̄ ikisinin ortası (kütleler eşit)."""
    root = Node(
        "montaj",
        children=[
            Node("p1", T=transform(None, (-40.0, 0.0, 0.0)), part="blok"),
            Node("p2", T=transform(rot_z(180), (40.0, 6.0, 0.0)), part="blok"),
        ],
    )
    # p1: (5, 2, 1) + (−40, 0, 0) = (−35, 2, 1); p2: Rz180 (5, 2, 1) + (40, 6, 0) = (35, 4, 1)
    x = mass_center(root, IKI_PARCA, IKI_KUTLE)
    np.testing.assert_allclose(x, [0.0, 3.0, 1.0], rtol=0, atol=1e-12)


def test_k6_mass_center_eksik_parca_hata():
    with pytest.raises(AssyError):
        mass_center(iki_kutleli_agac(), {"blok": IKI_PARCA["blok"]}, IKI_KUTLE)


def test_k6_mass_center_eksik_kutle_hata():
    with pytest.raises(AssyError):
        mass_center(iki_kutleli_agac(), IKI_PARCA, {"blok": 2.0})
