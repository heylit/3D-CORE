"""SPEC 09 — assy/girisim.py testleri: sınıflandırma, alt montajlar, kaba eleme, hatalar (K4–K7).

Testler sadece specs/09-girisim.md'deki teori ve arayüzden yazıldı; assy/girisim.py gövdesi okunmadı.
K4 gerçek Part (OCCT) kullanır ve `occt` işaretlidir. K5–K7 OCCT'siz: check parçayı sadece Part arayüzünden
(bbox, moved, common, distance, volume, center_of_mass) kullandığı için kesin sonuçlu sahte parçalarla:
    SahteKutu  eksen hizalı kutu (90°'nin katı dönmelerde kutu kalır); V∩ ve d kapalı formda
    SahteKure  merkezi yerel orijinden kaçık küre; yerel bbox = küreyi saran küp, böylece dönmüş parçada
               dünya AABB'si gerçek şekilden büyüktür (Teori: kutu şekli içerir)
Sınıflandırma (Teori tablosu): V∩ > tol_v → GIRISIM; d ≤ tol_d → TEMAS; tol_d < d < clearance → DAR.
Ağaç ve yollar SPEC 07: walk sırası derinlik öncelikli, yol "alt/yaprak".
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from assy.girisim import Clash, ClashKind, check, gap, world_aabb
from assy.model import AssyError, Node, rot_x, rot_y, rot_z, transform
from assy.tree import walk

# ---------- Sahte parçalar ----------


class Sayac:
    """common / distance çağrılarını parça adı çiftiyle (sırasız) kaydeder."""

    def __init__(self) -> None:
        self.cagrilar: list[tuple[str, frozenset[str]]] = []

    def kaydet(self, tur: str, a, b) -> None:
        self.cagrilar.append((tur, frozenset((a.name, b.name))))

    @property
    def ciftler(self) -> set[frozenset[str]]:
        return {c for _, c in self.cagrilar}


def _kose(lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    return np.array(
        [[(lo, hi)[i][0], (lo, hi)[j][1], (lo, hi)[k][2]] for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    )


class SahteSonuc:
    """common sonucu: sadece hacim ve ağırlık merkezi."""

    def __init__(self, volume: float, center: np.ndarray, name: str) -> None:
        self.volume = float(volume)
        self.center_of_mass = np.asarray(center, dtype=float)
        self.name = name


class SahteKutu:
    def __init__(self, lo, hi, name: str, sayac: Sayac | None = None) -> None:
        self.lo, self.hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
        self.name = name
        self.sayac = sayac if sayac is not None else Sayac()

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.lo.copy(), self.hi.copy()

    @property
    def volume(self) -> float:
        return float(np.prod(self.hi - self.lo))

    @property
    def center_of_mass(self) -> np.ndarray:
        return (self.lo + self.hi) / 2

    def moved(self, T: np.ndarray) -> SahteKutu:
        T = np.asarray(T, dtype=float)
        R, t = T[:3, :3], T[:3, 3]
        assert np.allclose(np.abs(R).sum(axis=0), 1.0), "SahteKutu sadece 90°'nin katı dönmelerle taşınır"
        k = _kose(self.lo, self.hi) @ R.T + t
        return SahteKutu(k.min(axis=0), k.max(axis=0), self.name, self.sayac)

    def common(self, other: SahteKutu, tol_v: float = 1e-6) -> SahteSonuc | None:
        self.sayac.kaydet("common", self, other)
        lo, hi = np.maximum(self.lo, other.lo), np.minimum(self.hi, other.hi)
        V = float(np.prod(np.maximum(0.0, hi - lo)))
        return None if V <= tol_v else SahteSonuc(V, (lo + hi) / 2, self.name)

    def distance(self, other: SahteKutu) -> tuple[float, np.ndarray, np.ndarray]:
        """Eksen başına: boşluk varsa yüzler, örtüşme varsa örtüşme aralığının ortası."""
        self.sayac.kaydet("distance", self, other)
        p, q = np.empty(3), np.empty(3)
        for k in range(3):
            if other.lo[k] > self.hi[k]:
                p[k], q[k] = self.hi[k], other.lo[k]
            elif self.lo[k] > other.hi[k]:
                p[k], q[k] = self.lo[k], other.hi[k]
            else:
                p[k] = q[k] = (max(self.lo[k], other.lo[k]) + min(self.hi[k], other.hi[k])) / 2
        return float(np.linalg.norm(q - p)), p, q


def _kure_kapak(r: float, h: float) -> tuple[float, float]:
    """Yüksekliği h olan küre kapağı: hacim π h² (3r − h) / 3, ağırlık merkezinin küre merkezine uzaklığı."""
    V = math.pi * h * h * (3 * r - h) / 3
    z = 3 * (2 * r - h) ** 2 / (4 * (3 * r - h))
    return V, z


class SahteKure:
    def __init__(self, c, r: float, name: str, sayac: Sayac | None = None) -> None:
        self.c, self.r = np.asarray(c, dtype=float), float(r)
        self.name = name
        self.sayac = sayac if sayac is not None else Sayac()

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.c - self.r, self.c + self.r

    @property
    def volume(self) -> float:
        return 4 / 3 * math.pi * self.r**3

    @property
    def center_of_mass(self) -> np.ndarray:
        return self.c.copy()

    def moved(self, T: np.ndarray) -> SahteKure:
        T = np.asarray(T, dtype=float)
        return SahteKure(T[:3, :3] @ self.c + T[:3, 3], self.r, self.name, self.sayac)

    def common(self, other: SahteKure, tol_v: float = 1e-6) -> SahteSonuc | None:
        self.sayac.kaydet("common", self, other)
        r1, r2 = self.r, other.r
        D = float(np.linalg.norm(other.c - self.c))
        if D >= r1 + r2:
            return None
        if D <= abs(r1 - r2):
            kucuk = self if r1 <= r2 else other
            V, c = kucuk.volume, kucuk.c
        else:
            u = (other.c - self.c) / D
            a = (D * D + r1 * r1 - r2 * r2) / (2 * D)  # kesişim düzleminin c₁'e uzaklığı
            V1, z1 = _kure_kapak(r1, r1 - a)
            V2, z2 = _kure_kapak(r2, r2 - (D - a))
            V = V1 + V2
            c = self.c + u * (V1 * z1 + V2 * (D - z2)) / V
        return None if V <= tol_v else SahteSonuc(V, c, self.name)

    def distance(self, other: SahteKure) -> tuple[float, np.ndarray, np.ndarray]:
        """Sınırlar arası: ayrıkta D − r₁ − r₂, iç içede |r₁ − r₂| − D, kesişende 0."""
        self.sayac.kaydet("distance", self, other)
        D = float(np.linalg.norm(other.c - self.c))
        u = (other.c - self.c) / D
        if D >= self.r + other.r:
            p, q = self.c + self.r * u, other.c - other.r * u
        elif D <= abs(self.r - other.r):
            s = 1.0 if self.r >= other.r else -1.0
            p, q = self.c + s * self.r * u, other.c + s * other.r * u
        else:
            p = q = self.c + u * (D * D + self.r**2 - other.r**2) / (2 * D)
        return float(np.linalg.norm(q - p)), p, q


def kutu(lo, hi, name: str, sayac: Sayac | None = None) -> SahteKutu:
    return SahteKutu(lo, hi, name, sayac)


def satirlar(sonuc: list[Clash]) -> list[tuple[str, str, ClashKind]]:
    return [(c.a, c.b, c.kind) for c in sonuc]


def tam_tarama(root: Node, parts, clearance: float, tol_v: float = 1e-6, tol_d: float = 1e-6):
    """Kaba elemesiz başvuru: walk sırasıyla her yaprak çifti, Teori tablosuyla sınıflandırılır."""
    yapraklar = [(y, parts[n.part].moved(T)) for y, n, T in walk(root) if n.part is not None]
    sonuc = []
    for i, (ya, pa) in enumerate(yapraklar):
        for yb, pb in yapraklar[i + 1 :]:
            k = pa.common(pb, tol_v)
            if k is not None and k.volume > tol_v:
                sonuc.append((ya, yb, ClashKind.GIRISIM, k.volume, 0.0))
                continue
            d, _, _ = pa.distance(pb)
            if d <= tol_d:
                sonuc.append((ya, yb, ClashKind.TEMAS, 0.0, d))
            elif d < clearance:
                sonuc.append((ya, yb, ClashKind.DAR, 0.0, d))
    return sonuc


# ---------- K4 sınıflandırma, gerçek parçalar (OCCT) ----------

R_DELIK = 5.0
L_ICICE = 20.0  # plaka kalınlığı; pim 30 mm boyunda, plakadan iki yana taşar
T_YER = transform(None, (100.0, 0.0, 0.0))


def _pim_delik(r: float):
    """40×40×20 plaka (z ∈ [−10, 10]) içinde R = 5 delik, eş eksenli r yarıçaplı pim; ikisi (100, 0, 0)'da."""
    from build123d import Box, Cylinder

    from geometry.part import Part

    plaka = Part(Box(40, 40, L_ICICE) - Cylinder(R_DELIK, 30), name="plaka")
    pim = Part(Cylinder(r, 30), name="pim")
    root = Node("montaj", children=[Node("plaka", T=T_YER, part="plaka"), Node("pim", T=T_YER, part="pim")])
    return root, {"plaka": plaka, "pim": pim}


