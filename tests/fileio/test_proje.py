"""SPEC 37 — fileio/proje.py testleri: tek proje dosyası `.3dc`, kanonik JSON, geri al / yinele (K1–K8).

Testler yalnız specs/37-proje-kabuk.md'deki teori ve arayüzden yazıldı; fileio/proje.py gövdesi okunmadı.
FastAPI, OCCT ve Node gerektirmez.

Varsayımlar (SPEC'in açık bıraktığı yerler, en zayıf okuma seçildi):
- "Tanınmayan bölüm" hangi ekranın sahiplendiğine bağlıdır; `fileio` ekranları bilmez. Burada yalnız böyle bir
  bölümün yüklenip yeniden kaydedilince bayt bayt korunduğu denenir; `uyari`'sı kabuğun işidir (K5).
- Uyarılar SPEC 24 `Kontrol` biçimindedir: `durum == "uyari"` ve ilgili girdi adı uyarının metninde geçer.
- Kaydın yarıda kesildiği (K6) hata türü belirtilmemiştir: `OSError` ya da `ProjeError` yeter (yutulmamalı).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import struct
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from fileio.proje import (
    GECMIS_SINIRI,
    SEMA,
    UZANTI,
    Gecmis,
    Onbellek,
    Proje,
    ProjeError,
    ac,
    bos_proje,
    geri_al,
    kanonik,
    kaydet,
    ozet,
    uygula,
    yinele,
)

# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _kanonik_bayt(b) -> bytes:
    """SPEC'teki kanonik tanımın bağımsız kopyası (karşılaştırma için)."""
    return json.dumps(b, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def _gecmis_belge(g: Gecmis) -> dict:
    return {"kayitlar": [dict(k) for k in g.kayitlar], "konum": g.konum}


def _durum(p: Proje) -> bytes:
    """Projenin ad + bölümler + geçmiş kanonik baytları (önbellek ve uyarılar hariç)."""
    return _kanonik_bayt(
        {"ad": p.ad, "bolumler": {k: v for k, v in p.bolumler.items()}, "gecmis": _gecmis_belge(p.gecmis)}
    )


def _bolumler(p: Proje) -> bytes:
    return _kanonik_bayt({k: v for k, v in p.bolumler.items()})


def _zip_oku(yol: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(yol) as z:
        return {ad: z.read(ad) for ad in z.namelist()}


def _zip_yaz(yol: Path, girdiler: dict[str, bytes]) -> None:
    """Testin elle kurduğu (bozuk ya da değiştirilmiş) zip."""
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_DEFLATED) as z:
        for ad, veri in girdiler.items():
            z.writestr(zipfile.ZipInfo(ad, date_time=(1980, 1, 1, 0, 0, 0)), veri, zipfile.ZIP_DEFLATED)


def _bildirim(girdiler: dict[str, bytes]) -> dict:
    return json.loads(girdiler["proje.json"])


def _bildirim_yaz(girdiler: dict[str, bytes], b: dict) -> None:
    girdiler["proje.json"] = _kanonik_bayt(b)


ANAHTAR = "torna_isleri.kademeli_mil.sim"
VERI = bytes(range(256)) * 16


def _ornek_proje() -> Proje:
    """Bölümler, önbellek ve 5 kayıtlı geçmişi (konum 3) olan proje."""
    p = bos_proje("yatak grubu")
    for i, L in enumerate([20.0, 9.5, 0.1 + 0.2, 1e-300, -0.0]):
        p = uygula(
            p,
            f"L {L}",
            "torna",
            {
                "torna_isleri": {"sema": 1, "kademeli_mil": {"parametreler": {"L": L, "D": 30.0}}},
                "isler": {"sema": 1, "flans": {"parametreler": {"paso": float(i + 1)}, "ad": "flanş ışık"}},
            },
        )
    p = geri_al(geri_al(p))
    girdi = ozet({"torna_isleri": dict(p.bolumler)["torna_isleri"]})
    return replace(p, onbellek={ANAHTAR: Onbellek(girdi_ozeti=girdi, veri=VERI)})


def _kayitli(tmp_path: Path) -> Path:
    """Örnek proje kaydedilmiş dosya. Fikstür değil: NotImplementedError test gövdesinde düşsün (conftest)."""
    yol = tmp_path / "ornek.3dc"
    kaydet(_ornek_proje(), yol)
    return yol


def _klasor(yol: Path) -> list[str]:
    return sorted(os.listdir(yol))


# ---------------------------------------------------------------------------
# Sabitler, kanonik JSON, özet
# ---------------------------------------------------------------------------


def test_constants():
    assert SEMA == 1
    assert UZANTI == ".3dc"
    assert GECMIS_SINIRI == 200
    assert issubclass(ProjeError, ValueError)


def test_canonical_bytes():
    b = {"b": 1, "a": "şğüöçıİ", "c": [1.5, {"z": None, "y": True}]}
    assert kanonik(b) == '{"a":"şğüöçıİ","b":1,"c":[1.5,{"y":true,"z":null}]}'.encode()
    assert kanonik(b) == _kanonik_bayt(b)
    assert ozet(b) == _sha(_kanonik_bayt(b))
    # anahtar sırası kanonik baytı değiştirmez
    assert kanonik({"y": {"q": 2, "p": 1}, "x": 0}) == kanonik({"x": 0, "y": {"p": 1, "q": 2}})


@pytest.mark.parametrize("kotu", [math.nan, math.inf, -math.inf])
def test_canonical_rejects_nan_inf(kotu):
    with pytest.raises(ProjeError):
        kanonik({"sema": 1, "x": [1.0, {"y": kotu}]})
    with pytest.raises(ProjeError):
        ozet({"x": kotu})


def test_empty_project():
    p = bos_proje("deneme")
    assert p.ad == "deneme"
    assert set(p.bolumler) == {"kabuk"}
    kabuk = dict(p.bolumler)["kabuk"]
    assert kabuk["sema"] == 1
    assert "aktif_ekran" in kabuk
    assert p.gecmis.konum == 0 and len(p.gecmis.kayitlar) == 0
    assert len(p.onbellek) == 0


# ---------------------------------------------------------------------------
# K1 Dosya gidiş-dönüşü
# ---------------------------------------------------------------------------


def test_round_trip(tmp_path):
    ornek = _ornek_proje()
    assert ornek.gecmis.konum == 3 and len(ornek.gecmis.kayitlar) == 5
    yol = tmp_path / "gidis.3dc"
    kaydet(ornek, yol)
    q = ac(yol)

    assert q.ad == ornek.ad
    assert set(q.bolumler) == set(ornek.bolumler)
    for ad in ornek.bolumler:
        assert kanonik(dict(q.bolumler)[ad]) == kanonik(dict(ornek.bolumler)[ad])
    assert set(q.onbellek) == {ANAHTAR}
    assert q.onbellek[ANAHTAR].veri == VERI
    assert q.onbellek[ANAHTAR].girdi_ozeti == ornek.onbellek[ANAHTAR].girdi_ozeti
    assert q.gecmis.konum == 3
    assert _kanonik_bayt(_gecmis_belge(q.gecmis)) == _kanonik_bayt(_gecmis_belge(ornek.gecmis))
    assert _durum(q) == _durum(ornek)
    assert q.uyarilar == ()


def test_round_trip_floats_bit_exact(tmp_path):
    degerler = [0.1 + 0.2, 1e-300, -0.0, 5e-324, 1.7976931348623157e308, 1 / 3, 123456789.123456789]
    p = uygula(bos_proje("sayilar"), "s", "freze", {"isler": {"sema": 1, "v": degerler}})
    yol = tmp_path / "sayilar.3dc"
    kaydet(p, yol)
    v = dict(ac(yol).bolumler)["isler"]["v"]
    assert [struct.pack("<d", x) for x in v] == [struct.pack("<d", x) for x in degerler]
    assert math.copysign(1.0, v[2]) == -1.0


# ---------------------------------------------------------------------------
# K2 Belirlenimci dosya
# ---------------------------------------------------------------------------


def test_deterministic_bytes(tmp_path):
    ornek = _ornek_proje()
    y1, y2, y3 = tmp_path / "a.3dc", tmp_path / "b.3dc", tmp_path / "c.3dc"
    kaydet(ornek, y1)
    kaydet(ornek, y2)
    assert y1.read_bytes() == y2.read_bytes()

    # Aynı proje, bölüm sözlükleri ters anahtar sırasıyla kurulmuş.
    def ters(d):
        return {k: ters(d[k]) for k in reversed(list(d))} if isinstance(d, dict) else d

    tersi = replace(
        ornek, bolumler={k: ters(dict(ornek.bolumler)[k]) for k in reversed(list(ornek.bolumler))}
    )
    kaydet(tersi, y3)
    assert y3.read_bytes() == y1.read_bytes()

    # Açılıp yeniden kaydedilen dosya da aynı.
    y4 = tmp_path / "d.3dc"
    kaydet(ac(y1), y4)
    assert y4.read_bytes() == y1.read_bytes()

    with zipfile.ZipFile(y1) as z:
        bilgiler = z.infolist()
    adlar = [i.filename for i in bilgiler]
    assert adlar == sorted(adlar)
    assert all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in bilgiler)
    assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in bilgiler)
    assert len({i.external_attr for i in bilgiler}) == 1


