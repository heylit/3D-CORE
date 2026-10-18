"""
SPEC 15 — viz.scene doğrulama testleri (K1–K9).

Beklenen değerler SPEC 15 "Teori" bölümünden türetilir, viz/ kodu okunmadan yazıldı:
- yay çokgeni: n = max(1, ⌈|Δθ| / min(φ_max, π/2)⌉), φ_max = 2 arccos(1 − tol/r);
  sagitta s = r (1 − cos(φ/2)); helis z açıyla doğrusal
- montaj: p' = R p + t (Craig, Bölüm 2)
- ağ hacmi: V = (1/6) Σ p₁ · (p₂ × p₃) (diverjans teoremi)
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from assy.model import Assembly, AssyError, Component, Mate, Ref, rot_z, transform
from cam.model import CamError, Move, MoveType, Stock, Tool, ToolKind, Toolpath
from viz.scene import (
    PALETTE,
    ComponentMesh,
    VizError,
    assembly_meshes,
    split_rapid_feed,
    stock_box,
    toolpath_polyline,
)

TOOL = Tool(id=1, name="T1 d6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)
F = 500.0  # mm/dk


def yol(start, moves) -> Toolpath:
    return Toolpath(name="deneme", tool=TOOL, start=start, moves=moves, rpm=8000.0)


def n_beklenen(dtheta: float, r: float, tol: float) -> int:
    """SPEC 15: n = max(1, ⌈|Δθ| / min(φ_max, π/2)⌉)."""
    phi_max = math.pi if tol >= r else 2 * math.acos(1 - tol / r)
    return max(1, math.ceil(dtheta / min(phi_max, math.pi / 2)))


def poly_boy(P: np.ndarray) -> float:
    return float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())


# ---------- K1: G0 / G1 ----------


def test_k1_dogrusal_yol_noktalari_ve_tipleri():
    tp = yol(
        (0, 0, 10),
        [
            Move(MoveType.RAPID, (0, 0, 5)),
            Move(MoveType.LINEAR, (10, 0, -1), feed=F),
            Move(MoveType.LINEAR, (10, 5, -1), feed=F),
            Move(MoveType.RAPID, (10, 5, 10)),
        ],
    )
    P, kinds = toolpath_polyline(tp)
    np.testing.assert_array_equal(P, tp.points())
    assert list(kinds) == [MoveType.RAPID, MoveType.LINEAR, MoveType.LINEAR, MoveType.RAPID]


# ---------- K2: yay çokgeni ----------

R = 10.0
TOL = 0.01

# (tip, bitiş, süpürme açısı |Δθ|); başlangıç (10, 0, 0), merkez (0, 0)
YAYLAR = [
    (MoveType.ARC_CCW, (0.0, 10.0, 0.0), math.pi / 2),  # G3 çeyrek
    (MoveType.ARC_CW, (0.0, -10.0, 0.0), math.pi / 2),  # G2 çeyrek
    (MoveType.ARC_CCW, (-10.0, 0.0, 0.0), math.pi),  # G3 yarım
    (MoveType.ARC_CW, (-10.0, 0.0, 0.0), math.pi),  # G2 yarım
    (MoveType.ARC_CCW, (10.0, 0.0, 0.0), 2 * math.pi),  # G3 tam daire
    (MoveType.ARC_CW, (10.0, 0.0, 0.0), 2 * math.pi),  # G2 tam daire
]
YAY_ID = ["G3-ceyrek", "G2-ceyrek", "G3-yarim", "G2-yarim", "G3-tam", "G2-tam"]


@pytest.mark.parametrize(("tip", "son", "dtheta"), YAYLAR, ids=YAY_ID)
def test_k2_yay_cokgeni(tip, son, dtheta):
    tp = yol((R, 0, 0), [Move(tip, son, feed=F, center=(0.0, 0.0))])
    P, kinds = toolpath_polyline(tp, tol=TOL)
    n = len(P) - 1

    # parça sayısı formülle aynı
    assert n == n_beklenen(dtheta, R, TOL)
    assert len(kinds) == n
    assert all(k == tip for k in kinds)

    # her nokta merkeze r uzaklıkta
    np.testing.assert_allclose(np.hypot(P[:, 0], P[:, 1]), R, atol=1e-9)

    # en büyük sagitta ≤ tol: kirişin orta noktasının merkeze uzaklığı r − s
    orta = (P[:-1, :2] + P[1:, :2]) / 2
    s = R - np.hypot(orta[:, 0], orta[:, 1])
    assert s.max() <= TOL + 1e-12

    # ilk nokta başlangıç, son nokta hareketin end'i (tam)
    np.testing.assert_array_equal(P[0], tp.start)
    np.testing.assert_array_equal(P[-1], np.array(son))

    # dönüş yönü: G3'te açı artıyor, G2'de azalıyor; toplam süpürme |Δθ|
    theta = np.unwrap(np.arctan2(P[:, 1], P[:, 0]))
    adim = np.diff(theta)
    if tip is MoveType.ARC_CCW:
        assert np.all(adim > 0)
    else:
        assert np.all(adim < 0)
    assert abs(abs(theta[-1] - theta[0]) - dtheta) < 1e-9


def test_k2_esit_acili_bolme():
    """Ara noktalar eşit açılı: θ_k = θ₀ ± k φ, φ = |Δθ| / n."""
    tp = yol((R, 0, 0), [Move(MoveType.ARC_CCW, (-R, 0, 0), feed=F, center=(0.0, 0.0))])
    P, _ = toolpath_polyline(tp, tol=TOL)
    theta = np.unwrap(np.arctan2(P[:, 1], P[:, 0]))
    n = len(P) - 1
    np.testing.assert_allclose(np.diff(theta), math.pi / n, atol=1e-9)


def test_k2_buyuk_tol_en_az_90_derecede_bir_nokta():
    """tol ≥ r → φ_max = π, ama en az 90°'de bir nokta: tam dairede n = 4."""
    tp = yol((R, 0, 0), [Move(MoveType.ARC_CCW, (R, 0, 0), feed=F, center=(0.0, 0.0))])
    P, _ = toolpath_polyline(tp, tol=2 * R)
    assert len(P) - 1 == 4


