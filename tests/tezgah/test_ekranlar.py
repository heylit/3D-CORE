"""
A3 — Tezgah ekran kaydı (specs/24a-ekran-kaydi.md §5, K1–K8).

Testler yalnız onaylı arayüz metnine dayanır. Keşif (`ekranlar()`) testleri `tezgah.ekranlar`
paketinin `__path__`'ini geçici bir klasöre çevirir ve oraya uydurma ekran modülleri yazar (metin:
"modülleri pkgutil ile bulur"); böylece gerçek ekranlar (freze, torna…) bu testlere karışmaz.
Sunucu testleri sahte `Ekran` listesini `uygulama(dist=None, ekranlar=[...])` ile verir.

K5 (sözleşme) paketteki gerçek modüller üzerinde parametrelidir: bölümü olan ekran yoksa test toplanmaz;
ekranlar taşındıkça kendiliğinden çalışır. K8 (geriye uyum) SPEC 24'ün `tests/tezgah/` testlerinin değişmeden
geçmesidir; burada yalnız sahte ekran listesiyle de SPEC 24 uçlarının aynı kaldığı sınanır.

Sunucu testleri `[web]` (fastapi + httpx) kurulu değilse atlanır.
"""

from __future__ import annotations

import copy
import dataclasses
import importlib
import json
import math
import pkgutil
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import APIRouter, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import tezgah.ekranlar as paket  # noqa: E402
from assy.model import AssyError  # noqa: E402
from cam.model import CamError  # noqa: E402
from core.model import ModelError  # noqa: E402
from geometry.part import GeometryError  # noqa: E402
from sketch.model import SketchError  # noqa: E402
from tests.tezgah import ornekler as o  # noqa: E402
from tezgah import SEMA  # noqa: E402
from tezgah.ekranlar import (  # noqa: E402
    KABUK_KISAYOLLARI,
    ONEK,
    Ekran,
    dogrula,
    ekranlar,
    is_kaydet,
    paylasilan_bolum,
)
from tezgah.isler import ORNEK_ISLER  # noqa: E402
from tezgah.kopru import is_json  # noqa: E402
from tezgah.sunucu import uygulama  # noqa: E402

ALANLAR = {"ad", "baslik", "sira", "tus", "hazir", "neden", "bolum", "bagimli"}


def _sim():
    return pytest.importorskip("cam.sim", reason="SPEC 05 (cam.sim) henüz yok")


def _istemci(liste: list[Ekran] | None) -> TestClient:
    return TestClient(uygulama(dist=None, ekranlar=liste))


def _json_tur(x):
    return json.loads(json.dumps(x, allow_nan=False))


def _belge(ad: str = "b") -> tuple[Callable, Callable]:
    """Bölüm sahibi için asgari disa_aktar / ice_aktar çifti."""
    durum = {"sema": 1, "ad": ad}

    def disa_aktar() -> dict:
        return copy.deepcopy(durum)

    def ice_aktar(belge: dict, onbellek) -> None:
        durum.clear()
        durum.update(copy.deepcopy(belge))

    return disa_aktar, ice_aktar


def _sahip(ad: str, bolum: str, **kw) -> Ekran:
    d, i = _belge(ad)
    return Ekran(ad=ad, baslik=ad.title(), bolum=bolum, disa_aktar=d, ice_aktar=i, **kw)


# ---------------------------------------------------------------- uydurma ekran paketi (keşif)


@pytest.fixture
def sahte_paket(tmp_path, monkeypatch):
    """`tezgah.ekranlar` keşfini geçici bir klasöre yöneltir; testin import ettiği modüller sonra silinir."""
    kok = tmp_path / "sahte_ekranlar"
    kok.mkdir()
    monkeypatch.setattr(paket, "__path__", [str(kok)])
    # Önceden import edilmiş gerçek ekranlar (ör. başka testin topladığı analiz) sahtelerin yerine geçmesin;
    # monkeypatch teardown'da onları geri koyar.
    for k in [k for k in sys.modules if k.startswith(f"{paket.__name__}.")]:
        monkeypatch.delitem(sys.modules, k)
    onceki = set(sys.modules)
    importlib.invalidate_caches()
    yield kok
    for k in list(sys.modules):
        if k.startswith("tezgah.ekranlar.") and k not in onceki:
            del sys.modules[k]
    importlib.invalidate_caches()


def _modul(kok: Path, ad: str, govde: str) -> None:
    (kok / f"{ad}.py").write_text(textwrap.dedent(govde), encoding="utf-8")
    importlib.invalidate_caches()


