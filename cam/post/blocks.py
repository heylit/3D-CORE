"""
Dilden bağımsız G-code blokları (SPEC 30): `plan()` üretir, biçimleyici (`format`) yazar.

Bloklar yuvarlanmış değerleri taşır: yazılacak sayının ta kendisi. Modal bastırma `plan()`'dadır:
eksen veya ilerleme alanı `None` ise "değişmedi, yazma" demektir. Biçimleyici karar vermez, yalnız yazar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Start:
    """Program başı: program numarası ve iş sıfırı kodu (G54..G59)."""

    program_no: int
    wcs: str = "G54"


@dataclass(frozen=True)
class Comment:
    """Yorum satırı; metin ASCII ve büyük harf (SPEC 30, `post` yorumları)."""

    text: str


@dataclass(frozen=True)
class ToolChange:
    """Takım değişimi; `first` programın ilk takımı mı (GRBL'de ilk takımda M0 yazılmaz)."""

    tool: int
    first: bool


@dataclass(frozen=True)
class ToolLength:
    """Takım boyu telafisi: GRBL `G43.1 Z<delta>` (Fanuc/Haas'ta G43 H, `Rapid.g43_h` ile)."""

    tool: int
    delta: float


@dataclass(frozen=True)
class Spindle:
    """İş mili: `rpm` (tam sayı) ile saat yönü dönüş (M3); `None` → dur (M5)."""

    rpm: int | None


@dataclass(frozen=True)
class MachineZ:
    """Makine koordinatında Z'ye hızlı gidiş (`G53 G0 Z<z>`); sonra iş koordinatında Z bilinmez."""

    z: float


@dataclass(frozen=True)
class Rapid:
    """G0. Eksen `None` → değişmedi. `g43_h` verilirse satır `G0 G43 X Y Z H<n>` (Fanuc/Haas)."""

    x: float | None
    y: float | None
    z: float | None
    g43_h: int | None = None


@dataclass(frozen=True)
class Linear:
    """G1. Eksen veya `F` `None` → değişmedi."""

    x: float | None
    y: float | None
    z: float | None
    F: float | None


@dataclass(frozen=True)
class Arc:
    """G2 (`ccw=False`) / G3 (`ccw=True`); `i`, `j` başlangıca göre bağıl merkez, her zaman yazılır."""

    x: float | None
    y: float | None
    z: float | None
    i: float
    j: float
    ccw: bool
    F: float | None


@dataclass(frozen=True)
class Cycle:
    """Delik çevrimi satırı (G81/G82/G83/G84, G98/G99). `first` → çevrimin ilk satırı (Z R Q P F yazılır).

    `p`: G82 dipte bekleme [s] (SPEC 04b); biçimleyici dile göre ms (Fanuc) veya s (Haas) yazar."""

    kind: str
    retract: str
    x: float | None
    y: float | None
    z: float | None
    r: float | None
    q: float | None
    F: float | None
    first: bool
    p: float | None = None


@dataclass(frozen=True)
class RigidTap:
    """Rijit kılavuz modu (SPEC 04b): Fanuc `M29 S<rpm>`; Haas'ta satır yok (G84 doğrudan rijit)."""

    rpm: int


@dataclass(frozen=True)
class Dwell:
    """Bekleme [s] (açılmış G82, SPEC 04b): GRBL `G4 P<s>`."""

    seconds: float


@dataclass(frozen=True)
class CycleEnd:
    """G80."""


@dataclass(frozen=True)
class End:
    """Program sonu (dilin son satırları)."""


Block = (
    Start
    | Comment
    | ToolChange
    | ToolLength
    | Spindle
    | MachineZ
    | Rapid
    | Linear
    | Arc
    | RigidTap
    | Dwell
    | Cycle
    | CycleEnd
    | End
)
