"""SPEC 27 — cam/features.py testleri (K1–K9). OCCT gerektirir.

Testler yalnızca SPEC 27 metninden ve sabit arayüzlerden (geometry/part.py, cam/model.py, cam/profile.py,
cam.ops2d / cam.gcode.cycles imzaları) yazıldı; cam/features.py gövdesi okunmadı.
Uydurma geometri: blok 100×60×20, min köşe orijinde, üst yüz z = 20 (SPEC 02 kuralı).
Beklenen değerler el ile türetildi:

- Seviyeler: +Z düzlemsel yüzlerin z'leri ve zmin; dilim [h_k, h_{k+1}].
- Yuvarlak köşeli cep pocket(x, y, w, l, t, r): x ∈ [x − w/2, x + w/2], y ∈ [y − l/2, y + l/2],
  alan w·l − (4 − π) r², köşe yay merkezleri köşelerden (r, r) içeride.
- r_corner (§8): dış halkada ccw yaylar (yarıçap) ve keskin sola dönüşler (0); köşe yoksa inf.
- Lamba (§2): d = 2R_alt, cbore_d = 2R_üst, cbore_depth = L_üst, depth = L_üst + L_alt.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

import build123d as bd  # noqa: E402

from cam import ops2d  # noqa: E402
from cam.features import Features, HoleFeature, OpenFeature, PocketFeature, recognize  # noqa: E402
from cam.gcode.cycles import hole_moves  # noqa: E402
from cam.model import CamError, MoveType, Stock, Tool, ToolKind  # noqa: E402
from cam.ops2d import Cut  # noqa: E402
from cam.profile import Arc, Line, Profile  # noqa: E402
from geometry.features import block, chamfer_top, hole, pocket  # noqa: E402
from geometry.fillet import fillet_top  # noqa: E402
from geometry.holes import counterbore_hole, countersink_hole, inclined_hole, tapped_hole  # noqa: E402
from geometry.part import Hole, Part  # noqa: E402

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 20.0  # blok kenarları [mm]
TOL = 1e-6  # mm, analitik değer toleransı
REL = 1e-6  # bağıl alan toleransı
ALT = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


# ---------------------------------------------------------------- yardımcılar


def blok() -> Part:
    return block(A, B, C)


def tek_kati(shape) -> Part:
    """build123d boolean sonucunu tek katılı Part yapar (uydurma geometri kurmak için)."""
    solids = list(shape.solids())
    assert len(solids) == 1, "test geometrisi tek katı olmalı"
    return Part(solids[0])


def yakin(p, q, tol: float = TOL) -> bool:
    return float(np.linalg.norm(np.asarray(p, dtype=float) - np.asarray(q, dtype=float))) <= tol


def kose_noktalari(profile: Profile) -> list[np.ndarray]:
    """Yalnız doğrulardan oluşan kapalı halkanın köşeleri (aynı doğrultudaki ardışık doğrular birleşik)."""
    assert all(isinstance(s, Line) for s in profile.segments), "halka yalnız doğrulardan oluşmalı"
    pts = [np.asarray(s.p0, dtype=float) for s in profile.segments]
    n = len(pts)
    kose = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        u, v = b - a, c - b
        if abs(u[0] * v[1] - u[1] * v[0]) > TOL * max(1.0, np.linalg.norm(u) * np.linalg.norm(v)):
            kose.append(b)
    return kose


def ayni_nokta_kumesi(P, Q, tol: float = TOL) -> bool:
    P, Q = list(P), list(Q)
    if len(P) != len(Q):
        return False
    p_in_q = all(any(yakin(p, q, tol) for q in Q) for p in P)
    return p_in_q and all(any(yakin(q, p, tol) for p in P) for q in Q)


def dikdortgen(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def uc_noktalari(profile: Profile) -> list[np.ndarray]:
    return [np.asarray(s.p0, dtype=float) for s in profile.segments]


def yaylar(profile: Profile) -> list[Arc]:
    return [s for s in profile.segments if isinstance(s, Arc)]


def tam_daire_mi(profile: Profile, c, R: float) -> bool:
    """Profil tek tam-daire yay mı (p0 = p1), merkez c, yarıçap R."""
    if len(profile.segments) != 1 or not isinstance(profile.segments[0], Arc):
        return False
    s = profile.segments[0]
    return yakin(s.p0, s.p1) and yakin(s.c, c) and abs(s.R - R) <= TOL


def esit_hole(h: Hole, origin, d, depth, through, cbore_d=0.0, cbore_depth=0.0) -> None:
    """Tanınan delik kaydını alan alan karşılaştırır (diş bilgisi tanımada yoktur)."""
    assert yakin(h.origin, origin)
    assert yakin(h.axis, (0.0, 0.0, -1.0))
    assert h.d == pytest.approx(d, abs=TOL)
    assert h.depth == pytest.approx(depth, abs=TOL)
    assert h.through is through
    assert h.cbore_d == pytest.approx(cbore_d, abs=TOL)
    assert h.cbore_depth == pytest.approx(cbore_depth, abs=TOL)
    assert h.csk_d == 0.0 and h.thread == ""


# K2 cebi: merkez (30, 30), 40 × 30, r = 5, derinlik 8 → x ∈ [10, 50], y ∈ [15, 45], taban z = 12
K2_MERKEZLER = [(15.0, 20.0), (45.0, 20.0), (45.0, 40.0), (15.0, 40.0)]
K2_UCLAR = [(15, 15), (45, 15), (50, 20), (50, 40), (45, 45), (15, 45), (10, 40), (10, 20)]
K2_ALAN = 40 * 30 - (4 - math.pi) * 25


def k2_parca() -> Part:
    return pocket(blok(), 30, 30, 40, 30, 8, r=5)


def k2_halkasi_dogru(outer: Profile) -> None:
    lines = [s for s in outer.segments if isinstance(s, Line)]
    arcs = yaylar(outer)
    assert len(lines) == 4 and len(arcs) == 4
    assert all(a.ccw for a in arcs)
    assert all(abs(a.R - 5.0) <= TOL for a in arcs)
    assert ayni_nokta_kumesi([a.c for a in arcs], K2_MERKEZLER)
    assert ayni_nokta_kumesi(uc_noktalari(outer), K2_UCLAR)
    assert outer.area == pytest.approx(K2_ALAN, rel=REL)


# ---------------------------------------------------------------- K1


def test_yuz_alma():
    stok = Stock(-2, -2, 0, 102, 62, 22)
    f = recognize(blok(), stok)
    assert isinstance(f, Features)
    assert len(f.faces) == 1
    ff = f.faces[0]
    assert ff.z == pytest.approx(20.0, abs=TOL)
    assert ff.depth == pytest.approx(2.0, abs=TOL)
    assert ff.boundary.closed
    assert ff.boundary.area == pytest.approx(104 * 64, rel=REL)  # CCW → pozitif
    assert ayni_nokta_kumesi(kose_noktalari(ff.boundary), dikdortgen(-2, -2, 102, 62))
    assert f.pockets == () and f.holes == ()

    # stok üstü parça üstünde → yüz alma yok
    f2 = recognize(blok(), Stock(-2, -2, 0, 102, 62, 20))
    assert f2.faces == ()


def test_yuz_alma_stoksuz_yok():
    f = recognize(blok())
    assert f.faces == () and f.pockets == () and f.opens == () and f.holes == ()


# ---------------------------------------------------------------- K2


def test_yuvarlak_koseli_cep():
    f = recognize(k2_parca())
    assert len(f.pockets) == 1
    p = f.pockets[0]
    assert isinstance(p, PocketFeature)
    assert p.z_top == pytest.approx(20.0, abs=TOL)
    assert p.z_bottom == pytest.approx(12.0, abs=TOL)
    assert p.region.holes == []
    k2_halkasi_dogru(p.region.outer)
    assert p.region.area == pytest.approx(K2_ALAN, rel=REL)
    assert p.r_corner == pytest.approx(5.0, abs=TOL)
    assert p.max_tool_d == pytest.approx(10.0, abs=TOL)
    assert f.faces == () and f.opens == () and f.holes == ()


# ---------------------------------------------------------------- K3


def test_ic_ice_cep():
    part = pocket(k2_parca(), 30, 30, 16, 12, 12)  # x ∈ [22, 38], y ∈ [24, 36], taban z = 8
    f = recognize(part)
    assert len(f.pockets) == 2
    p1, p2 = f.pockets
    assert (p1.z_top, p1.z_bottom) == (pytest.approx(20.0, abs=TOL), pytest.approx(12.0, abs=TOL))
    k2_halkasi_dogru(p1.region.outer)
    assert p1.region.holes == []
    assert p1.r_corner == pytest.approx(5.0, abs=TOL)

    assert (p2.z_top, p2.z_bottom) == (pytest.approx(12.0, abs=TOL), pytest.approx(8.0, abs=TOL))
    assert ayni_nokta_kumesi(kose_noktalari(p2.region.outer), dikdortgen(22, 24, 38, 36))
    assert p2.region.area == pytest.approx(192.0, rel=REL)
    assert p2.region.holes == []
    assert p2.r_corner == 0.0
    assert p2.max_tool_d == 0.0


# ---------------------------------------------------------------- K4


def test_adali_cep():
    # 60 × 40 cep, derinlik 15 (taban z = 5); içinde Ø20, yükseklik 10 silindir ada (z ∈ [5, 15])
    cep = pocket(blok(), 50, 30, 60, 40, 15)
    part = tek_kati(cep.shape + bd.Pos(50, 30, 5) * bd.Cylinder(10, 10, align=ALT))
    f = recognize(part)
    assert len(f.pockets) == 2
    ust, alt = f.pockets
    kose = dikdortgen(20, 10, 80, 50)

    assert (ust.z_top, ust.z_bottom) == (pytest.approx(20.0, abs=TOL), pytest.approx(15.0, abs=TOL))
    assert ust.region.holes == []
    assert ayni_nokta_kumesi(kose_noktalari(ust.region.outer), kose)
    assert ust.region.area == pytest.approx(2400.0, rel=REL)

    assert (alt.z_top, alt.z_bottom) == (pytest.approx(15.0, abs=TOL), pytest.approx(5.0, abs=TOL))
    assert ayni_nokta_kumesi(kose_noktalari(alt.region.outer), kose)
    assert len(alt.region.holes) == 1
    ada = alt.region.holes[0]
    assert tam_daire_mi(ada, (50.0, 30.0), 10.0)
    assert ada.area == pytest.approx(-math.pi * 100, rel=REL)  # Region kuralı: ada CW
    assert alt.region.area == pytest.approx(2400.0 - math.pi * 100, rel=REL)
    # dış halkada keskin köşeler var → 0
    assert ust.r_corner == 0.0 and alt.r_corner == 0.0


# ---------------------------------------------------------------- K5


def kayitli_delikli_parca() -> Part:
    p = hole(blok(), 15, 15, 8)  # Ø8 boydan
    p = countersink_hole(p, 35, 15, 6.6, 12.0, 90.0)  # Ø6.6 / Ø12 × 90° havşa, boydan
    p = counterbore_hole(p, 55, 15, screw="M6")  # Ø6.6 / Ø11 × 6.4 lamba, boydan
    p = tapped_hole(p, 75, 15, "M8", depth=12)  # Ø6.75 kör, 12
    a = math.radians(30)
    p = inclined_hole(p, np.array([50.0, 45.0, 20.0]), np.array([math.sin(a), 0.0, -math.cos(a)]), 6.0)
    return p


def test_kayitli_delikler():
    part = kayitli_delikli_parca()
    assert len(part.holes) == 5
    f = recognize(part)
    assert len(f.holes) == 5
    for hf, h in zip(f.holes, part.holes, strict=True):
        assert isinstance(hf, HoleFeature)
        assert hf.source == "kayit"
        assert hf.hole == h  # kayıt olduğu gibi
    assert [hf.top_access for hf in f.holes] == [True, True, True, True, False]
    # delik halkaları cep üretmez; havşa koni alanı alan dengesini bozmaz (CamError yok)
    assert f.pockets == ()
    assert f.opens == ()
    assert f.faces == ()


def test_kayitli_delik_cep_ile_birlikte():
    # cep tabanını değmeyen bir kayıtlı delik, cebi ve deliği ayrı ayrı verir
    part = hole(k2_parca(), 80, 30, 8, depth=10)
    f = recognize(part)
    assert len(f.pockets) == 1
    k2_halkasi_dogru(f.pockets[0].region.outer)
    assert len(f.holes) == 1 and f.holes[0].source == "kayit"
    assert f.holes[0].hole == part.holes[0]


# ---------------------------------------------------------------- K6


def test_taninan_delikler(tmp_path):
    p = hole(blok(), 15, 15, 8)  # Ø8 boydan
    p = counterbore_hole(p, 35, 15, screw="M6")  # Ø6.6 / Ø11 × 6.4
    p = tapped_hole(p, 55, 15, "M8", depth=12)  # geometride Ø6.75 kör, 12
    p = hole(p, 70, 40, 30, depth=10)  # Ø30 × 10 kör silindir (> hole_d_max)
    yol = tmp_path / "k6.step"
    p.to_step(yol)
    part = Part.from_step(yol)
    assert part.holes == ()  # kayıtlar STEP'te taşınmaz

    f = recognize(part)  # hole_d_max = 20
    assert len(f.holes) == 3
    assert all(hf.source == "tanima" for hf in f.holes)
    assert all(hf.top_access for hf in f.holes)
    h8, hm6, hm8 = (hf.hole for hf in f.holes)  # z_e eşit (20) → x artan
    esit_hole(h8, (15, 15, 20), d=8.0, depth=20.0, through=True)
    esit_hole(hm6, (35, 15, 20), d=6.6, depth=20.0, through=True, cbore_d=11.0, cbore_depth=6.4)
    esit_hole(hm8, (55, 15, 20), d=6.75, depth=12.0, through=False)

    # Ø30 kör silindir dairesel cep olur
    assert len(f.pockets) == 1
    c = f.pockets[0]
    assert c.z_top == pytest.approx(20.0, abs=TOL)
    assert c.z_bottom == pytest.approx(10.0, abs=TOL)
    assert tam_daire_mi(c.region.outer, (70.0, 40.0), 15.0)
    assert c.region.outer.segments[0].ccw  # Region kuralı: dış CCW
    assert c.region.holes == []
    assert c.r_corner == pytest.approx(15.0, abs=TOL)


def test_hole_d_max_sinir():
    # hole_d_max Ø30'dan büyükse Ø30 kör silindir de delik olarak tanınır
    p = hole(blok(), 70, 40, 30, depth=10)
    part = Part(p.shape)  # kaydı düşür
    f = recognize(part, hole_d_max=40.0)
    assert f.pockets == ()
    assert len(f.holes) == 1
    esit_hole(f.holes[0].hole, (70, 40, 20), d=30.0, depth=10.0, through=False)


# ---------------------------------------------------------------- K7


def basamakli_parca() -> Part:
    # üst kenar boyunca (y ∈ [50, 60]) 10 mm genişlik, 5 mm derinlik basamak
    return tek_kati(blok().shape - bd.Pos(0, 50, 15) * bd.Box(A, 10, 6, align=bd.Align.MIN))


def test_acik_bolge():
    f = recognize(basamakli_parca())
    assert len(f.opens) == 1
    o = f.opens[0]
    assert isinstance(o, OpenFeature)
    assert (o.z_top, o.z_bottom) == (pytest.approx(20.0, abs=TOL), pytest.approx(15.0, abs=TOL))
    assert ayni_nokta_kumesi(kose_noktalari(o.boundary), dikdortgen(0, 0, A, B))  # E = parça kutusu
    assert len(o.islands) == 1
    ada = o.islands[0]
    assert len(ada.segments) == 4  # tam köşeler: 4 doğru
    assert ayni_nokta_kumesi(kose_noktalari(ada), dikdortgen(0, 0, A, 50))
    assert f.pockets == () and f.holes == ()


def test_acik_bolge_buyuk_stok():
    # stok xy'de parçadan büyük, üstü parça üstünde → yüz alma yok, iki açık bölge
    stok = Stock(-5, -5, 0, 105, 65, 20)
    f = recognize(basamakli_parca(), stok)
    assert f.faces == ()
    assert len(f.opens) == 2
    o1, o2 = f.opens  # z_top azalan
    E = dikdortgen(-5, -5, 105, 65)
    assert (o1.z_top, o1.z_bottom) == (pytest.approx(20.0, abs=TOL), pytest.approx(15.0, abs=TOL))
    assert (o2.z_top, o2.z_bottom) == (pytest.approx(15.0, abs=TOL), pytest.approx(0.0, abs=TOL))
    for o in (o1, o2):
        assert ayni_nokta_kumesi(kose_noktalari(o.boundary), E)
        assert len(o.islands) == 1
    assert ayni_nokta_kumesi(kose_noktalari(o1.islands[0]), dikdortgen(0, 0, A, 50))
    assert ayni_nokta_kumesi(kose_noktalari(o2.islands[0]), dikdortgen(0, 0, A, B))


# ---------------------------------------------------------------- K8


def t_kanalli_parca() -> Part:
    # üstten dar boyun (x ∈ [45, 55], z ∈ [10, 20]), altta geniş kanal (x ∈ [35, 65], z ∈ [4, 10]):
    # geniş kanalın tavanı z = 10'da −Z yüzü (alttan erişilen bölge)
    s = blok().shape - bd.Pos(45, -1, 10) * bd.Box(10, B + 2, 11, align=bd.Align.MIN)
    s = s - bd.Pos(35, -1, 4) * bd.Box(30, B + 2, 6, align=bd.Align.MIN)
    return tek_kati(s)


def uc_kademeli_delikli_parca() -> Part:
    # aynı eksende Ø6 (z ∈ [0, 8]), Ø10 (z ∈ [8, 14]), Ø14 (z ∈ [14, 20]); kayıt yok
    s = blok().shape
    for r, z0 in ((3.0, -1.0), (5.0, 8.0), (7.0, 14.0)):
        s = s - bd.Pos(50, 30, z0) * bd.Cylinder(r, C + 2 - z0, align=ALT)
    return tek_kati(s)


@pytest.mark.parametrize(
    "kur",
    [
        pytest.param(lambda: (chamfer_top(blok(), 1.0), None), id="pah-egik-duzlem"),
        pytest.param(lambda: (fillet_top(blok(), 2.0), None), id="ust-kenar-yuvarlatma"),
        pytest.param(lambda: (t_kanalli_parca(), None), id="t-kanal-alttan"),
        pytest.param(lambda: (blok(), Stock(0, 0, 0, 50, B, C)), id="stoktan-tasan"),
        pytest.param(lambda: (uc_kademeli_delikli_parca(), None), id="uc-kademeli-delik"),
    ],
)
def test_25d_degil(kur):
    part, stok = kur()
    with pytest.raises(CamError):
        recognize(part, stok)


@pytest.mark.parametrize(
    "kw",
    [
        {"tol": 0.0},
        {"tol": -1e-3},
        {"tol": math.nan},
        {"tol": math.inf},
        {"hole_d_max": 0.0},
        {"hole_d_max": -5.0},
        {"hole_d_max": math.nan},
    ],
)
def test_gecersiz_parametre(kw):
    with pytest.raises(CamError):
        recognize(blok(), **kw)


@pytest.mark.parametrize("girdi", [None, "parca", 42, Profile.rectangle(0, 0, 10, 10)])
def test_part_olmayan_girdi(girdi):
    with pytest.raises(CamError):
        recognize(girdi)


# ---------------------------------------------------------------- K9


def freze(D: float) -> Tool:
    return Tool(id=1, name=f"freze{D:g}", kind=ToolKind.FLAT, D=D, flute_length=30.0)


def test_cam_girdisi():
    f = recognize(k2_parca())
    p = f.pockets[0]
    takim = freze(8.0)
    assert takim.D <= p.max_tool_d  # Ø8 köşelere girer (2·r_corner = 10)
    kes = Cut(
        z_top=p.z_top,
        z_bottom=p.z_bottom,
        a_p=3.0,
        feed=600.0,
        plunge_feed=150.0,
        rpm=8000.0,
        z_safe=p.z_top + 5.0,
        stepover=3.0,
    )
    tp = ops2d.pocket(p.region, takim, kes)
    tp.validate()
    kesme = [m for m in tp.moves if m.type is not MoveType.RAPID]
    assert kesme
    P = np.array([m.end for m in kesme])
    assert P[:, 2].min() == pytest.approx(p.z_bottom, abs=TOL)
    # takım merkezi cep sınırından r = 4 içeride kalır (x ∈ [10, 50], y ∈ [15, 45])
    assert P[:, 0].min() >= 14 - TOL and P[:, 0].max() <= 46 + TOL
    assert P[:, 1].min() >= 19 - TOL and P[:, 1].max() <= 41 + TOL

    # max_tool_d'den büyük takım köşede artık bırakır; bu r_corner ile görünür
    assert freze(12.0).D > p.max_tool_d


def test_cam_girdisi_delik():
    part = hole(blok(), 80, 30, 8, depth=10)
    f = recognize(part)
    hf = f.holes[0]
    assert hf.top_access
    h = hf.hole
    x, y = float(h.origin[0]), float(h.origin[1])
    z_dip = float(h.origin[2]) - h.depth
    mv = hole_moves("G81", (0.0, 0.0, 30.0), x, y, z_dip, float(h.origin[2]) + 2.0, 30.0, 100.0)
    dalis = [m for m in mv if m.type is MoveType.LINEAR]
    assert len(dalis) == 1
    assert yakin(dalis[0].end, (80.0, 30.0, 10.0))