def _basit_modul(kok: Path, ad: str, sira: int = 100, tus: str | None = None) -> None:
    _modul(
        kok,
        ad,
        f"""
        from tezgah.ekranlar import Ekran
        EKRAN = Ekran(ad={ad!r}, baslik={ad.title()!r}, sira={sira!r}, tus={tus!r})
        """,
    )


def _import(ad: str):
    return importlib.import_module(f"{paket.__name__}.{ad}")


# ---------------------------------------------------------------- K1: keşif ve sıralama


def test_discovers_modules_and_sorts_by_order_then_name(sahte_paket):
    """K1: her modülün `EKRAN`'ı bulunur; sıra `sira`, eşitse `ad`."""
    _basit_modul(sahte_paket, "torna", sira=20, tus="2")
    _basit_modul(sahte_paket, "freze", sira=10, tus="1")
    _basit_modul(sahte_paket, "montaj", sira=20, tus="3")
    _basit_modul(sahte_paket, "analiz", sira=60)
    E = ekranlar()
    assert [e.ad for e in E] == ["freze", "montaj", "torna", "analiz"]
    assert all(isinstance(e, Ekran) for e in E)
    assert {e.ad: e.tus for e in E} == {"freze": "1", "montaj": "3", "torna": "2", "analiz": None}


def test_discovered_object_is_the_modules_EKRAN(sahte_paket):
    _basit_modul(sahte_paket, "freze", sira=1)
    (e,) = ekranlar()
    assert e is _import("freze").EKRAN


def test_import_error_gives_closed_placeholder_and_others_work(sahte_paket):
    """K1: importu hata veren modül kabuğu çökertmez; modül adıyla, `hazir` hata metnini dönen yer tutucu."""
    _basit_modul(sahte_paket, "freze", sira=10, tus="1")
    _modul(sahte_paket, "bozuk", 'raise RuntimeError("bozuk modül: gmsh yok")\n')
    E = {e.ad: e for e in ekranlar()}
    assert set(E) == {"freze", "bozuk"}
    assert E["freze"].hazir is None or E["freze"].hazir() is None
    assert E["bozuk"].hazir is not None
    neden = E["bozuk"].hazir()
    assert isinstance(neden, str) and "bozuk modül: gmsh yok" in neden


def test_module_without_EKRAN_is_skipped(sahte_paket):
    """Sorunsuz import edilen ama `EKRAN` tanımlamayan modül sessizce atlanır (A3 sahibinin kuralı, 11:45)."""
    _basit_modul(sahte_paket, "freze", sira=10, tus="1")
    _modul(sahte_paket, "yardimci", "SABIT = 3\n\ndef f():\n    return SABIT\n")
    assert [e.ad for e in ekranlar()] == ["freze"]


def test_underscore_module_is_never_imported(sahte_paket):
    """`_` ile başlayan modül hiç import edilmez; import hatası verse bile yer tutucu üretilmez."""
    _basit_modul(sahte_paket, "freze", sira=10, tus="1")
    _modul(sahte_paket, "_ortak", 'raise RuntimeError("import edilmemeliydi")\n')
    _modul(
        sahte_paket,
        "_gizli",
        """
        from tezgah.ekranlar import Ekran
        EKRAN = Ekran(ad="gizli", baslik="Gizli")
        """,
    )
    assert [e.ad for e in ekranlar()] == ["freze"]
    assert f"{paket.__name__}._ortak" not in sys.modules
    assert f"{paket.__name__}._gizli" not in sys.modules


def test_import_error_placeholder_listed_by_server(sahte_paket):
    """K1 + K2: yer tutucu `/api/ekranlar`'da kapalı sekme (hazir false, neden = hata metni); diğerleri hazır.

    Yer tutucunun uçsuz ve tuşsuz olması onu sekme listesinden düşürmez (§1: "sekme kapalı, ipucu hata").
    """
    _basit_modul(sahte_paket, "freze", sira=10, tus="1")
    _modul(sahte_paket, "bozuk", 'raise ImportError("eksik paket: gmsh")\n')
    r = TestClient(uygulama(dist=None)).get("/api/ekranlar")
    assert r.status_code == 200
    L = {e["ad"]: e for e in r.json()["ekranlar"]}
    assert L["freze"]["hazir"] is True and L["freze"]["neden"] is None
    assert L["bozuk"]["hazir"] is False
    assert "eksik paket: gmsh" in L["bozuk"]["neden"]


