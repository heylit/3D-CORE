"""SPEC 48 — gerçek tezgâh doğrulama kaydı testleri (K1–K9; K10 test_bagimlilik.py'de).

Yalnız SPEC 48 metninden ve `atolye/dogrulama.py` iskeletinin imzaları ile modül docstring'inden yazıldı;
uygulama gövdesi okunmadı. Uydurma girdiler: SPEC 30 örnek profili (`ornek-sinumerik-dik.json`), SPEC 38 Ek A
iş föyü, elle yazılmış birkaç satırlık G-code dosyası.

Docstring'in sabitlediği ayrıntılar:
- Kanonik JSON: sort_keys, ensure_ascii=False, separators=(",", ":"), allow_nan=False, sonda tek "\\n".
- Dosya adı `<klasor>/<profil.ad>/<tarih>-<sıra 3 hane>-<adim>.json`; hata mesajı bu adla başlar.
- Zincir anahtarı (profil.ozet, program.ozet); son `masa` yeni zincir; `kaldi` sonrası yalnız `masa`.
- `profil_ozeti` `verified` hariç.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path

import pytest

from atolye import dogrulama as D
from atolye.dogrulama import (
    ADIMLAR,
    KAPSAMLAR,
    DogrulamaKaydi,
    IsFoyu,
    Madde,
    Olcum,
    Profil,
    Program,
    bos_kayit,
    denetle,
    dosya_ozeti,
    hazirlik,
    kanonik,
    kaydet,
    oku,
    profil_ozeti,
    rapor_html,
)
from atolye.is_foyu import InspectionItem, JobSheet, build_job_sheet
from atolye.olcum import tolerance_2768
from cam.model import AxisLimits, CamError, MachineProfile
from cam.post import load_machine
from tests.atolye import ek_a

KOK = Path(__file__).resolve().parents[2]
PROFIL_YOLU = KOK / "cam" / "post" / "profiles" / "ornek-sinumerik-dik.json"
DOCS = KOK / "docs" / "tezgah-dogrulama.md"
AD = "ORNEK-SINUMERIK-DIK"
TARIH = "2026-10-18"
HEX64 = re.compile(r"[0-9a-f]{64}")


# ---------------------------------------------------------------- girdiler


def profil() -> MachineProfile:
    return load_machine(PROFIL_YOLU)


def job_ek_a() -> JobSheet:
    """SPEC 38 Ek A föyü: 2 ölçüm kalemi (derinlik 1 ve 5), bölüm 2–5 doğrulama maddeleri."""
    return build_job_sheet(
        "Ek A", [ek_a.setup()], [ek_a.ops()], ek_a.lib(), ek_a.MATERIAL, machine=ek_a.machine()
    )


def job_20() -> JobSheet:
    """K4: tek kalem, nominal 20, ISO 2768-1 m sınıfı."""
    t = tolerance_2768(20.0, "m")
    assert t == pytest.approx(0.2, abs=1e-12)
    kalem = InspectionItem(1, "çap 20", 20.0, t, 20.0 - t, 20.0 + t)
    return replace(job_ek_a(), inspection=(kalem,))


@pytest.fixture
def prg(tmp_path) -> Path:
    p = tmp_path / "girdi" / "O0001.MPF"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"; uydurma program\nG0 X0 Y0 Z50\nG1 Z-1 F100\nM30\n")
    return p


@pytest.fixture
def prg2(tmp_path) -> Path:
    p = tmp_path / "girdi" / "O0002.MPF"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"; uydurma program 2\nG0 X0 Y0 Z50\nM30\n")
    return p


def doldur(
    k: DogrulamaKaydi, sonuc: str = "gecti", olculen: float | None = None, gerekce: str = ""
) -> DogrulamaKaydi:
    """Bütün maddeler işaretli; ölçüm kalemleri `olculen` (verilmezse nominal) ile dolu."""
    olcumler = tuple(replace(o, olculen=o.nominal if olculen is None else olculen) for o in k.olcumler)
    if k.adim not in ("mum", "olcum"):
        olcumler = ()
    if sonuc != "gecti" and not gerekce:
        gerekce = "uydurma gerekçe"
    return replace(
        k,
        sonuc=sonuc,
        maddeler=tuple(replace(m, isaret=True) for m in k.maddeler),
        olcumler=olcumler,
        gerekce=gerekce,
    )


def kayit(
    m: MachineProfile,
    program: Path,
    adim: str,
    sonuc: str = "gecti",
    job: JobSheet | None = None,
    kapsam=("freze_3x",),
    tarih: str = TARIH,
    olculen: float | None = None,
) -> DogrulamaKaydi:
    k = bos_kayit(m, program, job, adim, kapsam, tarih, "operatör A")
    return doldur(k, sonuc, olculen)


def zincir(m, program, job=None, kapsam=("freze_3x",), atla_mum=False) -> list[DogrulamaKaydi]:
    out = []
    for adim in ADIMLAR:
        sonuc = "atlandi" if (atla_mum and adim == "mum") else "gecti"
        out.append(kayit(m, program, adim, sonuc, job=job, kapsam=kapsam))
    return out


def ad(sira: int, adim: str, tarih: str = TARIH) -> str:
    return re.escape(f"{AD}/{tarih}-{sira:03d}-{adim}.json")


def docs_maddeleri() -> list[tuple[int, str]]:
    """docs bölüm 1–5'in "- [ ] " maddeleri; alt satıra taşan devam tek boşlukla birleşik."""
    out: list[tuple[int, str]] = []
    bolum = None
    for satir in DOCS.read_text(encoding="utf-8").splitlines():
        b = re.match(r"## (\d+)\.", satir)
        if b:
            bolum = int(b.group(1))
            continue
        if bolum is None or not 1 <= bolum <= 5:
            continue
        if satir.startswith("- [ ] "):
            out.append((bolum, satir[len("- [ ] ") :]))
        elif out and out[-1][0] == bolum and satir.startswith(" ") and satir.strip():
            out[-1] = (bolum, out[-1][1] + " " + satir.strip())
    return [(b, " ".join(t.split())) for b, t in out]


