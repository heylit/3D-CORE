"""SPEC 10 — K13 montaj köprüsü: `from_assembly`, `to_assembly` (sahte parçalar, OCCT'siz).

Testler sadece SPEC 10 metninden yazıldı; `cam/baglama.py` uygulama kodu okunmadı.
Teori ("Çerçeveler", "Montajdan CAM'e"): yaprağın dünya dönüşümü T_w = T(n₀)·…·T(n_k) (kök dahil),
iş koordinatı W (düğüm yolu → o düğümün dünya dönüşümü, Frame → [[R, origin], [0, 1]]); yaprak WCS'de W⁻¹·T_w.
Ham malzeme: parçanın yerel bbox'ının 8 köşesi T_p ile taşınır, eksen başına min/max, ± margin.
Yol biçimi SPEC 07 `walk` ile aynı: kökten sonraki adlar '/' ile. Beklenen dönüşümler bu testte numpy ile
bağımsız hesaplanır; tolerans 1e-12.
"""

from __future__ import annotations

import numpy as np
import pytest

from assy.model import Node
from cam.model import CamError, Setup, Stock, Wcs
from tests.cam.baglama_ara import (
    AssemblySetup,
    Fixture,
    envelope,
    from_assembly,
    make_fixture,
    to_assembly,
    vise_for,
)
from tests.cam.baglama_ref import STOK, T4, VISE_GRIP, VISE_OLCU, Rz, frame

ATOL = 1e-12


class SahteParca:
    """OCCT'siz parça: yalnız name ve bbox (geometry.part.Part ile aynı biçim: (min, max) özniteliği)."""

    def __init__(self, name: str, lo, hi) -> None:
        self.name = name
        self.bbox = (np.array(lo, dtype=float), np.array(hi, dtype=float))


def T(R=None, t=(0.0, 0.0, 0.0)) -> np.ndarray:
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = np.array(R)
    M[:3, 3] = t
    return M


T_TABLA = T(Rz(90), (200.0, 0.0, 10.0))  # alt montaj: R_z(90°) + öteleme
T_IS = T(None, (100.0, 50.0, 0.0))
T_MENGENE = T(None, (140.0, 75.0, -5.0))
T_P1 = T(Rz(180), (60.0, 140.0, 30.0))
T_P2 = T(Rz(-90), (180.0, 30.0, 30.0))

PARTS = {
    "blok": SahteParca("blok", (0, 0, 0), (80, 50, 30)),
    "mengene_p": SahteParca("mengene_p", (-50, -45, -40), (50, 105, 15)),
    "pabuc_p": SahteParca("pabuc_p", (-80, -10, -30), (0, 10, 27)),
}
FIKSTURLER = ["tabla/mengene", "tabla/p1", "tabla/p2"]


def agac() -> Node:
    # iki seviye: kök → tabla (alt montaj) → iş parçası, mengene, iki pabuç
    return Node(
        "kok",
        children=[
            Node(
                "tabla",
                T=T_TABLA,
                children=[
                    Node("is", T=T_IS, part="blok"),
                    Node("mengene", T=T_MENGENE, part="mengene_p"),
                    Node("p1", T=T_P1, part="pabuc_p"),
                    Node("p2", T=T_P2, part="pabuc_p"),
                ],
            )
        ],
    )


T_W = {
    "tabla/is": T_TABLA @ T_IS,
    "tabla/mengene": T_TABLA @ T_MENGENE,
    "tabla/p1": T_TABLA @ T_P1,
    "tabla/p2": T_TABLA @ T_P2,
}


