"""
SPEC 47a — Plan ekranının köprüsü (`tezgah/ekranlar/plan_kopru.py`): K2 plan JSON'u, K3 sessiz atlama yok,
K4 "Ne olurdu?" farkı, K5 doğrulama, K21 doğrulama önbelleği (oturum düzeyi).

Beklenen değerler köprüden değil, SPEC 29'un kendi fonksiyonlarından hesaplanır (`plan_ortak.planla`:
`plan_mill`, `plan_mill_features`, `plan_turn`; `summary`, `unplanned`, `notes`, `tool_changes`, `gcode`,
`verify_mill`, `verify_turn`). Fark ve kontrol kuralları ayrıca elle kurulmuş `Plan` sözlükleriyle
(SPEC 29'suz) denetlenir. `[web]` yoksa dosya atlanır (`tezgah.ekranlar` paketi FastAPI ister);
SPEC 29 / 28 kodu ya da
OCCT gerektiren testler onlar yokken atlanır.
"""

from __future__ import annotations

import dataclasses
import json
import math

import numpy as np
import pytest

pytest.importorskip("fastapi", reason="[web] kurulu değil (pip install -e .[web])")

from cam.gcode import GRBL  # noqa: E402
from cam.model import CamError, CuttingData, MoveType, Tool, ToolKind, ToolLibrary, Toolpath  # noqa: E402
from tests.tezgah.ekranlar import plan_ortak as o  # noqa: E402
from tezgah.ekranlar import plan_kopru as pk  # noqa: E402

FARK_ALANLARI = (
    "eklenen",
    "cikan",
    "takimi_degisen",
    "yeni_planlanamayan",
    "kurtulan",
    "sure_farki",
    "takim_degisimi_farki",
)
DOGRULAMA_SAYILARI = ("removed_volume", "rest_volume", "gouge_volume", "expected_rest", "total_time")


def _sirasiz(F: dict) -> dict:
    """Fark listelerinin sırası tanımlı değil: karşılaştırma için kanonik sıraya dizer."""
    return {
        k: sorted(v, key=lambda x: json.dumps(x, sort_keys=True)) if isinstance(v, list) else v
        for k, v in F.items()
        if k in FARK_ALANLARI
    }


def _bos_fark(F: dict) -> None:
    for k in FARK_ALANLARI[:5]:
        assert F[k] == [], (k, F[k])
    assert F["sure_farki"] == pytest.approx(0.0, abs=1e-9)
    assert F["takim_degisimi_farki"] == 0


def _plan_sozlugu(g, plan, **kw) -> dict:
    return o.jt(pk.plan_json(g.ad, plan, g.lib, secenekler=g.secenekler, **kw))


# ---------------------------------------------------------------- SPEC 29'suz saf parçalar


def test_gerekce_ve_not_metinleri():
    """SPEC 29 §1'deki 10 gerekçe ve 4 not kodunun hepsinin düz Türkçesi var; metinler farklı."""
    assert set(pk.GEREKCE_METNI) == set(o.GEREKCE_KODLARI)
    assert set(pk.NOT_METNI) == set(o.NOT_KODLARI)
    for tablo in (pk.GEREKCE_METNI, pk.NOT_METNI):
        assert all(isinstance(m, str) and m.strip() for m in tablo.values())
        assert len(set(tablo.values())) == len(tablo)
        assert all(m != k for k, m in tablo.items())


@pytest.mark.parametrize(
    "feature, beklenen",
    [
        ("holes[1,4]", ["holes[1]", "holes[4]"]),
        ("holes[0,2,10]", ["holes[0]", "holes[2]", "holes[10]"]),
        ("holes[3]", ["holes[3]"]),
        ("pockets[2]", ["pockets[2]"]),
        ("faces[0]", ["faces[0]"]),
        ("alt_yuz", ["alt_yuz"]),
        ("grooves[1]", ["grooves[1]"]),
        ("dis", ["dis"]),
    ],
)
def test_grup_ac(feature, beklenen):
    assert pk.grup_ac(feature) == beklenen


def _lib() -> ToolLibrary:
    al = {"al": CuttingData(Vc=200.0, fz=0.05, ap=2.0, ae=3.0)}
    return ToolLibrary(
        [
            Tool(1, "f16", ToolKind.FLAT, 16.0, 30.0, flutes=3, cutting=dict(al)),
            Tool(2, "f10", ToolKind.FLAT, 10.0, 25.0, flutes=3, cutting=dict(al)),
            Tool(11, "m8", ToolKind.DRILL, 8.0, 40.0, flutes=2, cutting={"al": CuttingData(Vc=80.0, fz=0.1)}),
        ]
    )


