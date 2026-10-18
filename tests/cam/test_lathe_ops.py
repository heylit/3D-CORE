"""SPEC 20 — cam/lathe_ops.py testleri (K7–K13, K16).

Testler sadece SPEC 20 metninden ve sabit arayüzlerden (cam/model.py, cam/profile.py, cam.lathe imzaları)
yazıldı; cam/lathe.py ve cam/lathe_ops.py gövdeleri okunmadı. Beklenen değerler el ile türetildi:

- Hayali uç P = C + q_T (T = 3: q = (−r, −r), (z, x) sırasında); yol noktaları (x, 0, z), yay merkezi (x, z).
- Güvenli nokta: C_A = (z_max + cl + r, X_s + cl + r), P_A = C_A + q_T (iç tarafta X_s = d/2 aynada).
- Alın: n = ⌈H/a_p⌉ (1e-9 toleranslı), temas düzlemi z_i = z_max − i·H/n, C_z = z_i + r, C_x → x_son.
- Kaba: x_low = δ ofsetli profilin başlangıç x'i, H = X_s − x_low, n = ⌈H/a_p⌉, x_k = X_s − k·H/n,
  boyuna paso C_x = x_k + r; ρ = r + δ sınırının seviyeyle ilk kesişimi:
    düşey duvar z_w: C_z = z_w + ρ;
    dışbükey köşe V yayı: C_z = V_z + √(ρ² − (C_x − V_x)²);
    koni (başlangıcı (z_c, x_c), yarım açı α): C_z = z_c − (C_x − x_c)/tan α + ρ/sin α.
- Kanal: m = ⌈(W − w)/(w − 2r)⌉ + 1, z_L,j = z_left + j·(W − w)/(m − 1).
Uzaklıklar tests/cam/ref2d.py'deki bağımsız analitik hesapla (cam.geom2d kullanılmaz).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.lathe import tip_path
from cam.lathe_ops import TurnCut, face, finish, groove, rough, thread, turn
from cam.model import CamError, CylinderStock, FeedMode, LatheTool, LatheToolKind, MoveType, Plane, Toolpath
from cam.profile import Arc, Line, Profile
from tests.cam.ref2d import Egriler, arc_ccw_form

TOL = 1e-9
R_NOSE = 0.8
DELTA = 0.3
TURN = LatheToolKind.TURN
BORE = LatheToolKind.BORE
GROOVE = LatheToolKind.GROOVE
THREAD = LatheToolKind.THREAD
KESME = {MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW}
YAY = {MoveType.ARC_CW, MoveType.ARC_CCW}

# SPEC 20 uç tablosu (s_z, s_x)
TABLO = {
    0: (0, 0),
    1: (1, 1),
    2: (-1, 1),
    3: (-1, -1),
    4: (1, -1),
    5: (1, 0),
    6: (0, 1),
    7: (-1, 0),
    8: (0, -1),
    9: (0, 0),
}
T30 = math.tan(math.radians(30.0))


# ------------------------------------------------------------------ takımlar, kesme, ham malzeme


def ttool(tip: int = 3, r: float = R_NOSE, kind=TURN, kappa: float = 93.0, eps: float = 55.0) -> LatheTool:
    return LatheTool(id=1, name="T", kind=kind, nose_r=r, tip=tip, kappa_r=kappa, eps_r=eps)


def gtool(tip: int = 3, w: float = 3.0, r: float = 0.2) -> LatheTool:
    return LatheTool(id=2, name="K", kind=GROOVE, nose_r=r, tip=tip, kappa_r=90.0, eps_r=90.0, width=w)


def cut(a_p: float | None = 3.0, css: float | None = 180.0, **kw) -> TurnCut:
    return TurnCut(feed=0.2, rpm=2000.0, css=css, a_p=a_p, **kw)


def q_of(tool: LatheTool) -> np.ndarray:
    """q_T, (z, x) sırasında, gerçek (aynalanmamış) koordinatta."""
    return tool.nose_r * np.array(TABLO[tool.tip], dtype=float)


def p_A(stock: CylinderStock, tool: LatheTool, c: TurnCut, side: str = "dis") -> np.ndarray:
    """Güvenli nokta P_A, (z, x)."""
    r = tool.nose_r
    Cx = stock.D / 2 + c.clearance + r if side == "dis" else stock.d / 2 - c.clearance - r
    return np.array([stock.zmax + c.clearance + r, Cx]) + q_of(tool)


# ------------------------------------------------------------------ profiller (uydurma)

STOCK = CylinderStock(D=50.0, zmin=-100.0, zmax=0.0)  # X_s = 25
STOCK60 = CylinderStock(D=60.0, zmin=-100.0, zmax=0.0)  # X_s = 30
TUBE = CylinderStock(D=60.0, zmin=-100.0, zmax=0.0, d=16.0)  # iç X_s = 8


def poly(*pts) -> Profile:
    return Profile.polygon(pts, closed=False)


def p_shoulder() -> Profile:
    """Omuzlu mil: x = 10 (z 0..−20), x = 16 (−20..−40), alın x = 25'e."""
    return poly((0.0, 10.0), (-20.0, 10.0), (-20.0, 16.0), (-40.0, 16.0), (-40.0, 25.0))


CONE = {"zc": -10.0, "xc": 12.0, "a": math.radians(30.0), "zw": -30.0}


def p_cone() -> Profile:
    """Silindir x = 12, z = −10'dan 30° koni z = −30'a, alın x = 25'e."""
    x_end = CONE["xc"] + 20.0 * T30
    return poly((0.0, 12.0), (-10.0, 12.0), (-30.0, x_end), (-30.0, 25.0))


def p_arc() -> Profile:
    """Önde dışbükey R = 3 yay (φ 90° → 0°), silindir x = 20, alın x = 25'e."""
    return Profile(
        [
            Arc((0.0, 17.0), (-3.0, 20.0), (-3.0, 17.0), ccw=True),
            Line((-3.0, 20.0), (-30.0, 20.0)),
            Line((-30.0, 20.0), (-30.0, 25.0)),
        ],
        closed=False,
    )


