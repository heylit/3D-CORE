"""
SPEC 25 — montaj ekranı (A3 kaydı). Uçlar `tezgah.sunucu_25.montaj_router`
(kabuk `/api/ekran/montaj` altına bağlar).

Bölüm "montajlar": örnek montajların adları (montajın kendi değiştirilebilir değeri yok). Parça ölçüleri torna
işlerinin parametrelerinden gelir ("torna_isleri"); parametre bağı onları `tezgah.iplik.Depo` üzerinden yazar.
"""

from __future__ import annotations

from collections.abc import Mapping

from tezgah import SEMA, sunucu_25
from tezgah.ekranlar import Ekran
from tezgah.ornekler_25 import MONTAJLAR


def disa_aktar() -> dict:
    return {"sema": SEMA, "montajlar": list(MONTAJLAR)}


def ice_aktar(belge: dict, onbellek: Mapping[str, bytes]) -> None:
    """Yalnız doğrular (durum yok): şema ve montaj adları örneklerle aynı olmalı."""
    sema = belge["sema"]
    if not isinstance(sema, int) or isinstance(sema, bool) or sema != SEMA:
        raise ValueError(f"'montajlar' bölümünün şeması {SEMA} olmalı, {sema!r} verildi")
    adlar = belge["montajlar"]
    if not isinstance(adlar, list) or list(adlar) != list(MONTAJLAR):
        raise KeyError(f"Bilinmeyen montaj listesi: {adlar!r} (var olanlar: {list(MONTAJLAR)})")


def ozet() -> dict[str, float | str]:
    """Etki kartı: girişim sayısı ve toplam girişim hacmi [mm³]."""
    with sunucu_25.KILIT:
        G = [g for ad in MONTAJLAR for g in sunucu_25.DEPO.montaj_json(ad)["girisimler"]]
    return {"girisim_sayisi": len(G), "girisim_mm3": float(sum(g["hacim"] for g in G))}


EKRAN = Ekran(
    ad="montaj",
    baslik="Montaj",
    sira=30,
    tus="3",
    router=sunucu_25.montaj_router(),
    bolum="montajlar",
    bagimli=("torna_isleri",),
    disa_aktar=disa_aktar,
    ice_aktar=ice_aktar,
    ozet=ozet,
)
