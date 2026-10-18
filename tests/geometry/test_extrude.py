"""SPEC 26 K1–K3 — geometry/extrude.py: ekstrüzyon, ekleme / kesim, yüz düzlemi ve kenarları. OCCT gerektirir.

Testler SPEC 26 "Katı işlemler", "Arayüz" ve "Kabul kriterleri" bölümlerinden, sketch/model.py ve
geometry/part.py arayüzlerinden yazıldı; geometry/extrude.py gövdesi okunmadı. Beklenen hacimler kapalı
formdur (V = A · |d|). Bölgeler elle kurulur (dış döngü CCW, delikler CW; SPEC 17 kuralı).
Uydurma geometri: blok 100×60×20 (SPEC 02 koordinat kuralı: min köşe orijinde, üst yüz z = 20).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

import build123d as bd  # noqa: E402

from geometry.extrude import extrude, extrude_add, extrude_cut, face_outline, face_plane  # noqa: E402
from geometry.features import block, hole  # noqa: E402
from geometry.part import GeometryError, Part  # noqa: E402
from sketch.model import Plane, SegArc, SegLine, SketchRegion  # noqa: E402

pytestmark = pytest.mark.occt

REL = 1e-6  # hacim ve alan (SPEC 02 ile aynı)
KONUM = 1e-9  # mm
A, B, C = 100.0, 60.0, 20.0
V0 = A * B * C
S2 = 1.0 / math.sqrt(2.0)


# --- Yardımcılar --------------------------------------------------------------------------------------


def dikdortgen(x0: float, y0: float, w: float, h: float) -> tuple[SegLine, ...]:
    """CCW dikdörtgen döngü (uv)."""
    k = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    return tuple(SegLine(k[i], k[(i + 1) % 4]) for i in range(4))


def daire(cx: float, cy: float, r: float, ccw: bool) -> tuple[SegArc, ...]:
    """Tam daire döngüsü: tek SegArc, start = end."""
    s = (cx + r, cy)
    return (SegArc((cx, cy), r, s, s, ccw),)


def kanal(a: float, r: float) -> tuple:
    """Kanal (obround): merkezler (0, 0) ve (a, 0), yarıçap r; CCW."""
    return (
        SegLine((0.0, -r), (a, -r)),
        SegArc((a, 0.0), r, (a, -r), (a, r), True),
        SegLine((a, r), (0.0, r)),
        SegArc((0.0, 0.0), r, (0.0, r), (0.0, -r), True),
    )


def ust_duzlem(z: float = C) -> Plane:
    return Plane((0.0, 0.0, z), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))


def kutu(part: Part, lo, hi, tol: float = 1e-6) -> None:
    b0, b1 = part.bbox
    np.testing.assert_allclose(b0, lo, atol=tol)
    np.testing.assert_allclose(b1, hi, atol=tol)


def yuz(part: Part, normal, en_uc: str = "max"):
    """Verilen dışa normalli düzlemsel yüzlerden ağırlık merkezi normal yönünde en uçta olanı."""
    n = np.asarray(normal, float)
    adaylar = [f for f in part.planar_faces() if np.allclose(f.normal, n, atol=1e-9)]
    assert adaylar, f"normali {normal} olan yüz yok"
    return (
        max(adaylar, key=lambda f: float(f.origin @ n))
        if en_uc == "max"
        else min(adaylar, key=lambda f: float(f.origin @ n))
    )


def bas(seg) -> np.ndarray:
    return np.asarray(seg.p0 if isinstance(seg, SegLine) else seg.start, float)


def son(seg) -> np.ndarray:
    return np.asarray(seg.p1 if isinstance(seg, SegLine) else seg.end, float)


def isaretli_alan(dongu) -> float:
    """½ Σ (u_i v_{i+1} − u_{i+1} v_i) + Σ ½ r² (α − sin α); α döngü yönünde işaretli yay açısı."""
    A_ = 0.0
    for seg in dongu:
        s, e = bas(seg), son(seg)
        A_ += 0.5 * float(s[0] * e[1] - s[1] * e[0])
        if isinstance(seg, SegArc):
            c = np.asarray(seg.center, float)
            ts = math.atan2(s[1] - c[1], s[0] - c[0])
            te = math.atan2(e[1] - c[1], e[0] - c[0])
            tam = np.allclose(s, e, atol=1e-12)
            if seg.ccw:
                a = 2 * math.pi if tam else (te - ts) % (2 * math.pi)
            else:
                a = -2 * math.pi if tam else -((ts - te) % (2 * math.pi))
            A_ += 0.5 * seg.r**2 * (a - math.sin(a))
    return A_


def ters(dongu) -> tuple:
    out = []
    for seg in reversed(dongu):
        if isinstance(seg, SegLine):
            out.append(SegLine(seg.p1, seg.p0))
        else:
            out.append(SegArc(seg.center, seg.r, seg.end, seg.start, not seg.ccw))
    return tuple(out)


def kapali(dongu) -> bool:
    n = len(dongu)
    return all(np.allclose(son(dongu[i]), bas(dongu[(i + 1) % n]), atol=KONUM) for i in range(n))


# --- K1: ekstrüzyon -----------------------------------------------------------------------------------


def test_dikdortgen_hacim_ve_kutu():
    p = extrude([SketchRegion(dikdortgen(0, 0, 40, 30))], Plane.XY(), 10.0)
    assert isinstance(p, Part)
    assert p.volume == pytest.approx(12000.0, rel=REL)
    kutu(p, (0, 0, 0), (40, 30, 10))
    assert p.name == "govde"
    assert p.holes == ()


def test_ad_parametresi():
    assert extrude([SketchRegion(dikdortgen(0, 0, 4, 3))], Plane.XY(), 1.0, name="plaka").name == "plaka"


def test_delikli_dikdortgen_gercek_daire():
    """Dikdörtgen + r = 5 delik → (1200 − 25π)·10; delik çokgen değil gerçek silindir yüzü."""
    r = SketchRegion(dikdortgen(0, 0, 40, 30), (daire(20, 15, 5, ccw=False),))
    p = extrude([r], Plane.XY(), 10.0)
    assert p.volume == pytest.approx((1200 - 25 * math.pi) * 10, rel=REL)
    silindir = p.cylindrical_faces()
    assert len(silindir) >= 1
    assert all(f.radius == pytest.approx(5.0, rel=1e-9) for f in silindir)
    assert all(f.concave for f in silindir)


def test_kanal_hacmi():
    """SPEC 17 K6 kanalı: (2ra + πr²)·d."""
    a, r, d = 30.0, 5.0, 7.0
    p = extrude([SketchRegion(kanal(a, r))], Plane.XY(), d)
    assert p.volume == pytest.approx((2 * r * a + math.pi * r**2) * d, rel=REL)
    kutu(p, (-r, -r, 0), (a + r, r, d))


def test_birden_cok_bolge():
    bolgeler = [SketchRegion(dikdortgen(0, 0, 10, 10)), SketchRegion(daire(30, 5, 4, ccw=True))]
    # Ayrık iki gövde tek parçada olabilir ya da reddedilebilir; ama hacim sessizce yanlış olamaz.
    try:
        p = extrude(bolgeler, Plane.XY(), 2.0)
    except GeometryError:
        return
    assert p.volume == pytest.approx((100 + 16 * math.pi) * 2, rel=REL)


def test_egik_duzlem_hacim_ve_kutu():
    """Normal (0, 1, 1)/√2, xdir X: ydir = n × x = (0, 1, −1)/√2; kutu köşelerden analitik."""
    pl = Plane((0, 0, 0), (0, S2, S2), (1, 0, 0))
    p = extrude([SketchRegion(dikdortgen(0, 0, 40, 30))], pl, 10.0)
    assert p.volume == pytest.approx(12000.0, rel=REL)
    # y = (v + t)/√2 ∈ [0, 40/√2]; z = (t − v)/√2 ∈ [−30/√2, 10/√2]
    kutu(p, (0, 0, -30 * S2), (40, 40 * S2, 10 * S2))


def test_ofsetli_duzlem():
    pl = Plane((5, -3, 7), (0, 0, 1), (1, 0, 0))
    p = extrude([SketchRegion(dikdortgen(0, 0, 40, 30))], pl, 10.0)
    kutu(p, (5, -3, 7), (45, 27, 17))


def test_simetrik_duzleme_gore_ortalar():
    p = extrude([SketchRegion(dikdortgen(0, 0, 40, 30))], Plane.XY(), 10.0, symmetric=True)
    assert p.volume == pytest.approx(12000.0, rel=REL)
    kutu(p, (0, 0, -5), (40, 30, 5))


def test_negatif_mesafe_ters_yon():
    p = extrude([SketchRegion(dikdortgen(0, 0, 40, 30))], Plane.XY(), -10.0)
    assert p.volume == pytest.approx(12000.0, rel=REL)
    kutu(p, (0, 0, -10), (40, 30, 0))


def test_xz_duzlemi_normal_yonunde():
    """Plane.XZ normali −Y: d = 5 gövdeyi y ∈ [−5, 0]'a çıkarır."""
    p = extrude([SketchRegion(dikdortgen(0, 0, 40, 30))], Plane.XZ(), 5.0)
    assert p.volume == pytest.approx(6000.0, rel=REL)
    b0, b1 = p.bbox
    assert b0[1] == pytest.approx(-5.0, abs=1e-6)
    assert b1[1] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("d", [0.0, math.inf, -math.inf, math.nan])
