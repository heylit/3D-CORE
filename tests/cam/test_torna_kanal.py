"""SPEC 40 C — profilli kanal (Recess) testleri (K11–K13).

Testler yalnız SPEC 40 metninden ve sabit arayüzlerden (cam/model.py, cam/torna_ek.py imzaları, SPEC 20
cam.lathe / cam.lathe_ops kuralları) yazıldı; uygulama gövdesi okunmadı. Geometri uydurmadır.

Çerçeve (u, v) = (z, x); kanal ucu genişliği w, burun yarıçapı r, a = w − 2r, ρ = r + δ.
C_L sol burun merkezi, C_R = C_L + (a, 0). Zarf h_ρ(z_L) = max_{s∈[0,a]} g(z_L + s).

Kapalı formlar (dış taraf, x_top = 20):
- T5: yarım daire taban R = 3, merkez (30, 17); w = 4, r = 2 (a = 0): g = 17 − √(1 − (z − 30)²),
  zarf tek yay merkez (30, 17) yarıçap 1, z_L ∈ [29, 31]; e_max = 0.
- T6: aynı taban, w = 4, r = 0,4 (a = 3,2): zarf iki yay, yarıçap 2,6, merkezler (30, 17) ve (26,8; 17),
  geçiş z_L = 28,4, h = 17 − √4,2; e_max = (R − r) − √((R − r)² − (a/2)²) = 2,6 − √4,2.
- T7: yamuk (35,20)→(32,17)→(28,17)→(25,20), w = 3, r = 0,2 (a = 2,6), s = ρ√2:
  h_ρ(z_L) = max(17 + ρ, 45 + s − z_L, z_L + a − 15 + s); C_R ön yanakta x − z = −15 + s;
  taban C_x = 17 + ρ, C_R,z ∈ [28 − ρ + s + a, 32 + ρ − s] → r = 0,2: [30,68284…, 31,91716…]; e_max = 0.
Programlanan nokta (SPEC 20 kanal kuralı): T3 → P = C_L + (−r, −r), T4 → P = C_R + (r, −r);
içte T2 / T1 (x → −x aynası).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.geom2d import distance, intersect
from cam.lathe import mirror_tip, tip_offset
from cam.lathe_ops import TurnCut
from cam.model import (
    CamError,
    CylinderStock,
    FeedMode,
    LatheTool,
    LatheToolKind,
    MoveType,
    Plane,
    Toolpath,
)
from cam.profile import Arc, Line, Profile
from cam.torna_ek import recess_envelope, recess_finish, recess_rest, recess_rough

TOL = 1e-9
G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
S2 = math.sqrt(2.0)

BAR = CylinderStock(D=40.0, zmin=0.0, zmax=60.0)  # X_s = 20 = x_top
TUBE = CylinderStock(D=60.0, zmin=0.0, zmax=60.0, d=40.0)  # iç: delik yarıçapı 20 = x_top
CUT = TurnCut(feed=0.05, rpm=800.0, clearance=1.0)
X_TOP = 20.0


def _tool(w: float, r: float, tip: int = 3, kind=LatheToolKind.GROOVE) -> LatheTool:
    return LatheTool(
        id=4, name=f"K{w}", kind=kind, nose_r=r, tip=tip, kappa_r=90.0, eps_r=90.0, width=w, edge_len=8.0
    )


def _t5_profile() -> Profile:
    return Profile(
        [
            Line((33.0, 20.0), (33.0, 17.0)),
            Arc((33.0, 17.0), (27.0, 17.0), (30.0, 17.0), ccw=False),  # (30, 14)'ten geçer
            Line((27.0, 17.0), (27.0, 20.0)),
        ],
        closed=False,
    )


def _t7_profile() -> Profile:
    return Profile.polygon([(35, 20), (32, 17), (28, 17), (25, 20)], closed=False)


def _mirror_about(p: Profile, x0: float) -> Profile:
    """x → 2·x0 − x aynası (iç kanal girdisi); yaylar yön değiştirir."""
    out = []
    for s in p.segments:
        f = lambda q: (q[0], 2 * x0 - q[1])  # noqa: E731
        if isinstance(s, Arc):
            out.append(Arc(f(s.p0), f(s.p1), f(s.c), not s.ccw))
        else:
            out.append(Line(f(s.p0), f(s.p1)))
    return Profile(out, closed=False)


# ------------------------------------------------------------------ geometri yardımcıları


def _core_dist(cl: np.ndarray, cr: np.ndarray, seg) -> float:
    """Yatay [C_L, C_R] doğru parçasının profil parçasına uzaklığı (kesişirse 0)."""
    if math.hypot(*(cr - cl)) < 1e-12:
        return distance(cl, seg)
    core = Line(cl, cr)
    if intersect(core, seg):
        return 0.0
    d = [distance(cl, seg), distance(cr, seg), distance(seg.p0, core), distance(seg.p1, core)]
    if isinstance(seg, Arc):
        h = cl[1]
        for phi in (math.pi / 2, -math.pi / 2):
            q = seg.c + seg.R * np.array([math.cos(phi), math.sin(phi)])
            if distance(q, seg) <= 1e-12 and cl[0] - 1e-12 <= q[0] <= cr[0] + 1e-12:
                d.append(abs(q[1] - h))
    return min(d)


def _prof_dist(cl: np.ndarray, a: float, profile: Profile) -> float:
    cr = cl + np.array([a, 0.0])
    return min(_core_dist(cl, cr, s) for s in profile.segments)


def _samples(seg, n: int = 41) -> list[np.ndarray]:
    return [seg.point(t) for t in np.linspace(0.0, 1.0, n)]


def _vertices(segs) -> list[np.ndarray]:
    return [segs[0].p0] + [s.p1 for s in segs]


def _same_seg(a, b) -> None:
    assert type(a) is type(b)
    assert a.p0 == pytest.approx(b.p0, abs=TOL)
    assert a.p1 == pytest.approx(b.p1, abs=TOL)
    if isinstance(a, Arc):
        assert a.c == pytest.approx(b.c, abs=TOL)
        assert a.ccw == b.ccw


def _q(tool: LatheTool, side: str = "dis") -> np.ndarray:
    """Gerçek çerçevede C_L'den programlanan noktaya vektör (z, x)."""
    r, a = tool.nose_r, tool.width - 2 * tool.nose_r
    sgn = 1 if side == "dis" else -1
    tip = tool.tip if sgn > 0 else mirror_tip(tool.tip)
    q = tip_offset(tip, r) * np.array([1.0, sgn])  # çerçeve → gerçek
    if tip == 4:
        q = q + np.array([a, 0.0])
    return q


