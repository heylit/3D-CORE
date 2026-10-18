"""
G-code bağımsız çapraz kontrolü (inceleme Y1, K1–K3).

`cam.gcode.write` çıktısı, `cam.gcode` ile hiçbir kod paylaşmayan `gcode_ref.RefMachine`
(LinuxCNC anlamı) ile yürütülür ve tezgâhın yapacağı hareketler CAM modeliyle karşılaştırılır.
`rs274` (LinuxCNC'nin bağımsız yorumlayıcısı) PATH'te varsa aynı program onunla da yürütülür.

Bilinen kusurlar `xfail(strict=True)`: kusur giderilince test XPASS olur ve strict olduğu için
KIRMIZI görünür. Bu bilinçli: G-code güvenlik düzeltmesi birleşince ilgili `xfail` işaretini
kaldırın; o andan itibaren test düzeltmeyi korur.

Geometri uydurmadır (ham malzeme üstü Z = 0, kesme Z < 0).
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL, DrillOp, write
from cam.model import Move, MoveType, Tool, ToolKind, Toolpath
from tests.reference.gcode_check import compare, expected, safety
from tests.reference.gcode_ref import Canon, RefError, RefMachine, run

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
STOCK_TOP = 0.0
DIALECTS = [pytest.param(GRBL, id="GRBL"), pytest.param(FANUC, id="Fanuc")]

T1 = Tool(1, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0)
T2 = Tool(2, "matkap5", ToolKind.DRILL, D=5.0, flute_length=40.0)
T3 = Tool(3, "freze10", ToolKind.FLAT, D=10.0, flute_length=30.0)


def known(reason: str):
    """Bilinen kusur: strict xfail; sadece AssertionError kabul (başka hata kırmızı kalır)."""
    return pytest.mark.xfail(
        strict=True, raises=AssertionError, reason=f"{reason} Düzeltme birleşince bu xfail'i kaldırın."
    )


def machine(d) -> RefMachine:
    return RefMachine(tool_change=d.tool_change, peck_clearance=d.peck_clearance)


def contour(end_retracted: bool = True) -> Toolpath:
    """Doğrular, iki yönde yay, helis ve tam daire içeren kontur (T1)."""
    z = -2.0
    moves = [
        Move(G1, (0, 0, z), 200),
        Move(G1, (40, 0, z), 600),
        Move(G3, (50, 10, z), 600, center=(40, 10)),  # 90° CCW
        Move(G1, (50, 30, z), 600),
        Move(G2, (40, 40, z), 450, center=(40, 30)),  # 270° CW
        Move(G1, (20.1234, 40, z), 450),
        Move(G3, (20.1234, 40, z - 1.5), 300, center=(20.1234, 32.5)),  # tam daire helis
        Move(G2, (12.6234, 32.5, z - 1.5), 300, center=(20.1234, 32.5)),
        Move(G1, (0, 0, z - 1.5), 600),
    ]
    if end_retracted:
        moves.append(Move(G0, (0, 0, 5)))
    return Toolpath("kontur", T1, (0, 0, 5), moves, rpm=8000)


def pocket(rpm: float = 6000) -> Toolpath:
    """Aynı takım (T1), farklı devir: devir değişimi takım değişimi olmadan."""
    z = -1.0
    pts = [(60, 0), (90, 0), (90, 20), (60, 20), (60, 5), (85, 5), (85, 15), (65, 15)]
    moves = [Move(G1, (60, 0, z), 150)] + [Move(G1, (x, y, z), 900) for x, y in pts[1:]]
    moves.append(Move(G0, (65, 15, 5)))
    return Toolpath("cep", T1, (60, 0, 5), moves, rpm=rpm)


def peck() -> DrillOp:
    return DrillOp(
        "gagalama",
        T2,
        rpm=2000,
        start=(10, 10, 10),
        holes=[(10, 10), (20, 10), (20, 22.5)],
        z=-12.3,
        r=2.0,
        feed=120,
        kind="G83",
        q=4.0,
        retract="G98",
    )


def spot() -> DrillOp:
    return DrillOp(
        "punta",
        T3,
        rpm=3000,
        start=(70, 40, 8),
        holes=[(70, 40), (80, 40), (80, 50)],
        z=-3.0,
        r=1.0,
        feed=90,
        kind="G81",
        retract="G99",
    )


def finish() -> Toolpath:
    """T3 ile son paso; yaylar R'si küçük, kiriş kısa (ama yuvarlama eşiğinin çok üstünde)."""
    z = -0.5
    moves = [
        Move(G1, (100, 0, z), 100),
        Move(G3, (100.05, 0.05, z), 400, center=(100.05, 0)),  # 0,05 mm yarıçap, 90°
        Move(G1, (120, 0.05, z), 400),
        Move(G2, (120, 0.05, z), 400, center=(125, 0.05)),  # tam daire CW
        Move(G0, (120, 0.05, 5)),
    ]
    return Toolpath("son", T3, (100, 0, 5), moves, rpm=9000)