def test_gecersiz_mesafe(d):
    with pytest.raises(GeometryError):
        extrude([SketchRegion(dikdortgen(0, 0, 40, 30))], Plane.XY(), d)


def test_bos_bolge_listesi():
    with pytest.raises(GeometryError):
        extrude([], Plane.XY(), 10.0)


# --- K2: ekle / kes -----------------------------------------------------------------------------------


def test_kor_kesim_ust_yuzden():
    p = block(A, B, C)
    q = extrude_cut(p, [SketchRegion(dikdortgen(30, 15, 40, 30))], ust_duzlem(), 8.0)
    assert q.volume == pytest.approx(V0 - 9600.0, rel=REL)
    kutu(q, (0, 0, 0), (A, B, C))
    assert p.volume == pytest.approx(V0, rel=1e-12)  # girdi değişmez


def test_boydan_boya_daire_kesimi():
    p = block(A, B, C)
    q = extrude_cut(p, [SketchRegion(daire(50, 30, 5, ccw=True))], ust_duzlem(), None)
    assert q.volume == pytest.approx(V0 - 25 * math.pi * 20, rel=REL)
    assert q.holes == ()  # kesim delik kaydı üretmez
    silindir = q.cylindrical_faces()
    assert len(silindir) >= 1 and all(f.radius == pytest.approx(5.0, rel=1e-9) for f in silindir)


