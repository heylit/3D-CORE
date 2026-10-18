"""
Kurulum: ham malzeme, iş sıfırı (WCS), güvenli yükseklik ve bağlama denetimi. SPEC 14.

Bağlama denetimi takım ucu noktasıyla, takım yarıçapı kadar şişirilmiş engelle yapılır (temkinli):
ρ = R + h/2 (freze R = D/2, torna R = nose_r), h örnekleme adımı. Yol h'den kısa parçalara
bölünür; h/2 şişirme örnekler arasında kaçan noktayı kapatır.
- Kutu eleman: [xmin − ρ, xmax + ρ] × [ymin − ρ, ymax + ρ] × [−∞, zmax + h/2]
- Silindir eleman (Z ekseni): hypot(x, y) ≤ D/2 + ρ ve zmin − ρ ≤ z ≤ zmax + ρ
Tutucu çarpışması ve talaş kaldırma SPEC 05'tir.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from cam.model import (
    _UVW,
    ARCS,
    CamError,
    CylinderStock,
    LatheTool,
    MoveType,
    Setup,
    Stock,
    Tool,
    Toolpath,
    Wcs,
    _arc_sweep,
    _center_uv,
    _sonlu,
)

CLEARANCE = 5.0  # mm, freze güvenli Z payı
CLEARANCE_R = 2.0  # mm, torna güvenli yarıçap payı
SAMPLE_STEP = 0.25  # mm, bağlama denetimi örnekleme adımı h


def _payli(nerede: str, **degerler) -> None:
    """Pay değerleri sonlu ve ≥ 0 olmalı."""
    _sonlu(nerede, **degerler)
    for ad, v in degerler.items():
        if np.any(np.asarray(v) < 0):
            raise CamError(f"{nerede}: {ad} negatif olamaz ({ad}={v})")


def stock_from_bbox(bmin, bmax, margin=(0.0, 0.0, 0.0)) -> Stock:
    """Sınır kutusundan eksen başına pay ile kutu ham malzeme."""
    bmin, bmax = np.asarray(bmin, dtype=float), np.asarray(bmax, dtype=float)
    m = np.broadcast_to(np.asarray(margin, dtype=float), (3,))
    _sonlu("Ham malzeme", bmin=bmin, bmax=bmax)
    _payli("Ham malzeme", margin=m)
    lo, hi = bmin - m, bmax + m
    return Stock(*lo, *hi)


def bar_stock_from_bbox(
    bmin, bmax, margin_r: float = 0.0, margin_z: float = 0.0, standard: Sequence[float] | None = None
) -> CylinderStock:
    """Z eksenli dönel parça için çubuk; standart çaplar verilirse en küçük uygun olanı.

    D = 2·max(|xmin|, |xmax|, |ymin|, |ymax|) + 2·margin_r (parça x = y = 0 ekseni etrafında dönel).
    """
    bmin, bmax = np.asarray(bmin, dtype=float), np.asarray(bmax, dtype=float)
    _sonlu("Çubuk ham malzeme", bmin=bmin, bmax=bmax)
    _payli("Çubuk ham malzeme", margin_r=margin_r, margin_z=margin_z)
    D = 2 * float(np.max(np.abs([bmin[0], bmax[0], bmin[1], bmax[1]]))) + 2 * margin_r
    if standard is not None:
        uygun = [float(s) for s in standard if s >= D - 1e-9]
        if not uygun:
            raise CamError(f"Çubuk ham malzeme: D = {D} için standart çap yok ({list(standard)})")
        D = min(uygun)
    return CylinderStock(D=D, zmin=float(bmin[2]) - margin_z, zmax=float(bmax[2]) + margin_z)


def wcs_from_touch(code: str, machine_point, work_point) -> Wcs:
    """Dokunulan noktanın makine ve iş koordinatından iş sıfırı: origin = m − w."""
    m, w = np.asarray(machine_point, dtype=float), np.asarray(work_point, dtype=float)
    if m.shape != (3,) or w.shape != (3,):
        raise CamError(f"İş sıfırı: noktalar 3 bileşenli olmalı ({machine_point}, {work_point})")
    _sonlu("İş sıfırı", machine_point=m, work_point=w)
    return Wcs(code, tuple(m - w))


def edge_position(machine_coord: float, probe_d: float, direction: int) -> float:
    """Kenar bulucu (çap d) `direction` (±1) yönünde dokunduğunda yüzeyin makine koordinatı: m + yön·d/2."""
    if isinstance(direction, bool) or direction not in (1, -1):
        raise CamError(f"Kenar bulucu: yön +1 veya −1 olmalı ({direction!r})")
    _sonlu("Kenar bulucu", machine_coord=machine_coord)
    _payli("Kenar bulucu", probe_d=probe_d)
    return machine_coord + direction * probe_d / 2


def _ustler(setup: Setup) -> list[Stock | CylinderStock]:
    return [setup.stock, *setup.fixtures]


def clearance_height(setup: Setup, clearance: float = CLEARANCE) -> float:
    """Ham malzeme ve bağlama elemanlarının en üst Z'si + pay."""
    _payli("Güvenli Z", clearance=clearance)
    return max(b.zmax for b in _ustler(setup)) + clearance


