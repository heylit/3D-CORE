"""
Torna tezgâh profili denetimi ve postprosesörü (SPEC 40 Ek E2, SPEC 30 Ek A).

- Kurs: makine koordinatı `X_m = 2·(x + o_x)` (profilde X **çap**, yolda `x` **yarıçap**), `Z_m = z + o_z`;
  her uç (`G0` dahil) ve yayların `(x, z)` düzleminde süpürdüğü eksen yönü noktaları; takım değiştirme
  noktası `tool_change = (x_tc, z_tc)` aynı dönüşümle. Kurs varken `setup` zorunlu.
- Devir: sabit devirde ve `G96`'nın `G50` sınırında `S = round(rpm)`, `rpm_min ≤ S ≤ rpm_max`.
- İlerleme (mm/dev): her kesme hareketinde `feed · S ≤ feed_max` (mm/dk; `G96`'da güvenli taraf).
- Taret: `tool_slots` varsa `1 ≤ T ≤ tool_slots`.
- Yol türü: `kind = "lathe"` profile freze yolu (`plane = XY` veya `feed_mode = PER_MIN`) → CamError.
- `post_lathe` = `check_lathe` + `write_lathe` + iki yorum satırı (`FANUC_TORNA` başlığından sonra).
"""

from __future__ import annotations

from cam.model import MachineProfile, Setup, Toolpath

__all__ = ["check_lathe", "post_lathe"]


def check_lathe(
    machine: MachineProfile,
    ops: list[Toolpath],
    setup: Setup | None,
    tool_change: tuple[float, float],
    program_no: int = 1,
) -> None:
    """Torna profili, program numarası ve her op için taret, devir, `feed·S` ve çap kursu denetimi."""
    raise NotImplementedError("SPEC 40 Ek E2: check_lathe")


def post_lathe(
    ops: list[Toolpath],
    machine: MachineProfile,
    setup: Setup | None,
    spindle: str,
    tool_change: tuple[float, float],
    program_no: int = 1,
) -> str:
    """Denetim + `write_lathe(…, dialect_for(machine))` + `(POST <AD> <DIL>)` ve doğrulanmamış uyarı."""
    raise NotImplementedError("SPEC 40 Ek E2: post_lathe")
