"""SPEC 10 — K14 bağlama elemanlarının OCCT katısı (`primitives_part`) ve OCCT ile denetimler.

Testler sadece SPEC 10 metninden yazıldı; `geometry/baglama_parca.py` ve `cam/baglama.py` uygulama kodu
okunmadı.
Hacimler SPEC 10 Teori formüllerinden (mengene 666000 mm³; ayna π (D_b/2)² L_b + 3·h·w_j·L_j; pabuç
L_a w_a t_a + w_h w_a H_s + π (d_b/2)² (H_s + h_c), cıvatanın koldaki boyu bir kez), göreli 1e-9.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d")

from cam.model import CamError  # noqa: E402
from geometry.baglama_parca import primitives_part  # noqa: E402
from geometry.part import GeometryError, Part  # noqa: E402
from tests.cam.baglama_ara import (  # noqa: E402
    Fixture,
    FixtureMap,
    check_clamping,
    chuck_for,
    clamp_for,
    fixture_map,
    make_fixture,
    mesh_topmap,
    primitive_topmap,
    primitives_wcs,
    vise_for,
)
from tests.cam.baglama_ref import (  # noqa: E402
    CHUCK_GRIP,
    CHUCK_OLCU,
    CHUCK_STOK,
    CLAMP_OLCU,
    STOK,
    VISE_GRIP,
    VISE_OLCU,
    frame,
    prim_aabb,
)

pytestmark = pytest.mark.occt


def mengene():
    v, fr = vise_for(STOK, VISE_GRIP, "x", **VISE_OLCU)
    return v, fr, make_fixture("mengene", v, fr)


def ayna():
    c, fr = chuck_for(CHUCK_STOK, CHUCK_GRIP, **CHUCK_OLCU)
    return c, fr, make_fixture("ayna", c, fr)


def pabuc():
    c, fr = clamp_for(STOK, "y-", 40.0, 8.0, **CLAMP_OLCU)
    return c, fr, make_fixture("pabuc", c, fr)


def kati(fx) -> Part:
    return primitives_part([p.to_dict() for p in primitives_wcs(fx)], fx.name)


def birlesim_kutusu(prims) -> tuple[np.ndarray, np.ndarray]:
    kutular = [prim_aabb(p) for p in prims]
    return np.min([k[0] for k in kutular], axis=0), np.max([k[1] for k in kutular], axis=0)


@pytest.mark.parametrize(
    ("uret", "V"),
    [
        (mengene, 666000.0),
        (ayna, math.pi * 80**2 * 80 + 3 * 25 * 20 * 20),
        (pabuc, 80 * 20 * 12 + 15 * 20 * 30 + math.pi * 6**2 * (30 + 15)),
    ],
    ids=["mengene", "ayna", "pabuc"],
)
def test_k14_hacim_ve_sinir_kutusu(uret, V):
    _, _, fx = uret()
    p = kati(fx)
    assert isinstance(p, Part)
    assert p.name == fx.name
    assert p.volume == pytest.approx(V, rel=1e-9)
    lo, hi = p.bbox
    blo, bhi = birlesim_kutusu(primitives_wcs(fx))
    np.testing.assert_allclose(lo, blo, atol=1e-9, rtol=0)
    np.testing.assert_allclose(hi, bhi, atol=1e-9, rtol=0)


def test_k14_mengene_sinir_kutusu_degerleri():
    # Teori: x ∈ [−10, 90], y ∈ [−20, 130], z ∈ [−45, 10]
    lo, hi = kati(mengene()[2]).bbox
    np.testing.assert_allclose(lo, (-10, -20, -45), atol=1e-9, rtol=0)
    np.testing.assert_allclose(hi, (90, 130, 10), atol=1e-9, rtol=0)


def test_k14_tek_silindir():
    d = {
        "shape": {"type": "silindir", "D": 10.0, "zmin": 0.0, "zmax": 7.0, "d": 0.0},
        "frame": frame().to_dict(),
    }
    p = primitives_part([d], "silindir")
    assert p.volume == pytest.approx(math.pi * 25 * 7, rel=1e-9)


def hizasiz_izgara() -> FixtureMap:
    # x0 = −10.9, y0 = −21.1, Δ = 2.33; mengene yüzleri (x: −10, 90; y: −20, 0, 6, 44, 50, 70, 130) içeride
    nx, ny = 44, 66
    return FixtureMap("hizasiz", -10.9, -21.1, 2.33, 2.33, nx, ny, np.full((ny, nx), -np.inf))


def test_k14_mengene_agi_ilkel_haritasiyla_ayni():
    v, fr, fx = mengene()
    g = hizasiz_izgara()
    # ön koşul: yüzler hücre sınırlarından 1e-6'dan uzak
    for x in (-10.0, 90.0):
        k = (x - g.x0) / g.dx
        assert abs(k - round(k)) * g.dx > 1e-6
    for y in (-20.0, 0.0, 6.0, 44.0, 50.0, 70.0, 130.0):
        k = (y - g.y0) / g.dy
        assert abs(k - round(k)) * g.dy > 1e-6
    yerel = primitives_part([p.to_dict() for p in v.primitives()], "mengene_yerel")
    V, F = yerel.mesh()
    agdan = mesh_topmap(V, F, fr, g)
    ilkelden = primitive_topmap(primitives_wcs(fx), g)
    np.testing.assert_array_equal(agdan, ilkelden)


def test_k14_ozel_fikstur_haritasi_kutuphaneyle_ayni():
    v, fr, fx = mengene()
    parts = {"mengene_p": primitives_part([p.to_dict() for p in v.primitives()], "mengene_p")}
    ozel = Fixture(name="ozel_m", part_ref="mengene_p", frame=fr, kind="ozel")
    # cell = 2.21 → dx = 100/46, dy = 150/68; iç yüzler (y = 0, 6, 44, 50, 70) sınırlardan ≥ 0.02 uzak
    a = fixture_map(ozel, 2.21, parts)
    b = fixture_map(fx, 2.21)
    assert (a.nx, a.ny) == (b.nx, b.ny)
    assert (a.x0, a.y0, a.dx, a.dy) == pytest.approx((b.x0, b.y0, b.dx, b.dy), abs=1e-9)
    np.testing.assert_array_equal(a.top, b.top)


def test_k14_ozel_fikstur_sikma_part_common():
    v, fr, _ = mengene()
    parts = {"mengene_p": primitives_part([p.to_dict() for p in v.primitives()], "mengene_p")}
    ozel = Fixture(name="ozel_m", part_ref="mengene_p", frame=fr, kind="ozel")
    # değen stok: kesişim hacmi ≤ tol_v → geçer
    assert check_clamping(STOK, [ozel], parts) is None
    # 1 mm içeri (+Y): sabit çene stoğa 1 mm girer → kesişim 100 × 1 × 15 > tol_v
    o = fr.origin
    kaymis = Fixture(
        name="ozel_m", part_ref="mengene_p", frame=frame((o[0], o[1] + 1.0, o[2]), fr.R), kind="ozel"
    )
    with pytest.raises(CamError, match="ozel_m"):
        check_clamping(STOK, [kaymis], parts)


KUTU = {"type": "kutu", "xmin": 0.0, "ymin": 0.0, "zmin": 0.0, "xmax": 1.0, "ymax": 2.0, "zmax": 3.0}
BIRIM = {"origin": [0.0, 0.0, 0.0], "R": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]}


@pytest.mark.parametrize(
    "prims",
    [
        [],
        [{"shape": dict(KUTU, type="koni"), "frame": BIRIM}],
        [{"shape": {k: v for k, v in KUTU.items() if k != "zmax"}, "frame": BIRIM}],
        [{"shape": KUTU}],
        [{"shape": KUTU, "frame": {"origin": [0, 0, 0], "R": [[2, 0, 0], [0, 2, 0], [0, 0, 2]]}}],
        [{"shape": KUTU, "frame": {"origin": [0, 0, 0], "R": [[1, 0, 0], [0, 1, 0], [0, 0, -1]]}}],
    ],
    ids=["bos", "bilinmeyen_tur", "eksik_alan", "cercevesiz", "olcekli_R", "yansima_R"],
)
def test_k14_gecersiz_sozlukler(prims):
    with pytest.raises(GeometryError):
        primitives_part(prims, "hatali")