def test_boss_ekleme():
    p = block(A, B, C)
    q = extrude_add(p, [SketchRegion(dikdortgen(40, 20, 20, 20))], ust_duzlem(), 15.0)
    assert q.volume == pytest.approx(V0 + 400 * 15, rel=REL)
    kutu(q, (0, 0, 0), (A, B, C + 15))
    assert p.volume == pytest.approx(V0, rel=1e-12)


def test_simetrik_ekleme():
    p = block(A, B, C)
    pl = Plane((A, 30, 10), (1, 0, 0), (0, 1, 0))  # sağ yan yüz, gövde düzlemin iki yanında
    q = extrude_add(p, [SketchRegion(dikdortgen(-5, -5, 10, 10))], pl, 8.0, symmetric=True)
    assert q.volume == pytest.approx(V0 + 100 * 4, rel=REL)
    kutu(q, (0, 0, 0), (A + 4, B, C))


def test_ayrik_ekleme_hata():
    p = block(A, B, C)
    with pytest.raises(GeometryError):
        extrude_add(p, [SketchRegion(dikdortgen(0, 0, 10, 10))], ust_duzlem(30.0), 5.0)
    with pytest.raises(GeometryError):
        extrude_add(p, [SketchRegion(dikdortgen(200, 0, 10, 10))], ust_duzlem(), 5.0)


def test_malzemesiz_kesim_hata():
    p = block(A, B, C)
    with pytest.raises(GeometryError):
        extrude_cut(p, [SketchRegion(dikdortgen(200, 0, 10, 10))], ust_duzlem(), 5.0)
    with pytest.raises(GeometryError):
        extrude_cut(p, [SketchRegion(dikdortgen(10, 10, 10, 10))], ust_duzlem(50.0), 5.0)