# ---------------------------------------------------------------------------
# K3 Biçim
# ---------------------------------------------------------------------------


def test_layout(tmp_path):
    ornek = _ornek_proje()
    kayitli = _kayitli(tmp_path)
    assert zipfile.is_zipfile(kayitli)
    g = _zip_oku(kayitli)
    b = _bildirim(g)

    assert b["sema"] == 1
    assert b["uygulama"] == "3D-CORE"
    assert b["ad"] == ornek.ad

    beklenen = (
        {"proje.json", "gecmis.json"}
        | {f"bolumler/{ad}.json" for ad in b["bolumler"]}
        | {f"onbellek/{k}.bin" for k in b["onbellek"]}
    )
    assert set(g) == beklenen
    assert set(b["bolumler"]) == set(ornek.bolumler)
    assert set(b["onbellek"]) == {ANAHTAR}

    for ad, bilgi in b["bolumler"].items():
        veri = g[f"bolumler/{ad}.json"]
        assert veri == _kanonik_bayt(json.loads(veri)), ad  # kanonik JSON
        assert bilgi["ozet"] == _sha(veri)
        assert bilgi["sema"] == dict(ornek.bolumler)[ad]["sema"]
        assert json.loads(veri) == json.loads(kanonik(dict(ornek.bolumler)[ad]))

    o = b["onbellek"][ANAHTAR]
    assert g[f"onbellek/{ANAHTAR}.bin"] == VERI
    assert o["ozet"] == _sha(VERI)
    assert o["boyut"] == len(VERI)
    assert o["girdi_ozeti"] == ornek.onbellek[ANAHTAR].girdi_ozeti

    gv = g["gecmis.json"]
    assert gv == _kanonik_bayt(json.loads(gv))
    assert b["gecmis"]["ozet"] == _sha(gv)
    assert b["gecmis"]["konum"] == 3
    assert b["gecmis"]["sayi"] == 5
    assert json.loads(gv)["konum"] == 3
    assert len(json.loads(gv)["kayitlar"]) == 5

    # Bildirimde saat yok.
    metin = g["proje.json"].decode("utf-8")
    assert "1980" not in metin and "zaman" not in metin and "tarih" not in metin


