"""SPEC 36 — assy/sira.py testleri: yönler, engelleme, örnekleme, montaj sırası, alt montaj, hatalar (K1–K8).

Testler sadece specs/36-montaj-sirasi.md'deki teori, arayüz ve Ek A'dan yazıldı; assy/sira.py gövdesi
okunmadı.
K7 gerçek Part (OCCT) kullanır ve `occt` işaretlidir. Diğerleri OCCT'siz: sira parçayı yalnız Part arayüzünden
(bbox, moved, common, volume) kullandığı için kesin sonuçlu sahte kutularla:
    SahteKutu  eksen hizalı kutu; common = kutu kesişimi (kapalı form). `kutu` verilirse bbox gerçek kutudan
               büyük raporlanır (kaba elemenin geçtiği ama kesişimin olmadığı noktaları üretmek için).
Engel tanımı (Teori):  j, i'yi d yönünde engeller ⇔ ∃ s > 0 : V((i + s d) ∩ j) > tol_v.
Kutularda bu, Teori'deki kutu penceresi (a, b)'nin boş olmamasıdır; Ek A kenarları buradan el ile hesaplandı.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from assy.model import Assembly, AssyError, Component, Mate, MateKind, Node, Ref, RefKind, rot_z, transform
from assy.sira import DIRECTIONS, Step, blocking, mate_directions, sequence

PZ, NZ, PX, NX, PY, NY = (
    np.array(v, dtype=float) for v in [(0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]
)

# ---------- Sahte parçalar ----------


class Sayac:
    """common çağrılarını kaydeder: (self adı, self.lo, other adı, other.lo)."""

    def __init__(self) -> None:
        self.cagrilar: list[tuple[str, np.ndarray, str, np.ndarray]] = []


class SahteSonuc:
    def __init__(self, volume: float) -> None:
        self.volume = float(volume)


class SahteKutu:
    """Gerçek kutu [lo, hi]; bbox varsayılan olarak aynı, `kutu` verilirse o (gerçek kutuyu içermeli)."""

    def __init__(self, lo, hi, name: str, sayac: Sayac | None = None, kutu=None) -> None:
        self.lo, self.hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
        if kutu is None:
            kutu = (self.lo, self.hi)
        self.blo, self.bhi = (np.asarray(v, dtype=float) for v in kutu)
        assert np.all(self.blo <= self.lo) and np.all(self.bhi >= self.hi)
        self.name = name
        self.sayac = sayac if sayac is not None else Sayac()

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.blo.copy(), self.bhi.copy()

    @property
    def volume(self) -> float:
        return float(np.prod(self.hi - self.lo))

    def moved(self, T: np.ndarray) -> SahteKutu:
        T = np.asarray(T, dtype=float)
        assert np.allclose(T[:3, :3], np.eye(3)), "Bu testlerde yalnız öteleme kullanılır"
        t = T[:3, 3]
        return SahteKutu(self.lo + t, self.hi + t, self.name, self.sayac, (self.blo + t, self.bhi + t))

    def common(self, other: SahteKutu, tol_v: float = 1e-6) -> SahteSonuc | None:
        self.sayac.cagrilar.append((self.name, self.lo.copy(), other.name, other.lo.copy()))
        lo, hi = np.maximum(self.lo, other.lo), np.minimum(self.hi, other.hi)
        V = float(np.prod(np.maximum(0.0, hi - lo)))
        return None if V <= tol_v else SahteSonuc(V)


def _sahne(kutular: dict[str, tuple], sayac: Sayac | None = None, kaba: dict | None = None):
    """Kök altında düz yapraklar; parça kimliği = ad, T birim."""
    sayac = sayac if sayac is not None else Sayac()
    kaba = kaba or {}
    parts = {a: SahteKutu(lo, hi, a, sayac, kaba.get(a)) for a, (lo, hi) in kutular.items()}
    root = Node("montaj", children=[Node(a, part=a) for a in kutular])
    return root, parts


# ---------- Ek A ----------

EK_A = {
    "taban": ((0, 0, -10), (100, 60, 0)),
    "blok_1": ((10, 10, 0), (40, 50, 30)),
    "blok_2": ((60, 10, 0), (90, 50, 30)),
    "dayama": ((40, 20, 0), (60, 40, 20)),
    "kapak": ((5, 5, 30), (95, 55, 38)),
    "pim": ((48, 28, -5), (52, 32, 25)),
}


def ek_a(sira: list[str], sayac: Sayac | None = None):
    return _sahne({a: EK_A[a] for a in sira}, sayac)


SIRA_1 = ["taban", "blok_1", "blok_2", "dayama", "kapak"]
SIRA_2 = ["taban", "kapak", "blok_1", "dayama", "blok_2"]
PIMLI = [*SIRA_1, "pim"]

# Ek A (pimsiz) yönlü engelleme kenarları, el hesabı: (i, j) = "j, i'yi d yönünde engeller"
EK_A_KENAR = [
    (
        PZ,
        {
            ("blok_1", "kapak"),
            ("blok_2", "kapak"),
            ("dayama", "kapak"),
            ("taban", "blok_1"),
            ("taban", "blok_2"),
            ("taban", "dayama"),
            ("taban", "kapak"),
        },
    ),
    (
        NZ,
        {
            ("blok_1", "taban"),
            ("blok_2", "taban"),
            ("dayama", "taban"),
            ("kapak", "blok_1"),
            ("kapak", "blok_2"),
            ("kapak", "dayama"),
            ("kapak", "taban"),
        },
    ),
    (PX, {("blok_1", "blok_2"), ("blok_1", "dayama"), ("dayama", "blok_2")}),
    (NX, {("blok_2", "blok_1"), ("blok_2", "dayama"), ("dayama", "blok_1")}),
    (PY, set()),
    (NY, set()),
]


def _tr(v) -> np.ndarray:
    return transform(t=np.asarray(v, dtype=float))


def _ozet(adimlar: list[Step]) -> list[tuple[str, tuple | None, float]]:
    return [(s.path, None if s.direction is None else tuple(s.direction), s.distance) for s in adimlar]


def _adimlari_dogrula(adimlar: list[Step], beklenen: list[tuple[str, np.ndarray | None, float]]) -> None:
    assert [s.path for s in adimlar] == [b[0] for b in beklenen]
    for s, (_, d, dist) in zip(adimlar, beklenen, strict=True):
        if d is None:
            assert s.direction is None
        else:
            assert s.direction is not None
            np.testing.assert_allclose(s.direction, d, atol=1e-12)
        assert s.distance == pytest.approx(dist, abs=1e-12)


def _kenarlar(sonuc) -> list[tuple[np.ndarray, set]]:
    return [(np.asarray(d, dtype=float), set(e)) for d, e in sonuc]


def _kenarlari_dogrula(sonuc, beklenen) -> None:
    sonuc = _kenarlar(sonuc)
    assert len(sonuc) == len(beklenen)
    for (d, e), (bd, be) in zip(sonuc, beklenen, strict=True):
        np.testing.assert_allclose(d, bd, atol=1e-12)
        assert e == be, f"d = {bd}"


# ---------- K1 Yön listesi ----------


def test_directions_constant_order():
    assert len(DIRECTIONS) == 6
    for d, b in zip(DIRECTIONS, [PZ, NZ, PX, NX, PY, NY], strict=True):
        np.testing.assert_array_equal(d, b)


def test_directions_normalized_and_deduplicated():
    """(0,0,2) birime normlanır; ardından gelen +Z ve 1 − d·d' ≤ 1e-9 olan neredeyse +Z atılır;
    sıra korunur."""
    root, parts = _sahne({"a": ((0, 0, 0), (10, 10, 10)), "b": ((0, 0, 10), (10, 10, 20))})
    yonler = [(0, 0, 2), (0, 0, 1), np.array([3.0, 0.0, 0.0]), (0, 1e-6, 1), [0, 0, -5]]
    sonuc = _kenarlar(blocking(root, parts, yonler))
    assert len(sonuc) == 3
    for (d, _), b in zip(sonuc, [PZ, PX, NZ], strict=True):
        np.testing.assert_allclose(d, b, atol=1e-12)
    assert sonuc[0][1] == {("a", "b")}
    assert sonuc[1][1] == set()
    assert sonuc[2][1] == {("b", "a")}


def test_directions_near_but_distinct_kept():
    """1 − cos θ ≈ 5e-9 > 1e-9: ayrı yön sayılır."""
    root, parts = _sahne({"a": ((0, 0, 0), (10, 10, 10)), "b": ((0, 0, 10), (10, 10, 20))})
    sonuc = _kenarlar(blocking(root, parts, [(0, 0, 1), (0, 1e-4, 1)]))
    assert len(sonuc) == 2
    np.testing.assert_allclose(sonuc[1][0], np.array([0, 1e-4, 1]) / math.hypot(1e-4, 1), atol=1e-12)


def test_sequence_deduplicates_directions():
    """Yinelenen yön sırayı değiştirmez: (0,0,3) ve +Z ile Ek A sıra 1 aynı sonucu verir."""
    root, parts = ek_a(SIRA_1)
    a = sequence(root, parts, directions=[(0, 0, 3), (0, 0, 1), (1, 0, 0)])
    _adimlari_dogrula(
        a, [("taban", None, 0), ("blok_1", PZ, 5), ("blok_2", PZ, 35), ("dayama", PZ, 35), ("kapak", PZ, 5)]
    )


def _kisit_montaji(mates: list[Mate]) -> Assembly:
    return Assembly(
        "m",
        components=[
            Component("govde", "govde"),
            Component("mil", "mil", T=transform(rot_z(90), (10, 20, 30))),
            Component("kapak", "kapak", T=_tr((0, 0, 50))),
        ],
        mates=mates,
    )


def test_mate_directions_concentric_and_planes():
    """Z'de 90° dönmüş milde yerel X ekseni dünyada +Y; önce +, sonra −. Düzlem–düzlem COINCIDENT normali
    +Z → (+Z, −Z). Nokta–nokta kısıt yön vermez."""
    a = _kisit_montaji(
        [
            Mate(
                MateKind.CONCENTRIC,
                Ref("mil", RefKind.AXIS, (0, 0, 0), (1, 0, 0)),
                Ref("govde", RefKind.AXIS, (0, 0, 0), (0, 1, 0)),
            ),
            Mate(
                MateKind.COINCIDENT,
                Ref("kapak", RefKind.POINT, (1, 2, 3)),
                Ref("govde", RefKind.POINT, (1, 2, 3)),
            ),
            Mate(
                MateKind.COINCIDENT,
                Ref("kapak", RefKind.PLANE, (0, 0, 0), (0, 0, 1)),
                Ref("govde", RefKind.PLANE, (0, 0, 50), (0, 0, -1)),
            ),
        ]
    )
    yonler = mate_directions(a)
    assert len(yonler) == 4
    for d, b in zip(yonler, [PY, NY, PZ, NZ], strict=True):
        np.testing.assert_allclose(d, b, atol=1e-12)


def test_mate_directions_distance_plane_and_duplicates_once():
    """DISTANCE düzlem–düzlem normal verir; ortak yönler (ikinci eş eksen +Y, ±Z tekrarı) bir kez;
    ANGLE ve nokta–düzlem kısıtları yön vermez. Kısıt sırası korunur."""
    a = _kisit_montaji(
        [
            Mate(
                MateKind.DISTANCE,
                Ref("kapak", RefKind.PLANE, (0, 0, 0), (1, 0, 0)),
                Ref("govde", RefKind.PLANE, (0, 0, 0), (-1, 0, 0)),
                value=3.0,
            ),
            Mate(
                MateKind.CONCENTRIC,
                Ref("mil", RefKind.AXIS, (0, 0, 0), (-1, 0, 0)),
                Ref("govde", RefKind.AXIS, (0, 0, 0), (0, 1, 0)),
            ),
            Mate(
                MateKind.ANGLE,
                Ref("kapak", RefKind.PLANE, (0, 0, 0), (0, 1, 1)),
                Ref("govde", RefKind.PLANE, (0, 0, 0), (0, 0, 1)),
                value=30.0,
            ),
            Mate(
                MateKind.COINCIDENT,
                Ref("kapak", RefKind.POINT, (0, 0, 0)),
                Ref("govde", RefKind.PLANE, (0, 0, 0), (1, 1, 0)),
            ),
            Mate(
                MateKind.COINCIDENT,
                Ref("mil", RefKind.PLANE, (0, 0, 0), (1, 0, 0)),
                Ref("govde", RefKind.PLANE, (0, 0, 0), (0, 1, 0)),
            ),
            Mate(
                MateKind.COINCIDENT,
                Ref("kapak", RefKind.PLANE, (0, 0, 0), (0, 0, -1)),
                Ref("govde", RefKind.PLANE, (0, 0, 0), (0, 0, 1)),
            ),
        ]
    )
    yonler = mate_directions(a)
    # DISTANCE: kapak +X → (+X, −X); CONCENTRIC: mil −X yerel → dünya −Y → (−Y, +Y);
    # mil düzlemi yerel +X → dünya +Y: tekrar; kapak −Z → (−Z, +Z)
    beklenen = [PX, NX, NY, PY, NZ, PZ]
    assert len(yonler) == len(beklenen)
    for d, b in zip(yonler, beklenen, strict=True):
        np.testing.assert_allclose(d, b, atol=1e-12)


def test_mate_directions_empty_without_directional_mates():
    a = _kisit_montaji(
        [
            Mate(
                MateKind.COINCIDENT,
                Ref("kapak", RefKind.POINT, (0, 0, 0)),
                Ref("govde", RefKind.POINT, (0, 0, 0)),
            )
        ]
    )
    assert list(mate_directions(a)) == []


def test_mate_directions_usable_as_directions():
    """Belgelenen kullanım: mate_directions(a) + list(DIRECTIONS)."""
    a = _kisit_montaji(
        [
            Mate(
                MateKind.COINCIDENT,
                Ref("kapak", RefKind.PLANE, (0, 0, 0), (0, 0, 1)),
                Ref("govde", RefKind.PLANE, (0, 0, 0), (0, 0, -1)),
            )
        ]
    )
    root, parts = ek_a(SIRA_1)
    adimlar = sequence(root, parts, directions=mate_directions(a) + list(DIRECTIONS))
    _adimlari_dogrula(
        adimlar,
        [("taban", None, 0), ("blok_1", PZ, 5), ("blok_2", PZ, 35), ("dayama", PZ, 35), ("kapak", PZ, 5)],
    )


# ---------- K2 Engelleme (analitik) ----------


def test_blocking_ek_a():
    root, parts = ek_a(SIRA_1)
    _kenarlari_dogrula(blocking(root, parts), EK_A_KENAR)


def test_blocking_touching_stack():
    """Üst üste değen kutular: ε ile yerel engel (±Z); yüzey boyunca kayan ±X, ±Y serbest."""
    root, parts = _sahne({"a": ((0, 0, 0), (10, 10, 10)), "b": ((0, 0, 10), (10, 10, 20))})
    _kenarlari_dogrula(
        blocking(root, parts),
        [(PZ, {("a", "b")}), (NZ, {("b", "a")}), (PX, set()), (NX, set()), (PY, set()), (NY, set())],
    )


def test_blocking_after_gap():
    """20 mm boşluktan sonra gelen engel +X'te yakalanır."""
    root, parts = _sahne({"a": ((0, 0, 0), (10, 10, 10)), "b": ((30, 0, 0), (40, 10, 10))})
    _kenarlari_dogrula(
        blocking(root, parts),
        [(PZ, set()), (NZ, set()), (PX, {("a", "b")}), (NX, {("b", "a")}), (PY, set()), (NY, set())],
    )


