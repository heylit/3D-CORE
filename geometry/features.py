"""
SPEC 02 — Kodla basit parça: blok, silindir, delik, cep, pah.

Koordinat kuralı: blok min köşesi orijinde; "üst yüz" = zmax düzlemi; delik ve cep üstten −Z yönünde.
Hiçbir işlem girdi parçayı değiştirmez, her zaman yeni Part döner; delik kayıtları (Part.holes) yeni
parçaya taşınır, `hole` kendi kaydını ekler (SPEC 23). Birimler: mm.
"""

from __future__ import annotations

import math

import build123d as bd
import numpy as np

from geometry.part import GeometryError, Hole, Part

DV_MIN = 1e-9  # mm³: bundan az malzeme kaldıran işlem "boşa" sayılır (SPEC 02)
PAY = 1.0  # mm: kesici gövdenin üst yüzün üstüne taşma payı (teğet yüz kalmasın diye)


def _pozitif(**degerler: float) -> None:
    """Her değer sonlu ve > 0 olmalı; değilse GeometryError."""
    for ad, v in degerler.items():
        if not (math.isfinite(v) and v > 0):
            raise GeometryError(f"{ad} > 0 olmalı ({ad}={v})")


def _z_araligi(part: Part) -> tuple[float, float]:
    """Parçanın (zmin, zmax) değerleri."""
    lo, hi = part.bbox
    return float(lo[2]), float(hi[2])


def _yeni_part(shape, name: str, holes: tuple[Hole, ...] = ()) -> Part:
    """OCCT sonucunu tek katıya indirip Part yapar; hatayı GeometryError'a sarar."""
    if isinstance(shape, bd.Compound | bd.ShapeList):
        solids = list(shape.solids())
        if len(solids) == 1:
            shape = solids[0]
    return Part(shape, name=name, holes=holes)


def _kes(part: Part, kesici, islem: str, yeni: Hole | None = None) -> Part:
    """part − kesici; kaldırılan hacim ΔV ≤ DV_MIN ise GeometryError.

    Girdinin delik kayıtları korunur; yeni verilirse sona eklenir.
    """
    holes = part.holes + ((yeni,) if yeni is not None else ())
    try:
        sonuc = _yeni_part(part.shape - kesici, part.name, holes)
    except GeometryError:
        raise
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"{islem}: OCCT boolean başarısız ({e})") from e
    dV = part.volume - sonuc.volume
    if dV <= DV_MIN:
        raise GeometryError(f"{islem}: parçadan malzeme kaldırmıyor (ΔV={dV})")
    return sonuc


def block(a: float, b: float, c: float, name: str = "blok") -> Part:
    """a × b × c blok, x ∈ [0,a], y ∈ [0,b], z ∈ [0,c]."""
    _pozitif(a=a, b=b, c=c)
    return Part(bd.Box(a, b, c, align=bd.Align.MIN), name=name)


def cylinder(r: float, h: float, name: str = "silindir") -> Part:
    """Yarıçap r, boy h silindir; taban merkezi orijinde, eksen +Z."""
    _pozitif(r=r, h=h)
    align = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    return Part(bd.Cylinder(r, h, align=align), name=name)


def hole(part: Part, x: float, y: float, d: float, depth: float | None = None) -> Part:
    """Üst yüzden −Z yönünde çap d delik, eksen (x, y). depth=None → boydan boya.

    Kesici: z ∈ [zmax − depth, zmax + PAY] silindir. Boydan boyada alt uç da PAY kadar dışarı taşar,
    böylece taban yüzü kesiciyle teğet kalmaz. Kaldırılan hacim ΔV = π d² t / 4 (parça içinde).
    """
    _pozitif(d=d)
    zmin, zmax = _z_araligi(part)
    h = zmax - zmin
    if depth is None:
        z0 = zmin - PAY
    else:
        _pozitif(depth=depth)
        if depth > h:
            raise GeometryError(f"delik derinliği yüksekliği aşıyor (depth={depth} > {h})")
        z0 = zmin - PAY if depth == h else zmax - depth
    boy = zmax + PAY - z0
    align = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    kesici = bd.Pos(x, y, z0) * bd.Cylinder(d / 2, boy, align=align)
    through = depth is None or depth == h
    kayit = Hole(
        origin=np.array([x, y, zmax]),
        axis=np.array([0.0, 0.0, -1.0]),
        d=d,
        depth=h if through else depth,
        through=through,
    )
    return _kes(part, kesici, "delik", kayit)