@pytest.mark.occt
def test_pin_hole_clearance_is_dar():
    """r = 4 < R = 5: DAR, d = R − r = 1; p delik yüzeyinde (eksene R), q pim yüzeyinde (eksene r)."""
    root, parts = _pim_delik(4.0)
    sonuc = check(root, parts, clearance=2.0)
    assert satirlar(sonuc) == [("plaka", "pim", ClashKind.DAR)]
    c = sonuc[0]
    assert c.distance == pytest.approx(1.0, abs=1e-6)
    assert c.volume == 0.0 and c.center is None
    p, q = c.points
    assert float(np.hypot(p[0] - 100.0, p[1])) == pytest.approx(R_DELIK, abs=1e-6)
    assert float(np.hypot(q[0] - 100.0, q[1])) == pytest.approx(4.0, abs=1e-6)
    assert float(np.linalg.norm(q - p)) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.occt
def test_pin_hole_clearance_zero_not_reported():
    """clearance = 0 (varsayılan): dar boşluk aranmaz."""
    root, parts = _pim_delik(4.0)
    assert check(root, parts) == []


@pytest.mark.occt
def test_pin_hole_equal_radius_is_temas():
    root, parts = _pim_delik(R_DELIK)
    sonuc = check(root, parts, clearance=2.0)
    assert satirlar(sonuc) == [("plaka", "pim", ClashKind.TEMAS)]
    c = sonuc[0]
    assert c.volume == 0.0 and c.center is None
    assert c.distance == pytest.approx(0.0, abs=1e-6)
    assert c.points is not None


