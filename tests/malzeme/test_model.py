"""SPEC B2 — malzeme/model.py testleri: malzeme kaydı, tutarlılık kuralları ve köprüler (K1–K7, K9).

Testler sadece specs/B2-malzeme-arayuz.md'deki teori, arayüz ve Kararlar bölümünden yazıldı; malzeme/model.py
gövdesi okunmadı. Birimler N – mm – MPa – s – t (SPEC tablosu); kodda dönüşüm yok.
- Kayma modülü G = E / (2(1 + ν)).
- Taylor takım ömrü Vc · T^n = C  →  T = (C / Vc)^(1/n).
- "ModelError" her yerde malzeme.model.ModelError(ValueError)'dır (Kararlar).
- taylor / kesme salt okunur sözlüktür; eksik anahtar hem ModelError hem KeyError fırlatır (Kararlar).

İskelet NotImplementedError fırlattığı sürece testler "uygulanmamış" sayılır.
"""

from __future__ import annotations

import dataclasses
import json
import math
import pathlib
import subprocess
import sys

import pytest

from malzeme.model import (
    GRUPLAR,
    TAKIM_MALZEMELERI,
    KesmeOnerisi,
    Malzeme,
    ModelError,
    Taylor,
)

KOK = pathlib.Path(__file__).resolve().parents[2]


def celik(**degisen) -> Malzeme:
    """SPEC tablosundaki çelik örneği; tüm alanlar dolu. degisen ile tek alan değiştirilir."""
    alanlar = dict(
        id="1.0503",
        name="C45",
        standart="EN 10083-2",
        grup="celik",
        kaynak="EN 10083-2:2006, Tablo 7 (test için tipik değerler)",
        iso513="P",
        tipik=True,
        kullanici=False,
        E=210000.0,
        nu=0.30,
        rho=7.85e-9,
        Rp02=355.0,
        Rm=600.0,
        A=16.0,
        sertlik="HB 210",
        sigma_f=270.0,
        k=50.0,
        cp=4.6e8,
        alpha=1.2e-5,
        kc11=1700.0,
        mc=0.25,
        taylor={"karbur": Taylor(C=300.0, n=0.25), "HSS": Taylor(C=40.0, n=0.125)},
        kesme={"karbur": KesmeOnerisi(Vc=200.0, fz=0.1), "HSS": KesmeOnerisi(Vc=30.0, fn=0.2)},
        fiyat=1.2,
    )
    alanlar.update(degisen)
    return Malzeme(**alanlar)


def yari_bos() -> Malzeme:
    """Yalnız zorunlu metinler ve E, ν, ρ (POM benzeri: talaş ve ısıl veri yok)."""
    return Malzeme(
        id="POM-C",
        name="POM-C",
        standart="",
        grup="plastik",
        kaynak="Üretici kataloğu, tipik aralık ortası (test kaydı)",
        E=2800.0,
        nu=0.35,
        rho=1.41e-9,
    )


# ---------------------------------------------------------------- sabitler


def test_sabit_kumeler():
    assert TAKIM_MALZEMELERI == ("HSS", "karbur", "kaplamali_karbur", "sermet", "seramik", "CBN", "PCD")
    assert GRUPLAR == (
        "celik",
        "paslanmaz",
        "dokme_demir",
        "aluminyum",
        "bakir",
        "titanyum",
        "nikel",
        "plastik",
        "diger",
    )


def test_model_error_value_error():
    assert issubclass(ModelError, ValueError)


# ---------------------------------------------------------------- K1 birimler ve köprü


def test_k1_celik_kurulur_ve_G():
    m = celik()
    # G = 210000 / (2 · 1.3) = 80769.2307692...
    assert m.G == pytest.approx(210000.0 / 2.6, rel=1e-12)
    assert m.G == pytest.approx(80769.23076923077, rel=1e-12)


def test_k1_fem_malzemesi():
    from core.model import Material

    f = celik().fem_malzemesi()
    assert isinstance(f, Material)
    assert f.name == "1.0503"  # ad = id: ağda Element.material == Malzeme.id
    assert f.E == 210000.0
    assert f.nu == 0.3
    assert f.rho == 7.85e-9