def kose_kutusu(Tp: np.ndarray, lo, hi, margin=(0.0, 0.0, 0.0)) -> np.ndarray:
    K = np.array([[x, y, z, 1.0] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    P = (Tp @ K.T).T[:, :3]
    m = np.asarray(margin, dtype=float)
    return np.concatenate([P.min(axis=0) - m, P.max(axis=0) + m])


def stok_degerleri(s: Stock) -> np.ndarray:
    return np.array([s.xmin, s.ymin, s.zmin, s.xmax, s.ymax, s.zmax])


def frame_matrisi(fr) -> np.ndarray:
    return T4(fr)


def denetle(job: AssemblySetup, W: np.ndarray, margin=(0.0, 0.0, 0.0)) -> None:
    Wi = np.linalg.inv(W)
    Tp = Wi @ T_W["tabla/is"]
    assert job.workpiece == "tabla/is"
    assert job.part == "blok"
    np.testing.assert_allclose(job.T_part, Tp, atol=ATOL, rtol=0)
    assert isinstance(job.setup, Setup)
    np.testing.assert_allclose(
        stok_degerleri(job.setup.stock), kose_kutusu(Tp, *PARTS["blok"].bbox, margin), atol=ATOL, rtol=0
    )
    assert [f.name for f in job.fixtures] == FIKSTURLER
    assert [f.part_ref for f in job.fixtures] == ["mengene_p", "pabuc_p", "pabuc_p"]
    for fx in job.fixtures:
        assert isinstance(fx, Fixture)
        assert fx.kind == "ozel"
        assert fx.params == ()
        np.testing.assert_allclose(frame_matrisi(fx.frame), Wi @ T_W[fx.name], atol=ATOL, rtol=0)
    # Setup.fixtures: her bağlamanın WCS zarfı ("ozel" → tek kutu), sırasıyla
    zarf = [b for fx in job.fixtures for b in envelope(fx, PARTS)]
    assert len(job.setup.fixtures) == len(zarf) == 3
    for a, b in zip(job.setup.fixtures, zarf, strict=True):
        np.testing.assert_allclose(stok_degerleri(a), stok_degerleri(b), atol=1e-9, rtol=0)


# ---------------------------------------------------------------- dönüşümler


def test_k13_wcs_yaprak_yolu():
    job = from_assembly(agac(), PARTS, "tabla/is", "tabla/is", FIKSTURLER)
    assert isinstance(job, AssemblySetup)
    W = T_W["tabla/is"]
    denetle(job, W)
    # iş parçası yaprağı WCS ise T_p = I ve ham malzeme parçanın bbox'ı
    np.testing.assert_allclose(job.T_part, np.eye(4), atol=ATOL, rtol=0)
    np.testing.assert_allclose(stok_degerleri(job.setup.stock), [0, 0, 0, 80, 50, 30], atol=ATOL, rtol=0)


def test_k13_wcs_alt_montaj_yolu():
    job = from_assembly(agac(), PARTS, "tabla/is", "tabla", FIKSTURLER)
    denetle(job, T_TABLA)


def test_k13_wcs_frame_dondurulmus_kose_kutusu():
    # Frame (R_z(30°)): iş parçası WCS'de dönmüş → ham malzeme döndürülmüş köşelerin kutusu (temkinli)
    fr = frame((10.0, 20.0, 5.0), Rz(30))
    job = from_assembly(agac(), PARTS, "tabla/is", fr, FIKSTURLER, margin=2.0)
    denetle(job, T4(fr), margin=(2.0, 2.0, 2.0))


def test_k13_margin_demet():
    job = from_assembly(agac(), PARTS, "tabla/is", "tabla/is", FIKSTURLER, margin=(1.0, 2.0, 3.0))
    np.testing.assert_allclose(stok_degerleri(job.setup.stock), [-1, -2, -3, 81, 52, 33], atol=ATOL, rtol=0)


def test_k13_setup_adi_ve_wcs():
    job = from_assembly(
        agac(), PARTS, "tabla/is", "tabla/is", FIKSTURLER, name="op10", code="G55", origin=(1.0, 2.0, 3.0)
    )
    assert job.setup.name == "op10"
    assert job.setup.wcs == Wcs("G55", (1.0, 2.0, 3.0))


def test_k13_kinds_kutuphane_tanimi():
    # kütüphane mengenesi: kind ve params tanımdan, frame montajdan
    v, fr_lib = vise_for(STOK, VISE_GRIP, "x", **VISE_OLCU)
    lib = make_fixture("katalog_mengene", v, fr_lib)
    job = from_assembly(agac(), PARTS, "tabla/is", "tabla/is", FIKSTURLER, kinds={"tabla/mengene": lib})
    fx = job.fixtures[0]
    assert fx.name == "tabla/mengene"
    assert fx.part_ref == "mengene_p"
    assert fx.kind == "mengene"
    assert fx.params == lib.params
    W = T_W["tabla/is"]
    np.testing.assert_allclose(T4(fx.frame), np.linalg.inv(W) @ T_W["tabla/mengene"], atol=ATOL, rtol=0)
    # diğerleri "ozel"
    assert [f.kind for f in job.fixtures[1:]] == ["ozel", "ozel"]
    # zarf: mengenede ilkel başına (5) + iki pabuç (1 + 1)
    assert len(job.setup.fixtures) == 7


# ---------------------------------------------------------------- gidiş-dönüş


def test_k13_to_assembly_yapisi():
    job = from_assembly(agac(), PARTS, "tabla/is", "tabla/is", FIKSTURLER)
    kok = to_assembly(job)
    assert isinstance(kok, Node)
    assert kok.name == "baglama"
    np.testing.assert_array_equal(kok.T, np.eye(4))
    adlar = {c.name: c for c in kok.children}
    # yoldaki '/' → '__'
    assert set(adlar) == {"is_parcasi", "tabla__mengene", "tabla__p1", "tabla__p2"}
    assert adlar["is_parcasi"].part == "blok"
    np.testing.assert_allclose(adlar["is_parcasi"].T, job.T_part, atol=ATOL, rtol=0)
    for fx in job.fixtures:
        yaprak = adlar[fx.name.replace("/", "__")]
        assert yaprak.part == fx.part_ref
        np.testing.assert_allclose(yaprak.T, T4(fx.frame), atol=ATOL, rtol=0)
    assert to_assembly(job, name="kurulum_2").name == "kurulum_2"


def test_k13_gidis_donus():
    fr = frame((10.0, 20.0, 5.0), Rz(30))
    job = from_assembly(agac(), PARTS, "tabla/is", fr, FIKSTURLER, margin=1.5)
    kok = to_assembly(job)
    yeni = ["tabla__mengene", "tabla__p1", "tabla__p2"]
    job2 = from_assembly(kok, PARTS, "is_parcasi", frame(), yeni, margin=1.5)
    np.testing.assert_allclose(job2.T_part, job.T_part, atol=ATOL, rtol=0)
    np.testing.assert_allclose(
        stok_degerleri(job2.setup.stock), stok_degerleri(job.setup.stock), atol=ATOL, rtol=0
    )
    for a, b in zip(job2.fixtures, job.fixtures, strict=True):
        np.testing.assert_allclose(T4(a.frame), T4(b.frame), atol=ATOL, rtol=0)
        assert a.part_ref == b.part_ref


# ---------------------------------------------------------------- hatalar


@pytest.mark.parametrize(
    ("workpiece", "wcs", "fixtures"),
    [
        ("tabla/yok", "tabla/is", FIKSTURLER),  # bilinmeyen iş parçası yolu
        ("tabla/is", "tabla/yok", FIKSTURLER),  # bilinmeyen wcs yolu
        ("tabla/is", "tabla/is", ["tabla/mengene", "tabla/yok"]),  # bilinmeyen bağlama yolu
        ("tabla", "tabla/is", FIKSTURLER),  # iş parçası yaprak değil
        ("tabla/is", "tabla/is", ["tabla/mengene", "tabla"]),  # bağlama yaprak değil
        ("tabla/is", "tabla/is", ["tabla/mengene", "tabla/is"]),  # iş parçası bağlama listesinde
        ("tabla/is", "tabla/is", ["tabla/p1", "tabla/p1"]),  # yinelenen yol
    ],
    ids=["is_yok", "wcs_yok", "bag_yok", "is_yaprak_degil", "bag_yaprak_degil", "is_listede", "yinelenen"],
)
def test_k13_yol_hatalari(workpiece, wcs, fixtures):
    with pytest.raises(CamError):
        from_assembly(agac(), PARTS, workpiece, wcs, fixtures)


@pytest.mark.parametrize("eksik", ["blok", "pabuc_p"])
def test_k13_parts_kimligi_yok(eksik):
    parts = {k: v for k, v in PARTS.items() if k != eksik}
    with pytest.raises(CamError):
        from_assembly(agac(), parts, "tabla/is", "tabla/is", FIKSTURLER)


@pytest.mark.parametrize("margin", [-0.1, (1.0, -1.0, 0.0)])
def test_k13_negatif_margin(margin):
    with pytest.raises(CamError):
        from_assembly(agac(), PARTS, "tabla/is", "tabla/is", FIKSTURLER, margin=margin)


def test_k13_kinds_listede_olmayan_anahtar():
    v, fr_lib = vise_for(STOK, VISE_GRIP, "x", **VISE_OLCU)
    lib = make_fixture("katalog", v, fr_lib)
    with pytest.raises(CamError):
        from_assembly(agac(), PARTS, "tabla/is", "tabla/is", ["tabla/p1"], kinds={"tabla/mengene": lib})
