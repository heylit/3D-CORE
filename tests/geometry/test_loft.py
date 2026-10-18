"""SPEC 65a K1, K2, K7, K8 (loft), K9 — loft unsuru ve ağaç davranışı.

Testler SPEC 65a metninden ve arayüzden yazıldı; uygulama gövdeleri okunmadı.
Ruled loft hacimleri kapalı formlu: prizma V = A h, kesik piramit V = h/3 (A1 + A2 + √(A1 A2)),
kesik koni V = π h/3 (r1² + r1 r2 + r2²).
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from tests.geometry.serbest_ortak import (
    REL,
    TABAN,
    acik_profil,
    daire,
    duzlem_z,
    kare,
    kesik_koni,
    rapor,
    sessiz_gecmez,
    yuzler,
)

occt = pytest.mark.occt


@pytest.fixture
def ag():
    pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')
    import geometry.agac as m

    return m


def iki_kesit(ag, b1, b2, h: float, ruled: bool = True, islem: str = "yeni"):
    return ag.Agac(
        (
            ag.Profil("p1", TABAN, (b1,)),
            ag.Profil("p2", duzlem_z(h), (b2,)),
            ag.Loft("loft", ("p1", "p2"), ruled=ruled, islem=islem),
        )
    )


def uc_daire(ag, ruled: bool):
    """K2: r = 10, 15, 10 daireler, z = 0, 25, 50."""
    return ag.Agac(
        (
            ag.Profil("p1", TABAN, (daire(10.0),)),
            ag.Profil("p2", duzlem_z(25.0), (daire(15.0),)),
            ag.Profil("p3", duzlem_z(50.0), (daire(10.0),)),
            ag.Loft("loft", ("p1", "p2", "p3"), ruled=ruled, islem="yeni"),
        )
    )


def test_loft_arayuzu_varsayilanlar(ag):
    oz = ag.Loft("l", ("a", "b"))
    assert oz.ruled is False
    assert oz.islem == "ekle"


# --- K1: ruled loft hacimleri ----------------------------------------------------------------------------


@occt
@pytest.mark.parametrize(
    ("b1", "b2", "h", "V"),
    [
        pytest.param(daire(10.0), daire(10.0), 50.0, 15707.963, id="silindir"),
        pytest.param(kare(20.0), kare(10.0), 30.0, 7000.0, id="kesik-piramit"),
        pytest.param(daire(10.0), daire(5.0), 30.0, 5497.787, id="kesik-koni"),
    ],
)
def test_k1_ruled_hacim(ag, b1, b2, h, V):
    s = ag.insa(iki_kesit(ag, b1, b2, h))
    assert s.basarili
    assert rapor(s, "loft").durum == "tamam"
    assert s.part.volume == pytest.approx(V, rel=1e-6)


def test_k1_kapali_formlar():
    """Beklenen değerlerin kendisi kapalı formlarla tutarlı (SPEC Teori)."""
    assert math.pi * 100 * 50 == pytest.approx(15707.963, rel=1e-7)
    assert 30 / 3 * (400 + 100 + math.sqrt(400 * 100)) == pytest.approx(7000.0)
    assert kesik_koni(10, 5, 30) == pytest.approx(5497.787, rel=1e-7)


@occt
def test_k1_ruled_adlar(ag):
    """ruled: bas, son ve kesit aralığı başına yan_1..yan_k."""
    s = ag.insa(uc_daire(ag, ruled=True))
    assert s.basarili
    adlar = {r.name for r in rapor(s, "loft").adlar}
    assert {"bas", "son", "yan_1", "yan_2"} <= adlar
    assert "yan_3" not in adlar
    (bas,) = yuzler(s.part, "loft", "bas")
    (son,) = yuzler(s.part, "loft", "son")
    assert bas.area == pytest.approx(100 * math.pi, rel=REL)
    assert son.area == pytest.approx(100 * math.pi, rel=REL)
    assert bas.center().Z == pytest.approx(0.0, abs=1e-9)
    assert son.center().Z == pytest.approx(50.0, abs=1e-9)
    assert s.part.volume == pytest.approx(2 * kesik_koni(10, 15, 25), rel=REL)


# --- K2: pürüzsüz loft -----------------------------------------------------------------------------------


@occt
def test_k2_tek_yan_yuz(ag):
    s = ag.insa(uc_daire(ag, ruled=False))
    assert s.basarili
    assert len(yuzler(s.part, "loft", "yan")) == 1
    assert len(yuzler(s.part, "loft", "bas")) == 1
    assert len(yuzler(s.part, "loft", "son")) == 1
    assert len(s.part.shape.faces()) == 3  # bas, son, tek yan yüz: kesitler arasında dikiş yok


@occt
def test_k2_hacim_ruleddan_buyuk(ag):
    v_puruzsuz = ag.insa(uc_daire(ag, ruled=False)).part.volume
    v_ruled = ag.insa(uc_daire(ag, ruled=True)).part.volume
    assert v_ruled == pytest.approx(2 * kesik_koni(10, 15, 25), rel=REL)
    assert v_puruzsuz > v_ruled  # dışbükey şişkinlik


@occt
def test_k2_ara_kesit_yaricapi(ag):
    """z = 25'te kesit, ara profilden geçer: yarıçap 15 (abs 1e-3)."""
    s = ag.insa(uc_daire(ag, ruled=False))
    bolgeler = s.part.section_z(25.0, tol=1e-4)
    assert len(bolgeler) == 1
    P = np.asarray(bolgeler[0].outer, dtype=float)
    r = np.hypot(P[:, 0], P[:, 1])
    assert r.max() == pytest.approx(15.0, abs=1e-3)
    assert r.min() == pytest.approx(15.0, abs=1e-3)