@pytest.mark.occt
def test_pin_hole_press_fit_is_girisim():
    """r = 5.5 > R = 5: GIRISIM, V∩ = π (r² − R²) L = π (30.25 − 25) · 20; merkez eksende, plaka ortasında."""
    r = 5.5
    root, parts = _pim_delik(r)
    sonuc = check(root, parts, clearance=2.0)
    assert satirlar(sonuc) == [("plaka", "pim", ClashKind.GIRISIM)]
    c = sonuc[0]
    assert c.volume == pytest.approx(math.pi * (r * r - R_DELIK**2) * L_ICICE, rel=1e-6)
    assert c.distance == 0.0 and c.points is None
    np.testing.assert_allclose(c.center, [100.0, 0.0, 0.0], atol=1e-6)


@pytest.mark.occt
def test_contained_part_is_girisim():
    """[2,5]×[3,7]×[1,9] bloğu [0,10]³ içinde: sınırlar arası d = 1 > 0 olsa da V∩ = 96 → GIRISIM."""
    from build123d import Box, Pos

    from geometry.part import Part

    parts = {"buyuk": Part(Pos(5, 5, 5) * Box(10, 10, 10)), "kucuk": Part(Pos(3.5, 5, 5) * Box(3, 4, 8))}
    root = Node("m", children=[Node("buyuk", part="buyuk"), Node("kucuk", part="kucuk")])
    sonuc = check(root, parts, clearance=5.0)
    assert satirlar(sonuc) == [("buyuk", "kucuk", ClashKind.GIRISIM)]
    assert sonuc[0].volume == pytest.approx(96.0, rel=1e-6)
    np.testing.assert_allclose(sonuc[0].center, [3.5, 5.0, 5.0], atol=1e-6)