def p_finish(R_fil: float = 2.0) -> Profile:
    """Pah + silindir + içbükey dolgu + omuz + silindir + 30° koni + alın (X_s = 30'a)."""
    x_cone = 18.0 + 10.0 * T30
    return Profile(
        [
            Line((0.0, 8.0), (-2.0, 10.0)),
            Line((-2.0, 10.0), (-17.0 + R_fil, 10.0)),
            Arc((-17.0 + R_fil, 10.0), (-17.0, 10.0 + R_fil), (-17.0 + R_fil, 10.0 + R_fil), ccw=False),
            Line((-17.0, 10.0 + R_fil), (-17.0, 18.0)),
            Line((-17.0, 18.0), (-25.0, 18.0)),
            Line((-25.0, 18.0), (-35.0, x_cone)),
            Line((-35.0, x_cone), (-35.0, 30.0)),
        ],
        closed=False,
    )


def p_narrow_groove() -> Profile:
    """1.5 mm genişliğinde kanal (< 2r = 1.6)."""
    return poly(
        (0.0, 15.0), (-10.0, 15.0), (-10.0, 12.0), (-11.5, 12.0), (-11.5, 15.0), (-30.0, 15.0), (-30.0, 30.0)
    )


def p_bore() -> Profile:
    """İç profil (gerçek koordinat): ağızda pah, iç omuzlar, delik yüzeyi x = 8'e iner."""
    return poly((0.0, 14.0), (-2.0, 12.0), (-15.0, 12.0), (-15.0, 10.0), (-30.0, 10.0), (-30.0, 8.0))


# ------------------------------------------------------------------ yol ayrıştırma (z, x)


def zx(p) -> np.ndarray:
    """(x, y, z) → (z, x)."""
    return np.array([p[2], p[0]], dtype=float)


def moves_zx(tp: Toolpath):
    """[(tip, a, b, merkez, feed)] (z, x) koordinatında; merkez (x, z) → (z, x)."""
    out = []
    a = zx(tp.start)
    for m in tp.moves:
        b = zx(m.end)
        c = None if m.center is None else np.array([m.center[1], m.center[0]], dtype=float)
        out.append((m.type, a, b, c, m.feed))
        a = b
    return out


def arc_form(a, b, c, ccw: bool):
    """(R, θ0, süpürme) saat yönü tersi biçimde; (z, x) düzleminde G3 = ccw."""
    return arc_ccw_form(a, b, c, cw=not ccw)


def sample_move(t, a, b, c, step: float = 0.05) -> np.ndarray:
    if t in YAY:
        ccw = t is MoveType.ARC_CCW
        R, _, sw = arc_form(a, b, c, ccw)
        n = max(2, int(math.ceil(R * sw / step)) + 1)
        th0 = math.atan2(a[1] - c[1], a[0] - c[0])
        th = th0 + (1.0 if ccw else -1.0) * sw * np.linspace(0.0, 1.0, n)
        return np.column_stack([c[0] + R * np.cos(th), c[1] + R * np.sin(th)])
    L = float(np.hypot(*(b - a)))
    n = max(2, int(math.ceil(L / step)) + 1)
    s = np.linspace(0.0, 1.0, n)
    return a[None, :] + s[:, None] * (b - a)[None, :]


def sample_path(tp: Toolpath, types=None, step: float = 0.05) -> np.ndarray:
    pts = [sample_move(t, a, b, c, step) for t, a, b, c, _ in moves_zx(tp) if types is None or t in types]
    return np.vstack(pts)


def profile_curves(prof: Profile) -> Egriler:
    e = Egriler()
    for s in prof.segments:
        if isinstance(s, Arc):
            R, th0, sw = arc_ccw_form(s.p0, s.p1, s.c, cw=not s.ccw)
            e.arc(s.c, R, th0, sw)
        else:
            e.line(s.p0, s.p1)
    return e


def path_curves(tp: Toolpath, shift, types=KESME) -> Egriler:
    """Yol hareketleri (z, x) düzleminde, shift kadar kaydırılmış (burun merkezi: shift = −q)."""
    shift = np.asarray(shift, dtype=float)
    e = Egriler()
    for t, a, b, c, _ in moves_zx(tp):
        if t not in types:
            continue
        if t in YAY:
            R, th0, sw = arc_form(a, b, c, t is MoveType.ARC_CCW)
            e.arc(c + shift, R, th0, sw)
        elif float(np.hypot(*(b - a))) > 0:
            e.line(a + shift, b + shift)
    return e


def close(p, q, tol: float = TOL) -> bool:
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol


def axial_cuts(tp: Toolpath, z_front: float):
    """Ön düzlemden (P_z = z_front) başlayan −Z yönlü G1 pasoları, sırasıyla: [(indis, a, b)]."""
    out = []
    for i, (t, a, b, _, _) in enumerate(moves_zx(tp)):
        if t is MoveType.LINEAR and abs(a[1] - b[1]) <= TOL and b[0] < a[0] and abs(a[0] - z_front) <= TOL:
            out.append((i, a, b))
    return out


def expected_moves(segs) -> list[tuple]:
    """tip_path parçaları → beklenen hareketler [(tip, bitiş (z, x), merkez (z, x) | None)]."""
    out = []
    for s in segs:
        if isinstance(s, Arc):
            out.append((MoveType.ARC_CCW if s.ccw else MoveType.ARC_CW, s.p1, s.c))
        else:
            out.append((MoveType.LINEAR, s.p1, None))
    return out


def match_segments(tp: Toolpath, segs) -> int:
    """Yolda tip_path parçalarıyla birebir eşleşen pencerenin ilk hareket indisi; yoksa AssertionError."""
    mv = moves_zx(tp)
    exp = expected_moves(segs)
    for i in range(len(mv) - len(exp) + 1):
        if not close(mv[i][1], segs[0].p0):
            continue
        ok = True
        for (t, _, b, c, _), (te, be, ce) in zip(mv[i : i + len(exp)], exp, strict=True):
            if t is not te or not close(b, be) or (ce is not None and not close(c, ce)):
                ok = False
                break
        if ok:
            return i
    raise AssertionError("yolda tip_path ile birebir eşleşen kontur pasosu yok")


