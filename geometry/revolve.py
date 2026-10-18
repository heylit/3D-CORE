"""
Eksenden geçen yarı düzlem kesiti, yüz sınıflama ve otomatik eksen (SPEC 28).

Arayüz geometry/part.py'dedir (Part.axial_section, SectionEdge, SectionFace, AxialSection); diğer paketler
bu dosyayı import etmez. Burada yalnız kesit alınır ve yüzler sınıflanır; doğrulama, bağlama, uydurma ve
dış / iç profil bölmesi cam/turn_profile.py'dedir. Koordinatlar (z, x): z = (p − origin)·axis,
x = (p − origin)·xdir. Birimler: mm.
"""

from __future__ import annotations

import math

import numpy as np

from geometry.part import AxialSection, GeometryError, Part, SectionEdge, SectionFace

try:
    import build123d as bd
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.GeomAbs import (
        GeomAbs_Circle,
        GeomAbs_Cone,
        GeomAbs_Cylinder,
        GeomAbs_Line,
        GeomAbs_Plane,
        GeomAbs_Sphere,
        GeomAbs_SurfaceOfRevolution,
        GeomAbs_Torus,
    )
except ImportError:  # pragma: no cover - build123d kurulu değilse Part zaten hata verir
    pass

D_TOL = 1e-7  # mm: eksen doğruları arası uzaklık / merkezin eksene uzaklığı
A_TOL = 1e-9  # rad: yön paralelliği


def _vektor(v) -> np.ndarray:
    return np.array([v.X(), v.Y(), v.Z()], dtype=float)


def _vec3(v, ad: str) -> np.ndarray:
    try:
        a = np.asarray(v, dtype=float).reshape(-1)
    except (TypeError, ValueError) as e:
        raise GeometryError(f"{ad} 3 bileşenli sayı vektörü olmalı: {v!r}") from e
    if a.shape != (3,) or not np.all(np.isfinite(a)):
        raise GeometryError(f"{ad} 3 bileşenli sonlu vektör olmalı: {v!r}")
    return a


def _paralel(u: np.ndarray, v: np.ndarray) -> bool:
    """Birim u, v paralel (aynı ya da ters yön) mi: |u × v| ≤ A_TOL."""
    return float(np.linalg.norm(np.cross(u, v))) <= A_TOL


def _dogruya_uzaklik(p: np.ndarray, o: np.ndarray, a: np.ndarray) -> float:
    """p noktasının o + s·a doğrusuna uzaklığı (a birim)."""
    d = p - o
    return float(np.linalg.norm(d - (d @ a) * a))


def _yuz_ekseni(yuz):
    """Yüz türü ve ekseni: ("eksen", o, a) | ("duzlem", o, n) | ("kure", c) | ("bilinmiyor",)."""
    s = BRepAdaptor_Surface(yuz.wrapped)
    t = s.GetType()
    if t == GeomAbs_Plane:
        ax = s.Plane().Axis()
        return ("duzlem", _vektor(ax.Location()), _vektor(ax.Direction()))
    if t == GeomAbs_Cylinder:
        ax = s.Cylinder().Axis()
    elif t == GeomAbs_Cone:
        ax = s.Cone().Axis()
    elif t == GeomAbs_Torus:
        ax = s.Torus().Axis()
    elif t == GeomAbs_SurfaceOfRevolution:
        ax = s.AxeOfRevolution()
    elif t == GeomAbs_Sphere:
        return ("kure", _vektor(s.Sphere().Location()))
    else:
        return ("bilinmiyor",)
    return ("eksen", _vektor(ax.Location()), _vektor(ax.Direction()))


def _siniflar(part: Part) -> list[tuple]:
    return [_yuz_ekseni(y) for y in part.shape.faces()]


