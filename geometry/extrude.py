"""
SPEC 26 — eskiz bölgesi + düzlem → OCCT katı: ekstrüzyon, ekleme, kesim; yüz düzlemi ve kenarları.

Bölgeler `sketch.model.SketchRegion` (uv, yaylar tam yay). Düzlem `sketch.model.Plane`:
P = origin + u·xdir + v·ydir. Yay ve daireler gerçek daire kenarıdır (çokgen yaklaşımı yok).
Bu modül `sketch`'ten yalnızca `sketch.model`'i import eder (K13).
"""

from __future__ import annotations

import math

import build123d as bd
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line

from geometry.boolean import V_BOS
from geometry.features import PAY
from geometry.part import GeometryError, Part
from sketch.model import Plane, SegArc, SegLine, SketchRegion

Seg = SegLine | SegArc
UC_TOL = 1e-6  # mm: kenar uçlarını döngüde eşleme toleransı


# --- Bölge → OCCT yüz ---------------------------------------------------------------------------------


def _bd_plane(plane: Plane, origin=None) -> bd.Plane:
    o = plane.origin if origin is None else origin
    return bd.Plane(origin=tuple(o), x_dir=tuple(plane.xdir), z_dir=tuple(plane.normal))


def _dunya(plane: Plane, uv) -> bd.Vector:
    u, v = float(uv[0]), float(uv[1])
    return bd.Vector(*(plane.origin + u * plane.xdir + v * plane.ydir))


def _kenar(seg: Seg, plane: Plane) -> bd.Edge:
    if isinstance(seg, SegLine):
        return bd.Edge.make_line(_dunya(plane, seg.p0), _dunya(plane, seg.p1))
    c, s, e = (np.asarray(x, float) for x in (seg.center, seg.start, seg.end))
    if np.allclose(s, e, atol=1e-12):
        return bd.Edge.make_circle(seg.r, _bd_plane(plane, _dunya(plane, c)))
    ts = math.atan2(s[1] - c[1], s[0] - c[0])
    te = math.atan2(e[1] - c[1], e[0] - c[0])
    a = (te - ts) % (2 * math.pi) if seg.ccw else -((ts - te) % (2 * math.pi))
    tm = ts + a / 2
    m = c + seg.r * np.array([math.cos(tm), math.sin(tm)])
    return bd.Edge.make_three_point_arc(_dunya(plane, s), _dunya(plane, m), _dunya(plane, e))


def _tel(dongu: tuple[Seg, ...], plane: Plane) -> bd.Wire:
    if not dongu:
        raise GeometryError("Boş döngü")
    return bd.Wire([_kenar(s, plane) for s in dongu])


def _yuz(region: SketchRegion, plane: Plane) -> bd.Face:
    try:
        f = bd.Face(_tel(region.outer, plane), [_tel(h, plane) for h in region.holes])
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"Bölge yüze çevrilemedi ({e})") from e
    if not f.is_valid or f.area <= 0:
        raise GeometryError("Bölge geçersiz yüz verdi")
    return f


def _sonlu(d: float, ne: str) -> float:
    d = float(d)
    if not math.isfinite(d) or d == 0.0:
        raise GeometryError(f"{ne}: sonlu ve sıfırdan farklı olmalı ({d})")
    return d


def _govde(regions: list[SketchRegion], plane: Plane, distance: float, symmetric: bool):
    """Bölgelerin ekstrüzyonu (build123d şekli)."""
    if not regions:
        raise GeometryError("Ekstrüzyon: bölge listesi boş")
    distance = _sonlu(distance, "Ekstrüzyon mesafesi")
    n = bd.Vector(*plane.normal)
    katilar = []
    for r in regions:
        f = _yuz(r, plane)
        if symmetric:
            katilar.append(bd.extrude(f, amount=abs(distance) / 2, dir=n, both=True))
        else:
            katilar.append(bd.extrude(f, amount=abs(distance), dir=n if distance > 0 else -n))
    if len(katilar) == 1:
        return katilar[0]
    return bd.Compound([s for k in katilar for s in k.solids()])


# --- Arayüz -------------------------------------------------------------------------------------------


def extrude(
    regions: list[SketchRegion], plane: Plane, distance: float, symmetric: bool = False, name: str = "govde"
) -> Part:
    """Bölgeleri düzlem normali yönünde `distance` kadar (işaretli) çeker; simetrikte iki yana distance/2.

    Boş bölge listesi, distance = 0, sonsuz değer → GeometryError.
    """
    return Part(_govde(regions, plane, distance, symmetric), name=name)


def extrude_add(
    part: Part, regions: list[SketchRegion], plane: Plane, distance: float, symmetric: bool = False
) -> Part:
    """Ekstrüzyonu parçaya ekler; sonuç tek katı olmalı, değmiyorsa GeometryError ("ayrık katı").
    Girdi parça değişmez; Part.holes kayıtları korunur."""
    arac = extrude(regions, plane, distance, symmetric, name=part.name)
    sonuc = part.fuse(arac)
    if len(sonuc.shape.solids()) != 1:
        raise GeometryError(f"Ekleme: yeni gövde '{part.name}' parçasına değmiyor (ayrık katı)")
    return sonuc