def test_empty_history_layout(tmp_path):
    yol = tmp_path / "bos.3dc"
    kaydet(bos_proje("bos"), yol)
    g = _zip_oku(yol)
    assert set(g) == {"proje.json", "gecmis.json", "bolumler/kabuk.json"}
    b = _bildirim(g)
    assert b["gecmis"]["konum"] == 0 and b["gecmis"]["sayi"] == 0
    assert b["onbellek"] == {}
    q = ac(yol)
    assert _durum(q) == _durum(bos_proje("bos"))


def test_save_requires_extension(tmp_path):
    ornek = _ornek_proje()
    for ad in ["proje.json", "proje", "proje.3dc.zip"]:
        with pytest.raises(ProjeError):
            kaydet(ornek, tmp_path / ad)
    assert _klasor(tmp_path) == []


def test_save_leaves_no_tmp(tmp_path):
    ornek = _ornek_proje()
    kaydet(ornek, tmp_path / "x.3dc")
    kaydet(ornek, tmp_path / "x.3dc")
    assert _klasor(tmp_path) == ["x.3dc"]


def test_save_accepts_str_path(tmp_path):
    ornek = _ornek_proje()
    kaydet(ornek, str(tmp_path / "s.3dc"))
    assert _durum(ac(str(tmp_path / "s.3dc"))) == _durum(ornek)


# ---------------------------------------------------------------------------
# K4 Bozuk dosya
# ---------------------------------------------------------------------------


def _hata_mesaji(yol: Path) -> str:
    with pytest.raises(ProjeError) as e:
        ac(yol)
    return str(e.value)


def test_corrupt_not_zip(tmp_path):
    yol = tmp_path / "metin.3dc"
    yol.write_bytes(b"bu bir zip degil\n")
    _hata_mesaji(yol)


def test_corrupt_missing_file(tmp_path):
    with pytest.raises((ProjeError, FileNotFoundError)):
        ac(tmp_path / "yok.3dc")


def test_corrupt_no_manifest(tmp_path):
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    del g["proje.json"]
    _zip_yaz(kayitli, g)
    assert "proje.json" in _hata_mesaji(kayitli)