# ---------------------------------------------------------------- yardımcılar: kanonik, özetler


def test_kanonik_bicim():
    assert kanonik({"b": 1, "a": "ş", "c": [1, 2.5]}) == '{"a":"ş","b":1,"c":[1,2.5]}\n'
    assert kanonik({"x": {"z": None, "y": True}}) == '{"x":{"y":true,"z":null}}\n'
    with pytest.raises((CamError, ValueError)):
        kanonik({"a": float("nan")})


def test_profil_ozeti_verified_haric():
    m = profil()
    oz = profil_ozeti(m)
    assert HEX64.fullmatch(oz)
    d = m.to_dict()
    d.pop("verified")
    metin = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    assert oz == hashlib.sha256(metin.encode("utf-8")).hexdigest()
    assert profil_ozeti(replace(m, verified=True)) == oz
    assert profil_ozeti(replace(m, z=AxisLimits(-450.0, 0.0))) != oz
    assert m.verified is False


def test_dosya_ozeti(tmp_path, prg):
    assert dosya_ozeti(prg) == hashlib.sha256(prg.read_bytes()).hexdigest()
    assert dosya_ozeti(str(prg)) == dosya_ozeti(prg)
    with pytest.raises(CamError):
        dosya_ozeti(tmp_path / "yok.MPF")


# ---------------------------------------------------------------- K1 gidiş-dönüş


def test_bos_kayit_alanlari(tmp_path, prg):
    m = profil()
    job = job_ek_a()
    foy = tmp_path / "girdi" / "is-foyu.html"
    foy.write_bytes("<html>föy</html>".encode())
    k = bos_kayit(m, prg, job, "olcum", ["freze_3x"], TARIH, "operatör A", is_foyu_yolu=foy)
    assert k.sema == 1
    assert k.profil == Profil(AD, profil_ozeti(m))
    assert k.program == Program("O0001.MPF", dosya_ozeti(prg), "sinumerik")
    assert isinstance(k.is_foyu, IsFoyu) and k.is_foyu.ozet == dosya_ozeti(foy)
    assert tuple(k.kapsam) == ("freze_3x",)
    assert (k.adim, k.sonuc, k.tarih, k.operator) == ("olcum", "gecti", TARIH, "operatör A")
    assert k.notlar == "" and k.gerekce == ""
    assert all(isinstance(x, Madde) and x.isaret is False for x in k.maddeler)
    assert all(isinstance(o, Olcum) and o.olculen is None for o in k.olcumler)


def test_round_trip(tmp_path, prg):
    m = profil()
    job = job_ek_a()
    k = bos_kayit(m, prg, job, "masa", ("freze_3x",), TARIH, "operatör A")
    assert k.is_foyu is None

    # maddeler: docs bölüm 1–5 satırları + job.checks, sırayla, işaretsiz
    beklenen = [Madde(b, t, False) for b, t in docs_maddeleri()]
    beklenen += [Madde(c.section, c.text, False) for c in job.checks]
    assert len(docs_maddeleri()) >= 20
    assert list(k.maddeler) == beklenen

    # ölçümler (olcum basamağı): job.inspection ile aynı, olculen boş
    ko = bos_kayit(m, prg, job, "olcum", ("freze_3x",), TARIH, "operatör A")
    assert [(o.no, o.metin, o.nominal, o.alt, o.ust, o.olculen) for o in ko.olcumler] == [
        (i.no, i.text, i.nominal, i.lower, i.upper, None) for i in job.inspection
    ]

    dolu = replace(doldur(k), notlar="ilk deneme: ş ğ ü ı ö ç")
    yol = kaydet(dolu, tmp_path / "dogrulama")
    assert yol == tmp_path / "dogrulama" / AD / f"{TARIH}-001-masa.json"
    metin = yol.read_bytes()
    assert metin == kanonik(dolu.to_dict()).encode("utf-8")
    assert metin.endswith(b"}\n") and not metin.endswith(b"\n\n")
    assert "ş ğ ü".encode() in metin  # ensure_ascii=False

    (geri,) = oku(tmp_path / "dogrulama")
    assert geri == dolu
    assert kanonik(geri.to_dict()) == kanonik(dolu.to_dict())
    assert DogrulamaKaydi.from_dict(json.loads(metin)) == dolu

    # aynı kayıt iki kez → bayt bayt aynı dosya
    yol2 = kaydet(dolu, tmp_path / "dogrulama-2")
    assert yol2.read_bytes() == metin


