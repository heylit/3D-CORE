"""
SPEC 06 — 3D takım yolları: raster ince işleme ve drop-cutter tabanlı katmanlı kaba işleme.

Her iki işlem de aynı raster kuruluşunu kullanır: XY dikdörtgeninde s aralıklı sıralar, zigzag;
sıralar arası geçiş sıra ucu boyunca bir çizgidir. Her çizgi ds aralıklı örneklenir, sonra
uyarlamalı bölünür (OpenCAMLib AdaptivePathDropCutter): orta noktadaki yükseklik ardışık iki CL'nin
doğrusal ara değerinden tol'dan fazla sapıyorsa araya nokta eklenir.

Birimler: mm, mm/dk, dev/dk.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from cam.dropcutter import TOL, TriMesh, _yaricap, drop
from cam.model import CamError, Move, MoveType, Stock, Tool, Toolpath
from cam.ops2d import depths

Yukseklik = Callable[[np.ndarray], np.ndarray]  # (k, 2) XY → (k,) z_CL


@dataclass
class Raster:
    """Raster alanı ve kesme parametreleri [mm, mm/dk, dev/dk]."""

    xmin: float
    xmax: float
    ymin: float
    ymax: float
    stepover: float  # sıra aralığı s
    ds: float  # çizgi üzerindeki ilk örnekleme aralığı
    tol: float  # uyarlamalı bölme toleransı
    ds_min: float  # bölmenin ineceği en küçük aralık
    feed: float
    plunge_feed: float
    rpm: float
    z_safe: float
    direction: str = "x"  # "x": X'e paralel sıralar, "y": Y'ye paralel
    clearance: float = 1.0

    def __post_init__(self) -> None:
        ad = ("xmin", "xmax", "ymin", "ymax", "stepover", "ds", "tol", "ds_min", "feed")
        ad += ("plunge_feed", "rpm", "z_safe", "clearance")
        for a in ad:
            if not math.isfinite(getattr(self, a)):
                raise CamError(f"Raster.{a} sonlu olmalı ({getattr(self, a)})")
        if not self.xmax > self.xmin or not self.ymax > self.ymin:
            raise CamError(f"Raster: xmax > xmin ve ymax > ymin olmalı ({self})")
        for a in ("stepover", "tol", "feed", "plunge_feed", "rpm"):
            if not getattr(self, a) > 0:
                raise CamError(f"Raster.{a} pozitif olmalı ({getattr(self, a)})")
        if not 0 < self.ds_min <= self.ds:
            raise CamError(f"Raster: 0 < ds_min ≤ ds olmalı (ds_min={self.ds_min}, ds={self.ds})")
        if self.clearance < 0:
            raise CamError(f"Raster.clearance negatif olamaz ({self.clearance})")
        if self.direction not in ("x", "y"):
            raise CamError(f"Raster.direction 'x' veya 'y' olmalı ({self.direction!r})")


def raster_lines(r: Raster) -> list[float]:
    """Sıraların sabit koordinatları: m = ⌈(üst − alt)/s⌉ + 1, eşit aralıklı, ilk ve son kenarda."""
    lo, hi = (r.ymin, r.ymax) if r.direction == "x" else (r.xmin, r.xmax)
    m = math.ceil((hi - lo) / r.stepover - 1e-9) + 1
    return [float(v) for v in np.linspace(lo, hi, m)]


def _cizgi(p: np.ndarray, q: np.ndarray, z_of: Yukseklik, r: Raster) -> np.ndarray:
    """p → q doğrusu üzerinde CL'ler (k, 3), uçlar dahil: ds örnekleme + uyarlamalı bölme."""
    L = float(np.hypot(*(q - p)))
    n = max(1, math.ceil(L / r.ds - 1e-9))
    t = np.linspace(0.0, 1.0, n + 1)
    z = z_of(p + t[:, None] * (q - p))
    while True:
        tm = (t[:-1] + t[1:]) / 2
        boy = (t[1:] - t[:-1]) * L
        aday = boy > 2 * r.ds_min
        if not np.any(aday):
            break
        zm = z_of(p + tm[aday, None] * (q - p))
        sapma = np.abs(zm - (z[:-1][aday] + z[1:][aday]) / 2)
        bol = sapma > r.tol
        if not np.any(bol):
            break
        yeni_t, yeni_z = tm[aday][bol], zm[bol]
        sira = np.searchsorted(t, yeni_t)
        t = np.insert(t, sira, yeni_t)
        z = np.insert(z, sira, yeni_z)
    xy = p + t[:, None] * (q - p)
    return np.column_stack([xy, z])


