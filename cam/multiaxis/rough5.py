"""
SPEC 50 — 5 eksen kaba: yönelim kümesinde (3+2) stok bilinçli katmanlı kaba işleme.

Her yönelim F_i için ağ ve stok yerel çerçeveye çevrilir, SPEC 06 katmanlı kaba yerelde çalışır;
o ana kadarki tri-dexel stokta v_min'den az malzeme kaldıran ardışık G1'ler güvenli yükseklikte G0 bağlantıya
çevrilir. Böylece ikinci yönelim ilkinin temizlediği yeri yeniden kesmez.

Ek A: yerel raster = yerel stoğun XY'si, ds = stepover, ds_min = DS_MIN, tol = 0.01, z_safe = zmax_yerel + 5,
direction = "x", z_bottom = max(zmin_yerel_stok, zmin_yerel_ağ). Son stok yolların sırayla (her biri bir
öncekinin stoğundan) simülasyonudur.

Birimler: mm, mm/dk, dev/dk, derece.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import CamError, Frame, Move, MoveType, PathMeta, Setup, Stock, Tool, ToolKind, Toolpath
from cam.multiaxis.collision import check
from cam.multiaxis.indexed import local_mesh, local_stock
from cam.multiaxis.machine import MachineModel
from cam.ops3d import Raster, rough
from cam.sim.simulate5 import simulate5
from cam.sim.tridexel import TriDexel

DS_MIN = 0.05  # mm, yerel raster'da uyarlamalı bölmenin en küçük aralığı (Ek A, test yazarı önerisi)
RASTER_TOL = 0.01  # mm
SAFE = 5.0  # mm, yerel stok üstünden z_safe
V_ORAN = 0.01  # v_min = V_ORAN·ae·ap·L


@dataclass
class RoughCut:
    """06 kaba parametreleri (SPEC 50 Ek A); yerel raster ve z_bottom yönelimde yerel stoktan türetilir."""

    a_p: float  # eksenel kesme derinliği
    stepover: float  # radyal adım (raster sıra aralığı)
    feed: float
    plunge_feed: float
    rpm: float
    allowance: float = 0.0
    clearance: float = 1.0

    def __post_init__(self) -> None:
        for ad in ("a_p", "stepover", "feed", "plunge_feed", "rpm", "allowance", "clearance"):
            v = getattr(self, ad)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise CamError(f"RoughCut.{ad} sonlu sayı olmalı ({v!r})")
        for ad in ("a_p", "stepover", "feed", "plunge_feed", "rpm"):
            if not getattr(self, ad) > 0:
                raise CamError(f"RoughCut.{ad} pozitif olmalı ({getattr(self, ad)})")
        for ad in ("allowance", "clearance"):
            if getattr(self, ad) < 0:
                raise CamError(f"RoughCut.{ad} negatif olamaz ({getattr(self, ad)})")


def _raster(st: Stock, cut: RoughCut) -> Raster:
    return Raster(
        xmin=st.xmin,
        xmax=st.xmax,
        ymin=st.ymin,
        ymax=st.ymax,
        stepover=cut.stepover,
        ds=cut.stepover,
        tol=RASTER_TOL,
        ds_min=min(DS_MIN, cut.stepover),
        feed=cut.feed,
        plunge_feed=cut.plunge_feed,
        rpm=cut.rpm,
        z_safe=st.zmax + SAFE,
        direction="x",
        clearance=cut.clearance,
    )


def _egim(F: Frame) -> float:
    """Yönelim ekseninin (yerel +z) +Z ile açısı [derece]."""
    ez = np.array(F.R, dtype=float)[:, 2]
    return math.degrees(math.atan2(math.hypot(ez[0], ez[1]), ez[2]))


def _hava_atla(
    tp: Toolpath, removed: list[float], v_min: float | None, cut: RoughCut, z_safe: float
) -> Toolpath:
    """v_min'den az kaldıran ardışık G1'leri z_safe'te G0 bağlantıya çevirir (yerel koordinat)."""
    P = [np.array(tp.start, dtype=float)] + [np.array(m.end, dtype=float) for m in tp.moves]

    def hava(k: int) -> bool:
        m = tp.moves[k]
        if m.type is not MoveType.LINEAR:
            return False
        esik = (
            V_ORAN * cut.stepover * cut.a_p * float(np.linalg.norm(P[k + 1] - P[k]))
            if v_min is None
            else v_min
        )
        return removed[k] < esik

    moves: list[Move] = []
    n = len(tp.moves)
    k = 0
    while k < n:
        if not hava(k):
            moves.append(tp.moves[k])
            k += 1
            continue
        b = k
        while b + 1 < n and hava(b + 1):
            b += 1
        A, B = P[k], P[b + 1]
        if abs(A[2] - z_safe) > 1e-9:
            moves.append(Move(MoveType.RAPID, (float(A[0]), float(A[1]), z_safe)))
        if b + 1 < n and tp.moves[b + 1].type is not MoveType.RAPID:
            moves.append(Move(MoveType.RAPID, (float(B[0]), float(B[1]), z_safe)))
            moves.append(Move(MoveType.RAPID, tuple(float(v) for v in B)))
        k = b + 1
    return dataclasses.replace(tp, moves=moves)


