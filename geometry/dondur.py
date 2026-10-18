"""
SPEC 18 — Döndürme (revolve) takım gövdesi ve yüz adları; kesit bölgesinden OCCT yüzü kurma.

Kesit bölgeleri (SPEC 17 `SketchRegion`, uv) eskiz düzlemindeki bir eksen etrafında döner. Hacim Pappus:
V = θ · ρ̄ · A. Bölge ekseni kesmez; eksene değen kenar yüzey üretmez. Yan yüzler `yan:<src>`, açı < 360°
ise kapaklar `bas`, `son` adını alır. `geometry/revolve.py` SPEC 28'indir; bu dosya ondan bağımsızdır.
Yeni kurulan gövdede yüzler kesit kenarlarıyla OCCT `Generated` geçmişinden eşlenir (belirsizlik yok).
Birimler: mm, derece.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import build123d as bd
import numpy as np
from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from geometry.part import GeometryError, Part
from sketch.model import Plane, SegArc, SegLine, SketchRegion

TOL_ESLEME = 1e-7  # mm: yüz kenarını kesit kenarına eşlerken orta nokta uzaklığı
TOL_EKSEN = 1e-9  # mm: eksene değen nokta (ρ = 0) sayılır


def _altlar(shape, tur, cevir) -> list:
    """shape içindeki tekrarsız alt şekiller (TopExp sırası), türüne indirgenmiş."""
    sonuc = []
    ex = TopExp_Explorer(shape, tur)
    while ex.More():
        s = cevir(ex.Current())
        if not any(s.IsSame(t) for t in sonuc):
            sonuc.append(s)
        ex.Next()
    return sonuc


def yuzler(shape) -> list:
    return _altlar(shape, TopAbs_FACE, TopoDS.Face)


def kenarlar(shape) -> list:
    return _altlar(shape, TopAbs_EDGE, TopoDS.Edge)


def _yay_acilari(s: SegArc) -> tuple[float, float]:
    """Yayın başlangıç ve bitiş açısı (uv, radyan); ccw ise a1 > a0, değilse a1 < a0."""
    a0 = math.atan2(*(s.start - s.center)[::-1])
    a1 = math.atan2(*(s.end - s.center)[::-1])
    if s.ccw:
        while a1 <= a0:
            a1 += 2 * math.pi
    else:
        while a1 >= a0:
            a1 -= 2 * math.pi
    return a0, a1


def _tam_daire(s: SegArc) -> bool:
    return bool(np.allclose(s.start, s.end, rtol=0, atol=1e-12))


def _orta_uv(s) -> np.ndarray:
    """Kenarın uv'deki orta noktası (tam dairede başlangıcın karşısı)."""
    if isinstance(s, SegLine):
        return 0.5 * (s.p0 + s.p1)
    if _tam_daire(s):
        return 2 * s.center - s.start
    a0, a1 = _yay_acilari(s)
    m = 0.5 * (a0 + a1)
    return s.center + s.r * np.array([math.cos(m), math.sin(m)])


def _kenar(s, P, plane: Plane) -> bd.Edge:
    """Kesit kenarını dünya koordinatında OCCT kenarına çevirir (yay gerçek daire kenarıdır)."""
    if isinstance(s, SegLine):
        if np.allclose(s.p0, s.p1, rtol=0, atol=1e-12):
            raise GeometryError("kesit: sıfır boylu doğru parçası")
        return bd.Edge.make_line(bd.Vector(*P(s.p0)), bd.Vector(*P(s.p1)))
    if _tam_daire(s):
        cerceve = bd.Plane(origin=bd.Vector(*P(s.center)), x_dir=tuple(plane.xdir), z_dir=tuple(plane.normal))
        return bd.Edge.make_circle(s.r, cerceve)
    return bd.Edge.make_three_point_arc(*(bd.Vector(*P(q)) for q in (s.start, _orta_uv(s), s.end)))