def test_blocking_thin_wall_with_step_1():
    """δ = 1 ile 0.5 mm kalınlığında duvar yakalanır."""
    root, parts = _sahne({"a": ((0, 0, 0), (10, 10, 10)), "duvar": ((20, 0, 0), (20.5, 10, 10))})
    _kenarlari_dogrula(
        blocking(root, parts, [PX, NX], step=1.0), [(PX, {("a", "duvar")}), (NX, {("duvar", "a")})]
    )


def test_blocking_diagonal_hit_and_box_miss():
    """d = (1,1,0)/√2: köşegendeki b engeller; c'nin kutusuyla eksen pencereleri ayrık (x ≈ (14.1, 42.4),
    y ≈ (56.6, 84.9)), engellemez."""
    root, parts = _sahne(
        {"a": ((0, 0, 0), (10, 10, 10)), "b": ((20, 20, 0), (30, 30, 10)), "c": ((20, 50, 0), (30, 60, 10))}
    )
    sonuc = _kenarlar(blocking(root, parts, [(1, 1, 0)]))
    assert len(sonuc) == 1
    np.testing.assert_allclose(sonuc[0][0], np.array([1, 1, 0]) / math.sqrt(2), atol=1e-12)
    assert sonuc[0][1] == {("a", "b")}