def test_kutuphane_suz():
    """Takımı kapatmak: o takım çıkarılmış YENİ kütüphane; girdi değişmez; bilinmeyen kimlik → CamError."""
    lib = _lib()
    once = lib.to_dict()
    yeni = pk.kutuphane_suz(lib, frozenset({2}))
    assert isinstance(yeni, ToolLibrary)
    assert yeni is not lib
    assert [t.id for t in yeni.tools] == [1, 11]
    assert lib.to_dict() == once
    assert pk.kutuphane_suz(lib, frozenset()).to_dict() == once
    assert pk.kutuphane_suz(lib, frozenset({1, 2, 11})).tools == []  # son freze takımı da kapatılabilir
    with pytest.raises(CamError):
        pk.kutuphane_suz(lib, frozenset({99}))
    assert lib.to_dict() == once


def test_ag_ikili_geri_donus():
    """Parça ağı ikilisi: başlık uint32 nv, nt; float32[nv·3] bayt 8'den; `ag_coz` tam tersi."""
    V = np.array([[0, 0, 0], [100, 0, 0], [100, 60, 0], [0.125, 60, 20.5], [1 / 3, 2, 3]], dtype=float)
    T = np.array([[0, 1, 2], [0, 2, 3], [1, 4, 2]], dtype=np.int64)
    b = pk.ag_ikili(V, T)
    assert isinstance(b, bytes)
    assert np.frombuffer(b, dtype="<u4", count=2).tolist() == [5, 3]
    assert len(b) >= 8 + 12 * 5 + 12 * 3
    assert np.array_equal(np.frombuffer(b, dtype="<f4", count=15, offset=8), V.astype("<f4").ravel())
    V2, T2 = pk.ag_coz(b)
    assert V2.dtype == np.float32 and V2.shape == (5, 3)
    assert T2.dtype == np.uint32 and T2.shape == (3, 3)
    assert np.array_equal(V2, V.astype(np.float32))
    assert np.array_equal(T2, T.astype(np.uint32))
    V0, T0 = pk.ag_coz(pk.ag_ikili(np.zeros((0, 3)), np.zeros((0, 3), dtype=int)))
    assert V0.shape == (0, 3) and T0.shape == (0, 3)


# ---------------------------------------------------------------- K4: plan farkı, elle kurulmuş sözlükler


def _satir(name, kind, feature, tool_id, sure, setup=0) -> dict:
    return {
        "name": name,
        "kind": kind,
        "setup": setup,
        "feature": feature,
        "tool_id": tool_id,
        "n": 8000.0,
        "F": 1200.0,
        "a_p": 2.0,
        "stepover": 4.0,
        "sure": sure,
    }


def _ples(adres, kod) -> dict:
    return {"adres": adres, "kod": kod, "detay": "uydurma", "metin": pk.GEREKCE_METNI[kod]}


def _sentetik(islemler: list[dict], planlanamayan: list[dict], takim_degisimi: int, sil=()) -> dict:
    """SPEC 47 şemasında elle kurulmuş `Plan` sözlüğü (SPEC 29'suz); `sil` ozellikler'den çıkar."""
    tasiyan: dict[str, list[str]] = {}
    for s in islemler:
        for a in o.ac(s["feature"]):
            tasiyan.setdefault(a, []).append(s["name"])
    kodlar = {p["adres"]: p["kod"] for p in planlanamayan}
    adresler = sorted(set(tasiyan) | set(kodlar))
    ozellikler = []
    for a in adresler:
        if a in sil:
            continue
        oz = {"adres": a, "tur": a.split("[")[0], "islemler": tasiyan.get(a, []), "geometri": {}}
        if a in kodlar:
            oz.update(durum="planlanamadi", kod=kodlar[a])
        else:
            oz["durum"] = "planlandi"
        ozellikler.append(oz)
    ids = sorted({s["tool_id"] for s in islemler})
    return {
        "sema": 1,
        "ad": "sentetik",
        "tur": "freze",
        "malzeme": "al",
        "baglamalar": [
            {
                "i": 0,
                "wcs": "G54",
                "stok": {"x0": 0.0, "x1": 100.0, "y0": 0.0, "y1": 60.0, "z0": 0.0, "z1": 22.0},
                "fiksturler": [],
            }
        ],
        "ozellikler": ozellikler,
        "islemler": islemler,
        "planlanamayan": planlanamayan,
        "notlar": [],
        "takim_degisimi": takim_degisimi,
        "takimlar": [{"id": i, "ad": f"T{i}", "tur": "flat", "D": 10.0, "acik": True} for i in ids],
        "secenekler": {},
        "dogrulama": None,
        "gcode": [["G90"]],
        "kontroller": [],
    }


