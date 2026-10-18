"""SPEC 26 K7 (köprü tarafı), K8 — tezgah/model_kopru.py: SolveResult / Rapor / Part → JSON ve ikili dizi,
"Tezgah'a gönder" → SPEC 24 Is.

Testler SPEC 26 "REST uçları", "Tezgah'a gönder" ve "Kabul kriterleri" bölümlerinden yazıldı;
tezgah/model_kopru.py gövdesi okunmadı. Beklenen değerler `sketch.solver.solve` / `drag`, `geometry` ve
elle kurulan modellerden (tests/tezgah/model_ornekler.py) gelir. SPEC 24 K2 (G-code ↔ okuyucu) ve K5
(kontroller) bu iş için de denetlenir. OCCT gerektiren testler `occt` ile işaretlidir.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from sketch.model import Arc, Circle, Constraint, Line, Plane, Point, Sketch, SketchError
from sketch.model import ConstraintType as CT
from sketch.solver import SolveResult, drag, solve
from tests.tezgah import model_ornekler as mo
from tezgah import SEMA
from tezgah.model_kopru import (
    ag_coz,
    ag_ikili,
    cozum_json,
    eskiz_coz,
    eskiz_surukle,
    rapor_json,
    tezgaha_gonder,
    yuz_json,
)

occt = pytest.mark.occt


def json_tur(x):
    return json.loads(json.dumps(x, allow_nan=False))


# --- Eskizler -----------------------------------------------------------------------------------------


def eksik_dikdortgen() -> Sketch:
    """dof = 1: sağ kenar boyu yok, üst kenar düşey kayar."""
    return mo.dikdortgen_eskiz(0.0, 0.0, 40.0, 30.0, tam=False)


def daire_uzerinde_nokta() -> Sketch:
    """Sabit merkez, r = 10; daire üzerindeki p tek serbestlikli (directions'ta yönü var)."""
    return Sketch(
        points={"m": Point(0.0, 0.0, fixed=True), "p": Point(7.0, 7.5)},
        entities={"o": Circle("m", 10.0)},
        constraints=[Constraint(CT.RADIUS, ("o",), 10.0), Constraint(CT.POINT_ON_CIRCLE, ("p", "o"))],
    )


def kanal() -> Sketch:
    """SPEC 17 K6 kanalı (TANGENT dalları sides'ta)."""
    pts = {
        "c1": Point(0.3, -0.2),
        "c2": Point(29.5, 0.4),
        "b1": Point(0.2, -5.3),
        "b2": Point(30.4, -4.8),
        "t2": Point(29.7, 5.2),
        "t1": Point(-0.3, 4.9),
    }
    ents = {
        "alt": Line("b1", "b2"),
        "ust": Line("t2", "t1"),
        "y2": Arc("c2", "b2", "t2"),
        "y1": Arc("c1", "t1", "b1"),
    }
    cs = [
        Constraint(CT.TANGENT, ("alt", "y1")),
        Constraint(CT.TANGENT, ("alt", "y2")),
        Constraint(CT.TANGENT, ("ust", "y1")),
        Constraint(CT.TANGENT, ("ust", "y2")),
        Constraint(CT.DISTANCE, ("c1", "c2"), 30.0),
        Constraint(CT.RADIUS, ("y1",), 5.0),
        Constraint(CT.EQUAL, ("y1", "y2")),
    ]
    return Sketch(points=pts, entities=ents, constraints=cs)


def celiskili() -> Sketch:
    return Sketch(
        points={"p": Point(0.0, 0.0), "q": Point(5.5, 0.5)},
        entities={},
        constraints=[Constraint(CT.DISTANCE, ("p", "q"), 5.0), Constraint(CT.DISTANCE, ("p", "q"), 7.0)],
    )


ESKIZLER = {
    "tam_dikdortgen": lambda: mo.dikdortgen_eskiz(0.0, 0.0, 40.0, 30.0),
    "eksik_dikdortgen": eksik_dikdortgen,
    "daire_uzerinde_nokta": daire_uzerinde_nokta,
    "kanal": kanal,
}


def cozum_denetle(J: dict, res: SolveResult) -> None:
    """J, SolveResult'ın kayıpsız JSON karşılığı (modül belgesindeki biçim)."""
    assert J == json_tur(J)  # JSON'a yazılıp okununca birebir aynı
    assert J["sema"] == SEMA
    assert set(J["points"]) == set(res.points)
    for k, p in res.points.items():
        assert J["points"][k] == [float(p[0]), float(p[1])]
    assert J["radii"] == {k: float(r) for k, r in res.radii.items()}
    assert J["sides"] == {str(k): int(v) for k, v in res.sides.items()}
    assert J["iterations"] == res.iterations
    assert J["residual"] == float(res.residual)
    assert J["dof"] == res.dof
    assert J["freedom"] == {k: int(v) for k, v in res.freedom.items()}
    assert set(J["directions"]) == set(res.directions)
    for k, v in res.directions.items():
        assert J["directions"][k] == [float(v[0]), float(v[1])]
    assert J["redundant"] == [int(i) for i in res.redundant]


# --- Çözüm JSON'u -------------------------------------------------------------------------------------


@pytest.mark.parametrize("ad", list(ESKIZLER))
def test_cozum_json_kayipsiz(ad):
    res = solve(ESKIZLER[ad]())
    cozum_denetle(cozum_json(res), res)


def test_cozum_json_yon_ve_dal_dolu():
    """Örneklerin gerçekten directions ve sides alanlarını sınadığını garanti et."""
    assert solve(daire_uzerinde_nokta()).directions
    assert solve(kanal()).sides


@pytest.mark.parametrize("ad", list(ESKIZLER))
def test_eskiz_coz_solve_ile_birebir(ad):
    sk = ESKIZLER[ad]()
    d = sk.to_dict()
    J = eskiz_coz(d)
    cozum_denetle(J, solve(Sketch.from_dict(d)))
    assert d == sk.to_dict()  # girdi değişmez


def test_eskiz_coz_celiski_kumesi():
    sk = celiskili()
    with pytest.raises(SketchError) as e0:
        solve(sk)
    with pytest.raises(SketchError) as e:
        eskiz_coz(sk.to_dict())
    assert tuple(sorted(e.value.constraints)) == tuple(sorted(e0.value.constraints)) == (0, 1)


def test_eskiz_coz_bozuk_eskiz():
    d = mo.dikdortgen_eskiz(0, 0, 4, 3).to_dict()
    d["sema"] = 99
    with pytest.raises(SketchError):
        eskiz_coz(d)
    d = mo.dikdortgen_eskiz(0, 0, 4, 3).to_dict()
    d["constraints"][0]["refs"] = ["yok"]
    with pytest.raises(SketchError):
        eskiz_coz(d)


@pytest.mark.parametrize(
    "ad, nokta, hedef",
    [
        ("eksik_dikdortgen", "c", (41.0, 45.0)),
        ("eksik_dikdortgen", "d", (-3.0, 12.5)),
        ("daire_uzerinde_nokta", "p", (-20.0, 3.0)),
    ],
)
def test_eskiz_surukle_drag_ile_birebir(ad, nokta, hedef):
    sk = ESKIZLER[ad]()
    J = eskiz_surukle(sk.to_dict(), nokta, hedef)
    cozum_denetle(J, drag(Sketch.from_dict(sk.to_dict()), nokta, hedef))


def test_eskiz_surukle_liste_hedef():
    sk = eksik_dikdortgen()
    J = eskiz_surukle(sk.to_dict(), "c", [41.0, 45.0])
    cozum_denetle(J, drag(sk, "c", (41.0, 45.0)))


def test_eskiz_surukle_sabit_ve_bilinmeyen_nokta():
    d = eksik_dikdortgen().to_dict()
    with pytest.raises(SketchError):
        eskiz_surukle(d, "a", (5.0, 5.0))  # a sabit
    with pytest.raises(SketchError):
        eskiz_surukle(d, "yok", (5.0, 5.0))


# --- Rapor JSON'u -------------------------------------------------------------------------------------


@occt
def test_rapor_json():
    pytest.importorskip("build123d")
    from tezgah.modelleme import insa

    _, r = insa(mo.plaka(tam=False))
    J = rapor_json(r)
    assert J == json_tur(J)
    assert J["sema"] == SEMA
    assert J["kontroller"] == json_tur(r.kontroller)
    assert [a["kimlik"] for a in J["adimlar"]] == [a.kimlik for a in r.adimlar]


@occt
def test_rapor_json_hata_ve_celiski():
    pytest.importorskip("build123d")
    from tezgah.modelleme import insa

    m = mo.plaka()
    sk = mo.dikdortgen_eskiz(0, 0, 40, 30)
    sk.constraints.append(Constraint(CT.LENGTH, ("ust",), 45.0))
    m["adimlar"][0]["eskiz"] = sk.to_dict()
    _, r = insa(m)
    J = rapor_json(r)
    assert J == json_tur(J)
    assert r.hata is not None
    s = json.dumps(J, ensure_ascii=False)
    assert r.hata.hata in s  # çekirdeğin hata metni JSON'da


# --- Ağ ve yüz ----------------------------------------------------------------------------------------


def _kutu_parcasi():
    pytest.importorskip("build123d")
    from tezgah.modelleme import insa

    p, r = insa(mo.plaka())
    assert r.hata is None
    return p


@occt
def test_ag_ikili_cozulur_ve_kapali_hacim():
    p = _kutu_parcasi()
    A = ag_coz(ag_ikili(p))
    V, T, Y = A["kose"], A["ucgen"], A["yuz"]
    assert V.dtype == np.float32 and V.ndim == 2 and V.shape[1] == 3
    assert T.dtype == np.int32 and T.ndim == 2 and T.shape[1] == 3
    assert Y.dtype == np.int32 and Y.shape == (T.shape[0],)
    assert T.min() >= 0 and T.max() < len(V)
    # kutu: 6 yüzün hepsinde üçgen var, indeksler OCCT yüz sırası
    assert set(Y.tolist()) == set(range(len(p.shape.faces())))
    # diverjans teoremi: kapalı ağın hacmi (float32 köşelerle)
    a, b, c = (V[T[:, i]].astype(float) for i in range(3))
    hac = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    assert hac == pytest.approx(p.volume, rel=1e-5)


@occt
def test_ag_yuz_indeksi_planar_faces_ile_tutarli():
    p = _kutu_parcasi()
    A = ag_coz(ag_ikili(p))
    for f in p.planar_faces():
        k = A["ucgen"][A["yuz"] == f.index]
        assert len(k)
        P = A["kose"][k.reshape(-1)].astype(float)
        uzaklik = (P - f.origin) @ f.normal
        assert np.abs(uzaklik).max() <= 1e-4  # float32 köşeler


@occt
def test_ag_ikili_belirlenimci():
    p = _kutu_parcasi()
    assert ag_ikili(p) == ag_ikili(p)


@occt
def test_yuz_json_ust_yuz():
    from geometry.extrude import face_outline, face_plane

    p = _kutu_parcasi()
    i = max((f for f in p.planar_faces() if f.normal[2] > 0.5), key=lambda f: f.origin[2]).index
    J = yuz_json(p, i)
    assert J == json_tur(J)
    assert J["sema"] == SEMA
    assert Plane.from_dict(J["plane"]).to_dict() == face_plane(p, i).to_dict()
    np.testing.assert_allclose(J["plane"]["origin"], (20, 15, 10), atol=1e-9)
    assert len(J["outline"]) == len(face_outline(p, i)) == 1
    assert len(J["outline"][0]) == 4


@occt
def test_yuz_json_duzlemsel_olmayan_hata():
    pytest.importorskip("build123d")
    from geometry.part import GeometryError
    from tezgah.modelleme import insa

    m = mo.plaka()
    m["adimlar"] += [
        mo.eskiz_adimi("e2", mo.daire_eskiz(20, 15, 4, plane=mo.duzlem_xy(10)), {"tur": "XY", "ofset": 10}),
        mo.ekstruzyon_adimi("d", "e2", 0, islem="kes", bitis="boydan_boya"),
    ]
    p, r = insa(m)
    assert r.hata is None
    with pytest.raises(GeometryError):
        yuz_json(p, p.cylindrical_faces()[0].index)
    with pytest.raises(GeometryError):
        yuz_json(p, 9999)


# --- K8: tasarım niyeti → CAM -------------------------------------------------------------------------


def _parca(m: dict):
    from tezgah.modelleme import insa

    p, r = insa(m)
    assert r.hata is None, r.hata
    return p


def _kesen(op, z_ust: float) -> np.ndarray:
    """Takım yolunun z_ust'ün altındaki kesme (G1/G2/G3) hareket uçları, (k, 3)."""
    from cam.model import MoveType

    P = [m.end for m in op.moves if m.type != MoveType.RAPID and m.end[2] < z_ust - 1e-9]
    return np.array(P, dtype=float).reshape(-1, 3)


def _sikistir(anahtarlar: list[str]) -> list[str]:
    out: list[str] = []
    for a in anahtarlar:
        if not out or out[-1] != a:
            out.append(a)
    return out


def _delik_noktalari(tanim) -> list[tuple[float, float]]:
    from cam.gcode import DrillOp

    return [h for isl in tanim.islemler if isinstance(isl.op, DrillOp) for h in isl.op.holes]


@occt
def test_gonder_stok_sinir_kutusu_arti_pay():
    pytest.importorskip("build123d")
    from cam.model import Stock
    from tezgah.kopru import IsTanimi

    m = mo.flans()
    p = _parca(m)
    tanim = tezgaha_gonder(m)
    assert isinstance(tanim, IsTanimi)
    st = tanim.kurulum.stock
    assert isinstance(st, Stock)
    b0, b1 = p.bbox
    beklenen = (b0[0] - 2, b0[1] - 2, b0[2], b1[0] + 2, b1[1] + 2, b1[2] + 1)
    np.testing.assert_allclose((st.xmin, st.ymin, st.zmin, st.xmax, st.ymax, st.zmax), beklenen, atol=1e-9)
    np.testing.assert_allclose(beklenen, (-2, -2, 0, 122, 82, 16), atol=1e-6)
    assert tanim.parca_ag is not None
    assert m == mo.flans()  # girdi model değişmez


@occt
def test_gonder_islem_sirasi():
    pytest.importorskip("build123d")
    tanim = tezgaha_gonder(mo.flans())
    assert _sikistir([i.anahtar for i in tanim.islemler]) == ["yuzey", "cep", "kontur", "delik"]
    assert sum(1 for i in tanim.islemler if i.anahtar == "cep") == 1
    assert sum(1 for i in tanim.islemler if i.anahtar == "kontur") == 1


@occt
def test_gonder_yuz_alma_ust_yuze():
    pytest.importorskip("build123d")
    tanim = tezgaha_gonder(mo.flans())
    (y,) = [i for i in tanim.islemler if i.anahtar == "yuzey"]
    P = _kesen(y.op, mo.FL_C + 1.0 + 1e-6)
    assert len(P)
    assert P[:, 2].min() == pytest.approx(mo.FL_C, abs=1e-9)


@occt
def test_gonder_cep_bolgesi_ve_derinlik():
    pytest.importorskip("build123d")
    tanim = tezgaha_gonder(mo.flans())
    (c,) = [i for i in tanim.islemler if i.anahtar == "cep"]
    R = c.op.tool.D / 2
    P = _kesen(c.op, mo.FL_C)
    assert len(P)
    assert P[:, 2].min() == pytest.approx(mo.FL_C - mo.FL_CEP_DERINLIK, abs=1e-9)
    x0, y0, w, h = mo.FL_CEP
    # Takım merkezi bölgeyi R kadar içeriden izler: uçlar bölge ± R (bölge eskizdekiyle aynı)
    dip = P[np.abs(P[:, 2] - P[:, 2].min()) <= 1e-9]
    assert dip[:, 0].min() == pytest.approx(x0 + R, abs=1e-6)
    assert dip[:, 0].max() == pytest.approx(x0 + w - R, abs=1e-6)
    assert dip[:, 1].min() == pytest.approx(y0 + R, abs=1e-6)
    assert dip[:, 1].max() == pytest.approx(y0 + h - R, abs=1e-6)
    assert P[:, 0].min() >= x0 + R - 1e-6 and P[:, 0].max() <= x0 + w - R + 1e-6
    assert P[:, 1].min() >= y0 + R - 1e-6 and P[:, 1].max() <= y0 + h - R + 1e-6


@occt
def test_gonder_dis_kontur_en_alt_kesit():
    pytest.importorskip("build123d")
    tanim = tezgaha_gonder(mo.flans())
    (k,) = [i for i in tanim.islemler if i.anahtar == "kontur"]
    R = k.op.tool.D / 2
    P = _kesen(k.op, mo.FL_C + 1.0)
    assert len(P)
    assert P[:, 2].min() == pytest.approx(0.0, abs=1e-9)
    dip = P[np.abs(P[:, 2] - P[:, 2].min()) <= 1e-9]
    assert dip[:, 0].min() == pytest.approx(-R, abs=1e-6)
    assert dip[:, 0].max() == pytest.approx(mo.FL_A + R, abs=1e-6)
    assert dip[:, 1].min() == pytest.approx(-R, abs=1e-6)
    assert dip[:, 1].max() == pytest.approx(mo.FL_B + R, abs=1e-6)


@occt
def test_gonder_delikler_part_holes_kayitlarindan():
    pytest.importorskip("build123d")
    m = mo.flans()
    p = _parca(m)
    tanim = tezgaha_gonder(m)
    N = sorted(_delik_noktalari(tanim))
    assert len(N) == 4
    np.testing.assert_allclose(N, sorted(mo.FL_DELIKLER.values()), atol=1e-9)
    np.testing.assert_allclose(N, sorted((h.origin[0], h.origin[1]) for h in p.holes), atol=1e-9)
    from cam.gcode import DrillOp

    for isl in tanim.islemler:
        if isinstance(isl.op, DrillOp):
            assert isl.op.z <= 1e-9  # boydan boya: dip parçanın altına kadar
            assert isl.op.kind in ("G81", "G83")


@occt
def test_gonder_boydan_boya_ic_bolge_ic_kontur():
    pytest.importorskip("build123d")
    m = mo.flans()
    m["adimlar"] += [
        mo.eskiz_adimi(
            "e4",
            mo.dikdortgen_eskiz(10, 30, 15, 20, plane=mo.duzlem_xy(mo.FL_C)),
            {"tur": "XY", "ofset": mo.FL_C},
        ),
        mo.ekstruzyon_adimi("pencere", "e4", 0, islem="kes", bitis="boydan_boya"),
    ]
    tanim = tezgaha_gonder(m)
    konturlar = [i for i in tanim.islemler if i.anahtar == "kontur"]
    assert len(konturlar) == 2
    ic = []
    for k in konturlar:
        R = k.op.tool.D / 2
        P = _kesen(k.op, mo.FL_C)
        if P[:, 0].max() < mo.FL_A / 2:
            ic.append((P, R))
    assert len(ic) == 1
    P, R = ic[0]
    dip = P[np.abs(P[:, 2] - P[:, 2].min()) <= 1e-9]
    assert P[:, 2].min() <= 1e-9
    assert dip[:, 0].min() == pytest.approx(10 + R, abs=1e-6)
    assert dip[:, 0].max() == pytest.approx(25 - R, abs=1e-6)
    assert dip[:, 1].min() == pytest.approx(30 + R, abs=1e-6)
    assert dip[:, 1].max() == pytest.approx(50 - R, abs=1e-6)


def yan_yuzlu_flans() -> dict:
    """Flanş + sağ yan yüzde (x = 120) kesim ve delik: +Z dışı, bu SPEC'te işlenmez."""
    pytest.importorskip("build123d")
    m = mo.flans()
    p = _parca(m)
    i = max((f for f in p.planar_faces() if f.normal[0] > 0.5), key=lambda f: f.origin[0]).index
    pl = Plane((mo.FL_A, mo.FL_B / 2, mo.FL_C / 2), (1, 0, 0), (0, 1, 0))
    duz = {"tur": "yuz", "adim": "x1", "yuz": i, "plane": pl.to_dict()}
    m["adimlar"] += [
        mo.eskiz_adimi("e5", mo.dikdortgen_eskiz(10, -2, 10, 4, plane=pl), duz),
        mo.ekstruzyon_adimi("yan_kes", "e5", 3, islem="kes"),
        mo.eskiz_adimi("e6", mo.nokta_eskiz({"s": (-15.0, 0.0)}, plane=pl), duz),
        mo.delik_adimi("yan_delik", "e6", ["s"], "duz", 5, 10),
    ]
    return m


@occt
def test_gonder_yan_yuz_islenmez():
    m = yan_yuzlu_flans()
    p = _parca(m)
    assert len(p.holes) == 5
    tanim = tezgaha_gonder(m)
    assert sum(1 for i in tanim.islemler if i.anahtar == "cep") == 1
    assert len(_delik_noktalari(tanim)) == 4  # yalnız düşey delikler


@occt
def test_ornek_flans_gonder():
    pytest.importorskip("build123d")
    from tezgah.modelleme import ornek_model

    m = ornek_model("flans")
    p = _parca(m)
    tanim = tezgaha_gonder(m)
    assert _sikistir([i.anahtar for i in tanim.islemler]) == ["yuzey", "cep", "kontur", "delik"]
    st = tanim.kurulum.stock
    b0, b1 = p.bbox
    np.testing.assert_allclose(
        (st.xmin, st.ymin, st.zmin, st.xmax, st.ymax, st.zmax),
        (b0[0] - 2, b0[1] - 2, b0[2], b1[0] + 2, b1[1] + 2, b1[2] + 1),
        atol=1e-9,
    )
    (c,) = [i for i in tanim.islemler if i.anahtar == "cep"]
    assert _kesen(c.op, b1[2])[:, 2].min() == pytest.approx(b1[2] - 8.0, abs=1e-9)
    N = sorted(_delik_noktalari(tanim))
    assert len(N) == 4
    np.testing.assert_allclose(N, sorted((h.origin[0], h.origin[1]) for h in p.holes if h.through), atol=1e-9)


# SPEC 24 K2 ve K5 bu iş için de geçer.


def _okuyucu_uc(metin: str, tanim, i: int):
    from cam.gcode import read

    tools = {isl.op.tool.id: isl.op.tool for isl in tanim.islemler}
    S = metin.splitlines()
    mv = [m for tp in read("\n".join(S[: i + 1]) + "\n", tools, tanim.dialect) for m in tp.moves]
    return np.array(mv[-1].end) if mv else None


@occt
@pytest.mark.parametrize("kaynak", ["test", "ornek"])
def test_gonder_k2_gcode_okuyucu(kaynak):
    pytest.importorskip("build123d")
    from tezgah.kopru import gcode_satirlari, hareketler
    from tezgah.modelleme import ornek_model

    tanim = tezgaha_gonder(mo.flans() if kaynak == "test" else ornek_model("flans"))
    H = hareketler(tanim)
    G, SH = gcode_satirlari(tanim)
    metin = "\n".join(g["metin"] for g in G) + "\n"
    hareketli = [i for i, ar in enumerate(SH) if ar is not None]
    assert hareketli
    if len(hareketli) > 30:
        sec = np.unique(np.linspace(0, len(hareketli) - 1, 30).round().astype(int))
        hareketli = [hareketli[j] for j in sec]
    for i in hareketli:
        p = _okuyucu_uc(metin, tanim, i)
        assert p is not None, G[i]["metin"]
        assert np.max(np.abs(np.array(H[SH[i][1]]["b"]) - p)) <= 5e-4, G[i]["metin"]


@occt
@pytest.mark.parametrize("kaynak", ["test", "ornek"])
def test_gonder_k5_kontroller_hepsi_tamam(kaynak):
    pytest.importorskip("build123d")
    pytest.importorskip("cam.sim", reason="SPEC 05 (cam.sim) henüz yok")
    from tezgah.kopru import is_json, kontroller
    from tezgah.modelleme import ornek_model

    tanim = tezgaha_gonder(mo.flans() if kaynak == "test" else ornek_model("flans"))
    K = kontroller(tanim)
    assert K and all(k["durum"] == "tamam" for k in K), [(k["kimlik"], k["durum"], k["aciklama"]) for k in K]
    J = is_json(tanim)
    assert J == json_tur(J)
    assert not math.isnan(J["sure"]["toplam"]) and J["sure"]["toplam"] > 0