def retracted_job():
    return [contour(), pocket(), peck(), spot(), finish()]


# ------------------------------------------------------------------ yorumlayıcının kendi testleri


def test_ref_machine_knows_basic_semantics():
    """Referansın kendisi el hesabıyla: G91, R biçimli yay, G90.1, G83 açılımı, satır hatası."""
    tr = run(
        "G21 G90 G17\nT1 M6\nS1000 M3\nG0 X0 Y0 Z5\nG91 G1 X10 F100\nG90 G2 X20 Y0 R5\n"
        "G90.1 G3 X10 Y0 I15 J0\nG91.1\nG0 Z5\nG99 G83 X0 Y0 Z-5 R1 Q2\nG80\nM30"
    )
    m = tr.moves
    assert np.allclose(m[0].p1, [10, 0, 5])  # ilk G0 konumlamadır, kayıt değil
    assert m[1].center == pytest.approx((15, 0)) and not m[1].ccw
    assert m[1].length == pytest.approx(5 * math.pi)
    assert m[2].center == pytest.approx((15, 0)) and m[2].ccw
    cyc = m[3:]
    feeds = [c.p1[2] for c in cyc if c.kind == "feed"]
    assert feeds == pytest.approx([-1, -3, -5])  # d_k = R − k·Q, son derinlik Z
    downs = [c.p1[2] for c in cyc if c.kind == "rapid" and c.p1[2] < 1]
    assert downs == pytest.approx([-1 + 0.254, -3 + 0.254])  # LinuxCNC geri çekilme payı
    assert cyc[-1].p1[2] == pytest.approx(1.0)  # G99: R'de biter
    with pytest.raises(RefError, match="satır 2"):
        run("G0 X0 Y0 Z0\nG2 X10 Y0 I3 J0 F100")  # yarıçaplar tutmuyor
    with pytest.raises(RefError, match="M6"):
        RefMachine(tool_change="M0").run("T1 M6")


# ------------------------------------------------------------------ model ↔ tezgâh hareketleri


@pytest.mark.parametrize("d", DIALECTS)
def test_machine_motion_matches_model(d):
    """Yazılan programı bağımsız yorumlayıcı yürütünce kesme hareketleri modelle aynı."""
    ops = retracted_job()
    tr = machine(d).run(write(ops, d))
    errs = compare(expected(ops, d.peck_clearance), tr.moves)
    assert not errs, "\n".join(errs)


def test_dialects_cut_the_same_path():
    """GRBL (yazıcı çevrimi açar) ve Fanuc (tezgâh G81/G83'ü açar) aynı kesme yolunu verir."""
    ops = retracted_job()
    g = machine(GRBL).run(write(ops, GRBL)).moves
    f = machine(FANUC).run(write(ops, FANUC)).moves
    errs = compare(g, f)
    assert not errs, "\n".join(errs)


def _random_job(seed: int) -> list[Toolpath]:
    """Sabit tohumlu rastgele iş: 3 op, her op güvenli Z'den iner, rastgele G1/G2/G3, geri çıkar."""
    rng = np.random.default_rng(seed)
    tools = [T1, T3, T1]
    ops = []
    for k, tool in enumerate(tools):
        p = np.array([rng.uniform(-80, 80), rng.uniform(-80, 80), 5.0])
        start = tuple(p)
        p = p.copy()
        p[2] = rng.uniform(-10, -0.5)
        moves = [Move(G1, tuple(p), 100)]
        for _ in range(60):
            f = float(rng.choice([300.0, rng.uniform(50, 3000)]))
            if rng.random() < 0.45:
                q = p + np.r_[rng.uniform(-30, 30, 2), rng.uniform(-1, 1) * (rng.random() < 0.3)]
                q[2] = min(q[2], -0.1)
                if np.max(np.abs(q - p)) < 0.01:
                    continue
                moves.append(Move(G1, tuple(q), f))
                p = q
                continue
            r = rng.uniform(0.2, 40)
            a0 = rng.uniform(0, 2 * math.pi)
            c = p[:2] - r * np.array([math.cos(a0), math.sin(a0)])
            ccw = rng.random() < 0.5
            if rng.random() < 0.15:
                sweep = 2 * math.pi  # tam daire
            else:
                # kiriş ≥ 0,05 mm: yuvarlamada tam daireye dönmesin (K1 ayrı testte)
                smin = 2 * math.asin(min(1.0, 0.05 / (2 * r)))
                sweep = rng.uniform(smin, 2 * math.pi - smin)
            a1 = a0 + (sweep if ccw else -sweep)
            q = np.r_[c + r * np.array([math.cos(a1), math.sin(a1)]), p[2]]
            if sweep == 2 * math.pi:
                q[:2] = p[:2]
            if rng.random() < 0.4:
                q[2] = min(p[2] + rng.uniform(-3, 3), -0.1)  # helis
            moves.append(Move(G3 if ccw else G2, tuple(q), f, center=tuple(c)))
            p = q
        moves.append(Move(G0, (p[0], p[1], 5.0)))
        ops.append(Toolpath(f"rastgele{k}", tool, start, moves, rpm=float(rng.integers(1000, 20000))))
    return ops


