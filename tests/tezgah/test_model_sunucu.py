"""SPEC 26 K7 ve REST uçları — modelleme ekranının sunucu uçları.

Testler SPEC 26 "REST uçları" tablosundan yazıldı; sunucu ve köprü gövdeleri okunmadı. Uç önekleri A3 ekran
kaydına göredir (SPEC 26 Ek A): `tezgah/ekranlar/model.py` `EKRAN`, uçlar `/api/ekran/model/...` altında;
gövdeler ve 422 kuralı SPEC 26 tablosundaki gibi.
Beklenen yanıtlar `sketch.solver.solve` / `drag` ve `tezgah.modelleme.insa`'dan hesaplanır.
Sunucu testleri `[web]` (fastapi + httpx) kurulu değilse atlanır.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from sketch.model import Constraint, Plane, Point, Sketch
from sketch.model import ConstraintType as CT
from sketch.solver import SolveResult, drag, solve
from tests.tezgah import model_ornekler as mo
from tezgah import SEMA

ON = "/api/ekran/model"
OCTET = "application/octet-stream"
occt = pytest.mark.occt


def _istemci():
    """Yalnız model ekranlı uygulama (A3: `uygulama(None, ekranlar=[model.EKRAN])`), durum sıfırlanmış."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.ekranlar import model
    from tezgah.sunucu import uygulama

    c = TestClient(uygulama(None, ekranlar=[model.EKRAN]))
    y = c.post("/api/sifirla")  # ekran durumu (model) varsayılana: ornek_model()
    assert y.status_code == 200, y.text
    return c


def json_tur(x):
    return json.loads(json.dumps(x, allow_nan=False))


def cozum_denetle(J: dict, res: SolveResult) -> None:
    """Yanıt, SolveResult'ın kayıpsız JSON karşılığı."""
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


# --- K7: eskiz uçları ---------------------------------------------------------------------------------


@pytest.mark.parametrize("tam", [True, False])
def test_eskiz_coz_solve_ile_birebir(tam):
    c = _istemci()
    sk = mo.dikdortgen_eskiz(0.0, 0.0, 40.0, 30.0, tam=tam)
    y = c.post(f"{ON}/eskiz/coz", json={"eskiz": sk.to_dict()})
    assert y.status_code == 200, y.text
    cozum_denetle(y.json(), solve(sk))


def test_eskiz_coz_daire_uzerinde_yon():
    c = _istemci()
    from sketch.model import Circle

    sk = Sketch(
        points={"m": Point(0.0, 0.0, fixed=True), "p": Point(7.0, 7.5)},
        entities={"o": Circle("m", 10.0)},
        constraints=[Constraint(CT.RADIUS, ("o",), 10.0), Constraint(CT.POINT_ON_CIRCLE, ("p", "o"))],
    )
    y = c.post(f"{ON}/eskiz/coz", json={"eskiz": sk.to_dict()})
    assert y.status_code == 200, y.text
    res = solve(sk)
    assert res.directions
    cozum_denetle(y.json(), res)


def test_eskiz_coz_celiski_422_kisitlar():
    c = _istemci()
    sk = mo.dikdortgen_eskiz(0.0, 0.0, 40.0, 30.0)
    sk.constraints.append(Constraint(CT.LENGTH, ("ust",), 45.0))
    from sketch.model import SketchError

    with pytest.raises(SketchError) as e:
        solve(sk)
    y = c.post(f"{ON}/eskiz/coz", json={"eskiz": sk.to_dict()})
    assert y.status_code == 422
    d = y.json()["detail"]
    assert isinstance(d["hata"], str) and d["hata"]
    assert sorted(d["kisitlar"]) == sorted(e.value.constraints)


def test_eskiz_coz_bozuk_eskiz_422():
    c = _istemci()
    d = mo.dikdortgen_eskiz(0.0, 0.0, 4.0, 3.0).to_dict()
    d["entities"]["alt"]["p1"] = "yok"
    y = c.post(f"{ON}/eskiz/coz", json={"eskiz": d})
    assert y.status_code == 422


