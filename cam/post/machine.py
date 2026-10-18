"""
Tezgâh profili dosyaları (SPEC 30). Veri sınıfları `cam/model.py`'dedir (`MachineProfile`, `AxisLimits`).

- `load_machine(path)`: UTF-8 JSON → `MachineProfile.from_dict` (dosya yok / bozuk JSON / geçersiz → CamError,
  mesajda dosya yolu).
- `save_machine(m, path)`: `json.dumps(m.to_dict(), ensure_ascii=False, indent=2) + "\\n"`.
- `builtin_machines()`: `cam/post/profiles/*.json`, ada göre.
"""

from __future__ import annotations

import json
from os import PathLike
from pathlib import Path

from cam.model import AxisLimits, CamError, MachineProfile

PROFIL_DIZINI = Path(__file__).parent / "profiles"

__all__ = ["AxisLimits", "MachineProfile", "builtin_machines", "load_machine", "save_machine"]


def load_machine(path: str | PathLike) -> MachineProfile:
    p = Path(path)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CamError(f"{p}: tezgâh profili dosyası yok") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CamError(f"{p}: tezgâh profili okunamadı ({e})") from None
    if not isinstance(d, dict):
        raise CamError(f"{p}: tezgâh profili JSON nesnesi olmalı ({type(d).__name__} geldi)")
    try:
        return MachineProfile.from_dict(d)
    except (CamError, TypeError, ValueError) as e:
        raise CamError(f"{p}: {e}") from None


def save_machine(m: MachineProfile, path: str | PathLike) -> None:
    m.validate()
    text = json.dumps(m.to_dict(), ensure_ascii=False, indent=2) + "\n"
    Path(path).write_bytes(text.encode("utf-8"))


def builtin_machines() -> dict[str, MachineProfile]:
    ms = [load_machine(f) for f in sorted(PROFIL_DIZINI.glob("*.json"))]
    return {m.name: m for m in ms}
