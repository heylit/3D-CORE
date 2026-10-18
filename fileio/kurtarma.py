"""
SPEC 54 §5 — Otomatik kayıt: kurtarma dosyasının kitaplık kısmı.

Zamanlama kararı saftır (saat parametre olarak gelir); iş parçacığı ve saat yalnız kabukta
(`tezgah/ekranlar/kabuk.py`). Asıl proje dosyası `P` hiçbir zaman yazılmaz, silinmez, taşınmaz.

    P = <klasör>/<ad>.3dc  →  <klasör>/.<ad>.3dc.kurtarma  (+ .json yan dosyası)

Bağımlılık: yalnız stdlib ve `fileio.proje` (K12).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fileio.proje import Proje

UZANTI = ".kurtarma"
ESKI = ".eski"


@dataclass(frozen=True)
class KurtarmaAyari:
    """T: s cinsinden yazım aralığı (≥ 10); K: yazım için yeni geçmiş kaydı sayısı (≥ 1)."""

    T: float = 60.0
    K: int = 10

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 54: KurtarmaAyari denetimi")


def kurtarma_yolu(proje_yolu: Path | None, ad: str, ilk_ozet: str, klasor: Path | None = None) -> Path:
    """Kurtarma dosyasının yolu; hiç kaydedilmemiş proje için `.kurtarma/<ad>-<ilk_ozet[:8]>.3dc.kurtarma`."""
    raise NotImplementedError("SPEC 54: kurtarma_yolu")


def yazmali_mi(simdi: float, son_yazim: float | None, yeni_kayit: int, kirli: bool, a: KurtarmaAyari) -> bool:
    """Saf zamanlama kararı: kirliyse ve (T doldu ya da K kayıt eklendi) ise yaz."""
    raise NotImplementedError("SPEC 54: yazmali_mi")


def kurtarma_yaz(p: Proje, yol: Path, kaynak_ozet: str | None, sayac: int) -> None:
    """Önbelleksiz .3dc ve .json yan dosyasını atomik yazar; yarıda hata → eski dosyalar aynı, .tmp yok."""
    raise NotImplementedError("SPEC 54: kurtarma_yaz")


def kurtarma_bul(proje_yolu: Path) -> dict | None:
    """{"yol", "okunur", "kaynak_tutuyor", "farkli", "neden"}; kurtarma dosyası yoksa None."""
    raise NotImplementedError("SPEC 54: kurtarma_bul")


def kurtarma_temizle(proje_yolu: Path) -> None:
    """Kurtarma .3dc ve .json'unu siler; yoksa sessizce geçer."""
    raise NotImplementedError("SPEC 54: kurtarma_temizle")


def kurtarma_eskit(proje_yolu: Path) -> Path:
    """ "Yok say": kurtarma dosyalarını .eski'ye taşır, yeni yolu döndürür; dosya yoksa ProjeError."""
    raise NotImplementedError("SPEC 54: kurtarma_eskit")
