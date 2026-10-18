"""SPEC 07 — fileio/step_montaj.py testleri: montaj STEP'i yazma / okuma (K7, K8). OCCT gerektirir.

Testler sadece specs/07-montaj-agaci.md'deki teori ve arayüzden yazıldı; fileio/step_montaj.py gövdesi
okunmadı. STEP AP214 montaj yapısı: her parça kimliği ve alt montaj tanımı bir PRODUCT (kök dahil),
her ağaç düğümü bir NEXT_ASSEMBLY_USAGE_OCCURRENCE. OCCT gerçel sayıları 13 anlamlı basamakla yazar;
|t| ≤ 1000 mm için dünya dönüşümleri atol 1e-9.

`Node` main'e arayüz PR'ıyla gelene kadar testler "uygulanmamış" (NotImplementedError) sayılır.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

bd = pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from assy.bom import bom  # noqa: E402
from assy.model import AssyError, rot_x, rot_z, transform  # noqa: E402
from assy.tree import walk  # noqa: E402
from fileio.step_montaj import read_step, write_step  # noqa: E402
from geometry.part import GeometryError, Part  # noqa: E402


def _uygulanmamis(*_a, **_k):
    raise NotImplementedError("assy.model.Node henüz yok (SPEC 07 arayüz PR'ı)")


try:
    from assy.model import Node
except ImportError:  # arayüz PR'ı gelene kadar testler "uygulanmamış" sayılır
    Node = _uygulanmamis

pytestmark = pytest.mark.occt

TOL_T = 1e-9


def parcalar() -> dict[str, Part]:
    return {
        "govde": Part(bd.Box(100.0, 60.0, 20.0), name="govde"),
        "plaka": Part(bd.Box(40.0, 40.0, 5.0), name="plaka"),
        "vida": Part(bd.Cylinder(3.0, 20.0), name="vida"),
        "kullanilmayan": Part(bd.Box(1.0, 2.0, 3.0), name="kullanilmayan"),  # yok sayılmalı
    }


def alt(ad: str, T: np.ndarray) -> Node:
    return Node(
        ad,
        T=T,
        ref="alt",
        children=[
            Node("plaka", T=transform(None, (0.0, 0.0, 2.5)), part="plaka"),
            Node("vida_1", T=transform(rot_x(180), (15.0, 15.0, 10.0)), part="vida"),
            Node("vida_2", T=transform(rot_x(180), (-15.0, 15.0, 10.0)), part="vida"),
        ],
    )


def ornek_agac(T_kok: np.ndarray | None = None) -> Node:
    """3 seviyeli, dönmeli, paylaşımlı alt montajlı ağaç. Farklı parça 3, farklı alt montaj tanımı 1."""
    return Node(
        "montaj",
        T=np.eye(4) if T_kok is None else T_kok,
        children=[
            Node("govde", T=transform(rot_z(30.0), (0.0, 0.0, -10.0)), part="govde"),
            alt("alt_a", transform(rot_z(37.0), (120.5, -40.25, 10.0))),
            alt("alt_b", transform(rot_x(-63.0) @ rot_z(12.0), (-250.0, 300.125, 75.5))),
        ],
    )


def dunyalar(root: Node) -> dict[str, tuple[Node, np.ndarray]]:
    return {y: (n, T) for y, n, T in walk(root)}


def product_sayisi(path) -> int:
    metin = path.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"=\s*PRODUCT\s*\(", metin))


# ---------------------------------------------------------------- K7 gidiş-dönüş


def gidis_donus(tmp_path):
    """Örnek ağacı yazıp okur. Fixture değil: kod yokken NotImplementedError testin içinde düşsün."""
    root = ornek_agac()
    p = parcalar()
    yol = tmp_path / "montaj.step"
    write_step(yol, root, p)
    return root, p, yol, read_step(yol)


def test_k7_yollar_adlar_parcalar_tanimlar(tmp_path):
    root, _, _, (geri, _) = gidis_donus(tmp_path)
    assert geri.name == "montaj"
    once, sonra = dunyalar(root), dunyalar(geri)
    assert list(sonra) == list(once)
    for y, (n, _) in once.items():
        m = sonra[y][0]
        assert m.name == n.name
        assert m.part == n.part
        if n.part is None:
            assert m.definition == n.definition  # alt montaj tanımı ('alt')


def test_k7_kok_birim(tmp_path):
    _, _, _, (geri, _) = gidis_donus(tmp_path)
    np.testing.assert_allclose(geri.T, np.eye(4), rtol=0, atol=TOL_T)


def test_k7_dunya_donusumleri(tmp_path):
    root, _, _, (geri, _) = gidis_donus(tmp_path)
    sonra = dunyalar(geri)
    for y, (_, T) in dunyalar(root).items():
        np.testing.assert_allclose(sonra[y][1], T, rtol=0, atol=TOL_T, err_msg=y)


def test_k7_parcalar_ve_hacimler(tmp_path):
    _, p, _, (_, geri_p) = gidis_donus(tmp_path)
    assert set(geri_p) == {"govde", "plaka", "vida"}
    for kimlik, parca in geri_p.items():
        assert isinstance(parca, Part)
        assert parca.name == kimlik
        assert parca.volume == pytest.approx(p[kimlik].volume, rel=1e-6)


def test_k7_parca_kendi_koordinatinda(tmp_path):
    """parts[kimlik] ürünün kendi koordinatındaki şekildir: ağırlık merkezi yazılan parçayla aynı."""
    _, p, _, (_, geri_p) = gidis_donus(tmp_path)
    for kimlik, parca in geri_p.items():
        np.testing.assert_allclose(parca.center_of_mass, p[kimlik].center_of_mass, rtol=0, atol=1e-6)


def test_k7_bom_ayni(tmp_path):
    root, _, _, (geri, _) = gidis_donus(tmp_path)
    assert bom(geri) == bom(root)
    assert bom(geri, flat=False) == bom(root, flat=False)


def test_k7_product_sayisi(tmp_path):
    _, _, yol, _ = gidis_donus(tmp_path)
    assert product_sayisi(yol) == 3 + 1 + 1  # parça + alt montaj tanımı + kök


def test_k7_gidis_donus_tekrarlanabilir(tmp_path):
    """Okunan ağaç tekrar yazılıp okununca aynı yapı ve dünya dönüşümleri."""
    _, _, _, (geri, geri_p) = gidis_donus(tmp_path)
    yol2 = tmp_path / "montaj2.step"
    write_step(yol2, geri, geri_p)
    geri2, _ = read_step(yol2)
    a, b = dunyalar(geri), dunyalar(geri2)
    assert list(a) == list(b)
    for y in a:
        np.testing.assert_allclose(b[y][1], a[y][1], rtol=0, atol=TOL_T)


# ---------------------------------------------------------------- K8 kenar durumları


def test_k8_kokun_T_si_birim_degil(tmp_path):
    T_kok = transform(rot_z(30.0) @ rot_x(20.0), (10.0, 20.0, 30.0))
    root = ornek_agac(T_kok)
    yol = tmp_path / "donmus_kok.step"
    write_step(yol, root, parcalar())
    geri, _ = read_step(yol)
    np.testing.assert_allclose(geri.T, np.eye(4), rtol=0, atol=TOL_T)
    sonra = dunyalar(geri)
    for y, (_, T) in dunyalar(root).items():
        if y:  # kök hariç her düğümün dünya konumu korunur
            np.testing.assert_allclose(sonra[y][1], T, rtol=0, atol=TOL_T, err_msg=y)


def test_k8_tek_parca_step(tmp_path):
    a, b, c = 10.0, 20.0, 30.0
    yol = tmp_path / "tek_blok.step"
    Part(bd.Box(a, b, c), name="blok").to_step(yol)
    root, p = read_step(yol)
    assert root.name == "tek_blok"
    np.testing.assert_allclose(root.T, np.eye(4), rtol=0, atol=TOL_T)
    assert len(root.children) == 1
    yaprak = root.children[0]
    assert yaprak.part is not None and yaprak.children == []
    assert yaprak.name == yaprak.part
    np.testing.assert_allclose(yaprak.T, np.eye(4), rtol=0, atol=TOL_T)
    assert set(p) == {yaprak.part}
    assert p[yaprak.part].name == yaprak.part
    assert p[yaprak.part].volume == pytest.approx(a * b * c, rel=1e-6)


def test_k8_eksik_parca_hata(tmp_path):
    p = parcalar()
    del p["vida"]
    with pytest.raises(AssyError):
        write_step(tmp_path / "eksik.step", ornek_agac(), p)


def test_k8_gecersiz_agac_hata(tmp_path):
    root = ornek_agac()
    root.children.append(Node("govde", part="govde"))  # yinelenen kardeş adı
    with pytest.raises(AssyError):
        write_step(tmp_path / "gecersiz.step", root, parcalar())


def test_k8_olmayan_dosya_hata(tmp_path):
    with pytest.raises(GeometryError):
        read_step(tmp_path / "yok.step")
