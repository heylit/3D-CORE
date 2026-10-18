"""
Talaş kaldırma simülasyonu (z-haritası ve tek yönlü dexel), işleme süresi, çakma ve çarpışma
denetimi. SPEC 05. Torna simülasyonu (radyal dexel): SPEC 22. Tri-dexel çok eksenli simülasyon: SPEC 43.
"""

from cam.sim.dexel import DexelMap
from cam.sim.lathe import LatheSimResult, simulate_lathe
from cam.sim.lathe_shape import LatheShape, cutter_shape, sweep_interval, to_radial
from cam.sim.lathe_time import lathe_move_time
from cam.sim.part import mesh_zmap, part_zmap
from cam.sim.radial import RadialMap, mesh_rmap, part_rmap, profile_rmap
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
    "LatheShape",
    "LatheSimResult",
    "Machine",
    "RadialMap",
    "SimResult",
    "SimResult5",
    "SimStep",
    "TriDexel",
    "ZMap",
    "body_steps",
    "cutter_shape",
    "lathe_move_time",
    "mesh_rmap",
    "mesh_zmap",
    "move_time",
    "part_intervals",
    "part_rmap",
    "part_zmap",
    "profile_rmap",
    "ray_tool",
    "simulate",
    "simulate5",
    "simulate_lathe",
    "sweep_envelope",
    "sweep_interval",
    "sweep_top",
    "to_radial",
    "tool_height",
]