def _eski() -> dict:
    return _sentetik(
        [
            _satir("01-yuz_alma-T1", "yuz_alma", "faces[0]", 1, 10.0),
            _satir("02-cep-T1", "cep", "pockets[0]", 1, 20.0),
            _satir("03-cep_kalan-T2", "cep_kalan", "pockets[0]", 2, 5.0),
            _satir("04-delik-T11", "delik", "holes[0,1]", 11, 3.0),
        ],
        [_ples("holes[2]", "takim_yok"), _ples("holes[3]", "havsa_takimi_yok")],
        3,
    )


def _yeni() -> dict:
    return _sentetik(
        [
            _satir("01-yuz_alma-T2", "yuz_alma", "faces[0]", 2, 12.0),
            _satir("02-cep-T2", "cep", "pockets[0]", 2, 30.0),
            _satir("03-delik-T11", "delik", "holes[0,1]", 11, 3.0),  # ad kaydı ama çift aynı: değişiklik yok
            _satir("04-delik-T14", "delik", "holes[2]", 14, 1.25),
        ],
        [_ples("holes[3]", "havsa_takimi_yok"), _ples("pockets[1]", "takim_sigmiyor")],
        5,
    )


def test_plan_farki_elle():
    """İşlemler `(feature, kind)` çiftiyle eşlenir (ad sıra numarası içerir, kayabilir)."""
    F = o.jt(pk.plan_farki(_eski(), _yeni()))
    assert set(FARK_ALANLARI) <= set(F)
    assert _sirasiz(F) == _sirasiz(
        {
            "eklenen": ["04-delik-T14"],
            "cikan": ["03-cep_kalan-T2"],
            "takimi_degisen": [
                {"adres": "faces[0]", "once": 1, "sonra": 2},
                {"adres": "pockets[0]", "once": 1, "sonra": 2},
            ],
            "yeni_planlanamayan": [{"adres": "pockets[1]", "kod": "takim_sigmiyor"}],
            "kurtulan": ["holes[2]"],
            "sure_farki": 46.25 - 38.0,
            "takim_degisimi_farki": 2,
        }
    )
    assert F["sure_farki"] == pytest.approx(8.25, rel=1e-12)


def test_plan_farki_ters_ve_bos():
    G = o.jt(pk.plan_farki(_yeni(), _eski()))
    assert sorted(G["eklenen"]) == ["03-cep_kalan-T2"]
    assert sorted(G["cikan"]) == ["04-delik-T14"]
    assert _sirasiz(G)["takimi_degisen"] == [
        {"adres": "faces[0]", "once": 2, "sonra": 1},
        {"adres": "pockets[0]", "once": 2, "sonra": 1},
    ]
    assert G["yeni_planlanamayan"] == [{"adres": "holes[2]", "kod": "takim_yok"}]
    assert G["kurtulan"] == ["pockets[1]"]
    assert G["sure_farki"] == pytest.approx(-8.25, rel=1e-12)
    assert G["takim_degisimi_farki"] == -2
    _bos_fark(o.jt(pk.plan_farki(_eski(), _eski())))
    eski = _eski()
    kopya = json.loads(json.dumps(eski))
    pk.plan_farki(eski, _yeni())
    assert eski == kopya  # girdi sözlükleri değişmez


# ---------------------------------------------------------------- K3: kontroller, elle kurulmuş sözlükler


def test_kontroller_elle():
    """Doğrulama yokken yalnız plan kontrolleri; `dogrulama_*`, `kalan_malzeme` listede yok (sahte tamam)."""
    P = _eski()
    K = o.jt(pk.kontroller(P))
    assert {k["kimlik"] for k in K} == {"sessiz_atlama", "planlanamayan", "takim_degisimi"}
    assert o.kontrol(K, "sessiz_atlama")["durum"] == "tamam"
    k = o.kontrol(K, "planlanamayan")
    assert (k["durum"], k["deger"]) == ("uyari", 2)
    k = o.kontrol(K, "takim_degisimi")
    assert (k["durum"], k["deger"]) == ("tamam", 3)


@pytest.mark.parametrize("silinen", ["pockets[0]", "holes[1]", "holes[0]", "holes[2]", "faces[0]"])
def test_sessiz_atlama_elle(silinen):
    """`ozellikler`'den bir adres silinince (planlanan, grupta ya da planlanamayan) `sessiz_atlama` hata."""
    e = _eski()
    P = _sentetik(e["islemler"], e["planlanamayan"], e["takim_degisimi"], sil={silinen})
    assert silinen not in [oz["adres"] for oz in P["ozellikler"]]
    assert o.kontrol(o.jt(pk.kontroller(P)), "sessiz_atlama")["durum"] == "hata"


def test_planlanamayan_yokken_tamam():
    e = _eski()
    P = _sentetik(e["islemler"], [], e["takim_degisimi"])
    k = o.kontrol(o.jt(pk.kontroller(P)), "planlanamayan")
    assert k["durum"] == "tamam"
    assert k["deger"] == 0


