"""SPEC 20 — cam/lathe.py testleri (K1–K6).

Testler sadece SPEC 20 metninden (Teori + Arayüz) ve sabit arayüzlerden (cam/model.py, cam/profile.py)
yazıldı; cam/lathe.py gövdeleri okunmadı. Beklenen değerler el ile türetilmiş kapalı formlardır:

- Profil koordinatı (u, v) = (z, x); ön→arka gezide birim teğet t, boş taraf normali n = (t_x, −t_z).
- Hayali uç P = C + q_T, q_T = r·(s_z, s_x) (Fanuc uç tablosu).
- Koni (T = 3, δ = 0, yarım açı α): ΔX = −r(1 − tan(45° − α/2)), ΔZ = −r(1 − tan(α/2)) (Smid).
- Yay: burun merkezi yolu dışbükeyde R + ρ, içbükeyde R − ρ; hayali uç yolu merkezi c + q_T.
- Köşe: dışbükeyde V merkezli ρ yarıçaplı ccw yay, içbükeyde keskin kesişim.
Uzaklıklar tests/cam/ref2d.py'deki bağımsız analitik hesapla (cam.geom2d kullanılmaz).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.lathe import (
    TIP_DIR,
    angles,
    check_reach,
    is_monotone,
    mirror,
    mirror_tip,
    nose_path,
    orient,
    tip_offset,
    tip_path,
)
from cam.model import CamError, LatheTool, LatheToolKind
from cam.profile import Arc, Line, Profile
from tests.cam.ref2d import Egriler, arc_ccw_form

TOL = 1e-9  # mm, SPEC 20 genel tolerans
R_NOSE = 0.8  # mm

# SPEC 20 uç tablosu, (s_z, s_x)
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
AYNA = {1: 4, 4: 1, 2: 3, 3: 2, 6: 8, 8: 6, 5: 5, 7: 7, 0: 0, 9: 9}


# ------------------------------------------------------------------ yardımcılar


def tool(tip: int = 3, r: float = R_NOSE, kappa: float = 93.0, eps: float = 55.0) -> LatheTool:
    return LatheTool(id=1, name="T", kind=LatheToolKind.TURN, nose_r=r, tip=tip, kappa_r=kappa, eps_r=eps)


def poly(*pts) -> Profile:
    return Profile.polygon(pts, closed=False)


def close(p, q, tol: float = TOL) -> bool:
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol


def chain_points(segs) -> list[np.ndarray]:
    return [s.p0 for s in segs] + [segs[-1].p1]


def assert_connected(segs) -> None:
    for a, b in zip(segs[:-1], segs[1:], strict=True):
        assert close(a.p1, b.p0, 1e-7), f"kopuk zincir: {a.p1} ≠ {b.p0}"


def curves(segs) -> Egriler:
    e = Egriler()
    for s in segs:
        if isinstance(s, Arc):
            R, th0, sw = arc_ccw_form(s.p0, s.p1, s.c, cw=not s.ccw)
            e.arc(s.c, R, th0, sw)
        else:
            e.line(s.p0, s.p1)
    return e


def sample(segs, n: int = 60) -> np.ndarray:
    return np.array([s.point(float(t)) for s in segs for t in np.linspace(0.0, 1.0, n)])


def arcs_of(segs) -> list[Arc]:
    return [s for s in segs if isinstance(s, Arc)]


def find_arc(segs, c, R: float) -> Arc | None:
    for s in arcs_of(segs):
        if close(s.c, c) and abs(s.R - R) <= TOL:
            return s
    return None


def normal(t) -> np.ndarray:
    """Boş taraf normali n = (t_x, −t_z)."""
    return np.array([t[1], -t[0]])


def fillet_profile(R: float, z_s: float = -17.0, x_f: float = 10.0, x_top: float = 18.0) -> Profile:
    """Silindir x_f → içbükey R dolgu → omuz z_s → silindir x_top."""
    return Profile(
        [
            Line((0.0, x_f), (z_s + R, x_f)),
            Arc((z_s + R, x_f), (z_s, x_f + R), (z_s + R, x_f + R), ccw=False),
            Line((z_s, x_f + R), (z_s, x_top)),
            Line((z_s, x_top), (-30.0, x_top)),
        ],
        closed=False,
    )


def convex_arc_profile() -> Profile:
    """Ön uçta dışbükey çeyrek yay (φ 90° → 0°), silindir, omuz."""
    return Profile(
        [
            Arc((0.0, 17.0), (-3.0, 20.0), (-3.0, 17.0), ccw=True),
            Line((-3.0, 20.0), (-30.0, 20.0)),
            Line((-30.0, 20.0), (-30.0, 25.0)),
        ],
        closed=False,
    )


def groove_profile(W: float) -> Profile:
    """Silindir x = 15, z = −10'da W genişliğinde, 3 mm derin kanal, silindir devam."""
    return poly(
        (0.0, 15.0), (-10.0, 15.0), (-10.0, 12.0), (-10.0 - W, 12.0), (-10.0 - W, 15.0), (-25.0, 15.0)
    )


