"""SPEC 72 — Tezgâh zaman profili JSON okuma / yazma (cam/post/profiles/zaman/*.json).

Anahtarlar dataclass alan adlarıyla aynıdır (TimeProfile, iç içe "dynamics": Dynamics). Örnek profillerdeki
"aciklama" (ör. "UYDURMA, ölçülmedi") okunur ama profile girmez; başka bilinmeyen anahtar → CamError.
"""

from __future__ import annotations

import json
from dataclasses import MISSING, fields
from os import PathLike
from pathlib import Path

from cam.model import CamError, MachineProfile
from cam.sim.cevrim import TimeProfile
from cam.sim.sure import Dynamics

NOTE_KEY = "aciklama"
TUPLE_KEYS = ("v_max", "a_max", "j_max", "rot_v", "rot_a")


def _fields(cls) -> tuple[set[str], set[str]]:
    """(tüm alanlar, zorunlu alanlar)."""
    allf = {f.name for f in fields(cls)}
    req = {f.name for f in fields(cls) if f.default is MISSING and f.default_factory is MISSING}
    return allf, req


def _check_keys(d, cls, yer: str, extra: set[str] = frozenset()) -> None:
    if not isinstance(d, dict):
        raise CamError(f"{yer}: nesne (sözlük) bekleniyor ({type(d).__name__})")
    allf, req = _fields(cls)
    bilinmeyen = set(d) - allf - set(extra)
    if bilinmeyen:
        raise CamError(f"{yer}: bilinmeyen anahtar {sorted(bilinmeyen)}")
    eksik = req - set(d)
    if eksik:
        raise CamError(f"{yer}: eksik alan {sorted(eksik)}")


def _dynamics(d) -> Dynamics:
    _check_keys(d, Dynamics, "dynamics")
    kw = dict(d)
    for key in TUPLE_KEYS:
        if key in kw and kw[key] is not None:
            if not isinstance(kw[key], list):
                raise CamError(f"dynamics.{key}: liste bekleniyor ({kw[key]!r})")
            kw[key] = tuple(kw[key])
    return Dynamics(**kw)


def load_time_profile(path: str | PathLike, machine: MachineProfile | None = None) -> TimeProfile:
    """Profil dosyasını okur. machine verilirse ad eşleşmesi denetlenir; bilinmeyen anahtar, eksik alan,
    bozuk JSON veya eşleşmeyen ad → CamError (mesajda dosya yolu)."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _check_keys(data, TimeProfile, "profil", {NOTE_KEY})
        kw = {k: v for k, v in data.items() if k != NOTE_KEY}
        kw["dynamics"] = _dynamics(kw["dynamics"])
        p = TimeProfile(**kw)
    except CamError as e:
        raise CamError(f"{path}: {e}") from None
    except (OSError, ValueError, TypeError) as e:
        raise CamError(f"{path}: zaman profili okunamadı ({e})") from None
    if machine is not None and machine.name != p.machine:
        raise CamError(f"{path}: profil '{p.machine}' tezgâhı için, verilen tezgâh '{machine.name}'")
    return p


def _to_dict(p: TimeProfile) -> dict:
    d = {f.name: getattr(p, f.name) for f in fields(TimeProfile)}
    dyn = {f.name: getattr(p.dynamics, f.name) for f in fields(Dynamics)}
    for key in TUPLE_KEYS:
        if dyn[key] is not None:
            dyn[key] = list(dyn[key])
    d["dynamics"] = dyn
    return d


def save_time_profile(p: TimeProfile, path: str | PathLike) -> None:
    """Profili JSON olarak yazar (gidiş-dönüş baytı aynı)."""
    if not isinstance(p, TimeProfile):
        raise CamError(f"save_time_profile: TimeProfile bekleniyor ({type(p).__name__})")
    text = json.dumps(_to_dict(p), ensure_ascii=False, indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8", newline="\n")