def test_k1_fem_malzemesi_rho_yoksa_sifir():
    f = celik(rho=None).fem_malzemesi()
    assert f.rho == 0.0


@pytest.mark.parametrize("alan", ["E", "nu"])
def test_k1_fem_malzemesi_E_nu_zorunlu(alan):
    m = celik(**{alan: None})
    with pytest.raises(ModelError):
        m.fem_malzemesi()


def test_k1_kup_kutlesi():
    """10 mm küp: V = 1000 mm³, m = ρ V = 7.85e-6 t = 7.85 g."""
    m = celik()
    assert m.iste("rho") * 10.0**3 == pytest.approx(7.85e-6, rel=1e-12)


def test_k1_iste_dolu_alan():
    m = celik()
    assert m.iste("E") == 210000.0
    assert m.iste("k") == 50.0
    assert m.iste("alpha") == 1.2e-5


# ---------------------------------------------------------------- K2 tutarlılık reddi


@pytest.mark.parametrize(
    "degisen",
    [
        {"nu": 0.5},
        {"nu": 0.0},
        {"nu": -0.1},
        {"E": 0.0},
        {"E": -1.0},
        {"Rp02": 400.0, "Rm": 350.0},
        {"sigma_f": 600.0},  # = Rm
        {"sigma_f": 700.0},  # > Rm
        {"rho": -1.0},
        {"rho": 0.0},
        {"k": math.nan},
        {"E": math.inf},
        {"cp": -math.inf},
        {"Rp02": 0.0},
        {"Rm": -5.0},
        {"kc11": 0.0},
        {"fiyat": -1.2},
        {"alpha": -1e-6},
        {"mc": 1.0},
        {"mc": 0.0},
        {"A": 120.0},
        {"A": -1.0},
        {"kaynak": ""},
        {"name": ""},
        {"id": ""},
        {"id": "C 45"},
        {"id": "C45/1"},
        {"grup": "tahta"},
        {"iso513": "X"},
        # kümede olmayan takım anahtarı; nesneler test içinde kurulur (toplama aşamasında değil)
        {"taylor": lambda: {"elmas": Taylor(C=300.0, n=0.25)}},
        {"kesme": lambda: {"elmas": KesmeOnerisi(Vc=200.0, fz=0.1)}},
    ],
    ids=lambda d: ",".join(f"{k}={'elmas' if callable(v) else v!r}" for k, v in d.items()),
)
def test_k2_tutarsiz_kayit_hata(degisen):
    degisen = {k: v() if callable(v) else v for k, v in degisen.items()}
    with pytest.raises(ModelError):
        celik(**degisen)


def test_k2_alpha_sifir_gecerli():
    """Invar benzeri malzeme: α = 0 geçerli."""
    assert celik(alpha=0.0).alpha == 0.0


def test_k2_sinir_degerler_gecerli():
    m = celik(Rp02=600.0, Rm=600.0, A=0.0)  # Rp02 = Rm ve A = 0 izinli
    assert m.Rp02 == m.Rm
    celik(A=100.0)


@pytest.mark.parametrize("harf", ["P", "M", "K", "N", "S", "H"])
def test_k2_iso513_gecerli_harfler(harf):
    assert celik(iso513=harf).iso513 == harf


@pytest.mark.parametrize("grup", GRUPLAR)
def test_k2_gruplar_gecerli(grup):
    assert celik(grup=grup).grup == grup


@pytest.mark.parametrize("id_", ["1.0503", "EN-AW-6061-T6", "POM-C", "a_b.c-9"])
def test_k2_gecerli_id(id_):
    assert celik(id=id_).id == id_


@pytest.mark.parametrize(
    "C, n",
    [
        (300.0, 1.0),
        (300.0, 0.0),
        (300.0, -0.2),
        (0.0, 0.25),
        (-300.0, 0.25),
        (math.nan, 0.25),
        (300.0, math.inf),
    ],
)
def test_k2_taylor_gecersiz(C, n):
    with pytest.raises(ModelError):
        Taylor(C=C, n=n)


