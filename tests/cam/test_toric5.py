"""SPEC 50 — torik uçla 5 eksen serbest eğim testleri (K6, K7, K9'un finish5 kısmı).

Testler yalnız SPEC 50 metninden, `cam/model.py`, `cam/dropcutter.py` (`TriMesh`, `drop_one`), `cam/ops3d.py`
(`Raster`) ve `cam/multiaxis/toolpath5.py` arayüzlerinden (`finish5`, `Orientation`) ve analitik
geometriden yazıldı; kod gövdeleri okunmadı.

Kurallar (SPEC 50 Teori, Arayüz):
- `finish5` `tool.kind = FLAT` ve `corner_r > 0` (torik) kabul eder; `corner_r = 0` düz uç → `CamError`.
- Ölçü noktası takım ucudur (eksen ucu); a takım ekseni (uçtan iş miline).
- Yatay düzleme φ eğik eksenle değen torik takımda z_uç − z₀ = r_c(1 − cos φ) + (R − r_c) sin φ.
  Türetme: tor merkez çemberinin en alt noktası z_uç + r_c cos φ − (R − r_c) sin φ;
  tüp yarıçapı r_c çıkınca düzlem.
- Genel düzlemde (birim normal N, yukarı) takımın N yönündeki en alt noktası
  N·uç + r_c (N·a) − (R − r_c)|N − (N·a)a| − r_c (aynı türetme, N_⊥ = N − (N·a)a).

Torik dal SPEC 50 kodunda gelir; iskelette `finish5` yalnız küresel uç kabul ettiği için olumlu testler
`xfail(strict=True)` ile işaretli (kod yazılınca işaret kaldırılır).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.dropcutter import TriMesh, drop_one
from cam.model import CamError, MoveType, Tool, ToolKind
from cam.multiaxis.toolpath5 import Orientation, finish5
from cam.ops3d import Raster
from tests.cam.ref3d import sample_triangles, sphere_cap_mesh

R, RC = 5.0, 1.0  # torik takım: dış yarıçap, köşe radyüsü
FLUTE = 20.0
FEED, PLUNGE, RPM = 1000.0, 300.0, 8000.0
TORIK_YOK = pytest.mark.xfail(strict=True, reason="SPEC 50 torik finish5 dalı henüz yok (iskelet)")


def _torik(corner_r: float = RC) -> Tool:
    return Tool(id=1, name="torik", kind=ToolKind.FLAT, D=2 * R, flute_length=FLUTE, corner_r=corner_r)


def _duzlem(beta_deg: float = 0.0, z0: float = 0.0, h: float = 60.0) -> TriMesh:
    """z = z0 + x·tan β düzlemi, [−h, h]² üstünde iki üçgen; birim normal (−sin β, 0, cos β)."""
    t = math.tan(math.radians(beta_deg))
    V = np.array([[x, y, z0 + x * t] for x, y in ((-h, -h), (h, -h), (h, h), (-h, h))])
    return TriMesh(V=V, T=np.array([[0, 1, 2], [0, 2, 3]]))


def _raster(lim: float = 10.0, stepover: float = 5.0, z_safe: float = 60.0) -> Raster:
    return Raster(
        xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, stepover=stepover, ds=2.0, tol=0.01, ds_min=0.5,
        feed=FEED, plunge_feed=PLUNGE, rpm=RPM, z_safe=z_safe,
    )  # fmt: skip


def _eksen(phi_deg: float) -> tuple[float, float, float]:
    p = math.radians(phi_deg)
    return (math.sin(p), 0.0, math.cos(p))


def _kesme(tp) -> list:
    """Kesme noktaları: ilerlemesi Raster.feed olan G1 hareketleri (dalma plunge_feed ile ayrılır)."""
    return [m for m in tp.moves if m.type is MoveType.LINEAR and m.feed == pytest.approx(FEED)]


def _uc_yuksekligi(phi_deg: float) -> float:
    p = math.radians(phi_deg)
    return RC * (1.0 - math.cos(p)) + (R - RC) * math.sin(p)


def _en_alt(N: np.ndarray, uc: np.ndarray, a: np.ndarray) -> float:
    """Torik takımın N yönündeki en küçük N·x değeri (modül belgesindeki formül)."""
    Na = float(N @ a)
    Nd = float(np.linalg.norm(N - Na * a))
    return float(N @ uc) + RC * Na - (R - RC) * Nd - RC


def _girme(Q: np.ndarray, uc: np.ndarray, a: np.ndarray) -> float:
    """Q noktalarının torik takım katısına en büyük girmesi (girme yoksa ≤ 0).

    Takım koordinatında h = (q − uç)·a, r = |q − uç − h a|. Katı: h ∈ [0, FLUTE];
    r ≤ R − r_c iken tabandan h kadar içeride; r > R − r_c, h < r_c iken köşe torunun
    içinde r_c − |(r − (R − r_c), h − r_c)|;
    h ≥ r_c iken R − r.
    """
    d = Q - uc
    h = d @ a
    r = np.linalg.norm(d - np.outer(h, a), axis=1)
    ic = (h > 0) & (h < FLUTE)
    if not np.any(ic):
        return -np.inf
    h, r = h[ic], r[ic]
    derin = np.where(
        h >= RC,
        R - r,
        np.where(r <= R - RC, np.minimum(h, R - r), RC - np.hypot(r - (R - RC), h - RC)),
    )
    return float(np.max(derin))


# ---------------------------------------------------------------- K6


@TORIK_YOK
@pytest.mark.parametrize("phi", [0.0, 10.0, 30.0, 60.0])
def test_k6_yatay_duzlemde_uc_yuksekligi(phi):
    z0 = 2.5
    tp = finish5(_duzlem(0.0, z0), _torik(), _raster(), Orientation("sabit", a=_eksen(phi)))
    kes = _kesme(tp)
    assert kes
    for m in kes:
        assert m.end[2] - z0 == pytest.approx(_uc_yuksekligi(phi), abs=1e-9)
        np.testing.assert_allclose(m.axis, _eksen(phi), atol=1e-12)


def test_k6_formul_degerleri():
    """Formülün kendisi (R = 5, r_c = 1): beklenen sayılar SPEC 50 test planında elle hesaplandı."""
    for phi, h in (
        (0.0, 0.0),
        (10.0, 0.7097849576555133),
        (30.0, 2.133974596215561),
        (60.0, 3.9641016151377544),
    ):
        assert _uc_yuksekligi(phi) == pytest.approx(h, abs=1e-12)
        # genel düzlem formülü yatay düzlemde aynı sonucu verir
        assert -_en_alt(np.array([0.0, 0.0, 1.0]), np.zeros(3), np.array(_eksen(phi))) == pytest.approx(
            h, abs=1e-12
        )


@TORIK_YOK
def test_k6_dik_eksen_06_drop_ile_birebir():
    """φ = 0: eksen +Z, 5 eksen yol 06 torik (düz uç köşe radyüslü) drop ile aynı uç yüksekliği."""
    mesh = _duzlem(12.0, 1.0)
    tool = _torik()
    tp = finish5(mesh, tool, _raster(), Orientation("sabit", a=(0.0, 0.0, 1.0)))
    kes = _kesme(tp)
    assert kes
    for m in kes:
        assert m.end[2] == pytest.approx(drop_one(mesh, tool, m.end[0], m.end[1]), abs=1e-9)


# ---------------------------------------------------------------- K7


@TORIK_YOK
@pytest.mark.parametrize(("beta", "phi"), [(20.0, -15.0), (20.0, 35.0), (35.0, 10.0)])
def test_k7_egik_duzlemde_temas_ve_cakmazlik(beta, phi):
    """Düzlem z = x tan β: en alt nokta düzlemde (temas) ve altında değil (çakma yok), 1e-9."""
    b = math.radians(beta)
    N = np.array([-math.sin(b), 0.0, math.cos(b)])
    tp = finish5(_duzlem(beta), _torik(), _raster(), Orientation("sabit", a=_eksen(phi)))
    kes = _kesme(tp)
    assert kes
    for m in kes:
        assert _en_alt(N, np.array(m.end), np.array(m.axis)) == pytest.approx(0.0, abs=1e-9)


_KURE = None


def _kure() -> tuple[TriMesh, np.ndarray]:
    """ρ = 30 yarım küre (3° × 3° ağ) ve üçgenlerden yoğun örnek noktaları."""
    global _KURE
    if _KURE is None:
        V, T = sphere_cap_mesh(30.0, math.pi / 2, 30, 120)
        _KURE = (TriMesh(V=V, T=T), sample_triangles(V, T, 6))
    return _KURE


@TORIK_YOK
@pytest.mark.parametrize(
    "orient",
    [Orientation("normal", lead=10.0), Orientation("sabit", a=_eksen(20.0))],
    ids=["normal-lead10", "sabit-20"],
)
def test_k7_kurede_cakmazlik(orient):
    mesh, Q = _kure()
    # max_dangle = 15°: satır dönüşünde lead ekseni ≈ 10° döner (SPEC 42 kuralı, ds_min = 0.5'te bölünemez);
    # çakmazlık denetimi bu parametreden bağımsız
    tp = finish5(mesh, _torik(), _raster(lim=12.0, stepover=4.0), orient, max_dangle=15.0)
    kes = _kesme(tp)
    assert kes
    for m in kes:
        uc, a = np.array(m.end), np.array(m.axis)
        yakin = Q[np.linalg.norm(Q - uc, axis=1) < R + FLUTE]
        assert _girme(yakin, uc, a) <= 1e-9


# ---------------------------------------------------------------- K9 (finish5)


def test_k9_duz_uc_finish5_hata():
    """corner_r = 0 düz uç → CamError (torik değil, küresel değil)."""
    with pytest.raises(CamError):
        finish5(_duzlem(), _torik(corner_r=0.0), _raster(), Orientation("sabit", a=(0.0, 0.0, 1.0)))
