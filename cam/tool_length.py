"""
Takım boyu: Fanuc G43 H ofset tablosu, GRBL G38.2 ölçüm programı ve G43.1 ofsetleri. SPEC 14.

L_n = Tool.gauge_length (iş mili ölçü hattından uca). GRBL'de Z sıfırı referans takımla alınır;
diğer takımlar için ΔL_n = L_n − L_ref (ön ayar) veya ΔL_n = z_n − z_ref (takım boyu ölçerde
G38.2 tetiklenme Z'leri, makine koordinatı). Uzun takımda ΔL pozitif.
Kaynak: GRBL 1.1 wiki "G-code commands" (G38.2, G43.1, G49, G53); LinuxCNC G38, G43.1.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cam.gcode.modal import fmt
from cam.model import CamError, ToolLibrary, _sonlu


@dataclass
class ToolSetter:
    """Takım boyu ölçer, makine koordinatında [mm]: ölçerin XY'si, probun başladığı Z, güvenli Z,
    en fazla prob boyu, hızlı / yavaş prob beslemesi [mm/dk] ve geri çekilme."""

    x: float
    y: float
    z_start: float
    z_safe: float
    travel: float
    feed_fast: float = 200.0
    feed_slow: float = 20.0
    backoff: float = 2.0

    def __post_init__(self) -> None:
        nerede = "Takım boyu ölçer"
        _sonlu(nerede, **vars(self))
        for ad in ("travel", "feed_fast", "feed_slow", "backoff"):
            if getattr(self, ad) <= 0:
                raise CamError(f"{nerede}: {ad} pozitif olmalı ({getattr(self, ad)})")
        if self.z_safe < self.z_start:
            raise CamError(f"{nerede}: güvenli Z ({self.z_safe}) prob başlangıcından ({self.z_start}) alçak")
        if 1.5 * self.backoff >= self.travel:
            raise CamError(f"{nerede}: 1.5·backoff ({1.5 * self.backoff}) < travel ({self.travel}) olmalı")


def _ref(ids, ref_id: int) -> None:
    if ref_id not in ids:
        raise CamError(f"Takım boyu: referans takım T{ref_id} listede yok ({list(ids)})")


def _boy(lib: ToolLibrary, n: int) -> float:
    t = lib.get(n)
    L = getattr(t, "gauge_length", None)
    if L is None:
        raise CamError(f"Takım boyu: T{n} '{t.name}' için ölçü boyu yok (tutucu veya taşma eksik)")
    return float(L)


def length_offsets(lib: ToolLibrary, ids: Sequence[int], ref_id: int) -> dict[int, float]:
    """Ön ayardan ΔL_n = L_n − L_ref."""
    _ref(ids, ref_id)
    L = {n: _boy(lib, n) for n in ids}
    return {n: L[n] - L[ref_id] for n in ids}


def offsets_from_probe(readings: dict[int, float], ref_id: int) -> dict[int, float]:
    """Prob tetiklenme Z'lerinden ΔL_n = z_n − z_ref."""
    _ref(readings, ref_id)
    _sonlu("Prob ölçümü", **{f"T{n}": z for n, z in readings.items()})
    return {n: float(z - readings[ref_id]) for n, z in readings.items()}


def verify_offsets(measured: dict[int, float], expected: dict[int, float], tol: float = 0.05) -> None:
    """Ölçülen ve beklenen ofset farkı tol'u aşan takım varsa CamError."""
    _sonlu("Ofset denetimi", tol=tol)
    if tol < 0:
        raise CamError(f"Ofset denetimi: tol negatif olamaz ({tol})")
    if measured.keys() != expected.keys():
        raise CamError(f"Ofset denetimi: takımlar uyuşmuyor ({sorted(measured)} ≠ {sorted(expected)})")
    hatali = [
        f"T{n}: ölçülen {measured[n]:g}, beklenen {expected[n]:g}"
        for n in sorted(measured)
        if not abs(measured[n] - expected[n]) <= tol
    ]
    if hatali:
        raise CamError(f"Takım boyu tol = {tol} mm dışında (yanlış takım veya taşma?): " + "; ".join(hatali))


def fanuc_offset_table(lib: ToolLibrary, ids: Sequence[int]) -> dict[int, float]:
    """Fanuc H kayıtları: {n: L_n}."""
    return {n: _boy(lib, n) for n in ids}


def probe_program(ids: Sequence[int], setter: ToolSetter, decimals: int = 3) -> str:
    """GRBL takım boyu ölçüm programı (SPEC 14 Ek A)."""
    if not ids:
        raise CamError("Ölçüm programı: takım listesi boş")
    if len(set(ids)) != len(ids):
        raise CamError(f"Ölçüm programı: yinelenen takım ({list(ids)})")

    def c(v: float) -> str:
        return fmt(v, decimals)

    s = setter
    lines = ["G21 G90 G17 G94", "M5", "G49"]
    for k, n in enumerate(ids):
        lines.append(f"T{n}" if k == 0 else f"T{n} M0")
        lines += [
            f"G53 G0 Z{c(s.z_safe)}",
            f"G53 G0 X{c(s.x)} Y{c(s.y)}",
            f"G53 G0 Z{c(s.z_start)}",
            "G91",
            f"G38.2 Z{c(-s.travel)} F{fmt(s.feed_fast, 1)}",
            f"G0 Z{c(s.backoff)}",
            f"G38.2 Z{c(-1.5 * s.backoff)} F{fmt(s.feed_slow, 1)}",
            "G90",
            f"G53 G0 Z{c(s.z_safe)}",
        ]
    lines.append("M30")
    return "\n".join(lines) + "\n"