def test_blocking_initial_interference_every_direction():
    root, parts = _sahne({"a": ((0, 0, 0), (10, 10, 10)), "b": ((5, 0, 0), (15, 10, 10))})
    _kenarlari_dogrula(blocking(root, parts), [(d, {("a", "b"), ("b", "a")}) for d in DIRECTIONS])


@pytest.mark.parametrize("ignore", [[("a", "b")], [("b", "a")], {("a", "b"), ("b", "a")}])
def test_blocking_ignore_pair_is_unordered(ignore):
    root, parts = _sahne({"a": ((0, 0, 0), (10, 10, 10)), "b": ((5, 0, 0), (15, 10, 10))})
    _kenarlari_dogrula(blocking(root, parts, ignore=ignore), [(d, set()) for d in DIRECTIONS])


def test_blocking_ignore_only_named_pair():
    """Ek A + pim: ignore yalnız (pim, taban) ve (pim, dayama) çiftlerini kaldırır;
    kapak pimi +Z'de engeller."""
    root, parts = ek_a(PIMLI)
    sonuc = _kenarlar(blocking(root, parts, ignore=[("pim", "taban"), ("pim", "dayama")]))
    kenar = {tuple(d): e for d, e in sonuc}
    assert ("pim", "kapak") in kenar[(0.0, 0.0, 1.0)]
    assert not any("pim" in e and ("taban" in e or "dayama" in e) for es in kenar.values() for e in es)
    assert {e for e in kenar[(0.0, 0.0, -1.0)] if e[0] == "pim"} == set()
    # pimsiz kenarlar değişmez
    for d, be in EK_A_KENAR:
        assert {e for e in kenar[tuple(d)] if "pim" not in e} == be


