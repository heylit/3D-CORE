"""
SPEC 23 — Havşalı, lambalı, dişli ve eğimli delik; diş ve lamba tabloları.

Her delik işlemi dönen parçaya bir geometry.part.Hole kaydı ekler (CAM delme çevrimleri bunu okur).
Hiçbir işlem girdi parçayı değiştirmez. Birimler: mm, açı: derece.
"""

from __future__ import annotations

import math
import re

import build123d as bd
import numpy as np

from geometry.features import PAY, _kes, _pozitif, _z_araligi
from geometry.part import GeometryError, Hole, Part

ASAGI = np.array([0.0, 0.0, -1.0])  # düz deliklerin delme yönü (üstten −Z)
TOL_YUZEY = 1e-6  # mm: eğimli delikte giriş noktasının yüzeye en büyük uzaklığı
COS_MIN = 0.05  # eksen ile yüzey normali arası açı ≤ ~87°; daha yatık giriş / çıkış reddedilir

# ISO 261 / ISO 724 kaba hatve P [mm]; kılavuz matkabı d_m = d_n − P
THREADS_COARSE: dict[str, float] = {
    "M3": 0.5,
    "M4": 0.7,
    "M5": 0.8,
    "M6": 1.0,
    "M8": 1.25,
    "M10": 1.5,
    "M12": 1.75,
    "M14": 2.0,
    "M16": 2.0,
    "M20": 2.5,
    "M24": 3.0,
}

# ISO 4762 imbus civata lambası: (d geçiş ISO 273 orta, D lamba, t_c lamba derinliği) DIN 974-1 [mm]
CBORE_ISO4762: dict[str, tuple[float, float, float]] = {
    "M3": (3.4, 6.5, 3.4),
    "M4": (4.5, 8.0, 4.4),
    "M5": (5.5, 10.0, 5.4),
    "M6": (6.6, 11.0, 6.4),
    "M8": (9.0, 15.0, 8.6),
    "M10": (11.0, 18.0, 10.6),
    "M12": (13.5, 20.0, 12.6),
    "M14": (15.5, 24.0, 14.6),
    "M16": (17.5, 26.0, 16.6),
    "M20": (22.0, 33.0, 20.6),
    "M24": (26.0, 40.0, 24.8),
}


def parse_thread(spec: str) -> tuple[float, float]:
    """ "M8" → (8.0, 1.25), "M8x1" → (8.0, 1.0): (nominal çap d_n, hatve P).

    Kaba hatve THREADS_COARSE tablosundan gelir; ince hatve yazımda verilir.
    """
    m = re.fullmatch(r"M(\d+(?:\.\d+)?)(?:x(\d+(?:\.\d+)?))?", spec or "")
    if m is None:
        raise GeometryError(f"diş yazımı bozuk: '{spec}' (beklenen 'M8' veya 'M8x1')")
    d_n = float(m.group(1))
    if m.group(2) is None:
        if spec not in THREADS_COARSE:
            raise GeometryError(f"kaba diş tabloda yok: '{spec}'")
        P = THREADS_COARSE[spec]
    else:
        P = float(m.group(2))
    if not 0 < P < d_n:
        raise GeometryError(f"hatve 0 < P < d_n olmalı ('{spec}': P={P}, d_n={d_n})")
    return d_n, P


def _derinlik(part: Part, depth: float | None) -> tuple[float, bool]:
    """Düz delikte (t, boydan_boya). depth=None veya yükseklik → boydan boya, t = yükseklik."""
    zmin, zmax = _z_araligi(part)
    h = zmax - zmin
    if depth is None:
        return h, True
    _pozitif(depth=depth)
    if depth > h:
        raise GeometryError(f"delik derinliği yüksekliği aşıyor (depth={depth} > {h})")
    return depth, depth == h


def _silindir(x: float, y: float, r: float, z0: float, z1: float):
    """z ∈ [z0, z1] boyunca, ekseni (x, y) olan dik silindir."""
    align = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    return bd.Pos(x, y, z0) * bd.Cylinder(r, z1 - z0, align=align)


def _dik_delik(part: Part, x: float, y: float, d: float, t: float, through: bool):
    """Üstten −Z, çap d, derinlik t silindir kesici ve delik dibinin / alt ucunun z'si."""
    zmin, zmax = _z_araligi(part)
    z0 = zmin - PAY if through else zmax - t
    return _silindir(x, y, d / 2, z0, zmax + PAY), zmax


