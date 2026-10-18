"""SPEC 10 testleri için ortak yardımcılar: çerçeveler, Teori örnek ölçüleri, ilkel sınır kutuları.

Uygulama kodundan bağımsız: ilkellerin WCS sınır kutusu, şeklin köşeleri (kutu) veya ekseni ve yarıçapı
(silindir) `Frame.to_world` ile taşınarak hesaplanır; ilkelin iç temsili (şekil mi kaydırılmış, çerçeve mi)
sonucu değiştirmez.
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import CylinderStock, Frame, Stock

I3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

# Teori sayısal örnekleri
STOK = Stock(0, 0, 0, 80, 50, 30)
VISE_OLCU = dict(jaw_width=100.0, jaw_thickness=20.0, jaw_height=15.0, bed_height=40.0, bed_extra=60.0)
VISE_OLCU["parallel_width"] = 6.0
VISE_GRIP = 10.0
CHUCK_STOK = CylinderStock(40, -60, 0)
CHUCK_GRIP = 20.0
CHUCK_OLCU = dict(body_d=160.0, body_length=80.0, jaw_height=25.0, jaw_width=20.0)
CLAMP_OLCU = dict(arm_length=80.0, arm_width=20.0, arm_thickness=12.0, bolt_d=12.0, bolt_above=15.0)
CLAMP_OLCU["heel_width"] = 15.0


def Rz(deg: float) -> tuple:
    """Z çevresinde dönme matrisi (satır satır): (x, y) → (x cos − y sin, x sin + y cos)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def Rx(deg: float) -> tuple:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def frame(origin=(0.0, 0.0, 0.0), R=I3) -> Frame:
    return Frame(tuple(float(v) for v in origin), R)


def T4(fr: Frame) -> np.ndarray:
    """Frame → 4x4 [[R, origin], [0, 1]]."""
    T = np.eye(4)
    T[:3, :3] = np.array(fr.R)
    T[:3, 3] = fr.origin
    return T


def frame_of(T: np.ndarray) -> Frame:
    return Frame(tuple(float(v) for v in T[:3, 3]), tuple(tuple(float(v) for v in r) for r in T[:3, :3]))


def _kose(b: Stock) -> np.ndarray:
    return np.array([[x, y, z] for x in (b.xmin, b.xmax) for y in (b.ymin, b.ymax) for z in (b.zmin, b.zmax)])


def prim_aabb(prim, outer: Frame | None = None) -> tuple[np.ndarray, np.ndarray]:
    """İlkelin (outer ∘ prim.frame ile taşınmış) eksenlere hizalı sınır kutusu (lo, hi)."""
    frames = [prim.frame] if outer is None else [prim.frame, outer]

    def tasi(p):
        for f in frames:
            p = f.to_world(p)
        return p

    s = prim.shape
    if isinstance(s, Stock):
        P = tasi(_kose(s))
        return P.min(axis=0), P.max(axis=0)
    a = tasi(np.array([0.0, 0.0, s.zmin]))
    b = tasi(np.array([0.0, 0.0, s.zmax]))
    ax = (b - a) / np.linalg.norm(b - a)
    r = s.D / 2
    pay = r * np.sqrt(np.clip(1 - ax**2, 0.0, None))
    return np.minimum(a, b) - pay, np.maximum(a, b) + pay


def box_center_wcs(prim) -> np.ndarray:
    s = prim.shape
    c = np.array([(s.xmin + s.xmax) / 2, (s.ymin + s.ymax) / 2, (s.zmin + s.zmax) / 2])
    return prim.frame.to_world(c)


def cyl_axis_wcs(prim) -> tuple[np.ndarray, float, float, float]:
    """Z eksenli silindir ilkel: (eksenin XY noktası, yarıçap, z_alt, z_üst) WCS'de."""
    s = prim.shape
    a = prim.frame.to_world(np.array([0.0, 0.0, s.zmin]))
    b = prim.frame.to_world(np.array([0.0, 0.0, s.zmax]))
    return a[:2], s.D / 2, min(a[2], b[2]), max(a[2], b[2])
