"""
SPEC 25 — torna ekranı (A3 kaydı). Uçlar `tezgah.sunucu_25.torna_router`
(kabuk `/api/ekran/torna` altına bağlar).

Bölüm "torna_isleri": torna işlerinin parametreleri (`tezgah.iplik.Depo`; montaj ekranının parametre bağı da
aynı depoyu yazar).
"""

from __future__ import annotations

from collections.abc import Mapping

from tezgah import depo, sunucu_25, torna
from tezgah.ekranlar import Ekran
from tezgah.ornekler_25 import TORNA_ISLERI


def disa_aktar() -> dict:
    with sunucu_25.KILIT:
        return sunucu_25.DEPO.disa_aktar()


def ice_aktar(belge: dict, onbellek: Mapping[str, bytes]) -> None:
    """Belgedeki parametreleri yükler (önbellek kullanılmaz: işler yeniden hesaplanır).

    Hata → depo değişmez.
    """
    with sunucu_25.KILIT:
        sunucu_25.DEPO.ice_aktar(belge)


def ozet() -> dict[str, float | str]:
    """Etki kartı: iş sayısı ve toplam G-code satırı (SPEC 21; simülasyon gerektirmez)."""
    with sunucu_25.KILIT:
        satir = sum(len(torna.gcode_satirlari(sunucu_25.DEPO.torna_isi(ad))[0]) for ad in TORNA_ISLERI)
    return {"is_sayisi": len(TORNA_ISLERI), "gcode_satir": satir}


# A3 is_kaydet: TornaIsi bu ekranın deposuna gider; adları /api/isler'de freze işlerinden sonra çıkar.
if hasattr(depo, "kaydedici_ekle"):  # kanca main'e girene kadar (#105) koşullu
    depo.kaydedici_ekle(torna.TornaIsi, kaydet=sunucu_25.kaydet, adlar=sunucu_25.adlar)

EKRAN = Ekran(
    ad="torna",
    baslik="Torna",
    sira=20,
    tus="2",
    router=sunucu_25.torna_router(),
    sifirla=sunucu_25.sifirla,
    kur=lambda app: sunucu_25.sifirla(),  # her yeni uygulama varsayılan parametrelerle
    bolum="torna_isleri",
    disa_aktar=disa_aktar,
    ice_aktar=ice_aktar,
    ozet=ozet,
)