def concave_corners(prof: Profile, side: str = "dis") -> list[tuple[np.ndarray, float]]:
    """Keskin içbükey köşeler: (V, θ) — θ köşenin malzeme dışından görülen iç açısı."""
    sgn = 1.0 if side == "dis" else -1.0  # iç tarafta ayna: dönüş yönü ters
    out = []
    for s1, s2 in zip(prof.segments[:-1], prof.segments[1:], strict=True):
        t1, t2 = s1.tangent(1.0), s2.tangent(0.0)
        k = sgn * (t1[0] * t2[1] - t1[1] * t2[0])
        if k < -1e-9:
            turn_angle = math.acos(float(np.clip(np.dot(t1, t2), -1.0, 1.0)))
            out.append((s1.p1, math.pi - turn_angle))
    return out


def profile_samples(prof: Profile, step: float = 0.02) -> np.ndarray:
    pts = []
    for s in prof.segments:
        n = max(2, int(math.ceil(s.length / step)) + 1)
        pts += [s.point(float(t)) for t in np.linspace(0.0, 1.0, n)]
    return np.array(pts)


# ------------------------------------------------------------------ K7 TurnCut


def test_k7_gecerli():
    c = TurnCut(feed=0.2, rpm=2000.0, css=180.0, a_p=2.0, clearance=1.5, retract=0.3)
    assert (c.feed, c.rpm, c.css, c.a_p, c.clearance, c.retract) == (0.2, 2000.0, 180.0, 2.0, 1.5, 0.3)
    c = TurnCut(feed=0.1, rpm=800.0)
    assert c.css is None and c.a_p is None and c.clearance == 1.0 and c.retract == 0.5


@pytest.mark.parametrize(
    "kw",
    [
        {"feed": 0.0},
        {"feed": -0.1},
        {"rpm": 0.0},
        {"rpm": -100.0},
        {"css": 0.0},
        {"css": -5.0},
        {"a_p": 0.0},
        {"a_p": -1.0},
        {"clearance": 0.0},
        {"clearance": -1.0},
        {"retract": 0.0},
        {"retract": -0.5},
        {"feed": math.nan},
        {"feed": math.inf},
        {"rpm": math.nan},
        {"css": math.inf},
        {"a_p": math.nan},
        {"clearance": math.inf},
        {"retract": math.nan},
    ],
)
def test_k7_hatali(kw):
    args = {"feed": 0.2, "rpm": 2000.0, "css": None, "a_p": 2.0, "clearance": 1.0, "retract": 0.5} | kw
    with pytest.raises(CamError):
        TurnCut(**args)


def test_k7_a_p_zorunlu():
    c = cut(a_p=None)
    with pytest.raises(CamError):
        face(STOCK, ttool(), c, z_face=-1.0)
    with pytest.raises(CamError):
        turn(STOCK, ttool(), c, x_final=20.0, z_end=-30.0)
    with pytest.raises(CamError):
        rough(p_shoulder(), STOCK, ttool(), c, allowance=DELTA)


# ------------------------------------------------------------------ K8 face


def face_passes(tp: Toolpath):
    """−X yönlü G1 alın pasoları [(a, b)] (z sabit)."""
    return [
        (a, b)
        for t, a, b, _, _ in moves_zx(tp)
        if t is MoveType.LINEAR and abs(a[0] - b[0]) <= TOL and b[1] < a[1]
    ]


@pytest.mark.parametrize(
    ("zmax", "z_face", "a_p", "n"),
    [(2.0, 0.0, 0.8, 3), (2.0, 0.0, 0.5, 4), (0.9, 0.0, 0.3, 3), (1.0, -0.5, 2.0, 1)],
)
def test_k8_face_paso_sayisi_ve_duzlemler(zmax, z_face, a_p, n):
    stock = CylinderStock(D=50.0, zmin=-100.0, zmax=zmax)
    tool = ttool()
    c = cut(a_p=a_p)
    tp = face(stock, tool, c, z_face=z_face)
    passes = face_passes(tp)
    assert len(passes) == n
    H = zmax - z_face
    q = q_of(tool)
    for i, (a, b) in enumerate(passes, start=1):
        z_i = z_face if i == n else zmax - i * H / n
        assert a[0] == pytest.approx(z_i, abs=TOL)  # T = 3: P_z = C_z − r = z_i
        assert a[1] == pytest.approx(stock.D / 2 + c.clearance + R_NOSE + q[1], abs=TOL)  # güvenli yarıçaptan
        assert b[1] == pytest.approx(0.0 + q[1], abs=TOL)  # dolu çubuk: C_x = 0, P_x = −r
    assert abs(passes[-1][0][0] - z_face) <= TOL


def test_k8_face_dolu_cubuk_t3_eksene_iner():
    tp = face(STOCK, ttool(), cut(a_p=1.0), z_face=-2.0)
    for _, b in face_passes(tp):
        assert b[1] == pytest.approx(-R_NOSE, abs=TOL)


@pytest.mark.parametrize("tip", [3, 0])
def test_k8_face_boru(tip):
    tool = ttool(tip=tip)
    c = cut(a_p=1.0, clearance=1.0)
    tp = face(TUBE, tool, c, z_face=-2.0)
    x_son = max(0.0, TUBE.d / 2 - c.clearance)  # burun merkezi C_x
    passes = face_passes(tp)
    assert len(passes) == 2
    for _, b in passes:
        assert b[1] == pytest.approx(x_son + q_of(tool)[1], abs=TOL)


def test_k8_face_kalin_boru_x_son_sifir():
    stock = CylinderStock(D=50.0, zmin=-100.0, zmax=0.0, d=1.0)  # d/2 − cl < 0 → 0
    tp = face(stock, ttool(tip=0), cut(a_p=1.0), z_face=-1.0)
    for _, b in face_passes(tp):
        assert b[1] == pytest.approx(0.0, abs=TOL)


@pytest.mark.parametrize("z_face", [0.0, 1.0, -100.0, -120.0])
def test_k8_face_hatali_z_face(z_face):
    with pytest.raises(CamError):
        face(STOCK, ttool(), cut(a_p=1.0), z_face=z_face)


@pytest.mark.parametrize(
    "tool",
    [ttool(tip=2), ttool(tip=4), ttool(kind=BORE, tip=3), gtool()],
    ids=["uc2", "uc4", "bore", "kanal"],
)
def test_k8_face_hatali_takim(tool):
    with pytest.raises(CamError):
        face(STOCK, tool, cut(a_p=1.0), z_face=-1.0)


# ------------------------------------------------------------------ K9 turn