# --- K7: ağaç davranışı ----------------------------------------------------------------------------------


def blok_ustu_loft(ag, bastir_p1: bool = False):
    """100 × 60 × 20 blok (min köşe orijinde) üstüne kesik koni; bağımlı yuvarlatma, bağımsız delik."""
    from geometry.agac import EdgeRef
    from geometry.part import FaceRef

    ust = ag.Profil("p1", duzlem_z(20.0), (daire(10.0, 50.0, 30.0),), bastir=bastir_p1)
    return ag.Agac(
        (
            ag.Blok("blok", 100, 60, 20),
            ust,
            ag.Profil("p2", duzlem_z(50.0), (daire(5.0, 50.0, 30.0),)),
            ag.Loft("loft", ("p1", "p2"), ruled=True, islem="ekle"),
            ag.Yuvarlatma("yuv", (EdgeRef(FaceRef("loft", "son"), FaceRef("loft", "yan_1")),), 1.0),
            ag.Delik("delik", duzlem_z(20.0), ((10.0, 10.0),), d=6.0),
        )
    )


@occt
def test_k7_profil_bastirilinca_loft_ve_bagimlilari_atlanir(ag):
    """Profil devre dışı (bastir) → loft ve bağımlısı "atlandi" (neden p1); bağımsız delik devam eder.

    Varsayım: "profil silinince" SPEC 18'deki bastırma ile sınanır; ağaçtan gerçek silme `sil` ile
    bağımlılar yüzünden reddedilir (aşağıdaki test).
    """
    s = ag.insa(blok_ustu_loft(ag, bastir_p1=True))
    assert rapor(s, "p1").durum == "bastirildi"
    for k in ("loft", "yuv"):
        assert rapor(s, k).durum == "atlandi"
        assert rapor(s, k).neden == "p1"
    assert rapor(s, "delik").durum == "tamam"
    assert s.part.volume == pytest.approx(120000 - 9 * math.pi * 20, rel=REL)


@occt
def test_k7_loft_bagimliligi(ag):
    from geometry.part import GeometryError

    a = blok_ustu_loft(ag)
    assert ag.bagimlilar(a, "p1") == ("loft", "yuv")
    assert ag.bagimlilar(a, "p2") == ("loft", "yuv")
    with pytest.raises(GeometryError):
        ag.sil(a, "p1")
    b = ag.sil(a, "p1", zincir=True)
    assert [o.kimlik for o in b.ozellikler] == ["blok", "p2", "delik"]


