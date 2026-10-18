"""SPEC 61 — atolye/dfm.py testleri (K1–K9, K12). K1–K9 OCCT gerektirir.

Testler yalnızca SPEC 61 metninden, atolye/dfm.py arayüzünden (imzalar, Bulgu / Rapor, kural dosyası biçimi)
ve sabit arayüzlerden (cam/model.py, geometry/part.py) yazıldı; dfm.py gövdeleri okunmadı.
Uydurma geometri: bloklar min köşesi orijinde, takım ekseni +Z.

Beklenen değerler el ile türetildi:
- İç köşe: h = cep derinliği, uygun freze FLAT ve flute_length ≥ h, R_min = min D/2;
  r < R_min hata (sınır R_min), R_min ≤ r < 1.1·R_min uyarı (sınır 1.1·R_min).
- Derin cep: λ = h / D_max, D_max = D ≤ w ve flute_length ≥ h olan en büyük çap; λ > 4 uyarı, λ > 8 hata.
- Delik: h/d > 10 uyarı, > 20 hata; |D − d| ≤ 0.01 matkap yoksa bilgi.
- Erişim: n·d ≥ 0 ve p + ε n'den +d ışını parçayı kesmiyorsa nokta erişilebilir; ρ = 0 hata.
- İnce duvar: t = karşıt paralel yüze uzaklık; t < t_min(grup) hata; H / t > 15 uyarı.
- Torna kanal: kanal genişliği < en dar kanal ucu genişliği → hata.
Bulgular tür ve dereceye göre süzülerek denetlenir; aynı parçada başka türden bulgu olması testi bozmaz.
"""

from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path

import pytest

from atolye.dfm import DERECELER, KURAL_DOSYASI, TURLER, Bulgu, Rapor, denetle, kurallari_oku
from cam.model import CamError, LatheTool, LatheToolKind, Tool, ToolKind, ToolLibrary

KOK = Path(__file__).resolve().parents[2]
TOL = 1e-6


# ---------------------------------------------------------------- yardımcılar


def freze(id: int, D: float, boy: float) -> Tool:
    return Tool(id=id, name=f"freze{D:g}x{boy:g}", kind=ToolKind.FLAT, D=D, flute_length=boy)


def matkap(id: int, D: float, boy: float = 150.0) -> Tool:
    return Tool(id=id, name=f"matkap{D:g}", kind=ToolKind.DRILL, D=D, flute_length=boy)


def kanal_ucu(id: int, w: float) -> LatheTool:
    return LatheTool(
        id=id,
        name=f"kanal{w:g}",
        kind=LatheToolKind.GROOVE,
        nose_r=0.2,
        tip=3,
        kappa_r=90.0,
        eps_r=90.0,
        width=w,
    )


def tornalama_ucu(id: int) -> LatheTool:
    return LatheTool(
        id=id, name="tornalama", kind=LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=93.0, eps_r=55.0
    )


def kutuphane(*tools) -> ToolLibrary:
    return ToolLibrary(list(tools))


def bul(rapor: Rapor, tur: str, derece: str | None = None) -> list[Bulgu]:
    return [b for b in rapor.bulgular if b.tur == tur and (derece is None or b.derece == derece)]


def tek(rapor: Rapor, tur: str, derece: str) -> Bulgu:
    b = bul(rapor, tur, derece)
    assert len(b) >= 1, f"{tur}/{derece} bulgusu yok: {rapor.bulgular}"
    return b[0]


def rapor_gecerli(rapor: Rapor) -> None:
    """Her raporda geçerli olması gereken genel kurallar."""
    assert isinstance(rapor, Rapor)
    assert isinstance(rapor.bulgular, tuple)
    sira = [DERECELER.index(b.derece) for b in rapor.bulgular]
    assert sira == sorted(sira), "bulgular derece sırasında değil (hata → bilgi)"
    for b in rapor.bulgular:
        assert isinstance(b, Bulgu)
        assert b.derece in DERECELER
        if rapor.tamam:
            assert b.tur in TURLER
        assert isinstance(b.yuzler, tuple)
        assert b.yuzler or b.nokta is not None, "bulgu bir yüze ya da noktaya bağlı olmalı"
        assert b.mesaj
        assert math.isfinite(b.olculen)