def test_k9_turn_dis():
    stock = CylinderStock(D=40.0, zmin=-100.0, zmax=0.0)  # X_s = 20
    tool = ttool()
    c = cut(a_p=2.5, retract=0.5)
    X_f, z_end = 14.0, -30.0
    tp = turn(stock, tool, c, x_final=X_f, z_end=z_end)
    H = 20.0 - X_f
    n = math.ceil(H / 2.5)  # 3
    z_front = stock.zmax + c.clearance  # P_z = C_z − r
    cuts = axial_cuts(tp, z_front)
    assert len(cuts) == n  # n − 1 boyuna paso + kontur girişi
    mv = moves_zx(tp)
    for k, (i, a, b) in enumerate(cuts[:-1], start=1):
        x_k = 20.0 - k * H / n
        assert a[1] == pytest.approx(x_k, abs=TOL)
        assert b[0] == pytest.approx(z_end, abs=TOL)  # T = 3: P_z = z_end
        # 45° geri çekilme (+e, +e)
        t, a2, b2, _, f = mv[i + 1]
        assert t is MoveType.LINEAR and f == c.feed
        assert close(b2 - a2, (c.retract, c.retract))
    # kontur pasosu: X_f'de z_end'e, sonra omuzda +X güvenli yarıçapa
    i0 = cuts[-1][0]
    assert cuts[-1][1][1] == pytest.approx(X_f, abs=TOL)
    rest = mv[i0:]
    j_g0 = next(j for j, m in enumerate(rest) if m[0] is MoveType.RAPID)
    kontur = rest[:j_g0]
    assert all(m[0] is MoveType.LINEAR for m in kontur)
    for _, _, b, _, _ in kontur:
        on_cyl = abs(b[1] - X_f) <= TOL and b[0] >= z_end - TOL
        on_shoulder = abs(b[0] - z_end) <= TOL and X_f - TOL <= b[1] <= 20.0 + c.clearance + TOL
        assert on_cyl or on_shoulder, f"kontur dışı nokta {b}"
    assert any(close(b, (z_end, X_f)) for _, _, b, _, _ in kontur)
    assert close(kontur[-1][2], (z_end, 20.0 + c.clearance))  # C_x = X_s + cl + r → P_x = X_s + cl


def test_k9_turn_ic_boru():
    tool = ttool(kind=BORE, tip=2, r=0.4)
    c = cut(a_p=2.5)
    X_f, z_end = 16.0, -25.0  # delik yarıçapı 8 → 16
    tp = turn(TUBE, tool, c, x_final=X_f, z_end=z_end, side="ic")
    H = X_f - TUBE.d / 2  # aynada X_s − X_f
    n = math.ceil(H / 2.5)  # 4
    z_front = TUBE.zmax + c.clearance  # T = 2: q_z = −r
    cuts = axial_cuts(tp, z_front)
    assert len(cuts) == n
    for k, (_, a, b) in enumerate(cuts[:-1], start=1):
        assert a[1] == pytest.approx(TUBE.d / 2 + k * H / n, abs=TOL)
        assert b[0] == pytest.approx(z_end, abs=TOL)
    assert cuts[-1][1][1] == pytest.approx(X_f, abs=TOL)
    pts = [b for _, _, b, _, _ in moves_zx(tp)]
    assert any(close(b, (z_end, X_f)) for b in pts)


@pytest.mark.parametrize(
    ("kw", "stock"),
    [
        ({"x_final": 25.0, "z_end": -30.0}, STOCK),  # x_final = D/2
        ({"x_final": -1.0, "z_end": -30.0}, STOCK),
        ({"x_final": 20.0, "z_end": 0.0}, STOCK),  # z_end = zmax
        ({"x_final": 20.0, "z_end": -101.0}, STOCK),
        ({"x_final": 8.0, "z_end": -30.0, "side": "ic"}, TUBE),  # x_final = d/2
        ({"x_final": 30.0, "z_end": -30.0, "side": "ic"}, TUBE),
        ({"x_final": 10.0, "z_end": -30.0, "side": "ic"}, STOCK),  # dolu çubukta iç işlem
        ({"x_final": 20.0, "z_end": -30.0, "side": "yan"}, STOCK),
    ],
)
def test_k9_turn_hatali_girdi(kw, stock):
    tool = ttool(kind=BORE, tip=2, r=0.4) if kw.get("side") == "ic" else ttool()
    with pytest.raises(CamError):
        turn(stock, tool, cut(a_p=2.0), **kw)


def test_k9_turn_hatali_takim():
    with pytest.raises(CamError):
        turn(STOCK, ttool(kind=BORE, tip=3), cut(a_p=2.0), x_final=20.0, z_end=-30.0)
    with pytest.raises(CamError):
        turn(TUBE, ttool(tip=2), cut(a_p=2.0), x_final=12.0, z_end=-30.0, side="ic")
    with pytest.raises(CamError):
        turn(STOCK, ttool(tip=8), cut(a_p=2.0), x_final=20.0, z_end=-30.0)


# ------------------------------------------------------------------ K10 rough


def rough_levels(x_low: float, X_s: float, a_p: float) -> tuple[int, list[float]]:
    H = X_s - x_low
    n = math.ceil(H / a_p - 1e-9)
    return n, [X_s - k * H / n for k in range(1, n)]


def test_k10_rough_omuzlu_mil_paso_uclari():
    tool = ttool()
    c = cut(a_p=3.0)
    tp = rough(p_shoulder(), STOCK, tool, c, allowance=DELTA)
    rho = R_NOSE + DELTA
    n, levels = rough_levels(10.0 + DELTA, 25.0, 3.0)
    assert n == 5
    cuts = axial_cuts(tp, STOCK.zmax + c.clearance)
    assert len(cuts) == n
    for (_, a, b), x_k in zip(cuts[:-1], levels, strict=True):
        C_x = x_k + R_NOSE
        assert min(abs(C_x - 16.0), abs(C_x - (16.0 + rho))) > 0.05  # seviye geçiş noktalarında değil
        if C_x < 16.0:  # ilk omuz duvarının ofseti z = −20 + ρ
            C_z = -20.0 + rho
        elif C_x < 16.0 + rho:  # omuz üst köşesinin (−20, 16) ρ yarıçaplı yayı
            C_z = -20.0 + math.sqrt(rho**2 - (C_x - 16.0) ** 2)
        else:  # ikinci duvarın ofseti z = −40 + ρ
            C_z = -40.0 + rho
        assert a[1] == pytest.approx(x_k, abs=TOL)
        assert b[0] == pytest.approx(C_z - R_NOSE, abs=TOL)