@pytest.mark.parametrize("d", DIALECTS)
@pytest.mark.parametrize("seed", [1, 2, 3, 20261018])
def test_random_paths_match_model(d, seed):
    ops = _random_job(seed)
    tr = machine(d).run(write(ops, d))
    errs = compare(expected(ops, d.peck_clearance), tr.moves)
    assert not errs, "\n".join(errs[:20])


@pytest.mark.parametrize("retract", ["G98", "G99"])
@pytest.mark.parametrize("kind,q", [("G81", None), ("G83", 4.0), ("G83", 2.5), ("G83", 20.0), ("G83", 0.7)])
def test_grbl_cycle_expansion_matches_linuxcnc(kind, q, retract):
    """GRBL'de çevrimi yazıcı açar (`hole_moves`); LinuxCNC G81/G83 tanımıyla karşılaştırılır."""
    op = DrillOp(
        "d",
        T2,
        rpm=1500,
        start=(0, 0, 7.5),
        holes=[(0, 0), (12.5, 0), (12.5, -8), (0, -8)],
        z=-9.1,
        r=1.5,
        feed=80,
        kind=kind,
        q=q,
        retract=retract,
    )
    tr = machine(GRBL).run(write([op], GRBL))
    errs = compare(expected([op], GRBL.peck_clearance), tr.moves)
    assert not errs, "\n".join(errs)
    exp_r = [c.p1 for c in expected([op], GRBL.peck_clearance) if c.kind == "rapid"]
    act_r = [c.p1 for c in tr.moves if c.kind == "rapid"]
    assert len(act_r) == len(exp_r) and np.allclose(act_r, exp_r, atol=5e-4)


# ------------------------------------------------------------------ bilinen kusurlar (inceleme)


@known("K1: kısa yay yuvarlanınca tam daire yazılıyor.")
@pytest.mark.parametrize("d", DIALECTS)
def test_K1_short_arc_is_not_a_full_circle(d):
    """0,0004 mm'lik yay: tezgâh 2π·r kesmemeli. Yazıcı ya yayı düşürmeli/doğruya çevirmeli ya reddetmeli."""
    tp = Toolpath(
        "kisa",
        T1,
        (10, 0, 5),
        [
            Move(G1, (10, 0, -1), 100),
            Move(G3, (9.9999999992, 0.0004, -1), 300, center=(0, 0)),
            Move(G1, (0, 10, -1), 300),
            Move(G0, (0, 10, 5)),
        ],
        rpm=5000,
    )
    try:
        text = write([tp], d)
    except ValueError:
        return  # açıkça reddetmek de güvenli
    cut = sum(c.length for c in machine(d).run(text).moves if c.kind != "rapid")
    model = 6 + 0.0004 + math.hypot(10 - 1e-9, 10)
    assert cut == pytest.approx(model, abs=0.01)


def depth_job():
    """İlk op kesme derinliğinde bitiyor (geri çekme yok), ikinci op başka takımla başlıyor."""
    return [contour(end_retracted=False), peck(), finish()]


@pytest.mark.parametrize("d", DIALECTS)
def test_retracted_job_has_no_rapid_through_stock(d):
    """Op'lar kendi içinde geri çekilince XY hızlı hareketler malzemenin üstünde, kesmede iş mili dönüyor."""
    tr = machine(d).run(write(retracted_job(), d))
    errs = [m for k, m in safety(tr, STOCK_TOP) if k in ("rapid", "cut_spindle", "end")]
    assert not errs, "\n".join(errs)