@pytest.mark.occt
def test_clean_assembly_empty():
    """1 mm aralıklı üç blok, clearance = 0: boş liste."""
    from build123d import Box

    from geometry.part import Part

    parts = {"blok": Part(Box(10, 10, 10))}
    root = Node(
        "m",
        children=[Node(f"b{i}", T=transform(None, (11.0 * i, 0.0, 0.0)), part="blok") for i in range(3)],
    )
    assert check(root, parts) == []


# ---------- Sınıflandırma eşikleri (sahte kutular) ----------


def _iki_kutu(b_lo, b_hi):
    parts = {"a": kutu((0, 0, 0), (1, 1, 1), "a"), "b": kutu(b_lo, b_hi, "b")}
    root = Node("m", children=[Node("a", part="a"), Node("b", part="b")])
    return root, parts


def test_face_contact_is_temas_with_points():
    root, parts = _iki_kutu((1, 0, 0), (2, 1, 1))
    sonuc = check(root, parts, clearance=0.5)
    assert satirlar(sonuc) == [("a", "b", ClashKind.TEMAS)]
    c = sonuc[0]
    assert c.volume == 0.0 and c.center is None
    assert c.distance == pytest.approx(0.0, abs=1e-12)
    p, q = c.points
    assert p[0] == pytest.approx(1.0) and q[0] == pytest.approx(1.0)


def test_gap_below_tol_d_is_temas():
    """d = 5e-7 ≤ tol_d = 1e-6 → TEMAS, distance = d."""
    root, parts = _iki_kutu((1 + 5e-7, 0, 0), (2, 1, 1))
    sonuc = check(root, parts)
    assert satirlar(sonuc) == [("a", "b", ClashKind.TEMAS)]
    assert sonuc[0].distance == pytest.approx(5e-7, abs=1e-12)


def test_tol_d_parameter():
    """d = 0.01: tol_d = 0.05 → TEMAS, varsayılan tol_d ve clearance = 0 → boş."""
    root, parts = _iki_kutu((1.01, 0, 0), (2, 1, 1))
    assert satirlar(check(root, parts, tol_d=0.05)) == [("a", "b", ClashKind.TEMAS)]
    assert check(root, parts) == []


def test_narrow_gap_is_dar_with_world_points():
    """d = 0.3 < clearance = 0.5 → DAR; p a'nın yüzünde (x = 1), q b'nin yüzünde (x = 1.3)."""
    root, parts = _iki_kutu((1.3, 0, 0), (2, 1, 1))
    sonuc = check(root, parts, clearance=0.5)
    assert satirlar(sonuc) == [("a", "b", ClashKind.DAR)]
    c = sonuc[0]
    assert c.distance == pytest.approx(0.3, abs=1e-12)
    assert c.volume == 0.0 and c.center is None
    p, q = c.points
    assert p[0] == pytest.approx(1.0) and q[0] == pytest.approx(1.3)


def test_gap_equal_clearance_is_free():
    """d = 0.5 = clearance → serbest (d ≥ clearance)."""
    root, parts = _iki_kutu((1.5, 0, 0), (2, 1, 1))
    assert check(root, parts, clearance=0.5) == []


def test_tiny_overlap_below_tol_v_is_temas():
    """V∩ = 1e-7 · 1 · 1 ≤ tol_v = 1e-6 → GIRISIM değil; d = 0 → TEMAS."""
    root, parts = _iki_kutu((1 - 1e-7, 0, 0), (2, 1, 1))
    assert satirlar(check(root, parts)) == [("a", "b", ClashKind.TEMAS)]