def test_to_dict_anahtarlari(prg):
    k = doldur(bos_kayit(profil(), prg, job_ek_a(), "olcum", ("freze_3x",), TARIH, "operatör A"))
    d = k.to_dict()
    assert set(d) == {
        "sema",
        "profil",
        "program",
        "is_foyu",
        "kapsam",
        "adim",
        "sonuc",
        "tarih",
        "operator",
        "maddeler",
        "olcumler",
        "notlar",
        "gerekce",
    }
    assert d["sema"] == 1
    assert set(d["profil"]) == {"ad", "ozet"}
    assert set(d["program"]) == {"ad", "ozet", "lehce"}
    assert d["is_foyu"] is None
    assert d["kapsam"] == ["freze_3x"]
    assert all(set(x) == {"bolum", "metin", "isaret"} for x in d["maddeler"])
    assert d["olcumler"] and all(
        set(x) == {"no", "metin", "nominal", "alt", "ust", "olculen"} for x in d["olcumler"]
    )
    json.loads(kanonik(d))  # JSON'a yazılabilir


def test_sira_numarasi_ve_oku_duzeni(tmp_path, prg):
    m = profil()
    klasor = tmp_path / "dogrulama"
    p1 = kaydet(kayit(m, prg, "masa"), klasor)
    p2 = kaydet(kayit(m, prg, "havada"), klasor)
    p3 = kaydet(kayit(m, prg, "mum", tarih="2026-10-19"), klasor)
    assert [p.name for p in (p1, p2, p3)] == [
        f"{TARIH}-001-masa.json",
        f"{TARIH}-002-havada.json",
        "2026-10-19-001-mum.json",
    ]
    assert [(k.tarih, k.adim) for k in oku(klasor)] == [
        (TARIH, "masa"),
        (TARIH, "havada"),
        ("2026-10-19", "mum"),
    ]


def test_oku_bos_klasor(tmp_path):
    (tmp_path / "bos").mkdir()
    assert oku(tmp_path / "bos") == []


# ---------------------------------------------------------------- K2 şema


def _dosyaya(tmp_path, d: dict, adim: str = "masa") -> Path:
    klasor = tmp_path / "dogrulama"
    p = klasor / AD / f"{TARIH}-001-{adim}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return klasor


def _iyi_dict(prg, adim="masa") -> dict:
    return doldur(bos_kayit(profil(), prg, job_ek_a(), adim, ("freze_3x",), TARIH, "operatör A")).to_dict()


@pytest.mark.parametrize(
    ("degistir", "alan"),
    [
        (lambda d: d.update(fazla=1), "fazla"),
        (lambda d: d.pop("operator"), "operator"),
        (lambda d: d.pop("tarih"), "tarih"),
        (lambda d: d["profil"].pop("ozet"), "ozet"),
        (lambda d: d["program"].update(boyut=3), "boyut"),
        (lambda d: d.update(adim="kuru"), "adim"),
        (lambda d: d.update(sonuc="belki"), "sonuc"),
        (lambda d: d.update(kapsam=["freze_7x"]), "kapsam"),
        (lambda d: d.update(operator=""), "operator"),
        (lambda d: d.update(sonuc="kaldi", gerekce=""), "gerekce"),
        (lambda d: d.update(sonuc="atlandi", gerekce=""), "gerekce"),
    ],
    ids=[
        "bilinmeyen-alan",
        "eksik-operator",
        "eksik-tarih",
        "eksik-profil-ozet",
        "bilinmeyen-program-alani",
        "bilinmeyen-adim",
        "bilinmeyen-sonuc",
        "bilinmeyen-kapsam",
        "bos-operator",
        "kaldi-gerekcesiz",
        "atlandi-gerekcesiz",
    ],
)
def test_schema_oku(tmp_path, prg, degistir, alan):
    d = _iyi_dict(prg)
    degistir(d)
    klasor = _dosyaya(tmp_path, d)
    with pytest.raises(CamError, match=re.escape(f"{TARIH}-001-masa.json")) as e:
        oku(klasor)
    assert alan in str(e.value)


def test_schema_olcum_bos_olcumler(tmp_path, prg):
    d = _iyi_dict(prg, "olcum")
    d["olcumler"] = []
    klasor = _dosyaya(tmp_path, d, "olcum")
    with pytest.raises(CamError, match=re.escape(f"{TARIH}-001-olcum.json")) as e:
        oku(klasor)
    assert "olcumler" in str(e.value)


def test_schema_bozuk_json(tmp_path):
    p = tmp_path / "dogrulama" / AD / f"{TARIH}-001-masa.json"
    p.parent.mkdir(parents=True)
    p.write_text("{bozuk", encoding="utf-8")
    with pytest.raises(CamError, match=re.escape(f"{TARIH}-001-masa.json")):
        oku(tmp_path / "dogrulama")


def test_schema_from_dict(prg):
    d = _iyi_dict(prg)
    d["fazla"] = 1
    with pytest.raises(CamError, match="fazla"):
        DogrulamaKaydi.from_dict(d)