def test_k10_rough_koni_paso_uclari():
    tool = ttool()
    c = cut(a_p=3.0)
    tp = rough(p_cone(), STOCK, tool, c, allowance=DELTA)
    rho = R_NOSE + DELTA
    zc, xc, a_, zw = CONE["zc"], CONE["xc"], CONE["a"], CONE["zw"]
    n, levels = rough_levels(12.0 + DELTA, 25.0, 3.0)
    assert n == 5
    x_top = xc + math.tan(a_) * (
        zc - (zw + rho) + rho / math.sin(a_)
    )  # koni ofseti ile duvar ofseti kesişimi
    cuts = axial_cuts(tp, STOCK.zmax + c.clearance)
    assert len(cuts) == n
    for (_, a, b), x_k in zip(cuts[:-1], levels, strict=True):
        C_x = x_k + R_NOSE
        assert xc + rho < C_x < x_top  # seviye koni ofsetini kesiyor
        C_z = zc - (C_x - xc) / math.tan(a_) + rho / math.sin(a_)
        assert a[1] == pytest.approx(x_k, abs=TOL)
        assert b[0] == pytest.approx(C_z - R_NOSE, abs=TOL)


@pytest.mark.parametrize("prof_fn", [p_shoulder, p_cone, p_arc], ids=["omuz", "koni", "yay"])
def test_k10_rough_kontur_pasosu_tip_path_ile_birebir(prof_fn):
    tool = ttool()
    c = cut(a_p=3.0)
    prof = prof_fn()
    tp = rough(prof, STOCK, tool, c, allowance=DELTA)
    segs = tip_path(prof, tool, allowance=DELTA, strict=False)
    i = match_segments(tp, segs)
    mv = moves_zx(tp)
    # giriş: G0 F → G1 C0 (F = (max(z_max + cl + r, C0_z), C0_x))
    q = q_of(tool)
    C0 = segs[0].p0 - q
    F = np.array([max(STOCK.zmax + c.clearance + R_NOSE, C0[0]), C0[1]])
    if not close(F, C0):
        t, a, b, _, _ = mv[i - 1]
        assert t is MoveType.LINEAR and close(a, F + q) and close(b, C0 + q)
        assert mv[i - 2][0] is MoveType.RAPID
    else:
        assert mv[i - 1][0] is MoveType.RAPID
    # çıkış: son noktadan +X yönünde G1 güvenli yarıçapa, sonra G0 A'ya
    t, a, b, _, _ = mv[i + len(segs)]
    assert t is MoveType.LINEAR
    assert b[0] == pytest.approx(a[0], abs=TOL) and b[1] > a[1]
    assert b[1] == pytest.approx(STOCK.D / 2 + c.clearance + R_NOSE + q[1], abs=TOL)
    assert mv[-1][0] is MoveType.RAPID and close(mv[-1][2], p_A(STOCK, tool, c))


def test_k10_rough_disbukey_yay_kontur_yaricapi():
    tool = ttool()
    tp = rough(p_arc(), STOCK, tool, cut(a_p=3.0), allowance=DELTA)
    beklenen_c = np.array([-3.0, 17.0]) + q_of(tool)
    bulunan = [(t, a, c) for t, a, b, c, _ in moves_zx(tp) if t in YAY and close(c, beklenen_c)]
    assert len(bulunan) == 1
    t, a, c = bulunan[0]
    assert t is MoveType.ARC_CCW
    assert float(np.hypot(*(a - c))) == pytest.approx(3.0 + DELTA + R_NOSE, abs=TOL)


@pytest.mark.parametrize(
    "prof",
    [
        poly((0.0, 10.0), (-10.0, 10.0), (-20.0, 9.0), (-20.0, 25.0)),  # monoton değil
        poly((-5.0, 10.0), (-20.0, 10.0), (-20.0, 25.0)),  # başlangıç z < z_max
        poly((0.0, 10.0), (-20.0, 10.0), (-20.0, 22.0)),  # son x < X_s
        poly((0.0, 25.0), (-20.0, 25.0), (-20.0, 26.0)),  # H ≤ 0
    ],
    ids=["monoton_degil", "baslangic_z", "son_x", "H_sifir"],
)
def test_k10_rough_on_kosullar(prof):
    with pytest.raises(CamError):
        rough(prof, STOCK, ttool(), cut(a_p=3.0), allowance=DELTA)


def test_k10_rough_hatali_girdi():
    with pytest.raises(CamError):
        rough(p_shoulder(), STOCK, ttool(), cut(a_p=3.0), allowance=-0.1)
    with pytest.raises(CamError):
        rough(p_shoulder(), STOCK, ttool(kappa=60.0), cut(a_p=3.0))  # 90° omuza erişemez
    with pytest.raises(CamError):
        rough(p_shoulder(), STOCK, ttool(kind=BORE), cut(a_p=3.0))
    with pytest.raises(CamError):
        rough(p_shoulder(), STOCK, ttool(), cut(a_p=3.0), side="yan")


# ------------------------------------------------------------------ K11 finish


def test_k11_finish_tip_path_ile_birebir():
    tool = ttool()
    c = cut(a_p=None)
    prof = p_finish()
    tp = finish(prof, STOCK60, tool, c)
    segs = tip_path(prof, tool)
    i = match_segments(tp, segs)
    mv = moves_zx(tp)
    q = q_of(tool)
    C0 = segs[0].p0 - q
    F = np.array([max(STOCK60.zmax + c.clearance + R_NOSE, C0[0]), C0[1]])
    assert not close(F, C0)
    t, a, b, _, _ = mv[i - 1]
    assert t is MoveType.LINEAR and close(a, F + q) and close(b, C0 + q)
    assert mv[i - 2][0] is MoveType.RAPID and close(mv[i - 2][2], F + q)
    t, a, b, _, _ = mv[i + len(segs)]
    assert t is MoveType.LINEAR and b[0] == pytest.approx(a[0], abs=TOL)
    assert b[1] == pytest.approx(STOCK60.D / 2 + c.clearance + R_NOSE + q[1], abs=TOL)
    assert mv[-1][0] is MoveType.RAPID and close(mv[-1][2], p_A(STOCK60, tool, c))


