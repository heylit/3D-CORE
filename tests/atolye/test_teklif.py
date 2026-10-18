"""SPEC 58 — K8 teklif sayfası (`teklif_html`, `tutar_metni`).

Testler sadece SPEC 58 metninden yazıldı; `atolye/teklif.py` uygulama kodu okunmadı.
Kural: tek dosya, dış kaynaksız HTML (`http` ve `<script>` yok), `table#kademe` her kademe için bir satır,
`dokum=False` iken iç maliyet kalemleri sayfada geçmez, aynı girdi → bayt bayt aynı, tutarlar gösterimde
2 ondalık ROUND_HALF_UP (`decimal`; 2.675 → 2.68). Maliyet kayıtları elle kurulur (maliyet() kullanılmaz).
"""

from __future__ import annotations

import html
from html.parser import HTMLParser

import pytest

from atolye.maliyet import Kalem, Maliyet
from atolye.teklif import teklif_html, tutar_metni

ACIKLAMALAR = {
    "tezgah": "Σ (t_isleme + t_yukle) · U_m / 3600 = (59.76 + 60) · 60 / 3600; süre: SPEC 05 (iş föyü)",
    "hazirlik": "Σ t_hazirlik · (U_m + U_i) / 3600 / n = 1800 · 90 / 3600 / 10",
    "iscilik": "Σ (t_isleme + t_yukle) · U_i · k_op / 3600 = 119.76 · 30 · 0.5 / 3600",
    "malzeme": "1.5 €/kg · 1000 · 7.85e-09 t/mm³ · 226304 mm³ · 1.05",
    "takim": "freze6: 12 € · 0.2 dk / 30 dk; takım: kenar ömrü (yerel dosya)",
    "dis_islem": "Isıl işlem 4.5",
}


def ornek(n: int, fiyat: float) -> Maliyet:
    kalemler = tuple(Kalem(ad, a, 1.0 + i) for i, (ad, a) in enumerate(ACIKLAMALAR.items()))
    return Maliyet(
        n=n,
        t_parca_s=300.0,
        kalemler=kalemler,
        ara_toplam_eur=sum(k.tutar_eur for k in kalemler),
        fiyat_eur=fiyat,
        uyarilar=("Süre SPEC 05 modelinden (72 zaman profili yok: VMC-A)",),
    )


KADEMELER = [ornek(1, 120.5), ornek(10, 30.125), ornek(50, 2.675), ornek(200, 1.005)]


def sayfa(**kw) -> str:
    args = dict(baslik="Teklif T-001", musteri="Uydurma Müşteri", tarih="2026-10-18", kademeler=KADEMELER)
    args.update(kw)
    return teklif_html(**args)


class Tablo(HTMLParser):
    """table#kademe içindeki veri satırları (td içeren tr) ve hücre metinleri."""

    def __init__(self) -> None:
        super().__init__()
        self.derinlik = 0  # kademe tablosu içinde mi (iç içe tablo sayılır)
        self.satirlar: list[list[str]] = []
        self.satir: list[str] | None = None
        self.hucre: list[str] | None = None
        self.kademe_tablosu = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            if self.derinlik or a.get("id") == "kademe":
                self.derinlik += 1
                if a.get("id") == "kademe":
                    self.kademe_tablosu += 1
        elif self.derinlik and tag == "tr":
            self.satir = []
        elif self.derinlik and tag == "td" and self.satir is not None:
            self.hucre = []

    def handle_endtag(self, tag):
        if tag == "table" and self.derinlik:
            self.derinlik -= 1
        elif self.derinlik and tag == "td" and self.hucre is not None:
            self.satir.append("".join(self.hucre).strip())
            self.hucre = None
        elif self.derinlik and tag == "tr" and self.satir is not None:
            if self.satir:
                self.satirlar.append(self.satir)
            self.satir = None

    def handle_data(self, data):
        if self.hucre is not None:
            self.hucre.append(data)


def ayristir(s: str) -> Tablo:
    p = Tablo()
    p.feed(s)
    p.close()
    return p


# ---------------------------------------------------------------- tutar_metni


@pytest.mark.parametrize(
    ("x", "metin"),
    [
        (2.675, "2.68"),  # ikili kayan noktada 2.67499…; ROUND_HALF_UP ondalık gösterimden
        (1.005, "1.01"),
        (2.665, "2.67"),  # banker yuvarlaması 2.66 verirdi
        (0.125, "0.13"),
        (0.135, "0.14"),
        (10.0, "10.00"),
        (0.0, "0.00"),
        (1234.5, "1234.50"),
        (2.674, "2.67"),
    ],
)
def test_tutar_metni_round_half_up(x, metin):
    assert tutar_metni(x) == metin


# ---------------------------------------------------------------- K8


def test_teklif_html_ayrisir_ve_tek_dosya():
    s = sayfa()
    assert isinstance(s, str)
    p = ayristir(s)
    assert p.kademe_tablosu == 1
    alt = s.lower()
    assert "http" not in alt
    assert "<script" not in alt


@pytest.mark.parametrize("dokum", [False, True])
def test_teklif_kademe_satir_sayisi(dokum):
    p = ayristir(sayfa(dokum=dokum))
    assert len(p.satirlar) == len(KADEMELER)
    p3 = ayristir(sayfa(kademeler=KADEMELER[:3], dokum=dokum))
    assert len(p3.satirlar) == 3


def test_teklif_tablo_adet_ve_birim_fiyat():
    p = ayristir(sayfa())
    for satir, m in zip(p.satirlar, KADEMELER, strict=True):
        metin = " ".join(satir)
        assert str(m.n) in metin
        assert tutar_metni(m.fiyat_eur) in metin  # birim fiyat, 2 ondalık
    # 2.675 → "2.68", 1.005 → "1.01" (ROUND_HALF_UP)
    assert "2.68" in " ".join(p.satirlar[2])
    assert "1.01" in " ".join(p.satirlar[3])


def test_teklif_dokumsuz_ic_maliyet_gecmez():
    s = sayfa(dokum=False)
    for ad, aciklama in ACIKLAMALAR.items():
        assert ad not in s, ad
        assert aciklama not in s and html.escape(aciklama) not in s
    assert "SPEC 05" not in s  # uyarılar / kaynak metni de iç bilgidir


def test_teklif_dokumlu_kalemler_gorunur():
    s = sayfa(dokum=True)
    for aciklama in ACIKLAMALAR.values():
        assert aciklama in s or html.escape(aciklama) in s


def test_teklif_bayt_bayt_ayni():
    assert sayfa() == sayfa()
    assert sayfa(dokum=True) == sayfa(dokum=True)
    assert sayfa().encode("utf-8") == teklif_html(
        "Teklif T-001", "Uydurma Müşteri", "2026-10-18", KADEMELER
    ).encode("utf-8")


def test_teklif_basliklar_ve_kacis():
    s = sayfa(baslik="Teklif <T-002>", musteri="A & B Ltd", tarih="2026-10-19", gecerlilik_gun=45)
    assert "Teklif &lt;T-002&gt;" in s and "<T-002>" not in s
    assert "A &amp; B Ltd" in s
    assert "2026-10-19" in s
    assert "45" in s


def test_teklif_varsayilan_gecerlilik():
    assert sayfa() == sayfa(gecerlilik_gun=30)
    assert "37" in sayfa(gecerlilik_gun=37) and "37" not in sayfa()
