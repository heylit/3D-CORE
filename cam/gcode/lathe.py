"""
Torna G-code: Fanuc torna (G-code sistemi A) son işlemcisi ve okuyucusu. SPEC 21.

- Modelde x yarıçaptır; G-code'da X çaptır (X = 2·x). Yay merkezi I yarıçap, başlangıca göre bağıl.
- İş mili: G97 S<n> (sabit devir) veya G50 S<n_max> + G96 S<Vc> (sabit kesme hızı); yön (M3/M4) zorunlu girdi.
- İlerleme G99 (mm/dev). G90, G91, G92, G94, G95, G98 asla yazılmaz (sistem A'da çevrim veya mm/dk).
- Taret sadece zorunlu takım değiştirme noktasında döner; hızlı hareketler eksen eksen
  (Fanuc G0 doğrusal olmayabilir).
- Diş: THREAD takımlı yolda Z'ye paralel G1 → G32 Z F<hatve>.
Kaynak: Fanuc Series 0i-TF Operatör El Kitabı (B-64604EN); Smid, CNC Programming Handbook, torna bölümleri.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import LatheTool, Toolpath


@dataclass(frozen=True)
class LatheDialect:
    name: str
    decimals: int  # X (çap) ve Z ondalık basamağı
    feed_decimals: int  # F (mm/dev) ondalık basamağı
    lead_decimals: int  # G32 F (hatve) ondalık basamağı
    line_numbers: bool  # N10, N20, ... yazılsın mı
    line_step: int  # satır numarası artışı
    header: tuple[str, ...]  # program başı ('{program_no}' yer tutucusu)
    footer: tuple[str, ...]  # program sonu


FANUC_TORNA = LatheDialect(
    name="Fanuc torna",
    decimals=3,
    feed_decimals=3,
    lead_decimals=4,
    line_numbers=True,
    line_step=10,
    header=("%", "O{program_no:04d}", "G21 G18 G40 G99 G54"),
    footer=("M5", "M30", "%"),
)


def spindle_rpm(css: float, x: float, rpm_max: float) -> float:
    """G96'da kontrolörün devri: n = min(1000·Vc / (π·D), n_max), D = 2·|x|; x = 0 → n_max."""
    raise NotImplementedError


def write_lathe(
    ops: list[Toolpath],
    spindle: str,
    tool_change: tuple[float, float],
    dialect: LatheDialect = FANUC_TORNA,
    program_no: int = 1,
) -> str:
    """Torna yollarını Fanuc torna programına çevirir.

    `spindle`: 'M3' veya 'M4' (zorunlu). `tool_change`: (x_tc, z_tc), yarıçap, iş koordinatında.
    """
    raise NotImplementedError


def read_lathe(
    text: str,
    tools: dict[int, LatheTool],
    spindle: str | None = None,
    arc_tol: float = 0.005,
) -> list[Toolpath]:
    """Fanuc torna programını Toolpath listesine okur (plane ZX, feed_mode PER_REV, x yarıçap)."""
    raise NotImplementedError