def test_k11_finish_g18_yay_yonleri():
    tool = ttool()
    tp = finish(p_finish(), STOCK60, tool, cut(a_p=None))
    arcs = [(m.type, m.center, np.array(m.end)) for m in tp.moves if m.type in YAY]
    # içbükey dolgu: cw → G2, merkez (x, z) = (12 − r, −15 − r), yarıçap R − r
    dolgu = [a for a in arcs if close(a[1], (12.0 - R_NOSE, -15.0 - R_NOSE))]
    assert len(dolgu) == 1 and dolgu[0][0] is MoveType.ARC_CW
    end = dolgu[0][2]
    assert math.hypot(end[0] - dolgu[0][1][0], end[2] - dolgu[0][1][1]) == pytest.approx(
        2.0 - R_NOSE, abs=TOL
    )
    # dışbükey köşe (−2, 10): V + q merkezli, r yarıçaplı G3
    kose = [a for a in arcs if close(a[1], (10.0 - R_NOSE, -2.0 - R_NOSE))]
    assert len(kose) == 1 and kose[0][0] is MoveType.ARC_CCW
    end = kose[0][2]
    assert math.hypot(end[0] - kose[0][1][0], end[2] - kose[0][1][1]) == pytest.approx(R_NOSE, abs=TOL)


def test_k11_finish_ic_tip_path_ile_birebir():
    tool = ttool(kind=BORE, tip=2, r=0.4)
    prof = p_bore()
    tp = finish(prof, TUBE, tool, cut(a_p=None), side="ic")
    match_segments(tp, tip_path(prof, tool, side="ic"))


def test_k11_finish_erisilemeyen_dolgu_hata():
    with pytest.raises(CamError):
        finish(p_finish(R_fil=0.5), STOCK60, ttool(), cut(a_p=None))


def test_k11_finish_dar_kanal_hata():
    with pytest.raises(CamError):
        finish(p_narrow_groove(), STOCK60, ttool(), cut(a_p=None))


def test_k11_finish_erisim_hata():
    with pytest.raises(CamError):
        finish(p_finish(), STOCK60, ttool(kappa=60.0), cut(a_p=None))


def test_k11_finish_hatali_takim():
    with pytest.raises(CamError):
        finish(p_finish(), STOCK60, ttool(kind=BORE, tip=3), cut(a_p=None))
    with pytest.raises(CamError):
        finish(p_bore(), TUBE, ttool(tip=2), cut(a_p=None), side="ic")
    with pytest.raises(CamError):
        finish(p_bore(), STOCK60, ttool(kind=BORE, tip=2, r=0.4), cut(a_p=None), side="ic")  # d = 0


# ------------------------------------------------------------------ K12 çakma yok, kalan malzeme yok


def gouge_cases():
    dis = ttool()
    ic = ttool(kind=BORE, tip=2, r=0.4)
    return {
        "kaba_omuz": (
            lambda: rough(p_shoulder(), STOCK, dis, cut(a_p=3.0), allowance=DELTA),
            p_shoulder(),
            dis,
            DELTA,
        ),
        "kaba_koni": (
            lambda: rough(p_cone(), STOCK, dis, cut(a_p=3.0), allowance=DELTA),
            p_cone(),
            dis,
            DELTA,
        ),
        "kaba_yay": (lambda: rough(p_arc(), STOCK, dis, cut(a_p=3.0), allowance=DELTA), p_arc(), dis, DELTA),
        "kaba_sifir_pay": (lambda: rough(p_cone(), STOCK, dis, cut(a_p=2.0)), p_cone(), dis, 0.0),
        "kaba_ic": (
            lambda: rough(p_bore(), TUBE, ic, cut(a_p=2.0), allowance=DELTA, side="ic"),
            p_bore(),
            ic,
            DELTA,
        ),
        "ince": (lambda: finish(p_finish(), STOCK60, dis, cut(a_p=None)), p_finish(), dis, 0.0),
        "ince_yay": (lambda: finish(p_arc(), STOCK, dis, cut(a_p=None)), p_arc(), dis, 0.0),
        "ince_ic": (lambda: finish(p_bore(), TUBE, ic, cut(a_p=None), side="ic"), p_bore(), ic, 0.0),
    }


@pytest.mark.parametrize("case", list(gouge_cases()))
def test_k12_cakma_yok(case):
    build, prof, tool, delta = gouge_cases()[case]
    tp = build()
    C = sample_path(tp) - q_of(tool)  # burun merkezi, G0 dahil bütün hareketler
    d = profile_curves(prof).distance(C)
    assert np.min(d) >= tool.nose_r + delta - 1e-9, f"en yakın {np.min(d)} < {tool.nose_r + delta}"


@pytest.mark.parametrize("case", ["ince", "ince_yay", "ince_ic"])
def test_k12_kalan_malzeme_yok(case):
    build, prof, tool, _ = gouge_cases()[case]
    side = "ic" if case.endswith("_ic") else "dis"
    tp = build()
    r = tool.nose_r
    P = profile_samples(prof)
    keep = np.ones(len(P), dtype=bool)
    for V, theta in concave_corners(prof, side):
        keep &= np.hypot(*(P - V).T) > r / math.tan(theta / 2) + 1e-9
    d = path_curves(tp, -q_of(tool)).distance(P[keep])
    assert np.max(d) <= r + 1e-9, f"en uzak {np.max(d)} > r = {r}"


# ------------------------------------------------------------------ K13 groove


def plunges(tp: Toolpath):
    """G1 dalışları [(a, b)]: z sabit, −X (dışta) veya +X (içte)."""
    return [(a, b) for t, a, b, _, _ in moves_zx(tp) if t is MoveType.LINEAR and abs(a[0] - b[0]) <= TOL]