def finish_profile() -> Profile:
    """Pah + silindir + içbükey dolgu (R = 2) + omuz + silindir + 30° koni + alın."""
    x_cone = 18.0 + 10.0 * math.tan(math.radians(30.0))
    return Profile(
        [
            Line((0.0, 8.0), (-2.0, 10.0)),
            Line((-2.0, 10.0), (-15.0, 10.0)),
            Arc((-15.0, 10.0), (-17.0, 12.0), (-15.0, 12.0), ccw=False),
            Line((-17.0, 12.0), (-17.0, 18.0)),
            Line((-17.0, 18.0), (-25.0, 18.0)),
            Line((-25.0, 18.0), (-35.0, x_cone)),
            Line((-35.0, x_cone), (-35.0, 30.0)),
        ],
        closed=False,
    )


# ------------------------------------------------------------------ K1 uç tablosu


@pytest.mark.parametrize("T", range(10))
def test_k1_tip_offset_tablo(T):
    q = tip_offset(T, R_NOSE)
    assert np.shape(q) == (2,)
    np.testing.assert_allclose(q, R_NOSE * np.array(TABLO[T], dtype=float), atol=1e-12)


def test_k1_tip_dir_sabiti():
    assert {k: tuple(v) for k, v in TIP_DIR.items()} == TABLO


@pytest.mark.parametrize("T", range(10))
def test_k1_mirror_tip(T):
    assert mirror_tip(T) == AYNA[T]
    # aynalanmış uç vektörü x bileşeninin işaretini çevirir
    q = tip_offset(T, R_NOSE)
    qm = tip_offset(mirror_tip(T), R_NOSE)
    np.testing.assert_allclose(qm, [q[0], -q[1]], atol=1e-12)


def test_k1_sifir_yaricap():
    np.testing.assert_allclose(tip_offset(3, 0.0), [0.0, 0.0], atol=0)


@pytest.mark.parametrize("T", [-1, 10, 11])
def test_k1_hatali_uc_numarasi(T):
    with pytest.raises(CamError):
        tip_offset(T, R_NOSE)


def test_k1_negatif_yaricap():
    with pytest.raises(CamError):
        tip_offset(3, -0.1)


# ------------------------------------------------------------------ K2 orient / mirror


def test_k2_orient_arkadan_one_verileni_ceviriyor():
    p = poly((-30.0, 10.0), (-10.0, 10.0), (-10.0, 5.0), (0.0, 5.0))
    o = orient(p)
    pts = chain_points(o.segments)
    beklenen = [(0.0, 5.0), (-10.0, 5.0), (-10.0, 10.0), (-30.0, 10.0)]
    assert len(pts) == len(beklenen)
    for a, b in zip(pts, beklenen, strict=True):
        assert close(a, b)


def test_k2_orient_dogru_yondekini_degistirmiyor():
    p = poly((0.0, 5.0), (-10.0, 5.0), (-10.0, 10.0), (-30.0, 10.0))
    o = orient(p)
    for a, b in zip(chain_points(o.segments), chain_points(p.segments), strict=True):
        assert close(a, b)


def test_k2_orient_yay_yonunu_ceviriyor():
    ref = convex_arc_profile()
    o = orient(ref.reversed())
    assert len(o.segments) == len(ref.segments)
    for a, b in zip(o.segments, ref.segments, strict=True):
        assert type(a) is type(b)
        assert close(a.p0, b.p0) and close(a.p1, b.p1)
        if isinstance(a, Arc):
            assert a.ccw == b.ccw
            assert close(a.c, b.c)


def test_k2_orient_kapali_profil_hata():
    with pytest.raises(CamError):
        orient(Profile.rectangle(-20.0, 5.0, 10.0, 5.0))