def test_tol_v_parameter():
    """V∩ = 0.5: tol_v = 1 → TEMAS; varsayılan → GIRISIM, V = 0.5, merkez (0.75, 0.5, 0.5)."""
    root, parts = _iki_kutu((0.5, 0, 0), (2, 1, 1))
    assert satirlar(check(root, parts, tol_v=1.0)) == [("a", "b", ClashKind.TEMAS)]
    sonuc = check(root, parts)
    assert satirlar(sonuc) == [("a", "b", ClashKind.GIRISIM)]
    c = sonuc[0]
    assert c.volume == pytest.approx(0.5)
    assert c.distance == 0.0 and c.points is None
    np.testing.assert_allclose(c.center, [0.75, 0.5, 0.5], atol=1e-12)


def test_root_transform_applies():
    """Kökün T'si de dünya dönüşümüne girer (SPEC 07 world): merkez (0.75, 0.5, 0.5) + (0, 0, 50)."""
    _, parts = _iki_kutu((0.5, 0, 0), (2, 1, 1))
    root = Node("m", T=transform(None, (0.0, 0.0, 50.0)), children=[Node("a", part="a"), Node("b", part="b")])
    np.testing.assert_allclose(check(root, parts)[0].center, [0.75, 0.5, 50.5], atol=1e-12)


# ---------- K5 alt montajlar (sahte kutular) ----------
#
# govde (yaprak, [90,101]×[−5,1]×[−5,1])
# g1 (ref "grup", T = öteleme (100, 0, 0))    c1 [0,4]³, c2 [3,7]×[0,4]×[0,4] → iç girişim [3,4]×[0,4]×[0,4]
# g2 (ref "grup", T = Rz90 + (0, 100, 0))     aynı tanım
# Dünya: g1/c1 [100,104]×[0,4]×[0,4], g1/c2 [103,107]×…, iç kesişim V = 16, merkez (103.5, 2, 2)
#        g2: Rz90 (x, y, z) = (−y, x, z) → kesişim merkezi (3.5, 2, 2) → (−2, 3.5, 2) + (0, 100, 0)
#            = (−2, 103.5, 2)
#        govde ∩ g1/c1 = [100,101]×[0,1]×[0,1], V = 1, merkez (100.5, 0.5, 0.5)
# walk sırası: govde, g1/c1, g1/c2, g2/c1, g2/c2

T_G1 = transform(None, (100.0, 0.0, 0.0))
T_G2 = transform(rot_z(90), (0.0, 100.0, 0.0))


def _grup(name: str, T: np.ndarray) -> Node:
    return Node(name, T=T, ref="grup", children=[Node("c1", part="k1"), Node("c2", part="k2")])


def _montaj(sayac: Sayac | None = None):
    parts = {
        "govde": kutu((90, -5, -5), (101, 1, 1), "govde", sayac),
        "k1": kutu((0, 0, 0), (4, 4, 4), "k1", sayac),
        "k2": kutu((3, 0, 0), (7, 4, 4), "k2", sayac),
    }
    root = Node("montaj", children=[Node("govde", part="govde"), _grup("g1", T_G1), _grup("g2", T_G2)])
    return root, parts


BEKLENEN_TUM = [
    ("govde", "g1/c1", ClashKind.GIRISIM),
    ("g1/c1", "g1/c2", ClashKind.GIRISIM),
    ("g2/c1", "g2/c2", ClashKind.GIRISIM),
]


def test_shared_definition_each_occurrence_separate_row():
    root, parts = _montaj()
    sonuc = check(root, parts)
    assert satirlar(sonuc) == BEKLENEN_TUM
    hacim = [c.volume for c in sonuc]
    np.testing.assert_allclose(hacim, [1.0, 16.0, 16.0], rtol=1e-12)
    np.testing.assert_allclose(sonuc[0].center, [100.5, 0.5, 0.5], atol=1e-12)
    np.testing.assert_allclose(sonuc[1].center, [103.5, 2.0, 2.0], atol=1e-12)