@pytest.mark.parametrize(
    "kw",
    [
        {"Vc": 200.0},  # ne fz ne fn
        {"Vc": 0.0, "fz": 0.1},
        {"Vc": -200.0, "fz": 0.1},
        {"Vc": 200.0, "fz": 0.0},
        {"Vc": 200.0, "fn": -0.2},
        {"Vc": math.nan, "fz": 0.1},
    ],
)
def test_k2_kesme_onerisi_gecersiz(kw):
    with pytest.raises(ModelError):
        KesmeOnerisi(**kw)


def test_k2_kesme_onerisi_gecerli():
    assert KesmeOnerisi(Vc=200.0, fz=0.1).fn is None
    assert KesmeOnerisi(Vc=120.0, fn=0.25).fz is None


# ---------------------------------------------------------------- K3 eksik alan istenince


def test_k3_yari_bos_kurulur():
    m = yari_bos()
    assert m.k is None and m.kc11 is None and m.sigma_f is None
    assert len(m.taylor) == 0 and len(m.kesme) == 0


def test_k3_iste_eksik_alan_mesajli():
    m = yari_bos()
    with pytest.raises(ModelError) as e:
        m.iste("k")
    assert "POM-C" in str(e.value)
    assert "'k'" in str(e.value)  # SPEC örneği: "'C45' malzemesinde 'k' yok"


def test_k3_kesme_verisi_oneri_yok():
    with pytest.raises(ModelError) as e:
        yari_bos().kesme_verisi("karbur", 2.0)
    assert "POM-C" in str(e.value)
    assert "kesme" in str(e.value)


def test_k3_taylor_eksik_anahtar():
    """Eksik anahtar: hem ModelError hem KeyError; mesajda malzeme ve alan adı."""
    m = yari_bos()
    with pytest.raises(ModelError) as e:
        m.taylor["karbur"]
    assert isinstance(e.value, KeyError)
    assert "POM-C" in str(e.value)
    assert "taylor" in str(e.value)


def test_k3_kesme_eksik_anahtar():
    with pytest.raises(ModelError) as e:
        celik().kesme["seramik"]
    assert isinstance(e.value, KeyError)
    assert "C45" in str(e.value)


def test_k3_salt_okunur_sozluk_get_ve_in():
    m = celik()
    assert m.taylor.get("CBN") is None
    assert "CBN" not in m.taylor
    assert "karbur" in m.taylor
    assert m.taylor["karbur"] == Taylor(C=300.0, n=0.25)
    assert set(m.kesme) == {"karbur", "HSS"}
    assert len(m.kesme) == 2


def test_k3_G_nu_yok():
    m = Malzeme(id="x", name="X", standart="", grup="diger", kaynak="test", E=1000.0)
    with pytest.raises(ModelError):
        _ = m.G


def test_k3_G_E_yok():
    m = Malzeme(id="x", name="X", standart="", grup="diger", kaynak="test", nu=0.3)
    with pytest.raises(ModelError):
        _ = m.G


# ---------------------------------------------------------------- K4 Taylor


def test_k4_taylor_omur():
    t = Taylor(C=300.0, n=0.25)
    assert t.omur(150.0) == pytest.approx(16.0, rel=1e-12)  # (300/150)^(1/0.25) = 2^4
    assert t.omur(300.0) == pytest.approx(1.0, rel=1e-12)


def test_k4_taylor_genel():
    t = Taylor(C=40.0, n=0.125)
    assert t.omur(20.0) == pytest.approx(256.0, rel=1e-12)  # 2^8


@pytest.mark.parametrize("Vc", [0.0, -5.0])
def test_k4_taylor_gecersiz_hiz(Vc):
    with pytest.raises(ModelError):
        Taylor(C=300.0, n=0.25).omur(Vc)


# ---------------------------------------------------------------- K5 kesme köprüsü


def test_k5_kesme_verisi_freze():
    from cam.model import CuttingData

    m = celik(kesme={"karbur": KesmeOnerisi(Vc=200.0, fz=0.1)})
    cd = m.kesme_verisi("karbur", ap=2.0, ae=5.0)
    assert isinstance(cd, CuttingData)
    assert cd.to_dict() == CuttingData(Vc=200.0, fz=0.1, ap=2.0, ae=5.0).to_dict()