def test_k2_yay_ve_dogru_karisik():
    """G1 + G2 + G1: yay parçaları doğru parçalarının arasına doğru yerde girer."""
    tp = yol(
        (0, 0, 0),
        [
            Move(MoveType.LINEAR, (R, 0, 0), feed=F),
            Move(MoveType.ARC_CW, (0, -R, 0), feed=F, center=(0.0, 0.0)),
            Move(MoveType.LINEAR, (0, -2 * R, 0), feed=F),
        ],
    )
    P, kinds = toolpath_polyline(tp, tol=TOL)
    n = n_beklenen(math.pi / 2, R, TOL)
    assert len(P) == 1 + 1 + n + 1
    assert list(kinds) == [MoveType.LINEAR] + [MoveType.ARC_CW] * n + [MoveType.LINEAR]
    np.testing.assert_array_equal(P[1], (R, 0, 0))
    np.testing.assert_array_equal(P[1 + n], (0, -R, 0))
    np.testing.assert_array_equal(P[-1], (0, -2 * R, 0))


# ---------- K3: helis ----------


def helis(tol: float):
    """Tam daire G3, z: 0 → −5 (helis)."""
    tp = yol((R, 0, 0), [Move(MoveType.ARC_CCW, (R, 0, -5.0), feed=F, center=(0.0, 0.0))])
    return tp, toolpath_polyline(tp, tol=tol)


def test_k3_helis_z_aciyla_dogrusal():
    tp, (P, _) = helis(TOL)
    theta = np.unwrap(np.arctan2(P[:, 1], P[:, 0]))
    z_beklenen = 0.0 + (-5.0 - 0.0) * (theta - theta[0]) / (2 * math.pi)
    np.testing.assert_allclose(P[:, 2], z_beklenen, atol=1e-9)
    np.testing.assert_array_equal(P[-1], (R, 0, -5.0))


@pytest.mark.parametrize("tol", [0.1, 0.01, 1e-3])
def test_k3_cokgen_boyu_yay_boyundan_buyuk_degil(tol):
    """Kiriş boyu ≤ yay boyu: n·sqrt((2r sin(φ/2))² + (Δz/n)²) ≤ sqrt((r|Δθ|)² + Δz²)."""
    tp, (P, _) = helis(tol)
    assert poly_boy(P) <= tp.length() + 1e-12


def test_k3_cokgen_boyu_yakinsiyor():
    """Göreli boy hatası ≈ tol / (3r); tol küçüldükçe azalır ve tol = 1e-5'te < 1e-6."""
    hatalar = []
    for tol in (0.1, 0.01, 1e-3, 1e-4, 1e-5):
        tp, (P, _) = helis(tol)
        hatalar.append((tp.length() - poly_boy(P)) / tp.length())
    assert all(h >= -1e-15 for h in hatalar)
    assert all(b < a for a, b in zip(hatalar, hatalar[1:], strict=False))
    assert hatalar[-1] < 1e-6


