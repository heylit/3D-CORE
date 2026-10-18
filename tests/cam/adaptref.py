"""SPEC 19 testleri için ortak yardımcılar: takım / kesme üreticileri, açı toleransı, yol ayrıştırma,
"yeniden oynatma" ve T'nin iç hücreleri.

Bu modül test değildir (adı test_ ile başlamaz). Uygulama kodu (cam/adaptive.py gövdeleri) okunmadan,
yalnızca SPEC 19 "Arayüz" ve "Kabul kriterleri" metninden yazıldı.

Yeniden oynatma (SPEC 19 "Kabul kriterleri" giriş paragrafı): MaterialGrid.from_region(Ω, h) üzerinde bir paso
derinliğinin hareketleri sırayla cut_segment / cut_arc ile uygulanır; helis ve tabandaki ilk tam tur hariç
her kesme
hareketi boyu ≤ step olan parçalara bölünür ve her parçanın engagement'ı kesimden önce ölçülür.

Açı toleransı (SPEC 19 Teori, malzeme ızgarası):
    tol(φ) = (180/π)·h / (r·sin φ) + 360°/n_α      (15° ≤ φ ≤ 165°)
    tol(180°) = (180/π)·h / r + 360°/n_α
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.model import MoveType, Tool, ToolKind, Toolpath
from cam.ops2d import Cut
from tests.cam.ref2d import Parca, RefBolge, arc_ccw_form, moves_of

TWO_PI = 2.0 * math.pi
ARC_TYPES = {MoveType.ARC_CW, MoveType.ARC_CCW}
FEED_TYPES = {MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW}
EPS_Z = 1e-9


def flat_tool(D: float = 10.0, flute_length: float = 30.0, **kw) -> Tool:
    """Düz parmak freze (uydurma)."""
    return Tool(id=1, name=f"freze{D:g}", kind=ToolKind.FLAT, D=D, flute_length=flute_length, **kw)


def make_cut(**kw) -> Cut:
    """Varsayılan: z 0 → −5 tek paso (a_p 5), z_safe 10, clearance 1, stepover yok."""
    args = dict(z_top=0.0, z_bottom=-5.0, a_p=5.0, feed=1500.0, plunge_feed=300.0, rpm=8000.0, z_safe=10.0)
    args.update(kw)
    return Cut(**args)


def tol_phi(phi: float, h: float, r: float, n: int = 1440) -> float:
    """SPEC 19 ızgara hata sınırı tol(φ) [derece]."""
    if phi >= 180.0 - 1e-9:
        return math.degrees(h / r) + 360.0 / n
    if not 15.0 - 1e-9 <= phi <= 165.0 + 1e-9:
        raise ValueError(f"tol(φ) yalnız 15°..165° ve 180° için tanımlı (φ={phi})")
    return math.degrees(h / (r * math.sin(math.radians(phi)))) + 360.0 / n


ARC_PIECE = math.radians(4.0)  # yeniden oynatmada yay parçalarının en büyük açısı


def chord_margin(s: float, r: float, arc: bool, arc_piece: float = ARC_PIECE) -> float:
    """Yeniden oynatmanın kiriş payı [derece]; tol(φ)'ye eklenir (koordinatör onayı, 2026-10-18).

    1. Yan bant: tanımdaki dist(q, [a, b]) ≥ r koşulu, b'nin arkasında ilerleme yönüne dik doğrultu çevresinde
       genişliği ≈ s/(2r) radyan olan bandı malzeme sayar (|q − a|² = s² − 2sr·cos β + r² > r² ⇔ cos β <
       s/(2r)),
       s parça boyu. SPEC tol(φ) bunu içermez; uygulama da aynı tanımla ölçtüğünden pay iki yönde de
       geçerlidir.
    2. Yay parçasında kiriş, b'deki teğetten parça açısının yarısı kadar döner; ön yarı düzlem de o kadar
    döner.
    """
    m = math.degrees(s / (2.0 * r))
    if arc:
        m += math.degrees(arc_piece) / 2.0
    return m


# ---------------------------------------------------------------- hareket sınıflandırma


def xy_len(p: Parca) -> float:
    if p.type in ARC_TYPES:
        R, _, sw = p.arc_form()
        return R * sw
    return float(np.hypot(*(p.p1[:2] - p.p0[:2])))


def is_helix(p: Parca) -> bool:
    """Z'si değişen yay (helis parçası)."""
    return p.type in ARC_TYPES and abs(p.p1[2] - p.p0[2]) > EPS_Z


