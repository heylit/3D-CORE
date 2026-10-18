"""
Punta, havşa (pah) ve kılavuz çevrimleri (SPEC 04b): G82 ve G84.

Delik kaydından (`geometry.part.Hole`, SPEC 23) op üretir; derinlik, ilerleme ve devir analitik formüllerden:
    punta   h_s = (d_s / 2) · cot(σ / 2)
    havşa   h_c = (D_h − d_t) / 2 · cot(α / 2)
    kılavuz h_t = t_d + lead · P,   F = S · P  (S = round(rpm); F yuvarlanmadan yazılabilmeli)
Kanonik açılım (SPEC 04 tanımlarıyla):
    G82: G0 (x, y, z_akım) -> G0 (x, y, r) -> G1 (x, y, z) F -> [bekle w] -> G0 (x, y, z_dön)
    G84: G0 (x, y, z_akım) -> G0 (x, y, r) -> G1 (x, y, z) F -> G1 (x, y, r) F -> G0 (x, y, z_dön)
Kaynak: Smid, CNC Programming Handbook, Bölüm 22; Fanuc 0i-MF Operator's Manual (B-64604EN), "Rigid tapping";
ISO 8830 (kılavuz giriş pahı); Machinery's Handbook, "Tapping", "Countersinks".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cam.gcode import GRBL, Dialect, hole_moves
from cam.model import CamError, Move, MoveType, Tool, Toolpath

if TYPE_CHECKING:
    from geometry.part import Hole

R_CLEAR = 2.0  # mm, R düzleminin delik üst yüzünden yüksekliği (varsayılan)
DWELL = 0.2  # s, punta ve havşada dipte bekleme (varsayılan)
TOL = 1e-9  # mm / derece: eşitlik toleransı (açı, çap, hatve, düşey eksen)
RETRACTS = ("G98", "G99")


def _sonlu(nerede: str, **degerler) -> None:
    """Her değer sonlu olmalı; nan / inf → CamError. Sessiz hata yok."""
    for ad, v in degerler.items():
        if not all(math.isfinite(float(x)) for x in (v if isinstance(v, tuple | list) else (v,))):
            raise CamError(f"{nerede}: {ad} sonlu olmalı ({ad}={v})")


def _tur(nerede: str, tool: Tool, *turler: str) -> None:
    """Takım türü (ToolKind üye adı: "SPOT", "CHAMFER", "TAP", "DRILL") beklenenlerden biri olmalı."""
    if tool.kind.name not in turler:
        raise CamError(f"{nerede}: takım '{tool.name}' türü {tool.kind.name}; beklenen {', '.join(turler)}")


# ---------------------------------------------------------------- hesap


def spot_depth(tool: Tool, d_s: float) -> float:
    """Punta derinliği h_s = (d_s / 2) · cot(σ / 2); σ = tool.tip_angle. Koşul 0 < d_s ≤ D."""
    _tur("Punta", tool, "SPOT")
    _sonlu("Punta", d_s=d_s)
    if not 0 < d_s <= tool.D:
        raise CamError(f"Punta: iz çapı 0 < d_s ≤ D olmalı (d_s={d_s}, D={tool.D})")
    return d_s / 2 / math.tan(math.radians(tool.tip_angle) / 2)


def chamfer_depth(tool: Tool, csk_d: float, csk_angle: float, d: float) -> float:
    """Havşa derinliği h_c = (csk_d − tip_d) / 2 · cot(α / 2); takım açısı havşa açısına eşit olmalı."""
    _tur("Havşa", tool, "CHAMFER")
    _sonlu("Havşa", csk_d=csk_d, csk_angle=csk_angle, d=d)
    if abs(tool.tip_angle - csk_angle) > TOL:
        raise CamError(f"Havşa: takım açısı {tool.tip_angle}° havşa açısına {csk_angle}° eşit değil")
    if csk_d > tool.D:
        raise CamError(f"Havşa: ağız çapı takımdan büyük (D_h={csk_d} > D={tool.D})")
    if csk_d <= d:
        raise CamError(f"Havşa: ağız çapı delikten büyük olmalı (D_h={csk_d}, d={d})")
    if tool.tip_d >= d:
        raise CamError(f"Havşa: takımın düz ucu delikten küçük olmalı (d_t={tool.tip_d}, d={d})")
    return (csk_d - tool.tip_d) / 2 / math.tan(math.radians(csk_angle) / 2)


def tap_depth(tool: Tool, thread_depth: float) -> float:
    """Kılavuz ucu derinliği h_t = t_d + lead · pitch."""
    _tur("Kılavuz", tool, "TAP")
    _sonlu("Kılavuz", thread_depth=thread_depth)
    if thread_depth <= 0:
        raise CamError(f"Kılavuz: diş derinliği pozitif olmalı (t_d={thread_depth})")
    return thread_depth + tool.lead * tool.pitch


def _yazilir(S: int, P: float, fd: int) -> bool:
    """S · P, fd basamakla tam yazılabiliyor mu: |S·P·10^fd − round| ≤ 1e-9."""
    v = S * P * 10**fd
    return abs(v - round(v)) <= TOL


def tap_feed(rpm: float, pitch: float, feed_decimals: int = 1) -> float:
    """Kılavuz ilerlemesi F = S · P (S = round(rpm)); feed_decimals basamakla tam yazılamıyorsa CamError."""
    _sonlu("Kılavuz ilerlemesi", rpm=rpm, pitch=pitch)
    if pitch <= 0:
        raise CamError(f"Kılavuz ilerlemesi: hatve pozitif olmalı (P={pitch})")
    S = round(rpm)
    if S < 1:
        raise CamError(f"Kılavuz ilerlemesi: devir en az 1 olmalı (S={S})")
    if not _yazilir(S, pitch, feed_decimals):
        raise CamError(
            f"Kılavuz ilerlemesi: F = S·P = {S}·{pitch} = {S * pitch} {feed_decimals} basamakla tam "
            f"yazılamaz (yuvarlama hatveyi bozar); tap_rpm() ile devir seçin"
        )
    return S * pitch


def tap_rpm(n: float, pitch: float, feed_decimals: int = 1) -> int:
    """n'yi aşmayan ve S · P · 10^fd tam sayı olan en büyük S (S ≥ 1 yoksa CamError)."""
    _sonlu("Kılavuz devri", n=n, pitch=pitch)
    if pitch <= 0:
        raise CamError(f"Kılavuz devri: hatve pozitif olmalı (P={pitch})")
    for S in range(math.floor(n), 0, -1):
        if _yazilir(S, pitch, feed_decimals):
            return S
    raise CamError(f"Kılavuz devri: {n}'yi aşmayan ve F = S·{pitch} tam yazılan devir yok")