@pytest.mark.parametrize("tip", [3, 4])
def test_k13_groove_dalis_sayisi_ve_konumlari(tip):
    w, r = 3.0, 0.2
    tool = gtool(tip=tip, w=w, r=r)
    c = cut(a_p=None)
    z_left, z_right, x_top, x_bottom = -20.0, -12.0, 25.0, 20.0
    tp = groove(STOCK, tool, c, z_left=z_left, z_right=z_right, x_top=x_top, x_bottom=x_bottom)
    W = z_right - z_left
    m = math.ceil((W - w) / (w - 2 * r)) + 1  # 3
    zL = [z_left + j * (W - w) / (m - 1) for j in range(m)]
    pl = plunges(tp)
    assert len(pl) == m
    for (a, b), z in zip(pl, zL, strict=True):  # z_left'ten z_right'a
        z_P = z if tip == 3 else z + w
        assert a[0] == pytest.approx(z_P, abs=TOL) and b[0] == pytest.approx(z_P, abs=TOL)
        assert b[1] == pytest.approx(x_bottom, abs=TOL)  # T = 3/4: P_x = C_x − r = x_bottom
        assert a[1] == pytest.approx(x_top + c.clearance, abs=TOL)


def test_k13_groove_taban_duz_ve_tasma_yok():
    w, r = 3.0, 0.2
    tool = gtool(tip=3, w=w, r=r)
    z_left, z_right, x_top, x_bottom = -20.0, -12.0, 25.0, 20.0
    tp = groove(STOCK, tool, cut(a_p=None), z_left=z_left, z_right=z_right, x_top=x_top, x_bottom=x_bottom)
    zLs = [b[0] for _, b in plunges(tp) if abs(b[1] - x_bottom) <= TOL]
    for z in np.linspace(z_left + r, z_right - r, 801):
        assert any(zL + r - TOL <= z <= zL + w - r + TOL for zL in zLs), f"taban z = {z} kesilmemiş"
    # takımın alt kenarı malzemenin içindeyken (P_x < x_top) takım [z_left, z_right] içinde
    P = sample_path(tp)
    inside = P[:, 1] < x_top - TOL
    assert np.any(inside)
    assert np.all(P[inside, 0] >= z_left - TOL)
    assert np.all(P[inside, 0] + w <= z_right + TOL)


def test_k13_groove_tek_dalis():
    tool = gtool(tip=3, w=3.0, r=0.2)
    tp = groove(STOCK, tool, cut(a_p=None), z_left=-15.0, z_right=-12.0, x_top=25.0, x_bottom=22.0)
    pl = plunges(tp)
    assert len(pl) == 1
    assert close(pl[0][1], (-15.0, 22.0))


def test_k13_groove_tam_bolunen_aralik():
    # (W − w)/(w − 2r) = 2/2 = 1 tam → m = 2
    tool = gtool(tip=3, w=3.0, r=0.5)
    tp = groove(STOCK, tool, cut(a_p=None), z_left=-20.0, z_right=-15.0, x_top=25.0, x_bottom=22.0)
    zs = [b[0] for _, b in plunges(tp)]
    assert len(zs) == 2
    assert zs[0] == pytest.approx(-20.0, abs=TOL) and zs[1] == pytest.approx(-18.0, abs=TOL)


def test_k13_groove_ic():
    tool = gtool(tip=2, w=3.0, r=0.2)
    stock = CylinderStock(D=60.0, zmin=-100.0, zmax=0.0, d=20.0)
    tp = groove(stock, tool, cut(a_p=None), z_left=-20.0, z_right=-12.0, x_top=10.0, x_bottom=13.0, side="ic")
    pl = plunges(tp)
    assert len(pl) == 3
    for (_, b), z in zip(pl, [-20.0, -17.5, -15.0], strict=True):
        assert close(b, (z, 13.0))


@pytest.mark.parametrize(
    ("tool", "kw"),
    [
        (gtool(), {"z_left": -20.0, "z_right": -18.0}),  # W < w
        (gtool(), {"x_bottom": 25.0}),  # x_bottom ≥ x_top
        (gtool(), {"x_bottom": 26.0}),
        (gtool(), {"x_top": 5.0, "x_bottom": -1.0}),  # x_bottom < 0
        (gtool(w=3.0, r=1.5), {}),  # tam yarıçaplı uç, W > w
        (ttool(), {}),  # tornalama ucu
        (gtool(tip=2), {}),  # dışta uç 2
        (gtool(), {"side": "ic"}),  # dolu çubukta iç kanal
    ],
    ids=[
        "W_kucuk",
        "taban_ust",
        "taban_ustunde",
        "taban_negatif",
        "tam_yaricap",
        "torna_ucu",
        "uc2",
        "ic_dolu",
    ],
)
def test_k13_groove_hatali_girdi(tool, kw):
    args = {"z_left": -20.0, "z_right": -12.0, "x_top": 25.0, "x_bottom": 20.0} | kw
    with pytest.raises(CamError):
        groove(STOCK, tool, cut(a_p=None), **args)


def test_k13_groove_tam_yaricap_tek_dalis_gecerli():
    tool = gtool(w=3.0, r=1.5)
    tp = groove(STOCK, tool, cut(a_p=None), z_left=-15.0, z_right=-12.0, x_top=25.0, x_bottom=22.0)
    assert len(plunges(tp)) == 1


# ------------------------------------------------------------------ K16 genel yol kuralları


def op_cases():
    """ad → (yolu üreten fonksiyon, ham malzeme, takım, kesme, taraf, kesme ilerlemesi, varsayılan ad)."""
    dis, ic = ttool(), ttool(kind=BORE, tip=2, r=0.4)
    gr = gtool()
    th = LatheTool(id=3, name="D", kind=THREAD, nose_r=0.1, tip=8, kappa_r=60.0, eps_r=60.0)
    c3, c25, cf, ct = cut(a_p=1.0), cut(a_p=2.5), cut(a_p=None), cut(a_p=None, css=None)
    return {
        "alin": (lambda: face(STOCK, dis, c3, z_face=-2.0), STOCK, dis, c3, "dis", 0.2, "alin"),
        "alin_boru": (lambda: face(TUBE, dis, c3, z_face=-2.0), TUBE, dis, c3, "dis", 0.2, "alin"),
        "boy": (lambda: turn(STOCK, dis, c25, x_final=18.0, z_end=-30.0), STOCK, dis, c25, "dis", 0.2, "boy"),
        "boy_ic": (
            lambda: turn(TUBE, ic, c25, x_final=16.0, z_end=-25.0, side="ic"),
            TUBE,
            ic,
            c25,
            "ic",
            0.2,
            "boy",
        ),
        "kaba": (
            lambda: rough(p_shoulder(), STOCK, dis, c25, allowance=DELTA),
            STOCK,
            dis,
            c25,
            "dis",
            0.2,
            "kaba",
        ),
        "kaba_ic": (
            lambda: rough(p_bore(), TUBE, ic, c25, allowance=DELTA, side="ic"),
            TUBE,
            ic,
            c25,
            "ic",
            0.2,
            "kaba",
        ),
        "ince": (lambda: finish(p_finish(), STOCK60, dis, cf), STOCK60, dis, cf, "dis", 0.2, "ince"),
        "ince_ic": (lambda: finish(p_bore(), TUBE, ic, cf, side="ic"), TUBE, ic, cf, "ic", 0.2, "ince"),
        "kanal": (
            lambda: groove(STOCK, gr, cf, z_left=-20.0, z_right=-12.0, x_top=25.0, x_bottom=20.0),
            STOCK,
            gr,
            cf,
            "dis",
            0.2,
            "kanal",
        ),
        "dis": (
            lambda: thread(
                STOCK, th, ct, z_start=3.0, z_end=-20.0, x0=25.0, pitch=1.5, depth=0.92, first=0.3
            ),
            STOCK,
            th,
            ct,
            "dis",
            1.5,
            "dis",
        ),
    }