@pytest.mark.parametrize("nokta, hedef", [("c", [41.0, 45.0]), ("d", [-3.0, 12.5])])
def test_eskiz_surukle_drag_ile_birebir(nokta, hedef):
    c = _istemci()
    sk = mo.dikdortgen_eskiz(0.0, 0.0, 40.0, 30.0, tam=False)
    y = c.post(f"{ON}/eskiz/surukle", json={"eskiz": sk.to_dict(), "nokta": nokta, "hedef": hedef})
    assert y.status_code == 200, y.text
    cozum_denetle(y.json(), drag(sk, nokta, tuple(hedef)))


def test_eskiz_surukle_sabit_nokta_422():
    c = _istemci()
    sk = mo.dikdortgen_eskiz(0.0, 0.0, 40.0, 30.0, tam=False)
    y = c.post(f"{ON}/eskiz/surukle", json={"eskiz": sk.to_dict(), "nokta": "a", "hedef": [5.0, 5.0]})
    assert y.status_code == 422
    assert y.json()["detail"]


# --- Model uçları -------------------------------------------------------------------------------------


@occt
def test_varsayilan_model_ornek_flans():
    pytest.importorskip("build123d")
    from tezgah.modelleme import ornek_model

    c = _istemci()
    y = c.get(f"{ON}/")
    assert y.status_code == 200, y.text
    assert y.json() == json_tur(ornek_model("flans"))


@occt
def test_put_model_rapor_ve_get():
    pytest.importorskip("build123d")
    from tezgah.model_kopru import rapor_json
    from tezgah.modelleme import insa

    c = _istemci()
    m = mo.plaka()
    y = c.put(f"{ON}/", json=m)
    assert y.status_code == 200, y.text
    J = y.json()
    assert J["sema"] == SEMA
    _, r = insa(m)
    assert J["rapor"] == json_tur(rapor_json(r))
    assert c.get(f"{ON}/").json() == json_tur(m)


@occt
def test_put_hatali_adim_rapor_dondurur():
    """Kurulum hatası (çelişki, GeometryError) PUT'u düşürmez: rapor adım kimlikli hatayı taşır."""
    pytest.importorskip("build123d")
    from tezgah.model_kopru import rapor_json
    from tezgah.modelleme import insa

    c = _istemci()
    m = mo.flans()
    m["adimlar"][2]["eskiz"] = mo.dikdortgen_eskiz(500, 500, 40, 30, plane=mo.duzlem_xy(mo.FL_C)).to_dict()
    y = c.put(f"{ON}/", json=m)
    _, r = insa(m)
    assert r.hata is not None
    if y.status_code == 200:
        assert y.json()["rapor"] == json_tur(rapor_json(r))
    else:
        assert y.status_code == 422
        assert y.json()["detail"]


@occt
def test_ag_k_adim_insa_ile_ayni():
    pytest.importorskip("build123d")
    from tezgah.model_kopru import ag_coz, ag_ikili
    from tezgah.modelleme import insa

    c = _istemci()
    m = mo.flans()
    assert c.put(f"{ON}/", json=m).status_code == 200
    for k in (2, 4, None):
        url = f"{ON}/ag" if k is None else f"{ON}/ag?k={k}"
        y = c.get(url)
        assert y.status_code == 200, y.text
        assert y.headers["content-type"].startswith(OCTET)
        A = ag_coz(y.content)
        B = ag_coz(ag_ikili(insa(m, k)[0]))
        for ad in ("kose", "ucgen", "yuz"):
            np.testing.assert_array_equal(A[ad], B[ad])


@occt
def test_ag_katisiz_adim_422():
    pytest.importorskip("build123d")
    c = _istemci()
    assert c.put(f"{ON}/", json=mo.flans()).status_code == 200
    assert c.get(f"{ON}/ag?k=1").status_code == 422


