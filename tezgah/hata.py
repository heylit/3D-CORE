"""
SPEC 54 §2 — Hata kartı ve hata günlüğü (saf; FastAPI'ye bağlı değil).

Çekirdek hata metni `<nesne>: <ne oldu> — <ne yapılabilir>` biçimindedir; kart bu üç parçayı ve teknik
ayrıntıyı (istisna zinciri, son 20 satır) taşır:

    {sinif, nesne, ne_oldu, oneri, teknik}
"""

from __future__ import annotations

from pathlib import Path

GUNLUK_SINIRI = 5 * 1024 * 1024  # bayt
TEKNIK_SATIR = 20


def hata_karti(e: BaseException) -> dict:
    """Çekirdek hatasını karta ayırır; biçim dışı metinde nesne ve öneri boş kalır."""
    raise NotImplementedError("SPEC 54: hata_karti")


def ic_hata_karti(e: BaseException, uc: str, gunluk: Path) -> dict:
    """Çekirdek dışı istisna (programlama hatası) için 'IcHata' kartı."""
    raise NotImplementedError("SPEC 54: ic_hata_karti")


def gunluge_yaz(e: BaseException, uc: str, gunluk: Path) -> None:
    """Günlüğe tek satır JSON ekler; sınır aşılacaksa önce hatalar.log → hatalar.log.1 döner."""
    raise NotImplementedError("SPEC 54: gunluge_yaz")
