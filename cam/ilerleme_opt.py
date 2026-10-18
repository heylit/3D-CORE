"""
İlerleme optimizasyonu: talaş incelmesi ve iş mili güç / tork sınırına göre F ayarı. SPEC 32.

Geometri değişmez; yalnız Move.feed değerleri yeniden hesaplanır. Yeni program yeniden simüle edilip
yükleri doğrulanır.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, replace

import numpy as np

from cam.gcode import DrillOp
from cam.kuvvet import (
    KienzleMaterial,
    Load,
    Overload,
    SpindleLimits,
    _bos_yuk,
    _hareket_indeksleri,
    _pozitif,
    _sonlu,
    check_spindle,
    lathe_loads,
    max_chip_thickness,
    milling_loads,
)
from cam.model import ARCS, CamError, CylinderStock, LatheTool, Move, MoveType, Plane, Stock, Toolpath
from cam.sim import Machine, simulate

# Düzlem → (u, v, w) eksen indisleri (cam/model.py ile aynı kural: G3 u'dan v'ye, w helis ekseni)
_UVW = {Plane.XY: (0, 1, 2), Plane.ZX: (2, 0, 1)}


# ---------------------------------------------------------------- bölütleme


def _varsayilan_seg(tool) -> float:
    if isinstance(tool, LatheTool):
        return max(2 * tool.nose_r, 1.0)
    return tool.D / 2


def _merkez_uv(plane: Plane, center) -> np.ndarray:
    """Merkez tuple'ı (XY: (x, y), ZX: (x, z)) → (u, v)."""
    c = np.asarray(center, dtype=float)
    return c if plane is Plane.XY else c[::-1].copy()


def _bol(tp: Toolpath, p0: np.ndarray, m: Move, seg: float) -> list[Move]:
    """Tek hareketi boyu ≤ seg parçalara böler (G0 bölünmez)."""
    p1 = np.asarray(m.end, dtype=float)
    if m.type is MoveType.RAPID:
        return [replace(m)]
    if m.type in ARCS:
        iu, iv, iw = _UVW[tp.plane]
        c = _merkez_uv(tp.plane, m.center)
        a0 = np.array([p0[iu], p0[iv]]) - c
        a1 = np.array([p1[iu], p1[iv]]) - c
        r = float(np.hypot(*a0))
        th0 = math.atan2(a0[1], a0[0])
        dth = math.atan2(a1[1], a1[0]) - th0
        cw = m.type is MoveType.ARC_CW
        if cw:
            dth = -dth
        dth %= 2 * math.pi
        if dth < 1e-12:
            dth = 2 * math.pi  # aynı nokta: tam daire
        L = math.hypot(r * dth, p1[iw] - p0[iw])
        n = max(1, math.ceil(L / seg))
        s = -1.0 if cw else 1.0
        out = []
        for i in range(1, n + 1):
            if i == n:
                e = tuple(p1)
            else:
                th = th0 + s * dth * i / n
                q = np.empty(3)
                q[iu] = c[0] + r * math.cos(th)
                q[iv] = c[1] + r * math.sin(th)
                q[iw] = p0[iw] + (p1[iw] - p0[iw]) * i / n
                e = tuple(float(v) for v in q)
            out.append(Move(m.type, e, feed=m.feed, center=m.center))
        return out
    L = float(np.linalg.norm(p1 - p0))
    n = max(1, math.ceil(L / seg))
    return [
        Move(m.type, tuple(p1) if i == n else tuple(float(v) for v in p0 + (p1 - p0) * i / n), feed=m.feed)
        for i in range(1, n + 1)
    ]