def _otomatik_eksen(siniflar: list[tuple]) -> tuple[np.ndarray, np.ndarray]:
    """Dönel yüzlerin ortak ekseni; en büyük |bileşen| pozitif; origin: orijinin eksene izdüşümü."""
    eksenler: list[tuple[np.ndarray, np.ndarray]] = []
    for k in siniflar:
        if k[0] != "eksen":
            continue
        o, a = k[1], k[2] / np.linalg.norm(k[2])
        if not any(_paralel(a, b) and _dogruya_uzaklik(o, p, b) <= D_TOL for p, b in eksenler):
            eksenler.append((o, a))
    if not eksenler:
        raise GeometryError("otomatik eksen bulunamadı: parçada eksenli dönel yüz yok; ekseni açık verin")

    def yaz(o, a):
        p = o - (o @ a) * a  # orijine en yakın eksen noktası
        return f"nokta ({p[0]:g}, {p[1]:g}, {p[2]:g}), yön ({a[0]:g}, {a[1]:g}, {a[2]:g})"

    if len(eksenler) > 1:
        liste = "; ".join(yaz(o, a) for o, a in eksenler)
        raise GeometryError(
            f"otomatik eksen belirsiz: {len(eksenler)} farklı eksen var ({liste}); ekseni açık verin"
        )
    o, a = eksenler[0]
    if a[int(np.argmax(np.abs(a)))] < 0:
        a = -a
    origin = o - (o @ a) * a
    for k in siniflar:
        if k[0] == "kure" and _dogruya_uzaklik(k[1], origin, a) > D_TOL:
            raise GeometryError(
                f"otomatik eksen belirsiz: küre merkezi {tuple(k[1])} eksen ({yaz(o, a)}) üzerinde değil"
            )
    return origin, a


def _donel_mi(k: tuple, o: np.ndarray, a: np.ndarray) -> bool | None:
    """Yüz bu eksene göre dönel mi; bilinmiyorsa None (SPEC 28 sınıflama tablosu)."""
    if k[0] == "bilinmiyor":
        return None
    if k[0] == "duzlem":
        return _paralel(k[2] / np.linalg.norm(k[2]), a)
    if k[0] == "kure":
        return _dogruya_uzaklik(k[1], o, a) <= D_TOL
    b = k[2] / np.linalg.norm(k[2])
    return _paralel(b, a) and _dogruya_uzaklik(k[1], o, a) <= D_TOL


def _xdir(a: np.ndarray) -> np.ndarray:
    """Global X'in eksene dik bileşeni; |a × X| < 1e-6 ise global Y'ninki."""
    for e in (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])):
        if np.linalg.norm(np.cross(a, e)) >= 1e-6:
            d = e - (e @ a) * a
            return d / np.linalg.norm(d)
    raise GeometryError("xdir bulunamadı")  # pragma: no cover - X ve Y aynı anda eksene paralel olamaz


def _yari_duzlem(part: Part, o: np.ndarray, a: np.ndarray, xd: np.ndarray, tol: float):
    """Sınır kutusunu her yönde 10·tol + 1 mm aşan yarı düzlem dikdörtgeni (x ≥ 0)."""
    lo, hi = part.bbox
    koseler = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    d = koseler - o
    z = d @ a
    r = np.linalg.norm(d - np.outer(z, a), axis=1)
    m = 10.0 * tol + 1.0
    z0, z1, x1 = z.min() - m, z.max() + m, r.max() + m
    pts = [o + z0 * a, o + z1 * a, o + z1 * a + x1 * xd, o + z0 * a + x1 * xd]
    return bd.Face(bd.Wire.make_polygon([bd.Vector(*p) for p in pts], close=True))


def _egri_noktalari(f, t0: float, t1: float, sapma: float) -> np.ndarray:
    """Parametre aralığını kiriş sapması ≤ sapma olana kadar ikiye böler; uçlar dahil (k, 2)."""
    pts = [(t0, f(t0)), (t1, f(t1))]
    for _ in range(4):  # en az 16 aralık
        yeni = [pts[0]]
        for (ta, _pa), (tb, pb) in zip(pts, pts[1:], strict=False):
            tm = 0.5 * (ta + tb)
            yeni += [(tm, f(tm)), (tb, pb)]
        pts = yeni
    sonuc = [pts[0]]
    yigin = list(reversed(list(zip(pts, pts[1:], strict=False))))
    while yigin:
        (ta, pa), (tb, pb) = yigin.pop()
        tm = 0.5 * (ta + tb)
        pm = f(tm)
        ab = pb - pa
        L = float(np.hypot(*ab))
        d = abs(ab[0] * (pm - pa)[1] - ab[1] * (pm - pa)[0]) / L if L > 0 else float(np.hypot(*(pm - pa)))
        if d > sapma and tb - ta > 1e-12 * max(1.0, abs(t1 - t0)):
            yigin += [((tm, pm), (tb, pb)), ((ta, pa), (tm, pm))]
        else:
            sonuc.append((tb, pb))
    return np.array([p for _, p in sonuc])


