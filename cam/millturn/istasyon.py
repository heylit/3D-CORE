"""
SPEC 49 — Taret istasyonu ve canlı takım denetimleri (işlemler, simülasyon ve post ortak kullanır).
"""

from __future__ import annotations

import math

from cam.millturn.polar import polar_check
from cam.model import CamError, LatheTool, MachineProfile, Tool, Toolpath, TurretStation

RADYAL_EKSEN = (1.0, 0.0, 0.0)  # radyal istasyonda takım ekseni (uçtan iş miline), C döndürmesinden önce
_EKSEN_TOL = 1e-9


def millturn(machine: MachineProfile) -> MachineProfile:
    """Profil torna-freze değilse CamError; geçerliliği de denetler."""
    if not isinstance(machine, MachineProfile):
        raise CamError(f"Tezgâh profili MachineProfile olmalı ({type(machine).__name__})")
    machine.validate()
    if machine.kind != "millturn":
        raise CamError(f"Tezgâh profili '{machine.name}': torna-freze değil (kind = {machine.kind!r})")
    return machine


def station(machine: MachineProfile, no: int | None) -> tuple[TurretStation, float | None]:
    """İstasyon no → (istasyon, taretin canlı devir sınırı); bilinmeyen no → CamError."""
    if no is None:
        raise CamError(f"Tezgâh profili '{machine.name}': canlı takım işleminde istasyon no zorunlu")
    for t in machine.turrets:
        for st in t.stations:
            if st.no == no:
                return st, t.live_rpm_max
    raise CamError(f"Tezgâh profili '{machine.name}': {no} numaralı taret istasyonu yok")


def live_tool(tool) -> Tool:
    """Canlı takım işleminde freze takımı zorunlu (LatheTool → CamError)."""
    if isinstance(tool, LatheTool) or not isinstance(tool, Tool):
        raise CamError(f"Canlı takım işlemi freze takımı ister ({type(tool).__name__})")
    return tool


def live_station(
    machine: MachineProfile | None, no: int | None, direction: str, rpm: float | None = None
) -> None:
    """machine verilirse: istasyon var, canlı ve yönü `direction`; rpm canlı devir sınırını aşmaz."""
    if machine is None:
        return
    millturn(machine)
    st, rpm_max = station(machine, no)
    if not st.live:
        raise CamError(f"İstasyon {no}: canlı takım istasyonu değil (sabit torna istasyonu)")
    if st.direction != direction:
        raise CamError(f"İstasyon {no}: yön {st.direction!r}, işlem {direction!r} istasyon ister")
    if rpm is not None and rpm_max is not None and rpm > rpm_max:
        raise CamError(f"İstasyon {no}: canlı takım devri {rpm} > {rpm_max} dev/dk")


def check_ops(ops, machine: MachineProfile) -> None:
    """Program denetimi (simülasyon ve post): profil torna-freze; her yol geçerli; freze yolu canlı
    istasyonda, yönü yolun takım ekseni / koordinat moduyla uyumlu; canlı devir sınırı;
    Y kursu (kartezyen yollar)."""
    millturn(machine)
    if not ops:
        raise CamError("Torna-freze programı boş")
    for i, tp in enumerate(ops):
        if not isinstance(tp, Toolpath):
            raise CamError(f"İşlem {i}: Toolpath bekleniyor ({type(tp).__name__})")
        tp.validate()
        if isinstance(tp.tool, LatheTool):
            if tp.station is not None:
                station(machine, tp.station)
            if tp.rpm > machine.rpm_max:
                raise CamError(f"Yol '{tp.name}': iş mili devri {tp.rpm} > {machine.rpm_max} dev/dk")
            continue
        yon = _direction(tp)
        live_station(machine, tp.station, yon, tp.rpm)
        if tp.coord == "polar":
            polar_check(tp, machine.c_axis)
        elif tp.coord == "silindirik" and not machine.c_axis.continuous:
            raise CamError(f"Yol '{tp.name}': sürekli olmayan C ekseninde silindirik enterpolasyon yok")
        if tp.coord == "kartezyen" and machine.y is not None:
            for p in tp.points():
                if not machine.y.min - 1e-9 <= p[1] <= machine.y.max + 1e-9:
                    raise CamError(
                        f"Yol '{tp.name}': Y = {p[1]} kurs dışında ({machine.y.min}, {machine.y.max})"
                    )


def _direction(tp: Toolpath) -> str:
    """Freze yolunun istediği istasyon yönü: polar → eksenel, silindirik → radyal; kartezyende takım ekseni
    (+X radyal, yok / +Z eksenel)."""
    if tp.coord == "polar":
        return "eksenel"
    if tp.coord == "silindirik":
        return "radyal"
    if tp.frame is not None:
        raise CamError(f"Yol '{tp.name}': torna-frezede frame'li yol yok")
    eksenler = {m.axis for m in tp.moves}
    if eksenler <= {None, (0.0, 0.0, 1.0)}:
        return "eksenel"
    if all(a is not None and math.dist(a, RADYAL_EKSEN) <= _EKSEN_TOL for a in eksenler):
        return "radyal"
    raise CamError(f"Yol '{tp.name}': takım ekseni radyal (+X) ya da eksenel (+Z) olmalı")
