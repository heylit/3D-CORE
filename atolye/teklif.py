"""
SPEC 58 — Teklif sayfası: tek dosya HTML, adet kademeli birim fiyat tablosu.

Dış kaynak yok (SPEC 38 §8); aynı girdi → bayt bayt aynı çıktı. Tutarlar gösterimde 2 ondalığa
ROUND_HALF_UP (decimal) ile yuvarlanır. dokum=False iken iç maliyet kalemleri sayfaya yazılmaz.
Firma başlığı: yerel_parcalar/teklif-baslik.html varsa sayfanın başına satır içi gömülür (Karar 4).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from malzeme.model import ModelError

if TYPE_CHECKING:  # K11: çalışma anında yalnız izinli modüller
    from atolye.maliyet import Maliyet

__all__ = ["tutar_metni", "teklif_html"]

BASLIK_DOSYASI = Path("yerel_parcalar/teklif-baslik.html")

# dokum=False sayfasında iç kalem adları (tezgah, hazirlik, ...) geçmemeli; stil ve metin buna göre.
STIL = """\
@page { size: A4; margin: 15mm }
body { font-family: sans-serif; font-size: 10pt; color: #000; background: #fff; margin: 0 }
h1 { font-size: 16pt; margin: 0 0 4mm }
table { border-collapse: collapse; table-layout: fixed; width: 100%; margin: 0 }
th, td { border: 0.3mm solid #444; padding: 1mm 2mm; width: 33.3% }
th { background: #eee; text-align: left }
td.tutar { text-align: right }
.not { font-size: 8pt; color: #444; margin-top: 4mm }
"""


def tutar_metni(x: float) -> str:
    """2 ondalık, ROUND_HALF_UP (2.675 → "2.68"). Float'ın kısa gösterimi (repr) yuvarlanır."""
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x):
        raise ModelError(f"Tutar sonlu sayı olmalı ({x!r})")
    return str(Decimal(repr(float(x))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _firma_basligi() -> str:
    if BASLIK_DOSYASI.is_file():
        return BASLIK_DOSYASI.read_text(encoding="utf-8") + "\n"
    return ""


def _dokum(m: Maliyet) -> list[str]:
    satirlar = [
        f"<h2>Döküm: {m.n} adet</h2>",
        '<table class="dokum"><tr><th>Kalem</th><th>Açıklama</th><th>€ / parça</th></tr>',
    ]
    for k in m.kalemler:
        satirlar.append(
            f"<tr><td>{escape(k.ad)}</td><td>{escape(k.aciklama)}</td>"
            f'<td class="tutar">{tutar_metni(k.tutar_eur)}</td></tr>'
        )
    satirlar.append(
        f'<tr><td>ara toplam</td><td></td><td class="tutar">{tutar_metni(m.ara_toplam_eur)}</td></tr>'
    )
    satirlar.append("</table>")
    satirlar += [f'<p class="not">{escape(u)}</p>' for u in m.uyarilar]
    return satirlar


def teklif_html(
    baslik: str,
    musteri: str,
    tarih: str,
    kademeler: Sequence[Maliyet],
    gecerlilik_gun: int = 30,
    dokum: bool = False,
) -> str:
    """Teklif sayfası; table#kademe her kademe için bir satır (adet / birim / toplam).

    Sütun başlıkları table#kademe'nin dışında, aynı genişlikte ayrı bir başlık tablosundadır; böylece
    table#kademe'nin satır sayısı kademe sayısına eşittir.
    """
    kademeler = list(kademeler)
    if not kademeler:
        raise ModelError("Teklif: kademe yok")
    if isinstance(gecerlilik_gun, bool) or not isinstance(gecerlilik_gun, int) or gecerlilik_gun < 1:
        raise ModelError(f"Teklif: geçerlilik gün sayısı ≥ 1 tam sayı olmalı ({gecerlilik_gun!r})")
    satirlar = [
        "<!DOCTYPE html>",
        '<html lang="tr">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{escape(baslik)}</title>",
        f"<style>\n{STIL}</style>",
        "</head>",
        "<body>",
    ]
    ust = _firma_basligi()
    if ust:
        satirlar.append(ust.rstrip("\n"))
    satirlar += [
        f"<h1>{escape(baslik)}</h1>",
        f"<p>Müşteri: {escape(musteri)}<br>Tarih: {escape(tarih)}<br>Geçerlilik: {gecerlilik_gun} gün</p>",
        '<table class="sutunlar"><tr><th>Adet</th><th>Birim fiyat (EUR)</th>'
        "<th>Toplam (EUR)</th></tr></table>",
        '<table id="kademe">',
    ]
    for m in kademeler:
        satirlar.append(
            f'<tr><td>{m.n}</td><td class="tutar">{tutar_metni(m.fiyat_eur)}</td>'
            f'<td class="tutar">{Decimal(tutar_metni(m.fiyat_eur)) * m.n}</td></tr>'
        )
    satirlar.append("</table>")
    satirlar.append('<p class="not">Fiyatlar parça başıdır; döviz çevirisi ve vergi dahil değildir.</p>')
    if dokum:
        for m in kademeler:
            satirlar += _dokum(m)
    satirlar += ["</body>", "</html>", ""]
    return "\n".join(satirlar)