def is_full_turn(p: Parca) -> bool:
    """Yatay tam tur: başlangıç = bitiş (XY), Z sabit."""
    return (
        p.type in ARC_TYPES
        and abs(p.p1[2] - p.p0[2]) <= EPS_Z
        and float(np.hypot(*(p.p1[:2] - p.p0[:2]))) < 1e-9
    )


def feed_runs(tp: Toolpath) -> list[list[Parca]]:
    """G0'larla ayrılmış ardışık kesme (G1/G2/G3) hareketi grupları."""
    runs: list[list[Parca]] = []
    cur: list[Parca] = []
    for p in moves_of(tp):
        if p.type is MoveType.RAPID:
            if cur:
                runs.append(cur)
                cur = []
        else:
            cur.append(p)
    if cur:
        runs.append(cur)
    return runs


def move_length(p: Parca) -> float:
    """Hareket boyu: yayda √((R·Δθ)² + Δz²), doğruda |p1 − p0| (cam/model.py kuralı)."""
    if p.type in ARC_TYPES:
        R, _, sw = p.arc_form()
        return math.hypot(R * sw, p.p1[2] - p.p0[2])
    return float(np.linalg.norm(p.p1 - p.p0))


def sub_arcs(p: Parca, max_chord: float, max_angle: float | None = None):
    """Yayı eşit açılı alt yaylara böler: her alt yayın kirişi ≤ max_chord (ve açısı ≤ max_angle [rad]).

    (q0, q1, merkez, ccw) XY dörtlüleri, ilerleme yönünde.
    """
    R, _, sw = p.arc_form()
    c = p.center[:2]
    ccw = p.type is MoveType.ARC_CCW
    dmax = 2.0 * math.asin(min(1.0, max_chord / (2.0 * R)))
    if max_angle is not None:
        dmax = min(dmax, max_angle)
    n = max(1, math.ceil(sw / dmax - 1e-12))
    t0 = math.atan2(p.p0[1] - c[1], p.p0[0] - c[0])
    sgn = 1.0 if ccw else -1.0
    out = []
    for k in range(n):
        a0 = t0 + sgn * sw * k / n
        a1 = t0 + sgn * sw * (k + 1) / n
        q0 = c + R * np.array([math.cos(a0), math.sin(a0)])
        q1 = c + R * np.array([math.cos(a1), math.sin(a1)])
        out.append((q0, q1, c, ccw))
    return out


def sub_lines(a, b, max_len: float):
    """[a, b] doğrusunu boyu ≤ max_len olan eşit parçalara böler."""
    a = np.asarray(a, dtype=float)[:2]
    b = np.asarray(b, dtype=float)[:2]
    L = float(np.hypot(*(b - a)))
    n = max(1, math.ceil(L / max_len - 1e-12))
    return [(a + (b - a) * k / n, a + (b - a) * (k + 1) / n) for k in range(n)]


# ---------------------------------------------------------------- yeniden oynatma


@dataclass
class Replay:
    """Yeniden oynatma sonucu. phis[k], lens[k]: ölçülen parçanın φ'si [derece] ve XY boyu [mm].
    plunges: helis dışı aşağı hareketlerin bitiş noktası ve o noktada cut_segment(p, p, r)'nin boşalttığı
    alan."""

    grid: object
    phis: list[float] = field(default_factory=list)
    lens: list[float] = field(default_factory=list)
    where: list[tuple[float, float]] = field(default_factory=list)
    is_arc: list[bool] = field(default_factory=list)
    plunges: list[tuple[tuple[float, float], float]] = field(default_factory=list)

    @property
    def max_phi(self) -> float:
        return max(self.phis) if self.phis else 0.0