def _yaricap(b: Stock | CylinderStock) -> float:
    """Z eksenine en uzak nokta: silindirde D/2, kutuda köşelerin hypot(x, y) en büyüğü."""
    if isinstance(b, CylinderStock):
        return b.D / 2
    return max(math.hypot(x, y) for x in (b.xmin, b.xmax) for y in (b.ymin, b.ymax))


def safe_radius(setup: Setup, clearance: float = CLEARANCE_R) -> float:
    """Ham malzeme ve bağlama elemanlarının en büyük yarıçapı + pay (torna)."""
    _payli("Güvenli yarıçap", clearance=clearance)
    return max(_yaricap(b) for b in _ustler(setup)) + clearance


# ---------------------------------------------------------------- bağlama denetimi


def _ornekler(tp: Toolpath, h: float) -> list[tuple[MoveType, np.ndarray]]:
    """Her hareket için (tip, örnek noktalar (k, 3)); ardışık örnekler arası ≤ h, uçlar dahil."""
    iu, iv, iw = _UVW[tp.plane]
    out = []
    p0 = np.array(tp.start, dtype=float)
    for m in tp.moves:
        p1 = np.array(m.end, dtype=float)
        if m.type in ARCS:
            c = _center_uv(tp.plane, m.center)
            u0 = np.array([p0[iu], p0[iv]])
            r, dtheta = _arc_sweep(u0, np.array([p1[iu], p1[iv]]), c, m.type is MoveType.ARC_CW)
            s_len = math.hypot(r * dtheta, p1[iw] - p0[iw])
            k = max(2, math.ceil(s_len / h) + 1)
            t = np.linspace(0.0, 1.0, k)
            th0 = math.atan2(u0[1] - c[1], u0[0] - c[0])
            th = th0 + (-1 if m.type is MoveType.ARC_CW else 1) * dtheta * t
            P = np.zeros((k, 3))
            P[:, iu] = c[0] + r * np.cos(th)
            P[:, iv] = c[1] + r * np.sin(th)
            P[:, iw] = p0[iw] + (p1[iw] - p0[iw]) * t
            P[0], P[-1] = p0, p1
        else:
            k = max(2, math.ceil(float(np.linalg.norm(p1 - p0)) / h) + 1)
            P = p0 + np.linspace(0.0, 1.0, k)[:, None] * (p1 - p0)
        out.append((m.type, P))
        p0 = p1
    return out


def _icinde(b: Stock | CylinderStock, P: np.ndarray, rho: float, h: float) -> np.ndarray:
    """Şişirilmiş bağlama elemanının içindeki örnekler (bool maske)."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    if isinstance(b, CylinderStock):
        return (np.hypot(x, y) <= b.D / 2 + rho) & (z >= b.zmin - rho) & (z <= b.zmax + rho)
    return (
        (x >= b.xmin - rho)
        & (x <= b.xmax + rho)
        & (y >= b.ymin - rho)
        & (y <= b.ymax + rho)
        & (z <= b.zmax + h / 2)
    )


def _yol(op) -> Toolpath:
    if isinstance(op, Toolpath):
        return op
    if hasattr(op, "to_toolpath"):  # DrillOp (SPEC 04): kanonik açılım
        from cam.gcode.dialect import GRBL

        op.validate()
        return op.to_toolpath(GRBL)
    raise CamError(f"Denetlenemeyen op tipi: {type(op).__name__}")


def check_setup(setup: Setup, ops: list[Toolpath], h: float = SAMPLE_STEP) -> None:
    """Bağlamaya çarpma, ham malzeme altına inme, kesici boydan derin kesim → CamError."""
    _sonlu("Bağlama denetimi", h=h)
    if h <= 0:
        raise CamError(f"Bağlama denetimi: örnekleme adımı pozitif olmalı (h={h})")
    stock = setup.stock
    for op in ops:
        tp = _yol(op)
        tool = tp.tool
        R = tool.nose_r if isinstance(tool, LatheTool) else tool.D / 2
        rho = R + h / 2
        ornek = _ornekler(tp, h)
        P = np.vstack([np.array([tp.start], dtype=float)] + [p for _, p in ornek])
        for i, b in enumerate(setup.fixtures):
            ic = _icinde(b, P, rho, h)
            if ic.any():
                q = P[np.argmax(ic)]
                raise CamError(
                    f"Op '{tp.name}': bağlama elemanına (sıra {i}) çarpma,"
                    f" uç noktası ({q[0]:g}, {q[1]:g}, {q[2]:g})"
                )
        if not isinstance(tool, Tool):
            continue
        if isinstance(stock, Stock) and P[:, 2].min() < stock.zmin - 1e-9:
            q = P[np.argmin(P[:, 2])]
            raise CamError(
                f"Op '{tp.name}': ham malzemenin altına iniyor (z = {q[2]:g} < {stock.zmin:g}),"
                f" nokta ({q[0]:g}, {q[1]:g}, {q[2]:g})"
            )
        kesme = [p for t, p in ornek if t is not MoveType.RAPID]
        if kesme:
            z_min = min(float(p[:, 2].min()) for p in kesme)
            derinlik = stock.zmax - z_min
            if derinlik > tool.flute_length + 1e-9:
                raise CamError(
                    f"Op '{tp.name}': kesme derinliği {derinlik:g} mm, takım '{tool.name}' kesici boyu"
                    f" {tool.flute_length:g} mm"
                )