def test_blocking_without_ignore_pin_blocked_everywhere():
    root, parts = ek_a(PIMLI)
    for _, e in _kenarlar(blocking(root, parts)):
        assert {("pim", "taban"), ("taban", "pim"), ("pim", "dayama"), ("dayama", "pim")} <= e


# ---------- K3 Örnekleme ve kaba eleme (çağrı sayan sahte parçalar) ----------


def _cagri_s(sayac: Sayac, kutular: dict, d: np.ndarray, hareketli: str, sabit: str) -> list[float]:
    """hareketli–sabit çifti için common çağrılarındaki s değerleri, çağrı sırasıyla.

    s, hareketlinin sabite göre göreli ötelemesidir (uygulama i'yi +s d ya da j'yi −s d ötelemiş olabilir).
    Göreli öteleme d ile paralel değilse (başka bir yönün sınaması) atlanır."""
    d = np.asarray(d, dtype=float) / np.linalg.norm(d)
    s_ler = []
    for a, lo_a, b, lo_b in sayac.cagrilar:
        if {a, b} != {hareketli, sabit}:
            continue
        lo = {a: lo_a, b: lo_b}
        v = (lo[hareketli] - np.asarray(kutular[hareketli][0], float)) - (
            lo[sabit] - np.asarray(kutular[sabit][0], float)
        )
        s = float(v @ d)
        if s > 0 and np.allclose(v, s * d, atol=1e-9):
            s_ler.append(s)
    return s_ler


def test_no_common_when_boxes_never_overlap_along_path():
    """Çapraz konumdaki iki kutu: altı eksen yönünün hiçbirinde kutular yol boyunca örtüşmez → 0 common."""
    sayac = Sayac()
    root, parts = _sahne({"a": ((0, 0, 0), (10, 10, 10)), "b": ((20, 20, 0), (30, 30, 10))}, sayac)
    _kenarlari_dogrula(blocking(root, parts), [(d, set()) for d in DIRECTIONS])
    assert sayac.cagrilar == []


def test_diagonal_box_miss_no_common():
    sayac = Sayac()
    root, parts = _sahne({"a": ((0, 0, 0), (10, 10, 10)), "c": ((20, 50, 0), (30, 60, 10))}, sayac)
    blocking(root, parts, [(1, 1, 0)])
    assert sayac.cagrilar == []


SAHTE_A = ((0, 0, 0), (10, 10, 10))