def countersink_hole(
    part: Part,
    x: float,
    y: float,
    d: float,
    csk_d: float,
    csk_angle: float = 90.0,
    depth: float | None = None,
) -> Part:
    """Üstten −Z havşalı delik, eksen (x, y). depth=None → boydan boya.

    Koni yüksekliği h = (D − d) / (2 tan(α/2)); ΔV = (π h / 3)(R² + R r + r²) + π r² (t − h).
    """
    _pozitif(d=d, csk_d=csk_d)
    if csk_d <= d:
        raise GeometryError(f"havşa çapı delikten büyük olmalı (csk_d={csk_d} <= d={d})")
    if not (math.isfinite(csk_angle) and 0 < csk_angle < 180):
        raise GeometryError(f"havşa açısı 0 < α < 180 olmalı (α={csk_angle})")
    t, through = _derinlik(part, depth)
    h = (csk_d - d) / (2 * math.tan(math.radians(csk_angle) / 2))
    if t <= h:
        raise GeometryError(f"havşa konisi delik dibine ulaşıyor (depth={t} <= h={h})")
    try:
        delik, zmax = _dik_delik(part, x, y, d, t, through)
        koni = bd.Pos(x, y, zmax - h) * bd.Cone(
            d / 2, csk_d / 2, h, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
        )
        kesici = delik + koni + _silindir(x, y, csk_d / 2, zmax, zmax + PAY)
    except Exception as e:
        raise GeometryError(f"havşa kesicisi oluşturulamadı ({e})") from e
    kayit = Hole(
        origin=np.array([x, y, zmax]),
        axis=ASAGI,
        d=d,
        depth=t,
        through=through,
        csk_d=csk_d,
        csk_angle=csk_angle,
    )
    return _kes(part, kesici, "havşalı delik", kayit)


def counterbore_hole(
    part: Part,
    x: float,
    y: float,
    screw: str | None = None,
    d: float | None = None,
    cbore_d: float | None = None,
    cbore_depth: float | None = None,
    depth: float | None = None,
) -> Part:
    """Üstten −Z lambalı delik, eksen (x, y). screw verilirse eksik ölçüler CBORE_ISO4762'den.

    ΔV = π (D² − d²) t_c / 4 + π d² t / 4.
    """
    if screw is not None:
        if screw not in CBORE_ISO4762:
            raise GeometryError(f"lamba tablosunda civata yok: '{screw}'")
        d0, D0, tc0 = CBORE_ISO4762[screw]
        d = d0 if d is None else d
        cbore_d = D0 if cbore_d is None else cbore_d
        cbore_depth = tc0 if cbore_depth is None else cbore_depth
    if d is None or cbore_d is None or cbore_depth is None:
        raise GeometryError("lamba: screw yoksa d, cbore_d ve cbore_depth zorunlu")
    _pozitif(d=d, cbore_d=cbore_d, cbore_depth=cbore_depth)
    if cbore_d <= d:
        raise GeometryError(f"lamba çapı delikten büyük olmalı (cbore_d={cbore_d} <= d={d})")
    t, through = _derinlik(part, depth)
    if cbore_depth >= t:
        raise GeometryError(f"lamba derinliği delik derinliğinden küçük olmalı ({cbore_depth} >= {t})")
    try:
        delik, zmax = _dik_delik(part, x, y, d, t, through)
        kesici = delik + _silindir(x, y, cbore_d / 2, zmax - cbore_depth, zmax + PAY)
    except Exception as e:
        raise GeometryError(f"lamba kesicisi oluşturulamadı ({e})") from e
    kayit = Hole(
        origin=np.array([x, y, zmax]),
        axis=ASAGI,
        d=d,
        depth=t,
        through=through,
        cbore_d=cbore_d,
        cbore_depth=cbore_depth,
    )
    return _kes(part, kesici, "lambalı delik", kayit)


def tapped_hole(
    part: Part,
    x: float,
    y: float,
    thread: str,
    depth: float | None = None,
    thread_depth: float | None = None,
) -> Part:
    """Üstten −Z dişli delik (kozmetik diş): kılavuz matkabı d_m = d_n − P, ΔV = π d_m² t / 4.

    Diş geometride yoktur; diş bilgisi Hole kaydındadır. thread_depth=None → depth.
    """
    d_n, P = parse_thread(thread)
    d_m = d_n - P
    t, through = _derinlik(part, depth)
    if thread_depth is None:
        thread_depth = t
    _pozitif(thread_depth=thread_depth)
    if thread_depth > t:
        raise GeometryError(f"diş derinliği delik derinliğini aşıyor ({thread_depth} > {t})")
    kesici, zmax = _dik_delik(part, x, y, d_m, t, through)
    kayit = Hole(
        origin=np.array([x, y, zmax]),
        axis=ASAGI,
        d=d_m,
        depth=t,
        through=through,
        thread=thread,
        thread_d=d_n,
        pitch=P,
        thread_depth=thread_depth,
    )
    return _kes(part, kesici, "dişli delik", kayit)


