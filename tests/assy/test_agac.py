"""SPEC 07 — assy/tree.py testleri: doğrulama, gezinme, dünya dönüşümü, düzleştirme ve geri dönüş (K1–K3).

Testler sadece specs/07-montaj-agaci.md'deki teori ve arayüzden yazıldı; assy/tree.py gövdesi okunmadı.
Dönüşüm zinciri (Craig, Bölüm 2.3): T_dünya(n_k) = T(n₀) · T(n₁) · … · T(n_k),  p' = R p + t.
Beklenen dünya dönüşümleri 90°'lik dönmelerle kapalı formda elle hesaplandı (her testin yorumunda):
    Rz90 (x, y, z) = (−y, x, z)        Rx90 (x, y, z) = (x, −z, y)

`Node` main'e arayüz PR'ıyla gelene kadar testler "uygulanmamış" (NotImplementedError) sayılır.
"""

from __future__ import annotations

import numpy as np
import pytest

from assy.model import Assembly, AssyError, Component, Mate, MateKind, Ref, RefKind, rot_x, rot_z, transform
from assy.solver import solve
from assy.tree import apply, flatten, validate, walk, world


def _uygulanmamis(*_a, **_k):
    raise NotImplementedError("assy.model.Node henüz yok (SPEC 07 arayüz PR'ı)")


try:
    from assy.model import Node
except ImportError:  # arayüz PR'ı gelene kadar testler "uygulanmamış" sayılır
    Node = _uygulanmamis

TOL = 1e-12

# Örnek ağacın yerel dönüşümleri
T_KOK = transform(rot_z(90), (10.0, 0.0, 0.0))
T_GOVDE = transform(None, (0.0, 0.0, -20.0))
T_ALT_A = transform(rot_z(90), (0.0, 100.0, 0.0))
T_ALT_B = transform(rot_x(90), (0.0, 0.0, 50.0))
T_PLAKA = np.eye(4)
T_VIDA_1 = transform(None, (5.0, 0.0, 0.0))
T_VIDA_2 = transform(None, (-5.0, 0.0, 0.0))

YOLLAR = [
    "",
    "govde",
    "alt_a",
    "alt_a/plaka",
    "alt_a/vida_1",
    "alt_a/vida_2",
    "alt_b",
    "alt_b/plaka",
    "alt_b/vida_1",
    "alt_b/vida_2",
]
YAPRAKLAR = [y for y in YOLLAR if y.count("/") == 1 or y == "govde"]


def alt_icerik() -> list[Node]:
    """Paylaşımlı 'alt' tanımının içeriği: her çağrıda yeni nesneler (paylaşım ref ile)."""
    return [
        Node("plaka", T=T_PLAKA.copy(), part="plaka"),
        Node("vida_1", T=T_VIDA_1.copy(), part="vida"),
        Node("vida_2", T=T_VIDA_2.copy(), part="vida"),
    ]


def ornek_agac() -> Node:
    """3 seviyeli dönmeli ağaç: kök → (govde, alt_a, alt_b) → alt montajlarda plaka + 2 vida."""
    return Node(
        "montaj",
        T=T_KOK.copy(),
        children=[
            Node("govde", T=T_GOVDE.copy(), part="govde"),
            Node("alt_a", T=T_ALT_A.copy(), ref="alt", children=alt_icerik()),
            Node("alt_b", T=T_ALT_B.copy(), ref="alt", children=alt_icerik()),
        ],
    )


def yerel_T(root: Node) -> dict[str, np.ndarray]:
    """Her yolun yerel T'si (walk'a bağlı olmadan, elle gezinerek)."""
    out = {"": root.T.copy()}

    def gez(n: Node, yol: str) -> None:
        for c in n.children:
            y = f"{yol}/{c.name}" if yol else c.name
            out[y] = c.T.copy()
            gez(c, y)

    gez(root, "")
    return out


def assert_ayni_agac(a: Node, b: Node, atol: float = TOL) -> None:
    assert b.name == a.name
    assert b.part == a.part
    assert b.definition == a.definition
    np.testing.assert_allclose(b.T, a.T, rtol=0, atol=atol)
    assert [c.name for c in b.children] == [c.name for c in a.children]
    for ca, cb in zip(a.children, b.children, strict=True):
        assert_ayni_agac(ca, cb, atol)