def kural_dosyasi_yaz(yol: Path, icerik: dict) -> Path:
    yol.write_text(json.dumps(icerik), encoding="utf-8")
    return yol


# ---------------------------------------------------------------- kural dosyası (OCCT'siz)


def test_kural_dosyasi_bicimi():
    veri = json.loads(Path(KURAL_DOSYASI).read_text(encoding="utf-8"))
    for grup, anahtarlar in veri.items():
        for anahtar, yaprak in anahtarlar.items():
            assert set(yaprak) == {"deger", "kaynak"}, f"{grup}.{anahtar}"
            assert isinstance(yaprak["deger"], int | float)
            assert yaprak["kaynak"].strip(), f"{grup}.{anahtar}: kaynak boş"
    # SPEC 61 Kararlar 4: varsayılan eşikler
    assert veri["derin_cep"]["lambda_uyari"]["deger"] == 4
    assert veri["derin_cep"]["lambda_hata"]["deger"] == 8
    assert veri["delik"]["oran_uyari"]["deger"] == 10
    assert veri["delik"]["oran_hata"]["deger"] == 20
    assert veri["ince_duvar"]["aluminyum"]["deger"] == 0.8
    assert veri["ince_duvar"]["celik"]["deger"] == 0.5
    assert veri["ince_duvar"]["plastik"]["deger"] == 1.5
    assert veri["ince_duvar"]["H_t_uyari"]["deger"] == 15
    assert veri["ic_kose"]["oran_uyari"]["deger"] == pytest.approx(1.1)


def test_kurallari_oku_yerelsiz(tmp_path):
    repo = json.loads(Path(KURAL_DOSYASI).read_text(encoding="utf-8"))
    for yerel in (None, tmp_path / "yok.json"):
        k = kurallari_oku(yerel)
        assert set(k) == set(repo)
        for grup, anahtarlar in repo.items():
            assert set(k[grup]) == set(anahtarlar)
            for anahtar, yaprak in anahtarlar.items():
                assert k[grup][anahtar]["deger"] == yaprak["deger"]
                assert k[grup][anahtar]["kaynak"] == yaprak["kaynak"]
                assert k[grup][anahtar]["yerel"] is False


def test_kurallari_oku_yerel_ezme(tmp_path):
    yol = kural_dosyasi_yaz(tmp_path / "dfm-kurallari.json", {"ince_duvar": {"aluminyum": 0.5}})
    k = kurallari_oku(yol)
    assert k["ince_duvar"]["aluminyum"]["deger"] == 0.5
    assert k["ince_duvar"]["aluminyum"]["yerel"] is True
    assert k["ince_duvar"]["celik"]["deger"] == 0.5 and k["ince_duvar"]["celik"]["yerel"] is False
    assert k["delik"]["oran_uyari"]["yerel"] is False
    k2 = kurallari_oku(str(yol))  # str yol da kabul
    assert k2["ince_duvar"]["aluminyum"]["deger"] == 0.5


@pytest.mark.parametrize(
    "icerik",
    [
        {"ince_duvar": {"titanyum": 0.7}},  # bilinmeyen anahtar
        {"yuzey": {"ra": 1.6}},  # bilinmeyen grup
    ],
    ids=["bilinmeyen-anahtar", "bilinmeyen-grup"],
)
def test_kurallari_oku_bilinmeyen(tmp_path, icerik):
    yol = kural_dosyasi_yaz(tmp_path / "dfm-kurallari.json", icerik)
    with pytest.raises(CamError):
        kurallari_oku(yol)


