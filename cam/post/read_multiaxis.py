"""
5 eksen program okuyucusu (SPEC 51): program metni → Toolpath listesi (WCS'de uç konumu + `Move.axis`).

- Döndürülmüş düzlem → `frame` açılardan geri kurulur (`from_xyz` / `from_zxz`), yerel bloklar aynen.
- TCP açık açı biçimi → `forward`'ın döner kısmı; vektör biçimi → doğrudan.
- TCP kapalı → `forward(kin, q, L, wcs)`; `L` takım kütüphanesinden, yoksa CamError.
Desteklenmeyen sözcükler (`TRAORI(2)`, `ORIAXES` / `ORIVECT` dışı yönelim modları, `CYCLE832`,
Heidenhain `FN`,
Fanuc `G43.4` ile vektör karışımı) → CamError, satır numarasıyla.
"""

from __future__ import annotations

from cam.model import MachineProfile, ToolLibrary, Toolpath

__all__ = ["read_program5"]


def read_program5(text: str, machine: MachineProfile, tools: ToolLibrary) -> list[Toolpath]:
    raise NotImplementedError("SPEC 51: read_program5")
