"""SPEC 59 testleri için ortak uydurma veri: malzeme kaydı, takımlar, yollar ve simülasyon sonuçları.

Yalnız specs/59-takim-omru.md'deki teori ve arayüzden; cam/omur.py gövdesi okunmadı.
Simülasyon sonuçları gerçek SimStep / SimResult / LatheSimResult sınıflarıyla, elle verilen adımlarla kurulur
(cam.omur yalnız `steps` alanını, adımın op / type / start / end / center / feed / link / duration'ını okur;
harita alanları boş). Her op'un link olmayan adım sayısı op'un hareket sayısına eşittir (SPEC 32 eşlemesi).
"""

from __future__ import annotations

import math

import numpy as np

from cam.kuvvet import Load
from cam.model import FeedMode, LatheTool, LatheToolKind, Move, MoveType, Plane, Tool, ToolKind, Toolpath
from cam.sim.lathe import LatheSimResult
from cam.sim.simulate import SimResult, SimStep
from core.model import ModelError as CoreModelError
from malzeme.model import Malzeme, Taylor
from malzeme.model import ModelError as MalzemeModelError

# SPEC "ModelError" diyor; malzeme paketi kendi ModelError'unu taşır (core'u yüklememek için). İkisi de kabul.
MODEL_HATASI = (MalzemeModelError, CoreModelError)

C, N_EXP = 300.0, 0.25  # SPEC örneği: Vc · T^n = C → T(150) = 16 dk, T(300) = 1 dk


def malzeme(taylor: dict[str, Taylor] | None = None) -> Malzeme:
    """Uydurma C45 kaydı; varsayılan yalnız karbur için Taylor(C = 300, n = 0.25)."""
    if taylor is None:
        taylor = {"karbur": Taylor(C, N_EXP)}
    return Malzeme(
        id="1.0503",
        name="C45",
        standart="EN 10083-2",
        grup="celik",
        kaynak="uydurma test kaydı (SPEC 59)",
        iso513="P",
        taylor=taylor,
    )


def T_taylor(Vc: float, c: float = C, n: float = N_EXP) -> float:
    """Taylor ömrü [dk] (SPEC Teori): T = (C / Vc)^(1/n)."""
    return (c / Vc) ** (1.0 / n)


def rpm_for(Vc: float, D: float) -> float:
    """Vc = π D n / 1000 → n (kesin; SPEC'teki 4774.65 yuvarlanmış değerdir)."""
    return 1000.0 * Vc / (math.pi * D)


def freze(id: int = 3, D: float = 10.0, kind: ToolKind = ToolKind.FLAT, corner_r: float = 0.0, **kw) -> Tool:
    kw.setdefault("flute_length", 25.0)
    kw.setdefault("flutes", 4)
    return Tool(id, f"freze{id}", kind, D=D, corner_r=corner_r, **kw)


def torna_ucu(id: int = 5, nose_r: float = 0.8, kappa_r: float = 95.0, eps_r: float = 80.0) -> LatheTool:
    return LatheTool(id, f"torna{id}", LatheToolKind.TURN, nose_r, 3, kappa_r, eps_r)


def _yuk(k: int, op: int, move: int | None, kind: str, ap: float) -> Load:
    return Load(k, op, move, kind, ap=ap, ae=None, h=None, kc=None, Q=0.0, P=0.0, M=0.0, F_t=None)


def _adim(k, op, typ, start, end, feed, link, t0, duration, center=None) -> SimStep:
    return SimStep(
        k=k,
        op=op,
        type=MoveType(typ),
        start=tuple(float(v) for v in start),
        end=tuple(float(v) for v in end),
        center=center,
        feed=feed,
        link=link,
        t0=t0,
        duration=duration,
        removed=0.0,
        mrr=0.0,
    )


def _sim_result(steps: list[SimStep], op_times: list[float]) -> SimResult:
    bos = np.zeros(0)
    return SimResult(
        zmap=None,
        steps=steps,
        start=steps[0].start if steps else (0.0, 0.0, 0.0),
        total_time=sum(s.duration for s in steps),
        op_times=op_times,
        event_cell=bos.astype(np.int32),
        event_k=bos.astype(np.int32),
        event_z=bos,
        offsets=bos.astype(np.int64),
    )