def _check(**kw):
    o.spec29()
    from cam.plan_verify import PlanCheck

    alan = {
        "ok": True,
        "collisions": (),
        "removed_volume": 1000.0,
        "rest_volume": 12.5,
        "gouge_volume": 0.0,
        "expected_rest": 12.5,
        "total_time": 321.0,
    }
    return PlanCheck(**{**alan, **kw})


def test_dogrulama_sozlugu():
    from cam.sim import Collision

    c = Collision("cakma", 7, 0, (10.0, 20.0, 5.5), 0.25)
    chk = _check(ok=False, collisions=(c,), gouge_volume=0.75)
    d = o.jt(pk.dogrulama_sozlugu(chk))
    assert d["ok"] is False
    for alan in DOGRULAMA_SAYILARI:
        assert d[alan] == getattr(chk, alan)
    assert len(d["collisions"]) == 1


def test_dogrulama_kontrolleri_elle():
    """`dogrulama` doluyken `dogrulama_carpma` (çarpışma sayısı), `dogrulama_cakma` (çakma hacmi)."""
    from cam.sim import Collision

    P = _eski()
    P["dogrulama"] = o.jt(pk.dogrulama_sozlugu(_check()))
    K = o.jt(pk.kontroller(P))
    assert {"dogrulama_carpma", "dogrulama_cakma", "kalan_malzeme"} <= {k["kimlik"] for k in K}
    assert o.kontrol(K, "dogrulama_carpma")["durum"] == "tamam"
    assert o.kontrol(K, "dogrulama_cakma")["durum"] == "tamam"
    o.kontrol(K, "kalan_malzeme")

    c = Collision("tutucu_carpma", 3, 1, (0.0, 0.0, 10.0), 1.5)
    P["dogrulama"] = o.jt(pk.dogrulama_sozlugu(_check(ok=False, collisions=(c, c))))
    K = o.jt(pk.kontroller(P))
    assert o.kontrol(K, "dogrulama_carpma")["durum"] == "hata"
    assert o.kontrol(K, "dogrulama_cakma")["durum"] == "tamam"

    P["dogrulama"] = o.jt(pk.dogrulama_sozlugu(_check(ok=False, gouge_volume=0.5)))
    K = o.jt(pk.kontroller(P))
    assert o.kontrol(K, "dogrulama_cakma")["durum"] == "hata"
    assert o.kontrol(K, "dogrulama_carpma")["durum"] == "tamam"


# ---------------------------------------------------------------- K2: plan JSON'u (SPEC 29 ile)


@pytest.mark.parametrize("ad", o.HEPSI)
def test_plan_json(ad):
    g = o.girdi(ad)
    plan = o.planla(g)
    P = _plan_sozlugu(g, plan)
    assert (P["sema"], P["ad"], P["tur"], P["malzeme"]) == (1, g.ad, g.tur, g.malzeme)

    # islemler = summary() satırları (aynı sıra, aynı değer) + süre
    assert o.ozet_satirlari(P) == o.jt(plan.summary())
    assert [s["sure"] for s in P["islemler"]] == pytest.approx(pk.islem_sureleri(plan), rel=1e-12)

    # planlanamayan ve notlar birebir; metin gerekçe / not tablosundan
    assert P["planlanamayan"] == o.jt(
        [
            {"adres": u.feature, "kod": u.code, "detay": u.detail, "metin": pk.GEREKCE_METNI[u.code]}
            for u in plan.unplanned
        ]
    )
    assert P["notlar"] == o.jt(
        [
            {
                "adres": n.feature,
                "kod": n.code,
                "deger": n.value,
                "detay": n.detail,
                "metin": pk.NOT_METNI[n.code],
            }
            for n in plan.notes
        ]
    )
    assert P["takim_degisimi"] == o.takim_degisimi(plan)

    # G-code: bağlama başına program, satır satır
    if g.tur == "freze":
        programlar = plan.gcode(g.lib, GRBL, program_no=1)
        assert len(programlar) == len(plan.setups)
        assert P["gcode"] == [p.splitlines() for p in programlar]
        setups = plan.setups
    else:
        assert P["gcode"] == [plan.gcode(spindle="M3", tool_change=(50, 80)).splitlines()]
        setups = (plan.setup,)

    assert [b["i"] for b in P["baglamalar"]] == list(range(len(setups)))
    for b, s in zip(P["baglamalar"], setups, strict=True):
        assert b["wcs"] in (s.wcs.code, o.jt(s.wcs.to_dict()))

    # kütüphane: hepsi açık
    assert sorted(t["id"] for t in P["takimlar"]) == sorted(t.id for t in g.lib.tools)
    adlar = {t.id: t.name for t in g.lib.tools}
    assert all(t["acik"] is True and t["ad"] == adlar[t["id"]] for t in P["takimlar"])

    # seçenekler: MillOptions / TurnOptions alanları, örneğin değerleriyle
    if g.tur == "freze":
        from cam.plan import MillOptions as Opt
    else:
        from cam.plan_turn import TurnOptions as Opt
    assert set(P["secenekler"]) == {f.name for f in dataclasses.fields(Opt)}
    for k, v in g.secenekler.items():
        assert P["secenekler"][k] == v

    # doğrulama yapılmadı: alan boş, doğrulama kontrolleri yok
    assert P["dogrulama"] is None
    kimlikler = {k["kimlik"] for k in P["kontroller"]}
    assert not kimlikler & {"dogrulama_carpma", "dogrulama_cakma", "kalan_malzeme"}
    assert P["kontroller"] == o.jt(pk.kontroller(P))