def _cep_kesiti(w: float, l: float, r: float) -> bd.Face:  # noqa: E741
    """Merkezi orijinde w × l köşe yarıçaplı dikdörtgen kesit (XY düzlemi).

    r = 0 → keskin dikdörtgen; r = min(w, l)/2 → kanal (obround) veya w = l ise daire;
    arada → yuvarlatılmış dikdörtgen.
    """
    r_max = min(w, l) / 2
    if r == 0:
        return bd.Rectangle(w, l).face()
    if math.isclose(r, r_max, rel_tol=1e-12, abs_tol=0.0):
        if w == l:
            return bd.Circle(r).face()
        if w > l:
            return bd.SlotOverall(w, l).face()
        return (bd.Rot(0, 0, 90) * bd.SlotOverall(l, w)).face()
    return bd.RectangleRounded(w, l, r).face()


def pocket(part: Part, x: float, y: float, w: float, l: float, depth: float, r: float = 0.0) -> Part:  # noqa: E741
    """Üstten w × l dikdörtgen cep, merkez (x, y), köşe yarıçapı r, derinlik depth.

    Kesici kesit, z ∈ [zmax − depth, zmax + PAY] boyunca çekilir. Kaldırılan hacim ΔV = A_c · t,
    A_c = w·l − (4 − π) r².
    """
    _pozitif(w=w, l=l, depth=depth)
    if not (math.isfinite(r) and 0 <= r <= min(w, l) / 2):
        raise GeometryError(f"köşe yarıçapı 0 <= r <= min(w, l)/2 olmalı (r={r})")
    zmin, zmax = _z_araligi(part)
    if depth >= zmax - zmin:
        raise GeometryError(f"cep parçayı deler (depth={depth} >= {zmax - zmin})")
    try:
        kesit = _cep_kesiti(w, l, r)
        kesici = bd.Pos(x, y, zmax - depth) * bd.extrude(kesit, amount=depth + PAY)
    except Exception as e:
        raise GeometryError(f"cep kesiti oluşturulamadı ({e})") from e
    return _kes(part, kesici, "cep")


def _ust_kenarlar(part: Part) -> list:
    """Üst yüzün (zmax düzleminde, normali +Z olan düzlemsel yüzler) tüm kenarları."""
    _, zmax = _z_araligi(part)
    tol = 1e-7 * max(1.0, abs(zmax))
    kenarlar = []
    for f in part.shape.faces():
        if f.geom_type != bd.GeomType.PLANE:
            continue
        n = f.normal_at()
        if n.Z < 1 - 1e-9 or abs(f.center().Z - zmax) > tol:
            continue
        kenarlar.extend(f.edges())
    if not kenarlar:
        raise GeometryError("üst yüz (zmax) bulunamadı")
    return kenarlar


def chamfer_top(part: Part, d: float) -> Part:
    """Üst yüzün (zmax) tüm kenarlarına eşit mesafeli d pahı (delik / cep ağızları dahil)."""
    _pozitif(d=d)
    kenarlar = _ust_kenarlar(part)
    solids = list(part.shape.solids())
    if len(solids) != 1:
        raise GeometryError(f"pah tek katıda uygulanır ({len(solids)} katı)")
    try:
        sonuc = _yeni_part(solids[0].chamfer(d, None, kenarlar), part.name, part.holes)
    except GeometryError:
        raise
    except Exception as e:
        raise GeometryError(f"pah oluşturulamadı (d={d}): {e}") from e
    if part.volume - sonuc.volume <= DV_MIN:
        raise GeometryError(f"pah malzeme kaldırmadı (d={d})")
    return sonuc
