"""
SPEC 58 — Teklif sayfası: tek dosya HTML, adet kademeli birim fiyat tablosu.

Dış kaynak yok (SPEC 38 §8); aynı girdi → bayt bayt aynı çıktı. Tutarlar gösterimde 2 ondalığa
ROUND_HALF_UP (decimal) ile yuvarlanır. dokum=False iken iç maliyet kalemleri sayfaya yazılmaz.
"""

from __future__ import annotations

from collections.abc import Sequence

from atolye.maliyet import Maliyet

__all__ = ["tutar_metni", "teklif_html"]


def tutar_metni(x: float) -> str:
    """2 ondalık, ROUND_HALF_UP (2.675 → "2.68")."""
    raise NotImplementedError("SPEC 58: tutar_metni")


def teklif_html(
    baslik: str,
    musteri: str,
    tarih: str,
    kademeler: Sequence[Maliyet],
    gecerlilik_gun: int = 30,
    dokum: bool = False,
) -> str:
    """Teklif sayfası; table#kademe her kademe için bir satır (adet / birim / toplam)."""
    raise NotImplementedError("SPEC 58: teklif_html")
