"""
Malzeme veri modeli (SPEC B2, arayüz).

Tek malzeme kaydı: mekanik, ısıl, talaş kaldırma ve maliyet özellikleri;
kaynak satırı ve "tipik değer" bayrağıyla.
Birimler N – mm – MPa – s – t (tablo: specs/B2-malzeme-arayuz.md). Kodda birim dönüşümü yok.

Saf Python + numpy. core.model ve cam.model yalnız fem_malzemesi() ve kesme_verisi() içinde geç import edilir;
`import malzeme.model` core / cam / OCCT yüklemez (K9). Bu yüzden hata sınıfı da paketin kendisindedir.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cam.model import CuttingData
    from core.model import Material

TAKIM_MALZEMELERI = ("HSS", "karbur", "kaplamali_karbur", "sermet", "seramik", "CBN", "PCD")
GRUPLAR = ("celik", "paslanmaz", "dokme_demir", "aluminyum", "bakir", "titanyum", "nikel", "plastik", "diger")
ISO513 = ("P", "M", "K", "N", "S", "H")


class ModelError(ValueError):
    """Malzeme kaydında tutarsızlık veya istenen alanın eksikliği (core.model.ModelError ile aynı anlam)."""


class SaltOkunurSozluk(Mapping):
    """Takım malzemesi → değer; değiştirilemez. Eksik anahtar → açıklayıcı ModelError (KeyError da)."""

    def __init__(self, veri: Mapping, sahip: str, alan: str) -> None:
        raise NotImplementedError("SPEC B2: SaltOkunurSozluk")

    def __getitem__(self, anahtar: str):
        raise NotImplementedError("SPEC B2: SaltOkunurSozluk.__getitem__")

    def __iter__(self) -> Iterator[str]:
        raise NotImplementedError("SPEC B2: SaltOkunurSozluk.__iter__")

    def __len__(self) -> int:
        raise NotImplementedError("SPEC B2: SaltOkunurSozluk.__len__")


@dataclass(frozen=True)
class Taylor:
    """Taylor takım ömrü  Vc · T^n = C."""

    C: float  # m/dk, T = 1 dk'daki kesme hızı
    n: float  # 0 < n < 1

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC B2: Taylor doğrulaması")

    def omur(self, Vc: float) -> float:
        """T = (C / Vc)^(1/n) dk; Vc ≤ 0 → ModelError."""
        raise NotImplementedError("SPEC B2: Taylor.omur")


@dataclass(frozen=True)
class KesmeOnerisi:
    Vc: float  # m/dk
    fz: float | None = None  # mm/diş (freze)
    fn: float | None = None  # mm/dev (torna); ikisinden en az biri

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC B2: KesmeOnerisi doğrulaması")


@dataclass(frozen=True)
class Malzeme:
    id: str  # "1.0503", "EN-AW-6061-T6", "POM-C": benzersiz anahtar, [A-Za-z0-9._-]
    name: str  # "C45"
    standart: str  # "EN 10083-2"; standart yoksa ""
    grup: str  # GRUPLAR'dan biri
    kaynak: str  # kaynak satırı, boş olamaz
    iso513: str | None = None  # ISO 513 talaş grubu; plastik için None
    tipik: bool = True  # değerler aralığın tipik orta noktası mı
    kullanici: bool = False  # kullanıcının eklediği kayıt
    # mekanik
    E: float | None = None  # MPa
    nu: float | None = None  # –
    rho: float | None = None  # t/mm³
    Rp02: float | None = None  # MPa
    Rm: float | None = None  # MPa
    A: float | None = None  # %
    sertlik: str | None = None  # "HB 210", serbest metin
    sigma_f: float | None = None  # MPa, dönen eğme R = −1
    # ısıl
    k: float | None = None  # mW/(mm·K)
    cp: float | None = None  # mJ/(t·K)
    alpha: float | None = None  # 1/K
    # talaş kaldırma
    kc11: float | None = None  # MPa
    mc: float | None = None  # –
    taylor: Mapping[str, Taylor] = field(default_factory=dict, hash=False)  # anahtar: TAKIM_MALZEMELERI
    kesme: Mapping[str, KesmeOnerisi] = field(default_factory=dict, hash=False)  # anahtar: TAKIM_MALZEMELERI
    # maliyet
    fiyat: float | None = None  # €/kg

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC B2: Malzeme doğrulaması")

    def iste(self, alan: str) -> float:
        """Alanın değeri; None → ModelError("'C45' malzemesinde 'k' yok")."""
        raise NotImplementedError("SPEC B2: Malzeme.iste")

    @property
    def G(self) -> float:
        """G = E / (2(1 + ν)); E veya ν yoksa ModelError."""
        raise NotImplementedError("SPEC B2: Malzeme.G")

    def fem_malzemesi(self) -> Material:
        """core.model.Material(name=id, E, nu, rho); rho yoksa 0.0."""
        raise NotImplementedError("SPEC B2: Malzeme.fem_malzemesi")

    def kesme_verisi(self, takim: str, ap: float, ae: float | None = None) -> CuttingData:
        """kesme[takim] + kullanıcının ap / ae'si → cam.model.CuttingData."""
        raise NotImplementedError("SPEC B2: Malzeme.kesme_verisi")

    def to_dict(self) -> dict:
        """None alanlar yazılmaz; JSON'a doğrudan uygun."""
        raise NotImplementedError("SPEC B2: Malzeme.to_dict")

    @classmethod
    def from_dict(cls, d: dict) -> Malzeme:
        """Bilinmeyen anahtar → ModelError."""
        raise NotImplementedError("SPEC B2: Malzeme.from_dict")