def replay(
    grid,
    tp: Toolpath,
    r: float,
    step: float,
    z_top: float,
    n: int = 1440,
    arc_angle: float | None = ARC_PIECE,
) -> Replay:
    """Takım yolunun malzemeye giren (min z < z_top) kesme hareketlerini ızgarada sırayla uygular.

    Helis yayları ve helisten hemen sonraki ilk yatay tam tur ölçülmeden kesilir. Diğer hareketler XY'de boyu
    ≤ step (yayda ayrıca açısı ≤ arc_angle) parçalara bölünür; her parçanın engagement'ı kesimden önce
    ölçülür.
    Tek paso derinlikli yollar için (yol XY'de her pasoda aynı; SPEC 19 adaptif cep).
    """
    rep = Replay(grid)
    after_helix = False
    for p in moves_of(tp):
        if p.type not in FEED_TYPES:
            continue
        if min(p.p0[2], p.p1[2]) >= z_top - EPS_Z:
            continue  # malzemenin üstünde
        if is_helix(p):
            grid.cut_arc(p.p0[:2], p.p1[:2], p.center[:2], p.type is MoveType.ARC_CCW, r)
            after_helix = True
            continue
        if after_helix and is_full_turn(p):
            grid.cut_arc(p.p0[:2], p.p1[:2], p.center[:2], p.type is MoveType.ARC_CCW, r)
            after_helix = False
            continue
        after_helix = False
        if p.p1[2] < p.p0[2] - EPS_Z and p.p1[2] < z_top - EPS_Z:
            q = (float(p.p1[0]), float(p.p1[1]))
            # hareketten ÖNCE iniş noktasında malzeme var mı (K7): cut_segment(p, p, r) boşalttığı alan
            if xy_len(p) < 1e-12:
                rep.plunges.append((q, float(grid.cut_segment(q, q, r))))
                continue
            probe = _probe(grid, q, r)
            rep.plunges.append((q, probe))
        if xy_len(p) < 1e-12:
            continue
        if p.type in ARC_TYPES:
            for q0, q1, c, ccw in sub_arcs(p, step, arc_angle):
                phi = float(grid.engagement(q0, q1, r, n))
                rep.phis.append(phi)
                rep.lens.append(float(np.hypot(*(q1 - q0))))
                rep.where.append((float(q1[0]), float(q1[1])))
                rep.is_arc.append(True)
                grid.cut_arc(q0, q1, c, ccw, r)
        else:
            for a, b in sub_lines(p.p0, p.p1, step):
                phi = float(grid.engagement(a, b, r, n))
                rep.phis.append(phi)
                rep.lens.append(float(np.hypot(*(b - a))))
                rep.where.append((float(b[0]), float(b[1])))
                rep.is_arc.append(False)
                grid.cut_segment(a, b, r)
    return rep


def _probe(grid, q, r: float) -> float:
    """cut_segment(q, q, r)'nin boşaltacağı alan; ızgara değişmez (kopyada ölçülür)."""
    m = grid.m.copy()
    area = float(grid.cut_segment(q, q, r))
    grid.m[...] = m
    return area


# ---------------------------------------------------------------- bölge ve T'nin iç hücreleri


def cell_centers(grid) -> tuple[np.ndarray, np.ndarray]:
    j = np.arange(grid.nx)
    i = np.arange(grid.ny)
    X = grid.x0 + (j + 0.5) * grid.h
    Y = grid.y0 + (i + 0.5) * grid.h
    return np.meshgrid(X, Y)  # (ny, nx)


def boundary_distance(bolge: RefBolge, P: np.ndarray, chunk: int = 200_000) -> np.ndarray:
    """Noktaların bölge sınırına uzaklığı (parça parça, bellek için)."""
    e = bolge.boundary()
    out = np.empty(len(P))
    for s in range(0, len(P), chunk):
        out[s : s + chunk] = e.distance(P[s : s + chunk])
    return out