def test_discovery_validation_error_is_model_error(sahte_paket):
    """K1: kayıt hatası keşifte de ModelError (import hatasından ayrı: yer tutucu değil)."""
    _basit_modul(sahte_paket, "freze", tus="1")
    _basit_modul(sahte_paket, "torna", tus="1")
    with pytest.raises(ModelError):
        ekranlar()


def test_app_build_with_invalid_discovery_raises(sahte_paket):
    """K1: uygulama kurulurken (ekranlar=None → keşif) kayıt hatası ModelError; sessiz geçilmez."""
    _modul(
        sahte_paket,
        "freze",
        """
        from tezgah.ekranlar import Ekran
        EKRAN = Ekran(ad="Freze", baslik="Freze")
        """,
    )
    with pytest.raises(ModelError):
        ekranlar()
    with pytest.raises(ModelError):
        uygulama(dist=None)


# ---------------------------------------------------------------- K1: doğrulama (her durum ayrı)


def test_valid_list_is_returned_sorted():
    A = Ekran(ad="b_ekran", baslik="B", sira=5, tus="2")
    B = Ekran(ad="a_ekran", baslik="A", sira=5)
    C = Ekran(ad="c1", baslik="C", sira=1, tus="1")
    D = _sahip("model", "model")
    M = Ekran(ad="montaj", baslik="Montaj", bolum="montajlar", bagimli=("model",), **_kw_belge())
    assert dogrula([A, B, C, D, M]) == [C, B, A, D, M]


def _kw_belge() -> dict:
    d, i = _belge()
    return {"disa_aktar": d, "ice_aktar": i}


@pytest.mark.parametrize("ad", ["Freze", "", "1freze", "cok-eksen", "çok_eksen", "a b", "freze/x"])
def test_invalid_name(ad):
    with pytest.raises(ModelError):
        dogrula([Ekran(ad=ad, baslik="X")])


@pytest.mark.parametrize("ad", ["freze", "cok_eksen", "a1", "x"])
def test_valid_names_accepted(ad):
    assert [e.ad for e in dogrula([Ekran(ad=ad, baslik="X")])] == [ad]


def test_duplicate_name():
    with pytest.raises(ModelError):
        dogrula([Ekran(ad="freze", baslik="A", sira=1), Ekran(ad="freze", baslik="B", sira=2)])


def test_duplicate_key():
    with pytest.raises(ModelError):
        dogrula([Ekran(ad="freze", baslik="F", tus="1"), Ekran(ad="torna", baslik="T", tus="1")])


def test_none_keys_are_not_duplicates():
    assert len(dogrula([Ekran(ad="a", baslik="A"), Ekran(ad="b", baslik="B")])) == 2


@pytest.mark.parametrize("tus", list(KABUK_KISAYOLLARI))
def test_shell_key(tus):
    with pytest.raises(ModelError):
        dogrula([Ekran(ad="freze", baslik="F", tus=tus)])


def test_shell_shortcut_list_matches_spec():
    """§3: kabuğun kısayolları."""
    assert set(KABUK_KISAYOLLARI) == {
        "Ctrl+K",
        "Ctrl+Z",
        "Ctrl+Shift+Z",
        "Ctrl+Y",
        "Ctrl+S",
        "Ctrl+Shift+S",
        "Ctrl+O",
    }
    assert ONEK == "/api/ekran"


def test_section_with_two_owners():
    with pytest.raises(ModelError):
        dogrula([_sahip("freze", "isler"), _sahip("plan", "isler")])


def test_dependency_on_unowned_section():
    with pytest.raises(ModelError):
        dogrula([_sahip("freze", "isler"), Ekran(ad="montaj", baslik="M", bagimli=("torna_isleri",))])


def test_dependency_on_owned_section_ok():
    E = dogrula([_sahip("freze", "isler"), Ekran(ad="analiz", baslik="A", bagimli=("isler",))])
    assert {e.ad for e in E} == {"freze", "analiz"}


@pytest.mark.parametrize(
    "bolumler",
    [
        [("a", "bol_a", ("bol_b",)), ("b", "bol_b", ("bol_a",))],
        [("a", "bol_a", ("bol_b",)), ("b", "bol_b", ("bol_c",)), ("c", "bol_c", ("bol_a",))],
        [("a", "bol_a", ("bol_a",))],
    ],
    ids=["iki", "uc", "kendine"],
)
def test_dependency_cycle(bolumler):
    liste = [_sahip(ad, bolum, bagimli=bagimli) for ad, bolum, bagimli in bolumler]
    with pytest.raises(ModelError):
        dogrula(liste)


