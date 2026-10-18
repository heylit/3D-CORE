"""
SPEC 10 — Bağlama elemanlarının OCCT katısı: ilkel listesinden (kutu, Z eksenli silindir) birleşim.

`cam`'i import etmez: ilkelleri `cam.baglama.Primitive.to_dict()` biçiminde düz sözlük olarak alır.
Hatalar `geometry.part.GeometryError`.
"""

from __future__ import annotations

from collections.abc import Sequence

import build123d as bd
import numpy as np
from OCP.gp import gp_Trsf

from geometry.part import GeometryError, Part

TOL_RIJIT = 1e-9
KUTU_ALAN = {"type", "xmin", "ymin", "zmin", "xmax", "ymax", "zmax"}
SILINDIR_ALAN = {"type", "D", "zmin", "zmax"}


def _sayi(nerede: str, d: dict, ad: str) -> float:
    try:
        v = float(d[ad])
    except (KeyError, TypeError, ValueError) as e:
        raise GeometryError(f"{nerede}: '{ad}' sayı olmalı") from e
    if not np.isfinite(v):
        raise GeometryError(f"{nerede}: '{ad}' sonlu olmalı")
    return v


def _cerceve(nerede: str, fr) -> np.ndarray:
    if not isinstance(fr, dict) or set(fr) != {"origin", "R"}:
        raise GeometryError(f"{nerede}: frame {{'origin', 'R'}} sözlüğü olmalı")
    try:
        o = np.asarray(fr["origin"], dtype=float)
        R = np.asarray(fr["R"], dtype=float)
    except (TypeError, ValueError) as e:
        raise GeometryError(f"{nerede}: frame sayısal olmalı") from e
    if o.shape != (3,) or R.shape != (3, 3) or not (np.all(np.isfinite(o)) and np.all(np.isfinite(R))):
        raise GeometryError(f"{nerede}: frame origin (3,) ve R (3, 3) sonlu olmalı")
    if not np.allclose(R.T @ R, np.eye(3), atol=TOL_RIJIT) or abs(np.linalg.det(R) - 1.0) > TOL_RIJIT:
        raise GeometryError(f"{nerede}: frame R rijit dönme olmalı (ölçek / ayna yok)")
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = o
    return T


def _trsf(T: np.ndarray) -> gp_Trsf:
    """Rijit 4x4 dönüşüm → gp_Trsf (B-spline'a çevirmeden, tolerans büyütmeden taşır)."""
    tr = gp_Trsf()
    tr.SetValues(*T[:3, :].ravel().tolist())
    return tr


def _kati(nerede: str, s) -> bd.Solid:
    if not isinstance(s, dict):
        raise GeometryError(f"{nerede}: shape sözlük olmalı")
    tur = s.get("type")
    if tur == "kutu":
        if not KUTU_ALAN <= s.keys():
            raise GeometryError(f"{nerede}: kutu alanları eksik ({sorted(KUTU_ALAN - s.keys())})")
        lo = np.array([_sayi(nerede, s, a) for a in ("xmin", "ymin", "zmin")])
        hi = np.array([_sayi(nerede, s, a) for a in ("xmax", "ymax", "zmax")])
        if np.any(hi <= lo):
            raise GeometryError(f"{nerede}: kutuda her eksende max > min olmalı")
        L = hi - lo
        c = (lo + hi) / 2
        return bd.Solid.make_box(*L).moved(bd.Location(tuple(c - L / 2)))
    if tur == "silindir":
        if not SILINDIR_ALAN <= s.keys():
            raise GeometryError(f"{nerede}: silindir alanları eksik ({sorted(SILINDIR_ALAN - s.keys())})")
        D, z0, z1 = (_sayi(nerede, s, a) for a in ("D", "zmin", "zmax"))
        d = _sayi(nerede, s, "d") if "d" in s else 0.0
        if D <= 0 or z1 <= z0 or not 0 <= d < D:
            raise GeometryError(f"{nerede}: silindir ölçüleri geçersiz (D={D}, d={d}, z=[{z0}, {z1}])")
        dis = bd.Solid.make_cylinder(D / 2, z1 - z0).moved(bd.Location((0, 0, z0)))
        if d > 0:
            ic = bd.Solid.make_cylinder(d / 2, z1 - z0).moved(bd.Location((0, 0, z0)))
            return dis.cut(ic)
        return dis
    raise GeometryError(f"{nerede}: bilinmeyen ilkel türü {tur!r}")


def primitives_part(prims: Sequence[dict], name: str) -> Part:
    """İlkellerin birleşimi; Part.name = name.

    Her ilkel {"shape": {"type": "kutu" | "silindir", ...}, "frame": {"origin", "R"}}.
    """
    if not prims:
        raise GeometryError(f"Bağlama parçası '{name}': ilkel listesi boş")
    katilar = []
    for i, p in enumerate(prims):
        nerede = f"Bağlama parçası '{name}', ilkel {i}"
        if not isinstance(p, dict) or "shape" not in p or "frame" not in p:
            raise GeometryError(f"{nerede}: {{'shape', 'frame'}} sözlüğü olmalı")
        T = _cerceve(nerede, p["frame"])
        katilar.append(_kati(nerede, p["shape"]).moved(bd.Location(_trsf(T))))
    sonuc = katilar[0]
    for k in katilar[1:]:
        sonuc = sonuc.fuse(k)
    sonuc = sonuc.clean()
    solids = list(sonuc.solids())
    if len(solids) == 1:
        sonuc = solids[0]
    return Part(sonuc, name=name)
