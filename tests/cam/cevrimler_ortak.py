"""SPEC 04b testlerinin ortak yardımcıları: punta / havşa / kılavuz takımları, Örnek A ve B op'ları,
elle kurulmuş (uydurma) delik kayıtları.

Testler yalnız SPEC 04b metninden, A0 arayüz ekinden (`cam/model.py`: `ToolKind.SPOT/CHAMFER/TAP`,
`Tool.tip_angle`, `tip_d`, `pitch`, `lead`) ve `geometry/part.py` `Hole` kaydından yazıldı;
`cam/cevrimler.py` uygulaması okunmadı (iskelet imzaları dışında).

Takımlar fonksiyonla kurulur: A0 birleşmeden önce modül toplanabilsin. Bağımlılık eksikken testler
`NotImplementedError` ile düşer (`a0_gerekli`, `spec30_gerekli`): yerelde "uygulanmamış", CI'da
(`--uygulanmamis-hata`) kırmızı. Eksik arayüz böylece sessizce atlanmaz, ama commit kapısını da kilitlemez.
"""

from __future__ import annotations

from dataclasses import fields

import numpy as np

from cam.cevrimler import DwellDrillOp, TapOp
from cam.model import Move, MoveType, Tool, ToolKind, Toolpath
from geometry.part import Hole

G0, G1 = MoveType.RAPID, MoveType.LINEAR
ASAGI = (0.0, 0.0, -1.0)
START = (0.0, 0.0, 5.0)
HOLES_A = [(10.0, 10.0), (30.0, 10.0)]  # Örnek A
HOLES3 = [(10.0, 10.0), (30.0, 10.0), (30.0, 25.0)]  # 3 delikli G98 / G99 sürümleri


# ---------------------------------------------------------------- bağımlılık denetimi


def a0_gerekli() -> None:
    """A0 eki (`cam/model.py`: SPOT / CHAMFER / TAP, tip_angle, tip_d, pitch, lead) yoksa uygulanmamış."""
    alanlar = {f.name for f in fields(Tool)}
    if (
        not all(hasattr(ToolKind, k) for k in ("SPOT", "CHAMFER", "TAP"))
        or not {
            "tip_angle",
            "tip_d",
            "pitch",
            "lead",
        }
        <= alanlar
    ):
        raise NotImplementedError("SPEC 04b: A0 arayüz eki (cam/model.py) henüz birleşmedi")


def spec30_gerekli() -> None:
    """SPEC 30 `cam/post/` blok ekleri (SPEC 04b ekler 1–8: `RigidTap`, `Dwell`) yoksa uygulanmamış."""
    try:
        import cam.post.blocks as blocks
    except ImportError as e:
        raise NotImplementedError("SPEC 04b: SPEC 30 cam/post/ henüz yok") from e
    if not all(hasattr(blocks, n) for n in ("RigidTap", "Dwell")):
        raise NotImplementedError("SPEC 04b: SPEC 30 blok ekleri (RigidTap, Dwell) henüz yok")


# ---------------------------------------------------------------- takımlar


def punta(sigma: float = 90.0, D: float = 10.0, id: int = 3, name: str = "punta10") -> Tool:
    """Örnek A takımı: SPOT, D = 10, kesici boy 20, uç açısı σ."""
    a0_gerekli()
    return Tool(id, name, ToolKind.SPOT, D=D, flute_length=20.0, tip_angle=sigma)


def havsa(
    alpha: float = 90.0, tip_d: float = 2.0, D: float = 16.0, id: int = 4, name: str = "havsa16"
) -> Tool:
    """CHAMFER, D = 16, kesici boy 20; koni yüksekliği (D − tip_d)/2 · cot(α/2) ≤ 20."""
    a0_gerekli()
    return Tool(id, name, ToolKind.CHAMFER, D=D, flute_length=20.0, tip_angle=alpha, tip_d=tip_d)


def kilavuz(D: float = 8.0, pitch: float = 1.25, lead: float = 3.0, id: int = 5, name: str = "M8") -> Tool:
    """Örnek B takımı: TAP M8, hatve 1.25, giriş pahı 3 diş, kesici boy 25."""
    a0_gerekli()
    return Tool(id, name, ToolKind.TAP, D=D, flute_length=25.0, pitch=pitch, lead=lead)


def matkap(id: int = 2) -> Tool:
    return Tool(id, "matkap6.8", ToolKind.DRILL, D=6.8, flute_length=40.0)


def freze(id: int = 1) -> Tool:
    return Tool(id, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0)


# ---------------------------------------------------------------- Örnek A ve B


