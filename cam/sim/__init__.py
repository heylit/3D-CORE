"""
Talaş kaldırma simülasyonu (z-haritası ve tek yönlü dexel), işleme süresi, çakma ve çarpışma
denetimi. SPEC 05.
"""

from cam.sim.dexel import DexelMap
from cam.sim.part import mesh_zmap, part_zmap
from cam.sim.simulate import Collision, SimResult, SimStep, simulate
from cam.sim.sweep import body_steps, sweep_envelope, sweep_top, tool_height
from cam.sim.timing import Machine, move_time
from cam.sim.zmap import ZMap

__all__ = [
    "Collision",
    "DexelMap",
    "Machine",
    "SimResult",
    "SimStep",
    "ZMap",
    "body_steps",
    "mesh_zmap",
    "move_time",
    "part_zmap",
    "simulate",
    "sweep_envelope",
    "sweep_top",
    "tool_height",
]