def test_k2_orient_eksenin_alti_hata():
    with pytest.raises(CamError):
        orient(poly((0.0, 5.0), (-10.0, 5.0), (-10.0, -1.0), (-20.0, -1.0)))


def test_k2_mirror():
    p = convex_arc_profile()
    m = mirror(p)
    for a, b in zip(m.segments, p.segments, strict=True):
        assert close(a.p0, (b.p0[0], -b.p0[1])) and close(a.p1, (b.p1[0], -b.p1[1]))
        if isinstance(b, Arc):
            assert isinstance(a, Arc)
            assert a.ccw == (not b.ccw)
            assert close(a.c, (b.c[0], -b.c[1]))
    mm = mirror(m)
    for a, b in zip(mm.segments, p.segments, strict=True):
        assert type(a) is type(b)
        assert close(a.p0, b.p0) and close(a.p1, b.p1)
        if isinstance(b, Arc):
            assert a.ccw == b.ccw and close(a.c, b.c)


# ------------------------------------------------------------------ K3 açılar ve erişim

T30 = math.tan(math.radians(30.0))


@pytest.mark.parametrize(
    ("prof", "beklenen"),
    [
        (poly((0.0, 10.0), (-20.0, 10.0)), (0.0, 0.0)),  # silindir
        (poly((0.0, 0.0), (0.0, 10.0)), (90.0, 90.0)),  # alın
        (poly((0.0, 10.0), (-20.0, 10.0), (-20.0, 16.0), (-40.0, 16.0)), (0.0, 90.0)),  # omuz
        (poly((0.0, 10.0), (-20.0, 10.0 + 20.0 * T30)), (30.0, 30.0)),  # 30° koni
        (
            poly((0.0, 10.0), (-10.0, 10.0), (-20.0, 10.0 - 10.0 * math.tan(math.radians(5.0)))),
            (-5.0, 0.0),
        ),  # 5° geri çekme
    ],
    ids=["silindir", "alin", "omuz", "koni30", "geri_cekme"],
)
def test_k3_acilar(prof, beklenen):
    lo, hi = angles(prof)
    assert lo == pytest.approx(beklenen[0], abs=1e-9)
    assert hi == pytest.approx(beklenen[1], abs=1e-9)


def test_k3_acilar_yay_supurmesi():
    lo, hi = angles(convex_arc_profile())
    assert lo == pytest.approx(0.0, abs=1e-9)
    assert hi == pytest.approx(90.0, abs=1e-9)


def test_k3_acilar_arkadan_verilen_profil():
    # orient önce uygulanır: arkadan öne verilen silindir de φ = 0
    lo, hi = angles(poly((-20.0, 10.0), (0.0, 10.0)))
    assert lo == pytest.approx(0.0, abs=1e-9)
    assert hi == pytest.approx(0.0, abs=1e-9)


def test_k3_ic_taraf_aynada_olculur():
    p = poly((0.0, 20.0), (-10.0, 20.0), (-10.0, 15.0), (-30.0, 15.0))  # iç omuz (delik daralıyor)
    lo, hi = angles(p, side="ic")
    assert (lo, hi) == (pytest.approx(0.0, abs=1e-9), pytest.approx(90.0, abs=1e-9))
    lo, hi = angles(p, side="dis")
    assert (lo, hi) == (pytest.approx(-90.0, abs=1e-9), pytest.approx(0.0, abs=1e-9))
    assert is_monotone(p, side="ic")
    assert not is_monotone(p, side="dis")


def test_k3_is_monotone():
    assert is_monotone(poly((0.0, 10.0), (-20.0, 10.0), (-20.0, 16.0), (-40.0, 16.0)))
    assert is_monotone(poly((0.0, 10.0), (-20.0, 10.0 + 20.0 * T30)))
    assert is_monotone(convex_arc_profile())
    assert is_monotone(fillet_profile(2.0))
    assert not is_monotone(poly((0.0, 10.0), (-10.0, 10.0), (-20.0, 9.0)))
    assert not is_monotone(groove_profile(3.0))


def test_k3_hatali_taraf():
    p = poly((0.0, 10.0), (-20.0, 10.0))
    with pytest.raises(CamError):
        angles(p, side="yan")
    with pytest.raises(CamError):
        is_monotone(p, side="yan")
    with pytest.raises(CamError):
        check_reach(p, tool(), side="yan")