def _cut_moves(tp: Toolpath) -> list:
    """İlk kesme hareketinden son kesme hareketine kadar (dahil) hareketler."""
    idx = [i for i, m in enumerate(tp.moves) if m.type is not G0]
    assert idx, "kesme hareketi yok"
    return tp.moves[idx[0] : idx[-1] + 1], idx[0]


def _as_c(m, q: np.ndarray) -> tuple[MoveType, np.ndarray, np.ndarray | None]:
    """Hareket → (tür, C_L ucu (z, x), C_L yay merkezi (z, x))."""
    end = np.array([m.end[2], m.end[0]]) - q
    c = None if m.center is None else np.array([m.center[1], m.center[0]]) - q
    return m.type, end, c


def _check_core(tp: Toolpath, tool: LatheTool, expected: list[tuple], side: str = "dis") -> None:
    """expected: [(tür, C_L ucu, C_L merkezi | None)] — ilk kesmeden son kesmeye."""
    moves, _ = _cut_moves(tp)
    q = _q(tool, side)
    assert len(moves) == len(expected)
    for m, (mt, end, c) in zip(moves, expected, strict=True):
        t, e, cc = _as_c(m, q)
        assert t is mt
        assert e == pytest.approx(end, abs=TOL)
        if c is not None:
            assert cc == pytest.approx(c, abs=TOL)
        assert m.feed == pytest.approx(CUT.feed)


def _check_path(tp: Toolpath, tool: LatheTool, stock: CylinderStock, side: str = "dis") -> None:
    """SPEC 20 K16 genel kuralları + çapraz G0 yok."""
    assert tp.tool is tool
    assert tp.plane is Plane.ZX
    assert tp.feed_mode is FeedMode.PER_REV
    assert tp.rpm == pytest.approx(CUT.rpm)
    assert tp.css == CUT.css
    tp.validate()
    r = tool.nose_r
    cl = CUT.clearance
    if side == "dis":
        A = np.array([stock.zmax + cl + r, stock.D / 2 + cl + r])  # dış çerçeve, başvuru burnu
        P = A + tip_offset(tool.tip, r)
        PA = (float(P[1]), 0.0, float(P[0]))
    else:
        A = np.array([stock.zmax + cl + r, -stock.d / 2 + cl + r])
        P = A + tip_offset(mirror_tip(tool.tip), r)
        PA = (float(-P[1]), 0.0, float(P[0]))
    assert tp.start == pytest.approx(PA, abs=TOL)
    assert tp.moves[-1].end == pytest.approx(PA, abs=TOL)
    p0 = np.array(tp.start)
    for m in tp.moves:
        p1 = np.array(m.end)
        assert p1[1] == 0.0
        if m.type is G0:
            assert m.feed is None
            assert abs(p1[0] - p0[0]) <= TOL or abs(p1[2] - p0[2]) <= TOL, "çapraz G0"
        else:
            assert m.feed == pytest.approx(CUT.feed)
        p0 = p1