def test_corrupt_manifest_not_json(tmp_path):
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    g["proje.json"] = b"{sema: 1"
    _zip_yaz(kayitli, g)
    assert "proje.json" in _hata_mesaji(kayitli)


def test_corrupt_future_schema(tmp_path):
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    b = _bildirim(g)
    b["sema"] = 2
    _bildirim_yaz(g, b)
    _zip_yaz(kayitli, g)
    assert "proje.json" in _hata_mesaji(kayitli)


def test_corrupt_section_digest(tmp_path):
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    g["bolumler/torna_isleri.json"] = _kanonik_bayt({"sema": 1, "kademeli_mil": {"parametreler": {"L": 1.0}}})
    _zip_yaz(kayitli, g)
    assert "torna_isleri" in _hata_mesaji(kayitli)


def test_corrupt_section_manifest_digest(tmp_path):
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    b = _bildirim(g)
    b["bolumler"]["isler"]["ozet"] = "0" * 64
    _bildirim_yaz(g, b)
    _zip_yaz(kayitli, g)
    assert "isler" in _hata_mesaji(kayitli)


@pytest.mark.parametrize(
    "icerik",
    [b"{bozuk", b'{"sema": 1, "x": 2}', '{"sema":1,"x":"\udcff"}'.encode("utf-8", "surrogatepass"), b"NaN"],
    ids=["gecersiz_json", "kanonik_degil", "gecersiz_utf8", "nan"],
)
def test_corrupt_section_json(tmp_path, icerik):
    """Bölüm geçerli JSON değil ya da kanonik değil; bildirimdeki özet içeriğe uydurulmuş."""
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    g["bolumler/isler.json"] = icerik
    b = _bildirim(g)
    b["bolumler"]["isler"]["ozet"] = _sha(icerik)
    _bildirim_yaz(g, b)
    _zip_yaz(kayitli, g)
    assert "isler" in _hata_mesaji(kayitli)


def test_corrupt_section_missing_from_zip(tmp_path):
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    del g["bolumler/isler.json"]
    _zip_yaz(kayitli, g)
    assert "isler" in _hata_mesaji(kayitli)


@pytest.mark.parametrize(
    "ad", ["../x.json", "/x.json", "bolumler/../x.json", "notlar.txt", "bolumler/Buyuk.json"]
)
def test_corrupt_entry_name(tmp_path, ad):
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    g[ad] = b"{}"
    _zip_yaz(kayitli, g)
    with zipfile.ZipFile(kayitli) as z:
        assert ad in z.namelist()  # zip gerçekten bu adı taşıyor
    mesaj = _hata_mesaji(kayitli)
    assert ad.rsplit("/", 1)[-1].split(".")[0] in mesaj


def _merkezi_boyut_yamala(yol: Path, ad: str, boyut: int) -> None:
    """Merkezi dizindeki `ad` girdisinin açılmış boyut alanını değiştirir (bildirilen boyut)."""
    veri = bytearray(yol.read_bytes())
    i = 0
    bulundu = False
    while True:
        i = veri.find(b"PK\x01\x02", i)
        if i < 0:
            break
        n = struct.unpack_from("<H", veri, i + 28)[0]
        if bytes(veri[i + 46 : i + 46 + n]).decode() == ad:
            struct.pack_into("<I", veri, i + 24, boyut)
            bulundu = True
        i += 4
    assert bulundu
    yol.write_bytes(bytes(veri))


def test_corrupt_declared_size_over_1gib(tmp_path):
    kayitli = _kayitli(tmp_path)
    ad = f"onbellek/{ANAHTAR}.bin"
    _merkezi_boyut_yamala(kayitli, ad, 0xF0000000)  # ~3.75 GiB bildirilir
    with zipfile.ZipFile(kayitli) as z:
        assert z.getinfo(ad).file_size > 2**30
    assert ANAHTAR in _hata_mesaji(kayitli)


def test_corrupt_compression_ratio(tmp_path):
    """Gerçekten 200'den fazla sıkışan girdi (sıfırlar); bildirim özeti doğru, tek kusur oran."""
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    sifir = bytes(4 * 2**20)
    g[f"onbellek/{ANAHTAR}.bin"] = sifir
    b = _bildirim(g)
    b["onbellek"][ANAHTAR]["ozet"] = _sha(sifir)
    b["onbellek"][ANAHTAR]["boyut"] = len(sifir)
    _bildirim_yaz(g, b)
    _zip_yaz(kayitli, g)
    with zipfile.ZipFile(kayitli) as z:
        i = z.getinfo(f"onbellek/{ANAHTAR}.bin")
        assert i.file_size / i.compress_size > 200
    assert ANAHTAR in _hata_mesaji(kayitli)


