"""SPEC 32 testleri için ortak uydurma veri ve programlar (cam.kuvvet koduna bakılmadan, SPEC'ten).

Bu modül test değildir (adı test_ ile başlamaz). Beklenen değerler SPEC 32 "Teori" bölümündeki kapalı
formlardan yazıldı:
- Kienzle: kc(h) = K·kc11·h^(−mc), Fc = K·kc11·b·h^(1−mc).
- Freze: φe = arccos(1 − 2ae/D), hm = fz·(2ae/D)/φe, hex = fz·sin(min(φe, π/2)),
  P = Q·kc(hm)/10⁶ [kW], M = 60000·P/(2π·n) [N·m].
- Torna: h = f·sin κr, Q = π(R² − r²)·v_f (v_f [mm/s] eksenel ilerleme hızı).

Uydurma malzeme kc11 = 1500 N/mm², mc = 0.25 (SPEC 32 sayısal örneği). Uydurma geometri.
"""

from __future__ import annotations

import math

import pytest

from cam.kuvvet import KienzleMaterial
from cam.model import CylinderStock, FeedMode, LatheTool, Move, MoveType, Plane, Stock, Tool, Toolpath

KC11 = 1500.0
MC = 0.25


def malzeme() -> KienzleMaterial:
    """Uydurma malzeme (iskelette kurucu NotImplementedError verir; modül düzeyinde kurulmaz)."""
    return KienzleMaterial("deneme", KC11, MC)


# Freze örneği (SPEC 32 Teori tablosu): D = 10, z = 3, fz = 0.1, n = 3000 → F = 900, ap = 3
D = 10.0
Z = 3
FZ = 0.1
N = 3000.0
F = FZ * Z * N  # 900 mm/dk
AP = 3.0
CELL = 0.5
STOCK = Stock(0.0, -20.0, -20.0, 100.0, 20.0, 0.0)

# ae → (hm, Q [mm³/s], P [kW], M [N·m], hex)  — SPEC 32 Teori tablosu
TABLO = {
    10.0: (0.0636620, 450.0, 1.343797, 4.277439, 0.1),
    5.0: (0.0636620, 225.0, 0.671899, 2.138720, 0.1),
    1.0: (0.0310800, 45.0, 0.160762, 0.511722, 0.06),
}

# Izgara toleransı (SPEC 32 K4): Δ = 0.5 mm'de rel ≤ 2Δ/D
REL_IZGARA = 2 * CELL / D

X0, X1, X2 = -30.0, 20.0, 60.0  # stok dışı başlangıç, giriş sonu, kararlı kanal sonu (L = 40)


def parmak(flutes: int | None = Z, id: int = 1) -> Tool:
    return Tool(id=id, name="parmak", kind="duz", D=D, flute_length=20.0, flutes=flutes)


def _g0(x, y, z) -> Move:
    return Move(MoveType.RAPID, (x, y, z))


def _g1(x, y, z, f=F) -> Move:
    return Move(MoveType.LINEAR, (x, y, z), feed=f)


def paso(y: float) -> list[Move]:
    """Stok dışında inip y'de x boyunca paso: G0 iniş, G1 giriş (X0 → X1), G1 kararlı (X1 → X2), G0 çıkış.
    Kararlı hareket listede 2. indekste (0'dan)."""
    return [_g0(X0, y, -AP), _g1(X1, y, -AP), _g1(X2, y, -AP), _g0(X2, y, 5.0)]


def kanal_programi(tool: Tool | None = None) -> tuple[Toolpath, dict[str, int]]:
    """K4: y = 0'da kanal (ae = D) + stok üstünde G1 (hava). Hareket indeksleri sözlükte."""
    moves = [_g0(X0, 0.0, -AP), _g1(X1, 0.0, -AP), _g1(X2, 0.0, -AP), _g0(X2, 0.0, 5.0), _g1(80.0, 0.0, 5.0)]
    tp = Toolpath("kanal", tool or parmak(), (X0, 0.0, 10.0), moves, rpm=N)
    return tp, {"inis": 0, "giris": 1, "kanal": 2, "cikis": 3, "hava_g1": 4}