def test_rotated_subassembly_world_center():
    """g2 Rz90 ile dönmüş: iç kesişim merkezi dünyada (−2, 103.5, 2), hacim 16."""
    root, parts = _montaj()
    c = check(root, parts)[2]
    assert (c.a, c.b) == ("g2/c1", "g2/c2")
    assert c.volume == pytest.approx(16.0, rel=1e-12)
    np.testing.assert_allclose(c.center, [-2.0, 103.5, 2.0], atol=1e-12)


def test_scope_subtree_only():
    root, parts = _montaj()
    assert satirlar(check(root, parts, scope="g1")) == [("g1/c1", "g1/c2", ClashKind.GIRISIM)]
    assert satirlar(check(root, parts, scope="g2")) == [("g2/c1", "g2/c2", ClashKind.GIRISIM)]
    assert satirlar(check(root, parts, scope="")) == BEKLENEN_TUM


def test_across_skips_inside_subassemblies():
    """across=True kökte: sadece farklı doğrudan çocuklar arası (govde – g1/c1); g1, g2 iç girişimleri yok."""
    root, parts = _montaj()
    assert satirlar(check(root, parts, across=True)) == [("govde", "g1/c1", ClashKind.GIRISIM)]


def test_across_inside_subassembly_scope():
    """across=True, scope = g1: doğrudan çocuklar c1, c2 farklı → c1 – c2 satırı."""
    root, parts = _montaj()
    assert satirlar(check(root, parts, scope="g1", across=True)) == [("g1/c1", "g1/c2", ClashKind.GIRISIM)]


def test_across_does_not_call_occt_for_inner_pairs():
    """across=True'da alt montaj içi çiftler için common / distance çağrılmaz."""
    sayac = Sayac()
    root, parts = _montaj(sayac)
    check(root, parts, across=True)
    assert frozenset(("k1", "k2")) not in sayac.ciftler


def test_ignore_pair_unordered():
    root, parts = _montaj()
    sonuc = check(root, parts, ignore=[("g1/c2", "g1/c1")])
    assert satirlar(sonuc) == [BEKLENEN_TUM[0], BEKLENEN_TUM[2]]
    sonuc = check(root, parts, ignore=[("govde", "g1/c1"), ("g2/c1", "g2/c2")])
    assert satirlar(sonuc) == [BEKLENEN_TUM[1]]


def test_ab_order_follows_walk():
    """b yaprağı ağaçta önce gelirse a odur: çocuk sırası ters çevrilince a/b de değişir."""
    parts = {"a": kutu((0, 0, 0), (1, 1, 1), "a"), "b": kutu((0.5, 0, 0), (2, 1, 1), "b")}
    root = Node("m", children=[Node("y2", part="b"), Node("y1", part="a")])
    assert satirlar(check(root, parts)) == [("y2", "y1", ClashKind.GIRISIM)]


def test_check_does_not_change_inputs():
    root, parts = _montaj()
    once = root.to_dict()
    kutular = {k: (v.lo.copy(), v.hi.copy()) for k, v in parts.items()}
    check(root, parts, clearance=1.0)
    gap(root, parts, "g1/c1", "g2/c1")
    assert root.to_dict() == once
    for k, (lo, hi) in kutular.items():
        np.testing.assert_array_equal(parts[k].lo, lo)
        np.testing.assert_array_equal(parts[k].hi, hi)


def test_returns_list_of_clash():
    root, parts = _montaj()
    sonuc = check(root, parts)
    assert isinstance(sonuc, list) and all(isinstance(c, Clash) for c in sonuc)


# ---------- gap ----------


def test_gap_world_distance():
    """g1/c1 [100,104]×[0,4]×[0,4], g2/c1 [−4,0]×[100,104]×[0,4]: x'te 100, y'de 96 boşluk.

    d = √(100² + 96²), p = (100, 4, ·), q = (0, 100, ·).
    """
    root, parts = _montaj()
    d, p, q = gap(root, parts, "g1/c1", "g2/c1")
    assert d == pytest.approx(math.hypot(100.0, 96.0), rel=1e-12)
    np.testing.assert_allclose(p[:2], [100.0, 4.0], atol=1e-12)
    np.testing.assert_allclose(q[:2], [0.0, 100.0], atol=1e-12)


