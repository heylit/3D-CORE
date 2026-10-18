"""
SPEC 37 — örnek proje (uydurma geometri): SPEC 25 "yatak grubu" (kademeli mil torna işi + montaj, L = 20,
girişim var) ve SPEC 24 flanş freze işi tek projede; SPEC 26 varsa "model" bölümü de eklenir.

Bölüm belgeleri elle yazılmaz: her bölümün biçimi sahibi ekranındır. Örnek, kayıtlı ekranların başlangıç
durumundan (`sifirla()` sonrası `disa_aktar()`) kurulur; SPEC 24 / 25 / 26 örnekleri zaten bu durumdur.
Dikkat: `sifirla()` ekranların canlı durumunu varsayılana döndürür (örnek açmak da bunu yapar).
"""

from __future__ import annotations

from fileio.proje import Proje, ProjeError, bos_proje
from tezgah.ekranlar import ekranlar

ORNEK_PROJELER = ("yatak_grubu",)

# Örneğin taşıması gereken bölümler ve kabuğun açılıştaki ekranı.
_GEREKEN = {"yatak_grubu": ("isler", "torna_isleri", "montajlar")}
_AKTIF = {"yatak_grubu": "montaj"}


def ornek_proje(ad: str) -> Proje:
    """Adı verilen örnek projeyi bellekte kurar. Bilinmeyen ad → KeyError; eksik ekran → ProjeError."""
    if ad not in ORNEK_PROJELER:
        raise KeyError(f"bilinmeyen örnek proje: {ad!r}")
    bolumler = dict(bos_proje(ad).bolumler)
    bolumler["kabuk"] = {**bolumler["kabuk"], "aktif_ekran": _AKTIF[ad]}
    for e in ekranlar():
        if e.bolum is None or e.bolum == "kabuk" or e.disa_aktar is None:
            continue
        if e.sifirla is not None:
            e.sifirla()
        bolumler[e.bolum] = e.disa_aktar()
    eksik = [b for b in _GEREKEN[ad] if b not in bolumler]
    if eksik:
        raise ProjeError(f"örnek {ad!r} için ekran bölümü yok: {', '.join(eksik)}")
    return Proje(ad, bolumler)