@pytest.mark.parametrize("ad", o.FREZE)
def test_plan_json_kapali_takim(ad):
    """`kapali` takımlar `takimlar`'da `acik = False`; diğerleri açık."""
    g = o.girdi(ad)
    plan = o.planla(g, lib=o.suz(g.lib, {2}))
    P = _plan_sozlugu(g, plan, kapali=frozenset({2}))
    assert {t["id"]: t["acik"] for t in P["takimlar"]} == {t.id: t.id != 2 for t in g.lib.tools}
    assert o.ozet_satirlari(P) == o.jt(plan.summary())


@pytest.mark.parametrize("ad", o.HEPSI)
def test_islem_sureleri(ad):
    """İşlem başına süre sonlu, pozitif; freze yolunda en az kesme hareketinin F ile süresi (kiriş ≤ yay)."""
    g = o.girdi(ad)
    plan = o.planla(g)
    sure = pk.islem_sureleri(plan)
    assert len(sure) == len(plan.ops)
    for t, op in zip(sure, plan.ops, strict=True):
        assert math.isfinite(t) and t > 0, (op.name, t)
        if g.tur == "freze" and isinstance(op.op, Toolpath):
            alt, p = 0.0, np.array(op.op.start)
            for m in op.op.moves:
                if m.type is not MoveType.RAPID and m.feed:
                    alt += float(np.linalg.norm(np.array(m.end) - p)) / (m.feed / 60.0)
                p = np.array(m.end)
            assert t >= alt * (1 - 1e-9), (op.name, t, alt)


@pytest.mark.parametrize("ad", o.HEPSI)
def test_oturum_plani(ad):
    """`PlanOturumu` başlangıçta örneğin kendi planını verir (kapalı takım yok, örnek seçenekleri)."""
    g = o.girdi(ad)
    oturum = pk.PlanOturumu(g)
    plan = o.planla(g)
    assert o.jt(oturum.plan().summary()) == o.jt(plan.summary())
    assert o.jt(oturum.json()) == _plan_sozlugu(g, plan)


# ---------------------------------------------------------------- K3: sessiz atlama yok (SPEC 29 ile)


@pytest.mark.parametrize("ad", o.HEPSI)
def test_sessiz_atlama(ad):
    g = o.girdi(ad)
    plan = o.planla(g)
    P = _plan_sozlugu(g, plan)
    beklenen = o.ozellik_adresleri(plan)
    tasiyan = o.tasiyanlar(plan)
    kodlar: dict[str, set[str]] = {}
    for u in plan.unplanned:
        kodlar.setdefault(u.feature, set()).add(u.code)

    adresler = [oz["adres"] for oz in P["ozellikler"]]
    assert len(adresler) == len(set(adresler)), "bir adres iki kez"
    assert [a for a in adresler if a in beklenen] == beklenen, "SPEC 27 adresi eksik ya da sıra bozuk"
    assert set(adresler) - set(beklenen) <= {"alt_yuz"}
    assert set(tasiyan) | set(kodlar) <= set(adresler)
    assert pk.ozellik_adresleri(plan) == adresler

    for oz in P["ozellikler"]:
        a = oz["adres"]
        assert set(oz["islemler"]) <= tasiyan.get(a, set()), a
        if a in kodlar:
            assert oz["durum"] == "planlanamadi", a
            assert oz["kod"] in kodlar[a], a
        else:
            assert oz["durum"] == "planlandi", a
            assert oz["islemler"], a
        assert "geometri" in oz
    # SPEC 29: hiçbir adres ne planlandı ne planlanamadı olamaz
    assert all(a in tasiyan or a in kodlar for a in beklenen)

    assert P["ozellikler"] == o.jt(pk.ozellik_eslemesi(plan))
    assert o.kontrol(P["kontroller"], "sessiz_atlama")["durum"] == "tamam"
    k = o.kontrol(P["kontroller"], "planlanamayan")
    assert k["deger"] == len(plan.unplanned)
    assert k["durum"] == ("uyari" if plan.unplanned else "tamam")
    k = o.kontrol(P["kontroller"], "takim_degisimi")
    assert (k["durum"], k["deger"]) == ("tamam", o.takim_degisimi(plan))


