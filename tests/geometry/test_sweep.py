"""SPEC 65a K3, K4, K7 (JSON), K8 (sweep) — yol boyunca profil.

Testler SPEC 65a metninden ve arayüzden yazıldı; uygulama gövdeleri okunmadı.
Pappus–Guldinus: profil merkezi yol üzerinde ve yol kendini kesmiyorsa V = A · s.
Helis: C(t) = (R cos t, R sin t, c t), c = p / 2π; s = √((2π R)² + p²) · tur.
Profil, yolun başında yola dik düzlemde ve merkezi yolun başlangıç noktasındadır.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from sketch.model import Plane
from tests.geometry.serbest_ortak import REL, daire, rapor, sessiz_gecmez, yuzler

occt = pytest.mark.occt


@pytest.fixture
def ag():
    pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')
    import geometry.agac as m

    return m


@pytest.fixture
def sb():
    pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')
    import geometry.serbest as m

    return m


def _yol():
    from geometry.serbest import Cizgi, Spline, Yay, Yol

    return Cizgi, Yay, Spline, Yol


def duz_yol(L: float = 100.0):
    Cizgi, _, _, Yol = _yol()
    return Yol((Cizgi((0.0, 0.0, 0.0), (0.0, 0.0, L)),))


def ceyrek_yay(R: float = 50.0):
    """Orijinden +z yönünde başlar, merkez (R, 0, 0) etrafında (R, 0, R)'ye döner (xz düzleminde)."""
    _, Yay, _, Yol = _yol()
    a = math.pi / 4
    orta = (R - R * math.cos(a), 0.0, R * math.sin(a))
    return Yol((Yay((0.0, 0.0, 0.0), orta, (R, 0.0, R)),))


R_H, P_H, TUR = 20.0, 10.0, 3


def helis_noktasi(t: float, R: float = R_H, p: float = P_H) -> np.ndarray:
    c = p / (2 * math.pi)
    return np.array([R * math.cos(t), R * math.sin(t), c * t])


def helis_teget(t: float, R: float = R_H, p: float = P_H) -> np.ndarray:
    c = p / (2 * math.pi)
    return np.array([-R * math.sin(t), R * math.cos(t), c])


def helis_yolu(R: float = R_H, p: float = P_H, tur: int = TUR, n_tur: int = 32):
    """Helis, tur başına n_tur aralıklı Spline noktalarıyla (uç teğetleri verilmez)."""
    _, _, Spline, Yol = _yol()
    ts = np.linspace(0.0, 2 * math.pi * tur, n_tur * tur + 1)
    noktalar = tuple(tuple(float(v) for v in helis_noktasi(t, R, p)) for t in ts)
    return Yol((Spline(noktalar),))


def helis_duzlemi(R: float = R_H, p: float = P_H) -> Plane:
    """Helisin başında yola dik düzlem: origin (R, 0, 0), normal = teğet, xdir = +x (teğete dik)."""
    T = helis_teget(0.0, R, p)
    return Plane((R, 0.0, 0.0), T / np.linalg.norm(T), (1.0, 0.0, 0.0))


def sweep_agaci(ag, plane: Plane, r: float, yol, **kw):
    kw.setdefault("islem", "yeni")
    return ag.Agac((ag.Profil("prf", plane, (daire(r),)), ag.Sweep("sw", "prf", yol, **kw)))


def test_sweep_arayuzu_varsayilanlar(ag):
    oz = ag.Sweep("s", "p", duz_yol())
    assert oz.yonlendirme == "frenet"
    assert oz.yardimci is None
    assert oz.islem == "ekle"


# --- Yol boyu ---------------------------------------------------------------------------------------------


@occt
def test_yol_boyu(sb):
    assert sb.yol_boyu(duz_yol(100.0)) == pytest.approx(100.0, rel=1e-9)
    assert sb.yol_boyu(ceyrek_yay(50.0)) == pytest.approx(25 * math.pi, rel=1e-9)
    s = math.hypot(2 * math.pi * R_H, P_H) * TUR
    assert sb.yol_boyu(helis_yolu()) == pytest.approx(s, rel=1e-4)


@occt
def test_yol_birlesik_teget_surekli(sb):
    """Düz çizgi + teğet devam eden çeyrek yay: tek tel, boy = L + πR/2."""
    Cizgi, Yay, _, Yol = _yol()
    R = 20.0
    a = math.pi / 4
    yol = Yol(
        (
            Cizgi((0.0, 0.0, 0.0), (0.0, 0.0, 30.0)),
            Yay((0.0, 0.0, 30.0), (R - R * math.cos(a), 0.0, 30.0 + R * math.sin(a)), (R, 0.0, 30.0 + R)),
        )
    )
    assert sb.yol_boyu(yol) == pytest.approx(30.0 + math.pi * R / 2, rel=1e-9)
    assert sb.yol_teli(yol) is not None


# --- K3: sweep hacimleri ---------------------------------------------------------------------------------