def _kenar(e, o: np.ndarray, a: np.ndarray, xd: np.ndarray, tol: float) -> SectionEdge:
    """OCCT kenarı → (z, x) düzleminde SectionEdge (doğru, yay ya da çokgen eğri)."""
    c = BRepAdaptor_Curve(e.wrapped)
    t0, t1 = c.FirstParameter(), c.LastParameter()

    def f(t: float) -> np.ndarray:
        d = _vektor(c.Value(t)) - o
        return np.array([d @ a, d @ xd])

    p0, p1 = f(t0), f(t1)
    tip = c.GetType()
    if tip == GeomAbs_Line:
        return SectionEdge("line", np.array([p0, p1]))
    if tip == GeomAbs_Circle:
        d = _vektor(c.Circle().Location()) - o
        m = np.array([d @ a, d @ xd])
        tam = float(np.hypot(*(p1 - p0))) <= 1e-9 * max(1.0, float(np.abs(p0).max()))
        q = f(t0 + (0.25 if tam else 0.5) * (t1 - t0))  # yayın orta noktası, süpürme < 2π için yönü belirler
        u, v = p0 - m, q - m
        return SectionEdge("arc", np.array([p0, p1]), m, bool(u[0] * v[1] - u[1] * v[0] > 0))
    return SectionEdge("curve", _egri_noktalari(f, t0, t1, tol / 4.0))


def _halka(tel, o, a, xd, tol) -> tuple[SectionEdge, ...]:
    exp = BRepTools_WireExplorer(tel.wrapped)
    kenarlar = []
    while exp.More():
        kenarlar.append(_kenar(bd.Edge(exp.Current()), o, a, xd, tol))
        exp.Next()
    return tuple(kenarlar)


def axial_section(
    part: Part, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), tol: float = 1e-3
) -> AxialSection:
    """Eksenden geçen x ≥ 0 yarı düzlem kesiti; axis="auto" → dönel yüzlerden eksen bulunur."""
    try:
        tol = float(tol)
    except (TypeError, ValueError) as e:
        raise GeometryError(f"tol sayı olmalı: {tol!r}") from e
    if not (math.isfinite(tol) and tol > 0):
        raise GeometryError(f"tol > 0 ve sonlu olmalı (tol={tol})")
    siniflar = _siniflar(part)
    if isinstance(axis, str):
        if axis != "auto":
            raise GeometryError(f'axis bir vektör ya da "auto" olmalı: {axis!r}')
        o, a = _otomatik_eksen(siniflar)
    else:
        o = _vec3(origin, "origin")
        a = _vec3(axis, "axis")
        n = float(np.linalg.norm(a))
        if n < 1e-12:
            raise GeometryError("axis sıfır vektör")
        a = a / n
    xd = _xdir(a)

    dis, bilinmeyen = [], []
    for i, k in enumerate(siniflar):
        r = _donel_mi(k, o, a)
        if r is None:
            bilinmeyen.append(i)
        elif not r:
            dis.append(i)

    try:
        kesit = part.shape.intersect(_yari_duzlem(part, o, a, xd, tol))
        yuzler = list(kesit.faces()) if kesit is not None else []
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"eksenel kesit başarısız: {e}") from e
    faces = tuple(
        SectionFace(
            outer=_halka(y.outer_wire(), o, a, xd, tol),
            holes=tuple(_halka(w, o, a, xd, tol) for w in y.inner_wires()),
        )
        for y in yuzler
    )
    return AxialSection(
        origin=o, axis=a, xdir=xd, faces=faces, off_axis_faces=tuple(dis), unknown_faces=tuple(bilinmeyen)
    )
