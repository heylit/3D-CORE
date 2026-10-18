"""SPEC 18 K5, K6 — geometry/desen.py dönüşümleri, ağaçta doğrusal / dairesel desen ve ayna (T10–T15).

Testler SPEC 18 "Desen ve ayna" teorisinden ve kabul tablosundan yazıldı; uygulama okunmadı.
Blok B = 100 × 60 × 20 (SPEC 02: min köşe orijinde, üst yüz z = 20). Delikler UST_20 düzleminde
(uv = dünya xy, normal +Z) → üstten −Z. `Hole` kayıtları alan alan karşılaştırılır (origin 1e-9, axis birim).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.agac import (  # noqa: E402
    Agac,
    Ayna,
    Blok,
    DaireselDesen,
    Delik,
    DogrusalDesen,
    EdgeRef,
    Ekstruzyon,
    Pah,
    Profil,
    insa,
)
from geometry.desen import ayna, dairesel, dogrusal, donustur_hole  # noqa: E402
from geometry.part import GeometryError, Hole  # noqa: E402
from sketch.model import Plane  # noqa: E402
from tests.geometry.agac_ortak import (  # noqa: E402
    KONUM,
    REL,
    UST_20,
    dikdortgen,
    duzlemsel,
    rapor,
    ref,
    silindirik,
    yakin,
)

pytestmark = pytest.mark.occt

V0 = 100 * 60 * 20
X = (1.0, 0.0, 0.0)
Y = (0.0, 1.0, 0.0)
Z = (0.0, 0.0, 1.0)
X50 = Plane((50, 0, 0), (1, 0, 0), (0, 1, 0))  # x = 50 ayna düzlemi


def B() -> Blok:
    return Blok("blok", 100, 60, 20)


def uygula(T: np.ndarray, p) -> np.ndarray:
    return (T @ np.append(np.asarray(p, float), 1.0))[:3]


def originler(part) -> list[tuple[float, float, float]]:
    return sorted(tuple(np.round(h.origin, 9)) for h in part.holes)


# --- desen.py: doğrusal ---------------------------------------------------------------------------------


def test_dogrusal_sira_ve_oteleme():
    Ts = dogrusal(3, 10.0, X, n2=2, s2=5.0, e2=Y)
    assert len(Ts) == 6
    for T in Ts:
        assert T.shape == (4, 4)
        assert np.allclose(T[:3, :3], np.eye(3), atol=1e-12)
    assert np.allclose(Ts[0], np.eye(4), atol=1e-12)  # ilk eleman asıl (birim)
    beklenen = [(0, 0), (10, 0), (20, 0), (0, 5), (10, 5), (20, 5)]  # j dış, i iç
    for T, (dx, dy) in zip(Ts, beklenen, strict=True):
        assert yakin(T[:3, 3], (dx, dy, 0))


def test_dogrusal_tek_yon():
    Ts = dogrusal(4, 20.0, X)
    assert len(Ts) == 4
    assert yakin([T[0, 3] for T in Ts], [0, 20, 40, 60])


@pytest.mark.parametrize(
    "arg",
    [
        dict(n1=0, s1=10.0, e1=X),
        dict(n1=2, s1=10.0, e1=(0.0, 0.0, 0.0)),
        dict(n1=2, s1=0.0, e1=X),
        dict(n1=2, s1=10.0, e1=X, n2=0, s2=5.0, e2=Y),
        dict(n1=2, s1=10.0, e1=X, n2=2, s2=5.0, e2=(0.0, 0.0, 0.0)),
        dict(n1=2, s1=10.0, e1=X, n2=2, s2=0.0, e2=Y),
    ],
)
def test_dogrusal_hatalar(arg):
    with pytest.raises(GeometryError):
        dogrusal(**arg)


# --- desen.py: dairesel ---------------------------------------------------------------------------------


def test_dairesel_tam_tur():
    Ts = dairesel((50, 30, 0), Z, 4, 360.0)
    assert len(Ts) == 4
    assert np.allclose(Ts[0], np.eye(4), atol=1e-12)
    p = (80, 30, 7)
    beklenen = [(80, 30, 7), (50, 60, 7), (20, 30, 7), (50, 0, 7)]  # sağ el, +Z etrafında
    for T, q in zip(Ts, beklenen, strict=True):
        assert yakin(uygula(T, p), q)
        assert np.linalg.det(T[:3, :3]) == pytest.approx(1.0, abs=1e-12)


def test_dairesel_kismi_aci_n_eksi_bir():
    Ts = dairesel((0, 0, 0), Z, 4, 90.0)  # φ_k = k · 90 / 3
    for k, T in enumerate(Ts):
        phi = math.radians(30 * k)
        assert yakin(uygula(T, (10, 0, 0)), (10 * math.cos(phi), 10 * math.sin(phi), 0))


@pytest.mark.parametrize(
    ("n", "eksen_y", "aci"),
    [(0, Z, 360.0), (3, (0.0, 0.0, 0.0), 360.0), (3, Z, 0.0), (3, Z, 400.0), (3, Z, -30.0)],
)
def test_dairesel_hatalar(n, eksen_y, aci):
    with pytest.raises(GeometryError):
        dairesel((0, 0, 0), eksen_y, n, aci)


# --- desen.py: ayna ve donustur_hole ---------------------------------------------------------------------


def test_ayna_yansima():
    T = ayna((50, 0, 0), (1, 0, 0))
    assert yakin(uygula(T, (10, 5, 3)), (90, 5, 3))
    assert yakin(uygula(T, (50, 7, 1)), (50, 7, 1))  # düzlemdeki nokta yerinde
    assert np.linalg.det(T[:3, :3]) == pytest.approx(-1.0, abs=1e-12)
    assert np.allclose(T @ T, np.eye(4), atol=1e-12)


def test_ayna_egik_duzlem():
    m = np.array([1.0, 1.0, 0.0]) / math.sqrt(2)
    T = ayna((0, 0, 0), m)
    assert yakin(uygula(T, (3, 0, 5)), (0, -3, 5))


def test_ayna_sifir_normal_hata():
    with pytest.raises(GeometryError):
        ayna((0, 0, 0), (0, 0, 0))


def test_donustur_hole_ayna_axis_birim_kalir():
    h = Hole(origin=(30, 30, 20), axis=(0.6, 0.0, -0.8), d=6.0, depth=20.0, through=True)
    h2 = donustur_hole(h, ayna((50, 0, 0), (1, 0, 0)))
    assert yakin(h2.origin, (70, 30, 20))
    assert yakin(h2.axis, (-0.6, 0.0, -0.8))
    assert np.linalg.norm(h2.axis) == pytest.approx(1.0, abs=1e-12)
    assert (h2.d, h2.depth, h2.through) == (h.d, h.depth, h.through)


def test_donustur_hole_dondurme_ve_oteleme():
    h = Hole(
        origin=(80, 30, 20),
        axis=(0.6, 0.0, -0.8),
        d=8.0,
        depth=12.0,
        through=False,
        csk_d=12.0,
        csk_angle=90.0,
    )
    T = dairesel((50, 30, 0), Z, 4)[1]  # +90°
    h2 = donustur_hole(h, T)
    assert yakin(h2.origin, (50, 60, 20))
    assert yakin(h2.axis, (0.0, 0.6, -0.8))
    assert (h2.d, h2.depth, h2.through, h2.csk_d, h2.csk_angle) == (8.0, 12.0, False, 12.0, 90.0)
    h3 = donustur_hole(h, dogrusal(2, 15.0, Y)[1])
    assert yakin(h3.origin, (80, 45, 20))
    assert yakin(h3.axis, h.axis)


# --- T10–T12: ağaçta desen ------------------------------------------------------------------------------


def test_t10_dogrusal_desen_delik():
    a = Agac(
        (
            B(),
            Delik("delik", UST_20, ((10, 30),), d=6.0),
            DogrusalDesen("desen", ("delik",), X, 20.0, 4),
        )
    )
    s = insa(a)
    assert s.basarili
    assert V0 - s.part.volume == pytest.approx(4 * math.pi * 9 * 20, rel=REL)
    assert len(s.part.holes) == 4
    assert originler(s.part) == [(x, 30.0, 20.0) for x in (10.0, 30.0, 50.0, 70.0)]
    for h in s.part.holes:
        assert yakin(h.axis, (0, 0, -1))
        assert h.through and h.d == 6.0
    idx = s.part.find(ref("desen:3/delik/0/duvar"))
    assert len(idx) == 1
    f = silindirik(s.part, idx[0])
    assert f.radius == pytest.approx(3.0, rel=REL)
    assert yakin(f.origin[:2], (70, 30))
    # k = 0 asıl: kendi adını korur
    f0 = silindirik(s.part, s.part.find(ref("delik:0/duvar"))[0])
    assert yakin(f0.origin[:2], (10, 30))


def test_t11_iki_yonlu_desen():
    a = Agac(
        (
            B(),
            Delik("delik", UST_20, ((25, 15),), d=6.0),
            DogrusalDesen("desen", ("delik",), X, 25.0, 3, e2=Y, s2=30.0, n2=2),
        )
    )
    s = insa(a)
    assert s.basarili
    assert V0 - s.part.volume == pytest.approx(6 * 180 * math.pi, rel=REL)
    beklenen = sorted((x, y, 20.0) for x in (25.0, 50.0, 75.0) for y in (15.0, 45.0))
    assert originler(s.part) == beklenen
    # sıra: j dış, i iç → k = 4 ikinci satırın ortası (50, 45)
    f = silindirik(s.part, s.part.find(ref("desen:4/delik/0/duvar"))[0])
    assert yakin(f.origin[:2], (50, 45))


def test_t12_dairesel_desen():
    a = Agac(
        (
            B(),
            Delik("delik", UST_20, ((80, 30),), d=8.0),
            DaireselDesen("desen", ("delik",), (50.0, 30.0, 0.0), Z, 6),
        )
    )
    s = insa(a)
    assert s.basarili
    assert V0 - s.part.volume == pytest.approx(1920 * math.pi, rel=REL)
    assert len(s.part.holes) == 6
    beklenen = sorted(
        tuple(
            np.round(
                (50 + 30 * math.cos(math.radians(60 * k)), 30 + 30 * math.sin(math.radians(60 * k)), 20), 9
            )
        )
        for k in range(6)
    )
    assert np.allclose(originler(s.part), beklenen, atol=KONUM)
    for h in s.part.holes:
        assert np.linalg.norm(h.axis) == pytest.approx(1.0, abs=1e-12)


def test_desen_cep_kopyalari():
    """Ekstrüzyon (kes) kaynağı: 3 kopya cep, ΔV = n · ΔV₁; kopya taban adı."""
    a = Agac(
        (
            B(),
            Profil("p", UST_20, (dikdortgen(5, 20, 15, 40),)),
            Ekstruzyon("cep", "p", 5.0, islem="kes"),
            DogrusalDesen("desen", ("cep",), X, 30.0, 3),
        )
    )
    s = insa(a)
    assert s.basarili
    assert V0 - s.part.volume == pytest.approx(3 * 200 * 5, rel=REL)
    f = duzlemsel(s.part, s.part.find(ref("desen:2/cep/son"))[0])
    assert yakin(f.origin, (70, 30, 15))
    assert f.area == pytest.approx(200, rel=REL)


# --- K5 hatalar ----------------------------------------------------------------------------------------


def test_k5_parcadan_tasan_kopya_hata():
    a = Agac(
        (
            B(),
            Delik("delik", UST_20, ((10, 30),), d=6.0),
            DogrusalDesen("desen", ("delik",), X, 40.0, 4),  # x = 130 kopyası malzeme kaldırmaz
        )
    )
    s = insa(a)
    assert not s.basarili
    assert rapor(s, "desen").durum == "hata"
    assert rapor(s, "delik").durum == "tamam"
    assert V0 - s.part.volume == pytest.approx(math.pi * 9 * 20, rel=REL)  # desen uygulanmadı
    assert len(s.part.holes) == 1


@pytest.mark.parametrize("kaynak", ["pah", "blok"])
def test_k5_gecersiz_desen_kaynagi(kaynak):
    a = Agac(
        (
            B(),
            Pah("pah", (EdgeRef(ref("blok:zmax"), ref("blok:ymin")),), 2.0),
            DogrusalDesen("desen", (kaynak,), X, 20.0, 2),
        )
    )
    with pytest.raises(GeometryError):
        insa(a)


def test_k5_yeni_ekstruzyon_kaynagi_hata():
    a = Agac(
        (
            Profil("p", UST_20, (dikdortgen(0, 0, 10, 10),)),
            Ekstruzyon("e", "p", 5.0, islem="yeni"),
            DogrusalDesen("desen", ("e",), X, 20.0, 2),
        )
    )
    with pytest.raises(GeometryError):
        insa(a)


# --- T13–T15, K6: ayna -----------------------------------------------------------------------------------


def test_t13_ozellik_aynasi_cep():
    a = Agac(
        (
            B(),
            Profil("p", UST_20, (dikdortgen(10, 15, 30, 45),)),
            Ekstruzyon("cep", "p", 8.0, islem="kes"),
            Ayna("ayna", X50, ("cep",)),
        )
    )
    s = insa(a)
    assert s.basarili
    assert V0 - s.part.volume == pytest.approx(2 * 4800, rel=REL)
    f = duzlemsel(s.part, s.part.find(ref("ayna:cep/son"))[0])
    assert f.origin[2] == pytest.approx(12.0, abs=KONUM)
    assert yakin(f.origin, (80, 30, 12))
    assert f.area == pytest.approx(600, rel=REL)
    asil = duzlemsel(s.part, s.part.find(ref("cep:son"))[0])
    assert yakin(asil.origin, (20, 30, 12))
    # aynalı cebin duvarı x = 90'da (sol kenarın aynası)
    duvar = duzlemsel(s.part, s.part.find(ref("ayna:cep/yan:sol"))[0])
    assert duvar.origin[0] == pytest.approx(90.0, abs=KONUM)


def test_t14_govde_aynasi():
    a = Agac((Blok("blok", 50, 60, 20), Ayna("ayna", ref("blok:xmax"), None)))
    s = insa(a)
    assert s.basarili
    assert len(s.part.shape.solids()) == 1
    assert s.part.volume == pytest.approx(120000, rel=REL)
    lo, hi = s.part.bbox
    assert yakin(hi - lo, (100, 60, 20), tol=1e-6)
    f = duzlemsel(s.part, s.part.find(ref("ayna:govde/blok/xmin"))[0])
    assert f.origin[0] == pytest.approx(100.0, abs=KONUM)
    assert yakin(f.normal, (1, 0, 0))
    assert f.area == pytest.approx(1200, rel=REL)
    assert ref("blok:xmax") not in s.part.names  # iç yüz oldu, silindi


def test_t15_delik_aynasi_hole_kaydi():
    a = Agac(
        (
            B(),
            Delik("delik", UST_20, ((30, 30),), d=6.0),
            Ayna("ayna", X50, ("delik",)),
        )
    )
    s = insa(a)
    assert s.basarili
    assert len(s.part.holes) == 2
    assert originler(s.part) == [(30.0, 30.0, 20.0), (70.0, 30.0, 20.0)]
    for h in s.part.holes:
        assert yakin(h.axis, (0, 0, -1))
        assert h.through
    assert V0 - s.part.volume == pytest.approx(2 * math.pi * 9 * 20, rel=REL)


def test_k6_ayrik_govde_aynasi_hata():
    a = Agac((Blok("blok", 50, 60, 20), Ayna("ayna", Plane((60, 0, 0), (1, 0, 0), (0, 1, 0)), None)))
    s = insa(a)
    assert not s.basarili
    r = rapor(s, "ayna")
    assert r.durum == "hata"
    assert "ayrık katı" in r.mesaj
    assert s.part.volume == pytest.approx(60000, rel=REL)