@pytest.mark.parametrize("ad", o.HEPSI)
def test_sessiz_atlama_silinen_adres(ad):
    """Gerçek bir plan sözlüğünden bir adres elle silinince `sessiz_atlama` hata."""
    g = o.girdi(ad)
    plan = o.planla(g)
    P = _plan_sozlugu(g, plan)
    silinecek = [o.ozellik_adresleri(plan)[0]] + [u.feature for u in plan.unplanned[:1]]
    for a in silinecek:
        Q = json.loads(json.dumps(P))
        Q["ozellikler"] = [oz for oz in Q["ozellikler"] if oz["adres"] != a]
        assert o.kontrol(o.jt(pk.kontroller(Q)), "sessiz_atlama")["durum"] == "hata", a


def test_sessiz_atlama_engelli():
    """`plan_engelli`: gerekçe kodları tam olarak dört kod; `kose_artigi` notu SPEC 29 K3 formülüyle."""
    g = o.girdi("plan_engelli")
    plan = o.planla(g)
    P = _plan_sozlugu(g, plan)
    dort = {"havsa_takimi_yok", "kilavuz_cevrimi_yok", "ustten_erisilemez", "takim_yok"}
    assert {u.code for u in plan.unplanned} == dort
    assert {p["kod"] for p in P["planlanamayan"]} == dort
    assert len(P["planlanamayan"]) == len(plan.unplanned)
    planlanamadi = [oz for oz in P["ozellikler"] if oz["durum"] == "planlanamadi"]
    assert {oz["kod"] for oz in planlanamadi} == dort

    notlar = [n for n in P["notlar"] if n["kod"] == "kose_artigi"]
    assert len(notlar) == 1
    n = notlar[0]
    assert n["adres"].startswith("pockets[")
    cep = g.features.pockets[int(n["adres"][len("pockets[") : -1])]
    assert cep.r_corner == 0.0  # K3 keskin köşeli cep
    son = [op for op in plan.ops if op.feature == n["adres"]][-1]
    r = g.lib.get(son.tool_id).D / 2
    assert r in (3.0, 2.0)  # SPEC 29 K3: T3 (Ø6, stok üstü 22) ya da T4 (Ø4, stok üstü 20)
    # dört dik köşe: A = (r² − 0)(tan 45° − π/4) = r²(1 − π/4); V = 4·A·(z_t − z_b)
    V = 4 * r**2 * (1 - math.pi / 4) * (cep.z_top - cep.z_bottom)
    assert n["deger"] == pytest.approx(V, rel=1e-9)
    assert n["metin"] == pk.NOT_METNI["kose_artigi"]


def test_geometri_engelli():
    """Özellik geometrisi kendi kaydından: delik {merkez, eksen, D, derinlik}, cep {z_ust, z_alt, dis}."""
    g = o.girdi("plan_engelli")
    P = _plan_sozlugu(g, o.planla(g))
    oz = {x["adres"]: x["geometri"] for x in P["ozellikler"]}
    for i, hf in enumerate(g.features.holes):
        G = oz[f"holes[{i}]"]
        assert G["merkez"] == pytest.approx(list(hf.hole.origin), abs=1e-9)
        assert G["eksen"] == pytest.approx(list(hf.hole.axis), abs=1e-9)
        assert G["D"] == pytest.approx(hf.hole.d, abs=1e-9)
        assert G["derinlik"] == pytest.approx(hf.hole.depth, abs=1e-9)
    for i, cep in enumerate(g.features.pockets):
        G = oz[f"pockets[{i}]"]
        assert G["z_ust"] == pytest.approx(cep.z_top, abs=1e-9)
        assert G["z_alt"] == pytest.approx(cep.z_bottom, abs=1e-9)
        assert len(G["dis"]) >= 3 and all(len(p) == 2 for p in G["dis"])
        assert len(G["adalar"]) == len(cep.region.holes)


# ---------------------------------------------------------------- K4: "Ne olurdu?" (SPEC 29 ile)


def _ciftler(plan, tool_id=None) -> dict[tuple[str, str], int]:
    return {(op.feature, op.kind): op.tool_id for op in plan.ops if tool_id is None or op.tool_id == tool_id}


def _ne_olurdu_ortak(oturum, J0, r, eski, yeni) -> None:
    """Yanıt planı doğrudan SPEC 29 planıyla aynı; fark `plan_farki(eski, yeni)`; süre farkları."""
    P, F = r["plan"], r["fark"]
    assert o.ozet_satirlari(P) == o.jt(yeni.summary())
    assert set(FARK_ALANLARI) <= set(F)
    assert _sirasiz(F) == _sirasiz(o.jt(pk.plan_farki(J0, P)))
    beklenen = sum(pk.islem_sureleri(yeni)) - sum(pk.islem_sureleri(eski))
    assert F["sure_farki"] == pytest.approx(beklenen, rel=1e-12, abs=1e-9)
    assert F["takim_degisimi_farki"] == o.takim_degisimi(yeni) - o.takim_degisimi(eski)
    assert o.jt(oturum.json()) == P  # durum kalıcı