# ---------------------------------------------------------------- K12 bağımlılık (OCCT'siz)

IZINLI = ("cam.model", "cam.features", "cam.offset", "cam.sim.raymesh", "geometry.part", "malzeme.model")


def _proje_importlari(yol: Path) -> list[str]:
    """Dosyadaki 3D-CORE paketlerinden yapılan importlar (stdlib / üçüncü taraf hariç)."""
    agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
    adlar: list[str] = []
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            adlar += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            assert n.level == 0, "göreli import yerine mutlak import beklenir"
            if n.module:
                adlar.append(n.module)
    return [a for a in adlar if (KOK / a.split(".")[0] / "__init__.py").is_file()]


def _izinli(ad: str) -> bool:
    return any(ad == m or ad.startswith(m + ".") for m in IZINLI)


def test_bagimlilik():
    ihlal = [a for a in _proje_importlari(KOK / "atolye" / "dfm.py") if not _izinli(a)]
    assert ihlal == []


def test_bagimlilik_tarayici(tmp_path):
    p = tmp_path / "x.py"
    p.write_text(
        "import numpy\nimport cam.model\nfrom cam.lathe import prepare\nfrom geometry.part import Part\n"
    )
    assert _proje_importlari(p) == ["cam.model", "cam.lathe", "geometry.part"]
    assert [a for a in _proje_importlari(p) if not _izinli(a)] == ["cam.lathe"]


# ---------------------------------------------------------------- OCCT'li parçalar

occt = pytest.mark.occt


def _bd():
    return pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')


def _geo():
    _bd()
    from geometry import features

    return features


def tek_kati(shape):
    from geometry.part import Part

    solids = list(shape.solids())
    assert len(solids) == 1, "test geometrisi tek katı olmalı"
    return Part(solids[0])


def k1_parca(r: float, derinlik: float = 10.0, yukseklik: float = 20.0):
    g = _geo()
    return g.pocket(g.block(60, 50, yukseklik), 30, 25, 40, 30, derinlik, r=r)


K1_LIB = (freze(1, 6.0, 25.0), freze(2, 10.0, 30.0))


# ---------------------------------------------------------------- K1


@occt
def test_ic_kose():
    lib = kutuphane(*K1_LIB)  # uygun frezeler (boy ≥ 10): Ø6, Ø10 → R_min = 3

    r = denetle(k1_parca(2.0), lib)
    rapor_gecerli(r)
    b = tek(r, "ic_kose", "hata")
    assert b.olculen == pytest.approx(2.0, abs=TOL)
    assert b.sinir == pytest.approx(3.0, abs=TOL)
    assert re.search(r"R\s*≥\s*3(?![\d.,]*[1-9])", b.oneri), b.oneri
    assert b.yuzler  # cep yüzlerine bağlı

    r = denetle(k1_parca(3.2), lib)
    rapor_gecerli(r)
    assert bul(r, "ic_kose", "hata") == []
    b = tek(r, "ic_kose", "uyari")
    assert b.olculen == pytest.approx(3.2, abs=TOL)
    assert b.sinir == pytest.approx(1.1 * 3.0, abs=TOL)

    r = denetle(k1_parca(4.0), lib)
    rapor_gecerli(r)
    assert bul(r, "ic_kose") == []

    r = denetle(k1_parca(0.0), lib)
    rapor_gecerli(r)
    b = tek(r, "ic_kose", "hata")
    assert b.olculen == pytest.approx(0.0, abs=TOL)
    assert "EDM" in b.mesaj or "EDM" in b.oneri


# ---------------------------------------------------------------- K2


@occt
def test_boy():
    # aynı cep 30 derin; Ø6 boy 25 < 30
    r = denetle(k1_parca(4.0, derinlik=30.0, yukseklik=40.0), kutuphane(freze(1, 6.0, 25.0)))
    rapor_gecerli(r)
    hatalar = [b for b in r.bulgular if b.derece == "hata" and "boyu yeten freze yok" in b.mesaj]
    assert hatalar, r.bulgular
    assert hatalar[0].tur in ("ic_kose", "derin_cep")