def test_k3_kappa93_omzu_isler():
    omuz = poly((0.0, 10.0), (-20.0, 10.0), (-20.0, 16.0), (-40.0, 16.0))
    assert check_reach(omuz, tool(kappa=93.0, eps=80.0)) is None


def test_k3_kappa60_omuz_hata():
    omuz = poly((0.0, 10.0), (-20.0, 10.0), (-20.0, 16.0), (-40.0, 16.0))
    with pytest.raises(CamError):
        check_reach(omuz, tool(kappa=60.0, eps=55.0))


def test_k3_arka_kenar_acisi():
    t = tool(kappa=93.0, eps=80.0)  # κr' = 180 − 93 − 80 = 7°
    hafif = poly((0.0, 10.0), (-10.0, 10.0), (-20.0, 10.0 - 10.0 * math.tan(math.radians(5.0))))
    check_reach(hafif, t)
    dik = poly((0.0, 10.0), (-10.0, 10.0), (-20.0, 10.0 - 10.0 * math.tan(math.radians(10.0))))
    with pytest.raises(CamError):
        check_reach(dik, t)


def test_k3_yayda_butun_supurme_kontrol_edilir():
    # 340° ccw yay: uç teğetleri φ = 10° ve 30° (aralıkta), ama yay her yöne döner
    c = np.array([-20.0, 15.0])
    R = 3.0
    S = c + R * np.array([math.cos(math.radians(80.0)), math.sin(math.radians(80.0))])
    E = c + R * np.array([math.cos(math.radians(60.0)), math.sin(math.radians(60.0))])
    p = Profile(
        [Line((0.0, S[1]), S), Arc(S, E, c, ccw=True), Line(E, (-40.0, E[1]))],
        closed=False,
    )
    with pytest.raises(CamError):
        check_reach(p, tool(kappa=93.0, eps=80.0))


# ------------------------------------------------------------------ K4 telafi, doğru


def test_k4_silindir_t3_profilin_kendisi():
    segs = tip_path(poly((0.0, 10.0), (-20.0, 10.0)), tool())
    assert_connected(segs)
    for p in chain_points(segs):
        assert abs(p[1] - 10.0) <= TOL
    assert close(segs[0].p0, (-R_NOSE, 10.0))
    assert close(segs[-1].p1, (-20.0 - R_NOSE, 10.0))


def test_k4_alin_t3_profilin_kendisi():
    segs = tip_path(poly((0.0, 0.0), (0.0, 10.0)), tool())
    assert_connected(segs)
    for p in chain_points(segs):
        assert abs(p[0]) <= TOL
    assert close(segs[0].p0, (0.0, -R_NOSE))
    assert close(segs[-1].p1, (0.0, 10.0 - R_NOSE))


@pytest.mark.parametrize("alpha", [30.0, 45.0])
def test_k4_koni_smid(alpha):
    a = math.radians(alpha)
    x0 = 10.0
    prof = poly((0.0, x0), (-20.0, x0 + 20.0 * math.tan(a)))
    segs = tip_path(prof, tool())
    assert len(segs) == 1 and isinstance(segs[0], Line)
    dX = -R_NOSE * (1.0 - math.tan(math.pi / 4 - a / 2))
    dZ = -R_NOSE * (1.0 - math.tan(a / 2))
    for p in chain_points(segs):
        x_prof = x0 + math.tan(a) * (0.0 - p[0])  # profilin p_z'deki x'i
        z_prof = -(p[1] - x0) / math.tan(a)  # profilin p_x'teki z'si
        assert p[1] - x_prof == pytest.approx(dX, abs=TOL)
        assert p[0] - z_prof == pytest.approx(dZ, abs=TOL)
    # başlangıç: profil başlangıcı + r·n + q_3
    n = np.array([math.sin(a), math.cos(a)])
    assert close(segs[0].p0, np.array([0.0, x0]) + R_NOSE * n + np.array([-R_NOSE, -R_NOSE]))


def test_k4_t0_burun_merkezi():
    a = math.radians(30.0)
    p0 = np.array([0.0, 10.0])
    p1 = np.array([-20.0, 10.0 + 20.0 * math.tan(a)])
    prof = poly(p0, p1)
    n = np.array([math.sin(a), math.cos(a)])
    segs = tip_path(prof, tool(tip=0))
    assert len(segs) == 1
    assert close(segs[0].p0, p0 + R_NOSE * n)
    assert close(segs[0].p1, p1 + R_NOSE * n)
    ns = nose_path(prof, R_NOSE)
    assert close(ns[0].p0, segs[0].p0) and close(ns[-1].p1, segs[-1].p1)