@pytest.mark.parametrize("islem", ["ekle", "kes"])
def test_ekle_kes_ortak_hatalar(islem):
    p = block(A, B, C)
    r = [SketchRegion(dikdortgen(10, 10, 10, 10))]
    with pytest.raises(GeometryError):
        extrude_add(p, [], ust_duzlem(), 5.0) if islem == "ekle" else extrude_cut(p, [], ust_duzlem(), 5.0)
    for d in (0.0, math.inf, math.nan):
        with pytest.raises(GeometryError):
            extrude_add(p, r, ust_duzlem(), d) if islem == "ekle" else extrude_cut(p, r, ust_duzlem(), d)


def test_delik_kayitlari_ekleme_ve_kesimden_gecer():
    p = hole(block(A, B, C), 10.0, 10.0, 6.0)
    assert len(p.holes) == 1
    q = extrude_cut(p, [SketchRegion(dikdortgen(40, 20, 20, 20))], ust_duzlem(), 5.0)
    assert q.holes == p.holes
    r = extrude_add(q, [SketchRegion(dikdortgen(70, 20, 10, 10))], ust_duzlem(), 5.0)
    assert r.holes == p.holes
    assert len(p.holes) == 1  # girdi kayıtları değişmez


def test_step_gidis_donus(tmp_path):
    p = block(A, B, C)
    q = extrude_cut(
        p, [SketchRegion(dikdortgen(30, 15, 40, 30), (daire(50, 30, 5, ccw=False),))], ust_duzlem(), 8.0
    )
    q = extrude_add(q, [SketchRegion(daire(15, 15, 6, ccw=True))], ust_duzlem(), 4.0)
    beklenen = V0 - (1200 - 25 * math.pi) * 8 + 36 * math.pi * 4
    assert q.volume == pytest.approx(beklenen, rel=REL)
    yol = tmp_path / "parca.step"
    q.to_step(yol)
    assert Part.from_step(yol).volume == pytest.approx(q.volume, rel=REL)


# --- K3: yüz düzlemi ve kenarlar ----------------------------------------------------------------------


def test_ust_yuz_duzlemi():
    p = block(A, B, C)
    f = yuz(p, (0, 0, 1))
    pl = face_plane(p, f.index)
    assert isinstance(pl, Plane)
    np.testing.assert_allclose(pl.normal, (0, 0, 1), atol=KONUM)
    np.testing.assert_allclose(pl.origin, (50, 30, 20), atol=KONUM)
    np.testing.assert_allclose(pl.xdir, (1, 0, 0), atol=KONUM)
    np.testing.assert_allclose(pl.ydir, (0, 1, 0), atol=KONUM)


@pytest.mark.parametrize(
    "normal, xdir",
    [
        ((-1, 0, 0), (0, 1, 0)),  # dünya X'in izdüşümü sıfır → dünya Y
        ((1, 0, 0), (0, 1, 0)),
        ((0, -1, 0), (1, 0, 0)),
        ((0, 0, -1), (1, 0, 0)),
    ],
)
def test_yan_ve_alt_yuz_xdir_kurali(normal, xdir):
    p = block(A, B, C)
    f = yuz(p, normal)
    pl = face_plane(p, f.index)
    np.testing.assert_allclose(pl.normal, normal, atol=KONUM)
    np.testing.assert_allclose(pl.xdir, xdir, atol=KONUM)
    np.testing.assert_allclose(pl.origin, f.origin, atol=KONUM)


def test_egik_yuz_xdir_izdusum():
    pl0 = Plane((0, 0, 0), (0, S2, S2), (1, 0, 0))
    p = extrude([SketchRegion(dikdortgen(0, 0, 40, 30))], pl0, 10.0)
    f = yuz(p, (0, S2, S2))
    pl = face_plane(p, f.index)
    np.testing.assert_allclose(pl.normal, (0, S2, S2), atol=KONUM)
    np.testing.assert_allclose(pl.xdir, (1, 0, 0), atol=KONUM)
    # üst yüz: düzlem + 10·n, ağırlık merkezi (20, 15) uv'de
    np.testing.assert_allclose(pl.origin, pl0.to_world((20, 15)) + 10 * pl0.normal, atol=KONUM)


