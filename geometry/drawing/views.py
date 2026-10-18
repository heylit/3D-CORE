"""HLR ile görünüş ve kesit (SPEC 16). OCCT gerektirir.

Görünüş koordinatı (u, v) = (P·U, P·V); bakış yönü d, U × V = −d (göze göre sağ ve yukarı):

    on : d = +Y, U = +X, V = +Z        ust: d = −Z, U = +X, V = +Y
    sol: d = +X, U = −Y, V = +Z        sag: d = −X, U = +Y, V = +Z

Sadece keskin kenarlar ve silüetler çizilir: HLRBRep_HLRToShape'in VCompound / OutLineVCompound (görünen)
ve HCompound / OutLineHCompound (gizli) çıktıları. Teğet (Rg1 / RgN) kenarlar alınmaz.
"""

from __future__ import annotations

import math

import numpy as np

from geometry.drawing.cleanup import classify, clean_edges
from geometry.drawing.hatch import hatch
from geometry.drawing.types import Entity, Line2D, Polyline2D, View
from geometry.part import GeometryError, Part, Region

try:
    import build123d as bd
    from OCP.BRepAdaptor import BRepAdaptor_CompCurve, BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
except ImportError:  # pragma: no cover - build123d kurulu değilse Part zaten hata verir
    pass

# yön adı -> (d, U, V) dünya vektörleri
YONLER: dict[str, tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]] = {
    "on": ((0, 1, 0), (1, 0, 0), (0, 0, 1)),
    "ust": ((0, 0, -1), (1, 0, 0), (0, 1, 0)),
    "sol": ((1, 0, 0), (0, -1, 0), (0, 0, 1)),
    "sag": ((-1, 0, 0), (0, 1, 0), (0, 0, 1)),
}
TASMA = 2.0  # mm: eksen çizgisinin çemberden / delikten taşma payı
N_MIN = 33  # sınıflama için en az örnek sayısı


def _yon(direction: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if direction not in YONLER:
        raise GeometryError(f"bilinmeyen görünüş yönü '{direction}' (on, ust, sol, sag)")
    return tuple(np.array(v, dtype=float) for v in YONLER[direction])  # type: ignore[return-value]


def _tol_kontrol(tol: float) -> None:
    if not (math.isfinite(tol) and tol > 0):
        raise GeometryError(f"tol > 0 olmalı (tol={tol})")


def _ornekle(edge, tol: float) -> tuple[np.ndarray, np.ndarray] | None:
    """Kenardan (sınıflama için düzgün parametreli, çoklu çizgi için kiriş sapmalı) 2D noktalar."""
    egri = BRepAdaptor_Curve(edge)
    t0, t1 = egri.FirstParameter(), egri.LastParameter()
    if not t1 > t0:
        return None
    orn = GCPnts_QuasiUniformDeflection(egri, tol)
    if orn.IsDone() and orn.NbPoints() >= 2:
        sapma = np.array([orn.Value(i).Coord()[:2] for i in range(1, orn.NbPoints() + 1)])
        n = max(N_MIN, orn.NbPoints())
    else:
        sapma, n = None, N_MIN
    duzgun = np.array([egri.Value(t).Coord()[:2] for t in np.linspace(t0, t1, n)])
    return duzgun, (sapma if sapma is not None else duzgun)


def _kenarlar_2d(compound, tol: float) -> list[Entity]:
    if compound is None or compound.IsNull():
        return []
    out: list[Entity] = []
    for e in bd.Compound(compound).edges():
        orn = _ornekle(e.wrapped, tol)
        if orn is None:
            continue
        duzgun, sapma = orn
        if np.linalg.norm(np.diff(duzgun, axis=0), axis=1).sum() <= 1e-9:
            continue
        ciz = classify(duzgun)
        out.append(Polyline2D(sapma, "GORUNUR") if isinstance(ciz, Polyline2D) else ciz)
    return out


def _hlr(shape, direction: str, tol: float) -> tuple[list[Entity], list[Entity]]:
    """Ham (görünen, gizli) 2D kenarlar."""
    d, U, _ = _yon(direction)
    N = -d  # projektör ekseni göze doğru; X ekseni U → Y ekseni N × U = V
    algo = HLRBRep_Algo()
    algo.Add(shape.wrapped)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*N), gp_Dir(*U))))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    gorunur = _kenarlar_2d(h.VCompound(), tol) + _kenarlar_2d(h.OutLineVCompound(), tol)
    gizli = _kenarlar_2d(h.HCompound(), tol) + _kenarlar_2d(h.OutLineHCompound(), tol)
    return gorunur, gizli