# ---------- K4: sınır kutusu ----------


def test_k4_sinir_kutusu_tp_bbox_icinde_ve_tol_yakininda():
    """−30°'den +60°'ye G3: x ekseni uç noktası (10, 0) yayın ortasında, köşe olmayabilir."""
    tol = 0.5
    a0, a1 = math.radians(-30), math.radians(60)
    p0 = (R * math.cos(a0), R * math.sin(a0), 2.0)
    p1 = (R * math.cos(a1), R * math.sin(a1), -1.0)
    tp = yol(
        (0, 0, 5),
        [
            Move(MoveType.RAPID, p0),
            Move(MoveType.ARC_CCW, p1, feed=F, center=(0.0, 0.0)),
            Move(MoveType.LINEAR, (0, 0, -1), feed=F),
        ],
    )
    P, _ = toolpath_polyline(tp, tol=tol)
    lo, hi = tp.bbox()
    plo, phi = P.min(axis=0), P.max(axis=0)
    assert np.all(plo >= lo - 1e-12) and np.all(phi <= hi + 1e-12)
    assert np.all(plo - lo <= tol + 1e-12) and np.all(hi - phi <= tol + 1e-12)


# ---------- K5: hatalar ----------


def test_k5_hareketsiz_yol_hata():
    with pytest.raises(VizError):
        toolpath_polyline(yol((0, 0, 0), []))


@pytest.mark.parametrize("tol", [0.0, -0.01])
def test_k5_gecersiz_tol_hata(tol):
    tp = yol((0, 0, 0), [Move(MoveType.LINEAR, (1, 0, 0), feed=F)])
    with pytest.raises(VizError):
        toolpath_polyline(tp, tol=tol)


def test_k5_tutmayan_yay_camerror():
    """Başlangıç yarıçapı 10, bitiş yarıçapı 12: tp.validate() CamError fırlatır, olduğu gibi yükselir."""
    tp = yol((R, 0, 0), [Move(MoveType.ARC_CCW, (0, 12.0, 0), feed=F, center=(0.0, 0.0))])
    with pytest.raises(CamError):
        toolpath_polyline(tp)


# ---------- K6: hızlı / kesme ayrımı ----------


def test_k6_split_rapid_feed():
    tp = yol(
        (0, 0, 10),
        [
            Move(MoveType.RAPID, (R, 0, 1)),  # hızlı 1
            Move(MoveType.LINEAR, (R, 0, -1), feed=F),  # kesme 1
            Move(MoveType.LINEAR, (R, 5, -1), feed=F),  # kesme 1 (birleşir)
            Move(MoveType.RAPID, (R, 0, -1)),  # hızlı 2
            Move(MoveType.ARC_CW, (0, -R, -1), feed=F, center=(0.0, 0.0)),  # kesme 2
        ],
    )
    P, kinds = toolpath_polyline(tp)
    hizli, kesme = split_rapid_feed(P, kinds)
    assert len(hizli) == 2 and len(kesme) == 2
    assert all(c.ndim == 2 and c.shape[1] == 3 for c in hizli + kesme)

    # G1–G1 tek çizgide: 3 nokta
    assert len(kesme[0]) == 3
    np.testing.assert_array_equal(kesme[0], [(R, 0, 1), (R, 0, -1), (R, 5, -1)])

    # uç noktalar paylaşılıyor
    np.testing.assert_array_equal(hizli[0][0], tp.start)
    np.testing.assert_array_equal(hizli[0][-1], kesme[0][0])
    np.testing.assert_array_equal(kesme[0][-1], hizli[1][0])
    np.testing.assert_array_equal(hizli[1][-1], kesme[1][0])
    np.testing.assert_array_equal(kesme[1][-1], (0, -R, -1))

    # toplam nokta: 4 çizgi, 3 ortak uç
    assert sum(len(c) for c in hizli + kesme) == len(P) + 3


# ---------- K7, K8: montaj ağları ----------


def ag_hacmi(V: np.ndarray, T: np.ndarray) -> float:
    """Diverjans teoremi: V = (1/6) Σ p₁ · (p₂ × p₃) (dışa bakan üçgenler)."""
    p1, p2, p3 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    return float(np.einsum("ij,ij->i", p1, np.cross(p2, p3)).sum() / 6.0)