def ornek_a(retract: str = "G98", holes=None, dwell: float = 0.5) -> DwellDrillOp:
    """Örnek A: punta, rpm 2000, F200, dwell 0.5 s, start (0, 0, 5), z = −3, r = 2."""
    return DwellDrillOp(
        name="punta",
        tool=punta(),
        rpm=2000.0,
        start=START,
        holes=list(HOLES_A if holes is None else holes),
        z=-3.0,
        r=2.0,
        feed=200.0,
        dwell=dwell,
        retract=retract,
    )


def ornek_b(retract: str = "G98", holes=None) -> TapOp:
    """Örnek B: M8 kılavuz, rpm 500 (F = 625), start (0, 0, 5), delik (10, 10), z = −15.75, r = 2."""
    return TapOp(
        name="kilavuz",
        tool=kilavuz(),
        rpm=500.0,
        start=START,
        holes=list([(10.0, 10.0)] if holes is None else holes),
        z=-15.75,
        r=2.0,
        retract=retract,
    )


# ---------------------------------------------------------------- delik kayıtları (uydurma)


def duz(
    x: float, y: float, z_top: float = 0.0, d: float = 6.8, depth: float = 20.0, through: bool = True
) -> Hole:
    return Hole(origin=(x, y, z_top), axis=ASAGI, d=d, depth=depth, through=through)


def havsali(
    x: float,
    y: float,
    z_top: float = 0.0,
    d: float = 6.6,
    csk_d: float = 12.0,
    csk_angle: float = 90.0,
    depth: float = 20.0,
    through: bool = True,
) -> Hole:
    return Hole(
        origin=(x, y, z_top),
        axis=ASAGI,
        d=d,
        depth=depth,
        through=through,
        csk_d=csk_d,
        csk_angle=csk_angle,
    )


def disli(
    x: float,
    y: float,
    z_top: float = 0.0,
    thread: str = "M8",
    d_n: float = 8.0,
    P: float = 1.25,
    depth: float = 16.0,
    thread_depth: float = 12.0,
    through: bool = False,
) -> Hole:
    """Kılavuz matkabı d = d_n − P (SPEC 23)."""
    return Hole(
        origin=(x, y, z_top),
        axis=ASAGI,
        d=d_n - P,
        depth=depth,
        through=through,
        thread=thread,
        thread_d=d_n,
        pitch=P,
        thread_depth=thread_depth,
    )


def egik(x: float, y: float, z_top: float = 0.0, d: float = 6.8) -> Hole:
    """Düşey olmayan delik: eksen düşeyden 30° yatık."""
    a = np.radians(30.0)
    return Hole(
        origin=(x, y, z_top), axis=(0.0, float(np.sin(a)), -float(np.cos(a))), d=d, depth=10.0, through=False
    )


# ---------------------------------------------------------------- karşılaştırma


def hareketler(tp: Toolpath) -> list[tuple[MoveType, tuple[float, float, float]]]:
    return [(m.type, tuple(float(v) for v in m.end)) for m in tp.moves]


def assert_moves(tp: Toolpath, expected, feed: float, tol: float = 1e-12) -> None:
    """Hareket tipleri ve uçlar beklenen listeyle aynı; her G1'de F = feed (tam)."""
    assert [m.type for m in tp.moves] == [t for t, _ in expected]
    for i, (m, (_, e)) in enumerate(zip(tp.moves, expected, strict=True)):
        assert np.max(np.abs(np.subtract(m.end, e))) <= tol, (i, m.end, e)
        if m.type is G1:
            assert m.feed == feed, (i, m.feed)


def with_retract(tp: Toolpath, safe_z: float) -> Toolpath:
    """SPEC 04 Ek B: yazıcı program sonunda güvenli Z'nin (verilmezse op başlarının en yükseği) altındaysa
    `G0 Z<safe_z>` ekler; okununca bu, yolun son hareketidir."""
    x, y, z = tp.points()[-1]
    if round(z, 3) >= round(safe_z, 3):
        return tp
    return Toolpath(tp.name, tp.tool, tp.start, [*tp.moves, Move(G0, (x, y, safe_z))], tp.rpm)


__all__ = [
    "ASAGI",
    "G0",
    "G1",
    "HOLES3",
    "HOLES_A",
    "START",
    "a0_gerekli",
    "assert_moves",
    "disli",
    "duz",
    "egik",
    "freze",
    "havsa",
    "havsali",
    "hareketler",
    "kilavuz",
    "matkap",
    "ornek_a",
    "ornek_b",
    "punta",
    "spec30_gerekli",
    "with_retract",
]