def test_corrupt_does_not_change_file(tmp_path):
    """Açma denetimi dosyaya dokunmaz."""
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    b = _bildirim(g)
    b["sema"] = 2
    _bildirim_yaz(g, b)
    _zip_yaz(kayitli, g)
    once = kayitli.read_bytes()
    _hata_mesaji(kayitli)
    assert kayitli.read_bytes() == once


@pytest.mark.parametrize("kotu", [math.nan, math.inf])
def test_corrupt_nan_not_saved(tmp_path, kotu):
    p = replace(
        bos_proje("nan"),
        bolumler={"kabuk": {"sema": 1, "aktif_ekran": "freze"}, "isler": {"sema": 1, "x": kotu}},
    )
    yol = tmp_path / "nan.3dc"
    with pytest.raises(ProjeError):
        kaydet(p, yol)
    assert _klasor(tmp_path) == []


def test_corrupt_nan_keeps_existing_file(tmp_path):
    ornek = _ornek_proje()
    kayitli = _kayitli(tmp_path)
    once = kayitli.read_bytes()
    bolumler = dict(ornek.bolumler)
    bolumler["isler"] = {"sema": 1, "x": math.nan}
    with pytest.raises(ProjeError):
        kaydet(replace(ornek, bolumler=bolumler), kayitli)
    assert kayitli.read_bytes() == once
    assert _klasor(kayitli.parent) == [kayitli.name]


@pytest.mark.parametrize(
    "kur",
    [
        lambda: Proje(ad="", bolumler={"kabuk": {"sema": 1, "aktif_ekran": "freze"}}),
        lambda: Proje(ad="x", bolumler={"Kötü-Ad": {"sema": 1}}),
        lambda: Proje(ad="x", bolumler={"a" * 41: {"sema": 1}}),
        lambda: Proje(ad="x", bolumler={"isler": {"x": 1}}),
        lambda: Proje(ad="x", bolumler={"isler": {"sema": "1"}}),
        lambda: Proje(ad="x", bolumler={"isler": {"sema": 1.0}}),
        lambda: Proje(ad="x", bolumler={"isler": {"sema": 0}}),
        lambda: Proje(
            ad="x", bolumler={"isler": {"sema": 1}}, onbellek={"Kötü/anahtar": Onbellek("0" * 64, b"x")}
        ),
        lambda: Proje(ad="x", bolumler={"isler": {"sema": 1}}, onbellek={"a" * 81: Onbellek("0" * 64, b"x")}),
    ],
    ids=[
        "bos_ad",
        "bolum_adi",
        "bolum_adi_uzun",
        "sema_yok",
        "sema_metin",
        "sema_float",
        "sema_sifir",
        "anahtar",
        "anahtar_uzun",
    ],
)
def test_invalid_project_not_saved(tmp_path, kur):
    """Geçersiz proje (kurulurken ya da kaydedilirken) ProjeError; diske hiçbir şey yazılmaz."""
    with pytest.raises(ProjeError):
        kaydet(kur(), tmp_path / "gecersiz.3dc")
    assert _klasor(tmp_path) == []


# ---------------------------------------------------------------------------
# K5 Hoşgörü
# ---------------------------------------------------------------------------


def _uyarilar_metni(p: Proje) -> list[str]:
    return [json.dumps(u, ensure_ascii=False) for u in p.uyarilar if u.get("durum") == "uyari"]


def test_lenient_cache_digest(tmp_path):
    ornek = _ornek_proje()
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    g[f"onbellek/{ANAHTAR}.bin"] = b"bozulmus onbellek"
    _zip_yaz(kayitli, g)
    q = ac(kayitli)
    assert ANAHTAR not in q.onbellek
    assert _durum(q) == _durum(ornek)
    assert any(ANAHTAR in m for m in _uyarilar_metni(q))


def test_lenient_extra_entry(tmp_path):
    ornek = _ornek_proje()
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    g["onbellek/fazla_girdi.bin"] = b"bildirimde yok"
    _zip_yaz(kayitli, g)
    q = ac(kayitli)
    assert "fazla_girdi" not in q.onbellek
    assert _durum(q) == _durum(ornek)
    assert any("fazla_girdi" in m for m in _uyarilar_metni(q))

    yeni = tmp_path / "yeniden.3dc"
    kaydet(q, yeni)
    assert "onbellek/fazla_girdi.bin" not in _zip_oku(yeni)