def extrude_cut(part: Part, regions: list[SketchRegion], plane: Plane, depth: float | None) -> Part:
    """Bölgeleri −normal yönünde `depth` kadar keser; None = boydan boya (+PAY üstten, köşegen + PAY).
    Malzeme kaldırmıyorsa (ΔV ≤ 1e-9 mm³) GeometryError. Girdi değişmez; kesim delik kaydı üretmez."""
    if depth is None:
        b0, b1 = part.bbox
        boy = float(np.linalg.norm(b1 - b0)) + PAY
    else:
        depth = _sonlu(depth, "Kesim derinliği")
        if depth < 0:
            raise GeometryError(f"Kesim derinliği pozitif olmalı ({depth})")
        boy = depth
    ust = Plane(plane.origin + PAY * plane.normal, plane.normal, plane.xdir)
    arac = extrude(regions, ust, -(boy + PAY), name="kesici")
    try:
        sonuc = part.cut(arac)
    except GeometryError as e:
        raise GeometryError(f"Kesim: {e}") from None
    if part.volume - sonuc.volume <= V_BOS:
        raise GeometryError(f"Kesim: '{part.name}' parçasından malzeme kaldırmıyor")
    return sonuc


def _duzlemsel(part: Part, index: int):
    yuzler = list(part.shape.faces())
    if not (isinstance(index, int) and 0 <= index < len(yuzler)):
        raise GeometryError(f"Bilinmeyen yüz: {index} ('{part.name}' parçasında {len(yuzler)} yüz var)")
    f = next((f for f in part.planar_faces() if f.index == index), None)
    if f is None:
        raise GeometryError(f"Yüz {index} düzlemsel değil")
    return f, yuzler[index]


def face_plane(part: Part, index: int) -> Plane:
    """Düzlemsel yüzün düzlemi: origin ağırlık merkezi, normal dışa, xdir dünya X'in izdüşümü
    (|izdüşüm| < 1e-6 ise dünya Y). Düzlemsel olmayan / bilinmeyen index → GeometryError."""
    f, _ = _duzlemsel(part, index)
    n = f.normal / np.linalg.norm(f.normal)
    for eksen in (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])):
        x = eksen - (eksen @ n) * n
        if np.linalg.norm(x) >= 1e-6:
            return Plane(f.origin, n, x / np.linalg.norm(x))
    raise GeometryError(f"Yüz {index}: xdir kurulamadı")  # n hem X hem Y'ye paralel olamaz


def _uv(plane: Plane, p) -> tuple[float, float]:
    d = np.array([p.X, p.Y, p.Z]) - plane.origin
    return (float(d @ plane.xdir), float(d @ plane.ydir))


def _segment(kenar: bd.Edge, plane: Plane, ileri: bool) -> Seg:
    """Kenarı döngü yönünde (ileri: kenarın kendi parametre yönü) uv segmentine çevirir."""
    egri = BRepAdaptor_Curve(kenar.wrapped)
    t0, t1 = egri.FirstParameter(), egri.LastParameter()
    s, e = (t0, t1) if ileri else (t1, t0)

    def nokta(t):
        return _uv(plane, bd.Vector(*egri.Value(t).Coord()))

    tur = egri.GetType()
    if tur == GeomAbs_Line:
        return SegLine(nokta(s), nokta(e))
    if tur == GeomAbs_Circle:
        daire = egri.Circle()
        c = _uv(plane, bd.Vector(*daire.Location().Coord()))
        r = float(daire.Radius())
        ps, pm = np.array(nokta(s)), np.array(nokta(s + 0.25 * (e - s)))
        yon = (ps[0] - c[0]) * (pm[1] - c[1]) - (ps[1] - c[1]) * (pm[0] - c[0])
        pe = tuple(ps) if kenar.is_closed else nokta(e)
        return SegArc(c, r, tuple(ps), pe, bool(yon > 0))
    raise GeometryError("Yüz kenarı doğru ya da daire değil; sessiz yaklaşım yapılmaz")


def _dongu(tel: bd.Wire, plane: Plane) -> tuple[Seg, ...]:
    """Teli uç noktaları eşleyerek sıralı, yönlü segmentlere çevirir."""
    kalan = list(tel.edges())
    if len(kalan) == 1:
        return (_segment(kalan[0], plane, True),)

    def uclar(k):
        egri = BRepAdaptor_Curve(k.wrapped)
        return tuple(
            np.array(_uv(plane, bd.Vector(*egri.Value(t).Coord())))
            for t in (egri.FirstParameter(), egri.LastParameter())
        )

    k0 = kalan.pop(0)
    a, b = uclar(k0)
    # ilk kenarın yönü: sonu bir sonraki kenara bağlanmalı
    ileri = any(np.linalg.norm(b - q) <= UC_TOL for k in kalan for q in uclar(k))
    out = [_segment(k0, plane, ileri)]
    uc = b if ileri else a
    while kalan:
        for i, k in enumerate(kalan):
            p, q = uclar(k)
            if np.linalg.norm(p - uc) <= UC_TOL or np.linalg.norm(q - uc) <= UC_TOL:
                yon = bool(np.linalg.norm(p - uc) <= UC_TOL)
                out.append(_segment(k, plane, yon))
                uc = q if yon else p
                kalan.pop(i)
                break
        else:
            raise GeometryError("Yüz kenarları kapalı bir döngü oluşturmuyor")
    return tuple(out)


def face_outline(part: Part, index: int) -> list[tuple[Seg, ...]]:
    """Yüzün kenar döngüleri face_plane uv'sinde (SegLine / SegArc; tam daire tek SegArc).
    Doğru ve daire dışı kenar → GeometryError."""
    plane = face_plane(part, index)
    _, yuz = _duzlemsel(part, index)
    return [_dongu(t, plane) for t in [yuz.outer_wire(), *yuz.inner_wires()]]
