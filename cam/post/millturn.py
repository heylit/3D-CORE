"""
SPEC 49 — Torna-freze postu: C ekseni aç / kapat ve indeks, canlı takım devri, polar ve silindirik
dönüşüm blokları.

| İşlev | Sinumerik 840D sl | Fanuc / MAPPS |
|---|---|---|
| C ekseni | SPOS / CAxis.m_on, m_off | CAxis.m_on (M45), m_off (M46) |
| C indeks | SPOS=DC(C) | G0 C |
| Canlı takım | SETMS(2) … M2=3 S2=n, SETMS | M13 S n |
| Polar | TRANSMIT … TRAFOOF | G12.1 … G13.1 (X çap) |
| Silindirik | TRACYL(2·r_ref) … TRAFOOF | G7.1 C r_ref … G7.1 C0 |
"""

from __future__ import annotations

from cam.model import MachineProfile, Setup, Toolpath


def post_mt(
    ops: list[Toolpath],
    machine: MachineProfile,
    setup: Setup | None = None,
    program_no: int = 1,
    spindle: str = "M3",
    tool_change: tuple[float, float] | None = None,
) -> str:
    """Torna + canlı takım programı; machine.kind != "millturn" → CamError."""
    raise NotImplementedError


def read_mt(text: str, machine: MachineProfile) -> list[Toolpath]:
    """post_mt çıktısını parça çerçevesinde yollara geri okur (gidiş-dönüş, yazılan ondalığa göre)."""
    raise NotImplementedError