def t_inner(grid, bolge: RefBolge, r: float, leave: float = 0.0) -> np.ndarray:
    """T'nin iç hücreleri (merkezi C'ye uzaklığı ≤ r − h) için tutucu (alt küme) bir maske, (ny, nx) bool.

    C = {p ∈ Ω : dist(p, ∂Ω) ≥ r + leave} hücre merkezlerinde tam hesaplanır; merkezi C-hücrelerine öklid
    uzaklığı
    ≤ r − 2h olan hücreler seçilir. C-hücre merkezleri C'nin içinde olduğundan dist(x, C) ≤ bu uzaklık:
    seçilen her
    hücre gerçekten iç hücredir (ek h payı ızgara örneklemesi için).
    """
    from scipy.ndimage import distance_transform_edt

    X, Y = cell_centers(grid)
    P = np.column_stack([X.ravel(), Y.ravel()])
    inside = bolge.contains(P)
    d = np.zeros(len(P))
    d[inside] = boundary_distance(bolge, P[inside])
    C = (inside & (d >= r + leave)).reshape(grid.ny, grid.nx)
    if not C.any():
        return np.zeros_like(C)
    dist = distance_transform_edt(~C) * grid.h
    return dist <= r - 2.0 * grid.h


def arc_sweep(p: Parca) -> float:
    """Yayın süpürme açısı [rad] (cam/model.py kuralı: başlangıç = bitiş → 2π)."""
    return arc_ccw_form(p.p0, p.p1, p.center, p.type is MoveType.ARC_CW)[2]


# ---------------------------------------------------------------- ızgarasız (tam) temas açısı


def _near(p: Parca, b: np.ndarray, reach: float) -> bool:
    """Hareket b'nin reach yakınından geçebilir mi (kaba eleme)."""
    if p.type in ARC_TYPES:
        R, _, _ = p.arc_form()
        return float(np.hypot(*(b - p.center[:2]))) <= R + reach
    a, c = p.p0[:2], p.p1[:2]
    ab = c - a
    L2 = float(ab @ ab)
    t = 0.0 if L2 == 0 else min(1.0, max(0.0, float((b - a) @ ab) / L2))
    return float(np.hypot(*(b - (a + t * ab)))) <= reach


def _add_curve(e, p: Parca, upto: float | None = None) -> None:
    """Hareketin XY izdüşümünü (upto verilirse başlangıçtan o kesre kadarki kısmını) eğri kümesine ekler."""
    f = 1.0 if upto is None else upto
    if f <= 0:
        return
    if p.type in ARC_TYPES:
        R, th0, sw = p.arc_form()
        if p.type is MoveType.ARC_CCW:
            e.arc(p.center[:2], R, th0, sw * f)
        else:  # CW: ccw biçiminde başlangıç bitiş açısıdır; ilk f kesri p0'dan geriye doğru
            e.arc(p.center[:2], R, th0 + sw * (1 - f), sw * f)
    else:
        e.line(p.p0[:2], p.p0[:2] + f * (p.p1[:2] - p.p0[:2]))


def exact_engagements(
    tp: Toolpath,
    r: float,
    z_top: float,
    n: int = 1440,
    d_ang: float = 1.0,
    d_len: float = 0.05,
    front_half: bool = False,
):
    """Izgarasız temas açısı: kesme yolu boyunca yoğun örnekte φ [derece] listesi.

    Malzeme: stok sınırsız; takım merkezinin b'ye kadarki önceki XY yoluna (yaylar analitik,
    tests/cam/ref2d.Egriler) uzaklığı > r olan noktalar. Varsayılan tanım SPEC 19 Ek A1'inkidir: φ = takım
    çevresinin bu malzemeye düşen açısı (trochoid_loop_engagement ile aynı tanım). front_half=True ise ayrıca
    (q − b)·u > 0 (ilerleme yönünün önü) istenir: ana tanımın a → b limiti. İkisi sıkı yaylarda ayrışır (dış
    taraftaki arka noktalar süpürülmemiş kalabilir). Helis yayları ve helisten sonraki ilk tam tur ölçülmez
    (yalnız yola eklenir). Örnek aralığı: yayda d_ang derece, doğruda d_len mm.
    Dönüş: (φ, b, hareket indisi) üçlüleri.
    """
    from tests.cam.ref2d import Egriler

    al = 2 * math.pi * np.arange(n) / n
    E = np.column_stack([np.cos(al), np.sin(al)])
    parts = [p for p in moves_of(tp) if p.type in FEED_TYPES and min(p.p0[2], p.p1[2]) < z_top - EPS_Z]
    out = []
    after_helix = False
    for idx, p in enumerate(parts):
        if is_helix(p):
            after_helix = True
            continue
        if after_helix and is_full_turn(p):
            after_helix = False
            continue
        after_helix = False
        L = xy_len(p)
        if L < 1e-12:
            continue
        if p.type in ARC_TYPES:
            R, _, sw = p.arc_form()
            m = max(1, math.ceil(math.degrees(sw) / d_ang))
        else:
            m = max(1, math.ceil(L / d_len))
        t0 = None
        if p.type in ARC_TYPES:
            c = p.center[:2]
            t0 = math.atan2(p.p0[1] - c[1], p.p0[0] - c[0])
            sgn = 1.0 if p.type is MoveType.ARC_CCW else -1.0
        for k in range(1, m + 1):
            f = k / m
            if p.type in ARC_TYPES:
                th = t0 + sgn * sw * f
                b = c + R * np.array([math.cos(th), math.sin(th)])
                u = sgn * np.array([-math.sin(th), math.cos(th)])
            else:
                b = p.p0[:2] + f * (p.p1[:2] - p.p0[:2])
                u = (p.p1[:2] - p.p0[:2]) / L
            e = Egriler()
            for q in parts[:idx]:
                if _near(q, b, 2 * r):
                    _add_curve(e, q)
            eps = 1e-6 / max(L, 1e-9)  # yay/doğru takımın 1e-6 mm gerisinde biter
            _add_curve(e, p, f - eps)
            Q = b + r * E
            mat = e.distance(Q) > r
            if front_half:
                mat &= (Q - b) @ u > 0
            out.append((360.0 / n * int(mat.sum()), (float(b[0]), float(b[1])), idx))
    return out