def _check_no_gouge(tp: Toolpath, tool: LatheTool, profile: Profile, rho: float, side: str = "dis") -> None:
    """İlk kesmeden son kesmeye her hareket boyunca (aradaki G0'lar dahil) çekirdeğin profile uzaklığı ≥ ρ."""
    moves, i0 = _cut_moves(tp)
    q = _q(tool, side)
    a = tool.width - 2 * tool.nose_r
    sgn = 1.0 if side == "dis" else -1.0
    prev = tp.moves[i0 - 1].end if i0 > 0 else tp.start
    p0 = np.array([prev[2], prev[0]]) - q
    # iç tarafta hesap dış çerçevede (x → −x)
    fr = np.array([1.0, sgn])
    prof = (
        profile
        if side == "dis"
        else Profile(
            [
                Arc(s.p0 * fr, s.p1 * fr, s.c * fr, not s.ccw)
                if isinstance(s, Arc)
                else Line(s.p0 * fr, s.p1 * fr)
                for s in profile.segments
            ],
            closed=False,
        )
    )
    for m in moves:
        _, p1, c = _as_c(m, q)
        if m.type in (G0, G1):
            seg = Line(p0 * fr, p1 * fr)
        else:
            ccw = (m.type is G3) == (sgn > 0)
            seg = Arc(p0 * fr, p1 * fr, c * fr, ccw)
        for cpt in _samples(seg):
            assert _prof_dist(cpt, a, prof) >= rho - 1e-9
        p0 = p1


# ------------------------------------------------------------------ K11 zarf