def split_moves(
    ops: list[Toolpath | DrillOp], seg: float | None = None
) -> tuple[list[Toolpath | DrillOp], list[tuple[int, int | None]]]:
    """Kesme hareketlerini boyu ≤ seg bölütlere ayırır; her yeni (op, hareket) için özgün hareket indeksi."""
    if seg is not None:
        _pozitif("Bölütleme", seg=seg)
    yeni: list[Toolpath | DrillOp] = []
    eslem: list[tuple[int, int | None]] = []
    for i, op in enumerate(ops):
        if isinstance(op, DrillOp):
            yeni.append(op)
            continue
        s = _varsayilan_seg(op.tool) if seg is None else seg
        moves: list[Move] = []
        p0 = np.array(op.start, dtype=float)
        for j, m in enumerate(op.moves):
            parca = _bol(op, p0, m, s)
            moves += parca
            eslem += [(i, j)] * len(parca)
            p0 = np.array(m.end, dtype=float)
        yeni.append(replace(op, moves=moves))
    return yeni, eslem


# ---------------------------------------------------------------- sonuç tipleri


@dataclass
class FeedChange:
    """reason ∈ {"inceltme", "guc", "tork", "en_cok", "ilerleme_siniri", "en_az", "hava", "degismedi"}."""

    op: int
    move: int
    F_old: float
    F_new: float
    reason: str


@dataclass
class FeedPlan:
    ops: list[Toolpath | DrillOp]
    changes: list[FeedChange]
    loads_before: list[Load]
    loads_after: list[Load]
    overloads_before: list[Overload]
    overloads_after: list[Overload]
    skipped: list[int]
    t_before: float
    t_after: float


# ---------------------------------------------------------------- yardımcılar


def _tur(ops: list) -> str:
    """'freze' veya 'torna'; karışık → CamError."""
    turler = set()
    for op in ops:
        if isinstance(op, DrillOp):
            turler.add("freze")
        elif isinstance(op, Toolpath):
            turler.add("torna" if isinstance(op.tool, LatheTool) else "freze")
        else:
            raise CamError(f"İlerleme optimizasyonu: Toolpath veya DrillOp bekleniyor ({type(op).__name__})")
    if not turler:
        raise CamError("İlerleme optimizasyonu: boş program")
    if len(turler) > 1:
        raise CamError("İlerleme optimizasyonu: freze ve torna yolları aynı programda olamaz")
    return turler.pop()


def _segment_eslemi(eslem: list[tuple[int, int | None]], n_ops: int) -> list[list[int]]:
    """split_moves eşlemesinden op başına: bölüt hareket indeksi → özgün hareket indeksi."""
    tablo: list[list[int]] = [[] for _ in range(n_ops)]
    for op, j in eslem:
        tablo[op].append(j)
    return tablo


def _indirge(seg_loads: list[Load], tablo: list[list[int]], hedef_ops: list, hedef_steps) -> list[Load]:
    """Bölüt yüklerini hedef programın adımlarına indirger: her hareket için en büyük P'li bölüt."""
    enkotu: dict[tuple[int, int], Load] = {}
    for ld in seg_loads:
        if ld.move is None:
            continue
        key = (ld.op, tablo[ld.op][ld.move])
        eski = enkotu.get(key)
        if eski is None or (ld.kind == "kesme" and (eski.kind != "kesme" or ld.P > eski.P)):
            enkotu[key] = ld
    sonuc = []
    for s, j in zip(hedef_steps, _hareket_indeksleri(hedef_ops, hedef_steps), strict=True):
        if j is None:
            sonuc.append(_bos_yuk(s.k, s.op, None, "atlandi"))
            continue
        ld = enkotu[(s.op, j)]
        sonuc.append(replace(ld, k=s.k, op=s.op, move=j))
    return sonuc


def _katsayi(ld: Load, tp: Toolpath, F: float, mat: KienzleMaterial, limits: SpindleLimits, max_factor: float,
             target_hex: float | None) -> tuple[float, str]:  # fmt: skip
    """Bir kesme bölütü için c = min(c_ince, c_P, c_M, max_factor) ve gerekçesi."""
    adaylar: list[tuple[float, str]] = []
    if not isinstance(tp.tool, LatheTool):
        fz = F / (tp.rpm * tp.tool.flutes)
        hedef = fz if target_hex is None else target_hex
        adaylar.append((hedef / max_chip_thickness(fz, ld.ae, tp.tool.D), "inceltme"))
    us = 1 / (1 - mat.mc)
    if limits.P_max is not None and ld.P > 0:
        adaylar.append(((limits.eta * limits.P_max / ld.P) ** us, "guc"))
    if limits.M_max is not None and ld.M > 0:
        adaylar.append(((limits.eta * limits.M_max / ld.M) ** us, "tork"))
    adaylar.append((max_factor, "en_cok"))
    return min(adaylar, key=lambda a: a[0])