@occt
def test_k3_duz_yol(ag):
    s = ag.insa(sweep_agaci(ag, Plane((0, 0, 0), (0, 0, 1), (1, 0, 0)), 5.0, duz_yol(100.0)))
    assert s.basarili
    assert rapor(s, "sw").durum == "tamam"
    assert s.part.volume == pytest.approx(7853.982, rel=1e-6)


@occt
def test_k3_ceyrek_yay_pappus(ag):
    s = ag.insa(sweep_agaci(ag, Plane((0, 0, 0), (0, 0, 1), (1, 0, 0)), 5.0, ceyrek_yay(50.0)))
    assert s.basarili
    assert s.part.volume == pytest.approx(6168.503, rel=1e-6)
    assert 25 * math.pi * (math.pi * 50 / 2) == pytest.approx(6168.503, rel=1e-6)


@occt
def test_k3_adlar(ag):
    """bas, son ve profil kenarı başına yan_i (daire: tek kenar → yan_1)."""
    s = ag.insa(sweep_agaci(ag, Plane((0, 0, 0), (0, 0, 1), (1, 0, 0)), 5.0, ceyrek_yay(50.0)))
    adlar = {r.name for r in rapor(s, "sw").adlar}
    assert {"bas", "son", "yan_1"} <= adlar
    assert "yan_2" not in adlar
    (bas,) = yuzler(s.part, "sw", "bas")
    (son,) = yuzler(s.part, "sw", "son")
    assert bas.area == pytest.approx(25 * math.pi, rel=REL)
    assert son.area == pytest.approx(25 * math.pi, rel=REL)
    c = son.center()
    assert (c.X, c.Y, c.Z) == pytest.approx((50.0, 0.0, 50.0), abs=1e-6)


@occt
@pytest.mark.parametrize(
    ("yonlendirme", "yardimci"), [("sabit", None), ("yardimci", (1.0, 0.0, 0.0)), ("frenet", None)]
)
def test_k3_duz_yolda_yonlendirmeler_ayni_hacim(ag, yonlendirme, yardimci):
    a = sweep_agaci(
        ag,
        Plane((0, 0, 0), (0, 0, 1), (1, 0, 0)),
        5.0,
        duz_yol(100.0),
        yonlendirme=yonlendirme,
        yardimci=yardimci,
    )
    s = ag.insa(a)
    assert s.basarili
    assert s.part.volume == pytest.approx(2500 * math.pi, rel=REL)


@occt
def test_k3_cikar_bloktan_kanal(ag):
    """islem "cikar": blok içinden geçen r = 5 kanal; kaldırılan hacim A · 100 (blok boyu)."""
    Cizgi, _, _, Yol = _yol()
    yol = Yol((Cizgi((-10.0, 30.0, 10.0), (110.0, 30.0, 10.0)),))
    a = ag.Agac(
        (
            ag.Blok("blok", 100, 60, 20),
            ag.Profil("prf", Plane((-10, 30, 10), (1, 0, 0), (0, 1, 0)), (daire(5.0),)),
            ag.Sweep("sw", "prf", yol, islem="cikar"),
        )
    )
    s = ag.insa(a)
    assert s.basarili
    assert s.part.volume == pytest.approx(120000 - 2500 * math.pi, rel=REL)


# --- K4: helis -------------------------------------------------------------------------------------------


def helis_agaci(ag):
    return sweep_agaci(ag, helis_duzlemi(), 2.0, helis_yolu(), yonlendirme="frenet")


@occt
@pytest.mark.slow
def test_k4_helis_hacmi(ag):
    s = ag.insa(helis_agaci(ag))
    assert s.basarili
    A = 4 * math.pi
    s_boy = math.hypot(2 * math.pi * R_H, P_H) * TUR
    assert s.part.volume == pytest.approx(A * s_boy, rel=1e-3)


def _en_yakin_t(P: np.ndarray) -> float:
    """Analitik helis üzerinde P'ye en yakın parametre: kaba tarama + Newton ((C − P)·C' = 0)."""
    ts = np.linspace(0.0, 2 * math.pi * TUR, 20001)
    c = P_H / (2 * math.pi)
    C = np.column_stack([R_H * np.cos(ts), R_H * np.sin(ts), c * ts])
    t = float(ts[np.argmin(np.linalg.norm(C - P, axis=1))])
    for _ in range(20):
        d = helis_noktasi(t) - P
        d1 = helis_teget(t)
        d2 = np.array([-R_H * math.cos(t), -R_H * math.sin(t), 0.0])
        g = float(d @ d1)
        gp = float(d1 @ d1 + d @ d2)
        t -= g / gp
    return t


