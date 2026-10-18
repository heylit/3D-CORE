"""
A3 — freze ekranı (SPEC 24'ün ilk ekranı). Uçları SPEC 24'ün `/api/isler`, `/api/is/{ad}/...` uçlarıdır;
onlar kabuğun iş deposu uçları olarak kalır (`tezgah/depo.py`), bu yüzden ekranın kendi `router`'ı yoktur.

Bölüm "isler": örnek işlerin işlem başına parametreleri. Dinamik işler (is_kaydet) çekirdek çıktısıdır,
proje dosyasına girmez.
"""

from __future__ import annotations

from collections.abc import Mapping

from tezgah import SEMA, depo
from tezgah.ekranlar import Ekran


def disa_aktar() -> dict:
    """{"sema": 1, "ornekler": [{"ad": iş adı, "parametreler": [işlem başına {anahtar: değer}]}]}."""
    P = depo.ornek_parametreleri()
    return {"sema": SEMA, "ornekler": [{"ad": ad, "parametreler": p} for ad, p in P.items()]}


def ice_aktar(belge: dict, onbellek: Mapping[str, bytes]) -> None:
    """Belgedeki parametrelerle örnek işleri kurar. Bozuk belge → ValueError / KeyError / TypeError;
    çekirdeğin reddettiği değer → CamError. Hata olursa depo değişmez (önce hepsi kurulur)."""
    sema = belge["sema"]
    if not isinstance(sema, int) or isinstance(sema, bool) or sema != SEMA:
        raise ValueError(f"'isler' bölümünün şeması {SEMA} olmalı, {sema!r} verildi")
    P: dict[str, list[dict[str, float]]] = {}
    for o in belge["ornekler"]:
        ad = o["ad"]
        if not isinstance(ad, str):
            raise TypeError(f"İş adı metin olmalı, {type(ad).__name__} verildi")
        P[ad] = [{str(k): float(v) for k, v in p.items()} for p in o["parametreler"]]
    depo.ornekleri_ayarla(P)


def ozet() -> dict[str, float | str]:
    """Etki kartı: iş ve işlem sayısı."""
    P = depo.ornek_parametreleri()
    return {"is_sayisi": len(depo.adlar()), "islem_sayisi": sum(len(p) for p in P.values())}


EKRAN = Ekran(
    ad="freze",
    baslik="Freze",
    sira=10,
    tus="1",
    sifirla=depo.ornekleri_sifirla,
    bolum="isler",
    disa_aktar=disa_aktar,
    ice_aktar=ice_aktar,
    ozet=ozet,
)
