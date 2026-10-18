"""SPEC 30 — bayt bayt uyum (K1): `write = format(plan(...), dialect)`.

K1: "50 rastgele op listesinde eski yazıcının bu dalın başındaki kopyasıyla metin eşitliği".
Eski yazıcının kopyası olarak onun ÇIKTISI saklandı: `data/post_compat_altin.json`, SPEC 30 iskelet
dalındaki (399f3cb, yazıcı ayrılmadan önce) `cam.gcode.write` ile üretildi. Dosya op listelerini de
(`Toolpath.to_dict` ve DrillOp alanları) taşır; böylece test rastgele sayı üretecine bağlı değildir.

Altın dosya yalnız eski yazıcıyla yeniden üretilebilir (`python -m tests.cam.test_post_compat`);
yeni yazıcıyla üretmek testi anlamsızlaştırır.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL, DrillOp, write
from cam.model import Move, MoveType, Tool, ToolKind, Toolpath
from cam.post import format, plan

ALTIN = Path(__file__).parent / "data" / "post_compat_altin.json"
DILLER = {"GRBL": GRBL, "Fanuc": FANUC}
N_LISTE = 50

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW


# ---------------------------------------------------------------- op listesi <-> JSON


def op_to_dict(op: Toolpath | DrillOp) -> dict:
    if isinstance(op, Toolpath):
        return {"tip": "yol", **op.to_dict()}
    return {
        "tip": "delik",
        "name": op.name,
        "tool": op.tool.to_dict(),
        "rpm": op.rpm,
        "start": list(op.start),
        "holes": [list(h) for h in op.holes],
        "z": op.z,
        "r": op.r,
        "feed": op.feed,
        "kind": op.kind,
        "q": op.q,
        "retract": op.retract,
    }


def op_from_dict(d: dict) -> Toolpath | DrillOp:
    d = dict(d)
    if d.pop("tip") == "yol":
        return Toolpath.from_dict(d)
    d["tool"] = Tool.from_dict(d["tool"])
    d["start"] = tuple(d["start"])
    d["holes"] = [tuple(h) for h in d["holes"]]
    return DrillOp(**d)


# ---------------------------------------------------------------- rastgele op listesi üretici

TAKIMLAR = [
    Tool(1, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0),
    Tool(2, "matkap5", ToolKind.DRILL, D=5.0, flute_length=40.0),
    Tool(3, "freze10", ToolKind.FLAT, D=10.0, flute_length=30.0),
]


def _yol(rng, k: int, tool: Tool) -> Toolpath:
    """Op başı z0 ∈ [2, 10]; kesme z < 0; doğru, iki yönde yay, helis, tam daire, kısa hareketler."""
    p = np.array([rng.uniform(-60, 60), rng.uniform(-60, 60), float(rng.uniform(2, 10))])
    start = tuple(float(v) for v in p)
    p = p.copy()
    p[2] = float(rng.uniform(-8, -0.2))
    moves = [Move(G1, tuple(float(v) for v in p), float(rng.uniform(50, 300)))]
    F = float(rng.uniform(100, 2500))
    for _ in range(int(rng.integers(3, 15))):
        if rng.random() < 0.4:
            F = float(rng.choice([F, rng.uniform(100, 2500), round(F, 1)]))
        u = rng.random()
        if u < 0.45:
            q = p.copy()
            if rng.random() < 0.15:
                q[0] += float(rng.choice([0.0003, 0.0006, 1e-5]))  # yuvarlanınca aynı / farklı
            else:
                q[:2] += rng.uniform(-25, 25, 2)
            if rng.random() < 0.3:
                q[2] = float(min(q[2] + rng.uniform(-1, 1), -0.1))
            moves.append(Move(G1, tuple(float(v) for v in q), F))
            p = q
        else:
            r = float(rng.uniform(0.5, 30))
            a0 = float(rng.uniform(0, 2 * math.pi))
            c = p[:2] - r * np.array([math.cos(a0), math.sin(a0)])
            ccw = rng.random() < 0.5
            tam = rng.random() < 0.15
            sweep = 2 * math.pi if tam else float(rng.uniform(0.3, 2 * math.pi - 0.3))
            a1 = a0 + (sweep if ccw else -sweep)
            q = np.r_[c + r * np.array([math.cos(a1), math.sin(a1)]), p[2]]
            if tam:
                q[:2] = p[:2]
            if rng.random() < 0.3:
                q[2] = float(min(p[2] + rng.uniform(-2, 2), -0.1))  # helis
            merkez = (float(c[0]), float(c[1]))
            moves.append(Move(G3 if ccw else G2, tuple(float(v) for v in q), F, center=merkez))
            p = q
    if rng.random() < 0.7:  # op kendisi geri çıkar; değilse yazıcı geri çeker (Ek B)
        moves.append(Move(G0, (float(p[0]), float(p[1]), start[2])))
    rpm = float(rng.choice([rng.uniform(1000, 20000), round(rng.uniform(1000, 20000))]))
    return Toolpath(f"yol{k}", tool, start, moves, rpm=rpm)


def _delik(rng, k: int, tool: Tool) -> DrillOp:
    z0 = float(rng.uniform(3, 10))
    r = float(rng.uniform(0.5, min(2.5, z0)))
    kind = str(rng.choice(["G81", "G83"]))
    n = int(rng.integers(1, 5))
    holes = [(float(rng.uniform(-60, 60)), float(rng.uniform(-60, 60))) for _ in range(n)]
    return DrillOp(
        f"delik{k}",
        tool,
        rpm=float(rng.uniform(500, 6000)),
        start=(holes[0][0], holes[0][1], z0),
        holes=holes,
        z=float(rng.uniform(-15, -1)),
        r=r,
        feed=float(rng.uniform(40, 300)),
        kind=kind,
        q=float(rng.uniform(1, 5)) if kind == "G83" else None,
        retract=str(rng.choice(["G98", "G99"])),
    )


def rastgele_is(seed: int) -> dict:
    """Bir op listesi ve write() parametreleri (safe_z, stock_top, program_no)."""
    rng = np.random.default_rng(seed)
    ops = []
    for k in range(int(rng.integers(1, 5))):
        tool = TAKIMLAR[int(rng.integers(3))]
        ops.append(_delik(rng, k, tool) if rng.random() < 0.25 else _yol(rng, k, tool))
    z_top = max(op.start[2] for op in ops)
    safe_z = None if rng.random() < 0.5 else float(round(z_top + rng.uniform(0, 5), 3))
    stock_top = 0.0 if rng.random() < 0.3 else None
    return {
        "seed": seed,
        "ops": [op_to_dict(op) for op in ops],
        "safe_z": safe_z,
        "stock_top": stock_top,
        "program_no": int(rng.integers(1, 10_000)),
    }


def uret() -> None:
    """Altın dosyayı ESKİ yazıcıyla üretir (yalnız yazıcı ayrılmadan önceki dalda çalıştırın)."""
    isler = []
    for seed in range(1, N_LISTE + 1):
        j = rastgele_is(seed)
        ops = [op_from_dict(d) for d in j["ops"]]
        j["metin"] = {
            ad: write(ops, d, program_no=j["program_no"], safe_z=j["safe_z"], stock_top=j["stock_top"])
            for ad, d in DILLER.items()
        }
        isler.append(j)
    ALTIN.parent.mkdir(exist_ok=True)
    satir = ",\n".join(json.dumps(j, ensure_ascii=False) for j in isler)  # iş başına bir satır
    ALTIN.write_text("[\n" + satir + "\n]\n", encoding="utf-8")


# ---------------------------------------------------------------- testler


def isler() -> list[dict]:
    return json.loads(ALTIN.read_text(encoding="utf-8"))


def test_golden_file_is_complete():
    """50 op listesi; delik, yay, tam daire, çok takım, safe_z ve stock_top temsil ediliyor."""
    js = isler()
    assert len(js) == N_LISTE
    metin = "".join(j["metin"]["Fanuc"] for j in js)
    for kelime in ("G81", "G83", "G2 ", "G3 ", "T2 M6", "T3 M6", "G98", "G99"):
        assert kelime in metin, kelime
    assert any(j["safe_z"] is not None for j in js)
    assert any(j["stock_top"] is not None for j in js)
    assert sum(len(j["ops"]) > 1 for j in js) >= 20


@pytest.mark.parametrize("dil", list(DILLER))
def test_K1_write_unchanged(dil):
    """K1: `cam.gcode.write` çıktısı yazıcı ayrılmadan önceki çıktıyla bayt bayt aynı."""
    d = DILLER[dil]
    for j in isler():
        ops = [op_from_dict(o) for o in j["ops"]]
        out = write(ops, d, program_no=j["program_no"], safe_z=j["safe_z"], stock_top=j["stock_top"])
        assert out == j["metin"][dil], f"tohum {j['seed']}"


@pytest.mark.parametrize("dil", list(DILLER))
def test_K1_format_of_plan_equals_old_writer(dil):
    """K1: `format(plan(...), dialect)` eski yazıcıyla bayt bayt aynı."""
    d = DILLER[dil]
    for j in isler():
        ops = [op_from_dict(o) for o in j["ops"]]
        bl = plan(ops, d, program_no=j["program_no"], safe_z=j["safe_z"], stock_top=j["stock_top"])
        assert format(bl, d) == j["metin"][dil], f"tohum {j['seed']}"


if __name__ == "__main__":
    uret()