def profil_yuzleri(
    regions: Sequence[SketchRegion], plane: Plane, kaydir=(0.0, 0.0, 0.0)
) -> tuple[list[bd.Face], list[tuple[object, str]]]:
    """Bölgeleri düzlemde (kaydir kadar ötelenmiş) OCCT yüzlerine çevirir.

    Dönüş: yüzler ve (yüz kenarı TopoDS_Edge, src) çiftleri. Eşleme yeni yüzde geometriktir (orta nokta).
    """
    regions = list(regions)
    if not regions:
        raise GeometryError("kesit: bölge listesi boş")
    k = np.asarray(kaydir, dtype=float)

    def P(uv):
        return plane.to_world(uv) + k

    yuz_listesi, eslesme = [], []
    for reg in regions:
        if not isinstance(reg, SketchRegion) or not reg.outer:
            raise GeometryError(f"kesit: geçersiz bölge ({reg!r})")
        halkalar = [reg.outer, *reg.holes]
        try:
            teller = [bd.Wire([_kenar(s, P, plane) for s in h]) for h in halkalar]
            yuz = bd.Face(teller[0], teller[1:])
        except GeometryError:
            raise
        except Exception as e:  # OCCT istisnası
            raise GeometryError(f"kesit yüzü kurulamadı ({e})") from e
        if not yuz.is_valid or yuz.area <= 0:
            raise GeometryError("kesit yüzü geçersiz")
        segler = [s for h in halkalar for s in h]
        for e in kenarlar(yuz.wrapped):
            orta = bd.Edge(e).position_at(0.5)
            o = np.array([orta.X, orta.Y, orta.Z])
            for s in segler:
                if isinstance(s, SegArc) and _tam_daire(s):
                    c = P(s.center)
                    uz = abs(np.linalg.norm(o - c) - s.r) + abs(float((o - c) @ plane.normal))
                else:
                    uz = float(np.linalg.norm(o - P(_orta_uv(s))))
                if uz < TOL_ESLEME:
                    eslesme.append((e, s.src))
                    break
        yuz_listesi.append(yuz)
    return yuz_listesi, eslesme


def uretilen(op, shape) -> list:
    sonuc = []
    for s in op.Generated(shape):
        sonuc += yuzler(s) if s.ShapeType() != TopAbs_FACE else [TopoDS.Face(s)]
    return sonuc


def _eksende(s, p: np.ndarray, y: np.ndarray) -> bool:
    """Doğru parçası eksen üzerinde mi (iki ucu da)?"""
    if not isinstance(s, SegLine):
        return False
    return all(abs(y[0] * (q[1] - p[1]) - y[1] * (q[0] - p[0])) <= TOL_EKSEN for q in (s.p0, s.p1))


def _isaret_kontrol(regions: Sequence[SketchRegion], p: np.ndarray, y: np.ndarray) -> None:
    """Bölgelerin hepsi eksenin aynı yanında olmalı (eksene değmek serbest)."""
    isaretler = []
    for reg in regions:
        for halka in (reg.outer, *reg.holes):
            for s in halka:
                if isinstance(s, SegLine):
                    noktalar = [s.p0, s.p1]
                else:
                    if _tam_daire(s):
                        a0, a1 = 0.0, 2 * math.pi
                    else:
                        a0, a1 = _yay_acilari(s)
                    t = np.linspace(a0, a1, 721)
                    noktalar = list(s.center + s.r * np.c_[np.cos(t), np.sin(t)])
                for q in noktalar:
                    d = y[0] * (q[1] - p[1]) - y[1] * (q[0] - p[0])
                    if abs(d) > TOL_EKSEN:
                        isaretler.append(d > 0)
    if not isaretler:
        raise GeometryError("döndürme: bölge eksen üzerinde (alan sıfır)")
    if any(isaretler) and not all(isaretler):
        raise GeometryError("döndürme: bölge ekseni kesiyor")