def test_lenient_unknown_section(tmp_path):
    """Hiçbir ekranın bilmediği bölüm olduğu gibi yüklenir ve yeniden kaydedilince bayt bayt korunur."""
    ornek = _ornek_proje()
    bolumler = dict(ornek.bolumler)
    bolumler["gelecek_ekran"] = {"sema": 7, "ağaç": {"z": [1, 2.5, "ü"], "a": None}}
    p = replace(ornek, bolumler=bolumler)
    y1 = tmp_path / "bilinmeyen.3dc"
    kaydet(p, y1)
    q = ac(y1)
    assert kanonik(dict(q.bolumler)["gelecek_ekran"]) == kanonik(bolumler["gelecek_ekran"])
    y2 = tmp_path / "bilinmeyen2.3dc"
    kaydet(q, y2)
    assert _zip_oku(y2)["bolumler/gelecek_ekran.json"] == _zip_oku(y1)["bolumler/gelecek_ekran.json"]
    assert y2.read_bytes() == y1.read_bytes()


def test_lenient_warnings_not_saved(tmp_path):
    kayitli = _kayitli(tmp_path)
    g = _zip_oku(kayitli)
    g[f"onbellek/{ANAHTAR}.bin"] = b"bozulmus"
    _zip_yaz(kayitli, g)
    q = ac(kayitli)
    assert q.uyarilar
    y = tmp_path / "temiz.3dc"
    kaydet(q, y)
    assert ac(y).uyarilar == ()


# ---------------------------------------------------------------------------
# K6 Atomik kayıt
# ---------------------------------------------------------------------------


def _kesici_compressobj(monkeypatch):
    """İkinci zip girdisinin verisi sıkıştırılırken yazımı keser (zipfile'ın kendi durumu tutarlı kalır)."""
    asil = zipfile.zlib.compressobj
    sayac = {"n": 0}

    class _Kesik:
        def __init__(self, ic):
            self.ic = ic

        def compress(self, veri):
            raise OSError("disk doldu (test)")

        def flush(self, *a):
            return self.ic.flush(*a)

    def kesici(*a, **k):
        sayac["n"] += 1
        ic = asil(*a, **k)
        return _Kesik(ic) if sayac["n"] >= 2 else ic

    monkeypatch.setattr(zipfile.zlib, "compressobj", kesici)


def _kesici_fsync(monkeypatch):
    def kesici(*a, **k):
        raise OSError("fsync başarısız (test)")

    monkeypatch.setattr(os, "fsync", kesici)


def _kesici_replace(monkeypatch):
    def kesici(*a, **k):
        raise OSError("replace başarısız (test)")

    monkeypatch.setattr(os, "replace", kesici)


@pytest.mark.parametrize(
    "kes", [_kesici_compressobj, _kesici_fsync, _kesici_replace], ids=["yazim", "fsync", "replace"]
)
def test_atomic_save(tmp_path, monkeypatch, kes):
    ornek = _ornek_proje()
    yol = tmp_path / "proje.3dc"
    kaydet(bos_proje("eski"), yol)
    once = yol.read_bytes()

    with monkeypatch.context() as m:
        kes(m)
        with pytest.raises((OSError, ProjeError)):
            kaydet(ornek, yol)

    assert yol.read_bytes() == once
    assert _klasor(tmp_path) == ["proje.3dc"]
    assert ac(yol).ad == "eski"


def test_atomic_save_new_file(tmp_path, monkeypatch):
    """Yeni dosya yazılırken kesilirse hiçbir şey kalmaz."""
    ornek = _ornek_proje()
    with monkeypatch.context() as m:
        _kesici_compressobj(m)
        with pytest.raises((OSError, ProjeError)):
            kaydet(ornek, tmp_path / "yeni.3dc")
    assert _klasor(tmp_path) == []


# ---------------------------------------------------------------------------
# K7 Geri al cebiri
# ---------------------------------------------------------------------------


class _Basvuru:
    """Bağımsız başvuru modeli: durum listesi + işaretçi (durumlar kanonik bayt olarak tutulur)."""

    def __init__(self, ilk: dict):
        self.durumlar = [dict(ilk)]
        self.kayitlar: list[tuple[str, str, dict]] = []
        self.konum = 0

    @property
    def guncel(self) -> dict:
        return self.durumlar[self.konum]

    def uygula(self, etiket: str, ekran: str, yeni: dict) -> bool:
        eski = self.guncel
        sonra = dict(eski)
        fark = {}
        for ad, belge in yeni.items():
            once_b = eski.get(ad)
            if (None if once_b is None else _kanonik_bayt(once_b)) == (
                None if belge is None else _kanonik_bayt(belge)
            ):
                continue
            fark[ad] = [once_b, belge]
            if belge is None:
                sonra.pop(ad, None)
            else:
                sonra[ad] = belge
        if not fark:
            return False
        del self.durumlar[self.konum + 1 :]
        del self.kayitlar[self.konum :]
        self.durumlar.append(sonra)
        self.kayitlar.append((etiket, ekran, fark))
        self.konum += 1
        if len(self.kayitlar) > GECMIS_SINIRI:
            del self.durumlar[0]
            del self.kayitlar[0]
            self.konum -= 1
        return True

    def geri_al(self) -> bool:
        if self.konum == 0:
            return False
        self.konum -= 1
        return True

    def yinele(self) -> bool:
        if self.konum == len(self.kayitlar):
            return False
        self.konum += 1
        return True