@pytest.mark.parametrize(
    ("b_gercek", "b_kutu", "step", "beklenen", "engel"),
    [
        # pencere (15, 40), δ = 4: P = 16, 20, 24, 27.5, 28, 32, 36; gerçek kesişim s > 23 → 24'te dur
        (((33, 0, 0), (40, 10, 10)), ((25, 0, 0), (40, 10, 10)), 4.0, [16.0, 20.0, 24.0], True),
        # aynı pencere, gerçek kutu y'de kaçık (hiç kesişmez) → P'nin tamamı
        (
            ((25, 20, 0), (40, 30, 10)),
            ((25, -5, 0), (40, 30, 10)),
            4.0,
            [16.0, 20.0, 24.0, 27.5, 28.0, 32.0, 36.0],
            False,
        ),
        # değen kutular, pencere (0, 20), δ = 4: P = ε, 4, 8, 10, 12, 16; gerçek kesişim s > 5 → 8'de dur
        (((15, 0, 0), (20, 10, 10)), ((10, 0, 0), (20, 10, 10)), 4.0, [0.01, 4.0, 8.0], True),
        # gerçek kutu da değiyor: ε'da dur
        (((10, 0, 0), (20, 10, 10)), ((10, 0, 0), (20, 10, 10)), 4.0, [0.01], True),
        # δ pencereden büyük: yalnız ε ve orta nokta
        (((10, 20, 0), (20, 30, 10)), ((10, -5, 0), (20, 30, 10)), 100.0, [0.01, 10.0], False),
        # step = None → δ = en küçük yerel bbox kenarı = 10: P = 20, 27.5, 30; gerçek kesişim s > 23
        (((33, 0, 0), (40, 10, 10)), ((25, 0, 0), (40, 10, 10)), None, [20.0, 27.5], True),
    ],
)
def test_sample_points_in_order_and_stop_at_first_block(b_gercek, b_kutu, step, beklenen, engel):
    """Yalnız (a, b, +X) sınanır (b +X'te a'dan uzaklaşır: pencere boş).
    Çağrılan s'ler P ile sırasıyla birebir."""
    sayac = Sayac()
    kutular = {"a": SAHTE_A, "b": b_gercek}
    root, parts = _sahne(kutular, sayac, kaba={"b": b_kutu})
    sonuc = _kenarlar(blocking(root, parts, [PX], step=step))
    assert sonuc[0][1] == ({("a", "b")} if engel else set())
    assert _cagri_s(sayac, kutular, PX, "a", "b") == pytest.approx(beklenen, abs=1e-9)
    assert len(sayac.cagrilar) == len(beklenen)


def test_sequence_caches_each_test():
    """Ek A sıra 2, yönler (+Z, +X) (zıt yön yok): her (i, j, d) için çağrılan s değerleri kesin artan,
    yani aynı sınama ikinci kez yapılmaz."""
    sayac = Sayac()
    root, parts = ek_a(SIRA_2, sayac)
    adimlar = sequence(root, parts, directions=[PZ, PX])
    _adimlari_dogrula(
        adimlar,
        [("taban", None, 0), ("kapak", PZ, 0), ("blok_1", PX, 95), ("dayama", PX, 65), ("blok_2", PX, 45)],
    )
    assert sayac.cagrilar
    adlar = list(EK_A)[:5]
    for d in (PZ, PX):
        for i in adlar:
            for j in adlar:
                if i == j:
                    continue
                s_ler = _cagri_s(sayac, EK_A, d, i, j)
                assert all(b > a for a, b in zip(s_ler, s_ler[1:], strict=False)), (i, j, d, s_ler)


def test_no_common_within_unit():
    """Bir birimin girişen iki yaprağı birbirine karşı sınanmaz; uzak birimle kutular hiç örtüşmez
    → 0 common."""
    sayac = Sayac()
    parts = {
        "u1": SahteKutu((0, 0, 0), (10, 10, 10), "u1", sayac),
        "u2": SahteKutu((5, 0, 0), (15, 10, 10), "u2", sayac),
        "w": SahteKutu((100, 100, 0), (110, 110, 10), "w", sayac),
    }
    root = Node(
        "montaj",
        children=[Node("alt", children=[Node("u1", part="u1"), Node("u2", part="u2")]), Node("w", part="w")],
    )
    _kenarlari_dogrula(blocking(root, parts, units="cocuk"), [(d, set()) for d in DIRECTIONS])
    assert sayac.cagrilar == []
    adimlar = sequence(root, parts, units="cocuk")
    assert [s.path for s in adimlar] == ["alt", "w"]
    assert sayac.cagrilar == []


def test_common_only_for_leaf_pairs_overlapping_at_s():
    """Birim U = {u1, u2}; +X'te s = ε'da yalnız u1'in kutusu v'ninkiyle örtüşür → yalnız (u1, v) sınanır."""
    sayac = Sayac()
    parts = {
        "u1": SahteKutu((0, 0, 0), (10, 10, 10), "u1", sayac),
        "u2": SahteKutu((0, 20, 0), (10, 30, 10), "u2", sayac),
        "v": SahteKutu((10, 0, 0), (20, 10, 10), "v", sayac),
    }
    root = Node(
        "montaj",
        children=[Node("U", children=[Node("u1", part="u1"), Node("u2", part="u2")]), Node("v", part="v")],
    )
    sonuc = _kenarlar(blocking(root, parts, [PX], units="cocuk"))
    assert sonuc[0][1] == {("U", "v")}
    assert sayac.cagrilar
    assert all({a, b} == {"u1", "v"} for a, _, b, _ in sayac.cagrilar)


