"""
Tezgâh sınır denetimi (SPEC 30): program tezgâha gitmeden kurs, devir, ilerleme, takım ve program
numarası. Hiçbir değer kırpılmaz; ilk ihlalde CamError (op adı, hareket sırası, değer, sınır).

Kurs: uç makinede p + origin; ölçü hattı Z'si z + origin_z + L (L = Tool.gauge_length).
Yaylarda süpürülen eksen yönü noktaları (0, π/2, π, 3π/2) da denetlenir. DrillOp kanonik açılımıyla.
"""

from __future__ import annotations

from cam.gcode.cycles import DrillOp
from cam.model import MachineProfile, Setup, Toolpath


def check_machine(
    machine: MachineProfile,
    ops: list[Toolpath | DrillOp],
    setup: Setup | None = None,
    program_no: int = 1,
) -> None:
    raise NotImplementedError("SPEC 30: check_machine")


def machine_extents(
    machine: MachineProfile, ops: list[Toolpath | DrillOp], setup: Setup
) -> dict[str, tuple[float, float]]:
    """Op'ların makine koordinatında kapladığı aralık: anahtarlar 'x', 'y', 'z_ölçü'."""
    raise NotImplementedError("SPEC 30: machine_extents")