@known("K2: op geçişinde güvenli Z yok, takım değişimi kesme derinliğinde.")
@pytest.mark.parametrize("d", DIALECTS)
def test_K2_post_retracts_between_ops(d):
    tr = machine(d).run(write(depth_job(), d))
    errs = [m for k, m in safety(tr, STOCK_TOP) if k in ("rapid", "tc_z")]
    assert not errs, "\n".join(errs)


@known("K3: GRBL'de T2 M0 öncesi M5 yok (M0 iş milini durdurmaz).")
def test_K3_grbl_stops_spindle_before_tool_change():
    tr = machine(GRBL).run(write(retracted_job(), GRBL))
    errs = [m for k, m in safety(tr, STOCK_TOP) if k == "tc_spindle"]
    assert not errs, "\n".join(errs)


@known("K3: Fanuc'ta G43 H<n> ve G54 yazılmıyor.")
def test_K3_fanuc_tool_length_and_work_offset():
    tr = machine(FANUC).run(write(retracted_job(), FANUC))
    errs = [m for k, m in safety(tr, STOCK_TOP, require_tlo=True, require_wcs=True) if k in ("tlo", "wcs")]
    assert not errs, "\n".join(errs[:10])


# ------------------------------------------------------------------ LinuxCNC rs274 (kuruluysa)

RS274 = shutil.which("rs274")
_CANON = re.compile(r"(STRAIGHT_TRAVERSE|STRAIGHT_FEED|ARC_FEED|SET_FEED_RATE)\(([^)]*)\)")


def rs274_moves(text: str, tmp_path) -> list[Canon]:
    """Programı LinuxCNC `rs274` ile yürütür, kanonik çağrılardan hareket listesi kurar.

    Not: bu bağdaştırıcı geliştirme ortamında rs274 olmadığı için denenmedi; LinuxCNC 2.8/2.9
    `rs274` çıktı biçimine (ARC_FEED(son1, son2, eksen1, eksen2, dönüş, son3, a, b, c[, u, v, w]))
    göre yazıldı. '%' ve 'O' satırları LinuxCNC'de anlamlı olmadığından atılır.
    """
    src = tmp_path / "prog.ngc"
    body = [ln for ln in text.splitlines() if ln.strip() != "%" and not re.match(r"^(N\d+\s*)?O\d", ln)]
    src.write_text("%\n" + "\n".join(body) + "\n%\n")
    tbl = tmp_path / "tool.tbl"
    tbl.write_text("".join(f"T{i} P{i} D6 Z0 ;\n" for i in range(1, 10)))
    out = subprocess.run(
        [RS274, "-t", str(tbl), str(src)],
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    moves: list[Canon] = []
    p = np.zeros(3)
    feed = None
    for name, args in _CANON.findall(out.stdout):
        v = [float(a) for a in args.split(",")]
        if name == "SET_FEED_RATE":
            feed = v[0]
            continue
        if name == "ARC_FEED":
            p1 = np.array([v[0], v[1], v[5]])
            moves.append(
                Canon("arc", p, p1, 0, feed=feed, center=(v[2], v[3]), ccw=v[4] > 0, turns=int(abs(v[4])) - 1)
            )
        else:
            p1 = np.array(v[:3])
            if np.linalg.norm(p1 - p) > 1e-9:
                kind = "rapid" if name == "STRAIGHT_TRAVERSE" else "feed"
                moves.append(Canon(kind, p, p1, 0, feed=feed if kind == "feed" else None))
        p = p1
    if not moves:
        pytest.fail(f"rs274 hareket üretmedi:\n{out.stdout[-2000:]}\n{out.stderr[-2000:]}")
    return moves


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 kurulu değil")
@pytest.mark.parametrize("d", DIALECTS)
def test_linuxcnc_rs274_agrees_with_model(d, tmp_path):
    """LinuxCNC'nin kendi yorumlayıcısı: kesme yolu modelle aynı (G83 payı LinuxCNC'de farklı: sadece G81)."""
    ops = [contour(), pocket(), spot(), finish()] if d is FANUC else retracted_job()
    moves = rs274_moves(write(ops, d), tmp_path)
    # rs274 takım/devir durumunu bu bağdaştırıcıda izlemiyoruz: o farklar atlanır
    errs = compare(expected(ops, d.peck_clearance), moves)
    errs = [e for e in errs if "takım" not in e and "devir" not in e]
    assert not errs, "\n".join(errs[:20])