# ---------------------------------------------------------------- K3


def yarik(derinlik: float):
    # 8 genişlik (y), 40 boy (x), uçları tam yarıçaplı yarık; blok derinlikten 10 yüksek
    g = _geo()
    return g.pocket(g.block(60, 40, derinlik + 10), 30, 20, 40, 8, derinlik, r=4.0)


@occt
def test_derin_cep():
    r = denetle(yarik(40.0), kutuphane(freze(1, 8.0, 45.0)))
    rapor_gecerli(r)
    assert bul(r, "derin_cep", "hata") == []
    b = tek(r, "derin_cep", "uyari")
    assert b.olculen == pytest.approx(5.0, abs=TOL)  # λ = 40 / 8
    assert b.sinir == pytest.approx(4.0, abs=TOL)

    r = denetle(yarik(70.0), kutuphane(freze(1, 8.0, 75.0)))
    rapor_gecerli(r)
    b = tek(r, "derin_cep", "hata")
    assert b.olculen == pytest.approx(8.75, abs=TOL)  # λ = 70 / 8
    assert b.sinir == pytest.approx(8.0, abs=TOL)


@occt
def test_derin_cep_genis_sorunsuz():
    # K1 cebi (w = 30, h = 10), Ø10: λ = 1 → derin cep bulgusu yok
    r = denetle(k1_parca(5.0), kutuphane(*K1_LIB))
    assert bul(r, "derin_cep") == []


# ---------------------------------------------------------------- K4


def delikli(d: float, derinlik: float | None, yukseklik: float):
    g = _geo()
    return g.hole(g.block(30, 30, yukseklik), 15, 15, d, depth=derinlik)


@occt
def test_delik():
    lib = kutuphane(matkap(1, 5.0), freze(2, 4.0, 20.0))

    r = denetle(delikli(5.0, 60.0, 80.0), lib)
    rapor_gecerli(r)
    assert bul(r, "delik", "hata") == []
    b = tek(r, "delik", "uyari")
    assert b.olculen == pytest.approx(12.0, abs=TOL)  # h/d = 60/5
    assert b.sinir == pytest.approx(10.0, abs=TOL)

    r = denetle(delikli(5.0, 110.0, 120.0), lib)
    rapor_gecerli(r)
    b = tek(r, "delik", "hata")
    assert b.olculen == pytest.approx(22.0, abs=TOL)  # h/d = 110/5
    assert b.sinir == pytest.approx(20.0, abs=TOL)

    # Ø5.3 boydan delik, yalnız Ø5 matkap: bilgi (frezeyle helisel); Ø4 freze daha küçük → hata yok
    r = denetle(delikli(5.3, None, 10.0), lib)
    rapor_gecerli(r)
    assert bul(r, "delik", "hata") == [] and bul(r, "delik", "uyari") == []
    assert bul(r, "delik", "bilgi")
    # Ø5.3 matkap eklenince bilgi düşer (boydan delik: düz dip bilgisi yok)
    r = denetle(delikli(5.3, None, 10.0), kutuphane(matkap(1, 5.0), freze(2, 4.0, 20.0), matkap(3, 5.3)))
    assert bul(r, "delik") == []


@occt
def test_delik_frezeden_kucuk():
    # Ø3 delik; matkap yok, en küçük freze Ø4 → hata
    r = denetle(delikli(3.0, None, 10.0), kutuphane(freze(1, 4.0, 20.0)))
    rapor_gecerli(r)
    assert bul(r, "delik", "hata")


