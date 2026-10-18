"""
Tezgâh profili dosyaları (SPEC 30). Veri sınıfları `cam/model.py`'dedir (`MachineProfile`, `AxisLimits`).

- `load_machine(path)`: UTF-8 JSON → `MachineProfile.from_dict` (dosya yok / bozuk JSON / geçersiz → CamError,
  mesajda dosya yolu).
- `save_machine(m, path)`: `json.dumps(m.to_dict(), ensure_ascii=False, indent=2) + "\\n"`.
- `builtin_machines()`: `cam/post/profiles/*.json`, ada göre.
"""

from __future__ import annotations

from os import PathLike

from cam.model import AxisLimits, MachineProfile

__all__ = ["AxisLimits", "MachineProfile", "builtin_machines", "load_machine", "save_machine"]


def load_machine(path: str | PathLike) -> MachineProfile:
    raise NotImplementedError("SPEC 30: load_machine")


def save_machine(m: MachineProfile, path: str | PathLike) -> None:
    raise NotImplementedError("SPEC 30: save_machine")


def builtin_machines() -> dict[str, MachineProfile]:
    raise NotImplementedError("SPEC 30: builtin_machines")
