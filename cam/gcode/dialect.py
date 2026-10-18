"""
Kontrolör dilleri (son işlemci ayarları): GRBL 1.1, Fanuc (0i/31i tipi) ve Haas (NGC, SPEC 30).

`tool_change` takım değişimi satırına T'den sonra eklenen M kelimesidir:
- 'M6': her takım değişiminde yazılır (Fanuc: `T1 M6`).
- 'M0': ilk takımda yazılmaz, sonrakilerde yazılır (GRBL: `T1`, `T2 M0`); GRBL 1.1 M6
  desteklemez, takım değişimi operatöre bırakılır (SPEC 04 varsayımı).
`tool_length_comp`: takım değişiminden sonraki ilk satıra `G43 ... H<n>` yazılsın mı (Fanuc).
GRBL 1.1'de G43 yok (yalnız G43.1); takım boyu operatörün Z sıfırlamasına kalır.
`tool_change_text`: takım değişim kelimesinin yazılışı (Haas `M06`); None → `tool_change`.
`h_digits`: G43 satırındaki H numarasının en az hane sayısı (Haas `H01`).
`header` satırlarında `{program_no}` yer tutucusu `write(..., program_no)` ile doldurulur.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    name: str
    decimals: int  # koordinat ondalık basamağı
    feed_decimals: int  # F ondalık basamağı
    line_numbers: bool  # N10, N20, ... yazılsın mı
    line_step: int  # satır numarası artışı
    header: tuple[str, ...]  # program başı
    footer: tuple[str, ...]  # program sonu
    tool_change: str  # 'M6' veya 'M0' (yukarıya bakınız)
    canned_cycles: bool  # G81/G83 yazılsın mı (yoksa kanonik açılım)
    peck_clearance: float  # G83 geri çekilme payı c [mm]
    tool_length_comp: bool = False  # takım değişiminden sonra G43 H<n> yazılsın mı
    tool_change_text: str | None = None  # 'M06' gibi yazılış; None → tool_change
    h_digits: int = 1  # H numarası en az hane


GRBL = Dialect(
    name="GRBL",
    decimals=3,
    feed_decimals=1,
    line_numbers=False,
    line_step=10,
    header=("G21 G90 G17 G94",),
    footer=("M5", "M30"),
    tool_change="M0",
    canned_cycles=False,
    peck_clearance=0.5,
)

FANUC = Dialect(
    name="Fanuc",
    decimals=3,
    feed_decimals=1,
    line_numbers=True,
    line_step=10,
    header=("%", "O{program_no:04d}", "G21 G90 G17 G94 G40 G49 G80 G54"),
    footer=("M5", "M30", "%"),
    tool_change="M6",
    canned_cycles=True,
    peck_clearance=0.5,
    tool_length_comp=True,
)

HAAS = Dialect(
    name="Haas",
    decimals=3,
    feed_decimals=1,
    line_numbers=False,
    line_step=10,
    header=("%", "O{program_no:05d}", "G21 G90 G17 G94 G40 G49 G80 G54"),
    footer=("M5", "M30", "%"),
    tool_change="M6",
    canned_cycles=True,
    peck_clearance=0.5,
    tool_length_comp=True,
    tool_change_text="M06",
    h_digits=2,
)
