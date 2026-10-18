"""
SPEC 48 — Gerçek tezgâh doğrulama kaydı: basamak kayıtları, sıra ve ölçüm denetimi, hazırlık raporu.

Basamaklar (`ADIMLAR`, bu sırayla): masa → havada → mum → ilk_metal → olcum. Bir kayıt bir basamaktır (B1
JSON'u). Kod `MachineProfile.verified` alanını hiçbir zaman yazmaz; onu yalnız kullanıcı elle `true` yapar.

Biçim kuralları (SPEC metninin bıraktığı yerlerde bu modülün kararları):
- Kanonik JSON: `json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)`,
  sonda tek "\\n", UTF-8 (SPEC 37 `main`'e girene dek yerel kural).
- Özetler: küçük harf 64 haneli sha256 onaltılığı. `profil_ozeti` = `MachineProfile.to_dict()`'in `verified`
  anahtarı **çıkarılmış** kanonik JSON'unun sha256'sı (kullanıcının `verified: true` yapması eski kayıtları
  geçersiz kılmaz; kurs, kinematik gibi her başka değişiklik kılar). `dosya_ozeti` = dosya baytlarının
  sha256'sı.
- Dosya adı: `<klasor>/<profil.ad>/<tarih>-<sıra 3 hane>-<adim>.json`; sıra = aynı profil adı ve tarihli
  mevcut kayıt sayısı + 1. Hata mesajları bu adla başlar ("<profil.ad>/<tarih>-<sıra>-<adim>.json: …");
  `denetle` sırayı `onceki`'den aynı kuralla hesaplar.
- Zincir: aynı `(profil.ozet, program.ozet)` kayıtları; son `masa` kaydı yeni zincir başlatır, zincirde
  `kaldi` varsa yalnız `masa` kaydedilebilir. `adim` i için önceki her basamağın zincirdeki en son kaydı
  `gecti` ya da `atlandi` olmalı. `masa` ve `olcum` `atlandi` olamaz.
- `olcumler` yalnız `mum` ve `olcum` basamağında dolu olabilir; `olcum`'da boş olamaz; denetimde `olculen`
  boş (None) olamaz. `gecti` iken her kalem `alt − 1e-9 ≤ olculen ≤ ust + 1e-9`.
- Bağ denetimi isteğe bağlı girdilerle: `is_foyu.yol` `kok`'a (kaydet'te kayıt klasörü) göre çözülür, dosya
  var ve özeti tutmalı; `program` yolu verilirse özeti `program.ozet`'e eşit olmalı; `job` verilirse `olcum`
  basamağındaki her kalemin no, metin, nominal, alt, üst değerleri `job.inspection`'daki aynı no'lu kalemle
  aynı.
- `bos_kayit` maddeleri: `docs/tezgah-dogrulama.md` bölüm 1–5'in her "- [ ] " maddesi (alt satırlara taşan
  devamı tek boşlukla birleştirilmiş, boşluklar sadeleştirilmiş), bölüm sırasıyla; ardından `job.checks`.
  Hepsi `isaret = False`. Ölçümler `job.inspection`'dan (`olculen = None`); `job` yoksa ikisi de boş kalır.
  `program.ad` dosya adı, `program.lehce` `m.controller`.
- `hazirlik`: `KAPSAMLAR`'ın her biri için; yalnız `profil.ad == m.name` ve `profil.ozet == profil_ozeti(m)`
  kayıtları. Kapsamı içeren bir zincir tamamsa "hazir", değilse en son kaydın zincirinde eksik ilk basamak
  (kayıt yoksa "masa"). Uyarılar: `verified` ve hazır kapsam yoksa "<ad>: verified=true ama geçen doğrulama
  kaydı yok"; aynı adlı ama farklı özetli kayıt varsa "<ad>: profil değişti, <n> eski kayıt sayılmadı".
- `rapor_html`: SPEC 38 §8 kuralları; `table#zincir` `<thead>` başlık + `<tbody>`'de verilen her kayıt için
  bir `<tr>` (verilen sırayla); `table#olcum` `mum` / `olcum` kayıtlarının ölçüm kalemleri; `ul#uyarilar`
  `hazirlik` uyarıları (yoksa öğe yok); `table#kapsam` hazırlık durumu.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from atolye.is_foyu import JobSheet
from cam.model import MachineProfile

SEMA = 1
ADIMLAR = ("masa", "havada", "mum", "ilk_metal", "olcum")
SONUCLAR = ("gecti", "kaldi", "atlandi")
KAPSAMLAR = ("torna_2x", "freze_3x", "freze_3arti2", "freze_4x_indeks", "freze_5x", "torna_freze")


@dataclass(frozen=True)
class Profil:
    ad: str
    ozet: str


@dataclass(frozen=True)
class Program:
    ad: str
    ozet: str
    lehce: str


@dataclass(frozen=True)
class IsFoyu:
    yol: str  # kayıt klasörüne göre göreli (ya da mutlak) is-foyu.html yolu
    ozet: str


@dataclass(frozen=True)
class Madde:
    bolum: int
    metin: str
    isaret: bool


@dataclass(frozen=True)
class Olcum:
    no: int
    metin: str
    nominal: float
    alt: float
    ust: float
    olculen: float | None  # bos_kayit'ta None; denetimde dolu olmalı


@dataclass(frozen=True)
class DogrulamaKaydi:
    """B1 kaydı; JSON anahtarları alan adlarıyla aynı (`to_dict` / `from_dict`)."""

    profil: Profil
    program: Program
    is_foyu: IsFoyu | None
    kapsam: tuple[str, ...]
    adim: str
    sonuc: str
    tarih: str  # YYYY-AA-GG
    operator: str
    maddeler: tuple[Madde, ...] = ()
    olcumler: tuple[Olcum, ...] = ()
    notlar: str = ""
    gerekce: str = ""
    sema: int = SEMA

    def to_dict(self) -> dict:
        raise NotImplementedError("SPEC 48: DogrulamaKaydi.to_dict")

    @classmethod
    def from_dict(cls, d: dict) -> DogrulamaKaydi:
        """Şema hatası → CamError."""
        raise NotImplementedError("SPEC 48: DogrulamaKaydi.from_dict")


def kanonik(d: dict) -> str:
    """Kanonik JSON metni (sonda "\\n")."""
    raise NotImplementedError("SPEC 48: kanonik")


def profil_ozeti(m: MachineProfile) -> str:
    """`verified` hariç kanonik profil özeti (sha256)."""
    raise NotImplementedError("SPEC 48: profil_ozeti")


def dosya_ozeti(yol: str | Path) -> str:
    """sha256(bytes); dosya yoksa CamError."""
    raise NotImplementedError("SPEC 48: dosya_ozeti")


def bos_kayit(
    m: MachineProfile,
    program: str | Path,
    job: JobSheet | None,
    adim: str,
    kapsam: Sequence[str],
    tarih: str,
    operator: str,
    is_foyu_yolu: str | Path | None = None,
) -> DogrulamaKaydi:
    """Doldurulacak kayıt: sonuc "gecti", maddeler işaretsiz, ölçümler boş (olculen None)."""
    raise NotImplementedError("SPEC 48: bos_kayit")


def denetle(
    k: DogrulamaKaydi,
    onceki: Sequence[DogrulamaKaydi],
    *,
    kok: str | Path | None = None,
    program: str | Path | None = None,
    job: JobSheet | None = None,
) -> None:
    """Şema, sıra, ölçüm ve bağ kuralları (B2); ihlal → CamError (mesaj dosya adıyla başlar)."""
    raise NotImplementedError("SPEC 48: denetle")


def kaydet(
    k: DogrulamaKaydi,
    klasor: str | Path,
    *,
    program: str | Path | None = None,
    job: JobSheet | None = None,
) -> Path:
    """denetle(k, oku(klasor), kok=klasor, …) + atomik yazım; yazılan dosyanın yolu."""
    raise NotImplementedError("SPEC 48: kaydet")


def oku(klasor: str | Path) -> list[DogrulamaKaydi]:
    """Klasördeki kayıtlar (tarih, sıra, profil adı düzeninde); bozuk kayıt → CamError (dosya adıyla)."""
    raise NotImplementedError("SPEC 48: oku")


def hazirlik(m: MachineProfile, kayitlar: Sequence[DogrulamaKaydi]) -> dict:
    """{"profil": ad, "kapsam": {k: "hazir" | "<eksik adim>"}, "uyarilar": [str]}; profili değiştirmez."""
    raise NotImplementedError("SPEC 48: hazirlik")


def rapor_html(m: MachineProfile, kayitlar: Sequence[DogrulamaKaydi]) -> str:
    """Tek dosya, dış kaynaksız HTML rapor (SPEC 38 §8 kuralları)."""
    raise NotImplementedError("SPEC 48: rapor_html")