@pytest.mark.occt
def test_ne_olurdu_t1():
    """`plan_blogu`'da T1 (Ø16) kapanınca T1'in her `(feature, kind)` çifti `takimi_degisen`'de `once = 1`."""
    g = o.girdi("plan_blogu")
    lib0 = g.lib.to_dict()
    oturum = pk.PlanOturumu(g)
    J0 = o.jt(oturum.json())
    r = o.jt(oturum.ne_olurdu(takim_kapat=[1]))
    eski, yeni = o.planla(g), o.planla(g, lib=o.suz(g.lib, {1}))
    _ne_olurdu_ortak(oturum, J0, r, eski, yeni)

    t1 = _ciftler(eski, 1)
    assert t1, "plan_blogu'da T1 kullanılmalı"
    y = _ciftler(yeni)
    td = r["fark"]["takimi_degisen"]
    for f, k in t1:
        assert (f, k) in y, (f, k)  # T1'in her işini başka bir takım alır
        assert {"adres": f, "once": 1, "sonra": y[(f, k)]} in td, (f, k)
    assert all(op.tool_id != 1 for op in yeni.ops)
    assert {t["id"]: t["acik"] for t in r["plan"]["takimlar"]}[1] is False
    assert oturum.kapali == frozenset({1})
    assert g.lib.to_dict() == lib0  # girdi kütüphanesi değişmez


@pytest.mark.occt
def test_ne_olurdu_tum_frezeler_kapali():
    """Bütün freze takımları kapatılınca her alan özelliği `yeni_planlanamayan`'da, `kurtulan`'da değil."""
    g = o.girdi("plan_blogu")
    oturum = pk.PlanOturumu(g)
    J0 = o.jt(oturum.json())
    frezeler = [t.id for t in g.lib.tools if getattr(t, "kind", None) is ToolKind.FLAT]
    r = o.jt(oturum.ne_olurdu(takim_kapat=frezeler))
    eski, yeni = o.planla(g), o.planla(g, lib=o.suz(g.lib, frezeler))
    _ne_olurdu_ortak(oturum, J0, r, eski, yeni)

    f = eski.features
    alan = [f"faces[{i}]" for i in range(len(f.faces))]
    alan += [f"opens[{i}]" for i in range(len(f.opens))]
    alan += [f"pockets[{i}]" for i in range(len(f.pockets))]
    assert alan
    yp = {}
    for x in r["fark"]["yeni_planlanamayan"]:
        yp.setdefault(x["adres"], set()).add(x["kod"])
    for a in alan:
        assert a in yp, a
        assert yp[a] & {"takim_yok", "kesme_verisi_yok"}, (a, yp[a])
        assert a not in r["fark"]["kurtulan"]
    assert all(op.tool_id not in frezeler for op in yeni.ops)


@pytest.mark.occt
def test_ne_olurdu_geri_ac():
    """Kapatılan takım yeniden açılınca plan ilk planla `summary()` düzeyinde aynı; ilke göre fark yok."""
    g = o.girdi("plan_blogu")
    oturum = pk.PlanOturumu(g)
    J0 = o.jt(oturum.json())
    J1 = o.jt(oturum.ne_olurdu(takim_kapat=[1]))["plan"]
    r = o.jt(oturum.ne_olurdu(takim_ac=[1]))
    assert o.ozet_satirlari(r["plan"]) == o.ozet_satirlari(J0)
    assert r["plan"] == J0
    assert oturum.kapali == frozenset()
    _bos_fark(o.jt(pk.plan_farki(J0, r["plan"])))
    assert _sirasiz(r["fark"]) == _sirasiz(o.jt(pk.plan_farki(J1, J0)))


@pytest.mark.parametrize("ad", o.FREZE)
def test_ne_olurdu_rest_kapali(ad):
    """`secenek: {rest: false}` → `cep_kalan` işlemleri `cikan`'da."""
    g = o.girdi(ad)
    oturum = pk.PlanOturumu(g)
    J0 = o.jt(oturum.json())
    r = o.jt(oturum.ne_olurdu(secenek={"rest": False}))
    eski, yeni = o.planla(g), o.planla(g, secenekler={"rest": False})
    _ne_olurdu_ortak(oturum, J0, r, eski, yeni)
    kalan = [op.name for op in eski.ops if op.kind == "cep_kalan"]
    assert kalan, f"{ad}: kalan malzeme işlemi olmalı (SPEC 29 K2 / K3)"
    assert set(kalan) <= set(r["fark"]["cikan"])
    assert all(op.kind != "cep_kalan" for op in yeni.ops)
    assert r["plan"]["secenekler"]["rest"] is False