def _esit(p: Proje, r: _Basvuru) -> None:
    assert _bolumler(p) == _kanonik_bayt(r.guncel)
    assert p.gecmis.konum == r.konum
    assert len(p.gecmis.kayitlar) == len(r.kayitlar)
    for kayit, (etiket, ekran, fark) in zip(p.gecmis.kayitlar, r.kayitlar, strict=True):
        assert kayit["etiket"] == etiket
        assert kayit["ekran"] == ekran
        assert _kanonik_bayt(kayit["bolumler"]) == _kanonik_bayt(fark)


def _rastgele_belge(rng: random.Random) -> dict:
    return {"sema": 1, "L": rng.choice([9.0, 9.5, 20.0, 0.1 + 0.2]), "ad": rng.choice(["mil", "flanş"])}


def test_undo_algebra():
    rng = random.Random(37)
    p = bos_proje("cebir")
    r = _Basvuru(dict(p.bolumler))
    _esit(p, r)

    for adim in range(300):
        once = _durum(p)
        islem = rng.choices(["degistir", "geri_al", "yinele"], weights=[5, 3, 2])[0]
        if islem == "degistir":
            yeni = {}
            for ad in rng.sample(["isler", "torna_isleri", "montajlar"], rng.randint(1, 3)):
                yeni[ad] = None if rng.random() < 0.2 else _rastgele_belge(rng)
            etiket = f"adim {adim}"
            q = uygula(p, etiket, "torna", yeni)
            r.uygula(etiket, "torna", yeni)
        elif islem == "geri_al":
            if r.geri_al():
                q = geri_al(p)
            else:
                with pytest.raises(ProjeError):
                    geri_al(p)
                q = p
        else:
            if r.yinele():
                q = yinele(p)
            else:
                with pytest.raises(ProjeError):
                    yinele(p)
                q = p
        assert _durum(p) == once, f"adım {adim}: girdi Proje değişti"
        p = q
        _esit(p, r)

    # Değişmez: k geri al + k yinele aynı projeyi verir; hepsi geri alınınca ilk durum.
    k = p.gecmis.konum
    q = p
    for _ in range(k):
        q = geri_al(q)
    assert _bolumler(q) == _kanonik_bayt(r.durumlar[0])
    for _ in range(k):
        q = yinele(q)
    assert _durum(q) == _durum(p)


def test_undo_no_op_change():
    p = uygula(bos_proje("x"), "ilk", "freze", {"isler": {"sema": 1, "a": 1.0, "b": [1, 2]}})
    assert len(p.gecmis.kayitlar) == 1
    # kanonik olarak aynı belge (farklı anahtar sırası) kayıt eklemez
    q = uygula(p, "aynı", "freze", {"isler": {"b": [1, 2], "a": 1.0, "sema": 1}})
    assert _durum(q) == _durum(p)
    # var olmayan bölümü silmek değişiklik değildir
    q = uygula(p, "sil", "freze", {"montajlar": None})
    assert _durum(q) == _durum(p)
    # boş yama
    assert _durum(uygula(p, "bos", "freze", {})) == _durum(p)


def test_undo_record_contents():
    p = uygula(bos_proje("x"), "ilk", "freze", {"isler": {"sema": 1, "a": 1.0}, "plan": {"sema": 1}})
    p = uygula(
        p,
        "L 9.5",
        "torna",
        {"isler": {"sema": 1, "a": 1.0}, "plan": None, "torna_isleri": {"sema": 1, "L": 9.5}},
    )
    k = p.gecmis.kayitlar[-1]
    assert k["etiket"] == "L 9.5" and k["ekran"] == "torna"
    # yalnız değişen bölümler; tam belge, silinen / yeni bölüm için null
    assert _kanonik_bayt(k["bolumler"]) == _kanonik_bayt(
        {"plan": [{"sema": 1}, None], "torna_isleri": [None, {"sema": 1, "L": 9.5}]}
    )
    q = geri_al(p)
    assert "torna_isleri" not in q.bolumler
    assert kanonik(dict(q.bolumler)["plan"]) == kanonik({"sema": 1})
    q = yinele(q)
    assert "plan" not in q.bolumler
    assert _durum(q) == _durum(p)


