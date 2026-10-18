"""
Talaş kaldırma simülasyonu (z-haritası ve tek yönlü dexel), işleme süresi, çakma ve çarpışma
denetimi. SPEC 05; tri-dexel çok eksenli simülasyon SPEC 43.
"""

from cam.sim.dexel import DexelMap
from cam.sim.part import mesh_zmap, part_zmap
from cam.sim.raymesh import part_intervals
from cam.sim.simulate import Collision, SimResult, SimStep, simulate
from cam.sim.simulate5 import SimResult5, simulate5
from cam.sim.sweep import body_steps, sweep_envelope, sweep_top, tool_height
from cam.sim.timing import Machine, move_time
from cam.sim.tridexel import TriDexel, ray_tool
from cam.sim.zmap import ZMap

__all__ = [
    "Collision",
    "DexelMap",
    "Machine",
    "SimResult",
    "SimResult5",
    "SimStep",
    "TriDexel",
    "ZMap",
    "body_steps",
    "mesh_zmap",
    "move_time",
    "part_intervals",
    "part_zmap",
    "ray_tool",
    "simulate",
    "simulate5",
    "sweep_envelope",
    "sweep_top",
    "tool_height",
]