# ---------- K4 Montaj sırası (Ek A) ----------

BEKLENEN_SIRA_1 = [
    ("taban", None, 0),
    ("blok_1", PZ, 5),
    ("blok_2", PZ, 35),
    ("dayama", PZ, 35),
    ("kapak", PZ, 5),
]
BEKLENEN_SIRA_2 = [
    ("taban", None, 0),
    ("kapak", PZ, 0),
    ("blok_1", PX, 95),
    ("dayama", PX, 65),
    ("blok_2", PX, 45),
]


def test_sequence_ek_a_order_1_is_walk_order():
    root, parts = ek_a(SIRA_1)
    adimlar = sequence(root, parts)
    _adimlari_dogrula(adimlar, BEKLENEN_SIRA_1)
    assert [s.path for s in adimlar] == SIRA_1


def test_sequence_ek_a_order_2():
    root, parts = ek_a(SIRA_2)
    _adimlari_dogrula(sequence(root, parts), BEKLENEN_SIRA_2)


@pytest.mark.parametrize("sira", [SIRA_1, SIRA_2])
def test_step_fields(sira):
    root, parts = ek_a(sira)
    adimlar = sequence(root, parts)
    assert all(isinstance(s, Step) for s in adimlar)
    taban = adimlar[0]
    assert taban.path == "taban" and taban.leaves == ("taban",)
    assert taban.direction is None and taban.distance == 0
    np.testing.assert_array_equal(taban.T_out, taban.T)
    for s in adimlar:
        assert s.leaves == (s.path,)
        np.testing.assert_allclose(s.T, np.eye(4), atol=1e-12)
    for s in adimlar[1:]:
        assert np.linalg.norm(s.direction) == pytest.approx(1.0, abs=1e-12)
        np.testing.assert_allclose(s.T_out, _tr(s.distance * np.asarray(s.direction)) @ s.T, atol=1e-12)


def test_step_T_is_world_transform():
    """Yaprak düğümlerin T'si ötelemeli: Step.T = world(root, path), T_out = Tr(s d) · T; sonuç aynı."""
    kayma = {
        "taban": (1, 2, 3),
        "blok_1": (-4, 0, 7),
        "blok_2": (0, 0, 0),
        "dayama": (2, -2, 0),
        "kapak": (0, 9, -1),
    }
    parts = {
        a: SahteKutu(np.subtract(EK_A[a][0], kayma[a]), np.subtract(EK_A[a][1], kayma[a]), a) for a in SIRA_1
    }
    root = Node("montaj", children=[Node(a, T=_tr(kayma[a]), part=a) for a in SIRA_1])
    adimlar = sequence(root, parts)
    _adimlari_dogrula(adimlar, BEKLENEN_SIRA_1)
    for s in adimlar:
        np.testing.assert_allclose(s.T, _tr(kayma[s.path]), atol=1e-12)
    for s in adimlar[1:]:
        np.testing.assert_allclose(s.T_out, _tr(s.distance * np.asarray(s.direction)) @ s.T, atol=1e-12)


def test_sequence_does_not_modify_inputs():
    root, parts = ek_a(SIRA_2)
    root0 = copy.deepcopy(root)
    lo0 = {a: (p.lo.copy(), p.hi.copy()) for a, p in parts.items()}
    yonler = [PZ.copy(), PX.copy()]
    sequence(root, parts, directions=yonler)
    blocking(root, parts, directions=yonler)
    assert root == root0
    for a, p in parts.items():
        np.testing.assert_array_equal(p.lo, lo0[a][0])
        np.testing.assert_array_equal(p.hi, lo0[a][1])
    np.testing.assert_array_equal(yonler[0], PZ)
    np.testing.assert_array_equal(yonler[1], PX)


def test_base_given_explicitly():
    """base verilince o birim tabandır: blok_1 taban → taban −Z ile sökülür."""
    root, parts = ek_a(SIRA_1)
    adimlar = sequence(root, parts, base="blok_1")
    assert adimlar[0].path == "blok_1" and adimlar[0].direction is None
    assert {s.path for s in adimlar} == set(SIRA_1)


def test_pay_changes_distance():
    root, parts = ek_a(SIRA_1)
    adimlar = sequence(root, parts, pay=0.0)
    _adimlari_dogrula(
        adimlar,
        [("taban", None, 0), ("blok_1", PZ, 0), ("blok_2", PZ, 30), ("dayama", PZ, 30), ("kapak", PZ, 0)],
    )


# ---------- K5 Kilit ve ignore ----------


def test_pin_locks_without_ignore():
    root, parts = ek_a(PIMLI)
    with pytest.raises(AssyError) as e:
        sequence(root, parts)
    mesaj = str(e.value)
    assert "dayama" in mesaj and "pim" in mesaj
    assert "blok_1" not in mesaj


def test_pin_with_ignore():
    root, parts = ek_a(PIMLI)
    adimlar = sequence(root, parts, ignore=[("pim", "taban"), ("pim", "dayama")])
    _adimlari_dogrula(adimlar, [*BEKLENEN_SIRA_1, ("pim", NZ, 40)])


# ---------- K6 Alt montaj birimi ----------