def _yeni_ilerleme(F: float, c: float, reason: str, min_factor: float, feed_max: float | None,
                   res: float) -> tuple[float, str]:  # fmt: skip
    """F' = ⌊min(F·c, feed_max)/res⌋·res; c < min_factor → F·min_factor ("en_az")."""
    if c < min_factor:
        Fn, reason = F * min_factor, "en_az"
    else:
        Fn = F * c
    if feed_max is not None and Fn > feed_max:
        Fn, reason = feed_max, "ilerleme_siniri"
    elif math.isclose(Fn, F, rel_tol=1e-12):
        return F, "degismedi"
    Fn = math.floor(Fn / res + 1e-9) * res
    if Fn <= 0:
        raise CamError(f"İlerleme optimizasyonu: yeni ilerleme pozitif değil (F={F}, c={c}, res={res})")
    return (F, "degismedi") if Fn == F else (Fn, reason)


def _hava_ilerlemesi(F: float, air_feed: float | None, feed_max: float | None) -> tuple[float, str]:
    if air_feed is None:
        return F, "degismedi"
    Fn = air_feed if feed_max is None else min(air_feed, feed_max)
    return (F, "degismedi") if Fn == F else (Fn, "hava")


def _birlestir(parcalar: list[tuple[Move, float]], ozgun: Move) -> list[Move]:
    """Aynı özgün hareketin ardışık eşit ilerlemeli bölütlerini birleştirir."""
    if all(F == parcalar[0][1] for _, F in parcalar):
        return [replace(ozgun, feed=parcalar[0][1])]
    out: list[Move] = []
    for m, F in parcalar:
        if out and out[-1].feed == F:
            out[-1] = replace(out[-1], end=m.end)
        else:
            out.append(replace(m, feed=F))
    return out


# ---------------------------------------------------------------- optimizasyon