@occt
def test_delik_kor_duz_dip_bilgi():
    # Ø5 × 10 kör, düz dip (konik dip yok) → bilgi; oran ve matkap sorunsuz
    r = denetle(delikli(5.0, 10.0, 20.0), kutuphane(matkap(1, 5.0), freze(2, 4.0, 20.0)))
    rapor_gecerli(r)
    assert bul(r, "delik", "hata") == [] and bul(r, "delik", "uyari") == []
    assert bul(r, "delik", "bilgi")


# ---------------------------------------------------------------- K5


def t_oluk():
    """Alttan kesik T-oluk: üstten dar boyun (x ∈ [45, 55], z ∈ [6, 20]), alttan açık geniş kanal
    (x ∈ [35, 65], z ∈ [0, 6]), ikisi de y ∈ [10, 50]. Geniş kanalın tavanı z = 6'da, normali −Z."""
    bd = _bd()
    g = _geo()
    s = g.block(100, 60, 20).shape
    s = s - bd.Pos(45, 10, 6) * bd.Box(10, 40, 15, align=bd.Align.MIN)
    s = s - bd.Pos(35, 10, -1) * bd.Box(30, 40, 7, align=bd.Align.MIN)
    return tek_kati(s)


def tavan_yuzleri(part) -> set[int]:
    out = {f.index for f in part.planar_faces() if f.normal[2] < -0.999 and abs(f.origin[2] - 6.0) < 1e-6}
    assert len(out) == 2
    return out


ERISIM_LIB = (freze(1, 6.0, 25.0), freze(2, 10.0, 30.0))


@occt
def test_erisim():
    part = t_oluk()
    tavan = tavan_yuzleri(part)

    r = denetle(part, kutuphane(*ERISIM_LIB), yonler=((0, 0, 1),))
    rapor_gecerli(r)
    hatali = {i for b in bul(r, "erisilemez", "hata") for i in b.yuzler}
    assert tavan <= hatali

    r = denetle(part, kutuphane(*ERISIM_LIB), yonler=((0, 0, 1), (0, 0, -1)))
    rapor_gecerli(r)
    hepsi = {i for b in bul(r, "erisilemez") for i in b.yuzler}
    assert not (tavan & hepsi)


@occt
def test_erisim_duz_blok():
    g = _geo()
    r = denetle(g.block(100, 60, 20), kutuphane(*ERISIM_LIB), yonler=((0, 0, 1), (0, 0, -1)))
    rapor_gecerli(r)
    assert bul(r, "erisilemez") == []


# ---------------------------------------------------------------- K6


def duvarli(t: float, H: float):
    """40 × 30 × 5 taban üstünde y ∈ [15, 15 + t], x ∈ [0, 40], yükseklik H dik duvar."""
    bd = _bd()
    g = _geo()
    s = g.block(40, 30, 5).shape + bd.Pos(0, 15, 5) * bd.Box(40, t, H, align=bd.Align.MIN)
    return tek_kati(s)


def kama():
    """XY'de (0, 0), (40, 0), (40, 20) üçgeni, 30 boy: yüzler arası açı ≈ 26.6° > 10°."""
    bd = _bd()
    return tek_kati(bd.extrude(bd.Polygon((0, 0), (40, 0), (40, 20), align=None), amount=30))


DUVAR_LIB = (freze(1, 6.0, 50.0),)


@occt
def test_ince_duvar():
    r = denetle(duvarli(0.6, 8.0), kutuphane(*DUVAR_LIB), malzeme_grubu="aluminyum")
    rapor_gecerli(r)
    b = tek(r, "ince_duvar", "hata")
    assert b.olculen == pytest.approx(0.6, abs=TOL)
    assert b.sinir == pytest.approx(0.8, abs=TOL)
    assert b.kural == "ince_duvar.aluminyum"

    r = denetle(duvarli(2.0, 40.0), kutuphane(*DUVAR_LIB), malzeme_grubu="aluminyum")
    rapor_gecerli(r)
    assert bul(r, "ince_duvar", "hata") == []
    b = tek(r, "ince_duvar", "uyari")
    assert b.olculen == pytest.approx(20.0, abs=TOL)  # H / t = 40 / 2
    assert b.sinir == pytest.approx(15.0, abs=TOL)

    r = denetle(kama(), kutuphane(*DUVAR_LIB), malzeme_grubu="aluminyum")
    rapor_gecerli(r)
    assert bul(r, "ince_duvar") == []