def dondur_arac(
    regions: Sequence[SketchRegion],
    plane: Plane,
    eksen_p: tuple[float, float],
    eksen_y: tuple[float, float],
    aci: float = 360.0,
):
    """Döndürme gövdesi (TopoDS_Shape) ve yerel adlar {ad: [TopoDS_Face]} (ağacın iç işi)."""
    p = np.asarray(eksen_p, dtype=float)
    y = np.asarray(eksen_y, dtype=float)
    if p.shape != (2,) or y.shape != (2,) or not (np.all(np.isfinite(p)) and np.all(np.isfinite(y))):
        raise GeometryError(f"döndürme: eksen (u, v) sonlu olmalı ({eksen_p}, {eksen_y})")
    if np.linalg.norm(y) < 1e-12:
        raise GeometryError("döndürme: eksen yönü sıfır")
    if not (math.isfinite(aci) and 0 < aci <= 360):
        raise GeometryError(f"döndürme: aci ∈ (0, 360] olmalı ({aci})")
    y = y / np.linalg.norm(y)
    regions = list(regions)
    if not regions:
        raise GeometryError("döndürme: bölge listesi boş")
    _isaret_kontrol(regions, p, y)
    yuz_listesi, _ = profil_yuzleri(regions, plane)
    P = plane.to_world(p)
    D = y[0] * plane.xdir + y[1] * plane.ydir
    kaynak = bd.Compound(yuz_listesi).wrapped if len(yuz_listesi) > 1 else yuz_listesi[0].wrapped
    try:
        op = BRepPrimAPI_MakeRevol(kaynak, gp_Ax1(gp_Pnt(*P), gp_Dir(*D)), math.radians(aci))
        govde = op.Shape()
    except Exception as e:
        raise GeometryError(f"döndürme: OCCT başarısız ({e})") from e
    sonuc_yuzleri = yuzler(govde)

    def var(f) -> bool:
        return any(f.IsSame(g) for g in sonuc_yuzleri)

    kapaklar = [] if aci >= 360 else [yuzler(op.FirstShape()), yuzler(op.LastShape())]
    kapak_yuzleri = [f for fs in kapaklar for f in fs]
    # Yan yüz eşlemesi: kenarın orta noktası eksen etrafında aci/2 döndürülünce yalnız o kenarın ürettiği
    # yüzün içine düşer (yeni gövde, belirsizlik yok). OCCT `Generated` eksene dik doğrularda boş döner.
    phi = math.radians(aci / 2)
    K = np.array([[0, -D[2], D[1]], [D[2], 0, -D[0]], [-D[1], D[0], 0]])
    R = np.eye(3) + math.sin(phi) * K + (1 - math.cos(phi)) * (K @ K)
    adlar: dict[str, list] = {}
    for reg in regions:
        for halka in (reg.outer, *reg.holes):
            for sg in halka:
                if not sg.src or _eksende(sg, p, y):
                    continue
                q = R @ (plane.to_world(_orta_uv(sg)) - P) + P
                nokta = bd.Vertex(*q)
                for f in sonuc_yuzleri:
                    if any(f.IsSame(c) for c in kapak_yuzleri):
                        continue
                    if bd.Face(f).distance_to(nokta) < TOL_ESLEME:
                        adlar.setdefault(f"yan:{sg.src}", []).append(f)
    if aci < 360:
        for ad, s in (("bas", op.FirstShape()), ("son", op.LastShape())):
            fs = [f for f in yuzler(s) if var(f)]
            if fs:
                adlar[ad] = fs
    return govde, adlar


def _part(govde, adlar: dict[str, list], name: str) -> Part:
    """Adlı TopoDS gövdesini Part'a çevirir (adlar: FaceRef(name, yerel ad))."""
    from geometry.part import FaceRef

    sekil = bd.Solid(govde) if govde.ShapeType().name == "TopAbs_SOLID" else bd.Compound(govde)
    if isinstance(sekil, bd.Compound):
        katilar = list(sekil.solids())
        if len(katilar) == 1:
            sekil = katilar[0]
    tum = [f.wrapped for f in sekil.faces()]
    names = {}
    for ad, fs in adlar.items():
        idx = sorted({i for i, g in enumerate(tum) for f in fs if g.IsSame(f)})
        if idx:
            names[FaceRef(name, ad)] = tuple(idx)
    return Part(sekil, name=name, names=names)


def revolve(
    regions: Sequence[SketchRegion],
    plane: Plane,
    eksen_p: tuple[float, float],
    eksen_y: tuple[float, float],
    aci: float = 360.0,
    name: str = "dondurme",
) -> Part:
    """Bölgeleri uv'de `eksen_p` noktasından geçen `eksen_y` yönlü eksen etrafında `aci` derece döndürür.

    Dönen gövde adlıdır (FaceRef(name, yerel ad)). Hatalar (`GeometryError`): boş bölge, ekseni kesen
    bölge, aci ∉ (0, 360], |eksen_y| = 0, sonsuz değer.
    """
    govde, adlar = dondur_arac(regions, plane, eksen_p, eksen_y, aci)
    return _part(govde, adlar, name)