def test_k5_kesme_verisi_torna_ae_yok():
    from cam.model import CuttingData

    cd = celik().kesme_verisi("HSS", ap=1.5)
    assert cd.to_dict() == CuttingData(Vc=30.0, fn=0.2, ap=1.5).to_dict()


def test_k5_kesme_verisi_oneri_olmayan_takim():
    m = celik(kesme={"karbur": KesmeOnerisi(Vc=200.0, fz=0.1)})
    with pytest.raises(ModelError):
        m.kesme_verisi("HSS", ap=2.0)


def test_k5_kesme_verisi_kume_disi_takim():
    with pytest.raises(ModelError):
        celik().kesme_verisi("elmas", ap=2.0)


# ---------------------------------------------------------------- K6 gidiş-dönüş


@pytest.mark.parametrize("kayit", [celik, yari_bos], ids=["dolu", "yari_bos"])
def test_k6_gidis_donus(kayit):
    m = kayit()
    d = m.to_dict()
    assert Malzeme.from_dict(d) == m
    assert Malzeme.from_dict(json.loads(json.dumps(d))) == m


def test_k6_none_alan_yazilmaz():
    d = yari_bos().to_dict()
    json.dumps(d)
    assert d["E"] == 2800.0
    for alan in ("k", "cp", "kc11", "mc", "fiyat", "iso513", "sigma_f", "sertlik"):
        assert alan not in d
    assert None not in d.values()


def test_k6_dolu_kayit_json():
    d = celik().to_dict()
    metin = json.dumps(d)
    assert "karbur" in metin and "HSS" in metin
    assert d["id"] == "1.0503"


def test_k6_bilinmeyen_anahtar_hata():
    d = celik().to_dict()
    d["Rp0.2"] = 355.0
    with pytest.raises(ModelError):
        Malzeme.from_dict(d)


def test_k6_from_dict_tutarlilik_denetler():
    d = celik().to_dict()
    d["nu"] = 0.5
    with pytest.raises(ModelError):
        Malzeme.from_dict(d)


# ---------------------------------------------------------------- K7 dondurulmuşluk


def test_k7_alan_degistirilemez():
    m = celik()
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.E = 1.0


def test_k7_sozluk_degistirilemez():
    m = celik()
    with pytest.raises(TypeError):
        m.taylor["karbur"] = Taylor(C=1.0, n=0.5)
    with pytest.raises(TypeError):
        m.kesme["CBN"] = KesmeOnerisi(Vc=100.0, fz=0.05)


def test_k7_disaridaki_sozluk_kaydi_degistirmez():
    taylor = {"karbur": Taylor(C=300.0, n=0.25)}
    m = celik(taylor=taylor)
    taylor["CBN"] = Taylor(C=500.0, n=0.3)
    assert "CBN" not in m.taylor


def test_k7_hash_ve_esitlik():
    a, b = celik(), celik()
    assert hash(a) == hash(b)
    assert a == b
    assert len({a, b, yari_bos()}) == 2
    # sözlük alanları eşitliğe katılır
    assert celik(taylor={"karbur": Taylor(C=301.0, n=0.25)}) != a


# ---------------------------------------------------------------- K9 bağımlılık yönü


def test_k9_import_core_cam_occt_yuklemez():
    kod = (
        "import sys, malzeme.model\n"
        "yasak = ('core', 'cam', 'OCP', 'build123d')\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in yasak))\n"
    )
    cikti = subprocess.run(
        [sys.executable, "-c", kod], cwd=KOK, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert cikti == "[]"


@pytest.mark.parametrize("paket", ["core", "cam", "assy", "geometry"])
def test_k9_paketler_malzemeye_bagli_degil(paket):
    for py in (KOK / paket).rglob("*.py"):
        metin = py.read_text(encoding="utf-8")
        assert "import malzeme" not in metin, py
        assert "from malzeme" not in metin, py