OP_NAMES = ["alin", "alin_boru", "boy", "boy_ic", "kaba", "kaba_ic", "ince", "ince_ic", "kanal", "dis"]


@pytest.mark.parametrize("case", OP_NAMES)
def test_k16_genel_yol_kurallari(case):
    build, stock, tool, c, side, feed, ad = op_cases()[case]
    tp = build()
    assert isinstance(tp, Toolpath)
    assert tp.name == ad
    assert tp.tool is tool
    assert tp.plane is Plane.ZX
    assert tp.feed_mode is FeedMode.PER_REV
    assert tp.css == c.css and tp.rpm == c.rpm
    tp.validate()
    assert len(tp.moves) > 0
    PA = p_A(stock, tool, c, side)
    assert tp.start[1] == 0.0
    assert close(zx(tp.start), PA), f"başlangıç {tp.start} ≠ P_A {PA}"
    assert close(zx(tp.moves[-1].end), PA)
    p0 = np.array(tp.start)
    for m in tp.moves:
        assert m.end[1] == 0.0
        assert float(np.linalg.norm(np.array(m.end) - p0)) > TOL, "sıfır boylu hareket"
        if m.type is MoveType.RAPID:
            assert m.feed is None and m.center is None
        else:
            assert m.feed == pytest.approx(feed, rel=1e-12)
        if m.type in YAY:
            assert m.center is not None and len(m.center) == 2
            cz = np.array([m.center[1], m.center[0]])
            assert abs(np.hypot(*(zx(p0) - cz)) - np.hypot(*(zx(m.end) - cz))) <= 1e-9
        else:
            assert m.center is None
        p0 = np.array(m.end)


def test_k16_ozel_ad():
    tp = face(STOCK, ttool(), cut(a_p=1.0), z_face=-1.0, name="on_alin")
    assert tp.name == "on_alin"


# ------------------------------------------------------------------ uç kapakları (SPEC 20 eki)
# Profilin son parçası (z = −35'teki 1 mm duvar) ρ = r + δ = 1.1'den kısa: kaba çevrimde bu parçanın
# ofseti tamamen silinir ve kontur, silindir ofsetinin son nokta merkezli ρ kapağıyla kesiştiği yerde biter;
# ardından SPEC'teki gibi +X yönünde G1 güvenli yarıçapa çıkılır.

END_CAP_Z = -35.0 + math.sqrt((R_NOSE + DELTA) ** 2 - 0.1**2)  # −33.904555...
STOCK32 = CylinderStock(D=32.0, zmin=-50.0, zmax=0.0)  # X_s = 16


def short_wall_profile() -> Profile:
    return poly((0.0, 10.0), (-20.0, 10.0), (-20.0, 15.0), (-35.0, 15.0), (-35.0, 16.0))


def test_uc_kapagi_kaba_cakma_yok():
    tool = ttool()
    prof = short_wall_profile()
    tp = rough(prof, STOCK32, tool, cut(a_p=2.0), allowance=DELTA)
    C = sample_path(tp, types=KESME) - q_of(tool)
    d = profile_curves(prof).distance(C)
    assert np.min(d) >= R_NOSE + DELTA - 1e-9, f"en yakın {np.min(d)} < r + δ"


def test_uc_kapagi_kaba_kontur_kapakta_biter():
    tool = ttool()
    c = cut(a_p=2.0)
    tp = rough(short_wall_profile(), STOCK32, tool, c, allowance=DELTA)
    mv = moves_zx(tp)
    q = q_of(tool)
    kesme = [i for i, m in enumerate(mv) if m[0] in KESME]
    # sondan bir önceki kesme hareketi kontur pasosunun sonu: kapakla kesişim
    kontur_son = mv[kesme[-2]]
    assert kontur_son[2][0] == pytest.approx(END_CAP_Z + q[0], abs=TOL)
    assert kontur_son[2][1] == pytest.approx(16.1 + q[1], abs=TOL)
    # son kesme hareketi: aynı z'de +X yönünde G1, güvenli yarıçapa (C_x = X_s + cl + r)
    t, a, b, _, _ = mv[kesme[-1]]
    assert kesme[-1] == kesme[-2] + 1
    assert t is MoveType.LINEAR
    assert close(a, kontur_son[2])
    assert b[0] == pytest.approx(END_CAP_Z + q[0], abs=TOL)
    assert b[1] == pytest.approx(STOCK32.D / 2 + c.clearance + R_NOSE + q[1], abs=TOL)
    # sonrasında sadece G0
    assert all(m[0] is MoveType.RAPID for m in mv[kesme[-1] + 1 :])


def test_uc_kapagi_ince_degismez():
    tool = ttool()
    prof = short_wall_profile()
    tp = finish(prof, STOCK32, tool, cut(a_p=None))
    segs = tip_path(prof, tool)
    match_segments(tp, segs)
    assert close(segs[-1].p1 - q_of(tool), (-35.0 + R_NOSE, 16.0))  # burun merkezi son noktası
    C = sample_path(tp) - q_of(tool)
    assert np.min(profile_curves(prof).distance(C)) >= R_NOSE - 1e-9