class TestK11Zarf:
    def test_T5_tek_yay(self):
        env = recess_envelope(_t5_profile(), _tool(4.0, 2.0))
        assert len(env) == 1
        s = env[0]
        assert isinstance(s, Arc)
        assert s.c == pytest.approx((30.0, 17.0), abs=TOL)
        assert s.R == pytest.approx(1.0, abs=TOL)
        # arkadan öne: (29, 17) → (31, 17), (30, 16)'dan geçerek
        assert s.p0 == pytest.approx((29.0, 17.0), abs=TOL)
        assert s.p1 == pytest.approx((31.0, 17.0), abs=TOL)
        assert s.point(0.5) == pytest.approx((30.0, 16.0), abs=TOL)

    def test_T6_iki_yay(self):
        env = recess_envelope(_t5_profile(), _tool(4.0, 0.4))
        h = 17.0 - math.sqrt(4.2)
        assert len(env) == 2
        a1, a2 = env
        assert isinstance(a1, Arc) and isinstance(a2, Arc)
        assert a1.c == pytest.approx((30.0, 17.0), abs=TOL)
        assert a2.c == pytest.approx((26.8, 17.0), abs=TOL)
        assert a1.R == pytest.approx(2.6, abs=TOL) and a2.R == pytest.approx(2.6, abs=TOL)
        assert a1.p0 == pytest.approx((27.4, 17.0), abs=TOL)
        assert a1.p1 == pytest.approx((28.4, h), abs=TOL)
        assert a2.p1 == pytest.approx((29.4, 17.0), abs=TOL)
        assert a1.point(0.5)[1] < 17.0 and a2.point(0.5)[1] < 17.0

    @pytest.mark.parametrize("r", [0.2, 0.35])
    def test_T7_dogrular(self, r):
        a = 3.0 - 2 * r
        s = r * S2
        env = recess_envelope(_t7_profile(), _tool(3.0, r))
        assert all(isinstance(e, Line) for e in env)
        exp = [
            (25.0 + r, 45.0 + s - (25.0 + r)),  # arka yanak, erişim aralığı başı (C_L = z_left + r)
            (45.0 + s - (17.0 + r), 17.0 + r),  # arka yanak ∩ taban (C_L)
            (32.0 + r - s - a, 17.0 + r),  # taban ∩ ön yanak (C_R = z_L + a)
            (35.0 - r - a, (35.0 - r) - 15.0 + s),  # ön yanak, erişim aralığı sonu (C_R = z_right − r)
        ]
        assert len(env) == 3
        for v, e in zip(_vertices(env), exp, strict=True):
            assert v == pytest.approx(e, abs=TOL)

    def test_T7_kapali_form_degerleri(self):
        # SPEC tablosu: tabanda C_x = 17,2, C_R,z ∈ [30,68284…, 31,91716…]
        env = recess_envelope(_t7_profile(), _tool(3.0, 0.2))
        flat = [e for e in env if abs(e.p0[1] - 17.2) <= TOL and abs(e.p1[1] - 17.2) <= TOL]
        assert len(flat) == 1
        zs = sorted([flat[0].p0[0] + 2.6, flat[0].p1[0] + 2.6])
        assert zs == pytest.approx([30.68284271, 31.91715729], abs=1e-8)
        # ön yanakta C_R doğrusu x − z = −15 + r√2
        front = env[-1]
        for pt in (front.p0, front.p1):
            assert pt[1] - (pt[0] + 2.6) == pytest.approx(-15.0 + 0.2 * S2, abs=TOL)

    def test_talas_payi(self):
        # δ = 0,1: ρ = 0,3; taban C_x = 17,3
        env = recess_envelope(_t7_profile(), _tool(3.0, 0.2), allowance=0.1)
        lo = min(min(e.p0[1], e.p1[1]) for e in env)
        assert lo == pytest.approx(17.3, abs=TOL)
        assert env[0].p0[0] == pytest.approx(25.3, abs=TOL)
        assert env[-1].p1[0] == pytest.approx(35.0 - 0.3 - 2.6, abs=TOL)

    @pytest.mark.parametrize(
        ("prof", "w", "r", "delta"),
        [
            ("t5", 4.0, 2.0, 0.0),
            ("t5", 4.0, 0.4, 0.0),
            ("t5", 4.0, 0.4, 0.15),
            ("t7", 3.0, 0.2, 0.0),
            ("t7", 3.0, 0.2, 0.1),
            ("t7", 2.0, 0.5, 0.0),
        ],
    )
    def test_carpmaz_ve_temas(self, prof, w, r, delta):
        profile = _t5_profile() if prof == "t5" else _t7_profile()
        rho = r + delta
        a = w - 2 * r
        env = recess_envelope(profile, _tool(w, r), allowance=delta)
        # arkadan öne, kopuksuz
        for s0, s1 in zip(env, env[1:], strict=False):
            assert s0.p1 == pytest.approx(s1.p0, abs=1e-7)
        assert env[0].p0[0] < env[-1].p1[0]
        for seg in env:
            for c in _samples(seg):
                d = _prof_dist(c, a, profile)
                assert d >= rho - 1e-9  # S profilin altına girmiyor
                assert d <= rho + 1e-9  # en az bir temas

    def test_ic_aynasi(self):
        # içte zarf, dış zarfın x → 40 − x aynası (yaylar yön değiştirir)
        tool = _tool(4.0, 0.4, tip=2)
        ext = recess_envelope(_t5_profile(), _tool(4.0, 0.4), side="dis")
        inn = recess_envelope(_mirror_about(_t5_profile(), X_TOP), tool, side="ic")
        assert len(inn) == len(ext)
        for a, b in zip(inn, ext, strict=True):
            m = np.array([0.0, 2 * X_TOP])
            f = np.array([1.0, -1.0])
            assert a.p0 == pytest.approx(m + b.p0 * f, abs=TOL)
            assert a.p1 == pytest.approx(m + b.p1 * f, abs=TOL)
            if isinstance(b, Arc):
                assert isinstance(a, Arc)
                assert a.c == pytest.approx(m + b.c * f, abs=TOL)
                assert a.ccw == (not b.ccw)


# ------------------------------------------------------------------ K12 kaba


def _h_t7(z_l: float, rho: float, a: float) -> float:
    s = rho * S2
    return max(17.0 + rho, 45.0 + s - z_l, z_l + a - 15.0 + s)