# ---------------------------------------------------------------- op'lar


def _ortak_denetim(op: DwellDrillOp | TapOp, nerede: str) -> None:
    """DrillOp kuralları: sonlu değerler, rpm > 0, delik var, z < r ≤ start_z, dönüş G98/G99."""
    _sonlu(nerede, rpm=op.rpm, start=op.start, z=op.z, r=op.r)
    for h in op.holes:
        _sonlu(nerede, delik=h)
    if op.rpm <= 0:
        raise CamError(f"{nerede}: devir pozitif olmalı (rpm={op.rpm})")
    if not op.holes:
        raise CamError(f"{nerede}: delik yok")
    if op.z >= op.r:
        raise CamError(f"{nerede}: z < r olmalı (z={op.z}, r={op.r})")
    if op.r > op.start[2]:
        raise CamError(f"{nerede}: R düzlemi başlangıç Z'sinin üstünde (r={op.r}, z0={op.start[2]})")
    if op.retract not in RETRACTS:
        raise CamError(f"{nerede}: dönüş G98 veya G99 olmalı ({op.retract})")


def _z_ret(op: DwellDrillOp | TapOp) -> float:
    """Çevrim sonu dönüş düzlemi: G98 → z0 = start[2], G99 → r."""
    return op.start[2] if op.retract == "G98" else op.r