def yan_programi() -> tuple[Toolpath, dict[str, int]]:
    """K5: kanal (y = 0, kesilen |y| ≤ 5), sonra +y yanında ae = 5 (merkez y = 5, kesilen 5..10) ve
    −y yanında ae = 1 (merkez y = −1, kesilen −6..−5) pasoları. Kanal x = 80'e uzar: yan pasolar (X2'de biter)
    kanalın uç yarım dairesinin köşelerine girmez, kararlı paso tam olarak ae·L·ap kaldırır."""
    moves = [_g0(X0, 0.0, -AP), _g1(X1, 0.0, -AP), _g1(X2, 0.0, -AP)]
    moves += [_g1(80.0, 0.0, -AP), _g0(80.0, 0.0, 5.0)]
    i5 = len(moves)
    moves += [_g0(X0, 5.0, 5.0)] + paso(5.0)
    i1 = len(moves)
    moves += [_g0(X0, -1.0, 5.0)] + paso(-1.0)
    tp = Toolpath("yan", parmak(), (X0, 0.0, 10.0), moves, rpm=N)
    return tp, {"kanal": 2, "ae5": i5 + 3, "ae1": i1 + 3, "ae5_giris": i5 + 2, "ae1_giris": i1 + 2}


def yuk(loads, op: int, move: int):
    """(op, move) için tek yük kaydı."""
    bul = [ld for ld in loads if ld.op == op and ld.move == move]
    assert len(bul) == 1, f"(op={op}, move={move}) için {len(bul)} yük kaydı"
    return bul[0]


def degisim(plan, op: int, move: int):
    bul = [c for c in plan.changes if c.op == op and c.move == move]
    assert len(bul) == 1, f"(op={op}, move={move}) için {len(bul)} FeedChange"
    return bul[0]


def asagi_yuvarlanmis(F_new: float, F_ust: float, res: float) -> None:
    """F_new = ⌊F_ust/res⌋·res (1e-9): F_ust'ü aşmaz, bir adımdan fazla altında değil, res katı."""
    assert F_new <= F_ust + 1e-9
    assert F_new > F_ust - res - 1e-9
    assert abs(F_new / res - round(F_new / res)) < 1e-6


# ------------------------------------------------------------------ freze kapalı formları


def phi_e(ae: float, D: float = D) -> float:
    return math.acos(1 - 2 * ae / D)


def hm_kapali(fz: float, ae: float, D: float = D) -> float:
    return fz * (2 * ae / D) / phi_e(ae, D)


def hex_kapali(fz: float, ae: float, D: float = D) -> float:
    return fz * math.sin(min(phi_e(ae, D), math.pi / 2))


def kc_kapali(h: float, K: float = 1.0) -> float:
    return K * KC11 * h ** (-MC)


# ------------------------------------------------------------------ torna (SPEC 22 gerekir)

R_STOK = 25.0  # CylinderStock D = 50
AP_T = 2.0
F_T = 0.2  # mm/dev
VC = 200.0  # m/dk
N_T = 1000 * VC / (math.pi * 50.0)  # 1273.24 dev/dk
CELL_T = 0.25
T_STOCK = CylinderStock(D=50.0, zmin=-80.0, zmax=0.0)
ZT0, ZT1, ZT2 = 2.0, -5.0, -45.0  # stok dışı, giriş sonu, kararlı paso sonu (L = 40)


def torna_sim():
    """SPEC 22 simülasyonu bu dalda yoksa testi atla (LatheSimResult henüz yalnız TYPE_CHECKING altında)."""
    try:
        from cam.sim import simulate_lathe
    except ImportError:
        pytest.skip("SPEC 22 (cam.sim.simulate_lathe) bu dalda yok")
    return simulate_lathe


def kalem(kappa_r: float = 90.0) -> LatheTool:
    # uç 3: dış tornalama, hayali uç burun dairesinin (−z, −x) köşesinde → program x'i = kesilen yarıçap
    return LatheTool(
        id=5, name="kaba", kind="tornalama", nose_r=0.4, tip=3, kappa_r=kappa_r, eps_r=80.0, edge_len=6.0
    )


def torna_programi(
    feed_mode: FeedMode = FeedMode.PER_REV, feed: float = F_T, rpm: float = N_T, css: float | None = None
) -> Toolpath:
    """Boyuna paso: x = R − ap = 23'te z boyunca; hareket 0 giriş, 1 kararlı (L = 40), 2-3 G0 çıkış."""
    x = R_STOK - AP_T
    moves = [
        Move(MoveType.LINEAR, (x, 0.0, ZT1), feed=feed),
        Move(MoveType.LINEAR, (x, 0.0, ZT2), feed=feed),
        Move(MoveType.RAPID, (R_STOK + 1.0, 0.0, ZT2)),
        Move(MoveType.RAPID, (R_STOK + 1.0, 0.0, ZT0)),
    ]
    return Toolpath(
        "boyuna", kalem(), (x, 0.0, ZT0), moves, rpm=rpm, plane=Plane.ZX, feed_mode=feed_mode, css=css
    )