@occt
def test_k7_tam_agac_kurulur(ag):
    s = ag.insa(blok_ustu_loft(ag))
    assert s.basarili
    assert rapor(s, "loft").durum == "tamam"
    v = 120000 + kesik_koni(10, 5, 30) - 9 * math.pi * 20
    assert s.part.volume == pytest.approx(v, rel=1e-3)  # yuvarlatma küçük bir fark bırakır
    assert s.part.volume < 120000 + kesik_koni(10, 5, 30) - 9 * math.pi * 20


@occt
def test_k7_profil_degisince_yeniden_hesap_adlar_korunur(ag):
    onb = ag.Onbellek()
    a = iki_kesit(ag, daire(10.0), daire(5.0), 30.0)
    s1 = ag.insa(a, onb)
    assert s1.part.volume == pytest.approx(kesik_koni(10, 5, 30), rel=REL)
    b = iki_kesit(ag, daire(10.0), daire(8.0), 30.0)
    s2 = ag.insa(b, onb)
    assert "loft" in s2.yeniden_hesaplanan
    assert s2.part.volume == pytest.approx(kesik_koni(10, 8, 30), rel=REL)
    (son,) = yuzler(s2.part, "loft", "son")
    (bas,) = yuzler(s2.part, "loft", "bas")
    assert son.area == pytest.approx(64 * math.pi, rel=REL)
    assert bas.area == pytest.approx(100 * math.pi, rel=REL)
    assert son.center().Z == pytest.approx(30.0, abs=1e-9)


@occt
@pytest.mark.parametrize("ruled", [True, False])
def test_k7_json_gidis_donus(ag, ruled):
    a = uc_daire(ag, ruled=ruled)
    d = ag.to_dict(a)
    d2 = json.loads(json.dumps(d))
    b = ag.from_dict(d2)
    assert ag.to_dict(b) == d
    loft = b.ozellikler[-1]
    assert isinstance(loft, ag.Loft)
    assert loft.profiller == ("p1", "p2", "p3")
    assert loft.ruled is ruled
    assert ag.insa(b).part.volume == pytest.approx(ag.insa(a).part.volume, rel=1e-9)


# --- K8: hatalar -----------------------------------------------------------------------------------------


@occt
def test_k8_acik_profil(ag):
    a = ag.Agac(
        (
            ag.Profil("p1", TABAN, (acik_profil(),)),
            ag.Profil("p2", duzlem_z(20.0), (kare(10.0, 5.0, 5.0),)),
            ag.Loft("loft", ("p1", "p2"), ruled=True, islem="yeni"),
        )
    )
    sessiz_gecmez(ag, a, "loft")


@occt
def test_k8_tek_profil(ag):
    a = ag.Agac((ag.Profil("p1", TABAN, (daire(10.0),)), ag.Loft("loft", ("p1",), islem="yeni")))
    sessiz_gecmez(ag, a, "loft")


@occt
def test_k8_loft_profili_profil_degil(ag):
    from geometry.part import GeometryError

    a = ag.Agac(
        (
            ag.Blok("blok", 10, 10, 10),
            ag.Profil("p2", duzlem_z(20.0), (daire(3.0, 5.0, 5.0),)),
            ag.Loft("loft", ("blok", "p2"), islem="ekle"),
        )
    )
    with pytest.raises(GeometryError):
        ag.dogrula(a)


# --- K9: STEP ve ağ zinciri ------------------------------------------------------------------------------


@occt
def test_k9_step_gidis_donus(ag, tmp_path):
    from geometry.part import Part

    s = ag.insa(uc_daire(ag, ruled=False))
    yol = tmp_path / "loft.step"
    s.part.to_step(yol)
    p = Part.from_step(yol)
    assert p.volume == pytest.approx(s.part.volume, rel=1e-6)


@occt
@pytest.mark.slow
def test_k9_tet_mesh(ag):
    pytest.importorskip("gmsh")
    from core.model import Material
    from mesh import tet_mesh

    s = ag.insa(uc_daire(ag, ruled=False))
    model = tet_mesh(s.part, 4.0, Material("celik", E=210000.0, nu=0.3))
    assert len(model.elements) > 0
    assert len(model.nodes) > 0
