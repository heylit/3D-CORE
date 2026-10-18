"""SPEC 27 — cam/turn_features.py testleri (K10–K12). OCCT gerektirmez.

Testler yalnızca SPEC 27 §9 metninden ve sabit arayüzlerden (cam/model.py, cam/profile.py, cam.lathe
imzaları) yazıldı; cam/turn_features.py gövdesi okunmadı. Profil koordinatları (u, v) = (z, x), ön uç
büyük z. Beklenen değerler el ile türetildi:

- Zarf: M(s) = max_{s' ≤ s} x(s'); x < M olan aralık x = M doğrusuyla köprülenir.
- Kanal: dik iniş → sabit x tabanı → dik çıkış ise Groove(z_left = çıkış z, z_right = iniş z, x_top = M,
  x_bottom = taban x); diğer şekiller Recess.
- Yay kesişimi: merkez (8, 6), R = 12 yayı x = 10 doğrusunu sin θ = 1/3'te keser:
  z = 8 + 12 cos θ = 8 + 8√2.
- İç taraf: x → −x aynasında aynı kurallar; geri aynada içte x_bottom > x_top.
Profiller yönden bağımsız karşılaştırılır: aynı doğrultudaki ardışık doğrular birleştirilir.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.lathe import is_monotone
from cam.model import CamError, CylinderStock
from cam.profile import Arc, Line, Profile
from cam.turn_features import Groove, Recess, TurnFeatures, turn_features

TOL = 1e-6  # mm
Z_KESISIM = 8 + 8 * math.sqrt(2)  # x = 10 doğrusu ile merkez (8, 6), R = 12 yayının kesişimi


# ---------------------------------------------------------------- yardımcılar


def yakin(p, q, tol: float = TOL) -> bool:
    return float(np.linalg.norm(np.asarray(p, dtype=float) - np.asarray(q, dtype=float))) <= tol


def cizgi(*pts) -> Profile:
    return Profile.polygon(pts, closed=False)


def sade(profile: Profile) -> list[tuple]:
    """Profilin yönlü parça listesi; aynı doğrultudaki ardışık doğrular ve aynı yayın parçaları birleşik.

    Doğru: ("L", p0, p1); yay: ("A", p0, p1, c, ccw).
    """
    out: list[tuple] = []
    for s in profile.segments:
        p0, p1 = np.asarray(s.p0, dtype=float), np.asarray(s.p1, dtype=float)
        if isinstance(s, Line):
            if out and out[-1][0] == "L":
                a0 = out[-1][1]
                u, v = out[-1][2] - a0, p1 - p0
                ayni_dogrultu = abs(u[0] * v[1] - u[1] * v[0]) <= TOL * np.linalg.norm(u) * np.linalg.norm(v)
                if ayni_dogrultu and u @ v > 0:
                    out[-1] = ("L", a0, p1)
                    continue
            out.append(("L", p0, p1))
        else:
            c = np.asarray(s.c, dtype=float)
            if out and out[-1][0] == "A" and yakin(out[-1][3], c) and out[-1][4] == s.ccw:
                out[-1] = ("A", out[-1][1], p1, c, s.ccw)
                continue
            out.append(("A", p0, p1, c, s.ccw))
    return out


def ayni_profil(P: Profile, Q: Profile) -> bool:
    a, b = sade(P), sade(Q)
    if len(a) != len(b):
        return False
    for x, y in zip(a, b, strict=True):
        if x[0] != y[0] or not (yakin(x[1], y[1]) and yakin(x[2], y[2])):
            return False
        if x[0] == "A" and not (yakin(x[3], y[3]) and x[4] == y[4]):
            return False
    return True


def ayni_kanal(g: Groove, z_left: float, z_right: float, x_top: float, x_bottom: float) -> bool:
    return all(
        abs(a - b) <= TOL
        for a, b in ((g.z_left, z_left), (g.z_right, z_right), (g.x_top, x_top), (g.x_bottom, x_bottom))
    )


# ---------------------------------------------------------------- profiller

# K10: alın, Ø20, kanal 34..40 Ø16 tabanlı, Ø20, omuz, Ø30
K10 = [(60, 0), (60, 10), (40, 10), (40, 8), (34, 8), (34, 10), (20, 10), (20, 15), (0, 15)]
K10_ZARF = [(60, 0), (60, 10), (40, 10), (34, 10), (20, 10), (20, 15), (0, 15)]


def k10() -> Profile:
    return cizgi(*K10)


# ---------------------------------------------------------------- K10


def test_zarf_ve_kanal():
    stok = CylinderStock(D=32.0, zmin=-5.0, zmax=62.0)
    tf = turn_features(k10(), stok)
    assert isinstance(tf, TurnFeatures)
    assert tf.side == "dis"
    assert not tf.rough.closed
    assert ayni_profil(tf.rough, cizgi(*K10_ZARF))
    assert is_monotone(tf.rough, "dis")
    assert len(tf.grooves) == 1
    assert ayni_kanal(tf.grooves[0], 34.0, 40.0, 10.0, 8.0)
    assert tf.recesses == ()
    assert tf.z_face == pytest.approx(60.0, abs=TOL)
    assert tf.face_depth == pytest.approx(2.0, abs=TOL)
    assert ayni_profil(tf.finish, k10())


def test_finish_on_arka_yonlu():
    # arkadan öne verilen profil ön→arka çevrilir; finish aynalanmamış girdi profilidir
    tf = turn_features(k10().reversed())
    assert yakin(tf.finish.start, (60, 0)) and yakin(tf.finish.end, (0, 15))
    assert ayni_profil(tf.finish, k10())
    assert ayni_profil(tf.rough, cizgi(*K10_ZARF))
    assert len(tf.grooves) == 1 and ayni_kanal(tf.grooves[0], 34.0, 40.0, 10.0, 8.0)


def test_monoton_profil_kopru_yok():
    prof = cizgi((60, 0), (60, 10), (20, 10), (20, 15), (0, 15))
    tf = turn_features(prof)
    assert ayni_profil(tf.rough, prof)
    assert tf.grooves == () and tf.recesses == ()


def test_iki_kanal_on_arka_sirali():
    prof = cizgi(
        (60, 0), (60, 10), (50, 10), (50, 7), (46, 7), (46, 10), (30, 10), (30, 8), (27, 8), (27, 10), (0, 10)
    )
    tf = turn_features(prof)
    assert ayni_profil(tf.rough, cizgi((60, 0), (60, 10), (0, 10)))
    assert len(tf.grooves) == 2
    assert ayni_kanal(tf.grooves[0], 46.0, 50.0, 10.0, 7.0)  # ön
    assert ayni_kanal(tf.grooves[1], 27.0, 30.0, 10.0, 8.0)  # arka


def test_alin_yok_stok_ustu_profilde():
    tf = turn_features(k10(), CylinderStock(D=32.0, zmin=-5.0, zmax=60.0))
    assert tf.face_depth is None  # face_depth ≤ tol → alın yok


# ---------------------------------------------------------------- K11


def test_girinti():
    # V kanal: iki 45° eğik doğru (40, 10) → (38, 8) → (36, 10)
    v = cizgi((60, 0), (60, 10), (40, 10), (38, 8), (36, 10), (20, 10), (20, 15), (0, 15))
    tf = turn_features(v)
    assert tf.grooves == ()
    assert len(tf.recesses) == 1
    r = tf.recesses[0]
    assert isinstance(r, Recess)
    assert not r.profile.closed
    assert ayni_profil(r.profile, cizgi((40, 10), (38, 8), (36, 10)))
    assert (r.z_left, r.z_right, r.x_top) == (
        pytest.approx(36.0, abs=TOL),
        pytest.approx(40.0, abs=TOL),
        pytest.approx(10.0, abs=TOL),
    )
    assert ayni_profil(tf.rough, cizgi((60, 0), (60, 10), (20, 10), (20, 15), (0, 15)))
    assert is_monotone(tf.rough, "dis")


def test_yay_tabanli_kanal():
    # yarım daire taban: (40, 10) → (34, 10), merkez (37, 10), R = 3, en alt (37, 7); saat yönünde
    taban = Arc((40, 10), (34, 10), (37, 10), ccw=False)
    prof = Profile(
        [
            Line((60, 0), (60, 10)),
            Line((60, 10), (40, 10)),
            taban,
            Line((34, 10), (20, 10)),
            Line((20, 10), (20, 15)),
            Line((20, 15), (0, 15)),
        ],
        closed=False,
    )
    tf = turn_features(prof)
    assert tf.grooves == ()
    assert len(tf.recesses) == 1
    r = tf.recesses[0]
    assert ayni_profil(r.profile, Profile([taban], closed=False))
    assert r.profile.length == pytest.approx(3 * math.pi, abs=TOL)
    assert (r.z_left, r.z_right, r.x_top) == (
        pytest.approx(34.0, abs=TOL),
        pytest.approx(40.0, abs=TOL),
        pytest.approx(10.0, abs=TOL),
    )
    assert ayni_profil(tf.rough, cizgi((60, 0), (60, 10), (20, 10), (20, 15), (0, 15)))
    assert ayni_profil(tf.finish, prof)


def test_kopru_yayla_kesisimde_biter():
    # Ø20 → iniş Ø12 → yay (merkez (8, 6), R = 12) ile Ø36'ya çıkış; yay x = 10'u z = 8 + 8√2'de keser
    yay = Arc((20, 6), (8, 18), (8, 6), ccw=True)
    prof = Profile(
        [
            Line((60, 0), (60, 10)),
            Line((60, 10), (40, 10)),
            Line((40, 10), (40, 6)),
            Line((40, 6), (20, 6)),
            yay,
            Line((8, 18), (0, 18)),
        ],
        closed=False,
    )
    q = np.array([Z_KESISIM, 10.0])
    assert abs(np.linalg.norm(q - (8, 6)) - 12) <= 1e-12  # kesişim noktası yayın üstünde
    tf = turn_features(prof)
    beklenen = Profile(
        [
            Line((60, 0), (60, 10)),
            Line((60, 10), q),
            Arc(q, (8, 18), (8, 6), ccw=True),
            Line((8, 18), (0, 18)),
        ],
        closed=False,
    )
    assert ayni_profil(tf.rough, beklenen)
    assert is_monotone(tf.rough, "dis")
    assert tf.grooves == ()
    assert len(tf.recesses) == 1
    r = tf.recesses[0]
    alt = Profile(
        [Line((40, 10), (40, 6)), Line((40, 6), (20, 6)), Arc((20, 6), q, (8, 6), ccw=True)],
        closed=False,
    )
    assert ayni_profil(r.profile, alt)
    assert r.z_right == pytest.approx(40.0, abs=TOL)
    assert r.z_left == pytest.approx(Z_KESISIM, abs=TOL)
    assert r.x_top == pytest.approx(10.0, abs=TOL)


def test_kopru_son_z_ye_kadar():
    # profil M'ye bir daha çıkmazsa köprü son z'ye kadar gider
    prof = cizgi((60, 0), (60, 10), (30, 10), (30, 6), (0, 6))
    tf = turn_features(prof)
    assert ayni_profil(tf.rough, cizgi((60, 0), (60, 10), (0, 10)))
    assert tf.grooves == ()
    assert len(tf.recesses) == 1
    r = tf.recesses[0]
    assert ayni_profil(r.profile, cizgi((30, 10), (30, 6), (0, 6)))
    assert r.z_right == pytest.approx(30.0, abs=TOL)
    assert r.z_left == pytest.approx(0.0, abs=TOL)
    assert r.x_top == pytest.approx(10.0, abs=TOL)


# ---------------------------------------------------------------- K12

# iç profil: Ø30 delik, dışa doğru kanal 34..40 Ø34 tabanlı, Ø30, omuz, Ø20
K12 = [(60, 15), (40, 15), (40, 17), (34, 17), (34, 15), (20, 15), (20, 10), (0, 10)]
K12_ZARF = [(60, 15), (40, 15), (34, 15), (20, 15), (20, 10), (0, 10)]


def test_ic_taraf_ve_hatalar():
    prof = cizgi(*K12)
    tf = turn_features(prof, CylinderStock(D=60.0, zmin=-5.0, zmax=62.0, d=16.0), side="ic")
    assert tf.side == "ic"
    assert ayni_profil(tf.rough, cizgi(*K12_ZARF))
    assert is_monotone(tf.rough, "ic")
    assert len(tf.grooves) == 1
    assert ayni_kanal(tf.grooves[0], 34.0, 40.0, 15.0, 17.0)  # içte x_bottom > x_top
    assert tf.recesses == ()
    assert tf.z_face is None and tf.face_depth is None  # iç tarafta alın yok
    assert ayni_profil(tf.finish, prof)  # aynalanmamış


@pytest.mark.parametrize(
    "prof, stok, side",
    [
        # arka kesim: (40, 10) → (42, 6) öne dönüyor (t_z > 0)
        (cizgi((60, 0), (60, 10), (40, 10), (42, 6), (30, 6), (30, 10), (0, 10)), None, "dis"),
        # dışta stoktan taşan: max x = 15 > D/2 = 10
        (cizgi(*K10), CylinderStock(D=20.0, zmin=-5.0, zmax=62.0), "dis"),
        # içte stoktan taşan: min x = 10 < d/2 = 12
        (cizgi(*K12), CylinderStock(D=60.0, zmin=-5.0, zmax=62.0, d=24.0), "ic"),
        # hatalı taraf
        (cizgi(*K10), None, "disari"),
        (cizgi(*K10), None, ""),
    ],
    ids=["arka-kesim", "dis-stoktan-tasan", "ic-stoktan-tasan", "hatali-taraf", "bos-taraf"],
)
def test_hatalar(prof, stok, side):
    with pytest.raises(CamError):
        turn_features(prof, stok, side=side)


@pytest.mark.parametrize("tol", [0.0, -1e-3, math.nan, math.inf])
def test_gecersiz_tol(tol):
    with pytest.raises(CamError):
        turn_features(k10(), tol=tol)


@pytest.mark.parametrize("girdi", [None, K10, "profil", 3.0])
def test_profile_olmayan_girdi(girdi):
    with pytest.raises(CamError):
        turn_features(girdi)
