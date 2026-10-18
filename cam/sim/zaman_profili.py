"""SPEC 72 — Tezgâh zaman profili JSON okuma / yazma (cam/post/profiles/zaman/*.json)."""

from __future__ import annotations

from os import PathLike

from cam.model import MachineProfile
from cam.sim.cevrim import TimeProfile


def load_time_profile(path: str | PathLike, machine: MachineProfile | None = None) -> TimeProfile:
    """Profil dosyasını okur. machine verilirse ad eşleşmesi denetlenir; bilinmeyen anahtar, eksik alan,
    bozuk JSON veya eşleşmeyen ad → CamError (mesajda dosya yolu)."""
    raise NotImplementedError


def save_time_profile(p: TimeProfile, path: str | PathLike) -> None:
    """Profili JSON olarak yazar (gidiş-dönüş baytı aynı)."""
    raise NotImplementedError