def optimize_feed(
    ops: list[Toolpath | DrillOp],
    stock: Stock | CylinderStock,
    material: KienzleMaterial,
    limits: SpindleLimits,
    *,
    feed_max: float | None = None,
    seg: float | None = None,
    split: bool = False,
    air_feed: float | None = None,
    max_factor: float = 2.0,
    min_factor: float = 0.1,
    target_hex: float | None = None,
    resolution: float = 0.1,
    K: float = 1.0,
    cell: float | None = None,
    machine: Machine | None = None,
) -> FeedPlan:
    """Freze (simulate) veya torna (simulate_lathe) programının ilerlemesini ayarlar; girdi değişmez."""
    nerede = "İlerleme optimizasyonu"
    _sonlu(nerede, max_factor=max_factor, min_factor=min_factor)
    if max_factor < 1:
        raise CamError(f"{nerede}: max_factor ≥ 1 olmalı ({max_factor})")
    if not 0 < min_factor <= 1:
        raise CamError(f"{nerede}: 0 < min_factor ≤ 1 olmalı ({min_factor})")
    _pozitif(nerede, resolution=resolution, K=K)
    for ad, v in (("feed_max", feed_max), ("air_feed", air_feed), ("target_hex", target_hex), ("seg", seg)):
        if v is not None:
            _pozitif(nerede, **{ad: v})
    tur = _tur(ops)
    if tur == "freze":
        sim, yuk_fn = simulate, milling_loads
        cell = 0.5 if cell is None else cell
    else:
        try:
            from cam.sim import simulate_lathe
        except ImportError as e:
            raise CamError(f"{nerede}: torna simülasyonu (SPEC 22) yok") from e
        sim, yuk_fn = simulate_lathe, lathe_loads
        cell = 0.25 if cell is None else cell

    def simule(program):
        return sim(program, stock, cell=cell, machine=machine)

    def analiz(program, tablo_ust: list[list[int]] | None = None):
        """Bölünmüş programın yükleri, program hareketine (tablo_ust ile özgün harekete) indirgenmiş."""
        bolunmus, eslem = split_moves(program, seg)
        seg_loads = yuk_fn(bolunmus, simule(bolunmus), material, K)
        tablo = _segment_eslemi(eslem, len(program))
        if tablo_ust is not None:
            tablo = [[tablo_ust[i][j] for j in t] for i, t in enumerate(tablo)]
        return bolunmus, eslem, seg_loads, tablo

    girdi = copy.deepcopy(ops)
    r0 = simule(girdi)
    bolunmus, eslem, seg_loads, tablo = analiz(girdi)
    loads_before = _indirge(seg_loads, tablo, girdi, r0.steps)

    # bölüt başına yeni ilerleme
    # (op, bölüt) → (F', gerekçe, c, ham gerekçe); havadaki bölütte c = inf
    seg_F: dict[tuple[int, int], tuple[float, str, float, str]] = {}
    for ld in seg_loads:
        if ld.move is None:
            continue
        tp = girdi[ld.op]
        m = bolunmus[ld.op].moves[ld.move]
        if m.type is MoveType.RAPID:
            continue
        if ld.kind == "kesme":
            c, ham = _katsayi(ld, tp, m.feed, material, limits, max_factor, target_hex)
            Fn, reason = _yeni_ilerleme(m.feed, c, ham, min_factor, feed_max, resolution)
        else:
            c, ham = math.inf, "hava"
            Fn, reason = _hava_ilerlemesi(m.feed, air_feed, feed_max)
        seg_F[(ld.op, ld.move)] = (Fn, reason, c, ham)

    yeni_ops: list[Toolpath | DrillOp] = []
    changes: list[FeedChange] = []
    skipped: list[int] = []
    yeni_ozgun: list[list[int]] = []  # split=True: yeni hareket → özgün hareket
    for i, op in enumerate(girdi):
        if isinstance(op, DrillOp):
            yeni_ops.append(op)
            skipped.append(i)
            yeni_ozgun.append([])
            continue
        bolutler: dict[int, list[int]] = {}
        for b, j in enumerate(tablo[i]):
            bolutler.setdefault(j, []).append(b)
        moves: list[Move] = []
        ozgun_idx: list[int] = []
        for j, m in enumerate(op.moves):
            if m.type is MoveType.RAPID:
                moves.append(replace(m))
                ozgun_idx.append(j)
                continue
            kayit = [seg_F[(i, b)] for b in bolutler[j]]
            kesen = [x for x in kayit if x[2] != math.inf]
            if kesen:
                # özgün hareket: bölütlerin en küçük c'si (split=True'da değişiklik kaydı en temkinli bölüt)
                _, _, c, ham = min(kesen, key=lambda x: x[2])
                Fn, reason = _yeni_ilerleme(m.feed, c, ham, min_factor, feed_max, resolution)
            else:
                Fn, reason = kayit[0][0], kayit[0][1]
            changes.append(FeedChange(op=i, move=j, F_old=m.feed, F_new=Fn, reason=reason))
            if split:
                parcalar = [(bolunmus[i].moves[b], seg_F[(i, b)][0]) for b in bolutler[j]]
                yeni = _birlestir(parcalar, m)
            else:
                yeni = [replace(m, feed=Fn)]
            moves += yeni
            ozgun_idx += [j] * len(yeni)
        yeni_ops.append(replace(op, moves=moves))
        yeni_ozgun.append(ozgun_idx)

    r1 = simule(yeni_ops)
    _, _, seg_after, tablo_after = analiz(yeni_ops, yeni_ozgun)
    # loads_after özgün hareketlere indirgenir; adım numaraları özgün programınkidir
    loads_after = _indirge(seg_after, tablo_after, girdi, r0.steps)
    return FeedPlan(
        ops=yeni_ops,
        changes=changes,
        loads_before=loads_before,
        loads_after=loads_after,
        overloads_before=check_spindle(loads_before, limits),
        overloads_after=check_spindle(loads_after, limits),
        skipped=skipped,
        t_before=float(r0.total_time),
        t_after=float(r1.total_time),
    )