def test_delikli_yuz_agirlik_merkezi():
    p = hole(block(A, B, C), 30.0, 20.0, 10.0)
    A1, A2 = A * B, 25 * math.pi
    cx = (A1 * 50 - A2 * 30) / (A1 - A2)
    cy = (A1 * 30 - A2 * 20) / (A1 - A2)
    pl = face_plane(p, yuz(p, (0, 0, 1)).index)
    np.testing.assert_allclose(pl.origin, (cx, cy, 20.0), atol=1e-6)


def test_ust_yuz_dikdortgen_dongusu():
    p = block(A, B, C)
    dongular = face_outline(p, yuz(p, (0, 0, 1)).index)
    assert len(dongular) == 1
    d = dongular[0]
    assert len(d) == 4 and all(isinstance(s, SegLine) for s in d)
    assert kapali(d)
    koseler = sorted(tuple(np.round(bas(s), 9)) for s in d)
    beklenen = sorted([(-50.0, -30.0), (50.0, -30.0), (50.0, 30.0), (-50.0, 30.0)])
    np.testing.assert_allclose(koseler, beklenen, atol=KONUM)
    assert abs(isaretli_alan(d)) == pytest.approx(A * B, rel=1e-12)


def test_delikli_yuzde_daire_tek_segarc():
    p = hole(block(A, B, C), 30.0, 20.0, 10.0)
    i = yuz(p, (0, 0, 1)).index
    pl = face_plane(p, i)
    dongular = face_outline(p, i)
    assert len(dongular) == 2
    daireler = [d for d in dongular if len(d) == 1]
    assert len(daireler) == 1
    (s,) = daireler[0]
    assert isinstance(s, SegArc)
    assert s.r == pytest.approx(5.0, rel=1e-9)
    np.testing.assert_allclose(s.start, s.end, atol=KONUM)
    np.testing.assert_allclose(pl.to_world(s.center), (30, 20, 20), atol=KONUM)
    dis = [d for d in dongular if len(d) != 1][0]
    assert kapali(dis) and all(isinstance(x, SegLine) for x in dis)


def _dongulerden_bolge(dongular) -> SketchRegion:
    """En büyük |alan|lı döngü dış (CCW), diğerleri delik (CW)."""
    sirali = sorted(dongular, key=lambda d: abs(isaretli_alan(d)), reverse=True)
    dis = sirali[0] if isaretli_alan(sirali[0]) > 0 else ters(sirali[0])
    delikler = tuple(d if isaretli_alan(d) < 0 else ters(d) for d in sirali[1:])
    return SketchRegion(dis, delikler)


@pytest.mark.parametrize("delikli", [False, True])
def test_kenarlardan_eskiz_alani_yuz_alani(delikli):
    p = block(A, B, C)
    if delikli:
        p = hole(p, 30.0, 20.0, 10.0)
    f = yuz(p, (0, 0, 1))
    pl = face_plane(p, f.index)
    r = _dongulerden_bolge(face_outline(p, f.index))
    q = extrude([r], pl, 2.0)
    assert q.volume == pytest.approx(f.area * 2.0, rel=REL)
    assert q.bbox[0][2] == pytest.approx(C, abs=1e-6)


def test_silindirik_yuz_hata():
    p = hole(block(A, B, C), 30.0, 20.0, 10.0)
    i = p.cylindrical_faces()[0].index
    with pytest.raises(GeometryError):
        face_plane(p, i)
    with pytest.raises(GeometryError):
        face_outline(p, i)


@pytest.mark.parametrize("i", [-1, 6, 9999])
def test_bilinmeyen_yuz_hata(i):
    p = block(A, B, C)
    with pytest.raises(GeometryError):
        face_plane(p, i)


def test_elips_kenar_sessiz_yaklasim_yok():
    """Doğru ve daire dışı kenar (elips) → GeometryError."""
    p = Part(bd.extrude(bd.Ellipse(10, 5), 5), name="elips")
    f = yuz(p, (0, 0, 1))
    face_plane(p, f.index)  # düzlemsel: düzlem tanımlı
    with pytest.raises(GeometryError):
        face_outline(p, f.index)