def _delikler(part: Part) -> list[tuple[np.ndarray, np.ndarray, float, float]]:
    """Tam silindirik delikler: (başlangıç q0, birim eksen a, yarıçap r, boy L); aynı eksen bir kez."""
    out: list[tuple[np.ndarray, np.ndarray, float, float]] = []
    for f in part.cylindrical_faces():
        if not f.concave or f.angle < 360.0 - 1e-6:
            continue
        q0, a = np.asarray(f.origin, dtype=float), np.asarray(f.axis, dtype=float)
        ayni = False
        for p0, b, r, _ in out:
            w = q0 - p0
            eksen_ayni = abs(abs(a @ b) - 1) < 1e-9 and np.linalg.norm(w - (w @ b) * b) < 1e-6
            if eksen_ayni and abs(r - f.radius) < 1e-6:
                ayni = True
        if not ayni:
            out.append((q0, a, float(f.radius), float(f.length)))
    return out


def _eksenler(part: Part, direction: str, kesit_d: float | None = None) -> list[Line2D]:
    """Delik eksen / merkez çizgileri (EKSEN). kesit_d: kesitte kalan taraf d·p ≥ kesit_d."""
    d, U, V = _yon(direction)
    out: list[Line2D] = []
    for q0, a, r, L in _delikler(part):
        q1 = q0 + L * a
        if kesit_d is not None and max(q0 @ d, q1 @ d) < kesit_d - 1e-9:
            continue
        uv0 = np.array([q0 @ U, q0 @ V])
        uv1 = np.array([q1 @ U, q1 @ V])
        if abs(abs(a @ d) - 1.0) < 1e-9:  # eksen bakışa paralel: merkez işareti
            m = r + TASMA
            out.append(Line2D(uv0 - [m, 0.0], uv0 + [m, 0.0], "EKSEN"))
            out.append(Line2D(uv0 - [0.0, m], uv0 + [0.0, m], "EKSEN"))
        elif abs(a @ d) < 1e-9:  # eksen görünüş düzleminde: eksen çizgisi
            e = (uv1 - uv0) / np.linalg.norm(uv1 - uv0)
            out.append(Line2D(uv0 - TASMA * e, uv1 + TASMA * e, "EKSEN"))
    return out


def project(part: Part, direction: str, tol: float = 0.01, axes: bool = True) -> View:
    """direction ∈ {"on", "ust", "sol", "sag"} yönünde dik izdüşüm, gizli çizgiler ayrılmış."""
    _yon(direction)
    _tol_kontrol(tol)
    gorunur, gizli = _hlr(part.shape, direction, tol)
    kenarlar = clean_edges(gorunur, gizli)
    if not any(e.layer == "GORUNUR" for e in kenarlar):
        raise GeometryError(f"'{direction}' görünüşünde görünen kenar yok")
    if axes:
        kenarlar += _eksenler(part, direction)
    return View(name=direction, direction=direction, edges=tuple(kenarlar))


# ---------- kesit ----------