def test_acyclic_chain_ok():
    liste = [
        _sahip("a", "bol_a"),
        _sahip("b", "bol_b", bagimli=("bol_a",)),
        _sahip("c", "bol_c", bagimli=("bol_a", "bol_b")),
    ]
    assert len(dogrula(liste)) == 3


@pytest.mark.parametrize("eksik", ["disa_aktar", "ice_aktar"])
def test_section_owner_missing_import_export(eksik):
    e = dataclasses.replace(_sahip("freze", "isler"), **{eksik: None})
    with pytest.raises(ModelError):
        dogrula([e])


def test_app_build_with_invalid_list_raises():
    """`uygulama(ekranlar=...)` verilen listeyi de doğrular (uygulama kurulurken ModelError)."""
    with pytest.raises(ModelError):
        uygulama(dist=None, ekranlar=[Ekran(ad="a", baslik="A", tus="1"), Ekran(ad="b", baslik="B", tus="1")])


# ---------------------------------------------------------------- K2: /api/ekranlar


def test_screen_list_sorted_with_full_fields():
    liste = [
        Ekran(ad="torna", baslik="Torna", sira=20, tus="2"),
        _sahip("freze", "isler", sira=10, tus="1"),
        Ekran(
            ad="montaj",
            baslik="Montaj",
            sira=20,
            tus="3",
            bolum="montajlar",
            bagimli=("isler",),
            **_kw_belge(),
        ),
        Ekran(ad="analiz", baslik="Analiz", router=APIRouter(), hazir=lambda: "gmsh kurulu değil"),
    ]
    r = _istemci(liste).get("/api/ekranlar")
    assert r.status_code == 200
    J = r.json()
    assert set(J) == {"ekranlar"}
    for e in J["ekranlar"]:
        assert set(e) == ALANLAR
    assert J["ekranlar"] == [
        {
            "ad": "freze",
            "baslik": "Freze",
            "sira": 10,
            "tus": "1",
            "hazir": True,
            "neden": None,
            "bolum": "isler",
            "bagimli": [],
        },
        {
            "ad": "montaj",
            "baslik": "Montaj",
            "sira": 20,
            "tus": "3",
            "hazir": True,
            "neden": None,
            "bolum": "montajlar",
            "bagimli": ["isler"],
        },
        {
            "ad": "torna",
            "baslik": "Torna",
            "sira": 20,
            "tus": "2",
            "hazir": True,
            "neden": None,
            "bolum": None,
            "bagimli": [],
        },
        {
            "ad": "analiz",
            "baslik": "Analiz",
            "sira": 100,
            "tus": None,
            "hazir": False,
            "neden": "gmsh kurulu değil",
            "bolum": None,
            "bagimli": [],
        },
    ]


def test_ready_callable_returning_none_is_ready():
    r = _istemci([Ekran(ad="freze", baslik="Freze", tus="1", hazir=lambda: None)]).get("/api/ekranlar")
    assert r.json()["ekranlar"][0]["hazir"] is True
    assert r.json()["ekranlar"][0]["neden"] is None


def test_shell_screen_without_router_and_key_is_not_a_tab():
    """`router=None` ve `tus=None` ekran sekme değildir (A3 sahibinin kararı, koordinatör notu 11:33):
    kayıtta ve doğrulamada vardır, GET /api/ekranlar (sekme listesi) onu listelemez. Tuşlu ya da uçlu ekran
    listelenir."""
    kabuk = Ekran(ad="kabuk", baslik="Kabuk", sira=0, kur=lambda app: None)
    model = _sahip("model", "model", sira=70)  # uçsuz, tuşsuz bölüm sahibi
    freze = Ekran(ad="freze", baslik="Freze", sira=10, tus="1")
    plan = Ekran(ad="plan", baslik="Plan", sira=40, router=_yonlendirici("plan"))
    liste = [plan, model, freze, kabuk]
    assert [e.ad for e in dogrula(liste)] == ["kabuk", "freze", "plan", "model"]
    r = _istemci(liste).get("/api/ekranlar")
    assert [e["ad"] for e in r.json()["ekranlar"]] == ["freze", "plan"]