def _yuzey_uzakligi(part: Part, p: bd.Vector) -> float:
    """p'nin parça yüzeyine (kabuğuna) uzaklığı; katı içindeki nokta için de pozitif."""
    return min(f.distance_to(p) for f in part.shape.faces())


def _eksen_kesisimleri(part: Part, p: bd.Vector, n: bd.Vector) -> tuple[float, float | None, float | None]:
    """Eksenin yüzeylerle kesişimi: (giriş cos'u, çıkış boyu L, çıkış cos'u).

    cos = |n · yüzey normali|; çıkış yoksa L ve çıkış cos'u None.
    """
    noktalar = [
        ((q - p).dot(n), abs(m.normalized().dot(n)))
        for q, m in part.shape.find_intersection_points(bd.Axis(p, n))
    ]
    giris = [c for s, c in noktalar if abs(s) <= TOL_YUZEY]
    cikis = sorted((s, c) for s, c in noktalar if s > TOL_YUZEY)
    cos_giris = max(giris) if giris else 1.0
    if not cikis:
        return cos_giris, None, None
    return cos_giris, cikis[0][0], cikis[0][1]


def _uzatma(r: float, cos_t: float, nerede: str) -> float:
    """Kesicinin yüzeyi tümüyle aşması için eksen boyunca pay: PAY + r tan θ (θ: eksen–normal açısı)."""
    if cos_t < COS_MIN:
        raise GeometryError(f"eğimli delik: {nerede} yüzeyine çok yatık (cos θ={cos_t})")
    return PAY + r * math.sqrt(1 - cos_t**2) / cos_t


def inclined_hole(
    part: Part,
    p: np.ndarray,
    n: np.ndarray,
    d: float,
    depth: float | None = None,
) -> Part:
    """Giriş noktası p (yüzeyde), delme yönü n ile eğimli delik. depth=None → boydan boya.

    Boydan boya iki paralel düzlem arasında ΔV = π r² c / cos θ; kör, düz dip: ΔV = π r² t.
    """
    _pozitif(d=d)
    p = np.asarray(p, dtype=float)
    n = np.asarray(n, dtype=float)
    if p.shape != (3,) or n.shape != (3,) or not (np.all(np.isfinite(p)) and np.all(np.isfinite(n))):
        raise GeometryError(f"eğimli delik: p ve n sonlu (3,) olmalı (p={p}, n={n})")
    norm = float(np.linalg.norm(n))
    if norm == 0:
        raise GeometryError("eğimli delik: yön sıfır olamaz")
    n = n / norm
    P0, N = bd.Vector(*p), bd.Vector(*n)
    if _yuzey_uzakligi(part, P0) > TOL_YUZEY:
        raise GeometryError(f"eğimli delik: giriş noktası parça yüzeyinde değil (p={p})")
    if not part.shape.is_inside(P0 + N * 1e-3):
        raise GeometryError(f"eğimli delik: yön malzemeye girmiyor (n={n})")
    cos_giris, L, cos_cikis = _eksen_kesisimleri(part, P0, N)
    e0 = _uzatma(d / 2, cos_giris, "giriş")
    if depth is None:
        if L is None:
            raise GeometryError("eğimli delik: eksen parçadan çıkmıyor")
        t, through, boy = L, True, e0 + L + _uzatma(d / 2, cos_cikis, "çıkış")
    else:
        _pozitif(depth=depth)
        if L is not None and depth > L:
            raise GeometryError(f"eğimli delik: derinlik eksen boyunu aşıyor ({depth} > {L})")
        t, through, boy = depth, False, e0 + depth
    try:
        kesici = bd.Solid.make_cylinder(d / 2, boy, bd.Plane(origin=P0 - N * e0, z_dir=N))
    except Exception as e:
        raise GeometryError(f"eğimli delik kesicisi oluşturulamadı ({e})") from e
    kayit = Hole(origin=p, axis=n, d=d, depth=t, through=through)
    return _kes(part, kesici, "eğimli delik", kayit)