def blok(a, b, c, name="blok"):
    bd = pytest.importorskip("build123d")
    from geometry.part import Part

    return Part(bd.Box(a, b, c, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN)), name=name)


@pytest.mark.occt
def test_k7_donmus_ve_otelenmis_blok():
    """Blok [0,100]×[0,60]×[0,20]; R = rot_z(90°): (x, y) → (−y, x); t = (5, 6, 7).
    Dünya: x ∈ [−60+5, 0+5], y ∈ [0+6, 100+6], z ∈ [0+7, 20+7]."""
    parca = blok(100, 60, 20)
    assy = Assembly("m", components=[Component("c1", "blok", T=transform(rot_z(90), (5, 6, 7)))])
    ms = assembly_meshes(assy, {"blok": parca})
    assert len(ms) == 1
    m = ms[0]
    assert isinstance(m, ComponentMesh) and m.name == "c1"
    np.testing.assert_allclose(m.V.min(axis=0), (-55, 6, 7), atol=1e-9)
    np.testing.assert_allclose(m.V.max(axis=0), (5, 106, 27), atol=1e-9)
    # dönüşüm hacmi ve üçgen yönünü korur (det R = +1)
    assert ag_hacmi(m.V, m.T) == pytest.approx(100 * 60 * 20, rel=1e-9)


@pytest.mark.occt
def test_k7_ayni_parca_iki_bilesen_ve_renkler():
    parca = blok(10, 10, 10)
    T2 = transform(t=(50, 0, 0))
    assy = Assembly("m", components=[Component("a", "p"), Component("b", "p", T=T2)])
    ms = assembly_meshes(assy, {"p": parca})
    assert [m.name for m in ms] == ["a", "b"]
    assert [m.color for m in ms] == [PALETTE[0], PALETTE[1]]
    np.testing.assert_allclose(ms[1].V.min(axis=0) - ms[0].V.min(axis=0), (50, 0, 0), atol=1e-9)
    assert ag_hacmi(ms[0].V, ms[0].T) == pytest.approx(1000, rel=1e-9)
    assert ag_hacmi(ms[1].V, ms[1].T) == pytest.approx(1000, rel=1e-9)


@pytest.mark.occt
def test_k7_palet_dongusel():
    assert len(PALETTE) == 8
    parca = blok(1, 1, 1)
    comps = [Component(f"c{i}", "p", T=transform(t=(2 * i, 0, 0))) for i in range(9)]
    ms = assembly_meshes(Assembly("m", components=comps), {"p": parca})
    assert [m.color for m in ms] == [PALETTE[i % 8] for i in range(9)]


def test_k8_eksik_parca_hata():
    assy = Assembly("m", components=[Component("c1", "yok.step")])
    with pytest.raises(VizError, match="c1"):
        assembly_meshes(assy, {})


def test_k8_bos_montaj_hata():
    with pytest.raises(VizError):
        assembly_meshes(Assembly("bos"), {})


@pytest.mark.occt
def test_k8_bilinmeyen_bilesenli_kisit_assyerror():
    parca = blok(1, 1, 1)
    a = Ref("c1", "duzlem", (0, 0, 1), (0, 0, 1))
    b = Ref("hayalet", "duzlem", (0, 0, 0), (0, 0, -1))
    assy = Assembly("m", components=[Component("c1", "p")], mates=[Mate("cakisik", a, b)])
    with pytest.raises(AssyError):
        assembly_meshes(assy, {"p": parca})


# ---------- K9: ham malzeme kutusu ----------


def test_k9_stock_box():
    st = Stock(-5, -3, -2, 95, 57, 18)
    C, E = stock_box(st)
    assert C.shape == (8, 3) and E.shape == (12, 2)
    beklenen = {(x, y, z) for x in (-5, 95) for y in (-3, 57) for z in (-2, 18)}
    assert {tuple(float(v) for v in c) for c in C} == beklenen

    assert len({tuple(sorted(e)) for e in E.tolist()}) == 12  # kenarlar tekrarsız
    eksen_sayisi = [0, 0, 0]
    for i, j in E:
        d = np.abs(C[j] - C[i])
        eksen = np.flatnonzero(d > 0)
        assert len(eksen) == 1  # tek eksene paralel
        k = int(eksen[0])
        assert d[k] == pytest.approx(st.size[k], rel=1e-12)
        eksen_sayisi[k] += 1
    assert eksen_sayisi == [4, 4, 4]