@occt
def test_yuz_ucu():
    pytest.importorskip("build123d")
    from geometry.extrude import face_outline, face_plane
    from tezgah.modelleme import insa

    c = _istemci()
    m = mo.plaka()
    assert c.put(f"{ON}/", json=m).status_code == 200
    p, _ = insa(m)
    i = max((f for f in p.planar_faces() if f.normal[2] > 0.5), key=lambda f: f.origin[2]).index
    y = c.get(f"{ON}/yuz/{i}")
    assert y.status_code == 200, y.text
    J = y.json()
    assert Plane.from_dict(J["plane"]).to_dict() == face_plane(p, i).to_dict()
    assert len(J["outline"]) == len(face_outline(p, i))
    assert c.get(f"{ON}/yuz/9999").status_code == 422


@occt
def test_tezgaha_gonder_ucu():
    pytest.importorskip("build123d")
    pytest.importorskip("cam.sim", reason="SPEC 05 (cam.sim) henüz yok")
    from tezgah.kopru import is_json
    from tezgah.model_kopru import tezgaha_gonder

    c = _istemci()
    m = mo.flans()
    assert c.put(f"{ON}/", json=m).status_code == 200
    y = c.post(f"{ON}/tezgaha-gonder")
    assert y.status_code == 200, y.text
    J = y.json()
    beklenen = json_tur(is_json(tezgaha_gonder(m)))
    assert J["sema"] == SEMA
    assert J["kurulum"] == beklenen["kurulum"]
    assert [i["anahtar"] for i in J["islemler"]] == [i["anahtar"] for i in beklenen["islemler"]]
    assert J["gcode"] == beklenen["gcode"]
    assert all(k["durum"] == "tamam" for k in J["kontroller"]), J["kontroller"]


@occt
def test_tezgaha_gonder_yan_yuz_uyarisi():
    """+Z dışı yüzden kesim / delik işlenmez; atlandıkları `uyari` kontrolüyle listelenir."""
    pytest.importorskip("build123d")
    pytest.importorskip("cam.sim", reason="SPEC 05 (cam.sim) henüz yok")
    from tests.tezgah.test_model_kopru import yan_yuzlu_flans

    c = _istemci()
    assert c.put(f"{ON}/", json=yan_yuzlu_flans()).status_code == 200
    y = c.post(f"{ON}/tezgaha-gonder")
    assert y.status_code == 200, y.text
    uyari = [k for k in y.json()["kontroller"] if k["durum"] == "uyari"]
    assert uyari
    assert all(k["spec"].startswith("SPEC ") for k in uyari)


# --- Ek A: "model" bölümü (A3 ekran sözleşmesi) -------------------------------------------------------


def test_ekran_kaydi():
    pytest.importorskip("fastapi")
    from tezgah.ekranlar import model

    E = model.EKRAN
    assert (E.ad, E.tus, E.bolum) == ("model", "7", "model")
    assert E.router is not None and E.disa_aktar and E.ice_aktar and E.sifirla


@occt
def test_bolum_disa_aktar_put_edilen_model():
    pytest.importorskip("build123d")
    from tezgah.ekranlar import model

    c = _istemci()
    m = mo.plaka()
    assert c.put(f"{ON}/", json=m).status_code == 200
    belge = model.EKRAN.disa_aktar()
    assert belge == json_tur(belge)
    assert belge["sema"] == 1
    assert belge == json_tur(m)


@occt
def test_bolum_ice_aktar_atomik():
    pytest.importorskip("build123d")
    from tezgah.ekranlar import model

    c = _istemci()
    assert c.put(f"{ON}/", json=mo.plaka()).status_code == 200
    once = model.EKRAN.disa_aktar()
    model.EKRAN.ice_aktar(once, {})
    assert model.EKRAN.disa_aktar() == once
    with pytest.raises(Exception):  # noqa: B017 - A3: bozuk belge hata verir, tür ekranın çekirdek hatası
        model.EKRAN.ice_aktar({"sema": 99, "adimlar": "bozuk"}, {})
    assert model.EKRAN.disa_aktar() == once
    m = mo.flans()
    model.EKRAN.ice_aktar(m, {})
    assert c.get(f"{ON}/").json() == json_tur(m)