def _isaretli_alan(P: np.ndarray) -> float:
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _cokgen_uv(wire, U: np.ndarray, V: np.ndarray, tol: float, ccw: bool) -> np.ndarray:
    """Kapalı teli görünüş koordinatında (k, 2) çokgene çevirir; istenen yönde, son nokta tekrarsız."""
    egri = BRepAdaptor_CompCurve(wire.wrapped)
    orn = GCPnts_QuasiUniformDeflection(egri, tol)
    if not orn.IsDone() or orn.NbPoints() < 3:
        raise GeometryError("kesit teli çokgene çevrilemedi")
    X = np.array([orn.Value(i).Coord() for i in range(1, orn.NbPoints() + 1)])
    P = np.column_stack([X @ U, X @ V])
    if np.linalg.norm(P[0] - P[-1]) <= 1e-9 * max(1.0, float(np.abs(P).max())):
        P = P[:-1]
    A = _isaretli_alan(P)
    if A == 0.0:
        raise GeometryError("kesit teli dejenere (alan 0)")
    if (A > 0) != ccw:
        P = P[::-1].copy()
    return P


def _kesit_duzlemi(direction: str, offset: float) -> tuple[np.ndarray, np.ndarray, float]:
    """(düzlem noktası, düzlem normali = d, kalan taraf eşiği d·p ≥ c)."""
    d, _, _ = _yon(direction)
    eksen = int(np.argmax(np.abs(d)))
    p0 = np.zeros(3)
    p0[eksen] = offset
    return p0, d, float(p0 @ d)


def section(
    part: Part,
    direction: str,
    offset: float,
    name: str = "A-A",
    s: float = 3.0,
    theta: float = 45.0,
    tol: float = 0.01,
) -> View:
    """Görünüş düzlemine paralel kesit (on: y = offset, ust: z = offset, sol/sag: x = offset).

    Gözle düzlem arasındaki malzeme kaldırılır, kalan parça aynı yönden izdüşürülür; gizli çizgi çizilmez.
    Kesit yüzeyi görünüş koordinatında Region listesi olarak verilir ve taranır.
    """
    d, U, V = _yon(direction)
    _tol_kontrol(tol)
    if not math.isfinite(offset):
        raise GeometryError(f"kesit konumu sonlu olmalı (offset={offset})")
    p0, n, c = _kesit_duzlemi(direction, offset)
    lo, hi = part.bbox
    eksen = int(np.argmax(np.abs(d)))
    if not (lo[eksen] < offset < hi[eksen]):
        raise GeometryError(f"kesit düzlemi parçayı kesmiyor (offset={offset})")
    try:
        yuzler = list(bd.section(part.shape, section_by=bd.Plane(origin=tuple(p0), z_dir=tuple(n))).faces())
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"kesit başarısız: {e}") from e
    if not yuzler:
        raise GeometryError(f"kesit düzlemi parçayı kesmiyor (offset={offset})")
    bolgeler = [
        Region(
            outer=_cokgen_uv(y.outer_wire(), U, V, tol, ccw=True),
            holes=tuple(_cokgen_uv(w, U, V, tol, ccw=False) for w in y.inner_wires()),
        )
        for y in yuzler
    ]
    bolgeler.sort(key=lambda r: -_isaretli_alan(r.outer))

    # kalan yarı: d·p ≥ c tarafı (göze uzak taraf)
    pay = 1.0
    kmin, kmax = lo - pay, hi + pay
    if d[eksen] > 0:
        kmin[eksen] = offset
    else:
        kmax[eksen] = offset
    kutu = bd.Solid.make_box(*(kmax - kmin)).translate(bd.Vector(*kmin))
    try:
        kalan = part.shape & kutu
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"kesit başarısız: {e}") from e
    gorunur, _ = _hlr(kalan, direction, tol)
    kenarlar = clean_edges(gorunur, [])
    kenarlar += _eksenler(part, direction, kesit_d=c)
    return View(
        name=name,
        direction=direction,
        edges=tuple(kenarlar),
        regions=tuple(bolgeler),
        hatch=tuple(hatch(bolgeler, s=s, theta=theta)),
    )
