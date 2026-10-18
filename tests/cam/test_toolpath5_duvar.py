"""SPEC 42 Ek A (onaylı): duvara doğru eğim regresyonu.

Kural: eksen boyunca indirilen merkez c ile istenen sürüş merkezi c₀ arasındaki fark toleransı aşarsa
(|c − c₀| > tol) bu konum çarpışma sayılır; eğim kaçınma devreye girer, çözüm yoksa CamError.

Düzenek (elle): z = 0 taban üstünde x ∈ [0, 20], y ∈ [−30, 30], z ∈ [0, 40] kapalı blok; x = 0 dik duvar.
Sürüş merkezi duvardan w = 3.5 / 3.6 mm uzakta tabanda (c₀ = (−w, y, R)), küre duvara değmez.
Duvara doğru yana eğimde eksen doğrusu blok üstünden geçer ve eksen boyunca indirme takımı bloğun
üstüne oturtur (c ≠ c₀, sap açıkta). Eski kural bunu çarpışmasız sayıyordu; yeni kuralda reddedilir ve
yalnız duvardan uzağa eğim kalır: sap (ρ = 5, H = 10) için τ* = 11.53° (w = 3.5) ve 10.80° (w = 3.6),
Δτ = 2° adımla seçilen eğim 12°.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.dropcutter import TriMesh
from cam.model import CamError, MoveType, Tool, ToolKind, Toolpath
from cam.multiaxis.toolpath5 import Avoid, Orientation, finish5
from cam.ops3d import Raster

TOL = 1e-9
R = 3.0
FEED = 1000.0


def _blok_agi() -> TriMesh:
    V = [[-60.0, -60.0, 0.0], [60.0, -60.0, 0.0], [60.0, 60.0, 0.0], [-60.0, 60.0, 0.0]]
    V += [[x, y, z] for z in (0.0, 40.0) for y in (-30.0, 30.0) for x in (0.0, 20.0)]

    def k(x, y, z):
        return 4 + x + 2 * y + 4 * z

    T = [[0, 1, 2], [0, 2, 3]]
    for a, b, c, d in (
        (k(0, 0, 1), k(1, 0, 1), k(1, 1, 1), k(0, 1, 1)),  # üst
        (k(0, 0, 0), k(0, 1, 0), k(0, 1, 1), k(0, 0, 1)),  # x = 0 duvarı
        (k(1, 0, 0), k(1, 1, 0), k(1, 1, 1), k(1, 0, 1)),  # x = 20
        (k(0, 0, 0), k(1, 0, 0), k(1, 0, 1), k(0, 0, 1)),  # y = −30
        (k(0, 1, 0), k(1, 1, 0), k(1, 1, 1), k(0, 1, 1)),  # y = 30
    ):
        T += [[a, b, c], [a, c, d]]
    return TriMesh(V=np.array(V), T=np.array(T))


def _takim() -> Tool:
    # küresel uç R = 3; sap basamağı (ρ, H) = (5, 10)
    return Tool(id=1, name="K6", kind=ToolKind.BALL, D=2 * R, flute_length=10.0, shank_d=10.0)


def _raster(ymin: float = -50.0, ymax: float = 50.0) -> Raster:
    return Raster(
        xmin=-3.6,
        xmax=-3.5,
        ymin=ymin,
        ymax=ymax,
        stepover=0.1,
        ds=2.0,
        tol=0.01,
        ds_min=0.25,
        feed=FEED,
        plunge_feed=300.0,
        rpm=12000.0,
        z_safe=80.0,
        direction="y",
    )


def _kesme(tp: Toolpath) -> tuple[np.ndarray, np.ndarray]:
    P, A = [], []
    for m in tp.moves:
        if m.type is MoveType.LINEAR and m.feed == FEED:
            P.append(m.end)
            A.append(m.axis)
    assert P, "kesme hareketi yok"
    return np.array(P, dtype=float), np.array(A, dtype=float)


def _aci(u, v) -> float:
    return math.degrees(math.atan2(np.linalg.norm(np.cross(u, v)), float(np.dot(u, v))))


def _duvar_payi(tau_deg: float, w: float, H: float = 10.0, rho: float = 5.0) -> float:
    """Duvardan uzağa τ eğimde, eksenel H yüksekliğindeki duvar noktasının eksene uzaklığı − ρ."""
    s, c = math.sin(math.radians(tau_deg)), math.cos(math.radians(tau_deg))
    dx = w - R * s
    return dx * c + s * (H + dx * s) / c - rho


def test_duvara_dogru_egim_blok_ustune_oturmuyor():
    adim = 2.0
    for w in (3.5, 3.6):  # elle: τ* ∈ (10°, 12°) → 6. adım
        assert _duvar_payi(10.0, w) < 0.0 < _duvar_payi(12.0, w)
    tp = finish5(_blok_agi(), _takim(), _raster(), Orientation("normal"), Avoid(dtilt=adim), max_dangle=90.0)
    U, A = _kesme(tp)
    C = U + R * A
    # hiçbir nokta blok üstüne / duvara oturmuyor: merkez her yerde tabanda, sürüş noktasında (c = c₀)
    np.testing.assert_allclose(C[:, 2], R, atol=TOL)
    sira = (np.abs(C[:, 0] + 3.5) < TOL) | (np.abs(C[:, 0] + 3.6) < TOL)
    uc = (np.abs(C[:, 1] + 50.0) < TOL) | (np.abs(C[:, 1] - 50.0) < TOL)
    assert np.all(sira | uc)
    orta = np.abs(C[:, 1]) <= 20.0
    assert orta.sum() >= 10
    for a in A[orta]:
        assert abs(_aci(a, (0.0, 0.0, 1.0)) - 12.0) < TOL
        assert a[0] < 0.0  # duvardan uzağa
        assert abs(a[1]) < TOL


def test_duvara_dogru_egim_kacinilamaz_hata():
    # uzağa 10°'ye kadar sap çarpar, duvara doğru eğimler c ≠ c₀ → çözüm yok
    with pytest.raises(CamError):
        finish5(
            _blok_agi(),
            _takim(),
            _raster(),
            Orientation("normal"),
            Avoid(dtilt=2.0, tilt_max=10.0),
            max_dangle=90.0,
        )


def test_sabit_eksen_duvara_dogru_sessiz_gecmiyor():
    # Sabit eksen duvara doğru 10° (+X): eksen doğrusu z = 40'ta x ≈ 3'te, takım bloğun üstüne oturur.
    # Ya CamError, ya da her nokta c = c₀ (tabanda) olmalı; c ≠ c₀ ile sessiz yol kabul edilmez.
    t = math.radians(10.0)
    o = Orientation("sabit", a=(math.sin(t), 0.0, math.cos(t)))
    try:
        tp = finish5(_blok_agi(), _takim(), _raster(-20.0, 20.0), o, Avoid(), max_dangle=90.0)
    except CamError:
        return
    U, A = _kesme(tp)
    np.testing.assert_allclose((U + R * A)[:, 2], R, atol=TOL)


def test_ek_a_sabit_eksen_duvara_10_derece_avoid_yokken_hata():
    # Ek A kabulü: duvar dibinde duvara 10° eğik sabit eksen, Avoid yok → c ≠ c₀ → CamError
    t = math.radians(10.0)
    o = Orientation("sabit", a=(math.sin(t), 0.0, math.cos(t)))
    with pytest.raises(CamError):
        finish5(_blok_agi(), _takim(), _raster(-20.0, 20.0), o, max_dangle=90.0)
