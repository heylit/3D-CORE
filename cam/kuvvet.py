"""
Kesme kuvveti (Kienzle), kesme gücü, iş mili torku ve iş mili sınırı denetimi. SPEC 32.

Birimler: kuvvet N, uzunluk mm, özgül kesme kuvveti N/mm² (= MPa), güç kW, tork N·m,
talaş debisi Q mm³/s, devir dev/dk. Simülasyon sonuçları (SPEC 05 / 22) yalnız okunur.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from cam.gcode import DrillOp
from cam.model import CamError, FeedMode, LatheTool, Move, MoveType, Plane, Toolpath
from cam.sim import Machine, SimResult, move_time

if TYPE_CHECKING:
    from cam.model import MachineProfile  # A0 arayüz eki (SPEC 30)
    from cam.sim import LatheSimResult  # SPEC 22

ETA = 0.8  # iş mili verimi varsayılanı (kullanıcı kararı, 2026-10-18)


def _sonlu(nerede: str, **degerler) -> None:
    """Her değer sonlu olmalı; nan / inf → CamError."""
    for ad, v in degerler.items():
        if not np.all(np.isfinite(np.asarray(v, dtype=float))):
            raise CamError(f"{nerede}: {ad} sonlu olmalı ({ad}={v})")


def _pozitif(nerede: str, **degerler) -> None:
    _sonlu(nerede, **degerler)
    for ad, v in degerler.items():
        if np.any(np.asarray(v, dtype=float) <= 0):
            raise CamError(f"{nerede}: {ad} pozitif olmalı ({ad}={v})")


# ---------------------------------------------------------------- malzeme


@dataclass(frozen=True)
class KienzleMaterial:
    """Kienzle malzeme verisi: kc11 [N/mm²] (b = h = 1 mm), mc [−] (0 ≤ mc < 1)."""

    name: str
    kc11: float
    mc: float

    def __post_init__(self) -> None:
        nerede = f"Malzeme '{self.name}'"
        _pozitif(nerede, kc11=self.kc11)
        _sonlu(nerede, mc=self.mc)
        if not 0 <= self.mc < 1:
            raise CamError(f"{nerede}: 0 ≤ mc < 1 olmalı (mc={self.mc})")

    def to_dict(self) -> dict:
        return {"name": self.name, "kc11": self.kc11, "mc": self.mc}

    @classmethod
    def from_dict(cls, d: dict) -> KienzleMaterial:
        eksik = {"name", "kc11", "mc"} - d.keys()
        fazla = d.keys() - {"name", "kc11", "mc", "kaynak"}
        if eksik or fazla:
            raise CamError(f"Malzeme: eksik alan {sorted(eksik)}, bilinmeyen alan {sorted(fazla)}")
        return cls(name=d["name"], kc11=d["kc11"], mc=d["mc"])


def load_materials(path) -> dict[str, KienzleMaterial]:
    """UTF-8 JSON {"malzemeler": [{name, kc11, mc, kaynak}]} → ada göre sözlük."""
    p = Path(path)
    try:
        veri = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise CamError(f"Malzeme dosyası yok: {p}") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise CamError(f"Malzeme dosyası bozuk: {p} ({e})") from e
    if not isinstance(veri, dict) or not isinstance(veri.get("malzemeler"), list):
        raise CamError(f"Malzeme dosyası: 'malzemeler' listesi yok ({p})")
    sonuc: dict[str, KienzleMaterial] = {}
    for d in veri["malzemeler"]:
        if not isinstance(d, dict):
            raise CamError(f"Malzeme dosyası: kayıt sözlük olmalı ({d!r})")
        if not isinstance(d.get("kaynak"), str) or not d["kaynak"].strip():
            raise CamError(f"Malzeme '{d.get('name')}': 'kaynak' (metin) zorunlu")
        m = KienzleMaterial.from_dict(d)
        if m.name in sonuc:
            raise CamError(f"Malzeme dosyası: yinelenen ad '{m.name}'")
        sonuc[m.name] = m
    return sonuc


# ---------------------------------------------------------------- Kienzle


def specific_force(mat: KienzleMaterial, h, K: float = 1.0):
    """kc(h) = K·kc11·h^(−mc) [N/mm²]; h ≤ 0, K ≤ 0 → CamError."""
    _pozitif("Özgül kesme kuvveti", h=h, K=K)
    kc = K * mat.kc11 * np.asarray(h, dtype=float) ** (-mat.mc)
    return float(kc) if np.ndim(kc) == 0 else kc


def kienzle_force(mat: KienzleMaterial, b: float, h: float, K: float = 1.0) -> float:
    """Fc = K·kc11·b·h^(1−mc) [N]."""
    _pozitif("Kienzle kuvveti", b=b)
    return float(b * h * specific_force(mat, h, K))


def turning_force(mat: KienzleMaterial, ap: float, f: float, kappa_r: float = 90.0, K: float = 1.0) -> float:
    """Torna: h = f·sin κr, b = ap/sin κr → Fc [N]; 0 < κr ≤ 90."""
    _pozitif("Torna kuvveti", ap=ap, f=f, kappa_r=kappa_r)
    if kappa_r > 90:
        raise CamError(f"Torna kuvveti: 0 < κr ≤ 90 olmalı (κr={kappa_r})")
    s = math.sin(math.radians(kappa_r))
    return kienzle_force(mat, ap / s, f * s, K)


def engagement_angle(ae: float, D: float) -> float:
    """φe = arccos(1 − 2·ae/D) [rad]; 0 < ae ≤ D."""
    _pozitif("Kavrama", ae=ae, D=D)
    if ae > D:
        raise CamError(f"Kavrama: ae ≤ D olmalı (ae={ae}, D={D})")
    return math.acos(max(-1.0, 1 - 2 * ae / D))


def mean_chip_thickness(fz: float, ae: float, D: float) -> float:
    """hm = fz·(2·ae/D)/φe [mm]."""
    phi = engagement_angle(ae, D)
    _pozitif("Talaş kalınlığı", fz=fz)
    return fz * (2 * ae / D) / phi


def max_chip_thickness(fz: float, ae: float, D: float) -> float:
    """hex = fz·sin(min(φe, π/2)) [mm]."""
    phi = engagement_angle(ae, D)
    _pozitif("Talaş kalınlığı", fz=fz)
    return fz * math.sin(min(phi, math.pi / 2))


def cutting_power(Q: float, kc: float) -> float:
    """P = Q·kc/10⁶ [kW]; Q mm³/s, kc N/mm²."""
    _sonlu("Kesme gücü", Q=Q, kc=kc)
    return Q * kc / 1e6


def spindle_torque(P: float, n: float) -> float:
    """M = 60000·P/(2π·n) [N·m]; n ≤ 0 → CamError."""
    _sonlu("İş mili torku", P=P)
    _pozitif("İş mili torku", n=n)
    return 60000 * P / (2 * math.pi * n)


# ---------------------------------------------------------------- iş mili sınırları


@dataclass(frozen=True)
class SpindleLimits:
    """İş mili sınırları: P_max [kW], M_max [N·m] (None → denetlenmez), verim eta (0 < eta ≤ 1)."""

    P_max: float | None = None
    M_max: float | None = None
    eta: float = ETA

    def __post_init__(self) -> None:
        for ad in ("P_max", "M_max"):
            v = getattr(self, ad)
            if v is not None:
                _pozitif("İş mili sınırı", **{ad: v})
        _pozitif("İş mili sınırı", eta=self.eta)
        if self.eta > 1:
            raise CamError(f"İş mili sınırı: 0 < eta ≤ 1 olmalı (eta={self.eta})")

    @classmethod
    def from_profile(cls, profile: MachineProfile, eta: float = ETA) -> SpindleLimits:
        """MachineProfile.spindle_power_kw / spindle_torque_nm (A0) alanlarından."""
        return cls(P_max=profile.spindle_power_kw, M_max=profile.spindle_torque_nm, eta=eta)


@dataclass
class Load:
    """Bir simülasyon adımının yükü. kind ∈ {"kesme", "hava", "atlandi"}."""

    k: int
    op: int
    move: int | None
    kind: str
    ap: float
    ae: float | None
    h: float | None
    kc: float | None
    Q: float
    P: float
    M: float
    F_t: float | None


@dataclass
class Overload:
    """İş mili sınırı aşımı. kind ∈ {"guc", "tork"}; value P/η veya M/η, limit P_max veya M_max."""

    k: int
    op: int
    move: int | None
    kind: str
    value: float
    limit: float


def _bos_yuk(k: int, op: int, move: int | None, kind: str) -> Load:
    return Load(k, op, move, kind, ap=0.0, ae=None, h=None, kc=None, Q=0.0, P=0.0, M=0.0, F_t=None)


def _hareket_indeksleri(ops: list, steps) -> list[int | None]:
    """Her adım için özgün ops[op].moves indeksi (bağlantı ve DrillOp → None); uyuşmazlık → CamError."""
    sayac = [0] * len(ops)
    sonuc: list[int | None] = []
    for s in steps:
        if not 0 <= s.op < len(ops):
            raise CamError(f"Yük: adım {s.k} op {s.op} programda yok ({len(ops)} op)")
        op = ops[s.op]
        if s.link or isinstance(op, DrillOp):
            sonuc.append(None)
            continue
        sonuc.append(sayac[s.op])
        sayac[s.op] += 1
    for i, op in enumerate(ops):
        if isinstance(op, Toolpath) and sayac[i] != len(op.moves):
            raise CamError(f"Yük: op {i} '{op.name}' {len(op.moves)} hareket, sonuçta {sayac[i]} adım")
    return sonuc


def _adim_hareketi(s) -> Move:
    return Move(s.type, s.end, feed=s.feed, center=s.center)


def _derinlikler(result: SimResult) -> np.ndarray:
    """Adım başına en derin kesim ap_k = max_hücre (zmap_at(k−1) − zmap_at(k)); dizin k (0 boş)."""
    z0 = result.zmap_at(0).ravel()
    c, k, z = result.event_cell, result.event_k, result.event_z
    once = z0[c].astype(float)
    if c.size > 1:
        ayni = c[1:] == c[:-1]  # olaylar (hücre, k) sıralı → önceki olay aynı hücredeyse onun z'si
        once[1:] = np.where(ayni, z[:-1], once[1:])
    ap = np.zeros(len(result.steps) + 1)
    np.maximum.at(ap, k, once - z)
    return ap


def milling_loads(
    ops: list[Toolpath | DrillOp],
    result: SimResult,
    material: KienzleMaterial,
    K: float = 1.0,
    v_tol: float = 1e-6,
) -> list[Load]:
    """SPEC 05 z-haritası sonucundan adım başına freze yükü (len == len(result.steps))."""
    _pozitif("Freze yükü", K=K, v_tol=v_tol)
    if result.dexel is not None:
        raise CamError("Freze yükü: dexel sonucu desteklenmez (üst yüzey farkı alttaki malzemeyi görmez)")
    moves = _hareket_indeksleri(ops, result.steps)
    for op in ops:
        if isinstance(op, Toolpath) and op.tool.flutes is None:
            raise CamError(f"Freze yükü: takım '{op.tool.name}' diş sayısı (flutes) yok")
    ap_k = _derinlikler(result)
    makine = Machine()  # ivmesiz t⁰
    loads: list[Load] = []
    for s, j in zip(result.steps, moves, strict=True):
        if j is None:
            loads.append(_bos_yuk(s.k, s.op, None, "atlandi"))
            continue
        if s.type is MoveType.RAPID or s.removed <= v_tol:
            loads.append(_bos_yuk(s.k, s.op, j, "hava"))
            continue
        tp = ops[s.op]
        tool = tp.tool
        t0 = move_time(s.start, s.end, _adim_hareketi(s), Plane.XY, makine)
        Q = s.removed / t0 if t0 > 0 else 0.0
        ap = float(ap_k[s.k])
        if Q <= 0 or ap <= 0:
            loads.append(_bos_yuk(s.k, s.op, j, "hava"))
            continue
        n = tp.rpm
        fz = s.feed / (n * tool.flutes)
        ae = min(tool.D, Q * 60 / (ap * s.feed))
        hm = mean_chip_thickness(fz, ae, tool.D)
        kc = specific_force(material, hm, K)
        P = cutting_power(Q, kc)
        F_t = kienzle_force(material, ap, max_chip_thickness(fz, ae, tool.D), K)
        loads.append(
            Load(
                k=s.k,
                op=s.op,
                move=j,
                kind="kesme",
                ap=ap,
                ae=ae,
                h=hm,
                kc=kc,
                Q=Q,
                P=P,
                M=spindle_torque(P, n),
                F_t=F_t,
            )  # fmt: skip
        )
    return loads


def _kaldirilan_dis_yaricap(once: list, sonra: list) -> float:
    """Hücre başına aralık farkı (önce − sonra) parçalarının en büyük üst ucu; fark yoksa 0."""
    r = 0.0
    for a, b in zip(once, sonra, strict=True):
        for lo, hi in a:
            kalan = [(lo, hi)]
            for l2, u2 in b:
                yeni = []
                for x, y in kalan:
                    if x < l2:
                        yeni.append((x, min(y, l2)))
                    if y > u2:
                        yeni.append((max(x, u2), y))
                kalan = [(x, y) for x, y in yeni if y > x]
            for _, y in kalan:
                r = max(r, y)
    return r


def lathe_loads(
    ops: list[Toolpath],
    result: LatheSimResult,
    material: KienzleMaterial,
    K: float = 1.0,
    v_tol: float = 1e-6,
) -> list[Load]:
    """SPEC 22 radyal dexel sonucundan adım başına torna yükü."""
    from cam.sim import lathe_move_time  # SPEC 22

    _pozitif("Torna yükü", K=K, v_tol=v_tol)
    moves = _hareket_indeksleri(ops, result.steps)
    loads: list[Load] = []
    onceki = result.section_at(0)
    for s, j in zip(result.steps, moves, strict=True):
        sonraki = result.section_at(s.k)
        kesit_once, onceki = onceki, sonraki
        if j is None:
            loads.append(_bos_yuk(s.k, s.op, None, "atlandi"))
            continue
        if s.type is MoveType.RAPID or s.removed <= v_tol:
            loads.append(_bos_yuk(s.k, s.op, j, "hava"))
            continue
        tp = ops[s.op]
        tool = tp.tool
        if not isinstance(tool, LatheTool):
            raise CamError(f"Torna yükü: op {s.op} takımı torna takımı değil")
        makine = Machine()
        t0 = lathe_move_time(s.start, s.end, _adim_hareketi(s), tp, makine)
        Q = s.removed / t0 if t0 > 0 else 0.0
        r_k = _kaldirilan_dis_yaricap(kesit_once, sonraki)
        if Q <= 0 or r_k <= 0:
            loads.append(_bos_yuk(s.k, s.op, j, "hava"))
            continue
        n_e = tp.rpm if tp.css is None else min(1000 * tp.css / (2 * math.pi * r_k), tp.rpm)
        f = s.feed if tp.feed_mode is FeedMode.PER_REV else s.feed / n_e
        sk = math.sin(math.radians(tool.kappa_r))
        h = f * sk
        kc = specific_force(material, h, K)
        P = cutting_power(Q, kc)
        vc = 2 * math.pi * r_k * n_e / 1000
        ap = Q * 60 / (1000 * vc * f)
        loads.append(
            Load(
                k=s.k,
                op=s.op,
                move=j,
                kind="kesme",
                ap=ap,
                ae=None,
                h=h,
                kc=kc,
                Q=Q,
                P=P,
                M=spindle_torque(P, n_e),
                F_t=turning_force(material, ap, f, tool.kappa_r, K),
            )  # fmt: skip
        )
    return loads


def check_spindle(loads: list[Load], limits: SpindleLimits, tol: float = 1e-9) -> list[Overload]:
    """value > limit·(1 + tol) olan her (k, kind) için bir kayıt, k sırasıyla."""
    sonuc: list[Overload] = []
    for ld in sorted(loads, key=lambda x: x.k):
        if ld.kind != "kesme":
            continue
        for kind, deger, sinir in (("guc", ld.P, limits.P_max), ("tork", ld.M, limits.M_max)):
            if sinir is None:
                continue
            v = deger / limits.eta
            if v > sinir * (1 + tol):
                sonuc.append(Overload(k=ld.k, op=ld.op, move=ld.move, kind=kind, value=v, limit=sinir))
    return sonuc
