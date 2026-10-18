"""SPEC 63 — DNC, dosya yoluyla gönderme (K1–K7): dosya_kurali, dosya_adi, denetle, gonder, kayitlari_oku.

Testler yalnız SPEC 63 metninden ve sabit arayüzlerden (atolye/dnc.py imzaları, atolye/dnc_kurallari.json,
cam.post `post` / `builtin_machines`) yazıldı; atolye/dnc.py gövdeleri okunmadı.

Uydurma iş: 30 × 20 mm dikdörtgen cep (Ø6 düz freze, 4 mm derinlik, iki paso), SPEC 30 / 31 örnek profilleri.
Program `cam.post.post` ile üretilir; Ö2 gidiş-dönüşü bu yolla karşılaştırılır. Hedef klasör `tmp_path`.

Yorumlanan noktalar (SPEC'te sayı / biçim yok):
- `kontroller` Tezgah kontrol sözlükleri; derece alanı `durum` ("tamam" | "uyari" | "hata").
- Kanonik JSON satırı: `json.dumps(kayit, sort_keys=True, separators=(",", ":"))` (ensure_ascii serbest).
- `program.ozet`: yazılan dosya baytlarının sha256 onaltılığını içerir (önekli biçim de kabul).
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from dataclasses import replace
from pathlib import Path

import pytest

from atolye import DosyaKurali, Gonderim, denetle, dosya_adi, dosya_kurali, gonder, kayitlari_oku
from cam.model import CamError, MachineProfile, Setup, Stock, Tool, ToolHolder, ToolKind, Wcs
from cam.ops2d import Cut, pocket
from cam.post import builtin_machines, post
from cam.profile import Profile, Region

KOK = Path(__file__).resolve().parents[2]
KURAL_DOSYASI = KOK / "atolye" / "dnc_kurallari.json"

SIN = "ORNEK-SINUMERIK-DIK"
HEI = "ORNEK-HEIDENHAIN-DIK"
FAN = "ORNEK-FANUC-DIK"
HAAS = "ORNEK-HAAS-DIK"
GRBL = "ORNEK-GRBL-ROUTER"

ZAMAN1 = "2026-10-18T12:00:00Z"
ZAMAN2 = "2026-10-18T12:05:00Z"
OPERATOR = "operator1"
TEMIZ = [
    {
        "kimlik": "sim_carpisma",
        "baslik": "Çarpışma",
        "deger": 0,
        "birim": "",
        "durum": "tamam",
        "aciklama": "",
        "spec": "05",
    }
]


# ------------------------------------------------------------------ uydurma iş


def takim() -> Tool:
    tutucu = ToolHolder("TUTUCU", gauge_length=60.0, profile=((0.0, 20.0), (60.0, 20.0)))
    return Tool(1, "freze1", ToolKind.FLAT, D=6.0, flute_length=20.0, stickout=40.0, holder=tutucu)


def cep(derinlik: float = 4.0):
    cut = Cut(
        z_top=0.0,
        z_bottom=-derinlik,
        a_p=2.0,
        feed=600.0,
        plunge_feed=200.0,
        rpm=6000.0,
        z_safe=5.0,
        stepover=2.5,
    )
    return pocket(Region(Profile.rectangle(-15.0, -10.0, 30.0, 20.0)), takim(), cut)


KURULUM = Setup("bag", Wcs("G54", (0.0, 0.0, -200.0)), Stock(-50.0, -50.0, -30.0, 50.0, 50.0, 0.0))


def profil(ad: str, **kw) -> MachineProfile:
    m = builtin_machines()[ad]
    return replace(m, **kw) if kw else m


def is_(ad: str, program_no: int = 12, derinlik: float = 4.0, **kw):
    """(metin, profil, yollar) üçlüsü."""
    m = profil(ad, **kw)
    yol = cep(derinlik)
    return post([yol], m, KURULUM, program_no=program_no), m, [yol]


def yolla(metin, m, yollar, hedef, kayit, program_no=12, ad=None, kontroller=TEMIZ, zaman=ZAMAN1, **kw):
    return gonder(
        metin,
        m,
        yollar,
        kontroller,
        hedef=hedef,
        operator=OPERATOR,
        zaman=zaman,
        program_no=program_no,
        ad=ad,
        kayit_dosyasi=kayit,
        **kw,
    )


@pytest.fixture
def hedef(tmp_path) -> Path:
    h = tmp_path / "tezgah"
    h.mkdir()
    (h / "BASKA.NC").write_bytes(b"%\r\nO0001\r\nM30\r\n%\r\n")  # hedefte önceden duran başka program
    return h


@pytest.fixture
def kayit(tmp_path) -> Path:
    return tmp_path / "kayit" / "gonderim-kaydi.jsonl"


def liste(klasor: Path) -> list[tuple[str, bytes]]:
    """Klasörün bütün içeriği (gizli dosyalar ve alt klasörler dahil)."""
    return sorted(
        (str(p.relative_to(klasor)), p.read_bytes() if p.is_file() else b"<dir>") for p in klasor.rglob("*")
    )


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ kural tablosu


def test_kural_tablosu_spec_tablosuyla_ayni():
    d = json.loads(KURAL_DOSYASI.read_text(encoding="utf-8"))
    assert d["sema"] == 1
    k = {r["kontrolor"]: r for r in d["kurallar"]}
    assert set(k) == {"sinumerik", "heidenhain", "fanuc", "haas", "grbl"}
    beklenen = {
        "sinumerik": (".MPF", "\n", None),
        "heidenhain": (".H", "\r\n", None),
        "fanuc": ("", "\r\n", "%"),
        "haas": (".NC", "\r\n", "%"),
        "grbl": (".nc", "\n", None),
    }
    for kon, (uz, ss, sin) in beklenen.items():
        assert (k[kon]["uzanti"], k[kon]["satir_sonu"], k[kon]["sinirlayici"]) == (uz, ss, sin), kon
        assert k[kon]["kaynak"]
        assert isinstance(k[kon]["satir_uzunlugu"], int) and k[kon]["satir_uzunlugu"] > 0
    # ad desenleri SPEC tablosundaki örneklerle
    assert re.fullmatch(k["sinumerik"]["ad_deseni"], "CEP_1")
    assert not re.fullmatch(k["sinumerik"]["ad_deseni"], "1CEP")
    assert not re.fullmatch(k["sinumerik"]["ad_deseni"], "C1EP")  # ilk iki karakter harf
    assert re.fullmatch(k["fanuc"]["ad_deseni"], "O0012")
    assert re.fullmatch(k["haas"]["ad_deseni"], "O00012")


@pytest.mark.parametrize("ad", [SIN, HEI, FAN, HAAS, GRBL])
def test_dosya_kurali_tablodan(ad):
    m = profil(ad)
    satir = {r["kontrolor"]: r for r in json.loads(KURAL_DOSYASI.read_text(encoding="utf-8"))["kurallar"]}[
        m.controller
    ]
    beklenen = DosyaKurali(
        kontrolor=satir["kontrolor"],
        ad_deseni=satir["ad_deseni"],
        uzanti=satir["uzanti"],
        satir_sonu=satir["satir_sonu"],
        satir_uzunlugu=satir["satir_uzunlugu"],
        sinirlayici=satir["sinirlayici"],
    )
    assert dosya_kurali(m) == beklenen


def test_dosya_kurali_bilinmeyen_kontrolor():
    with pytest.raises(CamError):
        dosya_kurali(profil(FAN, controller="okuma"))


# ------------------------------------------------------------------ K1 dosya adı


def test_ad():
    assert dosya_adi(profil(SIN), 12, "CEP_1") == "CEP_1.MPF"
    assert dosya_adi(profil(HEI), 12, "CEP_1") == "CEP_1.H"
    assert dosya_adi(profil(FAN), 12) == "O0012"
    assert dosya_adi(profil(FAN), 7) == "O0007"
    assert dosya_adi(profil(HAAS), 12) == "O00012.NC"
    assert dosya_adi(profil(GRBL), 12, "cep-1") == "cep-1.nc"


@pytest.mark.parametrize("ad", ["1CEP", "çep", "ÇEP", "A" * 25, "CEP 1", "", "C1EP"])
def test_ad_sinumerik_kurala_uymayan(ad):
    with pytest.raises(CamError):
        dosya_adi(profil(SIN), 12, ad)


@pytest.mark.parametrize("ad", ["çep", "A" * 25, "CEP 1", "CEP-1", ""])
def test_ad_heidenhain_kurala_uymayan(ad):
    with pytest.raises(CamError):
        dosya_adi(profil(HEI), 12, ad)


def test_ad_sinir_uzunluklari():
    assert dosya_adi(profil(SIN), 12, "AB" + "C" * 22) == "AB" + "C" * 22 + ".MPF"  # 24 karakter
    assert dosya_adi(profil(HEI), 12, "a" * 24) == "a" * 24 + ".H"


def test_ad_fanuc_dort_haneyi_asan_numara():
    m = profil(FAN, program_no_range=(1, 99999))
    with pytest.raises(CamError):
        dosya_adi(m, 10000)  # O10000: 'O' + 4 hane kuralına uymaz


# ------------------------------------------------------------------ K2 içerik biçimi


def crlf_tam(b: bytes) -> bool:
    """Her satır '\\r\\n' ile bitiyor, tek başına '\\r' veya '\\n' yok."""
    return b.endswith(b"\r\n") and b.count(b"\n") == b.count(b"\r\n") == b.count(b"\r")


def test_bicim_sinumerik(hedef, kayit):
    metin, m, yollar = is_(SIN)
    g = yolla(metin, m, yollar, hedef, kayit, ad="CEP_1")
    assert isinstance(g, Gonderim)
    assert g.sonuc == "yazildi"
    assert Path(g.yol) == hedef / "CEP_1.MPF"
    b = (hedef / "CEP_1.MPF").read_bytes()
    assert b"\r" not in b
    assert b.decode("ascii") == metin


def test_bicim_heidenhain(hedef, kayit):
    metin, m, yollar = is_(HEI)
    g = yolla(metin, m, yollar, hedef, kayit, ad="CEP_1")
    assert Path(g.yol) == hedef / "CEP_1.H"
    b = (hedef / "CEP_1.H").read_bytes()
    assert crlf_tam(b)
    t = b.decode("ascii").replace("\r\n", "\n")
    lines = t.splitlines()
    bas = re.search(r"\bBEGIN PGM (\S+) MM\b", lines[0])
    son = re.search(r"\bEND PGM (\S+) MM\b", lines[-1])
    assert bas and son
    assert bas.group(1) == son.group(1) == "CEP_1"
    assert sum("BEGIN PGM" in s for s in lines) == 1 and sum("END PGM" in s for s in lines) == 1
    # adlar dışında içerik post çıktısıyla aynı
    norm = re.sub(r"(BEGIN|END) PGM \S+ MM", r"\1 PGM X MM", t)
    assert norm == re.sub(r"(BEGIN|END) PGM \S+ MM", r"\1 PGM X MM", metin)


def test_bicim_fanuc(hedef, kayit):
    metin, m, yollar = is_(FAN)
    g = yolla(metin, m, yollar, hedef, kayit)
    assert Path(g.yol) == hedef / "O0012"
    b = (hedef / "O0012").read_bytes()
    assert crlf_tam(b)
    t = b.decode("ascii")
    lines = t.split("\r\n")[:-1]
    assert lines[0] == "%" and lines[-1] == "%"
    assert "O0012" in lines[1]  # O numarası program numarasıyla aynı
    assert t.replace("\r\n", "\n") == metin


# ------------------------------------------------------------------ K3 ön koşullar


def satir_no(metin: str, desen: str) -> tuple[int, str]:
    """Deseni tutan ilk satırın (1 tabanlı) numarası ve kendisi."""
    for i, s in enumerate(metin.split("\n"), 1):
        if re.search(desen, s):
            return i, s
    raise AssertionError(desen)


def bozuk_program(metin: str) -> tuple[str, int]:
    """Gövdedeki ilk 'X<sayı>' satırının X değerini 1 mm kaydırır (yalnız X'li doğrusal satır)."""
    lines = metin.split("\n")
    for i, s in enumerate(lines):
        if i > 5 and re.fullmatch(r"X-?\d+(\.\d*)?", s):
            lines[i] = f"X{float(s[1:]) + 1.0:g}"
            return "\n".join(lines), i + 1
    raise AssertionError("X satırı yok")


def hata_durumlari(tmp_path):
    """(ad, metin, profil, yollar, kontroller, program_no, mesaj deseni)."""
    sm, s, sy = is_(SIN)
    fm, f, fy = is_(FAN)
    bozuk, n_bozuk = bozuk_program(sm)
    hata_k = [*TEMIZ, {**TEMIZ[0], "kimlik": "tezgah_kurs", "durum": "hata", "aciklama": "Z kursu dışında"}]
    n4 = 4
    lines = fm.split("\n")
    sl = "\n".join(lines[: n4 - 1] + ["(KOSE ş)"] + lines[n4 - 1 :])
    uzun = "\n".join(lines[: n4 - 1] + ["(" + "A" * 300 + ")"] + lines[n4 - 1 :])
    n_uyari, _ = satir_no(fm, "DOGRULANMAMIS PROFIL")
    uyarisiz = "\n".join(s for i, s in enumerate(lines, 1) if i != n_uyari)
    return [
        ("O1 hata dereceli kontrol", fm, f, fy, hata_k, 12, None),
        ("O2 bozuk satir", bozuk, s, sy, TEMIZ, 12, rf"satır {n_bozuk}\b"),
        ("O3 aralik disi numara", fm, f, fy, TEMIZ, 8000, None),
        ("O4 ascii disi", sl, f, fy, TEMIZ, 12, rf"satır {n4}\b"),
        ("O4 uzun satir", uzun, f, fy, TEMIZ, 12, rf"satır {n4}\b"),
        ("O5 uyarisiz dogrulanmamis", uyarisiz, f, fy, TEMIZ, 12, None),
    ]


DURUMLAR = ["O1", "O2", "O3", "O4a", "O4b", "O5"]


@pytest.mark.parametrize("i", range(len(DURUMLAR)), ids=DURUMLAR)
def test_on_kosul(i, tmp_path, hedef, kayit):
    _, metin, m, yollar, kontroller, no, desen = hata_durumlari(tmp_path)[i]
    once = liste(hedef)
    with pytest.raises(CamError, match=desen):
        yolla(metin, m, yollar, hedef, kayit, program_no=no, kontroller=kontroller)
    assert liste(hedef) == once  # hedef klasör değişmedi
    assert not kayit.exists()  # başarısız gönderim kayda girmez


@pytest.mark.parametrize("i", range(len(DURUMLAR)), ids=DURUMLAR)
def test_on_kosul_denetle(i, tmp_path):
    _, metin, m, yollar, kontroller, no, desen = hata_durumlari(tmp_path)[i]
    if no != 12:
        pytest.skip("program numarası denetle'ye verilmez; gonder ile sınanıyor")
    with pytest.raises(CamError, match=desen):
        denetle(metin, m, yollar, kontroller)


def test_on_kosul_ascii_disi_karakter_mesajda(hedef, kayit):
    fm, f, fy = is_(FAN)
    lines = fm.split("\n")
    sl = "\n".join(lines[:3] + ["(KOSE ş)"] + lines[3:])
    with pytest.raises(CamError) as e:
        yolla(sl, f, fy, hedef, kayit)
    assert "ş" in str(e.value) or "\\u015f" in str(e.value) or "U+015F" in str(e.value).upper()


def test_on_kosul_temiz_is_gecer(tmp_path):
    for ad in (SIN, HEI, FAN):
        metin, m, yollar = is_(ad)
        uyarilar = denetle(metin, m, yollar, TEMIZ)
        assert isinstance(uyarilar, list) and all(isinstance(u, str) for u in uyarilar)


def test_on_kosul_dogrulanmis_profil_uyarisiz_gecer(hedef, kayit):
    metin, m, yollar = is_(FAN, verified=True)
    assert "DOGRULANMAMIS" not in metin
    g = yolla(metin, m, yollar, hedef, kayit)
    assert g.sonuc == "yazildi"
    assert g.kayit["dogrulanmis"] is True


# ------------------------------------------------------------------ K4 ezme


def test_ezme(hedef, kayit):
    metin, m, yollar = is_(FAN)
    g1 = yolla(metin, m, yollar, hedef, kayit)
    yol = hedef / "O0012"
    eski = yol.read_bytes()
    os.utime(yol, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    zaman_once = yol.stat().st_mtime_ns

    # aynı içerik: yazılmaz, 'ayni', dosya zamanı değişmez, kayda girer
    g2 = yolla(metin, m, yollar, hedef, kayit, zaman=ZAMAN2)
    assert g1.sonuc == "yazildi" and g2.sonuc == "ayni"
    assert yol.stat().st_mtime_ns == zaman_once
    assert yol.read_bytes() == eski
    assert [k["sonuc"] for k in kayitlari_oku(kayit)] == ["yazildi", "ayni"]

    # farklı içerik
    yeni_metin, _, yeni_yollar = is_(FAN, derinlik=3.0)
    assert yeni_metin != metin
    once = liste(hedef)
    with pytest.raises(CamError):
        yolla(yeni_metin, m, yeni_yollar, hedef, kayit)
    with pytest.raises(CamError):
        yolla(yeni_metin, m, yeni_yollar, hedef, kayit, ezme=True, gerekce="")
    assert liste(hedef) == once
    assert len(kayitlari_oku(kayit)) == 2

    g3 = yolla(yeni_metin, m, yeni_yollar, hedef, kayit, ezme=True, gerekce="rev B")
    assert g3.sonuc == "ezildi"
    assert yol.read_bytes().replace(b"\r\n", b"\n").decode("ascii") == yeni_metin
    yedek = hedef / ".3dcore-yedek" / f"O0012.{sha(eski)[:12]}"
    assert yedek.read_bytes() == eski
    son = kayitlari_oku(kayit)[-1]
    assert son["sonuc"] == "ezildi" and son["gerekce"] == "rev B"
    assert len(kayitlari_oku(kayit)) == 3


def test_ezme_farkli_icerik_mesaji(hedef, kayit):
    metin, m, yollar = is_(FAN)
    yolla(metin, m, yollar, hedef, kayit)
    eski = (hedef / "O0012").read_bytes()
    yeni_metin, _, yeni_yollar = is_(FAN, derinlik=3.0)
    with pytest.raises(CamError) as e:
        yolla(yeni_metin, m, yeni_yollar, hedef, kayit)
    msg = str(e.value)
    assert "O0012" in msg
    assert sha(eski)[:12] in msg  # eski dosyanın sha256'sı mesajda


# ------------------------------------------------------------------ K5 atomik yazım


def test_atomik(hedef, kayit, monkeypatch):
    metin, m, yollar = is_(FAN)
    once = liste(hedef)

    def bozuk_replace(*a, **k):
        raise OSError("ağ sürücüsü replace desteklemiyor")

    monkeypatch.setattr(os, "replace", bozuk_replace)
    with pytest.raises(CamError):
        yolla(metin, m, yollar, hedef, kayit)
    monkeypatch.undo()
    assert liste(hedef) == once  # ne asıl ne geçici (.O0012.yaziliyor) dosya kaldı
    assert not (hedef / "O0012").exists()
    assert not (hedef / ".O0012.yaziliyor").exists()


# ------------------------------------------------------------------ K6 kayıt


def kanonik(d: dict) -> set[str]:
    return {json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=a) for a in (True, False)}


def test_kayit(hedef, kayit):
    sm, s, sy = is_(SIN)
    fm, f, fy = is_(FAN)
    g1 = yolla(sm, s, sy, hedef, kayit, ad="CEP_1", zaman=ZAMAN1)
    g2 = yolla(fm, f, fy, hedef, kayit, zaman=ZAMAN2)
    raw = kayit.read_text(encoding="utf-8")
    satirlar = raw.splitlines()
    assert raw.endswith("\n") and len(satirlar) == 2
    okunan = kayitlari_oku(kayit)
    assert okunan == [json.loads(x) for x in satirlar]
    assert okunan == [g1.kayit, g2.kayit]
    for x in satirlar:
        assert x in kanonik(json.loads(x))
    for k, g, m, zaman in ((okunan[0], g1, s, ZAMAN1), (okunan[1], g2, f, ZAMAN2)):
        assert k["sema"] == 1
        assert k["zaman"] == zaman  # çağıranın verdiği
        assert k["operator"] == OPERATOR
        assert k["profil"]["ad"] == m.name and k["profil"]["ozet"]
        assert sha(Path(g.yol).read_bytes()) in k["program"]["ozet"]
        assert k["program"]["program_no"] == 12
        assert "lehce" in k["program"] and "ad" in k["program"]
        assert str(hedef) in k["hedef"]
        assert k["sonuc"] == "yazildi"
        assert k["gerekce"] == ""
        assert k["dogrulanmis"] is False
        assert k["denetim"]["sim"] == "temiz" and k["denetim"]["gidis_donus"] == "ayni"
        assert isinstance(k["denetim"]["uyarilar"], list)
        assert k["is_foyu"] is None


def test_kayit_is_foyu(tmp_path, hedef, kayit):
    foy = tmp_path / "is-foyu.html"
    foy.write_text("<html>uydurma föy</html>", encoding="utf-8")
    metin, m, yollar = is_(FAN)
    g = yolla(metin, m, yollar, hedef, kayit, is_foyu=foy)
    assert set(g.kayit["is_foyu"]) >= {"yol", "ozet"}
    assert foy.name in g.kayit["is_foyu"]["yol"]


def test_kayit_dosyasi_yalniz_eklenir(hedef, kayit):
    metin, m, yollar = is_(FAN)
    yolla(metin, m, yollar, hedef, kayit)
    ilk = kayit.read_bytes()
    yolla(metin, m, yollar, hedef, kayit, zaman=ZAMAN2)  # 'ayni'
    assert kayit.read_bytes().startswith(ilk)


def test_kayit_profil_ozeti_spec48(hedef, kayit):
    dogrulama = pytest.importorskip("atolye.dogrulama")
    profil_ozeti = getattr(dogrulama, "profil_ozeti", None)
    if profil_ozeti is None:
        pytest.skip("SPEC 48 profil_ozeti yok")
    metin, m, yollar = is_(FAN)
    g = yolla(metin, m, yollar, hedef, kayit)
    assert g.kayit["profil"]["ozet"] == profil_ozeti(m)


# ------------------------------------------------------------------ K7 ağ yok

YASAK = {"socket", "serial", "http", "urllib", "ftplib", "requests", "subprocess"}
YASAK_CAGRI = {"system", "popen", "spawnl", "spawnv", "spawnlp", "spawnvp", "execv", "execl", "startfile"}


def yasaklar(yol: Path) -> list[str]:
    agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
    out = []
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names if a.name.split(".")[0] in YASAK]
        elif isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] in YASAK:
            out.append(n.module)
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "os":
            if n.attr in YASAK_CAGRI or n.attr.startswith(("spawn", "exec", "popen")):
                out.append(f"os.{n.attr}")
        elif isinstance(n, ast.Name) and n.id in {"__import__"}:
            out.append(n.id)
    return out


def test_ag_yok():
    assert yasaklar(KOK / "atolye" / "dnc.py") == []


def test_ag_yok_tarayici_yakalar(tmp_path):
    p = tmp_path / "x.py"
    p.write_text(
        "import socket\nimport http.client\nfrom urllib.request import urlopen\nimport subprocess\n"
        "import os\nos.system('ls')\nimport serial\nimport json\n"
    )
    assert sorted(yasaklar(p)) == sorted(
        ["socket", "http.client", "urllib.request", "subprocess", "os.system", "serial"]
    )