def freze_programi(
    oplar: list[tuple[Tool, float, list[tuple[str, float, str, float]]]],
) -> tuple[list[Toolpath], SimResult, list[Load]]:
    """Uydurma freze programı.

    oplar: her op için (takım, rpm, hareketler); hareket = (tip "G0" / "G1", süre [dk], yük türü, ap).
    G1 hareketleri x yönünde F = 1000 mm/dk ile süre × F boyunda; G0 hareketleri z = 50'de. Op'lar arasına
    bir link adımı (G0, "hava") girer.
    """
    ops: list[Toolpath] = []
    steps: list[SimStep] = []
    loads: list[Load] = []
    t0 = 0.0
    p = np.array([0.0, 0.0, 50.0])
    op_times = []
    for i, (tool, rpm, hareketler) in enumerate(oplar):
        if i > 0:
            q = p + np.array([0.0, 10.0, 0.0])
            steps.append(_adim(len(steps), i, "G0", p, q, None, True, t0, 0.5))
            loads.append(_yuk(len(loads), i, None, "hava", 0.0))
            t0 += 0.5
            p = q
        start = tuple(p)
        moves = []
        t_op = 0.0
        for j, (typ, t_dk, tur, ap) in enumerate(hareketler):
            if typ == "G0":
                q = p + np.array([5.0, 0.0, 0.0])
                moves.append(Move(MoveType.RAPID, tuple(q)))
                feed = None
            else:
                q = p + np.array([1000.0 * t_dk, 0.0, 0.0])
                moves.append(Move(MoveType.LINEAR, tuple(q), feed=1000.0))
                feed = 1000.0
            sure = 60.0 * t_dk
            steps.append(_adim(len(steps), i, typ, p, q, feed, False, t0, sure))
            loads.append(_yuk(len(loads), i, j, tur, ap))
            t0 += sure
            t_op += sure
            p = q
        ops.append(Toolpath(f"op{i}", tool, start, moves, rpm=rpm))
        op_times.append(t_op)
    return ops, _sim_result(steps, op_times), loads


def torna_programi(
    oplar: list[tuple[LatheTool, float, float | None, float, list[tuple[float, float]], float]],
) -> tuple[list[Toolpath], LatheSimResult, list[Load]]:
    """Uydurma torna programı (ZX, G95 mm/dev).

    oplar: her op için (takım, rpm, css, f, noktalar [(x, z), ...], ap); x yarıçap. Ardışık noktalar G1 kesme
    hareketleridir (yük "kesme"). Adım süreleri teoriden (dt = ds / (f n)) hesaplanır ve ayrıca verilir.
    """
    ops: list[Toolpath] = []
    steps: list[SimStep] = []
    loads: list[Load] = []
    t0 = 0.0
    op_times = []
    for i, (tool, rpm, css, f, noktalar, ap) in enumerate(oplar):
        start = (noktalar[0][0], 0.0, noktalar[0][1])
        moves = []
        t_op = 0.0
        for j, ((x0, z0), (x1, z1)) in enumerate(zip(noktalar, noktalar[1:], strict=False)):
            moves.append(Move(MoveType.LINEAR, (x1, 0.0, z1), feed=f))
            # devirsiz yol (yalnız hata testi): süre teoride tanımsız, 0 verilir
            sure = 0.0 if css is None and rpm <= 0 else 60.0 * kesme_suresi(x0, z0, x1, z1, f, rpm, css)
            steps.append(_adim(len(steps), i, "G1", (x0, 0, z0), (x1, 0, z1), f, False, t0, sure))
            loads.append(_yuk(len(loads), i, j, "kesme", ap))
            t0 += sure
            t_op += sure
        ops.append(
            Toolpath(
                f"op{i}", tool, start, moves, rpm=rpm, plane=Plane.ZX, feed_mode=FeedMode.PER_REV, css=css
            )
        )
        op_times.append(t_op)
    bos = np.zeros(0)
    res = LatheSimResult(
        rmap=None,
        steps=steps,
        start=steps[0].start,
        total_time=t0,
        op_times=op_times,
        event_cell=bos.astype(np.int32),
        event_k=bos.astype(np.int32),
        event_iv_off=np.zeros(1, dtype=np.int64),
        event_iv=np.zeros((0, 2)),
        offsets=np.zeros(1, dtype=np.int64),
    )
    return ops, res, loads


def kesme_suresi(x0, z0, x1, z1, f, rpm, css) -> float:
    """Doğrusal adımın süresi [dk] (yalnız teorideki durumlar): sabit devirde L / (f N); G96'da sabit r
    (boy tornalama) L / (f n(r)); G96 alın (z sabit) ∫ dr / (f n(r)), r* altında n = N_max."""
    L = math.hypot(x1 - x0, z1 - z0)
    if css is None:
        return L / (f * rpm)
    r_yildiz = 1000.0 * css / (2 * math.pi * rpm)
    if abs(x1 - x0) < 1e-15:
        r = abs(x0)
        n = rpm if r < r_yildiz else 1000.0 * css / (2 * math.pi * r)
        return L / (f * n)
    assert abs(z1 - z0) < 1e-15, "uydurma G96 yolu: yalnız alın veya boy"
    a, b = sorted((abs(x0), abs(x1)))
    ust = max(a, r_yildiz)
    t = 0.0
    if b > ust:  # n(r) = 1000 Vc₀ / (2π r) → ∫ 2π r dr / (1000 Vc₀ f)
        t += 2 * math.pi * (b * b - ust * ust) / (2 * 1000.0 * css * f)
    alt_ust = min(b, r_yildiz)
    if alt_ust > a:
        t += (alt_ust - a) / (f * rpm)
    return t


def g97_alin_D(N: float, f: float, R0: float, c: float = C, n: float = N_EXP) -> float:
    """SPEC kapalı form: D = (2π N / (1000 C))^m · R₀^(m+1) / ((m + 1) · f · N)."""
    m = 1.0 / n
    return (2 * math.pi * N / (1000.0 * c)) ** m * R0 ** (m + 1) / ((m + 1) * f * N)
