"""
G-code son işlemci (GRBL, Fanuc), delik çevrimleri (G81/G83) ve G-code okuyucu. SPEC 04.

Yazıcı ve okuyucu aynı modal durum makinesini (`ModalState`) kullanır.
"""

from cam.gcode.cycles import DrillOp, hole_moves, peck_count, peck_depths
from cam.gcode.dialect import FANUC, GRBL, Dialect
from cam.gcode.modal import ModalState, fmt, snap
from cam.gcode.reader import read
from cam.gcode.writer import write

__all__ = [
    "Dialect",
    "DrillOp",
    "FANUC",
    "GRBL",
    "ModalState",
    "fmt",
    "hole_moves",
    "peck_count",
    "peck_depths",
    "read",
    "snap",
    "write",
]
