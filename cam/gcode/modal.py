"""
G-code modal durum makinesi ve sayı biçimi.

G0/G1/G2/G3, G90/G91, G17, G21, F ve S bir kez yazılır, değişene kadar geçerlidir.
Yazıcı ve okuyucu aynı `ModalState`'i kullanır:
- yazıcı: kelime durumdaki değerle aynıysa yazılmaz,
- okuyucu: satırda olmayan kelime durumdan doldurulur.

Durumdaki sayılar her zaman "makinenin bildiği" değerlerdir: yazıcıda yuvarlanmış (metne yazılan),
okuyucuda metinden okunan değer. Böylece iki taraf aynı sayıları görür.
Kaynak: Smid, CNC Programming Handbook, Bölüm 4–6; LinuxCNC "Modal Groups".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cam.model import CamError

CYCLES = ("G81", "G83")


def fmt(v: float, decimals: int) -> str:
    """Sayıyı `decimals` ondalıkla, her zaman ondalık noktalı yazar: 10 -> '10.', -2.5 -> '-2.5'.

    Sondaki sıfırlar atılır, nokta kalır. '-0.' yazılmaz, '0.' yazılır.
    """
    v = float(v)
    if not math.isfinite(v):
        raise CamError(f"Sonlu olmayan sayı yazılamaz: {v}")
    s = f"{v:.{decimals}f}"
    s = s.rstrip("0") if "." in s else s + "."
    if s == "-0.":
        s = "0."
    return s


def snap(v: float, decimals: int) -> float:
    """Yazılan metnin okununca verdiği değer: float(fmt(v, d))."""
    return float(fmt(v, decimals))


@dataclass
class ModalState:
    """Yazıcı ve okuyucunun ortak modal durumu.

    motion   : 'G0' | 'G1' | 'G2' | 'G3' | 'G81' | 'G83' | None (bilinmiyor / G80 sonrası)
    distance : 'G90' mutlak | 'G91' artımsal
    plane    : 'G17' (XY; tek desteklenen düzlem)
    units    : 'G21' (mm; tek desteklenen birim)
    feed     : F [mm/dk] veya None
    rpm      : S [dev/dk] veya None
    tool     : T numarası veya None
    pos      : (x, y, z) [mm] veya None (konum bilinmiyor)
    retract  : 'G98' (z0'a dön) | 'G99' (R düzlemine dön)
    cycle_z, cycle_r, cycle_q : çevrim dip Z'si, R düzlemi, gagalama derinliği (modal)
    cycle_z0 : çevrimin başladığı Z (G98 dönüş düzlemi; çevrim boyunca sabit)
    """

    motion: str | None = None
    distance: str = "G90"
    plane: str = "G17"
    units: str = "G21"
    feed: float | None = None
    rpm: float | None = None
    tool: int | None = None
    pos: tuple[float, float, float] | None = None
    retract: str = "G98"
    cycle_z: float | None = None
    cycle_r: float | None = None
    cycle_q: float | None = None
    cycle_z0: float | None = None

    @property
    def in_cycle(self) -> bool:
        """Delik çevrimi (G81/G83) etkin mi?"""
        return self.motion in CYCLES

    def end_cycle(self) -> None:
        """G80: çevrim iptal; hareket tipi bilinmiyor sayılır."""
        self.motion = None
        self.cycle_z0 = None