def _gruplu(alt_T: np.ndarray | None = None):
    """Kök: taban, alt (blok_1, blok_2, dayama), kapak.
    alt_T verilirse yapraklar ters ötelenir (dünya konumları aynı)."""
    alt_T = np.eye(4) if alt_T is None else alt_T
    ic_T = np.linalg.inv(alt_T)
    parts = {a: SahteKutu(*EK_A[a], a) for a in SIRA_1}
    alt = Node("alt", T=alt_T, children=[Node(a, T=ic_T, part=a) for a in ["blok_1", "blok_2", "dayama"]])
    root = Node("montaj", children=[Node("taban", part="taban"), alt, Node("kapak", part="kapak")])
    return root, parts


def test_group_base_by_volume():
    root, parts = _gruplu()
    adimlar = sequence(root, parts, units="cocuk")
    _adimlari_dogrula(adimlar, [("alt", None, 0), ("taban", NZ, 5), ("kapak", PZ, 5)])


def test_group_base_taban():
    root, parts = _gruplu()
    adimlar = sequence(root, parts, base="taban", units="cocuk")
    _adimlari_dogrula(adimlar, [("taban", None, 0), ("alt", PZ, 5), ("kapak", PZ, 5)])


def test_group_step_leaves_and_T():
    alt_T = _tr((10, 0, 0))
    root, parts = _gruplu(alt_T)
    adimlar = sequence(root, parts, base="taban", units="cocuk")
    _adimlari_dogrula(adimlar, [("taban", None, 0), ("alt", PZ, 5), ("kapak", PZ, 5)])
    alt = adimlar[1]
    assert alt.leaves == ("alt/blok_1", "alt/blok_2", "alt/dayama")
    np.testing.assert_allclose(alt.T, alt_T, atol=1e-12)
    np.testing.assert_allclose(alt.T_out, _tr((0, 0, 5)) @ alt_T, atol=1e-12)
    assert adimlar[0].leaves == ("taban",) and adimlar[2].leaves == ("kapak",)


def test_group_blocking_unit_paths():
    root, parts = _gruplu()
    _kenarlari_dogrula(
        blocking(root, parts, units="cocuk"),
        [
            (PZ, {("alt", "kapak"), ("taban", "alt"), ("taban", "kapak")}),
            (NZ, {("alt", "taban"), ("kapak", "alt"), ("kapak", "taban")}),
            (PX, set()),
            (NX, set()),
            (PY, set()),
            (NY, set()),
        ],
    )


@pytest.mark.parametrize("units", ["yaprak", "cocuk"])
def test_scope_only_subtree(units):
    """scope = "alt": taban ve kapak yok sayılır; blok_1 ve blok_2 hacimleri eşit → walk'ta önce gelen blok_1
    taban; dayama ve blok_2 +Z ile çıkar (yalnız alt içindeki kutular: H_z = 30)."""
    root, parts = _gruplu()
    adimlar = sequence(root, parts, scope="alt", units=units)
    _adimlari_dogrula(adimlar, [("alt/blok_1", None, 0), ("alt/blok_2", PZ, 35), ("alt/dayama", PZ, 35)])


def test_scope_blocking_only_subtree():
    root, parts = _gruplu()
    sonuc = _kenarlar(blocking(root, parts, scope="alt"))
    birimler = {"alt/blok_1", "alt/blok_2", "alt/dayama"}
    assert all(set(e) <= birimler for _, es in sonuc for e in es)
    np.testing.assert_allclose(sonuc[2][0], PX)
    assert sonuc[2][1] == {
        ("alt/blok_1", "alt/blok_2"),
        ("alt/blok_1", "alt/dayama"),
        ("alt/dayama", "alt/blok_2"),
    }


# ---------- K7 Gerçek parçalar (OCCT) ----------


def _plaka_pim(kor: bool):
    """40×40×10 plaka (x, y ∈ [0, 40], z ∈ [0, 10]), (20, 20)'de Ø10 delik; Ø9.8, 20 mm pim.
    kor = False: boydan boya delik, pim z ∈ [−5, 15].
    kor = True: 6 mm derin kör delik (dibi z = 4), pim dipte."""
    from build123d import Align, Box, Cylinder, Pos

    from geometry.part import Part

    alt = (Align.MIN, Align.MIN, Align.MIN)
    merkez = (Align.CENTER, Align.CENTER, Align.MIN)
    if kor:
        delik = Pos(20, 20, 4) * Cylinder(5.0, 10.0, align=merkez)
        pim_z = 4.0
    else:
        delik = Pos(20, 20, -5) * Cylinder(5.0, 20.0, align=merkez)
        pim_z = -5.0
    plaka = Part(Box(40, 40, 10, align=alt) - delik, name="plaka")
    pim = Part(Pos(20, 20, pim_z) * Cylinder(4.9, 20.0, align=merkez), name="pim")
    root = Node("montaj", children=[Node("plaka", part="plaka"), Node("pim", part="pim")])
    return root, {"plaka": plaka, "pim": pim}


@pytest.mark.occt
def test_real_through_hole_pin():
    root, parts = _plaka_pim(kor=False)
    kenar = _kenarlar(blocking(root, parts))
    for d, e in kenar:
        if abs(d[2]) > 0.5:
            assert ("pim", "plaka") not in e, d
        else:
            assert ("pim", "plaka") in e, d