class TestK12Kaba:
    @pytest.mark.parametrize(("r", "delta"), [(0.2, 0.1), (0.2, 0.0), (0.3, 0.25)])
    def test_dalislar_T7(self, r, delta):
        tool = _tool(3.0, r)
        a = 3.0 - 2 * r
        rho = r + delta
        tp = recess_rough(_t7_profile(), X_TOP, BAR, tool, CUT, allowance=delta)
        _check_path(tp, tool, BAR)
        span = 10.0 - 2 * rho - a
        m = math.ceil(span / a - 1e-9) + 1
        zl = [25.0 + rho + j * span / (m - 1) for j in range(m)]
        q = _q(tool)
        dives = [i for i, mv in enumerate(tp.moves) if mv.type is not G0]
        assert len(dives) == m
        top = X_TOP + CUT.clearance + r
        for i, z in zip(dives, zl, strict=True):
            mv = tp.moves[i]
            assert mv.type is G1
            _, end, _ = _as_c(mv, q)
            assert end == pytest.approx((z, _h_t7(z, rho, a)), abs=TOL)
            _, before, _ = _as_c(tp.moves[i - 1], q)
            _, after, _ = _as_c(tp.moves[i + 1], q)
            assert before == pytest.approx((z, top), abs=TOL)
            assert after == pytest.approx((z, top), abs=TOL)
            assert tp.moves[i - 1].type is G0 and tp.moves[i + 1].type is G0
        _check_no_gouge(tp, tool, _t7_profile(), rho)

    def test_T3_dalis_sayisi(self):
        # r = 0,2, δ = 0,1: span = 6,8, a = 2,6 → m = ⌈2,615…⌉ + 1 = 4
        tp = recess_rough(_t7_profile(), X_TOP, BAR, _tool(3.0, 0.2), CUT, allowance=0.1)
        assert len([mv for mv in tp.moves if mv.type is G1]) == 4

    def test_tek_dalis(self):
        # W = 6, w = 6, r = 0,4: span = 0 → tek dalış, z_L = 27,4, taban h = 17
        tool = _tool(6.0, 0.4)
        tp = recess_rough(_t5_profile(), X_TOP, BAR, tool, CUT)
        _check_path(tp, tool, BAR)
        g1 = [mv for mv in tp.moves if mv.type is not G0]
        assert len(g1) == 1
        _, end, _ = _as_c(g1[0], _q(tool))
        assert end == pytest.approx((27.4, 17.0), abs=TOL)

    def test_yay_tabanli_pay(self):
        # T5 tabanı, w = 3, r = 0,3, δ = 0,2: her yerde ≥ r + δ
        tool = _tool(3.0, 0.3)
        tp = recess_rough(_t5_profile(), X_TOP, BAR, tool, CUT, allowance=0.2)
        _check_path(tp, tool, BAR)
        _check_no_gouge(tp, tool, _t5_profile(), 0.5)

    def test_T4_ucu(self):
        tool3, tool4 = _tool(3.0, 0.2, tip=3), _tool(3.0, 0.2, tip=4)
        tp3 = recess_rough(_t7_profile(), X_TOP, BAR, tool3, CUT, allowance=0.1)
        tp4 = recess_rough(_t7_profile(), X_TOP, BAR, tool4, CUT, allowance=0.1)
        _check_path(tp4, tool4, BAR)
        d3 = [m for m in tp3.moves if m.type is G1]
        d4 = [m for m in tp4.moves if m.type is G1]
        assert len(d3) == len(d4)
        for m3, m4 in zip(d3, d4, strict=True):
            # T4: P = C_R + (r, −r) = T3 noktası + (w, 0)
            assert m4.end == pytest.approx((m3.end[0], 0.0, m3.end[2] + 3.0), abs=TOL)

    def test_ad(self):
        assert recess_rough(_t7_profile(), X_TOP, BAR, _tool(3.0, 0.2), CUT).name == "girinti_kaba"

    def test_dar_kanal(self):
        # W = 10 < w + 2δ = 3 + 7,2
        with pytest.raises(CamError):
            recess_rough(_t7_profile(), X_TOP, BAR, _tool(3.0, 0.2), CUT, allowance=3.6)

    def test_tam_yaricapli_cok_dalis(self):
        # a = 0 ve span > 0
        with pytest.raises(CamError):
            recess_rough(_t5_profile(), X_TOP, BAR, _tool(4.0, 2.0), CUT)
        with pytest.raises(CamError):
            recess_rough(_t7_profile(), X_TOP, BAR, _tool(0.4, 0.2), CUT)

    @pytest.mark.parametrize("delta", [-0.1, math.nan])
    def test_gecersiz_pay(self, delta):
        with pytest.raises(CamError):
            recess_rough(_t7_profile(), X_TOP, BAR, _tool(3.0, 0.2), CUT, allowance=delta)


# ------------------------------------------------------------------ K13 ince ve kalan malzeme