def test_gap_no_broad_phase():
    """gap kaba eleme yapmaz: uzak çiftte de distance çağrılır."""
    sayac = Sayac()
    root, parts = _montaj(sayac)
    gap(root, parts, "govde", "g2/c2")
    assert frozenset(("govde", "k2")) in sayac.ciftler


# ---------- K6 kaba eleme ----------


def test_world_aabb_rotated_45():
    """[0,10]×[0,20]×[0,30], Rz45 + t = (1, 2, 3).

    x' = (x − y)/√2 ∈ [−20/√2, 10/√2], y' = (x + y)/√2 ∈ [0, 30/√2], z' = z.
    """
    s = 1 / math.sqrt(2)
    lo, hi = world_aabb(kutu((0, 0, 0), (10, 20, 30), "k"), transform(rot_z(45), (1.0, 2.0, 3.0)))
    np.testing.assert_allclose(lo, [1.0 - 20 * s, 2.0, 3.0], atol=1e-12)
    np.testing.assert_allclose(hi, [1.0 + 10 * s, 2.0 + 30 * s, 33.0], atol=1e-12)


def test_world_aabb_offset_box_rotated():
    """Orijinden kaçık kutu [2,3]×[4,6]×[0,1], Rx90 (x, y, z) = (x, −z, y): y' ∈ [−1, 0], z' ∈ [4, 6]."""
    lo, hi = world_aabb(kutu((2, 4, 0), (3, 6, 1), "k"), transform(rot_x(90)))
    np.testing.assert_allclose(lo, [2.0, -1.0, 4.0], atol=1e-12)
    np.testing.assert_allclose(hi, [3.0, 0.0, 6.0], atol=1e-12)


N_IZGARA = 10


def _izgara(sayac: Sayac):
    """10 × 10 ızgara, 4 mm küpler, adım 5 mm: kenar komşuları 1 mm, köşe komşuları √2 mm uzakta."""
    parts, cocuk = {}, []
    for i in range(N_IZGARA):
        for j in range(N_IZGARA):
            ad = f"b{i}_{j}"
            parts[ad] = kutu((0, 0, 0), (4, 4, 4), ad, sayac)
            cocuk.append(Node(ad, T=transform(None, (5.0 * i, 5.0 * j, 0.0)), part=ad))
    return Node("izgara", children=cocuk), parts


def test_grid_broad_phase_eliminates_all():
    """clearance = 0.5: en küçük kutu boşluğu 1 ≥ 0.5 → hiç common / distance çağrısı yok, boş sonuç."""
    sayac = Sayac()
    root, parts = _izgara(sayac)
    assert check(root, parts, clearance=0.5) == []
    assert sayac.cagrilar == []


def test_grid_broad_phase_edge_neighbours_only():
    """clearance = 1.2: sadece 2 · 10 · 9 = 180 kenar komşusu çağrılır, hepsi DAR (d = 1), walk sırasıyla."""
    sayac = Sayac()
    root, parts = _izgara(sayac)
    sonuc = check(root, parts, clearance=1.2)
    beklenen = []
    for i in range(N_IZGARA):
        for j in range(N_IZGARA):
            if j + 1 < N_IZGARA:
                beklenen.append((f"b{i}_{j}", f"b{i}_{j + 1}"))
            if i + 1 < N_IZGARA:
                beklenen.append((f"b{i}_{j}", f"b{i + 1}_{j}"))
    sira = {f"b{i}_{j}": N_IZGARA * i + j for i in range(N_IZGARA) for j in range(N_IZGARA)}
    beklenen.sort(key=lambda ab: (sira[ab[0]], sira[ab[1]]))
    assert len(beklenen) == 180
    assert [(c.a, c.b) for c in sonuc] == beklenen
    assert all(c.kind is ClashKind.DAR for c in sonuc)
    np.testing.assert_allclose([c.distance for c in sonuc], 1.0, atol=1e-12)
    assert sayac.ciftler == {frozenset(ab) for ab in beklenen}


