"""SPEC 17 K10, K11 — çözülmüş eskizden bölgeler ve yaylı döngü alanı.

Testler yalnızca specs/17-kroki.md "Bölgeler" bölümünden ve sketch/model.py arayüzünden yazıldı;
sketch/regions.py gövdesi okunmadı. Yön ve alan bağımsız bir yardımcıyla (Green teoremi + kesit alanı)
ölçülür.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from sketch.model import (
    Circle,
    Constraint,
    ConstraintType,
    Line,
    Point,
    SegArc,
    SegLine,
    Sketch,
    SketchError,
    SketchRegion,
)
from sketch.regions import area, regions

CT = ConstraintType


# --- Yardımcılar --------------------------------------------------------------------------------------


def eskiz(points: dict, entities: dict, constraints: list) -> Sketch:
    return Sketch(points=points, entities=entities, constraints=constraints)


def bas(seg) -> np.ndarray:
    return np.asarray(seg.p0 if isinstance(seg, SegLine) else seg.start, float)


def son(seg) -> np.ndarray:
    return np.asarray(seg.p1 if isinstance(seg, SegLine) else seg.end, float)


def cross(a, b) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def isaretli_alan(dongu) -> float:
    """½ Σ (u_i v_{i+1} − u_{i+1} v_i) + Σ ½ r² (α − sin α), α döngü yönünde işaretli yay açısı."""
    A = 0.0
    for seg in dongu:
        s, e = bas(seg), son(seg)
        A += 0.5 * cross(s, e)
        if isinstance(seg, SegArc):
            c = np.asarray(seg.center, float)
            ts = math.atan2(*(s - c)[::-1])
            te = math.atan2(*(e - c)[::-1])
            tam = np.allclose(s, e, atol=1e-12)
            if seg.ccw:
                a = 2 * math.pi if tam else (te - ts) % (2 * math.pi)
            else:
                a = -2 * math.pi if tam else -((ts - te) % (2 * math.pi))
            A += 0.5 * seg.r**2 * (a - math.sin(a))
    return A


def kapali(dongu) -> bool:
    n = len(dongu)
    return all(np.allclose(son(dongu[i]), bas(dongu[(i + 1) % n]), atol=1e-9) for i in range(n))


def dikdortgen(on: str, x0: float, y0: float, w: float, h: float, pts: dict, ents: dict, cs: list) -> None:
    """Paylaşılan köşeli dikdörtgen; H, V, H, V kısıtları (sağlanmış)."""
    a, b, c, d = (f"{on}_{k}" for k in "abcd")
    pts.update({a: Point(x0, y0), b: Point(x0 + w, y0), c: Point(x0 + w, y0 + h), d: Point(x0, y0 + h)})
    ents.update(
        {
            f"{on}_ab": Line(a, b),
            f"{on}_bc": Line(b, c),
            f"{on}_cd": Line(c, d),
            f"{on}_da": Line(d, a),
        }
    )
    cs += [
        Constraint(CT.HORIZONTAL, (f"{on}_ab",)),
        Constraint(CT.VERTICAL, (f"{on}_bc",)),
        Constraint(CT.HORIZONTAL, (f"{on}_cd",)),
        Constraint(CT.VERTICAL, (f"{on}_da",)),
    ]


def plaka_delikli(ada: bool = False) -> Sketch:
    """40×30 dikdörtgen + (20, 15) merkezli r = 5 daire; ada=True → dairenin içinde 4×4 kare."""
    pts, ents, cs = {}, {}, []
    dikdortgen("dis", 0.0, 0.0, 40.0, 30.0, pts, ents, cs)
    pts["m"] = Point(20.0, 15.0)
    ents["delik"] = Circle("m", 5.0)
    cs.append(Constraint(CT.RADIUS, ("delik",), 5.0))
    if ada:
        dikdortgen("ada", 18.0, 13.0, 4.0, 4.0, pts, ents, cs)
    return eskiz(pts, ents, cs)


def hata_mesajinda(err: SketchError, kimlikler) -> bool:
    return any(k in str(err) for k in kimlikler)


# --- K10: bölgeler ------------------------------------------------------------------------------------


def test_delikli_plaka():
    bol = regions(plaka_delikli())
    assert len(bol) == 1
    r = bol[0]
    assert isinstance(r, SketchRegion)
    assert len(r.outer) == 4
    assert len(r.holes) == 1
    assert kapali(r.outer) and kapali(r.holes[0])
    # dış CCW, delik CW
    assert isaretli_alan(r.outer) == pytest.approx(1200.0, abs=1e-9)
    assert isaretli_alan(r.holes[0]) == pytest.approx(-25.0 * math.pi, abs=1e-9)
    assert area(r) == pytest.approx(1200.0 - 25.0 * math.pi, abs=1e-9)


def test_tek_daire_bolge():
    s = eskiz({"c": Point(3.0, -2.0)}, {"o": Circle("c", 7.0)}, [])
    bol = regions(s)
    assert len(bol) == 1 and bol[0].holes == ()
    assert len(bol[0].outer) == 1 and isinstance(bol[0].outer[0], SegArc)
    assert isaretli_alan(bol[0].outer) == pytest.approx(49.0 * math.pi, abs=1e-9)
    assert area(bol[0]) == pytest.approx(49.0 * math.pi, abs=1e-9)


def test_delikteki_ada_ayri_bolge():
    bol = sorted(regions(plaka_delikli(ada=True)), key=area)
    assert len(bol) == 2
    ada, plaka = bol
    assert ada.holes == ()
    assert area(ada) == pytest.approx(16.0, abs=1e-9)
    assert isaretli_alan(ada.outer) == pytest.approx(16.0, abs=1e-9)  # ada dış sınır: CCW
    assert len(plaka.holes) == 1
    assert area(plaka) == pytest.approx(1200.0 - 25.0 * math.pi, abs=1e-9)


def test_iki_ayrik_dikdortgen():
    pts, ents, cs = {}, {}, []
    dikdortgen("r1", 0.0, 0.0, 40.0, 30.0, pts, ents, cs)
    dikdortgen("r2", 100.0, 0.0, 10.0, 10.0, pts, ents, cs)
    bol = sorted(regions(eskiz(pts, ents, cs)), key=area)
    assert len(bol) == 2
    assert [area(b) for b in bol] == pytest.approx([100.0, 1200.0], abs=1e-9)
    assert all(b.holes == () for b in bol)


def test_cw_cizilmis_dongu_ccw_doner():
    """Kullanıcı dikdörtgeni saat yönünde çizse de dış sınır CCW döner."""
    pts = {"a": Point(0.0, 0.0), "b": Point(0.0, 30.0), "c": Point(40.0, 30.0), "d": Point(40.0, 0.0)}
    ents = {"ab": Line("a", "b"), "bc": Line("b", "c"), "cd": Line("c", "d"), "da": Line("d", "a")}
    bol = regions(eskiz(pts, ents, []))
    assert len(bol) == 1
    assert isaretli_alan(bol[0].outer) == pytest.approx(1200.0, abs=1e-9)


def test_construction_cizgi_bolgeye_girmez():
    s = plaka_delikli()
    s.entities["kosegen"] = Line("dis_a", "dis_c", construction=True)
    s.entities["yardim"] = Circle("m", 12.0, construction=True)
    bol = regions(s)
    assert len(bol) == 1
    assert len(bol[0].outer) == 4 and len(bol[0].holes) == 1
    assert area(bol[0]) == pytest.approx(1200.0 - 25.0 * math.pi, abs=1e-9)


def test_coincident_ile_birlesen_uclar():
    """Ayrı kimlikli ama COINCIDENT ile bağlanmış uçlar bağlı sayılır."""
    pts, ents, cs = {}, {}, []
    dikdortgen("r", 0.0, 0.0, 40.0, 30.0, pts, ents, cs)
    pts["r_a2"] = Point(0.0, 0.0)
    ents["r_da"] = Line("r_d", "r_a2")
    cs.append(Constraint(CT.COINCIDENT, ("r_a2", "r_a")))
    bol = regions(eskiz(pts, ents, cs))
    assert len(bol) == 1
    assert area(bol[0]) == pytest.approx(1200.0, abs=1e-9)


# --- K11: bölge hataları ------------------------------------------------------------------------------


def test_geometrik_cakisik_ama_bagsiz_uclar_hata():
    """Sessiz yapıştırma yok: aynı konumdaki iki ayrı nokta kısıtsız bağlanmaz → açık zincir."""
    pts, ents, cs = {}, {}, []
    dikdortgen("r", 0.0, 0.0, 40.0, 30.0, pts, ents, cs)
    pts["r_a2"] = Point(0.0, 0.0)
    ents["r_da"] = Line("r_d", "r_a2")
    with pytest.raises(SketchError) as e:
        regions(eskiz(pts, ents, cs))
    assert hata_mesajinda(e.value, ("r_da", "r_ab", "r_a2", "r_a"))


def test_acik_zincir_hata():
    pts, ents, cs = {}, {}, []
    dikdortgen("r", 0.0, 0.0, 40.0, 30.0, pts, ents, cs)
    del ents["r_da"]
    cs.pop()  # r_da'nın VERTICAL kısıtı
    with pytest.raises(SketchError) as e:
        regions(eskiz(pts, ents, cs))
    assert hata_mesajinda(e.value, ("r_ab", "r_cd"))


def test_dallanma_hata():
    """T bağlantı: köşegen profil çizgisi köşelerde derece 3 yapar."""
    pts, ents, cs = {}, {}, []
    dikdortgen("r", 0.0, 0.0, 40.0, 30.0, pts, ents, cs)
    ents["capraz"] = Line("r_a", "r_c")
    with pytest.raises(SketchError) as e:
        regions(eskiz(pts, ents, cs))
    assert hata_mesajinda(e.value, ("capraz", "r_ab", "r_da", "r_bc", "r_cd"))


def test_papyon_kendini_kesen_dongu_hata():
    pts = {"a": Point(0.0, 0.0), "b": Point(10.0, 10.0), "c": Point(10.0, 0.0), "d": Point(0.0, 10.0)}
    ents = {"pp1": Line("a", "b"), "pp2": Line("b", "c"), "pp3": Line("c", "d"), "pp4": Line("d", "a")}
    with pytest.raises(SketchError) as e:
        regions(eskiz(pts, ents, []))
    assert hata_mesajinda(e.value, ("pp1", "pp3"))


def test_kesisen_iki_dongu_hata():
    pts, ents, cs = {}, {}, []
    dikdortgen("r1", 0.0, 0.0, 40.0, 30.0, pts, ents, cs)
    dikdortgen("r2", 20.0, 10.0, 40.0, 30.0, pts, ents, cs)
    with pytest.raises(SketchError) as e:
        regions(eskiz(pts, ents, cs))
    assert hata_mesajinda(e.value, ("r1_bc", "r1_cd", "r2_ab", "r2_da"))


def test_daire_dikdortgeni_kesiyor_hata():
    s = plaka_delikli()
    s.points["m"] = Point(38.0, 15.0)  # r = 5 daire sağ kenarı keser
    with pytest.raises(SketchError) as e:
        regions(s)
    assert hata_mesajinda(e.value, ("delik", "dis_bc"))


def test_saglanmamis_kisit_hata():
    s = plaka_delikli()
    s.constraints.append(Constraint(CT.LENGTH, ("dis_ab",), 50.0))
    with pytest.raises(SketchError):
        regions(s)