def test_k4_talas_payi():
    segs = tip_path(poly((0.0, 10.0), (-20.0, 10.0)), tool(), allowance=0.3)
    for p in chain_points(segs):
        assert abs(p[1] - 10.3) <= TOL
    assert close(segs[0].p0, (-R_NOSE, 10.3))


def test_k4_rho_sifir_profilin_kendisi():
    prof = finish_profile()
    segs = nose_path(prof, 0.0)
    assert_connected(segs)
    assert close(segs[0].p0, prof.start) and close(segs[-1].p1, prof.end)
    d = curves(prof.segments).distance(sample(segs))
    assert np.max(d) <= TOL


def test_k4_hatali_taraf():
    with pytest.raises(CamError):
        nose_path(poly((0.0, 10.0), (-20.0, 10.0)), 0.8, side="yan")


# ------------------------------------------------------------------ K5 telafi, yay


def test_k5_disbukey_yay():
    prof = Profile([Arc((0.0, 17.0), (-3.0, 20.0), (-3.0, 17.0), ccw=True)], closed=False)
    ns = nose_path(prof, R_NOSE)
    assert find_arc(ns, (-3.0, 17.0), 3.0 + R_NOSE) is not None
    tp = tip_path(prof, tool())
    a = find_arc(tp, (-3.0 - R_NOSE, 17.0 - R_NOSE), 3.0 + R_NOSE)
    assert a is not None and a.ccw


def test_k5_icbukey_yay():
    R = 2.0
    prof = fillet_profile(R)
    c = np.array([-17.0 + R, 10.0 + R])
    ns = nose_path(prof, R_NOSE)
    assert find_arc(ns, c, R - R_NOSE) is not None
    tp = tip_path(prof, tool())
    a = find_arc(tp, c + np.array([-R_NOSE, -R_NOSE]), R - R_NOSE)
    assert a is not None and not a.ccw


@pytest.mark.parametrize("R", [0.5, R_NOSE])
def test_k5_erisilemeyen_icbukey_yay_siki_modda_hata(R):
    prof = fillet_profile(R)
    with pytest.raises(CamError):
        nose_path(prof, R_NOSE, strict=True)
    with pytest.raises(CamError):
        tip_path(prof, tool(), strict=True)


def test_k5_erisilemeyen_icbukey_yay_gevsek_modda_duser():
    R = 0.5
    prof = fillet_profile(R)
    ns = nose_path(prof, R_NOSE, strict=False)
    assert_connected(ns)
    c = (-17.0 + R, 10.0 + R)
    for a in arcs_of(ns):
        assert not close(a.c, c, 1e-6), "erişilemeyen dolgu yayı düşmeli"
    # dolgu düşünce silindir ve omuz ofsetleri keskin köşede kesişir
    corner = (-17.0 + R_NOSE, 10.0 + R_NOSE)
    assert any(close(s.p1, corner) for s in ns[:-1])


# ------------------------------------------------------------------ K6 köşeler, budama

RHO = 1.1


def test_k6_omuz_keskin_icbukey_kose():
    prof = poly((0.0, 10.0), (-20.0, 10.0), (-20.0, 16.0), (-40.0, 16.0))
    ns = nose_path(prof, RHO)
    assert_connected(ns)
    corner = (-20.0 + RHO, 10.0 + RHO)
    idx = [i for i in range(len(ns) - 1) if close(ns[i].p1, corner)]
    assert len(idx) == 1
    i = idx[0]
    assert isinstance(ns[i], Line) and isinstance(ns[i + 1], Line)
    # üst köşe (alın → silindir) dışbükey: V merkezli ρ yaylı
    a = find_arc(ns, (-20.0, 16.0), RHO)
    assert a is not None and a.ccw


def test_k6_pah_disbukey_kose_yaylari():
    prof = poly((0.0, 0.0), (0.0, 8.0), (-2.0, 10.0), (-30.0, 10.0))
    ns = nose_path(prof, RHO)
    assert_connected(ns)
    for V in [(0.0, 8.0), (-2.0, 10.0)]:
        a = find_arc(ns, V, RHO)
        assert a is not None, f"{V} köşesinde yay yok"
        assert a.ccw


