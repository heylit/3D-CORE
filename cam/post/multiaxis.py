"""
5 eksen postprosesör (SPEC 51): döndürülmüş iş düzlemi, takım ucu kontrolü (TCP), ters zaman ilerlemesi.

Biçim seçimi yolun `meta.axis_mode`'u ve profilin `multiaxis` alanıyla (SPEC 51 tablosu):
- `3+2` + `swivel ≠ yok` → döndürülmüş düzlem (`CYCLE800`, `PLANE SPATIAL`, `G68.2`), yerel 3 eksen blokları;
- `3+2` + `swivel = yok` → 41 `machine_toolpath` (makine koordinatı + sabit açılar);
- `5` + `tcp ≠ yok` → TCP açık (`TRAORI`, `M128` / `FUNCTION TCPM`, `G43.4` / `G43.5`),
  açı ya da vektör biçimi;
- `5` + `tcp = yok` → 42 `linearize` + `to_machine` → eklem değerleri, `G93`.
"""

from __future__ import annotations

from cam.model import Frame, MachineProfile, Setup, ToolLibrary, Toolpath

__all__ = ["post5", "swivel_angles"]


def swivel_angles(
    frame: Frame, machine: MachineProfile, prev: tuple[float, ...] | None = None
) -> tuple[float, ...]:
    """Dile göre döndürme açıları: Sinumerik `CYCLE800` ve Heidenhain `PLANE SPATIAL` için `xyz_angles`,
    Fanuc `G68.2` için `zxz_angles` (derece)."""
    raise NotImplementedError("SPEC 51: swivel_angles")


def post5(
    ops: list[Toolpath],
    machine: MachineProfile,
    setup: Setup,
    tools: ToolLibrary,
    program_no: int = 1,
    tol_p: float = 1e-3,
    tol_a: float = 0.05,
    max_jump: float = 90.0,
) -> str:
    """Denetim + biçim seçimi + program metni; SPEC 30 `post` ile aynı başlık / yorum kuralları.
    `kinematics` yok → CamError."""
    raise NotImplementedError("SPEC 51: post5")