@dataclass
class DwellDrillOp:
    """G82: dipte beklemeli delme (punta, havşa). dwell saniye, 1 ms'nin katı."""

    name: str
    tool: Tool
    rpm: float
    start: tuple[float, float, float]
    holes: list[tuple[float, float]]
    z: float
    r: float
    feed: float
    dwell: float
    retract: str = "G98"
    kind: str = "G82"

    def __post_init__(self) -> None:
        self.start = tuple(float(v) for v in self.start)
        self.holes = [tuple(float(v) for v in h) for h in self.holes]

    def validate(self) -> None:
        nerede = f"G82 op '{self.name}'"
        _tur(nerede, self.tool, "SPOT", "CHAMFER", "DRILL")
        _ortak_denetim(self, nerede)
        _sonlu(nerede, feed=self.feed, dwell=self.dwell)
        if self.feed <= 0:
            raise CamError(f"{nerede}: ilerleme pozitif olmalı (feed={self.feed})")
        if self.dwell <= 0:
            raise CamError(f"{nerede}: bekleme pozitif olmalı (dwell={self.dwell})")
        ms = 1000 * self.dwell
        if abs(ms - round(ms)) > TOL:
            raise CamError(f"{nerede}: bekleme 1 ms'nin katı olmalı (dwell={self.dwell} s)")

    def to_toolpath(self, dialect: Dialect = GRBL) -> Toolpath:
        """Kanonik açılım (G81'inkiyle aynı hareketler; bekleme yolda temsil edilmez)."""
        self.validate()
        z_ret = _z_ret(self)
        p = self.start
        moves: list[Move] = []
        for x, y in self.holes:
            moves += hole_moves("G81", p, x, y, self.z, self.r, z_ret, self.feed)
            p = (x, y, z_ret)
        return Toolpath(self.name, self.tool, self.start, moves, self.rpm)


@dataclass
class TapOp:
    """G84: rijit kılavuz. İlerleme takımın hatvesinden türetilir: F = S · P."""

    name: str
    tool: Tool
    rpm: float
    start: tuple[float, float, float]
    holes: list[tuple[float, float]]
    z: float
    r: float
    retract: str = "G98"
    feed_decimals: int = 1
    kind: str = "G84"

    def __post_init__(self) -> None:
        self.start = tuple(float(v) for v in self.start)
        self.holes = [tuple(float(v) for v in h) for h in self.holes]

    @property
    def feed(self) -> float:
        """F = S · P [mm/dk]; tam yazılamıyorsa CamError."""
        return tap_feed(self.rpm, self.tool.pitch, self.feed_decimals)

    def validate(self) -> None:
        nerede = f"G84 op '{self.name}'"
        _tur(nerede, self.tool, "TAP")
        _ortak_denetim(self, nerede)
        self.feed  # noqa: B018 — yazılamayan F → CamError

    def to_toolpath(self, dialect: Dialect = GRBL) -> Toolpath:
        """G84 kanonik açılımı: aşağı G1, yukarı G1 (aynı F), sonra G0 dönüş; sıfır boylu hareket yok."""
        self.validate()
        F = self.feed
        z_ret = _z_ret(self)
        p = self.start
        moves: list[Move] = []
        for x, y in self.holes:
            seq = [
                (MoveType.RAPID, (x, y, p[2])),
                (MoveType.RAPID, (x, y, self.r)),
                (MoveType.LINEAR, (x, y, self.z)),
                (MoveType.LINEAR, (x, y, self.r)),
                (MoveType.RAPID, (x, y, z_ret)),
            ]
            for t, pt in seq:
                if pt == p:
                    continue  # sıfır boylu hareket yazılmaz
                moves.append(Move(t, pt, F if t is MoveType.LINEAR else None))
                p = pt
        return Toolpath(self.name, self.tool, self.start, moves, self.rpm)


# ---------------------------------------------------------------- delik kaydından


def _dusey(holes: list[Hole], nerede: str) -> None:
    """Liste boş olmamalı; her delik düşey (axis = (0, 0, −1)). Mesajda 1 tabanlı delik sırası."""
    if not holes:
        raise CamError(f"{nerede}: delik listesi boş")
    for i, h in enumerate(holes, start=1):
        if max(abs(a - b) for a, b in zip(h.axis, (0.0, 0.0, -1.0), strict=True)) > TOL:
            raise CamError(f"{nerede}: delik {i} düşey değil (eksen {tuple(h.axis)}); eğimli delik SPEC 41")


def _grupla(holes: list[Hole], derinlik: list[float], r_clear: float) -> list[tuple[float, float, list]]:
    """(z_top, h) ile gruplar, giriş sırası korunur: [(z, r, [(x, y), ...]), ...]."""
    gruplar: dict[tuple[float, float], list] = {}
    for hole, h in zip(holes, derinlik, strict=True):
        z_top = float(hole.origin[2])
        gruplar.setdefault((round(z_top, 9), round(h, 9)), [z_top, h, []])[2].append(
            (float(hole.origin[0]), float(hole.origin[1]))
        )
    return [(z_top - h, z_top + r_clear, xy) for z_top, h, xy in gruplar.values()]