def test_k6_dar_kanal_siki_modda_hata():
    prof = groove_profile(2.0)  # 2 < 2ρ = 2.2
    with pytest.raises(CamError):
        nose_path(prof, RHO, strict=True)
    with pytest.raises(CamError):
        tip_path(groove_profile(1.5), tool(), strict=True)  # 1.5 < 2r = 1.6
    ns = nose_path(prof, RHO, strict=False)
    assert len(ns) > 0


@pytest.mark.parametrize("rho", [R_NOSE, RHO])
@pytest.mark.parametrize("prof_fn", [finish_profile, lambda: groove_profile(3.0)], ids=["ince", "kanal"])
def test_k6_budama_sonrasi_uzaklik_rho(prof_fn, rho):
    prof = prof_fn()
    ns = nose_path(prof, rho)
    assert_connected(ns)
    d = curves(prof.segments).distance(sample(ns))
    np.testing.assert_allclose(d, rho, atol=1e-9)
    # baş ve son: profil uçlarının ρ·n ötesi
    s0, s1 = prof.segments[0], prof.segments[-1]
    assert close(ns[0].p0, s0.p0 + rho * normal(s0.tangent(0.0)))
    assert close(ns[-1].p1, s1.p1 + rho * normal(s1.tangent(1.0)))


def test_k6_kanal_tabani_budaniyor():
    # W = 3, ρ = 1.1: taban ofseti x = 13.1'de, z ∈ [−11.9, −11.1]
    ns = nose_path(groove_profile(3.0), RHO)
    taban = [
        s for s in ns if isinstance(s, Line) and abs(s.p0[1] - 13.1) <= TOL and abs(s.p1[1] - 13.1) <= TOL
    ]
    assert len(taban) == 1
    zs = sorted([taban[0].p0[0], taban[0].p1[0]])
    assert zs[0] == pytest.approx(-13.0 + RHO, abs=TOL)
    assert zs[1] == pytest.approx(-10.0 - RHO, abs=TOL)


# ------------------------------------------------------------------ uç kapakları (SPEC 20 eki)
# Son parçası ρ'dan kısa açık profil: z = −35'teki duvar 1 mm, ρ = r + δ = 1.1.
# Budama profilin baş ve son noktası merkezli ρ yarıçaplı tam dairelerle de böler (uç kapakları);
# silindir ofseti x = 16.1, son nokta (−35, 16) merkezli kapakla z = −35 + √(1.1² − 0.1²)'de kesişir.

END_CAP_RHO = 1.1
END_CAP_Z = -35.0 + math.sqrt(END_CAP_RHO**2 - 0.1**2)  # −33.904555...


def short_wall_profile() -> Profile:
    return poly((0.0, 10.0), (-20.0, 10.0), (-20.0, 15.0), (-35.0, 15.0), (-35.0, 16.0))


def test_uc_kapagi_gevsek_modda_kapakta_biter():
    prof = short_wall_profile()
    ns = nose_path(prof, END_CAP_RHO, strict=False)
    assert_connected(ns)
    assert close(ns[-1].p1, (END_CAP_Z, 16.1))
    assert END_CAP_Z == pytest.approx(-33.904555, abs=1e-6)


def test_uc_kapagi_gevsek_modda_profile_rho_uzak():
    prof = short_wall_profile()
    ns = nose_path(prof, END_CAP_RHO, strict=False)
    P = np.vstack([sample(ns), [ns[0].p0, ns[-1].p1]])  # uç noktalar dahil
    d = curves(prof.segments).distance(P)
    assert np.min(d) >= END_CAP_RHO - 1e-9, f"en yakın {np.min(d)} < ρ"


def test_uc_kapagi_siki_modda_hata():
    with pytest.raises(CamError):
        nose_path(short_wall_profile(), END_CAP_RHO, strict=True)


def test_uc_kapagi_kapaga_ulasmayan_profil_degismez():
    # r = 0.8 < 1 mm duvar: son nokta eskisi gibi profil sonu + ρ·n = (−34.2, 16)
    ns = nose_path(short_wall_profile(), R_NOSE, strict=True)
    assert_connected(ns)
    assert close(ns[-1].p1, (-35.0 + R_NOSE, 16.0))
    assert any(close(s.p1, (-35.0 + R_NOSE, 15.0 + R_NOSE)) for s in ns[:-1])  # keskin iç köşe
    d = curves(short_wall_profile().segments).distance(sample(ns))
    np.testing.assert_allclose(d, R_NOSE, atol=1e-9)
