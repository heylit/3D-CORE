"""
G-code son işlemci (GRBL, Fanuc), delik çevrimleri (G81/G83) ve G-code okuyucu. SPEC 04.
Torna (Fanuc torna) yazıcı ve okuyucu: `cam.gcode.lathe`, SPEC 21.

Yazıcı ve okuyucu aynı modal durum makinesini (`ModalState`) kullanır.
"""

from cam.gcode.cycles import DrillOp, hole_moves, peck_count, peck_depths
from cam.gcode.dialect import FANUC, GRBL, Dialect
from cam.gcode.lathe import FANUC_TORNA, LatheDialect, read_lathe, spindle_rpm, write_lathe
from cam.gcode.modal import ModalState, fmt, snap
from cam.gcode.reader import read
from cam.gcode.writer import write

__all__ = [
    "Dialect",
    "DrillOp",
    "FANUC",
    "FANUC_TORNA",
    "GRBL",
    "LatheDialect",
    "ModalState",
    "fmt",
    "hole_moves",
    "peck_count",
    "peck_depths",
    "read",
    "read_lathe",
    "snap",
    "spindle_rpm",
    "write",
    "write_lathe",
]