@pytest.mark.parametrize(
    ("degistir", "alan"),
    [
        (dict(operator=""), "operator"),
        (dict(operator="   "), "operator"),
        (dict(sonuc="kaldi", gerekce=""), "gerekce"),
        (dict(sonuc="atlandi", gerekce=""), "gerekce"),
        (dict(adim="kuru"), "adim"),
        (dict(sonuc="belki"), "sonuc"),
        (dict(kapsam=("freze_7x",)), "kapsam"),
    ],
    ids=["bos-operator", "bosluk-operator", "kaldi", "atlandi", "adim", "sonuc", "kapsam"],
)
def test_schema_denetle(prg, degistir, alan):
    k = replace(kayit(profil(), prg, "masa"), **degistir)
    with pytest.raises(CamError, match="^" + ad(1, k.adim)) as e:
        denetle(k, [])
    assert alan in str(e.value)


def test_schema_denetle_olcum_bos(prg):
    m = profil()
    onceki = zincir(m, prg, job_ek_a())[:4]
    k = replace(onceki[-1], adim="olcum", olcumler=())
    with pytest.raises(CamError, match="^" + ad(5, "olcum")) as e:
        denetle(k, onceki)
    assert "olcumler" in str(e.value)


def test_schema_olcumler_yalniz_mum_ve_olcum(prg):
    m = profil()
    o = Olcum(1, "çap 20", 20.0, 19.8, 20.2, 20.0)
    with pytest.raises(CamError, match="^" + ad(1, "masa")):
        denetle(replace(kayit(m, prg, "masa"), olcumler=(o,)), [])
    onceki = [kayit(m, prg, "masa")]
    with pytest.raises(CamError, match="^" + ad(2, "havada")):
        denetle(replace(kayit(m, prg, "havada"), olcumler=(o,)), onceki)
    onceki.append(kayit(m, prg, "havada"))
    denetle(replace(kayit(m, prg, "mum"), olcumler=(o,)), onceki)  # mum'da olabilir
    denetle(replace(kayit(m, prg, "mum"), olcumler=()), onceki)  # mum'da zorunlu değil


# ---------------------------------------------------------------- K3 sıra


def test_order(prg):
    m = profil()
    with pytest.raises(CamError, match="^" + ad(1, "havada")):
        denetle(kayit(m, prg, "havada"), [])

    # masa, havada, mum(atlandi), ilk_metal, olcum kabul
    z = zincir(m, prg, job_ek_a(), atla_mum=True)
    for i, k in enumerate(z):
        denetle(k, z[:i])
    assert z[2].sonuc == "atlandi" and z[2].gerekce


def test_order_atlama_yok(prg):
    m = profil()
    onceki = [kayit(m, prg, "masa"), kayit(m, prg, "havada")]
    with pytest.raises(CamError, match="^" + ad(3, "ilk_metal")):
        denetle(kayit(m, prg, "ilk_metal"), onceki)  # mum'un kaydı yok
    z = zincir(m, prg, job_ek_a())
    with pytest.raises(CamError, match="^" + ad(4, "olcum")):
        denetle(z[4], z[:2] + [z[3]])  # ilk_metal var, mum yok


def test_order_kaldi_sonrasi(prg):
    m = profil()
    onceki = [kayit(m, prg, "masa"), kayit(m, prg, "havada", "kaldi")]
    with pytest.raises(CamError, match="^" + ad(3, "mum")):
        denetle(kayit(m, prg, "mum"), onceki)
    with pytest.raises(CamError, match="^" + ad(3, "havada")):
        denetle(kayit(m, prg, "havada"), onceki)  # kaldi sonrası yalnız masa
    yeni_masa = kayit(m, prg, "masa")
    denetle(yeni_masa, onceki)
    # zincir sıfırlandı: yeni masa'dan sonra havada kabul, mum değil
    onceki = onceki + [yeni_masa]
    with pytest.raises(CamError, match="^" + ad(4, "mum")):
        denetle(kayit(m, prg, "mum"), onceki)
    denetle(kayit(m, prg, "havada"), onceki)


def test_order_yeni_masa_eski_gecisleri_sayamaz(prg):
    """Son masa yeni zincir başlatır: önceki zincirin havada'sı yeni zincirde sayılmaz."""
    m = profil()
    onceki = [kayit(m, prg, "masa"), kayit(m, prg, "havada"), kayit(m, prg, "masa")]
    with pytest.raises(CamError, match="^" + ad(4, "mum")):
        denetle(kayit(m, prg, "mum"), onceki)


def test_order_masa_ve_olcum_atlanamaz(prg):
    m = profil()
    with pytest.raises(CamError, match="^" + ad(1, "masa")):
        denetle(kayit(m, prg, "masa", "atlandi"), [])
    z = zincir(m, prg, job_ek_a())
    with pytest.raises(CamError, match="^" + ad(5, "olcum")):
        denetle(kayit(m, prg, "olcum", "atlandi", job=job_ek_a()), z[:4])


@pytest.mark.parametrize("adim", ["havada", "mum", "ilk_metal"])
def test_order_ara_basamak_atlanabilir(prg, adim):
    m = profil()
    z = zincir(m, prg, job_ek_a())
    i = ADIMLAR.index(adim)
    onceki = z[:i] + [kayit(m, prg, adim, "atlandi")]
    denetle(z[i + 1], onceki)


