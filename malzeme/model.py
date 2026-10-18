"""
Malzeme veri modeli (SPEC B2, arayüz).

Tek malzeme kaydı: mekanik, ısıl, talaş kaldırma ve maliyet özellikleri;
kaynak satırı ve "tipik değer" bayrağıyla.
Birimler N – mm – MPa – s – t (tablo: specs/B2-malzeme-arayuz.md). Kodda birim dönüşümü yok.

Saf Python + numpy. core.model ve cam.model yalnız fem_malzemesi() ve kesme_verisi() içinde geç import edilir;
`import malzeme.model` core / cam / OCCT yüklemez (K9). Bu yüzden hata sınıfı da paketin kendisindedir.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cam.model import CuttingData
    from core.model import Material

TAKIM_MALZEMELERI = ("HSS", "karbur", "kaplamali_karbur", "sermet", "seramik", "CBN", "PCD")
GRUPLAR = ("celik", "paslanmaz", "dokme_demir", "aluminyum", "bakir", "titanyum", "nikel", "plastik", "diger")
ISO513 = ("P", "M", "K", "N", "S", "H")


class ModelError(ValueError):
    """Malzeme kaydında tutarsızlık veya istenen alanın eksikliği (core.model.ModelError ile aynı anlam)."""


class _EksikAnahtar(ModelError, KeyError):
    """Sözlükte olmayan takım malzemesi: hem ModelError hem KeyError (.get() ve `in` çalışsın)."""

    def __str__(self) -> str:  # KeyError mesajı tırnaklı yazar; açıklayıcı mesajı aynen göster
        return str(self.args[0]) if self.args else ""


_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def _sonlu(sahip: str, ad: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ModelError(f"'{sahip}': {ad} sonlu bir sayı olmalı ({v!r})")
    return float(v)


class SaltOkunurSozluk(Mapping):
    """Takım malzemesi → değer; değiştirilemez. Eksik anahtar → açıklayıcı ModelError (KeyError da)."""

    def __init__(self, veri: Mapping, sahip: str, alan: str) -> None:
        self._veri = dict(veri)
        self._sahip = sahip
        self._alan = alan

    def __getitem__(self, anahtar: str):
        try:
            return self._veri[anahtar]
        except KeyError:
            raise _EksikAnahtar(f"'{self._sahip}' malzemesinde '{self._alan}[{anahtar!r}]' yok") from None

    def __contains__(self, anahtar: object) -> bool:
        # `in` hata fırlatmaz: anahtar varsa True, yoksa False
        return anahtar in self._veri

    def __iter__(self) -> Iterator[str]:
        return iter(self._veri)

    def __len__(self) -> int:
        return len(self._veri)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self.items()) == dict(other.items())
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"SaltOkunurSozluk({self._veri!r})"


@dataclass(frozen=True)
class Taylor:
    """Taylor takım ömrü  Vc · T^n = C."""

    C: float  # m/dk, T = 1 dk'daki kesme hızı
    n: float  # 0 < n < 1

    def __post_init__(self) -> None:
        C, n = _sonlu("Taylor", "C", self.C), _sonlu("Taylor", "n", self.n)
        if C <= 0:
            raise ModelError(f"Taylor: C pozitif olmalı ({C})")
        if not 0 < n < 1:
            raise ModelError(f"Taylor: 0 < n < 1 olmalı ({n})")
        object.__setattr__(self, "C", C)
        object.__setattr__(self, "n", n)

    def omur(self, Vc: float) -> float:
        """T = (C / Vc)^(1/n) dk; Vc ≤ 0 → ModelError."""
        Vc = _sonlu("Taylor", "Vc", Vc)
        if Vc <= 0:
            raise ModelError(f"Taylor: Vc pozitif olmalı ({Vc})")
        return (self.C / Vc) ** (1.0 / self.n)


@dataclass(frozen=True)
class KesmeOnerisi:
    Vc: float  # m/dk
    fz: float | None = None  # mm/diş (freze)
    fn: float | None = None  # mm/dev (torna); ikisinden en az biri

    def __post_init__(self) -> None:
        if _sonlu("Kesme önerisi", "Vc", self.Vc) <= 0:
            raise ModelError(f"Kesme önerisi: Vc pozitif olmalı ({self.Vc})")
        if self.fz is None and self.fn is None:
            raise ModelError("Kesme önerisi: fz ya da fn verilmeli")
        for ad in ("fz", "fn"):
            v = getattr(self, ad)
            if v is not None and _sonlu("Kesme önerisi", ad, v) <= 0:
                raise ModelError(f"Kesme önerisi: {ad} pozitif olmalı ({v})")


# Sayısal alanlar ve kuralları (Teori, tutarlılık kuralları 2–7)
_POZITIF = ("rho", "Rp02", "Rm", "sigma_f", "k", "cp", "kc11", "fiyat")
_SAYILAR = ("E", "nu", "rho", "Rp02", "Rm", "A", "sigma_f", "k", "cp", "alpha", "kc11", "mc", "fiyat")


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
        for ad in ("id", "name", "kaynak"):
            v = getattr(self, ad)
            if not isinstance(v, str) or not v.strip():
                raise ModelError(f"Malzeme {self.name!r}: {ad} boş olmayan metin olmalı ({v!r})")
        if not _ID.match(self.id):
            raise ModelError(f"Malzeme {self.name!r}: id yalnız [A-Za-z0-9._-] içerebilir ({self.id!r})")
        if not isinstance(self.standart, str):
            raise ModelError(f"Malzeme {self.name!r}: standart metin olmalı ({self.standart!r})")
        if self.grup not in GRUPLAR:
            raise ModelError(f"Malzeme {self.name!r}: bilinmeyen grup {self.grup!r} (seçenekler: {GRUPLAR})")
        if self.iso513 is not None and self.iso513 not in ISO513:
            raise ModelError(f"Malzeme {self.name!r}: ISO 513 grubu {ISO513} içinde değil ({self.iso513!r})")
        for ad in ("tipik", "kullanici"):
            if not isinstance(getattr(self, ad), bool):
                raise ModelError(f"Malzeme {self.name!r}: {ad} bool olmalı")
        if self.sertlik is not None and not isinstance(self.sertlik, str):
            raise ModelError(f"Malzeme {self.name!r}: sertlik metin olmalı ({self.sertlik!r})")
        for ad in _SAYILAR:
            v = getattr(self, ad)
            if v is not None:
                object.__setattr__(self, ad, _sonlu(self.name, ad, v))
        self._denetle()
        object.__setattr__(self, "taylor", self._sozluk("taylor", self.taylor, Taylor))
        object.__setattr__(self, "kesme", self._sozluk("kesme", self.kesme, KesmeOnerisi))

    def _denetle(self) -> None:
        def hata(m: str) -> ModelError:
            return ModelError(f"Malzeme {self.name!r}: {m}")

        if self.E is not None and self.E <= 0:
            raise hata(f"E > 0 olmalı ({self.E})")
        if self.nu is not None and not 0 < self.nu < 0.5:
            raise hata(f"0 < ν < 0.5 olmalı ({self.nu})")
        for ad in _POZITIF:
            v = getattr(self, ad)
            if v is not None and v <= 0:
                raise hata(f"{ad} > 0 olmalı ({v})")
        if self.alpha is not None and self.alpha < 0:
            raise hata(f"alpha ≥ 0 olmalı ({self.alpha})")
        if self.Rp02 is not None and self.Rm is not None and self.Rp02 > self.Rm:
            raise hata(f"Rp02 ≤ Rm olmalı ({self.Rp02} > {self.Rm})")
        if self.sigma_f is not None and self.Rm is not None and self.sigma_f >= self.Rm:
            raise hata(f"sigma_f < Rm olmalı ({self.sigma_f} ≥ {self.Rm})")
        if self.A is not None and not 0 <= self.A <= 100:
            raise hata(f"0 ≤ A ≤ 100 olmalı ({self.A})")
        if self.mc is not None and not 0 < self.mc < 1:
            raise hata(f"0 < mc < 1 olmalı ({self.mc})")

    def _sozluk(self, alan: str, veri, tip: type) -> SaltOkunurSozluk:
        if not isinstance(veri, Mapping):
            raise ModelError(f"Malzeme {self.name!r}: {alan} sözlük olmalı ({veri!r})")
        for takim, v in veri.items():
            if takim not in TAKIM_MALZEMELERI:
                raise ModelError(f"Malzeme {self.name!r}: {alan} anahtarı {takim!r} takım malzemesi değil")
            if not isinstance(v, tip):
                raise ModelError(f"Malzeme {self.name!r}: {alan}[{takim!r}] {tip.__name__} olmalı ({v!r})")
        return SaltOkunurSozluk(veri, self.name, alan)

    def iste(self, alan: str) -> float:
        """Alanın değeri; None → ModelError("'C45' malzemesinde 'k' yok")."""
        if alan not in _SAYILAR:
            raise ModelError(f"'{self.name}' malzemesinde '{alan}' diye sayısal alan yok")
        v = getattr(self, alan)
        if v is None:
            raise ModelError(f"'{self.name}' malzemesinde '{alan}' yok")
        return v

    @property
    def G(self) -> float:
        """G = E / (2(1 + ν)); E veya ν yoksa ModelError."""
        return self.iste("E") / (2.0 * (1.0 + self.iste("nu")))

    def fem_malzemesi(self) -> Material:
        """core.model.Material(name=id, E, nu, rho); rho yoksa 0.0."""
        from core.model import Material

        return Material(self.id, self.iste("E"), self.iste("nu"), 0.0 if self.rho is None else self.rho)

    def kesme_verisi(self, takim: str, ap: float, ae: float | None = None) -> CuttingData:
        """kesme[takim] + kullanıcının ap / ae'si → cam.model.CuttingData."""
        from cam.model import CamError, CuttingData

        if takim not in TAKIM_MALZEMELERI:
            raise ModelError(f"'{self.name}': {takim!r} takım malzemesi değil ({TAKIM_MALZEMELERI})")
        o = self.kesme[takim]  # yoksa açıklayıcı ModelError
        try:
            return CuttingData(Vc=o.Vc, fz=o.fz, fn=o.fn, ap=ap, ae=ae)
        except CamError as e:
            raise ModelError(f"'{self.name}' kesme verisi ({takim}): {e}") from e

    def to_dict(self) -> dict:
        """None alanlar yazılmaz; JSON'a doğrudan uygun."""
        d: dict = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if f.name == "taylor":
                if v:
                    d[f.name] = {t: {"C": x.C, "n": x.n} for t, x in v.items()}
            elif f.name == "kesme":
                if v:
                    d[f.name] = {
                        t: {a: getattr(x, a) for a in ("Vc", "fz", "fn") if getattr(x, a) is not None}
                        for t, x in v.items()
                    }
            elif v is not None:
                d[f.name] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Malzeme:
        """Bilinmeyen anahtar → ModelError."""
        if not isinstance(d, Mapping):
            raise ModelError(f"Malzeme sözlüğü bekleniyordu ({d!r})")
        bilinen = {f.name for f in fields(cls)}
        fazla = sorted(set(d) - bilinen)
        if fazla:
            raise ModelError(f"Malzeme {d.get('name')!r}: bilinmeyen anahtar {fazla}")
        k = dict(d)
        try:
            k["taylor"] = {t: Taylor(**x) for t, x in d.get("taylor", {}).items()}
            k["kesme"] = {t: KesmeOnerisi(**x) for t, x in d.get("kesme", {}).items()}
            return cls(**k)
        except TypeError as e:  # eksik zorunlu alan ya da bilinmeyen alt anahtar
            raise ModelError(f"Malzeme {d.get('name')!r}: {e}") from e