@occt
def test_ince_duvar_malzeme_grubu():
    part = duvarli(1.0, 8.0)  # 1 mm: alüminyum (0.8) ve çelik (0.5) için yeterli, plastik (1.5) için ince
    for grup in ("aluminyum", "celik"):
        assert bul(denetle(part, kutuphane(*DUVAR_LIB), malzeme_grubu=grup), "ince_duvar", "hata") == []
    b = tek(denetle(part, kutuphane(*DUVAR_LIB), malzeme_grubu="plastik"), "ince_duvar", "hata")
    assert b.sinir == pytest.approx(1.5, abs=TOL)
    # malzeme grubu yok → en sıkı sınır (1.5)
    b = tek(denetle(part, kutuphane(*DUVAR_LIB)), "ince_duvar", "hata")
    assert b.olculen == pytest.approx(1.0, abs=TOL)
    assert b.sinir == pytest.approx(1.5, abs=TOL)


# ---------------------------------------------------------------- K7


def kanalli_mil():
    """Ø40 × 60 mil (eksen Z), z ∈ [29, 31]'de 2 mm genişlik, Ø34 tabanlı kanal."""
    bd = _bd()
    g = _geo()
    orta = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    halka = bd.Pos(0, 0, 29) * (bd.Cylinder(25, 2, align=orta) - bd.Cylinder(17, 2, align=orta))
    return tek_kati(g.cylinder(20, 60).shape - halka)


@occt
def test_torna():
    r = denetle(kanalli_mil(), kutuphane(tornalama_ucu(1), kanal_ucu(2, 3.0)))
    rapor_gecerli(r)
    b = tek(r, "torna_kanal", "hata")
    assert b.olculen == pytest.approx(2.0, abs=TOL)
    assert b.sinir == pytest.approx(3.0, abs=TOL)

    r = denetle(kanalli_mil(), kutuphane(tornalama_ucu(1), kanal_ucu(2, 3.0), kanal_ucu(3, 2.0)))
    assert bul(r, "torna_kanal") == []


# ---------------------------------------------------------------- K8


@occt
def test_kural_ezme(tmp_path):
    part = duvarli(0.6, 8.0)
    lib = kutuphane(*DUVAR_LIB)

    k = kurallari_oku(kural_dosyasi_yaz(tmp_path / "a.json", {"ince_duvar": {"aluminyum": 0.5}}))
    r = denetle(part, lib, malzeme_grubu="aluminyum", kurallar=k)
    rapor_gecerli(r)
    assert bul(r, "ince_duvar", "hata") == []  # 0.6 > 0.5

    k = kurallari_oku(kural_dosyasi_yaz(tmp_path / "b.json", {"ince_duvar": {"aluminyum": 0.7}}))
    r = denetle(part, lib, malzeme_grubu="aluminyum", kurallar=k)
    b = tek(r, "ince_duvar", "hata")
    assert b.sinir == pytest.approx(0.7, abs=TOL)
    assert b.kural == "ince_duvar.aluminyum (yerel)"

    with pytest.raises(CamError):
        kurallari_oku(kural_dosyasi_yaz(tmp_path / "c.json", {"ince_duvar": {"alminyum": 0.5}}))


# ---------------------------------------------------------------- K9


@occt
def test_belirlenimci():
    part = t_oluk()
    lib = kutuphane(*ERISIM_LIB, matkap(3, 5.0))
    r1 = denetle(part, lib)
    r2 = denetle(part, lib)
    assert r1.bulgular  # T-oluk + yalnız +Z: en az erişim bulgusu var
    assert r1.bulgular == r2.bulgular