# ---------------------------------------------------------------- K1 validate


def test_k1_gecerli_agac_gecer_ve_degismez():
    root = ornek_agac()
    once = yerel_T(root)
    validate(root)
    sonra = yerel_T(root)
    assert once.keys() == sonra.keys()
    for y in once:
        np.testing.assert_array_equal(sonra[y], once[y])


def test_k1_yinelenen_kardes_adi_kokte():
    root = ornek_agac()
    root.children.append(Node("govde", part="govde"))
    with pytest.raises(AssyError):
        validate(root)


def test_k1_yinelenen_kardes_adi_alt_montajda():
    icerik = alt_icerik() + [Node("vida_1", T=transform(None, (0.0, 9.0, 0.0)), part="vida")]
    root = Node("montaj", children=[Node("alt_a", children=icerik)])
    with pytest.raises(AssyError):
        validate(root)


def test_k1_cocuksuz_alt_montaj():
    root = ornek_agac()
    root.children.append(Node("bos_grup"))
    with pytest.raises(AssyError):
        validate(root)


def test_k1_cocuksuz_kok():
    with pytest.raises(AssyError):
        validate(Node("montaj"))


def test_k1_ayni_nesne_iki_kez():
    """Paylaşım nesneyle değil ref ile yapılır: aynı Node nesnesi iki ayrı yerde hata."""
    vida = Node("vida_1", part="vida")
    root = Node(
        "montaj",
        children=[Node("grup_a", children=[vida]), Node("grup_b", children=[vida])],
    )
    with pytest.raises(AssyError):
        validate(root)


def test_k1_ayni_nesne_iki_kez_alt_montaj():
    alt = Node("alt", children=[Node("vida", part="vida")])
    root = Node("montaj", children=[Node("ust_a", children=[alt]), Node("ust_b", children=[alt])])
    with pytest.raises(AssyError):
        validate(root)


def _ayrisan(degistir) -> Node:
    """alt_b'nin içeriği 'degistir' ile bozulmuş örnek ağaç (alt_a ile aynı tanım adı 'alt')."""
    root = ornek_agac()
    degistir(root.children[2].children)
    return root


@pytest.mark.parametrize(
    "degistir",
    [
        lambda ch: setattr(ch[1], "name", "vida_9"),  # ad farklı
        lambda ch: setattr(ch[0], "part", "plaka_kalin"),  # parça kimliği farklı
        lambda ch: setattr(ch[1], "T", transform(None, (5.0, 1e-6, 0.0))),  # T farklı (> 1e-9)
        lambda ch: ch.pop(),  # çocuk sayısı farklı
        lambda ch: ch.append(Node("pul", part="pul")),  # fazla çocuk
    ],
    ids=["ad", "parca", "T", "eksik_cocuk", "fazla_cocuk"],
)
def test_k1_ayni_tanimli_alt_montajlarin_icerigi_farkli(degistir):
    with pytest.raises(AssyError):
        validate(_ayrisan(degistir))


def test_k1_ayni_tanimli_ic_alt_montaj_tanimi_farkli():
    """İç içe: alt montajın içindeki alt montajların tanımı farklı → üst tanımlar ayrışır."""

    def ust(ad: str, ic_ref: str) -> Node:
        return Node(
            ad, ref="ust", children=[Node("baglanti", ref=ic_ref, children=[Node("pul", part="pul")])]
        )

    root = Node("montaj", children=[ust("u1", "bag_a"), ust("u2", "bag_b")])
    with pytest.raises(AssyError):
        validate(root)


def test_k1_T_farki_tolerans_icinde_gecer():
    """İçerik karşılaştırması T için atol 1e-9: 1e-12 kadar fark aynı tanım sayılır."""
    root = _ayrisan(lambda ch: setattr(ch[1], "T", transform(None, (5.0 + 1e-12, 0.0, 0.0))))
    validate(root)


def test_k1_parca_kimligi_ve_alt_montaj_tanimi_ayni_ad():
    root = ornek_agac()
    root.children.append(Node("tek", part="alt"))  # 'alt' zaten alt montaj tanımı
    with pytest.raises(AssyError):
        validate(root)