@occt
@pytest.mark.slow
def test_k4_profil_yola_dik(ag):
    """Rastgele 10 noktada yan yüz normali, en yakın yol noktasındaki teğete dik (≤ 1e-3 rad)."""
    s = ag.insa(helis_agaci(ag))
    yanlar = yuzler(s.part, "sw", "yan_1")
    assert yanlar
    rng = np.random.default_rng(65)
    for _ in range(10):
        f = yanlar[int(rng.integers(len(yanlar)))]
        u, v = (float(x) for x in rng.uniform(0.05, 0.95, 2))
        p = f.position_at(u, v)
        n = f.normal_at(p)
        P = np.array([p.X, p.Y, p.Z])
        N = np.array([n.X, n.Y, n.Z])
        t = _en_yakin_t(P)
        T = helis_teget(t)
        cos = abs(float(N @ T)) / (np.linalg.norm(N) * np.linalg.norm(T))
        assert abs(math.pi / 2 - math.acos(min(1.0, cos))) <= 1e-3
        assert np.linalg.norm(P - helis_noktasi(t)) == pytest.approx(2.0, abs=1e-2)  # tüp yarıçapı


# --- K7: JSON ---------------------------------------------------------------------------------------------


@occt
@pytest.mark.parametrize("hangi", ["duz", "yay", "helis-spline", "birlesik"])
def test_k7_sweep_json_gidis_donus(ag, hangi):
    Cizgi, Yay, Spline, Yol = _yol()
    yollar = {
        "duz": duz_yol(),
        "yay": ceyrek_yay(),
        "helis-spline": helis_yolu(n_tur=8),
        "birlesik": Yol(
            (
                Cizgi((0.0, 0.0, 0.0), (0.0, 0.0, 10.0)),
                Spline(((0.0, 0.0, 10.0), (1.0, 0.0, 20.0), (3.0, 0.0, 30.0)), (0.0, 0.0, 1.0), None),
            )
        ),
    }
    oz = ag.Sweep("sw", "prf", yollar[hangi], yonlendirme="yardimci", yardimci=(1.0, 0.0, 0.0), islem="yeni")
    a = ag.Agac((ag.Profil("prf", Plane((0, 0, 0), (0, 0, 1), (1, 0, 0)), (daire(1.0),)), oz))
    d = ag.to_dict(a)
    b = ag.from_dict(json.loads(json.dumps(d)))
    assert ag.to_dict(b) == d
    assert b.ozellikler[1] == oz  # Yol ve parçaları tuple olarak döner


@occt
def test_k7_sweep_json_sonrasi_ayni_hacim(ag):
    a = sweep_agaci(ag, Plane((0, 0, 0), (0, 0, 1), (1, 0, 0)), 5.0, ceyrek_yay(50.0))
    b = ag.from_dict(json.loads(json.dumps(ag.to_dict(a))))
    assert ag.insa(b).part.volume == pytest.approx(ag.insa(a).part.volume, rel=1e-9)


# --- K8: hatalar -----------------------------------------------------------------------------------------


def koseli_yol():
    """İki çizgi, köşede 90°."""
    Cizgi, _, _, Yol = _yol()
    return Yol((Cizgi((0.0, 0.0, 0.0), (0.0, 0.0, 50.0)), Cizgi((0.0, 0.0, 50.0), (50.0, 0.0, 50.0))))


@occt
def test_k8_koseli_yol_teli(sb):
    from geometry.part import GeometryError

    with pytest.raises(GeometryError):
        sb.yol_teli(koseli_yol())


@occt
def test_k8_koseli_yol_agacta(ag):
    a = sweep_agaci(ag, Plane((0, 0, 0), (0, 0, 1), (1, 0, 0)), 5.0, koseli_yol())
    sessiz_gecmez(ag, a, "sw")


@occt
def test_k8_kendini_kesen_helis(ag):
    """Adım 3 < 2r = 4: komşu sarımlar kesişir."""
    a = sweep_agaci(ag, helis_duzlemi(p=3.0), 2.0, helis_yolu(p=3.0, n_tur=16), yonlendirme="frenet")
    sessiz_gecmez(ag, a, "sw")


@occt
def test_k8_kopuk_yol(sb):
    from geometry.part import GeometryError

    Cizgi, _, _, Yol = _yol()
    with pytest.raises(GeometryError):
        sb.yol_teli(
            Yol((Cizgi((0.0, 0.0, 0.0), (0.0, 0.0, 10.0)), Cizgi((0.0, 0.0, 11.0), (0.0, 0.0, 20.0))))
        )


@occt
def test_k8_bos_yol(sb):
    from geometry.part import GeometryError

    _, _, _, Yol = _yol()
    with pytest.raises(GeometryError):
        sb.yol_teli(Yol(()))


@occt
def test_k8_yardimci_vektorsuz(ag):
    a = sweep_agaci(ag, Plane((0, 0, 0), (0, 0, 1), (1, 0, 0)), 5.0, duz_yol(), yonlendirme="yardimci")
    sessiz_gecmez(ag, a, "sw")


@occt
def test_k8_acik_profil_sweep(ag):
    from tests.geometry.serbest_ortak import acik_profil

    a = ag.Agac(
        (
            ag.Profil("prf", Plane((0, 0, 0), (0, 0, 1), (1, 0, 0)), (acik_profil(),)),
            ag.Sweep("sw", "prf", duz_yol(), islem="yeni"),
        )
    )
    sessiz_gecmez(ag, a, "sw")