def rough5(
    mesh: TriMesh,
    stock: Stock,
    tool: Tool,
    frames: list[Frame],
    cut: RoughCut,
    cell: float = 1.0,
    v_min: float | None = None,
    machine: MachineModel | None = None,
    setup: Setup | None = None,
    max_tilt: float = 30.0,
) -> tuple[list[Toolpath], TriDexel]:
    """Yönelim listesiyle kaba işleme; her yol frame = F_i, meta (kaba, 3+2). Son stok da döner.

    max_tilt [°]: yönelim ekseninin +Z ile en büyük açısı (Ek A kararı, varsayılan 30°); aşan F_i → CamError.
    machine verilirse setup zorunlu; her yol 44 check ile denetlenir.
    v_min [mm³]: None → hareket başına 0.01·ae·ap·L; 0 → hava atlama kapalı.
    """
    if not isinstance(frames, (list, tuple)) or len(frames) == 0:
        raise CamError("rough5: yönelim listesi boş olamaz")
    if any(not isinstance(F, Frame) for F in frames):
        raise CamError("rough5: yönelimler Frame olmalı")
    if tool.kind not in (ToolKind.BALL, ToolKind.FLAT):
        raise CamError(f"rough5: yalnız küresel ve düz uç desteklenir ({tool.kind.value})")
    if not isinstance(cut, RoughCut):
        raise CamError(f"rough5: cut RoughCut olmalı ({type(cut).__name__})")
    if not (math.isfinite(cell) and cell > 0):
        raise CamError(f"rough5: cell pozitif olmalı ({cell})")
    if v_min is not None and not (math.isfinite(v_min) and v_min >= 0):
        raise CamError(f"rough5: v_min negatif olmayan sonlu sayı olmalı ({v_min})")
    if not (math.isfinite(max_tilt) and 0 <= max_tilt <= 180):
        raise CamError(f"rough5: max_tilt 0..180° olmalı ({max_tilt})")
    if machine is not None and setup is None:
        raise CamError("rough5: machine verildiğinde setup zorunlu")
    for i, F in enumerate(frames):
        if _egim(F) > max_tilt + 1e-9:
            raise CamError(f"rough5: yönelim {i} ekseni +Z ile {_egim(F):.3f}° > max_tilt {max_tilt}°")
    meta = PathMeta(strategy="kaba", axis_mode="3+2", allowance=cut.allowance, ap=cut.a_p, ae=cut.stepover)
    yollar: list[Toolpath] = []
    td: TriDexel | None = None
    for i, F in enumerate(frames):
        ls, lm = local_stock(stock, F), local_mesh(mesh, F)
        z_bottom = max(ls.zmin, float(lm.bbox()[0][2]))
        r = _raster(ls, cut)
        tp = rough(lm, ls, tool, r, cut.a_p, z_bottom, cut.allowance)
        tp = dataclasses.replace(tp, name=f"kaba-5x-{i + 1}", frame=F, meta=meta)
        sim = simulate5([tp], stock, cell=cell, initial=td)
        if v_min != 0:
            atla = _hava_atla(tp, [s.removed for s in sim.steps], v_min, cut, r.z_safe)
            if atla.moves != tp.moves:
                tp = atla
                sim = simulate5([tp], stock, cell=cell, initial=td)
        tp.validate()
        yollar.append(tp)
        td = sim.tridexel
    if machine is not None:
        olaylar = check(machine, setup, yollar)
        if olaylar:
            raise CamError(f"rough5: tezgâh denetimi {len(olaylar)} olay buldu, ilki: {olaylar[0]}")
    return yollar, td