def test_order_farkli_program_eski_zinciri_ilerletmez(prg, prg2):
    m = profil()
    z = zincir(m, prg, job_ek_a())
    with pytest.raises(CamError, match="^" + ad(5, "olcum")):
        denetle(kayit(m, prg2, "olcum", job=job_ek_a()), z[:4])
    with pytest.raises(CamError, match="^" + ad(2, "havada")):
        denetle(kayit(m, prg2, "havada"), z[:1])
    denetle(kayit(m, prg2, "masa"), z[:4])  # ikinci program kendi zincirini başlatır


def test_order_kaydet_ile(tmp_path, prg):
    m = profil()
    klasor = tmp_path / "dogrulama"
    with pytest.raises(CamError, match="^" + ad(1, "havada")):
        kaydet(kayit(m, prg, "havada"), klasor)
    assert not klasor.exists() or not list(klasor.rglob("*.json"))
    for k in zincir(m, prg, job_ek_a()):
        kaydet(k, klasor)
    assert [k.adim for k in oku(klasor)] == list(ADIMLAR)


# ---------------------------------------------------------------- K4 ölçüm


def _olcum_kaydi(m, prg, job, olculen, sonuc="gecti"):
    return kayit(m, prg, "olcum", sonuc, job=job, olculen=olculen)


def test_measurement(prg):
    m = profil()
    job = job_20()
    onceki = zincir(m, prg, job)[:4]
    k = _olcum_kaydi(m, prg, job, 20.2)
    assert [(o.no, o.metin, o.alt, o.ust) for o in k.olcumler] == [
        (1, "çap 20", pytest.approx(19.8), pytest.approx(20.2))
    ]
    denetle(k, onceki, job=job)
    denetle(_olcum_kaydi(m, prg, job, 19.8), onceki, job=job)
    denetle(_olcum_kaydi(m, prg, job, 20.2 + 5e-10), onceki, job=job)  # 1e-9 pay

    with pytest.raises(CamError, match="^" + ad(5, "olcum")) as e:
        denetle(_olcum_kaydi(m, prg, job, 20.21), onceki, job=job)
    msg = str(e.value)
    assert "1" in msg and "çap 20" in msg
    assert re.search(r"20[.,]21", msg) and re.search(r"19[.,]8", msg) and re.search(r"20[.,]2\b", msg)

    with pytest.raises(CamError, match="^" + ad(5, "olcum")):
        denetle(_olcum_kaydi(m, prg, job, 19.79), onceki, job=job)

    # aynı kalem kaldi ile kabul
    denetle(_olcum_kaydi(m, prg, job, 20.21, "kaldi"), onceki, job=job)


def test_measurement_olculen_bos(prg):
    m = profil()
    job = job_20()
    onceki = zincir(m, prg, job)[:4]
    k = bos_kayit(m, prg, job, "olcum", ("freze_3x",), TARIH, "operatör A")  # olculen None
    with pytest.raises(CamError, match="^" + ad(5, "olcum")):
        denetle(replace(k, maddeler=tuple(replace(x, isaret=True) for x in k.maddeler)), onceki)
    with pytest.raises(CamError, match="^" + ad(5, "olcum")):
        denetle(replace(k, sonuc="kaldi", gerekce="ölçülmedi"), onceki)


def test_measurement_alt_ust_ters(prg):
    m = profil()
    onceki = zincir(m, prg, job_20())[:4]
    k = _olcum_kaydi(m, prg, job_20(), 20.0)
    ters = replace(k, olcumler=(Olcum(1, "çap 20", 20.0, 20.2, 19.8, 20.0),))
    with pytest.raises(CamError, match="^" + ad(5, "olcum")):
        denetle(ters, onceki)


def test_measurement_foyden_farkli(prg):
    m = profil()
    job = job_20()
    onceki = zincir(m, prg, job)[:4]
    k = _olcum_kaydi(m, prg, job, 20.0)
    for olc in (
        Olcum(1, "çap 20", 20.0, 19.7, 20.2, 20.0),  # alt farklı
        Olcum(1, "çap 20", 20.0, 19.8, 20.3, 20.0),  # üst farklı
        Olcum(1, "çap 21", 20.0, 19.8, 20.2, 20.0),  # metin farklı
        Olcum(1, "çap 20", 20.1, 19.8, 20.2, 20.0),  # nominal farklı
        Olcum(2, "çap 20", 20.0, 19.8, 20.2, 20.0),  # no föyde yok
    ):
        farkli = replace(k, olcumler=(olc,))
        denetle(farkli, onceki)  # job verilmeden bağ denetlenmez
        with pytest.raises(CamError, match="^" + ad(5, "olcum")):
            denetle(farkli, onceki, job=job)


# ---------------------------------------------------------------- K5 bağ