# ---------------------------------------------------------------- Ek A1: döngü boyunca temas (testin kendi
# hesabı)


def loop_phi_at(rho: float, r: float, p: float, th: float, n: int = 7200) -> float:
    """Ek A1 φ(α) [derece], α = th [rad] ∈ (π, 3π]: döngü merkezi orijinde, önceki döngü merkezi (−p, 0).

    Malzeme: |q − (−p, 0)| > ρ + r ve q'nun bu döngüde π'den th'ye kadarki yaya (yarıçap ρ, CCW) uzaklığı > r.
    Yaya uzaklık analitik: q'nun kutup açısı süpürülen aralıktaysa ||q| − ρ|, değilse uç noktalara uzaklığın
    küçüğü.
    Yay, takımın bulunduğu noktadan 1e-9 rad önce biter (takımın kendi çevresi sınırda kalır).
    """
    al = 2 * math.pi * np.arange(n) / n
    b = rho * np.array([math.cos(th), math.sin(th)])
    Q = b + r * np.column_stack([np.cos(al), np.sin(al)])
    mat = np.hypot(Q[:, 0] + p, Q[:, 1]) > rho + r
    sw = th - math.pi - 1e-9
    rel = np.mod(np.arctan2(Q[:, 1], Q[:, 0]) - math.pi, TWO_PI)
    e0 = np.array([-rho, 0.0])
    e1 = rho * np.array([math.cos(math.pi + sw), math.sin(math.pi + sw)])
    d_end = np.minimum(np.linalg.norm(Q - e0, axis=1), np.linalg.norm(Q - e1, axis=1))
    d = np.where(rel <= sw, np.abs(np.hypot(Q[:, 0], Q[:, 1]) - rho), d_end)
    mat &= d > r
    return 360.0 * float(mat.mean())


def loop_phi_ref(rho: float, r: float, p: float, n: int = 7200) -> tuple[float, float]:
    """Ek A1 φ_loop = max φ(α): 0,5° adımlı tarama + en büyüğün çevresinde 0,025° adımlı inceltme.

    Dönüş: (φ_loop [derece], konum [derece, ön nokta 0°, CCW]).
    """
    ths = np.radians(np.arange(180.5, 540.0 + 1e-9, 0.5))
    v = [loop_phi_at(rho, r, p, t, n) for t in ths]
    i = int(np.argmax(v))
    lo, hi = ths[max(i - 1, 0)], ths[min(i + 1, len(ths) - 1)]
    best = max((loop_phi_at(rho, r, p, t, n), t) for t in np.linspace(lo, hi, 41))
    return best[0], math.degrees(best[1]) % 360.0