def test_k1_parca_kimligi_ve_ref_siz_alt_montaj_adi_ayni():
    root = Node(
        "montaj",
        children=[Node("grup", children=[Node("pim", part="pim")]), Node("x", part="grup")],
    )
    with pytest.raises(AssyError):
        validate(root)


def test_k1_parca_kimligi_kok_tanimiyla_ayni():
    root = ornek_agac()
    root.children.append(Node("kopya", part="montaj"))
    with pytest.raises(AssyError):
        validate(root)


# ---------------------------------------------------------------- K2 walk / world


def test_k2_walk_yol_bicimi_ve_sirasi():
    root = ornek_agac()
    sonuc = list(walk(root))
    assert [y for y, _, _ in sonuc] == YOLLAR
    for y, n, T in sonuc:
        assert n.name == (root.name if y == "" else y.split("/")[-1])
        assert T.shape == (4, 4)


def test_k2_kokun_T_si_zincirde():
    root = ornek_agac()
    y, n, T = next(iter(walk(root)))
    assert y == "" and n.name == "montaj"
    np.testing.assert_allclose(T, T_KOK, rtol=0, atol=TOL)
    np.testing.assert_allclose(world(root, ""), T_KOK, rtol=0, atol=TOL)


def test_k2_govde_dunya():
    # T_KOK · T_GOVDE: R = Rz90, t = Rz90 (0, 0, −20) + (10, 0, 0) = (10, 0, −20)
    beklenen = transform(rot_z(90), (10.0, 0.0, -20.0))
    np.testing.assert_allclose(world(ornek_agac(), "govde"), beklenen, rtol=0, atol=TOL)