def test_ne_olurdu_matkap_engelli():
    """OCCT'siz: `plan_engelli`'de T11 (Ø8 matkap) kapanınca T11'in her işi ya başka takıma geçer ya çıkar."""
    g = o.girdi("plan_engelli")
    lib0 = g.lib.to_dict()
    oturum = pk.PlanOturumu(g)
    J0 = o.jt(oturum.json())
    r = o.jt(oturum.ne_olurdu(takim_kapat=[11]))
    eski, yeni = o.planla(g), o.planla(g, lib=o.suz(g.lib, {11}))
    _ne_olurdu_ortak(oturum, J0, r, eski, yeni)
    t11 = _ciftler(eski, 11)
    assert t11, "plan_engelli'de Ø8 delik T11 ile delinmeli (SPEC 29 K6)"
    y = _ciftler(yeni)
    adlar = {(op.feature, op.kind): op.name for op in eski.ops}
    for f, k in t11:
        if (f, k) in y:
            assert {"adres": f, "once": 11, "sonra": y[(f, k)]} in r["fark"]["takimi_degisen"]
        else:
            assert adlar[(f, k)] in r["fark"]["cikan"]
    assert g.lib.to_dict() == lib0


def test_ne_olurdu_hata_durumu_degistirmez():
    """Geçersiz seçenek / bilinmeyen takım → CamError; oturumun durumu (kapalı, seçenek, plan) değişmez."""
    g = o.girdi("plan_engelli")
    oturum = pk.PlanOturumu(g)
    oturum.ne_olurdu(takim_kapat=[2])
    once = (oturum.kapali, dict(oturum.secenekler), o.jt(oturum.json()))
    for kw in ({"secenek": {"n_max": 0}}, {"secenek": {"plunge_ratio": 0}}, {"takim_kapat": [999]}):
        with pytest.raises(CamError):
            oturum.ne_olurdu(**kw)
        assert (oturum.kapali, dict(oturum.secenekler), o.jt(oturum.json())) == once, kw


# ---------------------------------------------------------------- K5: doğrulama


def _dogrula_beklenen(g, plan):
    from cam.plan_verify import verify_mill, verify_turn

    if g.tur == "torna":
        return verify_turn(plan, cell=0.25)
    return verify_mill(plan, g.part, cell=0.5)


@pytest.mark.slow
@pytest.mark.occt
@pytest.mark.parametrize("ad", ["plan_blogu", "plan_mili"])
def test_dogrulama(ad):
    g = o.girdi(ad)
    oturum = pk.PlanOturumu(g)
    P = o.jt(oturum.dogrula())
    chk = _dogrula_beklenen(g, o.planla(g))
    d = P["dogrulama"]
    assert d is not None
    assert d["ok"] == chk.ok
    for alan in DOGRULAMA_SAYILARI:
        assert d[alan] == pytest.approx(getattr(chk, alan), rel=1e-12, abs=1e-12), alan
    assert len(d["collisions"]) == len(chk.collisions)
    assert d == o.jt(pk.dogrulama_sozlugu(chk))
    if ad == "plan_blogu":
        assert chk.ok
        assert o.kontrol(P["kontroller"], "dogrulama_cakma")["durum"] == "tamam"
        assert o.kontrol(P["kontroller"], "dogrulama_carpma")["durum"] == "tamam"
        o.kontrol(P["kontroller"], "kalan_malzeme")
    assert o.jt(oturum.dogrula()) == P  # ikinci çağrı önbellekten, aynı sonuç
    assert o.ozet_satirlari(P) == o.jt(o.planla(g).summary())


# ---------------------------------------------------------------- K21: doğrulama önbelleği (sayaçlı sahte)


@pytest.mark.occt
def test_dogrulama_onbellek(monkeypatch):
    """Aynı girdiyle ikinci `dogrula` `verify_mill`'i yeniden çağırmaz; girdi değişince yeniden hesaplar."""
    g = o.girdi("plan_blogu")
    import cam.plan_verify as pv

    sahte = _check()
    cagri: list[float] = []

    def say(plan, part, cell=0.5, machine=None):
        cagri.append(cell)
        return sahte

    monkeypatch.setattr(pv, "verify_mill", say)
    monkeypatch.setattr(pk, "verify_mill", say, raising=False)
    oturum = pk.PlanOturumu(g)
    P1 = o.jt(oturum.dogrula())
    P2 = o.jt(oturum.dogrula())
    assert cagri == [0.5]
    assert P1 == P2
    assert P1["dogrulama"] == o.jt(pk.dogrulama_sozlugu(sahte))
    oturum.ne_olurdu(takim_kapat=[1])
    oturum.dogrula()
    assert len(cagri) == 2