def test_links(tmp_path, prg):
    m = profil()
    job = job_ek_a()
    klasor = tmp_path / "dogrulama"
    foy = klasor / "is" / "is-foyu.html"
    foy.parent.mkdir(parents=True)
    foy.write_bytes("<html><body>föy</body></html>".encode())
    bag = IsFoyu("is/is-foyu.html", dosya_ozeti(foy))
    z = [replace(k, is_foyu=bag) for k in zincir(m, prg, job)]

    denetle(z[0], [], kok=klasor)
    kaydet(z[0], klasor, program=prg, job=job)

    # iş föyü bir bayt değişti
    b = bytearray(foy.read_bytes())
    b[-2] ^= 0x01
    foy.write_bytes(bytes(b))
    with pytest.raises(CamError, match="^" + ad(1, "masa")):
        denetle(z[0], [], kok=klasor)
    with pytest.raises(CamError, match="^" + ad(2, "havada")):
        kaydet(z[1], klasor)
    denetle(z[0], [])  # kok verilmeden bağ denetlenmez

    # iş föyü dosyası yok
    foy.unlink()
    with pytest.raises(CamError, match="^" + ad(1, "masa")):
        denetle(z[0], [], kok=klasor)


def test_links_program(prg, prg2):
    m = profil()
    k = kayit(m, prg, "masa")
    denetle(k, [], program=prg)
    with pytest.raises(CamError, match="^" + ad(1, "masa")):
        denetle(k, [], program=prg2)
    prg.write_bytes(prg.read_bytes() + b"\n")
    with pytest.raises(CamError, match="^" + ad(1, "masa")):
        denetle(k, [], program=prg)


def test_links_profil_degisti(tmp_path, prg):
    m = profil()
    kayitlar = zincir(m, prg, job_ek_a())
    assert hazirlik(m, kayitlar)["kapsam"]["freze_3x"] == "hazir"
    m2 = replace(m, z=AxisLimits(-450.0, 0.0))
    r = hazirlik(m2, kayitlar)
    assert r["kapsam"]["freze_3x"] == "masa"
    assert f"{AD}: profil değişti, 5 eski kayıt sayılmadı" in r["uyarilar"]
    assert f"{AD}: profil değişti, 5 eski kayıt sayılmadı" in _uyarilar(rapor_html(m2, kayitlar))


# ---------------------------------------------------------------- K6 hazırlık


def test_readiness(prg):
    m = profil()
    kayitlar = zincir(m, prg, job_ek_a(), kapsam=("freze_3x",))
    r = hazirlik(m, kayitlar)
    assert r["profil"] == AD
    assert set(r["kapsam"]) == set(KAPSAMLAR)
    assert r["kapsam"]["freze_3x"] == "hazir"
    assert r["kapsam"]["freze_3arti2"] == "masa"
    assert all(r["kapsam"][k] == "masa" for k in KAPSAMLAR if k != "freze_3x")
    assert r["uyarilar"] == []


def test_readiness_eksik_ilk_basamak(prg, prg2):
    m = profil()
    k32 = ("freze_3arti2",)
    kayitlar = [kayit(m, prg, "masa", kapsam=k32), kayit(m, prg, "havada", kapsam=k32)]
    assert hazirlik(m, kayitlar)["kapsam"]["freze_3arti2"] == "mum"
    kayitlar.append(kayit(m, prg, "mum", "atlandi", kapsam=k32))
    assert hazirlik(m, kayitlar)["kapsam"]["freze_3arti2"] == "ilk_metal"
    kayitlar.append(kayit(m, prg, "ilk_metal", "kaldi", kapsam=k32))
    assert hazirlik(m, kayitlar)["kapsam"]["freze_3arti2"] == "ilk_metal"
    # iki kapsamlı tam zincir başka programla
    iki = zincir(m, prg2, job_ek_a(), kapsam=("freze_3x", "freze_3arti2"))
    r = hazirlik(m, kayitlar + iki)
    assert r["kapsam"]["freze_3x"] == "hazir" and r["kapsam"]["freze_3arti2"] == "hazir"


def test_readiness_atlanan_mum_tam_sayilir(prg):
    m = profil()
    r = hazirlik(m, zincir(m, prg, job_ek_a(), atla_mum=True))
    assert r["kapsam"]["freze_3x"] == "hazir"


def test_readiness_verified_uyarisi(prg):
    m = replace(profil(), verified=True)
    r = hazirlik(m, [])
    assert r["kapsam"] == {k: "masa" for k in KAPSAMLAR}
    assert r["uyarilar"] == [f"{AD}: verified=true ama geçen doğrulama kaydı yok"]
    eksik = [kayit(m, prg, "masa")]
    assert hazirlik(m, eksik)["uyarilar"] == [f"{AD}: verified=true ama geçen doğrulama kaydı yok"]
    assert hazirlik(m, zincir(m, prg, job_ek_a()))["uyarilar"] == []
    assert hazirlik(profil(), [])["uyarilar"] == []  # verified=false: uyarı yok


def test_readiness_baska_profil_sayilmaz(prg):
    m = profil()
    baska = replace(m, name="BASKA-TEZGAH")
    r = hazirlik(m, zincir(baska, prg, job_ek_a()))
    assert r["kapsam"]["freze_3x"] == "masa"