def test_shell_screen_still_discovered(sahte_paket):
    """Sekme olmayan ekran `ekranlar()`'da yine vardır (bölüm, bağımlılık ve paylasilan_bolum için)."""
    _basit_modul(sahte_paket, "freze", sira=10, tus="1")
    _basit_modul(sahte_paket, "kabuk", sira=0)
    assert [e.ad for e in ekranlar()] == ["kabuk", "freze"]
    r = TestClient(uygulama(dist=None)).get("/api/ekranlar")
    assert [e["ad"] for e in r.json()["ekranlar"]] == ["freze"]


def test_empty_screen_list():
    r = _istemci([]).get("/api/ekranlar")
    assert r.status_code == 200
    assert r.json() == {"ekranlar": []}


def test_default_discovery_used_when_list_none(sahte_paket):
    """`ekranlar=None` → `tezgah.ekranlar.ekranlar()`."""
    _basit_modul(sahte_paket, "torna", sira=2, tus="2")
    _basit_modul(sahte_paket, "freze", sira=1, tus="1")
    r = TestClient(uygulama(dist=None)).get("/api/ekranlar")
    assert [e["ad"] for e in r.json()["ekranlar"]] == ["freze", "torna"]


# ---------------------------------------------------------------- K3: yalıtım, 503, kur


def _yonlendirici(cevap: str) -> APIRouter:
    r = APIRouter()

    @r.get("/x")
    def x() -> dict:
        return {"kim": cevap}

    @r.post("/x")
    def x_yaz(govde: dict) -> dict:
        return {"kim": cevap, "govde": govde}

    return r


def test_same_path_isolated_under_screen_prefix():
    """K3: iki ekranın `/x`'i `/api/ekran/<ad>/x` altında ayrı yanıt verir."""
    istemci = _istemci(
        [
            Ekran(ad="alfa", baslik="Alfa", router=_yonlendirici("alfa")),
            Ekran(ad="beta", baslik="Beta", router=_yonlendirici("beta")),
        ]
    )
    assert istemci.get(f"{ONEK}/alfa/x").json() == {"kim": "alfa"}
    assert istemci.get(f"{ONEK}/beta/x").json() == {"kim": "beta"}
    assert istemci.post(f"{ONEK}/beta/x", json={"a": 1}).json() == {"kim": "beta", "govde": {"a": 1}}
    # Öneksiz bağlanmaz.
    assert istemci.get("/x").status_code == 404
    assert istemci.get(f"{ONEK}/gama/x").status_code == 404


def test_unavailable_screen_endpoints_503_with_reason():
    """K3: kullanılamaz ekranın ucu 503, `detail` = neden; diğer ekran etkilenmez."""
    istemci = _istemci(
        [
            Ekran(ad="alfa", baslik="Alfa", router=_yonlendirici("alfa")),
            Ekran(
                ad="analiz",
                baslik="Analiz",
                router=_yonlendirici("analiz"),
                hazir=lambda: "gmsh kurulu değil",
            ),
        ]
    )
    r = istemci.get(f"{ONEK}/analiz/x")
    assert r.status_code == 503
    assert r.json()["detail"] == "gmsh kurulu değil"
    r = istemci.post(f"{ONEK}/analiz/x", json={})
    assert r.status_code == 503
    assert r.json()["detail"] == "gmsh kurulu değil"
    assert istemci.get(f"{ONEK}/alfa/x").json() == {"kim": "alfa"}


def test_setup_hook_called_once_with_app():
    """`kur` uygulama kurulurken bir kez, FastAPI uygulamasıyla çağrılır."""
    cagrilar: list = []
    app = uygulama(dist=None, ekranlar=[Ekran(ad="kabuk", baslik="Kabuk", kur=cagrilar.append)])
    assert len(cagrilar) == 1
    assert cagrilar[0] is app
    assert isinstance(cagrilar[0], FastAPI)
    TestClient(app).get("/api/ekranlar")
    assert len(cagrilar) == 1


# ---------------------------------------------------------------- K4: hata eşlemesi


HATALAR = {
    "key": KeyError("bilinmeyen eleman: 7"),
    "cam": CamError("takım çapı sıfır"),
    "model": ModelError("tekil matris"),
    "assy": AssyError("kısıt çelişkili"),
    "geometry": GeometryError("sıfır hacim"),
    "sketch": SketchError("kroki aşırı kısıtlı"),
}


def _hatali_ekran(ad: str) -> Ekran:
    r = APIRouter()

    @r.get("/hata/{tur}")
    def hata(tur: str) -> dict:
        raise HATALAR[tur]

    @r.post("/hata/{tur}")
    def hata_yaz(tur: str) -> dict:
        raise HATALAR[tur]

    return Ekran(ad=ad, baslik=ad.title(), router=r)