def _raster_cl(z_of: Yukseklik, r: Raster) -> np.ndarray:
    """Zigzag raster CL'leri (k, 3): sıralar ters yönlerde, aralarında sıra ucu boyunca geçiş."""
    akan = (r.xmin, r.xmax) if r.direction == "x" else (r.ymin, r.ymax)

    def nokta(sabit: float, a: float) -> np.ndarray:
        return np.array([a, sabit]) if r.direction == "x" else np.array([sabit, a])

    parcalar: list[np.ndarray] = []
    onceki = None
    for k, c in enumerate(raster_lines(r)):
        a0, a1 = akan if k % 2 == 0 else akan[::-1]
        p, q = nokta(c, a0), nokta(c, a1)
        if onceki is not None:
            parcalar.append(_cizgi(onceki, p, z_of, r)[1:])  # geçiş
        parcalar.append(_cizgi(p, q, z_of, r)[1 if onceki is not None else 0 :])
        onceki = q
    return np.vstack(parcalar)


def _gecis_z_safe(P: list[np.ndarray], r: Raster) -> None:
    z_ust = max(float(np.max(cl[:, 2])) for cl in P)
    if r.z_safe < z_ust + r.clearance - TOL:
        raise CamError(f"z_safe en yüksek CL'nin clearance üstünde olmalı (z_safe={r.z_safe}, z_CL={z_ust})")


def _yol(name: str, tool: Tool, r: Raster, seviyeler: list[tuple[np.ndarray, float]]) -> Toolpath:
    """Seviye başına CL dizisi ve yaklaşma yüksekliği → hareketler (giriş: G0, G0, G1 dalma)."""
    _gecis_z_safe([cl for cl, _ in seviyeler], r)
    ilk = seviyeler[0][0][0]
    tp = Toolpath(name=name, tool=tool, start=(ilk[0], ilk[1], r.z_safe), rpm=r.rpm)
    M = tp.moves
    for i, (cl, z_yak) in enumerate(seviyeler):
        x0, y0, z0 = cl[0]
        if i > 0:
            M.append(Move(MoveType.RAPID, (x0, y0, r.z_safe)))
        M.append(Move(MoveType.RAPID, (x0, y0, z_yak)))
        M.append(Move(MoveType.LINEAR, (x0, y0, z0), feed=r.plunge_feed))
        M.extend(Move(MoveType.LINEAR, tuple(p), feed=r.feed) for p in cl[1:])
        x1, y1, _ = cl[-1]
        M.append(Move(MoveType.RAPID, (x1, y1, r.z_safe)))
    tp.validate()
    return tp


def finish(mesh: TriMesh, tool: Tool, r: Raster, floor: float | None = None) -> Toolpath:
    """Raster ince işleme: her CL drop-cutter'dan (floor ile), uyarlamalı bölme, zigzag."""
    _yaricap(tool)  # desteklenmeyen takım → CamError

    def z_of(xy: np.ndarray) -> np.ndarray:
        return drop(mesh, tool, xy, floor)

    cl = _raster_cl(z_of, r)
    return _yol("ince-raster", tool, r, [(cl, cl[0, 2] + r.clearance)])


def rough(
    mesh: TriMesh,
    stock: Stock,
    tool: Tool,
    r: Raster,
    a_p: float,
    z_bottom: float,
    allowance: float = 0.0,
) -> Toolpath:
    """Katmanlı kaba işleme: her seviye z_i için z_CL = max(z_δ, z_i).

    İşleme payı δ: z_δ = drop(R + δ) + δ (büyütülmüş takım). Seviyeler cam.ops2d.depths ile.
    """
    _yaricap(tool)  # desteklenmeyen takım → CamError
    for ad, v in (("a_p", a_p), ("z_bottom", z_bottom), ("allowance", allowance)):
        if not math.isfinite(v):
            raise CamError(f"rough: {ad} sonlu olmalı ({v})")
    if not a_p > 0:
        raise CamError(f"rough: a_p pozitif olmalı ({a_p})")
    if allowance < 0:
        raise CamError(f"rough: allowance negatif olamaz ({allowance})")
    if not stock.zmin <= z_bottom < stock.zmax:
        raise CamError(f"rough: stock.zmin ≤ z_bottom < stock.zmax olmalı (z_bottom={z_bottom})")
    if not r.z_safe > stock.zmax:
        raise CamError(f"rough: z_safe ham malzemenin üstünde olmalı ({r.z_safe} ≤ {stock.zmax})")
    buyuk = tool
    if allowance > 0:
        buyuk = Tool(id=tool.id, name=tool.name, kind=tool.kind, D=tool.D + 2 * allowance,
                     flute_length=tool.flute_length)  # fmt: skip
    taban = z_bottom - allowance - 1.0  # ağın dışında: +δ sonrası z_bottom'ın altında kalır

    def z_delta(xy: np.ndarray) -> np.ndarray:
        return drop(mesh, buyuk, xy, floor=taban) + allowance

    seviyeler = []
    z_onceki = stock.zmax
    for zi in depths(stock.zmax, z_bottom, a_p):
        cl = _raster_cl(lambda xy, zi=zi: np.maximum(z_delta(xy), zi), r)
        seviyeler.append((cl, max(cl[0, 2], z_onceki) + r.clearance))
        z_onceki = zi
    return _yol("kaba-katman", tool, r, seviyeler)