def test_k2_alt_a_vida_1_dunya_ve_nokta():
    """T_KOK · T_ALT_A · T_VIDA_1: R = Rz90 Rz90 = Rz180.
    t: (5, 0, 0) → Rz90 → (0, 5, 0) + (0, 100, 0) = (0, 105, 0)
       → Rz90 → (−105, 0, 0) + (10, 0, 0) = (−95, 0, 0).
    Vida üzerindeki yerel nokta p = (1, 0, 0): p' = Rz180 p + t = (−96, 0, 0)."""
    root = ornek_agac()
    beklenen = np.array(
        [[-1.0, 0.0, 0.0, -95.0], [0.0, -1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    )
    T = world(root, "alt_a/vida_1")
    np.testing.assert_allclose(T, beklenen, rtol=0, atol=TOL)
    p = T @ np.array([1.0, 0.0, 0.0, 1.0])
    np.testing.assert_allclose(p[:3], [-96.0, 0.0, 0.0], rtol=0, atol=TOL)


def test_k2_alt_b_vida_1_dunya_ve_nokta():
    """T_KOK · T_ALT_B · T_VIDA_1: R = Rz90 Rx90 = [[0,0,1],[1,0,0],[0,1,0]].
    t: (5, 0, 0) → Rx90 → (5, 0, 0) + (0, 0, 50) = (5, 0, 50) → Rz90 → (0, 5, 50) + (10, 0, 0) = (10, 5, 50).
    Yerel p = (0, 0, 1): R p = (1, 0, 0) → p' = (11, 5, 50)."""
    root = ornek_agac()
    beklenen = np.array(
        [[0.0, 0.0, 1.0, 10.0], [1.0, 0.0, 0.0, 5.0], [0.0, 1.0, 0.0, 50.0], [0.0, 0.0, 0.0, 1.0]]
    )
    T = world(root, "alt_b/vida_1")
    np.testing.assert_allclose(T, beklenen, rtol=0, atol=TOL)
    p = T @ np.array([0.0, 0.0, 1.0, 1.0])
    np.testing.assert_allclose(p[:3], [11.0, 5.0, 50.0], rtol=0, atol=TOL)


def test_k2_alt_montaj_dugumu_dunya():
    # T_KOK · T_ALT_B: R = Rz90 Rx90, t = Rz90 (0, 0, 50) + (10, 0, 0) = (10, 0, 50)
    beklenen = transform(rot_z(90) @ rot_x(90), (10.0, 0.0, 50.0))
    np.testing.assert_allclose(world(ornek_agac(), "alt_b"), beklenen, rtol=0, atol=TOL)


def test_k2_walk_ve_world_ayni_dunya():
    root = ornek_agac()
    for y, _, T in walk(root):
        np.testing.assert_allclose(world(root, y), T, rtol=0, atol=TOL)


def test_k2_genel_acilarla_zincir_carpimi():
    """Genel açı (30°, −50°) ile zincir: T_dünya = T0 · T1 · T2 matris çarpımı."""
    T0 = transform(rot_z(30.0), (1.0, 2.0, 3.0))
    T1 = transform(rot_x(-50.0), (0.0, 40.0, -7.0))
    T2 = transform(rot_z(12.5) @ rot_x(80.0), (3.0, 0.0, 1.0))
    root = Node("k", T=T0, children=[Node("a", T=T1, children=[Node("b", T=T2, part="p")])])
    np.testing.assert_allclose(world(root, "a/b"), T0 @ T1 @ T2, rtol=0, atol=TOL)


@pytest.mark.parametrize("yol", ["alt_c", "alt_a/yok", "govde/x", "alt_a/vida_1/x", "/govde", "montaj"])
def test_k2_bilinmeyen_yol_hata(yol):
    with pytest.raises(AssyError):
        world(ornek_agac(), yol)


# ---------------------------------------------------------------- K3 flatten


def test_k3_flatten_bilesenler():
    root = ornek_agac()
    assy = flatten(root)
    assert isinstance(assy, Assembly)
    assert assy.name == "montaj"
    assert assy.mates == []
    assert [c.name for c in assy.components] == YAPRAKLAR
    parcalar = {"govde": "govde", "plaka": "plaka", "vida_1": "vida", "vida_2": "vida"}
    for c in assy.components:
        assert c.part == parcalar[c.name.split("/")[-1]]
        assert c.fixed is False
        np.testing.assert_allclose(c.T, world(root, c.name), rtol=0, atol=TOL)


def test_k3_flatten_sabit():
    assy = flatten(ornek_agac(), fixed=["govde", "alt_b/plaka"])
    assert {c.name for c in assy.components if c.fixed} == {"govde", "alt_b/plaka"}


@pytest.mark.parametrize("fixed", [["yok"], ["alt_a"], [""], ["govde", "alt_a/vida_9"]])
def test_k3_flatten_sabit_yaprak_degil_hata(fixed):
    with pytest.raises(AssyError):
        flatten(ornek_agac(), fixed=fixed)


# ---------------------------------------------------------------- K3 apply


def test_k3_apply_flatten_agaci_degistirmez():
    root = ornek_agac()
    yeni = apply(root, flatten(root))
    assert yeni is not root
    assert_ayni_agac(root, yeni, atol=TOL)


def test_k3_apply_kok_seviyesindeki_yapragi_tasir():
    root = ornek_agac()
    once = yerel_T(root)
    assy = flatten(root)
    T_yeni = transform(rot_z(30.0) @ rot_x(15.0), (7.0, -3.0, 12.0))
    assy.component("govde").T = T_yeni
    yeni = apply(root, assy)

    np.testing.assert_allclose(world(yeni, "govde"), T_yeni, rtol=0, atol=TOL)
    yeni_yerel = yerel_T(yeni)
    for y, T in once.items():
        if y != "govde":  # kardeşler, ebeveyn ve diğer yapraklar aynı
            np.testing.assert_allclose(yeni_yerel[y], T, rtol=0, atol=TOL)
    # verilen ağaç değişmedi
    for y, T in yerel_T(root).items():
        np.testing.assert_array_equal(T, once[y])


def test_k3_apply_paylasimli_tanimda_tutarli_tasima():
    """alt_a/vida_1 ve alt_b/vida_1 aynı yeni yerel T'ye taşınınca tanım ayrışmaz; alt montaj T'leri aynı."""
    root = ornek_agac()
    once = yerel_T(root)
    T_vida_yeni = transform(rot_x(45.0), (6.0, 1.0, -2.0))
    assy = flatten(root)
    for alt in ("alt_a", "alt_b"):
        assy.component(f"{alt}/vida_1").T = world(root, alt) @ T_vida_yeni
    yeni = apply(root, assy)

    yeni_yerel = yerel_T(yeni)
    for alt in ("alt_a", "alt_b"):
        np.testing.assert_allclose(yeni_yerel[f"{alt}/vida_1"], T_vida_yeni, rtol=0, atol=TOL)
        np.testing.assert_allclose(world(yeni, f"{alt}/vida_1"), assy.component(f"{alt}/vida_1").T, atol=TOL)
    for y, T in once.items():
        if not y.endswith("/vida_1"):
            np.testing.assert_allclose(yeni_yerel[y], T, rtol=0, atol=TOL)
    validate(yeni)


def test_k3_apply_paylasimli_tanim_ayrisirsa_hata():
    root = ornek_agac()
    assy = flatten(root)
    assy.component("alt_a/vida_1").T = transform(None, (0.0, 0.0, 99.0))  # sadece alt_a'da
    with pytest.raises(AssyError):
        apply(root, assy)


def test_k3_apply_eksik_bilesen_hata():
    root = ornek_agac()
    assy = flatten(root)
    assy.components = [c for c in assy.components if c.name != "alt_b/vida_2"]
    with pytest.raises(AssyError):
        apply(root, assy)


def test_k3_apply_fazla_bilesen_hata():
    root = ornek_agac()
    assy = flatten(root)
    assy.components.append(Component(name="yabanci", part="vida"))
    with pytest.raises(AssyError):
        apply(root, assy)


def test_k3_apply_ad_uyusmazligi_hata():
    root = ornek_agac()
    assy = flatten(root)
    assy.components[0].name = "Govde"
    with pytest.raises(AssyError):
        apply(root, assy)


# ---------------------------------------------------------------- K3 SPEC 08 ile uçtan uca


def test_k3_cozucu_ile_uctan_uca():
    """Kök dönmüş, pim bir alt montajın içinde. Kısıtlar: pim alt yüzü taban üst yüzünde (yüz yüze),
    pim ekseni taban deliğinin ekseninde. Çözülen düz montaj ağaca geri yazılınca yaprakların dünya
    konumu çözümle 1e-9 mm; alt montajın ve kökün T'si değişmez."""
    root = Node(
        "montaj",
        T=transform(rot_z(30.0), (5.0, 5.0, 0.0)),
        children=[
            Node("taban", part="taban"),
            Node(
                "grup",
                T=transform(rot_x(10.0), (18.0, 3.0, 12.0)),
                children=[Node("pim", T=transform(None, (1.0, -2.0, 0.0)), part="pim")],
            ),
        ],
    )
    assy = flatten(root, fixed=["taban"])
    assy.mates = [
        Mate(
            MateKind.COINCIDENT,
            Ref("taban", RefKind.PLANE, (0.0, 0.0, 10.0), (0.0, 0.0, 1.0)),
            Ref("grup/pim", RefKind.PLANE, (0.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
        ),
        Mate(
            MateKind.CONCENTRIC,
            Ref("taban", RefKind.AXIS, (20.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            Ref("grup/pim", RefKind.AXIS, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        ),
    ]
    sonuc = solve(assy)
    sonuc.apply(assy)
    yeni = apply(root, assy)

    for c in assy.components:
        np.testing.assert_allclose(world(yeni, c.name), c.T, rtol=0, atol=1e-9)
    # pim dünyada: alt yüz merkezi taban deliği ekseninde, taban üst yüzünde
    T_taban = world(yeni, "taban")
    T_pim = world(yeni, "grup/pim")
    np.testing.assert_allclose(T_pim[:3, 3], T_taban[:3, :3] @ [20.0, 0.0, 10.0] + T_taban[:3, 3], atol=1e-9)
    np.testing.assert_allclose(T_pim[:3, 2], T_taban[:3, 2], atol=1e-9)
    yeni_yerel, eski_yerel = yerel_T(yeni), yerel_T(root)
    for y in ("", "taban", "grup"):
        np.testing.assert_allclose(yeni_yerel[y], eski_yerel[y], rtol=0, atol=TOL)
