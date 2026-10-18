"""SPEC 42 — eş zamanlı 5 eksen ince işleme testleri (K1–K6, K10).

Testler yalnız SPEC 42 metninden, `cam/model.py`, `cam/dropcutter.py` (`TriMesh`, `drop_one`),
`cam/ops3d.py` (`Raster`, `raster_lines`) arayüzlerinden ve analitik geometriden yazıldı;
`cam/multiaxis/toolpath5.py` gövdeleri okunmadı (iskelette NotImplementedError).

Kurallar (SPEC 42 Teori):
- Küresel uçta ölçü noktası takım ucudur; merkez c = uç + R·a (a takım ekseni, uçtan iş miline).
- Düşey drop ile merkez yüzeyi z_c = drop + R; normal ofset yüzeyden.
- normal(λ, τ): a₁ = n cos λ + f sin λ, a = R_f(τ)·a₁. noktaya(P): a = norm(P − c₀), noktadan: norm(c₀ − P).
- Gövde basamağı (ρ, H) çarpışması: z_j > z_uç + H (takım çerçevesinde düz uç drop).

Kesme noktaları: ilerlemesi `Raster.feed` olan G1 hareketleri (dalma `plunge_feed` ile ayrılır).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.dropcutter import TriMesh, drop_one
from cam.model import CamError, MoveType, Tool, ToolKind, Toolpath
from cam.multiaxis.toolpath5 import Avoid, Orientation, drop_along, finish5, surface_normal
from cam.ops3d import Raster, raster_lines

TOL = 1e-9
R = 3.0  # küresel uç yarıçapı
RHO = 30.0  # küre ağı yarıçapı
N_LAT, N_LON = 30, 120  # küre ağı bölmesi: 3° × 3°
DELTA = math.radians(max(90.0 / N_LAT, 360.0 / N_LON))  # ağ kiriş açısı [rad]
FEED, PLUNGE = 1000.0, 300.0


# ---------------------------------------------------------------- ağlar ve takımlar


def _ball(**kw) -> Tool:
    return Tool(id=1, name="K6", kind=ToolKind.BALL, D=2 * R, flute_length=kw.pop("flute_length", 20.0), **kw)


def _duzlem(beta_deg: float = 0.0, z0: float = 0.0, h: float = 60.0) -> TriMesh:
    """z = z0 + x·tan β düzlemi, [−h, h]² üstünde iki üçgen; normal (−sin β, 0, cos β)."""
    t = math.tan(math.radians(beta_deg))
    V = np.array([[x, y, z0 + x * t] for x, y in ((-h, -h), (h, -h), (h, h), (-h, h))])
    return TriMesh(V=V, T=np.array([[0, 1, 2], [0, 2, 3]]))


def _yarim_kure(rho: float = RHO, n_lat: int = N_LAT, n_lon: int = N_LON) -> TriMesh:
    """Merkezi orijinde, z ≥ 0 yarım küre (UV ağı, köşeler küre üstünde)."""
    V = [[0.0, 0.0, rho]]
    for i in range(1, n_lat + 1):
        th = math.radians(90.0 * i / n_lat)
        for j in range(n_lon):
            ph = 2 * math.pi * j / n_lon
            V.append(
                [rho * math.sin(th) * math.cos(ph), rho * math.sin(th) * math.sin(ph), rho * math.cos(th)]
            )

    def k(i: int, j: int) -> int:
        return 1 + (i - 1) * n_lon + j % n_lon

    T = [[0, k(1, j), k(1, j + 1)] for j in range(n_lon)]
    for i in range(1, n_lat):
        for j in range(n_lon):
            T.append([k(i, j), k(i + 1, j), k(i + 1, j + 1)])
            T.append([k(i, j), k(i + 1, j + 1), k(i, j + 1)])
    return TriMesh(V=np.array(V), T=np.array(T))


_KURE = None


def _kure() -> TriMesh:
    global _KURE
    if _KURE is None:
        _KURE = _yarim_kure()
    return _KURE


def _raster(xmin, xmax, ymin, ymax, stepover, direction="x", ds=2.0, z_safe=80.0) -> Raster:
    return Raster(
        xmin=xmin,
        xmax=xmax,
        ymin=ymin,
        ymax=ymax,
        stepover=stepover,
        ds=ds,
        tol=0.01,
        ds_min=0.25,
        feed=FEED,
        plunge_feed=PLUNGE,
        rpm=12000.0,
        z_safe=z_safe,
        direction=direction,
    )


def _yon(tilt_deg: float, az_deg: float = 0.0) -> np.ndarray:
    t, a = math.radians(tilt_deg), math.radians(az_deg)
    return np.array([math.sin(t) * math.cos(a), math.sin(t) * math.sin(a), math.cos(t)])


def _kesme(tp: Toolpath) -> tuple[np.ndarray, np.ndarray]:
    """Kesme hareketlerinin uçları (k, 3) ve eksenleri (k, 3)."""
    P, A = [], []
    for m in tp.moves:
        if m.type is MoveType.LINEAR and m.feed == FEED:
            P.append(m.end)
            A.append(m.axis)
    assert P, "kesme hareketi yok"
    return np.array(P, dtype=float), np.array(A, dtype=float)


def _aci(u, v) -> float:
    """İki birim vektör arası açı [derece]."""
    return math.degrees(math.atan2(np.linalg.norm(np.cross(u, v)), float(np.dot(u, v))))


def _ucgen_uzaklik(p: np.ndarray, mesh: TriMesh) -> float:
    """p noktasının ağa (tüm üçgenler) en küçük uzaklığı."""
    P = np.asarray(mesh.V, dtype=float)[np.asarray(mesh.T)]
    A, B, C = P[:, 0], P[:, 1], P[:, 2]
    n = np.cross(B - A, C - A)
    n /= np.linalg.norm(n, axis=1)[:, None]
    d = np.einsum("ij,ij->i", p - A, n)
    q = p - d[:, None] * n
    ic = np.ones(len(P), dtype=bool)
    for U, W in ((A, B), (B, C), (C, A)):
        ic &= np.einsum("ij,ij->i", np.cross(W - U, q - U), n) >= -1e-12
    best = np.where(ic, np.abs(d), np.inf)
    for U, W in ((A, B), (B, C), (C, A)):
        e = W - U
        t = np.clip(np.einsum("ij,ij->i", p - U, e) / np.einsum("ij,ij->i", e, e), 0.0, 1.0)
        best = np.minimum(best, np.linalg.norm(p - (U + t[:, None] * e), axis=1))
    return float(best.min())


def _ic_nokta(C: np.ndarray, r: Raster) -> np.ndarray:
    """X sıralı rasterde sıra içindeki (uçlardan ds uzak) noktalar."""
    sira = np.min(np.abs(C[:, 1][:, None] - np.array(raster_lines(r))[None, :]), axis=1) < 1e-6
    return sira & (C[:, 0] > r.xmin + r.ds) & (C[:, 0] < r.xmax - r.ds)


# ---------------------------------------------------------------- K1 eksen boyunca drop


@pytest.mark.parametrize("phi", [0.0, 20.0, 45.0, 60.0])
def test_k1_yatay_duzlemde_egik_drop(phi):
    z0 = 5.0
    mesh = _duzlem(0.0, z0)
    for az in (0.0, 70.0, -135.0):
        a = _yon(phi, az)
        point = np.array([1.0, -2.0, 15.0])
        tip = drop_along(mesh, _ball(), point, a)
        assert tip.shape == (3,)
        c = tip + R * a
        assert abs(c[2] - (z0 + R)) < TOL  # merkez z₀ + R'de
        assert abs(tip[2] - (z0 + R * (1.0 - math.cos(math.radians(phi))))) < TOL
        np.testing.assert_allclose(np.cross(c - point, a), 0.0, atol=TOL)  # merkez çizgi üstünde


def test_k1_dusey_eksende_06_drop_ile_ayni():
    tool = _ball()
    for mesh, noktalar in (
        (_duzlem(20.0, 1.0), [(0.0, 0.0), (7.5, -3.0), (-12.0, 9.0)]),
        (_kure(), [(0.0, 0.0), (5.0, 3.0), (-11.0, 8.0), (14.0, -2.5)]),
    ):
        for x, y in noktalar:
            tip = drop_along(mesh, tool, (x, y, 100.0), (0.0, 0.0, 1.0))
            np.testing.assert_allclose(tip, [x, y, drop_one(mesh, tool, x, y)], atol=TOL)


def test_k1_x_ipucu_sonucu_degistirmez():
    mesh = _kure()
    a = _yon(15.0, 30.0)
    t0 = drop_along(mesh, _ball(), (2.0, 1.0, 80.0), a)
    t1 = drop_along(mesh, _ball(), (2.0, 1.0, 80.0), a, x_hint=(0.0, 1.0, 0.0))
    np.testing.assert_allclose(t0, t1, atol=TOL)


# ---------------------------------------------------------------- K2 normal tahmini


@pytest.mark.parametrize("beta", [0.0, 20.0, 45.0])
def test_k2_egik_duzlem_normali(beta):
    mesh = _duzlem(beta, 2.0)
    b = math.radians(beta)
    beklenen = np.array([-math.sin(b), 0.0, math.cos(b)])
    for x, y in ((0.0, 0.0), (8.0, -4.0), (-15.0, 11.0)):
        n = surface_normal(mesh, _ball(), x, y)
        assert n.shape == (3,)
        np.testing.assert_allclose(n, beklenen, atol=TOL)
        np.testing.assert_allclose(surface_normal(mesh, _ball(), x, y, h_n=1.0), beklenen, atol=TOL)


def test_k2_kure_normali_kiris_acisi_icinde():
    mesh = _kure()
    rng = np.random.default_rng(42)
    for _ in range(30):
        x, y = rng.uniform(-15.0, 15.0, size=2)
        n = surface_normal(mesh, _ball(), x, y)
        assert abs(np.linalg.norm(n) - 1.0) < TOL
        # gerçek ofset küre (ρ + R) normali (x, y)'de
        gercek = np.array([x, y, math.sqrt((RHO + R) ** 2 - x * x - y * y)]) / (RHO + R)
        assert math.radians(_aci(n, gercek)) <= DELTA


# ---------------------------------------------------------------- K3 stratejiler


BETA = 20.0
N_EGIK = np.array([-math.sin(math.radians(BETA)), 0.0, math.cos(math.radians(BETA))])
F_EGIK = np.array([math.cos(math.radians(BETA)), 0.0, math.sin(math.radians(BETA))])  # +X sıra yönü


def _egik_yol(orient: Orientation) -> tuple[Toolpath, Raster]:
    r = _raster(-10.0, 10.0, -5.0, 5.0, 10.0)
    # zikzakta ilerleme yönü dönünce öne / yana eğimli eksen sıçrar: süreklilik K6'da sınanır
    return finish5(_duzlem(BETA, 0.0), _ball(), r, orient, max_dangle=180.0), r


def _yol_genel(tp: Toolpath) -> None:
    assert tp.frame is None
    for m in tp.moves:
        assert m.axis is not None
        assert abs(np.linalg.norm(m.axis) - 1.0) < TOL
    tp.validate()


def test_k3_normal_sifir_egim_a_esit_n():
    tp, _ = _egik_yol(Orientation("normal"))
    _yol_genel(tp)
    _, A = _kesme(tp)
    np.testing.assert_allclose(A, np.broadcast_to(N_EGIK, A.shape), atol=TOL)


def test_k3_one_egim():
    lam = 10.0
    tp, r = _egik_yol(Orientation("normal", lead=lam))
    _yol_genel(tp)
    P, A = _kesme(tp)
    np.testing.assert_allclose(A @ N_EGIK, math.cos(math.radians(lam)), atol=TOL)
    C = P + R * A
    ic = _ic_nokta(C, r)
    assert ic.sum() >= 6
    for i in np.flatnonzero(ic):
        yon = math.copysign(1.0, C[i + 1, 0] - C[i - 1, 0])  # ilerleme yönü ±X
        f = yon * F_EGIK
        b = np.cross(N_EGIK, f)
        assert abs(A[i] @ b) < TOL  # a·b = 0
        assert abs(A[i] @ f - math.sin(math.radians(lam))) < TOL  # eksen ilerleme yönüne doğru


def test_k3_yana_egim():
    tau = 12.0
    tp, r = _egik_yol(Orientation("normal", tilt=tau))
    _yol_genel(tp)
    P, A = _kesme(tp)
    np.testing.assert_allclose(A @ N_EGIK, math.cos(math.radians(tau)), atol=TOL)
    C = P + R * A
    ic = _ic_nokta(C, r)
    assert ic.sum() >= 6
    np.testing.assert_allclose(A[ic] @ F_EGIK, 0.0, atol=TOL)  # a·f = 0


@pytest.mark.parametrize("kind,P", [("noktaya", (5.0, 3.0, 200.0)), ("noktadan", (-4.0, 2.0, -150.0))])
def test_k3_noktaya_noktadan(kind, P):
    tp, _ = _egik_yol(Orientation(kind, point=P))
    _yol_genel(tp)
    U, A = _kesme(tp)
    P = np.array(P)
    for u, a in zip(U, A, strict=True):
        c = u + R * a
        d = P - c
        assert np.linalg.norm(np.cross(d / np.linalg.norm(d), a)) < TOL  # P eksen doğrusu üstünde
        assert (d @ a > 0) == (kind == "noktaya")


def test_k3_sabit_eksen():
    a = _yon(10.0, 40.0)
    tp, _ = _egik_yol(Orientation("sabit", a=tuple(a)))
    _yol_genel(tp)
    _, A = _kesme(tp)
    np.testing.assert_allclose(A, np.broadcast_to(a, A.shape), atol=TOL)


def test_k3_max_tilt_asimi():
    with pytest.raises(CamError):
        _egik_yol(Orientation("sabit", a=tuple(_yon(45.0)), max_tilt=30.0))
    with pytest.raises(CamError):  # n 20° + öne 15° = 35° > 30°
        _egik_yol(Orientation("normal", lead=15.0, max_tilt=30.0))
    with pytest.raises(CamError):  # nokta yana çok uzakta: eksen yataya yakın
        _egik_yol(Orientation("noktaya", point=(1000.0, 0.0, 10.0), max_tilt=60.0))


# ---------------------------------------------------------------- K4 konum, çakmazlık

# Orientation iskelette NotImplementedError: toplama aşamasında kurulmasın diye alanlar sözlükte
STRATEJILER = [
    {"kind": "normal"},
    {"kind": "normal", "lead": 8.0, "tilt": 5.0},
    {"kind": "noktaya", "point": (3.0, -2.0, 300.0)},
    {"kind": "sabit", "a": tuple(_yon(10.0, -60.0))},
]


@pytest.mark.parametrize("orient", STRATEJILER, ids=["normal", "egimli", "noktaya", "sabit"])
def test_k4_egik_duzlemde_merkez_c0(orient):
    orient = Orientation(**orient)
    mesh = _duzlem(BETA, 0.0)
    r = _raster(-10.0, 10.0, -5.0, 5.0, 10.0)
    tp = finish5(mesh, _ball(), r, orient, max_dangle=180.0)
    U, A = _kesme(tp)
    C = U + R * A
    satir = np.min(np.abs(C[:, 1][:, None] - np.array(raster_lines(r))[None, :]), axis=1) < TOL
    uc = (np.abs(C[:, 0] - r.xmin) < TOL) | (np.abs(C[:, 0] - r.xmax) < TOL)
    assert np.all(satir | uc)  # merkez sürüş noktasının üstünde (sıra ya da sıra ucu geçişi)
    for c in C:
        assert abs(c[2] - (drop_one(mesh, _ball(), c[0], c[1]) + R)) < TOL  # c = c₀
        assert _ucgen_uzaklik(c, mesh) >= R - TOL  # çakma yok


@pytest.mark.parametrize("orient", STRATEJILER, ids=["normal", "egimli", "noktaya", "sabit"])
def test_k4_kurede_merkez_c0(orient):
    orient = Orientation(**orient)
    mesh = _kure()
    r = _raster(-12.0, 12.0, -12.0, 12.0, 6.0, ds=1.5)
    tp = finish5(mesh, _ball(), r, orient, max_dangle=180.0)
    U, A = _kesme(tp)
    C = U + R * A
    kiris = RHO * (1.0 - math.cos(DELTA))  # ağın küreden en büyük içeri sapması (cömert)
    d = np.linalg.norm(C, axis=1)
    assert np.all(d <= RHO + R + TOL)
    assert np.all(d >= RHO * math.cos(DELTA) + R - TOL)
    satir = np.min(np.abs(C[:, 1][:, None] - np.array(raster_lines(r))[None, :]), axis=1) <= kiris
    uc = (np.abs(C[:, 0] - r.xmin) <= kiris) | (np.abs(C[:, 0] - r.xmax) <= kiris)
    assert np.all(satir | uc)
    for c in C[:: max(1, len(C) // 60)]:
        assert _ucgen_uzaklik(c, mesh) >= R - TOL  # çakma yok


# ---------------------------------------------------------------- K5 gövde çarpışması


def _duvar_agi() -> TriMesh:
    """z = 0 taban ([−60, 60]²) ve x = 0'da dik duvar yüzü (y ∈ [−30, 30], z ∈ [0, 300]).

    Duvar yüksek ve tek yüzdür: duvara doğru yana eğimde eksen çizgisi duvar yüzünü deler, eksen boyunca
    drop takımı duvarın arkasına oturtur ve sap yine duvarı keser (çarpışma); yalnız duvardan uzağa eğim
    çarpışmasızdır. Böylece seçilecek eğim elle hesaplanabilir.
    """
    V = np.array(
        [
            [-60.0, -60.0, 0.0],
            [60.0, -60.0, 0.0],
            [60.0, 60.0, 0.0],
            [-60.0, 60.0, 0.0],
            [0.0, -30.0, 0.0],
            [0.0, 30.0, 0.0],
            [0.0, 30.0, 300.0],
            [0.0, -30.0, 300.0],
        ]
    )
    return TriMesh(V=V, T=np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]))


def _sap_takimi() -> Tool:
    # Sap basamağı (ρ, H) = (shank/2, flute_length) = (5, 10)
    return _ball(flute_length=10.0, shank_d=10.0)


def _duvar_payi(tau_deg: float, w: float, H: float = 10.0, rho: float = 5.0) -> float:
    """Duvardan w uzaktaki merkezle (taban teması), duvardan uzağa τ eğik eksende sapın duvara
    radyal payı − ρ: eksenel yükseklik H olan duvar noktasının eksene uzaklığı − ρ (< 0 → çarpışma).

    a = (−sin τ, 0, cos τ), uç p = c − R·a; duvar noktası d = (w − R sin τ, z − R + R cos τ) (uca göre),
    eksenel d·a = H'den z bulunur, radyal d·e (e = (cos τ, sin τ)).
    """
    s, c = math.sin(math.radians(tau_deg)), math.cos(math.radians(tau_deg))
    dx = w - R * s
    return dx * c + s * (H + dx * s) / c - rho


def _beklenen_egim(w: float, adim: float) -> float:
    k = 1
    while _duvar_payi(k * adim, w) < 1e-6:
        k += 1
    return k * adim


def _duvar_rasteri() -> Raster:
    return _raster(-3.6, -3.5, -50.0, 50.0, 0.1, direction="y", z_safe=80.0)


def test_k5_dik_eksende_sap_duvara_carpiyor():
    # 06 düz uç drop (ρ = 5) ile: z_j = 300 > z_uç + H = 0 + 10
    duz = Tool(id=9, name="D10", kind=ToolKind.FLAT, D=10.0, flute_length=10.0)
    mesh = _duvar_agi()
    for x in (-3.6, -3.5):
        assert drop_one(mesh, _sap_takimi(), x, 0.0) == pytest.approx(0.0, abs=TOL)  # küre duvara değmiyor
        assert drop_one(mesh, duz, x, 0.0) > 0.0 + 10.0
        assert _duvar_payi(0.0, -x) < 0.0


def test_k5_kacinma_en_kucuk_yana_egim():
    adim = 2.0
    beklenen = {w: _beklenen_egim(w, adim) for w in (3.5, 3.6)}
    assert beklenen == {3.5: 12.0, 3.6: 12.0}  # elle: τ* = 11.53° ve 10.80° → 6. adım
    tp = finish5(
        _duvar_agi(),
        _sap_takimi(),
        _duvar_rasteri(),
        Orientation("normal"),
        Avoid(dtilt=adim),
        max_dangle=90.0,
    )
    _yol_genel(tp)
    U, A = _kesme(tp)
    C = U + R * A
    orta = np.abs(C[:, 1]) <= 20.0
    uzak = np.abs(C[:, 1]) >= 40.0
    assert orta.sum() >= 10 and uzak.sum() >= 4
    for c, a in zip(C[orta], A[orta], strict=True):
        assert abs(_aci(a, (0.0, 0.0, 1.0)) - beklenen[round(-c[0], 1)]) < TOL
        assert a[0] < 0.0  # duvardan uzağa
        assert abs(a[1]) < TOL  # f (±Y) etrafında yana eğim
        assert abs(c[2] - R) < TOL  # taban teması değişmedi
    np.testing.assert_allclose(A[uzak], np.broadcast_to((0.0, 0.0, 1.0), A[uzak].shape), atol=TOL)


def test_k5_kacinilamaz_hata():
    with pytest.raises(CamError):
        finish5(
            _duvar_agi(),
            _sap_takimi(),
            _duvar_rasteri(),
            Orientation("normal"),
            Avoid(dtilt=2.0, tilt_max=10.0),
            max_dangle=90.0,
        )


# ---------------------------------------------------------------- K6 süreklilik


@pytest.mark.parametrize("max_dangle", [5.0, 2.0])
def test_k6_yarim_kurede_noktadan_merkez(max_dangle):
    mesh = _kure()
    r = _raster(-15.0, 15.0, -15.0, 15.0, 5.0, ds=3.0)
    tp = finish5(mesh, _ball(), r, Orientation("noktadan", point=(0.0, 0.0, 0.0)), max_dangle=max_dangle)
    _yol_genel(tp)
    U, A = _kesme(tp)
    for a0, a1 in zip(A[:-1], A[1:], strict=True):
        assert _aci(a0, a1) <= max_dangle + 1e-9
    C = U + R * A
    # eksen merkezden radyal: a ∥ c₀ − O
    np.testing.assert_allclose(
        np.linalg.norm(np.cross(C / np.linalg.norm(C, axis=1)[:, None], A), axis=1), 0.0, atol=TOL
    )


# ---------------------------------------------------------------- K10 hatalar


def test_k10_ball_disi_takim():
    duz = Tool(id=2, name="D6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)
    with pytest.raises(CamError):
        finish5(_duzlem(), duz, _raster(-5.0, 5.0, -5.0, 5.0, 5.0), Orientation("normal"))


def test_k10_sifir_eksen():
    with pytest.raises(CamError):
        drop_along(_duzlem(), _ball(), (0.0, 0.0, 10.0), (0.0, 0.0, 0.0))
    with pytest.raises(CamError):
        Orientation("sabit", a=(0.0, 0.0, 0.0))


def test_k10_agla_ortusme_yok():
    with pytest.raises(CamError):
        drop_along(_duzlem(h=10.0), _ball(), (500.0, 0.0, 10.0), (0.0, 0.0, 1.0))


@pytest.mark.parametrize(
    "kw",
    [
        {"kind": "bilinmeyen"},
        {"kind": "sabit"},  # a eksik
        {"kind": "noktaya"},  # point eksik
        {"kind": "noktadan"},  # point eksik
        {"kind": "sabit", "a": (0.0, 0.0, 1.0), "point": (0.0, 0.0, 9.0)},  # fazla alan
        {"kind": "normal", "a": (0.0, 0.0, 1.0)},  # fazla alan
        {"kind": "noktaya", "point": (0.0, 0.0, 9.0), "a": (0.0, 0.0, 1.0)},  # fazla alan
        {"kind": "normal", "lead": float("nan")},
    ],
)
def test_k10_gecersiz_orientation(kw):
    with pytest.raises(CamError):
        Orientation(**kw)


@pytest.mark.parametrize(
    "kw",
    [{"dtilt": 0.0}, {"dtilt": -1.0}, {"tilt_max": -5.0}, {"tol": -1e-6}, {"dtilt": float("nan")}],
)
def test_k10_gecersiz_avoid(kw):
    with pytest.raises(CamError):
        Avoid(**kw)


def test_k10_gecerli_orientation_avoid():
    Orientation("sabit", a=(0.0, 0.0, 1.0))
    Orientation("normal", lead=5.0, tilt=-3.0)
    Orientation("noktaya", point=(0.0, 0.0, 100.0))
    Orientation("noktadan", point=(0.0, 0.0, -100.0))
    Avoid()
    Avoid(dtilt=1.0, tilt_max=20.0, tol=1e-4)