def _rastgele_montaj(tohum: int):
    """6 alt montaj × 5 küre; hem alt montajlar hem yapraklar rastgele dönmüş ve ötelenmiş (sabit tohum)."""
    rng = np.random.default_rng(tohum)

    def T_rastgele(olcek: float) -> np.ndarray:
        a, b, c = rng.uniform(0, 360, 3)
        return transform(rot_z(a) @ rot_y(b) @ rot_x(c), rng.uniform(0, olcek, 3))

    parts, gruplar = {}, []
    for g in range(6):
        yapraklar = []
        for k in range(5):
            ad = f"k{g}_{k}"
            parts[ad] = SahteKure(rng.uniform(-5, 5, 3), rng.uniform(2, 5), ad)
            yapraklar.append(Node(f"y{k}", T=T_rastgele(12.0), part=ad))
        gruplar.append(Node(f"g{g}", T=T_rastgele(45.0), children=yapraklar))
    return Node("rastgele", children=gruplar), parts


@pytest.mark.parametrize("tohum", [7, 2026])
def test_broad_phase_misses_nothing_random(tohum):
    """30 rastgele dönmüş parça: kaba elemeli check = kaba elemesiz tam tarama (tür, hacim, uzaklık)."""
    root, parts = _rastgele_montaj(tohum)
    clearance = 1.5
    beklenen = tam_tarama(root, parts, clearance)
    sonuc = check(root, parts, clearance=clearance)
    assert sum(1 for s in beklenen if s[2] is ClashKind.GIRISIM) >= 3  # test anlamlı olsun
    assert satirlar(sonuc) == [s[:3] for s in beklenen]
    np.testing.assert_allclose([c.volume for c in sonuc], [s[3] for s in beklenen], rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose([c.distance for c in sonuc], [s[4] for s in beklenen], rtol=1e-9, atol=1e-12)


# ---------- K7 hatalar ----------


def test_error_part_missing():
    root, parts = _montaj()
    del parts["k2"]
    with pytest.raises(AssyError):
        check(root, parts)


def test_error_invalid_tree():
    """validate(root) çağrılır: yinelenen kardeş adı → AssyError."""
    parts = {"a": kutu((0, 0, 0), (1, 1, 1), "a")}
    root = Node("m", children=[Node("x", part="a"), Node("x", part="a")])
    with pytest.raises(AssyError):
        check(root, parts)


def test_error_unknown_scope():
    root, parts = _montaj()
    with pytest.raises(AssyError):
        check(root, parts, scope="g3")


def test_error_scope_is_leaf():
    root, parts = _montaj()
    with pytest.raises(AssyError):
        check(root, parts, scope="g1/c1")


def test_error_across_single_child():
    parts = {"a": kutu((0, 0, 0), (1, 1, 1), "a"), "b": kutu((0.5, 0, 0), (2, 1, 1), "b")}
    root = Node("m", children=[Node("tek", children=[Node("y1", part="a"), Node("y2", part="b")])])
    with pytest.raises(AssyError):
        check(root, parts, across=True)
    assert satirlar(check(root, parts, scope="tek", across=True)) == [("tek/y1", "tek/y2", ClashKind.GIRISIM)]


@pytest.mark.parametrize(
    "ignore",
    [[("g1", "govde")], [("govde", "g9/c1")], [("g1/c1", "")]],
    ids=["alt-montaj", "bilinmeyen", "kok"],
)
def test_error_ignore_not_leaf(ignore):
    root, parts = _montaj()
    with pytest.raises(AssyError):
        check(root, parts, ignore=ignore)


@pytest.mark.parametrize("ad", ["clearance", "tol_v", "tol_d"])
@pytest.mark.parametrize("deger", [-1e-3, math.nan, math.inf])
def test_error_bad_tolerances(ad, deger):
    root, parts = _montaj()
    with pytest.raises(AssyError):
        check(root, parts, **{ad: deger})


@pytest.mark.parametrize(
    "a, b",
    [("g1/c1", "g1/c9"), ("yok", "govde"), ("g1", "govde"), ("govde", ""), ("g1/c1", "g1/c1")],
    ids=["bilinmeyen-b", "bilinmeyen-a", "alt-montaj", "kok", "ayni"],
)
def test_error_gap(a, b):
    root, parts = _montaj()
    with pytest.raises(AssyError):
        gap(root, parts, a, b)
