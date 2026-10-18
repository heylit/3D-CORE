"""SPEC 30 testlerinin ortak yardımcıları: ölçü boylu takım, kurulum, test profili, satır işlemleri.

Testler yalnız SPEC 30 metninden, `cam/model.py` arayüzünden ve SPEC 04 altın metinlerinden yazıldı;
`cam/post/` uygulama kodu okunmadı (iskelet imzaları dışında).
"""

from __future__ import annotations

import re
from dataclasses import replace

import numpy as np

from cam.gcode import DrillOp
from cam.model import (
    AxisLimits,
    MachineProfile,
    Move,
    MoveType,
    Setup,
    Stock,
    Tool,
    ToolHolder,
    ToolKind,
    Toolpath,
    Wcs,
)

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW

UYARI = "(DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN)"


def tutucu(gauge: float) -> ToolHolder:
    """Uydurma tutucu: ölçü hattından ağza `gauge` mm, düz silindir kesit."""
    return ToolHolder("TUTUCU", gauge_length=gauge, profile=((0.0, 20.0), (gauge, 20.0)))


def takim(id: int = 1, L: float = 100.0, D: float = 6.0, name: str | None = None) -> Tool:
    """Ölçü boyu `L` olan düz freze: gauge_length = tutucu (L − 40) + taşma 40."""
    return Tool(
        id,
        name or f"freze{id}",
        ToolKind.FLAT,
        D=D,
        flute_length=20.0,
        stickout=40.0,
        holder=tutucu(L - 40.0),
    )


def boysuz(id: int = 1) -> Tool:
    """Ölçü boyu bilinmeyen takım (gauge_length None)."""
    return Tool(id, f"boysuz{id}", ToolKind.FLAT, D=6.0, flute_length=20.0)


def kurulum(origin=(0.0, 0.0, 0.0), code: str = "G54") -> Setup:
    """İş sıfırı `origin` (makine koordinatı) olan uydurma bağlama."""
    return Setup("bag", Wcs(code, tuple(origin)), Stock(-50.0, -50.0, -30.0, 50.0, 50.0, 0.0))


def profil(**kw) -> MachineProfile:
    """Eksen kursu olmayan, geniş sınırlı test profili; alanlar `kw` ile değiştirilir."""
    d = dict(
        name="TEST",
        controller="fanuc",
        rpm_min=0.0,
        rpm_max=30_000.0,
        feed_max=20_000.0,
        program_no_range=(1, 9999),
    )
    d.update(kw)
    return MachineProfile(**d)


def altin_yol(tool: Tool | None = None) -> Toolpath:
    """SPEC 04 Ek A altın yolu: 10x10 kare, üst kenar yerine yarım daire (G3, merkez (5, 10))."""
    return Toolpath(
        name="altin",
        tool=tool or takim(1),
        start=(0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -1.0), feed=100.0),
            Move(G1, (10.0, 0.0, -1.0), feed=300.0),
            Move(G1, (10.0, 10.0, -1.0), feed=300.0),
            Move(G3, (0.0, 10.0, -1.0), feed=300.0, center=(5.0, 10.0)),
            Move(G1, (0.0, 0.0, -1.0), feed=300.0),
            Move(G0, (0.0, 0.0, 5.0)),
        ],
    )


def iki_takim(t1: Tool | None = None, t2: Tool | None = None) -> list[Toolpath]:
    """op1 (T1, 10000) kesme derinliğinde biter; op2 (T2, 8000) güvenli Z'ye kendisi çıkar."""
    t1 = t1 or takim(1)
    t2 = t2 or takim(2, D=10.0)
    op1 = Toolpath(
        "op1",
        t1,
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[Move(G1, (0.0, 0.0, -1.0), feed=100.0), Move(G1, (20.0, 0.0, -1.0), feed=300.0)],
    )
    op2 = Toolpath(
        "op2",
        t2,
        (40.0, 0.0, 5.0),
        rpm=8_000.0,
        moves=[Move(G1, (40.0, 0.0, -2.0), feed=80.0), Move(G0, (40.0, 0.0, 5.0))],
    )
    return [op1, op2]


def satirlar(text: str) -> list[str]:
    """Metin '\\n' ile bitmeli; satır listesi."""
    assert text.endswith("\n")
    return text[:-1].split("\n")


_N = re.compile(r"^N\d+ ")


def n_siz(text: str) -> list[str]:
    """Satır numaraları (Fanuc `N10 `) atılmış satırlar: yorumun numaralanıp numaralanmaması serbest."""
    return [_N.sub("", ln) for ln in satirlar(text)]


def yorumsuz(lines: list[str]) -> list[str]:
    """Yalnız yorumdan oluşan satırlar atılmış liste."""
    return [ln for ln in lines if not re.fullmatch(r"\([^()]*\)", ln)]


def sinirla(op: Toolpath | DrillOp, m: MachineProfile) -> Toolpath | DrillOp:
    """Op devrini profilin [rpm_min, rpm_max] aralığına çeker (testlerde kullanılan iş verisi)."""
    return replace(op, rpm=float(min(max(op.rpm, m.rpm_min), m.rpm_max)))


def kapsam(ops: list[Toolpath | DrillOp], z_ek: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Op'ların iş koordinatında sınır kutusu (yay çeyrek noktaları dahil); `z_ek` güvenli Z gibi ek Z."""
    kutular = [(op if isinstance(op, Toolpath) else op.to_toolpath()).bbox() for op in ops]
    lo = np.min([k[0] for k in kutular], axis=0)
    hi = np.max([k[1] for k in kutular], axis=0)
    if z_ek is not None:
        lo[2], hi[2] = min(lo[2], z_ek), max(hi[2], z_ek)
    return lo, hi


def ortala(m: MachineProfile, ops, L: float, z_ek: float | None = None) -> Setup:
    """Op'ları profilin kurslarının ortasına yerleştiren iş sıfırı (makine koordinatı).

    x_m = x + ox, z_ölçü = z + oz + L. Kursa sığmıyorsa test verisi yanlıştır (assert)."""
    lo, hi = kapsam(ops, z_ek)
    o = [0.0, 0.0, 0.0]
    for i, lim in enumerate((m.x, m.y, m.z)):
        if lim is None:
            continue
        assert hi[i] - lo[i] < lim.max - lim.min, (i, lo[i], hi[i], lim)
        o[i] = (lim.min + lim.max) / 2 - (lo[i] + hi[i]) / 2 - (L if i == 2 else 0.0)
    return kurulum(tuple(o))


def ile_takim(op: Toolpath | DrillOp, tool: Tool) -> Toolpath | DrillOp:
    return replace(op, tool=tool)


__all__ = [
    "G0",
    "G1",
    "G2",
    "G3",
    "UYARI",
    "AxisLimits",
    "altin_yol",
    "boysuz",
    "ile_takim",
    "iki_takim",
    "kapsam",
    "kurulum",
    "n_siz",
    "ortala",
    "profil",
    "satirlar",
    "sinirla",
    "takim",
    "tutucu",
    "yorumsuz",
]