@pytest.mark.occt
def test_real_blind_hole_pin():
    root, parts = _plaka_pim(kor=True)
    kenar = _kenarlar(blocking(root, parts))
    serbest = [d for d, e in kenar if ("pim", "plaka") not in e]
    assert len(serbest) == 1
    np.testing.assert_allclose(serbest[0], PZ, atol=1e-12)


@pytest.mark.occt
def test_real_blind_hole_sequence():
    root, parts = _plaka_pim(kor=True)
    adimlar = sequence(root, parts)
    assert [s.path for s in adimlar] == ["plaka", "pim"]
    assert adimlar[0].direction is None
    np.testing.assert_allclose(adimlar[1].direction, PZ, atol=1e-12)
    assert adimlar[1].distance == pytest.approx(11.0, abs=1e-9)


# ---------- K8 Hatalar ----------


def _hata_sahnesi():
    root, parts = _gruplu()
    return root, parts


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scope": "yok"},
        {"scope": "alt/blok_1"},
        {"scope": "taban"},
        {"units": "parca"},
        {"units": ""},
        {"ignore": [("alt/blok_1", "yok")]},
        {"ignore": [("alt/blok_1", "alt")]},
        {"ignore": [("alt/blok_1", "alt/blok_1")]},
        {"ignore": [("taban", "kapak")], "scope": "alt"},
        {"directions": []},
        {"directions": [(0, 0, 0)]},
        {"directions": [(0, 0, 1), (0, 0, 0)]},
        {"directions": [(0, 0, math.nan)]},
        {"directions": [(math.inf, 0, 0)]},
        {"step": 0.0},
        {"step": -1.0},
        {"step": math.inf},
        {"step": math.nan},
        {"eps": 0.0},
        {"eps": -0.01},
        {"eps": math.inf},
        {"eps": math.nan},
        {"tol_v": -1e-6},
        {"tol_v": math.inf},
        {"tol_v": math.nan},
    ],
)
@pytest.mark.parametrize("fonksiyon", [sequence, blocking])
def test_errors_common(fonksiyon, kwargs):
    root, parts = _hata_sahnesi()
    with pytest.raises(AssyError):
        fonksiyon(root, parts, **kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base": "yok"},
        {"base": "alt"},  # units = "yaprak": alt bir birim değil
        {"base": "alt/blok_1", "units": "cocuk"},
        {"base": "taban", "scope": "alt"},
        {"pay": -1.0},
        {"pay": math.inf},
        {"pay": math.nan},
    ],
)
def test_errors_sequence_only(kwargs):
    root, parts = _hata_sahnesi()
    with pytest.raises(AssyError):
        sequence(root, parts, **kwargs)


def test_zero_tol_v_and_pay_allowed():
    root, parts = ek_a(SIRA_1)
    adimlar = sequence(root, parts, tol_v=0.0, pay=0.0)
    assert [s.path for s in adimlar] == SIRA_1


@pytest.mark.parametrize("fonksiyon", [sequence, blocking])
def test_error_missing_part(fonksiyon):
    root, parts = ek_a(SIRA_1)
    del parts["dayama"]
    with pytest.raises(AssyError):
        fonksiyon(root, parts)


@pytest.mark.parametrize("fonksiyon", [sequence, blocking])
def test_error_invalid_tree(fonksiyon):
    """validate(root) çağrılır: yinelenen kardeş adı."""
    parts = {"a": SahteKutu((0, 0, 0), (1, 1, 1), "a"), "b": SahteKutu((0, 0, 1), (1, 1, 2), "b")}
    root = Node("montaj", children=[Node("x", part="a"), Node("x", part="b")])
    with pytest.raises(AssyError):
        fonksiyon(root, parts)


@pytest.mark.parametrize(
    ("root_fn", "kwargs"),
    [
        # kapsamda tek yaprak
        (lambda: Node("montaj", children=[Node("taban", part="taban")]), {}),
        # units = "cocuk": kökün tek çocuğu (iki yapraklı alt montaj) → tek birim
        (
            lambda: Node(
                "montaj",
                children=[Node("alt", children=[Node("taban", part="taban"), Node("kapak", part="kapak")])],
            ),
            {"units": "cocuk"},
        ),
        # scope altında tek yaprak
        (
            lambda: Node(
                "montaj",
                children=[Node("alt", children=[Node("taban", part="taban")]), Node("kapak", part="kapak")],
            ),
            {"scope": "alt"},
        ),
    ],
)
@pytest.mark.parametrize("fonksiyon", [sequence, blocking])
def test_error_single_unit(fonksiyon, root_fn, kwargs):
    parts = {a: SahteKutu(*EK_A[a], a) for a in ("taban", "kapak")}
    with pytest.raises(AssyError):
        fonksiyon(root_fn(), parts, **kwargs)


def test_error_not_disassemblable_message_lists_remaining_in_walk_order():
    """Kilitli iki birim (girişen çift, ignore yok) taban dışında kalır; mesaj walk sırasıyla."""
    root, parts = _sahne(
        {
            "taban": ((0, 0, -10), (100, 100, 0)),
            "zkilit": ((0, 0, 0), (10, 10, 10)),
            "akilit": ((5, 0, 0), (15, 10, 10)),
        }
    )
    with pytest.raises(AssyError) as e:
        sequence(root, parts)
    mesaj = str(e.value)
    assert "zkilit" in mesaj and "akilit" in mesaj
    assert mesaj.index("zkilit") < mesaj.index("akilit")