def test_readiness_profili_degistirmez(tmp_path, prg):
    kopya = tmp_path / "profil.json"
    shutil.copyfile(PROFIL_YOLU, kopya)
    once = kopya.read_bytes()
    m = replace(load_machine(kopya), verified=True)
    d = m.to_dict()
    kayitlar = zincir(m, prg, job_ek_a())
    hazirlik(m, kayitlar)
    rapor_html(m, kayitlar)
    assert m.to_dict() == d and m.verified is True
    assert kopya.read_bytes() == once
    m0 = load_machine(kopya)
    hazirlik(m0, kayitlar)
    assert m0.verified is False


# ---------------------------------------------------------------- K7 verified yazılmaz

ATLA = {
    ".git",
    ".venv",
    "node_modules",
    "tests",
    "yerel_parcalar",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def _dosyalar(desen: str) -> list[Path]:
    return [p for p in sorted(KOK.rglob(desen)) if not (set(p.relative_to(KOK).parts) & ATLA)]


def _true_mu(n) -> bool:
    return isinstance(n, ast.Constant) and n.value is True


def _ad(n) -> str | None:
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        return n.attr
    if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant):
        return n.slice.value if isinstance(n.slice.value, str) else None
    return None


def verified_true_atamalari(kaynak: str) -> list[int]:
    """`verified`'ı True yapan satırlar: atama, anahtar kelime, sözlük, setattr."""
    out = []
    for n in ast.walk(ast.parse(kaynak)):
        if isinstance(n, ast.Assign) and _true_mu(n.value):
            out += [n.lineno for t in n.targets if _ad(t) == "verified"]
        elif isinstance(n, ast.AnnAssign) and _true_mu(n.value) and _ad(n.target) == "verified":
            out.append(n.lineno)
        elif isinstance(n, ast.keyword) and n.arg == "verified" and _true_mu(n.value):
            out.append(n.value.lineno)
        elif isinstance(n, ast.Dict):
            out += [
                v.lineno
                for k, v in zip(n.keys, n.values, strict=True)
                if isinstance(k, ast.Constant) and k.value == "verified" and _true_mu(v)
            ]
        elif (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "setattr"
            and len(n.args) == 3
            and isinstance(n.args[1], ast.Constant)
            and n.args[1].value == "verified"
            and _true_mu(n.args[2])
        ):
            out.append(n.lineno)
    return out


def test_tarayici_yakalar():
    kaynak = (
        "m.verified = True\n"
        "verified: bool = True\n"
        "f(verified=True)\n"
        "d = {'verified': True}\n"
        "d['verified'] = True\n"
        "setattr(m, 'verified', True)\n"
        "m.verified = False\n"
        "x = 'verified=True'\n"
    )
    assert sorted(verified_true_atamalari(kaynak)) == [1, 2, 3, 4, 5, 6]


def test_never_sets_verified():
    py = _dosyalar("*.py")
    assert KOK / "atolye" / "dogrulama.py" in py
    ihlal = {}
    for p in py:
        satirlar = verified_true_atamalari(p.read_text(encoding="utf-8"))
        if satirlar:
            ihlal[str(p.relative_to(KOK))] = satirlar
    assert ihlal == {}

    js = _dosyalar("*.json")
    ornek = [p for p in js if p.parent == KOK / "cam" / "post" / "profiles"]
    assert ornek
    for p in ornek:
        assert json.loads(p.read_text(encoding="utf-8")).get("verified") is False, p
    yazan = [
        str(p.relative_to(KOK))
        for p in js
        if re.search(r'"verified"\s*:\s*true', p.read_text(encoding="utf-8"))
    ]
    assert yazan == []