@pytest.mark.parametrize("tur", list(HATALAR))
@pytest.mark.parametrize("yontem", ["get", "post"])
def test_core_errors_map_to_422_for_screen_endpoints(tur, yontem):
    """K4: her çekirdek hata türü → 422, `detail=str(e)`; ekrandan bağımsız (iki ekran aynı sonucu verir)."""
    istemci = _istemci([_hatali_ekran("alfa"), _hatali_ekran("beta")])
    for ad in ("alfa", "beta"):
        r = getattr(istemci, yontem)(f"{ONEK}/{ad}/hata/{tur}")
        assert r.status_code == 422
        assert r.json()["detail"] == str(HATALAR[tur])


# ---------------------------------------------------------------- K6: paylasilan_bolum


SAHIP_MODUL = """
from tezgah.ekranlar import Ekran

DURUM = {"sema": 1, "isler": [{"ad": "kapak", "D": 10.0}]}


def disa_aktar():
    return DURUM  # bilerek kopya değil: kopyalamak paylasilan_bolum'un işi


def ice_aktar(belge, onbellek):
    DURUM.clear()
    DURUM.update(belge)


EKRAN = Ekran(
    ad="sahip", baslik="Sahip", sira=1, bolum="deneme_bolum", disa_aktar=disa_aktar, ice_aktar=ice_aktar
)
"""

OKUYAN_MODUL = """
from tezgah.ekranlar import Ekran

EKRAN = Ekran(ad="okuyan", baslik="Okuyan", sira=2, bagimli=("deneme_bolum",))
"""


def _bolum_kur(kok: Path):
    """Sahip + bağımlı ekran; hem keşifle hem de aynı nesnelerle kurulmuş uygulamayla görünür."""
    _modul(kok, "sahip", SAHIP_MODUL)
    _modul(kok, "okuyan", OKUYAN_MODUL)
    sahip, okuyan = _import("sahip"), _import("okuyan")
    TestClient(uygulama(dist=None, ekranlar=[sahip.EKRAN, okuyan.EKRAN]))
    return sahip


def test_shared_section_is_owners_current_document(sahte_paket):
    sahip = _bolum_kur(sahte_paket)
    assert paylasilan_bolum("deneme_bolum") == {"sema": 1, "isler": [{"ad": "kapak", "D": 10.0}]}
    sahip.DURUM["isler"].append({"ad": "flans", "D": 8.0})
    assert paylasilan_bolum("deneme_bolum") == {
        "sema": 1,
        "isler": [{"ad": "kapak", "D": 10.0}, {"ad": "flans", "D": 8.0}],
    }


def test_shared_section_is_a_deep_copy(sahte_paket):
    """K6: dönen kopyayı değiştirmek sahibi değiştirmez (iç içe alanlar dahil)."""
    sahip = _bolum_kur(sahte_paket)
    B = paylasilan_bolum("deneme_bolum")
    B["isler"][0]["D"] = 99.0
    B["isler"].append({"ad": "yabanci"})
    B["sema"] = 7
    assert sahip.DURUM == {"sema": 1, "isler": [{"ad": "kapak", "D": 10.0}]}
    assert paylasilan_bolum("deneme_bolum") == {"sema": 1, "isler": [{"ad": "kapak", "D": 10.0}]}


def test_unowned_section_key_error(sahte_paket):
    _bolum_kur(sahte_paket)
    with pytest.raises(KeyError):
        paylasilan_bolum("olmayan_bolum")


# ---------------------------------------------------------------- K7: is_kaydet


DINAMIK = "a3-dinamik"


@pytest.fixture
def depo():
    """Gerçek iş deposuna istemci kuran fonksiyon; test sonunda POST /api/sifirla ile temizlenir."""
    yield lambda: _istemci([])
    try:
        _istemci([]).post("/api/sifirla")
    except NotImplementedError:
        pass


def _is_listesi(istemci: TestClient) -> list[str]:
    r = istemci.get("/api/isler")
    assert r.status_code == 200
    return r.json()["isler"]


def test_registered_job_appears_in_list_and_endpoint(depo):
    """K7: iş /api/isler'de görünür, /api/is/<ad> SPEC 24 biçiminde (kopru.is_json) döner."""
    istemci = depo()
    _sim()
    tanim = dataclasses.replace(o.kucuk_is(), ad=DINAMIK)
    is_kaydet(DINAMIK, tanim)
    L = _is_listesi(istemci)
    assert DINAMIK in L
    assert set(ORNEK_ISLER) <= set(L)
    r = istemci.get(f"/api/is/{DINAMIK}")
    assert r.status_code == 200
    assert r.json() == _json_tur(is_json(tanim))
    assert r.json()["sema"] == SEMA
    assert istemci.get(f"/api/is/{DINAMIK}/noktalar").status_code == 200


