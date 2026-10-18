"""
Delik delme çevrimleri (G81, G83) ve kanonik açılımları.

Tanımlar: başlangıç yüksekliği z0, R düzlemi r, dip z (z < r ≤ z0), gagalama derinliği q,
geri çekilme payı c (Dialect.peck_clearance). Dönüş düzlemi: G98 -> z0, G99 -> r.
Kanonik açılım (her delik):
    G81: G0 (x, y, z_akım) -> G0 (x, y, r) -> G1 (x, y, z) F -> G0 (x, y, z_dön)
    G83: G0 (x, y, z_akım) -> G0 (x, y, r) -> k = 1..n:
             (k > 1 ise G0 (x, y, d_{k-1} + c)) -> G1 (x, y, d_k) F -> G0 (x, y, r)
         sonra G0 (x, y, z_dön);   d_k = max(r - k·q, z),  n = ⌈(r - z)/q⌉
Boyu sıfır olan hareketler atlanır. Yazıcı (GRBL) ve okuyucu (her iki dil) aynı açılımı kullanır.
Kaynak: Smid, CNC Programming Handbook, Bölüm 21–22; LinuxCNC G81/G83.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from cam.gcode.dialect import GRBL, Dialect
from cam.model import CamError, Move, MoveType, Tool, Toolpath

KINDS = ("G81", "G83")
RETRACTS = ("G98", "G99")


def peck_count(r: float, z: float, q: float) -> int:
    """Gagalama sayısı n = ⌈(r − z)/q⌉: d_n = z olan en küçük k.

    Bölmedeki kayan nokta gürültüsü n'yi bir artırmasın diye n, d_k tanımıyla doğrulanır:
    r − n·q ≤ z ve (n > 1 ise) r − (n−1)·q > z.
    """
    n = max(1, math.ceil((r - z) / q))
    while n > 1 and r - (n - 1) * q <= z:
        n -= 1
    while r - n * q > z:
        n += 1
    return n


def peck_depths(r: float, z: float, q: float) -> list[float]:
    """Gagalama derinlikleri d_k = max(r − k·q, z), k = 1..n; son derinlik tam z."""
    n = peck_count(r, z, q)
    return [max(r - k * q, z) for k in range(1, n + 1)]


def hole_moves(
    kind: str,
    p: tuple[float, float, float],
    x: float,
    y: float,
    z: float,
    r: float,
    z_ret: float,
    feed: float,
    q: float | None = None,
    c: float = 0.0,
) -> list[Move]:
    """Tek deliğin kanonik açılımı. p: takımın o anki konumu (z_akım = p[2]).

    Boyu sıfır olan hareketler (bir önceki noktayla aynı) listeye girmez.
    """
    seq: list[tuple[MoveType, tuple[float, float, float]]] = [
        (MoveType.RAPID, (x, y, p[2])),
        (MoveType.RAPID, (x, y, r)),
    ]
    if kind in ("G81", "G82"):  # G82: dipte bekleme yolda temsil edilmez (SPEC 04b)
        seq.append((MoveType.LINEAR, (x, y, z)))
    elif kind == "G84":  # rijit kılavuz: çıkış da F ile (SPEC 04b)
        seq.append((MoveType.LINEAR, (x, y, z)))
        seq.append((MoveType.LINEAR, (x, y, r)))
    elif kind == "G83":
        if q is None or q <= 0:
            raise CamError(f"G83: gagalama derinliği q pozitif olmalı (q={q})")
        if not 0 <= c < q:
            raise CamError(f"G83: geri çekilme payı 0 ≤ c < q olmalı (c={c}, q={q})")
        d = peck_depths(r, z, q)
        for k, d_k in enumerate(d):
            if k > 0:
                seq.append((MoveType.RAPID, (x, y, d[k - 1] + c)))
            seq.append((MoveType.LINEAR, (x, y, d_k)))
            seq.append((MoveType.RAPID, (x, y, r)))
    else:
        raise CamError(f"Bilinmeyen delik çevrimi: {kind}")
    seq.append((MoveType.RAPID, (x, y, z_ret)))

    moves: list[Move] = []
    prev = tuple(float(v) for v in p)
    for t, pt in seq:
        pt = tuple(float(v) for v in pt)
        if pt == prev:
            continue  # sıfır boylu hareket yazılmaz
        moves.append(Move(t, pt, feed if t is not MoveType.RAPID else None))
        prev = pt
    return moves


@dataclass
class DrillOp:
    """Delik delme işlemi: aynı Z/R/Q ile bir dizi delik (G81 veya G83)."""

    name: str
    tool: Tool
    rpm: float
    start: tuple[float, float, float]
    holes: list[tuple[float, float]] = field(default_factory=list)
    z: float = 0.0
    r: float = 0.0
    feed: float = 0.0
    kind: str = "G81"
    q: float | None = None
    retract: str = "G98"

    def __post_init__(self) -> None:
        self.start = tuple(float(v) for v in self.start)
        self.holes = [tuple(float(v) for v in h) for h in self.holes]

    def validate(self) -> None:
        """Tutarsızlıkta CamError: rpm, feed, delik listesi, z < r ≤ z0, çevrim tipi, q, dönüş."""
        if not self.tool.center_cutting:
            raise CamError(f"Delik op '{self.name}': takım '{self.tool.name}' merkezden kesmiyor (Ek C3)")
        if self.rpm <= 0:
            raise CamError(f"Delik op '{self.name}': devir pozitif olmalı (rpm={self.rpm})")
        if self.feed <= 0:
            raise CamError(f"Delik op '{self.name}': ilerleme pozitif olmalı (feed={self.feed})")
        if not self.holes:
            raise CamError(f"Delik op '{self.name}': delik yok")
        if self.z >= self.r:
            raise CamError(f"Delik op '{self.name}': z < r olmalı (z={self.z}, r={self.r})")
        if self.r > self.start[2]:
            raise CamError(f"Delik op '{self.name}': R düzlemi başlangıç Z'sinin üstünde (r={self.r})")
        if self.kind not in KINDS:
            raise CamError(f"Delik op '{self.name}': çevrim G81 veya G83 olmalı ({self.kind})")
        if self.kind == "G83" and (self.q is None or self.q <= 0):
            raise CamError(f"Delik op '{self.name}': G83'te q pozitif olmalı (q={self.q})")
        if self.retract not in RETRACTS:
            raise CamError(f"Delik op '{self.name}': dönüş G98 veya G99 olmalı ({self.retract})")

    @property
    def z_ret(self) -> float:
        """Çevrim sonu dönüş düzlemi: G98 -> z0 = start[2], G99 -> r."""
        return self.start[2] if self.retract == "G98" else self.r

    def to_toolpath(self, dialect: Dialect = GRBL) -> Toolpath:
        """Kanonik açılım: G0/G1 hareketlerinden oluşan Toolpath (c = dialect.peck_clearance)."""
        self.validate()
        c = dialect.peck_clearance
        if self.kind == "G83" and not c < self.q:
            raise CamError(f"Delik op '{self.name}': G83'te c < q olmalı (c={c}, q={self.q})")
        p = self.start
        moves: list[Move] = []
        for x, y in self.holes:
            moves += hole_moves(self.kind, p, x, y, self.z, self.r, self.z_ret, self.feed, self.q, c)
            p = (x, y, self.z_ret)
        return Toolpath(self.name, self.tool, self.start, moves, self.rpm)