def test_dogrulama_profil_dosyasina_yazmaz():
    kaynak = (KOK / "atolye" / "dogrulama.py").read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    adlar = {n.id for n in ast.walk(agac) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(agac) if isinstance(n, ast.Attribute)
    }
    alinan = {a.name for n in ast.walk(agac) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert not ({"save_machine", "PROFIL_DIZINI"} & (adlar | alinan))
    dizgiler = [n.value for n in ast.walk(agac) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    kod_dizgileri = [s for s in dizgiler if "\n" not in s]  # docstring'ler hariç
    assert not any("profiles" in s for s in kod_dizgileri)


def test_akis_profil_dosyalarini_degistirmez(tmp_path, prg):
    """Bütün akış çalıştıktan sonra örnek profil dosyaları bayt bayt aynı."""
    profiller = sorted((KOK / "cam" / "post" / "profiles").glob("*.json"))
    once = {p: p.read_bytes() for p in profiller}
    m = profil()
    klasor = tmp_path / "dogrulama"
    for k in zincir(m, prg, job_ek_a()):
        kaydet(k, klasor, program=prg)
    kayitlar = oku(klasor)
    hazirlik(m, kayitlar)
    rapor_html(m, kayitlar)
    assert {p: p.read_bytes() for p in profiller} == once


# ---------------------------------------------------------------- K8 rapor


class _Ayristirici(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.yigin: list[tuple[str, str | None]] = []
        self.idler: dict[str, str] = {}
        self.satirlar: dict[str, int] = {}  # tablo id → td içeren tr sayısı (başlık satırı hariç)
        self._td = False
        self.li: dict[str, list[str]] = {}
        self._li_metin: list[str] | None = None

    def _kap(self, tag: str) -> str | None:
        for t, i in reversed(self.yigin):
            if t == tag and i:
                return i
        return None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        i = a.get("id")
        if i:
            self.idler[i] = tag
        if tag == "tr":
            self._td = False
        if tag == "td" and not self._td:
            self._td = True
            k = self._kap("table")
            if k:
                self.satirlar[k] = self.satirlar.get(k, 0) + 1
        if tag == "li":
            self._li_metin = []
        if tag not in ("br", "meta", "img", "hr", "input", "link", "col", "wbr"):
            self.yigin.append((tag, i))

    def handle_endtag(self, tag):
        if tag == "li" and self._li_metin is not None:
            k = self._kap("ul")
            if k:
                self.li.setdefault(k, []).append(" ".join("".join(self._li_metin).split()))
            self._li_metin = None
        for j in range(len(self.yigin) - 1, -1, -1):
            if self.yigin[j][0] == tag:
                del self.yigin[j:]
                break

    def handle_data(self, data):
        if self._li_metin is not None:
            self._li_metin.append(data)


def _ayristir(metin: str) -> _Ayristirici:
    p = _Ayristirici()
    p.feed(metin)
    p.close()
    return p


def _uyarilar(metin: str) -> list[str]:
    return _ayristir(metin).li.get("uyarilar", [])


def test_report_html(prg):
    m = profil()
    job = job_ek_a()
    kayitlar = zincir(m, prg, job, atla_mum=False)
    kayitlar[2] = replace(kayitlar[2], notlar="<b>mum</b> & köpük")
    metin = rapor_html(m, kayitlar)
    p = _ayristir(metin)
    assert "http" not in metin.lower()
    assert "<script" not in metin.lower()
    assert "<b>mum</b>" not in metin  # kullanıcı metni kaçışlı
    assert p.idler.get("zincir") == "table"
    assert p.idler.get("olcum") == "table"
    assert p.idler.get("kapsam") == "table"
    assert "uyarilar" not in p.idler  # uyarı yok → öğe yok
    assert p.satirlar.get("zincir", 0) == len(kayitlar)
    n_olcum = sum(len(k.olcumler) for k in kayitlar if k.adim in ("mum", "olcum"))
    assert n_olcum >= len(job.inspection)
    assert p.satirlar.get("olcum", 0) == n_olcum
    assert rapor_html(m, kayitlar) == metin  # aynı girdi → aynı metin
    assert AD in metin


def test_report_html_satir_sayisi_kayit_sayisi(prg, prg2):
    m = profil()
    kayitlar = [kayit(m, prg, "masa"), kayit(m, prg, "havada", "kaldi"), kayit(m, prg2, "masa")]
    assert _ayristir(rapor_html(m, kayitlar)).satirlar.get("zincir", 0) == 3
    assert _ayristir(rapor_html(m, [])).satirlar.get("zincir", 0) == 0


def test_report_html_uyarilar():
    m = replace(profil(), verified=True)
    metin = rapor_html(m, [])
    p = _ayristir(metin)
    assert p.idler.get("uyarilar") == "ul"
    assert p.li["uyarilar"] == [f"{AD}: verified=true ama geçen doğrulama kaydı yok"]


# ---------------------------------------------------------------- K9 belge


def _bolum(metin: str, n: int) -> str:
    m = re.search(rf"^## {n}\..*?(?=^## \d+\.|\Z)", metin, flags=re.M | re.S)
    assert m, f"## {n}. yok"
    return m.group(0)


def test_document():
    metin = DOCS.read_text(encoding="utf-8")
    if not re.search(r"^## 7\.", metin, flags=re.M):
        raise NotImplementedError("SPEC 48: docs/tezgah-dogrulama.md bölüm 7 ve 8 henüz eklenmedi")
    basliklar = [int(x) for x in re.findall(r"^## (\d+)\.", metin, flags=re.M)]
    assert basliklar[:8] == [1, 2, 3, 4, 5, 6, 7, 8]
    b7 = _bolum(metin, 7)
    for adim in ADIMLAR:
        assert adim in b7, adim
    b8 = _bolum(metin, 8)
    tezgahlar = ["NLX 2500", "DMU 50", "NHC 5000", "DMU 75", "DMF 360", "NTX 3000"]
    yerler = [b8.find(t) for t in tezgahlar]
    assert all(y >= 0 for y in yerler), dict(zip(tezgahlar, yerler, strict=True))
    assert yerler == sorted(yerler)


def test_document_bolum_1_6_basliklari_aynen():
    metin = DOCS.read_text(encoding="utf-8")
    for baslik in (
        "## 1. Masa başında (tezgâhtan önce)",
        "## 2. İş sıfırı (WCS)",
        "## 3. Takım boyu",
        "## 4. Kuru çalıştırma (havada)",
        "## 5. İlk parça",
        "## 6. İş föyü",
    ):
        assert re.search(rf"^{re.escape(baslik)}$", metin, flags=re.M), baslik


def test_modul_sabitleri():
    assert ADIMLAR == ("masa", "havada", "mum", "ilk_metal", "olcum")
    assert KAPSAMLAR == ("torna_2x", "freze_3x", "freze_3arti2", "freze_4x_indeks", "freze_5x", "torna_freze")
    assert D.SEMA == 1