def test_same_name_replaces(depo):
    istemci = depo()
    _sim()
    t1 = dataclasses.replace(o.kucuk_is(), ad=DINAMIK)
    t2 = dataclasses.replace(o.kucuk_is(kanal_z=17.0), ad=DINAMIK)
    is_kaydet(DINAMIK, t1)
    is_kaydet(DINAMIK, t2)
    assert _is_listesi(istemci).count(DINAMIK) == 1
    assert istemci.get(f"/api/is/{DINAMIK}").json() == _json_tur(is_json(t2))


@pytest.mark.parametrize(
    "bozuk",
    [
        lambda: dataclasses.replace(o.kucuk_is(), ad=DINAMIK, islemler=[]),
        lambda: "bir iş tanımı değil",
    ],
    ids=["islem-yok", "tur-yanlis"],
)
def test_invalid_definition_cam_error_and_store_unchanged(depo, bozuk):
    """K7: geçersiz tanım → CamError; depo değişmez (yeni ad eklenmez, aynı adlı eski iş yerinde kalır)."""
    istemci = depo()
    _sim()
    once = _is_listesi(istemci)
    with pytest.raises(CamError):
        is_kaydet("a3-gecersiz", bozuk())
    assert _is_listesi(istemci) == once
    assert istemci.get("/api/is/a3-gecersiz").status_code == 404

    gecerli = dataclasses.replace(o.kucuk_is(), ad=DINAMIK)
    is_kaydet(DINAMIK, gecerli)
    J = istemci.get(f"/api/is/{DINAMIK}").json()
    with pytest.raises(CamError):
        is_kaydet(DINAMIK, bozuk())
    assert istemci.get(f"/api/is/{DINAMIK}").json() == J


def test_reset_removes_dynamic_jobs(depo):
    """K7: POST /api/sifirla dinamik işleri siler; ekranların sabit örnek işleri kalır.

    Karşılaştırma uygulama açılırkenki listeyle yapılır (ör. SPEC 25 tornası kendi örneğini ekler).
    """
    istemci = depo()
    baslangic = _is_listesi(istemci)
    assert set(ORNEK_ISLER) <= set(baslangic)
    is_kaydet(DINAMIK, dataclasses.replace(o.kucuk_is(), ad=DINAMIK))
    assert DINAMIK in _is_listesi(istemci)
    assert istemci.post("/api/sifirla").status_code == 200
    assert _is_listesi(istemci) == baslangic
    assert istemci.get(f"/api/is/{DINAMIK}").status_code == 404


# ---------------------------------------------------------------- /api/sifirla


def test_reset_calls_every_screen_reset_once():
    sayac = {"a": 0, "b": 0}
    liste = [
        Ekran(ad="a", baslik="A", sifirla=lambda: sayac.__setitem__("a", sayac["a"] + 1)),
        Ekran(ad="b", baslik="B", sifirla=lambda: sayac.__setitem__("b", sayac["b"] + 1)),
        Ekran(ad="c", baslik="C"),
    ]
    istemci = _istemci(liste)
    assert sayac == {"a": 0, "b": 0}
    assert istemci.post("/api/sifirla").status_code == 200
    assert sayac == {"a": 1, "b": 1}


def test_reset_restores_default_job_parameters():
    """POST /api/sifirla iş deposunu varsayılana döndürür: parametre değişikliği geri alınır."""
    _sim()
    istemci = _istemci([])
    ad = ORNEK_ISLER[0]
    J0 = istemci.get(f"/api/is/{ad}").json()
    D0 = J0["islemler"][2]["parametreler"]["D"]
    D1 = 8.0 if D0 != 8.0 else 6.0
    assert (
        istemci.post(f"/api/is/{ad}/parametre", json={"islem": 2, "anahtar": "D", "deger": D1}).status_code
        == 200
    )
    assert istemci.post("/api/sifirla").status_code == 200
    assert istemci.get(f"/api/is/{ad}").json()["islemler"][2]["parametreler"]["D"] == D0


# ---------------------------------------------------------------- K8: SPEC 24 uçları sahte listeyle de aynı


