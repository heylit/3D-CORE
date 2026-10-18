"""SPEC 69 K7: parça köprüsü (OCCT). `kutleler_parcadan` ve gerçek parçalı krank–biyelde güç dengesi.

Testler SPEC 69 metninden ve arayüzlerden yazıldı (assy/dinamik.py gövdesi okunmadı):
- `kutleler_parcadan(assembly, parts, kutuphane)`: her hareketli bileşen için `Component.material` kimliği →
  `kutuphane[kimlik]` (Mapping[str, malzeme.model.Malzeme]) → `.rho` →
  `geometry.props.mass_props(part, rho)` → `Kutle(m, com, I)`, bileşenin yerel çerçevesinde
  (parçanın kendi koordinatları; Component.T etkilemez).
- Malzemesiz hareketli bileşen, eksik parça, kütüphanede olmayan kimlik ve `rho`'suz malzeme →
  core ModelError.

Varsayımlar (SPEC'te açık değil, makul varsayılan):
- 66 kütüphanesi henüz main'de yok: kayıtlar testte `Malzeme` ile kurulur (1.0503 C45 ρ = 7.85e-9 t/mm³,
  EN-AW-6061-T6 ρ = 2.70e-9 t/mm³; tipik değerler, uydurma geometri).
- `parts` anahtarı `Component.part`; testlerde bileşen adı ile parça referansı aynıdır (iki okuma da tutar).
- Sabit bileşen kütle istemez: malzemesi ve parçası olmayan sabit zemin hata vermez.
- Hata mesajı ilgili bileşenin adını içerir.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from assy.dinamik import Kutle, Surucu, kutleler_parcadan, ters_dinamik
from assy.model import Assembly, Component, rot_z, transform
from core.model import ModelError
from malzeme.model import Malzeme
from tests.assy.test_dinamik import L_B, R_K, guc_referans, krank_biyel, yakin

pytestmark = pytest.mark.occt

RHO_C45 = 7.85e-9  # t/mm³
RHO_AL = 2.70e-9  # t/mm³


def c45() -> Malzeme:
    return Malzeme(
        id="1.0503", name="C45", standart="EN 10083-2", grup="celik", kaynak="test: tipik değer", rho=RHO_C45
    )


def al6061() -> Malzeme:
    return Malzeme(
        id="EN-AW-6061-T6",
        name="AlMg1SiCu",
        standart="EN 573-3",
        grup="aluminyum",
        kaynak="test: tipik değer",
        rho=RHO_AL,
    )


def kutuphane(*kayitlar: Malzeme) -> dict[str, Malzeme]:
    kayitlar = kayitlar or (c45(), al6061())
    return {m.id: m for m in kayitlar}


def kutu(a: float, b: float, c: float, merkez=(0.0, 0.0, 0.0), aci_z: float = 0.0):
    """a×b×c kutu; önce z etrafında aci_z derece döner, sonra merkeze taşınır (parçanın kendi çerçevesi)."""
    from build123d import Box, Pos, Rot

    from geometry.part import Part

    return Part(Pos(*merkez) * Rot(0, 0, aci_z) * Box(a, b, c), name="kutu")


def kutu_J(m: float, a: float, b: float, c: float, aci_z: float = 0.0) -> np.ndarray:
    """Kapalı form: J = R diag(m/12 (b²+c²), m/12 (a²+c²), m/12 (a²+b²)) Rᵀ, kütle merkezi etrafında."""
    J0 = m / 12 * np.diag([b * b + c * c, a * a + c * c, a * a + b * b])
    R = rot_z(aci_z)
    return R @ J0 @ R.T


def bilesen(name: str, T=None, fixed: bool = False, material: str | None = None) -> Component:
    return Component(name=name, part=name, T=np.eye(4) if T is None else T, fixed=fixed, material=material)


def tek_kutu_montaji(material: str | None = "1.0503", T=None) -> Assembly:
    comps = [bilesen("zemin", fixed=True), bilesen("kol", T=T, material=material)]
    return Assembly(name="kutu", components=comps, mates=[], joints=[])


# ---------- kutleler_parcadan: kapalı form ve mass_props ----------


def test_k7_c45_kutu_kapali_form():
    """10×2×2 mm C45 kutu, merkezi (5, 1, 1): m = ρ·40, c = merkez, J kutu formülü."""
    a, b, c = 10.0, 2.0, 2.0
    merkez = np.array([5.0, 1.0, 1.0])
    K = kutleler_parcadan(tek_kutu_montaji(), {"kol": kutu(a, b, c, merkez)}, kutuphane())["kol"]
    m = RHO_C45 * a * b * c
    assert isinstance(K, Kutle)
    assert K.m == pytest.approx(m, rel=1e-9)
    np.testing.assert_allclose(K.c, merkez, rtol=0, atol=1e-9)
    np.testing.assert_allclose(K.J, kutu_J(m, a, b, c), rtol=0, atol=1e-9 * m * a * a)


def test_k7_yerel_cerceve_donuk_parca_ve_T():
    """Dönük kutu (z 30°): J köşegen dışı; Component.T kütleyi değiştirmez (yerel çerçeve)."""
    a, b, c, aci = 10.0, 2.0, 2.0, 30.0
    merkez = np.array([3.0, -2.0, 4.0])
    parts = {"kol": kutu(a, b, c, merkez, aci)}
    m = RHO_C45 * a * b * c
    T = transform(rot_z(55.0), (100.0, -40.0, 7.0))
    for asm in (tek_kutu_montaji(), tek_kutu_montaji(T=T)):
        K = kutleler_parcadan(asm, parts, kutuphane())["kol"]
        assert K.m == pytest.approx(m, rel=1e-9)
        np.testing.assert_allclose(K.c, merkez, rtol=0, atol=1e-9)
        np.testing.assert_allclose(K.J, kutu_J(m, a, b, c, aci), rtol=0, atol=1e-9 * m * a * a)
    assert abs(K.J[0, 1]) > 1e-3 * m * a * a


# ---------- Gerçek parçalı krank–biyel ----------


def kb_parcalar() -> dict:
    """Uydurma geometri, bileşen yerel çerçevelerinde (krank_biyel kurgusu: pimler yerel x ekseninde)."""
    return {
        "krank": kutu(R_K + 12.0, 12.0, 8.0, (R_K / 2, 0.0, 0.0)),
        "biyel": kutu(L_B + 10.0, 10.0, 6.0, (L_B / 2, 0.0, 0.0)),
        "piston": kutu(24.0, 20.0, 20.0),
    }


KB_MALZEME = {"krank": "1.0503", "biyel": "EN-AW-6061-T6", "piston": "1.0503"}
KB_RHO = {"1.0503": RHO_C45, "EN-AW-6061-T6": RHO_AL}


def kb_montaj() -> Assembly:
    asm = krank_biyel(0.0)
    for comp in asm.components:
        comp.material = KB_MALZEME.get(comp.name)
    return asm


def test_k7_krank_biyel_kutleleri_mass_props_ile_ayni():
    from geometry.props import mass_props

    parts = kb_parcalar()
    kut = kutleler_parcadan(kb_montaj(), parts, kutuphane())
    assert set(KB_MALZEME) <= set(kut)
    for ad, mid in KB_MALZEME.items():
        mp = mass_props(parts[ad], KB_RHO[mid])
        K = kut[ad]
        assert K.m == pytest.approx(mp.m, rel=1e-12)
        np.testing.assert_allclose(K.c, mp.com, rtol=0, atol=1e-9)
        np.testing.assert_allclose(K.J, mp.I, rtol=1e-12, atol=1e-12 * np.max(np.abs(mp.I)))


def test_k7_krank_biyel_guc_dengesi():
    """Gerçek parça kütleleriyle, düzlem içi yerçekimi: Σ τ q̇ = dE_k/dt + dV_g/dt (K4 toleransı)."""
    asm = kb_montaj()
    kut = kutleler_parcadan(asm, kb_parcalar(), kutuphane())
    hiz = math.degrees(10.0)
    th = np.linspace(0.0, 330.0, 12)
    g = (0.0, -9810.0, 0.0)
    res = ters_dinamik(asm, kut, [Surucu.sabit_hiz("J_krank", 0.0, hiz)], th / hiz, g=g)
    P = guc_referans(asm, {ad: kut[ad] for ad in KB_MALZEME}, "J_krank", th, hiz, g)
    yakin(res.guc, P, 0.0, 1e-6 * np.max(np.abs(P)))
    yakin(res.tork["J_krank"] * math.radians(hiz), P, 0.0, 1e-6 * np.max(np.abs(P)))


# ---------- Hatalar ----------


def test_k7_malzemesiz_hareketli_bilesen():
    with pytest.raises(ModelError, match="kol"):
        kutleler_parcadan(tek_kutu_montaji(material=None), {"kol": kutu(10, 2, 2)}, kutuphane())


def test_k7_parca_eksik():
    with pytest.raises(ModelError, match="kol"):
        kutleler_parcadan(tek_kutu_montaji(), {}, kutuphane())


def test_k7_kimlik_kutuphanede_yok():
    with pytest.raises(ModelError, match="kol"):
        kutleler_parcadan(tek_kutu_montaji(material="1.2312"), {"kol": kutu(10, 2, 2)}, kutuphane())


def test_k7_rho_yok():
    rhosuz = Malzeme(id="1.0503", name="C45", standart="EN 10083-2", grup="celik", kaynak="test")
    with pytest.raises(ModelError, match="kol"):
        kutleler_parcadan(tek_kutu_montaji(), {"kol": kutu(10, 2, 2)}, kutuphane(rhosuz))