def spot_ops(
    holes: list[Hole],
    tool: Tool,
    rpm: float,
    feed: float,
    start: tuple[float, float, float],
    d_s: float | None = None,
    dwell: float = DWELL,
    name: str = "punta",
    r_clear: float = R_CLEAR,
    retract: str = "G98",
) -> list[DwellDrillOp]:
    """Punta op'ları; d_s=None → her delik için Hole.d. (z_top, h) ile gruplanır, sıra korunur."""
    _dusey(holes, "Punta")
    h = [spot_depth(tool, hole.d if d_s is None else d_s) for hole in holes]
    ops = [
        DwellDrillOp(f"{name}-{k}", tool, rpm, start, xy, z, r, feed, dwell, retract)
        for k, (z, r, xy) in enumerate(_grupla(holes, h, r_clear), start=1)
    ]
    for op in ops:
        op.validate()
    return ops


def chamfer_ops(
    holes: list[Hole],
    tool: Tool,
    rpm: float,
    feed: float,
    start: tuple[float, float, float],
    dwell: float = DWELL,
    name: str = "havsa",
    r_clear: float = R_CLEAR,
    retract: str = "G98",
) -> list[DwellDrillOp]:
    """Havşa op'ları; havşasız delik, kör delikte h_c > depth → CamError."""
    _dusey(holes, "Havşa")
    h = []
    for i, hole in enumerate(holes, start=1):
        if hole.csk_d <= 0:
            raise CamError(f"Havşa: delik {i} havşasız (csk_d = 0)")
        h_c = chamfer_depth(tool, hole.csk_d, hole.csk_angle, hole.d)
        if not hole.through and h_c > hole.depth + TOL:
            raise CamError(f"Havşa: delik {i} kör ve havşa derinliği delikten büyük ({h_c} > {hole.depth})")
        h.append(h_c)
    ops = [
        DwellDrillOp(f"{name}-{k}", tool, rpm, start, xy, z, r, feed, dwell, retract)
        for k, (z, r, xy) in enumerate(_grupla(holes, h, r_clear), start=1)
    ]
    for op in ops:
        op.validate()
    return ops


def tap_ops(
    holes: list[Hole],
    tool: Tool,
    rpm: float,
    start: tuple[float, float, float],
    feed_decimals: int = 1,
    name: str = "kilavuz",
    r_clear: float = R_CLEAR,
    retract: str = "G98",
) -> list[TapOp]:
    """Kılavuz op'ları; dişsiz delik, çap / hatve uyuşmazlığı, kör delikte h_t > depth → CamError."""
    _dusey(holes, "Kılavuz")
    _tur("Kılavuz", tool, "TAP")
    h = []
    for i, hole in enumerate(holes, start=1):
        if not hole.thread:
            raise CamError(f"Kılavuz: delik {i} dişsiz")
        if abs(tool.D - hole.thread_d) > TOL or abs(tool.pitch - hole.pitch) > TOL:
            raise CamError(
                f"Kılavuz: delik {i} {hole.thread} (d_n={hole.thread_d}, P={hole.pitch}) takımla "
                f"'{tool.name}' (D={tool.D}, P={tool.pitch}) uyuşmuyor"
            )
        h_t = tap_depth(tool, hole.thread_depth)
        if not hole.through and h_t > hole.depth + TOL:
            raise CamError(
                f"Kılavuz: delik {i} kör, kılavuz dibe vurur (h_t={h_t} > depth={hole.depth}); "
                f"daha kısa giriş pahlı kılavuz veya daha derin delik"
            )
        if h_t > tool.flute_length + TOL:
            raise CamError(f"Kılavuz: delik {i} için h_t={h_t} kesici boydan uzun ({tool.flute_length})")
        h.append(h_t)
    ops = [
        TapOp(f"{name}-{k}", tool, rpm, start, xy, z, r, retract, feed_decimals)
        for k, (z, r, xy) in enumerate(_grupla(holes, h, r_clear), start=1)
    ]
    for op in ops:
        op.validate()
    return ops