def test_undo_new_change_drops_redo():
    p = bos_proje("x")
    for i in range(3):
        p = uygula(p, f"d{i}", "freze", {"isler": {"sema": 1, "i": i}})
    p = geri_al(geri_al(p))
    assert p.gecmis.konum == 1 and len(p.gecmis.kayitlar) == 3
    p = uygula(p, "yeni", "torna", {"torna_isleri": {"sema": 1}})
    assert p.gecmis.konum == 2
    assert [k["etiket"] for k in p.gecmis.kayitlar] == ["d0", "yeni"]
    with pytest.raises(ProjeError):
        yinele(p)


def test_undo_limit_200():
    p = bos_proje("sinir")
    ilk = _bolumler(p)
    for i in range(GECMIS_SINIRI + 1):
        p = uygula(p, f"#{i}", "freze", {"isler": {"sema": 1, "i": i}})
    assert len(p.gecmis.kayitlar) == 200
    assert p.gecmis.konum == 200
    assert p.gecmis.kayitlar[0]["etiket"] == "#1"
    assert p.gecmis.kayitlar[-1]["etiket"] == "#200"
    q = p
    for _ in range(200):
        q = geri_al(q)
    with pytest.raises(ProjeError):
        geri_al(q)
    # en eski kayıt atıldığı için ilk duruma değil, "#0" sonrasına dönülür
    assert _bolumler(q) != ilk
    assert dict(q.bolumler)["isler"]["i"] == 0


def test_undo_empty_stack():
    p = bos_proje("bos")
    with pytest.raises(ProjeError):
        geri_al(p)
    with pytest.raises(ProjeError):
        yinele(p)
    p = uygula(p, "a", "freze", {"isler": {"sema": 1}})
    with pytest.raises(ProjeError):
        yinele(p)


def test_undo_does_not_mutate_input():
    p = uygula(bos_proje("x"), "a", "freze", {"isler": {"sema": 1, "liste": [1, 2], "ic": {"v": 1.0}}})
    once = _durum(p)
    belge = dict(p.bolumler)["isler"]
    yeni = {"isler": {"sema": 1, "liste": [1, 2, 3], "ic": {"v": 2.0}}}
    yeni_once = _kanonik_bayt(yeni)
    q = uygula(p, "b", "freze", yeni)
    assert _durum(p) == once
    assert _kanonik_bayt(yeni) == yeni_once
    assert belge["liste"] == [1, 2]
    geri_al(q)
    yinele(geri_al(q))
    assert _durum(p) == once


# ---------------------------------------------------------------------------
# K8 Geçmiş dosyada yaşar
# ---------------------------------------------------------------------------


def test_history_persists(tmp_path):
    p = bos_proje("gecmis")
    p = uygula(p, "L 20", "torna", {"torna_isleri": {"sema": 1, "L": 20.0}})
    p = uygula(p, "L 9.5", "torna", {"torna_isleri": {"sema": 1, "L": 9.5}})
    p = uygula(p, "paso 2", "freze", {"isler": {"sema": 1, "paso": 2.0}})
    p = geri_al(p)
    yol = tmp_path / "gecmis.3dc"
    kaydet(p, yol)
    q = ac(yol)

    assert _durum(q) == _durum(p)
    assert _durum(geri_al(q)) == _durum(geri_al(p))
    assert _durum(geri_al(geri_al(q))) == _durum(geri_al(geri_al(p)))
    assert _durum(yinele(q)) == _durum(yinele(p))
    with pytest.raises(ProjeError):
        yinele(yinele(q))
    # açılan projede yeni değişiklik yinele dalını siler, kaydetmeden önceki gibi
    assert _durum(uygula(q, "D 31", "torna", {"torna_isleri": {"sema": 1, "D": 31.0}})) == _durum(
        uygula(p, "D 31", "torna", {"torna_isleri": {"sema": 1, "D": 31.0}})
    )


def test_history_persists_bytes_stable(tmp_path):
    """Aç → kaydet → aç: geçmiş dahil dosya aynı kalır."""
    p = _ornek_proje()
    y1, y2 = tmp_path / "1.3dc", tmp_path / "2.3dc"
    kaydet(p, y1)
    kaydet(ac(y1), y2)
    assert y1.read_bytes() == y2.read_bytes()