def test_spec24_endpoints_unchanged_with_screen_list():
    istemci = _istemci([Ekran(ad="alfa", baslik="Alfa", router=_yonlendirici("alfa"))])
    J = istemci.get("/api/isler").json()
    assert set(J) == {"sema", "isler"} and J["sema"] == SEMA
    # Örnek freze işleri başta; gerçek ekranların sabit işleri (ör. torna) arkadan gelebilir.
    assert J["isler"][: len(ORNEK_ISLER)] == list(ORNEK_ISLER)
    assert istemci.get("/api/is/olmayan-is").status_code == 404
    r = istemci.post(f"/api/is/{ORNEK_ISLER[0]}/parametre", json={"islem": 99, "anahtar": "D", "deger": 8.0})
    assert r.status_code == 422


# ---------------------------------------------------------------- K5: gerçek ekranların sözleşmesi


def _gercek_moduller() -> list[str]:
    """Paketteki gerçek modül adları (dosya sistemi; `ekranlar()` çağrılmadan, toplama aşamasında)."""
    return sorted(m.name for m in pkgutil.iter_modules(paket.__path__) if not m.name.startswith("_"))


def _gercek_ekran(modul: str) -> Ekran:
    e = getattr(_import(modul), "EKRAN", None)
    if e is None:
        pytest.skip(f"{modul}: EKRAN yok (ekran modülü değil)")
    if e.bolum is None:
        pytest.skip(f"{modul}: bölümü yok (K5 yalnız bölümü olan ekranlar için)")
    if e.hazir is not None and e.hazir() is not None:
        pytest.skip(f"{modul}: kullanılamaz ({e.hazir()})")
    if e.sifirla is not None:
        e.sifirla()
    return e


def _sonlu_ozet(z: dict) -> None:
    assert isinstance(z, dict)
    for k, v in z.items():
        assert isinstance(k, str)
        assert isinstance(v, (str, int, float)) and not isinstance(v, bool), (k, v)
        if not isinstance(v, str):
            assert math.isfinite(v), (k, v)


@pytest.fixture(params=_gercek_moduller())
def gercek(request):
    e = _gercek_ekran(request.param)
    yield e
    if e.sifirla is not None:
        e.sifirla()


def test_contract_export_json_with_schema(gercek):
    """K5: `disa_aktar()` JSON'a döner (nan/inf yok), `sema` alanı var."""
    B = gercek.disa_aktar()
    assert isinstance(B, dict)
    assert "sema" in B
    assert json.loads(json.dumps(B, allow_nan=False)) == B


def test_contract_roundtrip_changes_nothing(gercek):
    """K5: `ice_aktar(disa_aktar(), {})` sonrası `disa_aktar()` ve `ozet()` aynı."""
    B = copy.deepcopy(gercek.disa_aktar())
    z = gercek.ozet() if gercek.ozet is not None else None
    gercek.ice_aktar(copy.deepcopy(B), {})
    assert gercek.disa_aktar() == B
    if gercek.ozet is not None:
        assert gercek.ozet() == z


def test_contract_roundtrip_with_cache(gercek):
    """K5: önbellekle yükleme de aynı durumu verir."""
    if gercek.onbellek is None:
        pytest.skip("önbellek yok")
    B = copy.deepcopy(gercek.disa_aktar())
    on = gercek.onbellek()
    assert isinstance(on, dict)
    assert all(isinstance(k, str) and isinstance(v, bytes) for k, v in on.items())
    gercek.ice_aktar(copy.deepcopy(B), on)
    assert gercek.disa_aktar() == B


@pytest.mark.parametrize("bozuk", [{}, {"sema": None}], ids=["bos", "sema-yok"])
def test_contract_import_atomic_on_broken_document(gercek, bozuk):
    """K5: bozuk belgeyle `ice_aktar` hata verir; sonrasında `disa_aktar()` öncekiyle aynı (atomiklik)."""
    B = copy.deepcopy(gercek.disa_aktar())
    with pytest.raises((ValueError, KeyError, TypeError)):
        gercek.ice_aktar(bozuk, {})
    assert gercek.disa_aktar() == B


def test_contract_summary_finite(gercek):
    """K5: `ozet()` değerleri sonlu sayı ya da metin."""
    if gercek.ozet is None:
        pytest.skip("özet yok")
    _sonlu_ozet(gercek.ozet())


def test_real_package_screens_validate():
    """Paketteki gerçek ekranlar (taşındıkça) kayıt doğrulamasından geçer."""
    E = ekranlar()
    assert dogrula(E) == E