class TestK13Ince:
    def test_T5_tek_yay(self):
        tool = _tool(4.0, 2.0)
        tp = recess_finish(_t5_profile(), X_TOP, BAR, tool, CUT)
        _check_path(tp, tool, BAR)
        top = X_TOP + CUT.clearance + 2.0
        _check_core(
            tp,
            tool,
            [
                (G1, (31.0, 17.0), None),
                (G2, (29.0, 17.0), (30.0, 17.0)),  # önden arkaya: saat yönü
                (G1, (29.0, top), None),
            ],
        )
        moves, i0 = _cut_moves(tp)
        _, before, _ = _as_c(tp.moves[i0 - 1], _q(tool))
        assert tp.moves[i0 - 1].type is G0
        assert before == pytest.approx((31.0, top), abs=TOL)  # ön sanal duvarda giriş
        _check_no_gouge(tp, tool, _t5_profile(), 2.0)

    def test_T5_programlanan_nokta(self):
        # T3: P = C_L + (−r, −r): yay merkezi (x, z) = (15, 28), bitiş (15, 0, 27)
        tp = recess_finish(_t5_profile(), X_TOP, BAR, _tool(4.0, 2.0), CUT)
        arc = next(m for m in tp.moves if m.type in (G2, G3))
        assert arc.center == pytest.approx((15.0, 28.0), abs=TOL)
        assert arc.end == pytest.approx((15.0, 0.0, 27.0), abs=TOL)

    def test_T7_dogrular(self):
        r = 0.2
        s = r * S2
        tool = _tool(3.0, r)
        tp = recess_finish(_t7_profile(), X_TOP, BAR, tool, CUT)
        _check_path(tp, tool, BAR)
        top = X_TOP + CUT.clearance + r
        _check_core(
            tp,
            tool,
            [
                (G1, (32.2, 19.8 + s), None),  # ön sanal duvar: z_L = z_right − r − a
                (G1, (29.6 - s, 17.2), None),
                (G1, (27.8 + s, 17.2), None),
                (G1, (25.2, 19.8 + s), None),  # arka sanal duvar: z_L = z_left + r
                (G1, (25.2, top), None),
            ],
        )
        moves, i0 = _cut_moves(tp)
        _, before, _ = _as_c(tp.moves[i0 - 1], _q(tool))
        assert before == pytest.approx((32.2, top), abs=TOL)
        _check_no_gouge(tp, tool, _t7_profile(), r)

    def test_T6_zarfla_birebir(self):
        tool = _tool(4.0, 0.4)
        env = recess_envelope(_t5_profile(), tool)
        tp = recess_finish(_t5_profile(), X_TOP, BAR, tool, CUT, rest_max=0.56)
        _check_path(tp, tool, BAR)
        top = X_TOP + CUT.clearance + 0.4
        exp = [(G1, env[-1].p1, None)]
        for e in reversed(env):
            b = e.reversed()
            if isinstance(b, Arc):
                exp.append((G3 if b.ccw else G2, b.p1, b.c))
            else:
                exp.append((G1, b.p1, None))
        exp.append((G1, (env[0].p0[0], top), None))
        _check_core(tp, tool, exp)
        _check_no_gouge(tp, tool, _t5_profile(), 0.4)

    def test_T4_programlanan_nokta(self):
        # T4: P = C_R + (r, −r) = T3 noktası + (w, 0)
        t3, t4 = _tool(3.0, 0.2, tip=3), _tool(3.0, 0.2, tip=4)
        c3, _ = _cut_moves(recess_finish(_t7_profile(), X_TOP, BAR, t3, CUT))
        tp4 = recess_finish(_t7_profile(), X_TOP, BAR, t4, CUT)
        _check_path(tp4, t4, BAR)
        c4, _ = _cut_moves(tp4)
        assert len(c3) == len(c4)
        for m3, m4 in zip(c3, c4, strict=True):
            assert m4.type is m3.type
            assert m4.end == pytest.approx((m3.end[0], 0.0, m3.end[2] + 3.0), abs=TOL)

    def test_T4_yay(self):
        t3, t4 = _tool(4.0, 0.4, tip=3), _tool(4.0, 0.4, tip=4)
        c3, _ = _cut_moves(recess_finish(_t5_profile(), X_TOP, BAR, t3, CUT, rest_max=0.56))
        c4, _ = _cut_moves(recess_finish(_t5_profile(), X_TOP, BAR, t4, CUT, rest_max=0.56))
        for m3, m4 in zip(c3, c4, strict=True):
            assert m4.end == pytest.approx((m3.end[0], 0.0, m3.end[2] + 4.0), abs=TOL)
            if m3.center is not None:
                assert m4.center == pytest.approx((m3.center[0], m3.center[1] + 4.0), abs=TOL)

    def test_ad(self):
        assert recess_finish(_t7_profile(), X_TOP, BAR, _tool(3.0, 0.2), CUT).name == "girinti_ince"

    # -------------------------------------------------------------- kalan malzeme

    def test_rest_T5(self):
        assert recess_rest(_t5_profile(), _tool(4.0, 2.0)) == pytest.approx(0.0, abs=TOL)

    def test_rest_T6(self):
        e = 2.6 - math.sqrt(4.2)
        assert recess_rest(_t5_profile(), _tool(4.0, 0.4)) == pytest.approx(e, rel=1e-12)
        assert recess_rest(_t5_profile(), _tool(4.0, 0.4)) == pytest.approx(0.55060984, abs=1e-8)

    def test_rest_genel_formul(self):
        # yarım daire R = 3, a > 0: e_max = (R − r) − √((R − r)² − (a/2)²)
        w, r = 3.0, 0.5
        a = w - 2 * r
        e = (3.0 - r) - math.sqrt((3.0 - r) ** 2 - (a / 2) ** 2)
        assert recess_rest(_t5_profile(), _tool(w, r)) == pytest.approx(e, rel=1e-12)

    def test_rest_T7(self):
        assert recess_rest(_t7_profile(), _tool(3.0, 0.2)) == pytest.approx(0.0, abs=TOL)

    def test_T6_rest_max_0_hata(self):
        with pytest.raises(CamError, match=r"0[.,]55"):
            recess_finish(_t5_profile(), X_TOP, BAR, _tool(4.0, 0.4), CUT)

    def test_T6_rest_max_056_gecer(self):
        tp = recess_finish(_t5_profile(), X_TOP, BAR, _tool(4.0, 0.4), CUT, rest_max=0.56)
        tp.validate()

    def test_T6_rest_max_055_hata(self):
        with pytest.raises(CamError):
            recess_finish(_t5_profile(), X_TOP, BAR, _tool(4.0, 0.4), CUT, rest_max=0.55)

    @pytest.mark.parametrize("rest_max", [-0.1, math.nan])
    def test_gecersiz_rest_max(self, rest_max):
        with pytest.raises(CamError):
            recess_finish(_t7_profile(), X_TOP, BAR, _tool(3.0, 0.2), CUT, rest_max=rest_max)

    # -------------------------------------------------------------- iç taraf

    def test_ic_T7_aynasi(self):
        # iç kanal: T7'nin x → 40 − x aynası, delik yarıçapı 20; T2 ucu dıştaki T3'ün aynası
        ext_tool = _tool(3.0, 0.2, tip=3)
        int_tool = _tool(3.0, 0.2, tip=2)
        ext = recess_finish(_t7_profile(), X_TOP, BAR, ext_tool, CUT)
        inn = recess_finish(_mirror_about(_t7_profile(), X_TOP), X_TOP, TUBE, int_tool, CUT, side="ic")
        _check_path(inn, int_tool, TUBE, side="ic")
        ce, _ = _cut_moves(ext)
        ci, _ = _cut_moves(inn)
        assert len(ce) == len(ci)
        for me, mi in zip(ce, ci, strict=True):
            assert mi.type is me.type
            assert mi.end == pytest.approx((2 * X_TOP - me.end[0], 0.0, me.end[2]), abs=TOL)
        _check_no_gouge(inn, int_tool, _mirror_about(_t7_profile(), X_TOP), 0.2, side="ic")

    def test_ic_T6_yaylar(self):
        ext = recess_finish(_t5_profile(), X_TOP, BAR, _tool(4.0, 0.4, tip=3), CUT, rest_max=0.56)
        inn = recess_finish(
            _mirror_about(_t5_profile(), X_TOP),
            X_TOP,
            TUBE,
            _tool(4.0, 0.4, tip=2),
            CUT,
            rest_max=0.56,
            side="ic",
        )
        ce, _ = _cut_moves(ext)
        ci, _ = _cut_moves(inn)
        swap = {G1: G1, G2: G3, G3: G2}
        assert len(ce) == len(ci)
        for me, mi in zip(ce, ci, strict=True):
            assert mi.type is swap[me.type]
            assert mi.end == pytest.approx((2 * X_TOP - me.end[0], 0.0, me.end[2]), abs=TOL)
            if me.center is not None:
                assert mi.center == pytest.approx((2 * X_TOP - me.center[0], me.center[1]), abs=TOL)

    def test_ic_rest(self):
        e = recess_rest(_mirror_about(_t5_profile(), X_TOP), _tool(4.0, 0.4, tip=2), side="ic")
        assert e == pytest.approx(2.6 - math.sqrt(4.2), rel=1e-12)

    def test_ic_kaba(self):
        tool = _tool(3.0, 0.2, tip=2)
        tp = recess_rough(
            _mirror_about(_t7_profile(), X_TOP), X_TOP, TUBE, tool, CUT, allowance=0.1, side="ic"
        )
        _check_path(tp, tool, TUBE, side="ic")
        _check_no_gouge(tp, tool, _mirror_about(_t7_profile(), X_TOP), 0.3, side="ic")

    # -------------------------------------------------------------- hatalar

    def test_arka_kesim(self):
        # (33,17) → (34,15): t_z > 0 (alttan oyuk)
        p = Profile.polygon([(35, 20), (33, 17), (34, 15), (27, 15), (25, 20)], closed=False)
        for f in (
            lambda: recess_envelope(p, _tool(3.0, 0.2)),
            lambda: recess_rest(p, _tool(3.0, 0.2)),
            lambda: recess_rough(p, X_TOP, BAR, _tool(3.0, 0.2), CUT),
            lambda: recess_finish(p, X_TOP, BAR, _tool(3.0, 0.2), CUT),
        ):
            with pytest.raises(CamError):
                f()

    def test_dik_duvar_serbest(self):
        # t_z = 0 (dik duvar) arka kesim sayılmaz
        recess_envelope(_t5_profile(), _tool(4.0, 0.4))

    def test_x_topa_donmeyen_profil(self):
        p = Profile.polygon([(35, 20), (32, 17), (28, 17), (25, 18)], closed=False)
        with pytest.raises(CamError):
            recess_envelope(p, _tool(3.0, 0.2))
        with pytest.raises(CamError):
            recess_finish(p, X_TOP, BAR, _tool(3.0, 0.2), CUT)

    def test_x_top_uyusmuyor(self):
        with pytest.raises(CamError):
            recess_finish(_t7_profile(), 21.0, BAR, _tool(3.0, 0.2), CUT)
        with pytest.raises(CamError):
            recess_rough(_t7_profile(), 19.0, BAR, _tool(3.0, 0.2), CUT)

    def test_x_topun_ustunde_nokta(self):
        p = Profile.polygon([(35, 20), (34, 21), (32, 17), (28, 17), (25, 20)], closed=False)
        with pytest.raises(CamError):
            recess_envelope(p, _tool(3.0, 0.2))

    def test_eksenin_altinda(self):
        p = Profile.polygon([(35, 2), (33, -1), (27, -1), (25, 2)], closed=False)
        with pytest.raises(CamError):
            recess_envelope(p, _tool(3.0, 0.2))

    def test_takimdan_dar(self):
        # W = 10 < w = 11
        with pytest.raises(CamError):
            recess_envelope(_t7_profile(), _tool(11.0, 0.2))
        with pytest.raises(CamError):
            recess_finish(_t7_profile(), X_TOP, BAR, _tool(11.0, 0.2), CUT)

    def test_torna_takimi(self):
        lt = LatheTool(id=1, name="T", kind=LatheToolKind.TURN, nose_r=0.4, tip=3, kappa_r=95.0, eps_r=80.0)
        for f in (
            lambda: recess_envelope(_t7_profile(), lt),
            lambda: recess_rest(_t7_profile(), lt),
            lambda: recess_rough(_t7_profile(), X_TOP, BAR, lt, CUT),
            lambda: recess_finish(_t7_profile(), X_TOP, BAR, lt, CUT),
        ):
            with pytest.raises(CamError):
                f()

    @pytest.mark.parametrize(("tip", "side"), [(2, "dis"), (1, "dis"), (8, "dis"), (3, "ic"), (4, "ic")])
    def test_yanlis_uc(self, tip, side):
        prof = _t7_profile() if side == "dis" else _mirror_about(_t7_profile(), X_TOP)
        stock = BAR if side == "dis" else TUBE
        with pytest.raises(CamError):
            recess_finish(prof, X_TOP, stock, _tool(3.0, 0.2, tip=tip), CUT, side=side)
        with pytest.raises(CamError):
            recess_rough(prof, X_TOP, stock, _tool(3.0, 0.2, tip=tip), CUT, side=side)

    def test_yanlis_taraf(self):
        with pytest.raises(CamError):
            recess_envelope(_t7_profile(), _tool(3.0, 0.2), side="yan")

    def test_kapali_profil(self):
        p = Profile.polygon([(35, 20), (32, 17), (28, 17), (25, 20)], closed=True)
        with pytest.raises(CamError):
            recess_envelope(p, _tool(3.0, 0.2))


def test_cut_a_p_kullanilmaz():
    # cut.a_p dalış derinliğini belirlemez: a_p verilse de verilmese de aynı yol
    tool = _tool(3.0, 0.2)
    t1 = recess_rough(_t7_profile(), X_TOP, BAR, tool, CUT, allowance=0.1)
    t2 = recess_rough(_t7_profile(), X_TOP, BAR, tool, TurnCut(feed=0.05, rpm=800.0, a_p=0.5), allowance=0.1)
    assert [m.end for m in t1.moves] == pytest.approx([m.end for m in t2.moves], abs=TOL)
