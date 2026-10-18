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

import hashlib
import json
import math
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from html import escape
from pathlib import Path

from atolye.is_foyu import JobSheet
from cam.model import CamError, MachineProfile

SEMA = 1
ADIMLAR = ("masa", "havada", "mum", "ilk_metal", "olcum")
SONUCLAR = ("gecti", "kaldi", "atlandi")
KAPSAMLAR = ("torna_2x", "freze_3x", "freze_3arti2", "freze_4x_indeks", "freze_5x", "torna_freze")

PAY = 1e-9  # ölçüm sınırı ve föy karşılaştırması payı
_BELGE = Path(__file__).resolve().parents[1] / "docs" / "tezgah-dogrulama.md"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_DOSYA = re.compile(r"(\d{4}-\d{2}-\d{2})-(\d{3})-([a-z_]+)\.json")
_OLCUMLU = ("mum", "olcum")


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
        return {
            "sema": self.sema,
            "profil": {"ad": self.profil.ad, "ozet": self.profil.ozet},
            "program": {"ad": self.program.ad, "ozet": self.program.ozet, "lehce": self.program.lehce},
            "is_foyu": None if self.is_foyu is None else {"yol": self.is_foyu.yol, "ozet": self.is_foyu.ozet},
            "kapsam": list(self.kapsam),
            "adim": self.adim,
            "sonuc": self.sonuc,
            "tarih": self.tarih,
            "operator": self.operator,
            "maddeler": [{"bolum": x.bolum, "metin": x.metin, "isaret": x.isaret} for x in self.maddeler],
            "olcumler": [
                {
                    "no": o.no,
                    "metin": o.metin,
                    "nominal": o.nominal,
                    "alt": o.alt,
                    "ust": o.ust,
                    "olculen": o.olculen,
                }
                for o in self.olcumler
            ],
            "notlar": self.notlar,
            "gerekce": self.gerekce,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DogrulamaKaydi:
        """Şema hatası → CamError."""
        _anahtarlar("kayıt", d, _ALANLAR)
        p = _anahtarlar("profil", d["profil"], ("ad", "ozet"))
        g = _anahtarlar("program", d["program"], ("ad", "ozet", "lehce"))
        f = None
        if d["is_foyu"] is not None:
            f = _anahtarlar("is_foyu", d["is_foyu"], ("yol", "ozet"))
            f = IsFoyu(_metin("is_foyu.yol", f["yol"]), _metin("is_foyu.ozet", f["ozet"]))
        if not isinstance(d["kapsam"], list):
            raise CamError("kapsam: liste olmalı")
        for ad in ("maddeler", "olcumler"):
            if not isinstance(d[ad], list):
                raise CamError(f"{ad}: liste olmalı")
        maddeler = []
        for x in d["maddeler"]:
            x = _anahtarlar("maddeler", x, ("bolum", "metin", "isaret"))
            if not isinstance(x["isaret"], bool):
                raise CamError("maddeler.isaret: true / false olmalı")
            maddeler.append(
                Madde(_tam("maddeler.bolum", x["bolum"]), _metin("maddeler.metin", x["metin"]), x["isaret"])
            )
        olcumler = []
        for x in d["olcumler"]:
            x = _anahtarlar("olcumler", x, ("no", "metin", "nominal", "alt", "ust", "olculen"))
            olc = None if x["olculen"] is None else _sayi("olcumler.olculen", x["olculen"])
            olcumler.append(
                Olcum(
                    _tam("olcumler.no", x["no"]),
                    _metin("olcumler.metin", x["metin"]),
                    _sayi("olcumler.nominal", x["nominal"]),
                    _sayi("olcumler.alt", x["alt"]),
                    _sayi("olcumler.ust", x["ust"]),
                    olc,
                )
            )
        k = cls(
            profil=Profil(_metin("profil.ad", p["ad"]), _metin("profil.ozet", p["ozet"])),
            program=Program(
                _metin("program.ad", g["ad"]),
                _metin("program.ozet", g["ozet"]),
                _metin("program.lehce", g["lehce"]),
            ),
            is_foyu=f,
            kapsam=tuple(_metin("kapsam", x) for x in d["kapsam"]),
            adim=_metin("adim", d["adim"]),
            sonuc=_metin("sonuc", d["sonuc"]),
            tarih=_metin("tarih", d["tarih"]),
            operator=_metin("operator", d["operator"]),
            maddeler=tuple(maddeler),
            olcumler=tuple(olcumler),
            notlar=_metin("notlar", d["notlar"]),
            gerekce=_metin("gerekce", d["gerekce"]),
            sema=_tam("sema", d["sema"]),
        )
        _kurallar(k)
        return k


_ALANLAR = (
    "sema",
    "profil",
    "program",
    "is_foyu",
    "kapsam",
    "adim",
    "sonuc",
    "tarih",
    "operator",
    "maddeler",
    "olcumler",
    "notlar",
    "gerekce",
)


# ---------------------------------------------------------------- şema yardımcıları


def _anahtarlar(yer: str, d, alanlar: tuple[str, ...]) -> dict:
    if not isinstance(d, dict):
        raise CamError(f"{yer}: nesne olmalı")
    fazla = sorted(set(d) - set(alanlar))
    if fazla:
        raise CamError(f"{yer}: bilinmeyen alan: {', '.join(fazla)}")
    eksik = [a for a in alanlar if a not in d]
    if eksik:
        raise CamError(f"{yer}: eksik alan: {', '.join(eksik)}")
    return d


def _metin(alan: str, v) -> str:
    if not isinstance(v, str):
        raise CamError(f"{alan}: metin olmalı")
    return v


def _tam(alan: str, v) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise CamError(f"{alan}: tam sayı olmalı")
    return v


def _sayi(alan: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise CamError(f"{alan}: sonlu sayı olmalı")
    return v


def _s(v: float) -> str:
    """Sayıyı virgüllü, en çok 6 ondalıkla yazar (20.2 → "20,2")."""
    t = f"{v:.6f}".rstrip("0").rstrip(".")
    return ("0" if t in ("-0", "") else t).replace(".", ",")


def _kurallar(k: DogrulamaKaydi) -> None:
    """Tek kayda bakan B2 kuralları (şema ve ölçüm); ihlal → CamError (dosya adı öneki çağırandan)."""
    if k.sema != SEMA:
        raise CamError(f"sema: {k.sema} desteklenmiyor (beklenen {SEMA})")
    ad = k.profil.ad
    if not ad.strip() or ad in (".", "..") or "/" in ad or "\\" in ad:
        raise CamError(f"profil.ad: dosya adı olarak kullanılamaz: {ad!r}")
    for alan, oz in (("profil.ozet", k.profil.ozet), ("program.ozet", k.program.ozet)):
        if not _HEX64.fullmatch(oz):
            raise CamError(f"{alan}: 64 haneli sha256 onaltılığı olmalı")
    if k.is_foyu is not None and not _HEX64.fullmatch(k.is_foyu.ozet):
        raise CamError("is_foyu.ozet: 64 haneli sha256 onaltılığı olmalı")
    if not k.kapsam:
        raise CamError("kapsam: en az bir kapsam gerekli")
    for x in k.kapsam:
        if x not in KAPSAMLAR:
            raise CamError(f"kapsam: bilinmeyen {x!r} (bilinenler: {', '.join(KAPSAMLAR)})")
    if k.adim not in ADIMLAR:
        raise CamError(f"adim: bilinmeyen {k.adim!r} (bilinenler: {', '.join(ADIMLAR)})")
    if k.sonuc not in SONUCLAR:
        raise CamError(f"sonuc: bilinmeyen {k.sonuc!r} (bilinenler: {', '.join(SONUCLAR)})")
    try:
        gecerli = re.fullmatch(r"\d{4}-\d{2}-\d{2}", k.tarih) and date.fromisoformat(k.tarih)
    except ValueError:
        gecerli = False
    if not gecerli:
        raise CamError(f"tarih: YYYY-AA-GG olmalı: {k.tarih!r}")
    if not k.operator.strip():
        raise CamError("operator: boş olamaz")
    if k.sonuc != "gecti" and not k.gerekce.strip():
        raise CamError(f"gerekce: {k.sonuc} sonucu için boş olamaz")
    if k.sonuc == "atlandi" and k.adim in ("masa", "olcum"):
        raise CamError(f"sonuc: {k.adim} basamağı atlanamaz")
    if k.olcumler and k.adim not in _OLCUMLU:
        raise CamError(f"olcumler: yalnız mum ve olcum basamağında olabilir ({k.adim})")
    if k.adim == "olcum" and not k.olcumler:
        raise CamError("olcumler: olcum basamağında boş olamaz")
    for o in k.olcumler:
        if o.olculen is None:
            raise CamError(f"olcumler: {o.no} {o.metin}: ölçülen boş")
        if o.alt > o.ust:
            raise CamError(f"olcumler: {o.no} {o.metin}: alt {_s(o.alt)} > üst {_s(o.ust)}")
        if k.sonuc == "gecti" and not (o.alt - PAY <= o.olculen <= o.ust + PAY):
            raise CamError(f"{o.no} {o.metin}: ölçülen {_s(o.olculen)}, sınır [{_s(o.alt)}; {_s(o.ust)}]")


# ---------------------------------------------------------------- özetler


def kanonik(d: dict) -> str:
    """Kanonik JSON metni (sonda "\\n")."""
    try:
        return (
            json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        )
    except ValueError as e:
        raise CamError(f"kanonik JSON: {e}") from None


def profil_ozeti(m: MachineProfile) -> str:
    """`verified` hariç kanonik profil özeti (sha256)."""
    d = m.to_dict()
    d.pop("verified", None)
    return hashlib.sha256(kanonik(d).encode("utf-8")).hexdigest()


def dosya_ozeti(yol: str | Path) -> str:
    """sha256(bytes); dosya yoksa CamError."""
    p = Path(yol)
    if not p.is_file():
        raise CamError(f"dosya yok: {p}")
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- boş kayıt


def _belge_maddeleri() -> list[Madde]:
    """docs bölüm 1–5'in "- [ ] " maddeleri; alt satıra taşan devamı tek boşlukla birleşik."""
    if not _BELGE.is_file():
        raise CamError(f"doğrulama belgesi yok: {_BELGE}")
    out: list[tuple[int, str]] = []
    bolum = None
    for satir in _BELGE.read_text(encoding="utf-8").splitlines():
        b = re.match(r"## (\d+)\.", satir)
        if b:
            bolum = int(b.group(1))
            continue
        if bolum is None or not 1 <= bolum <= 5:
            continue
        if satir.startswith("- [ ] "):
            out.append((bolum, satir[len("- [ ] ") :]))
        elif out and out[-1][0] == bolum and satir.startswith(" ") and satir.strip():
            out[-1] = (bolum, out[-1][1] + " " + satir.strip())
    return [Madde(b, " ".join(t.split()), False) for b, t in out]


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
    if adim not in ADIMLAR:
        raise CamError(f"adim: bilinmeyen {adim!r} (bilinenler: {', '.join(ADIMLAR)})")
    for x in kapsam:
        if x not in KAPSAMLAR:
            raise CamError(f"kapsam: bilinmeyen {x!r} (bilinenler: {', '.join(KAPSAMLAR)})")
    maddeler = _belge_maddeleri()
    olcumler: list[Olcum] = []
    if job is not None:
        maddeler += [Madde(c.section, c.text, False) for c in job.checks]
        if adim == "olcum":
            olcumler = [Olcum(i.no, i.text, i.nominal, i.lower, i.upper, None) for i in job.inspection]
    foy = None
    if is_foyu_yolu is not None:
        foy = IsFoyu(Path(is_foyu_yolu).as_posix(), dosya_ozeti(is_foyu_yolu))
    return DogrulamaKaydi(
        profil=Profil(m.name, profil_ozeti(m)),
        program=Program(Path(program).name, dosya_ozeti(program), m.controller),
        is_foyu=foy,
        kapsam=tuple(kapsam),
        adim=adim,
        sonuc="gecti",
        tarih=tarih,
        operator=operator,
        maddeler=tuple(maddeler),
        olcumler=tuple(olcumler),
    )


# ---------------------------------------------------------------- denetim


def _dosya_adi(k: DogrulamaKaydi, onceki: Sequence[DogrulamaKaydi]) -> str:
    sira = 1 + sum(1 for o in onceki if o.profil.ad == k.profil.ad and o.tarih == k.tarih)
    return f"{k.profil.ad}/{k.tarih}-{sira:03d}-{k.adim}.json"


def _zincir(kayitlar: Sequence[DogrulamaKaydi], anahtar: tuple[str, str]) -> list[DogrulamaKaydi]:
    """Anahtarın (profil.ozet, program.ozet) son `masa` kaydından başlayan zinciri; masa yoksa boş."""
    ks = [k for k in kayitlar if (k.profil.ozet, k.program.ozet) == anahtar]
    bas = [i for i, k in enumerate(ks) if k.adim == "masa"]
    return ks[bas[-1] :] if bas else []


def _son(zincir: Sequence[DogrulamaKaydi], adim: str) -> DogrulamaKaydi | None:
    for k in reversed(zincir):
        if k.adim == adim:
            return k
    return None


def _eksik(zincir: Sequence[DogrulamaKaydi]) -> str | None:
    """Zincirde en son kaydı geçmemiş (yok ya da kaldi) ilk basamak; tamamsa None."""
    for adim in ADIMLAR:
        son = _son(zincir, adim)
        if son is None or son.sonuc == "kaldi":
            return adim
    return None


def _sira(k: DogrulamaKaydi, onceki: Sequence[DogrulamaKaydi]) -> None:
    if k.adim == "masa":
        return
    z = _zincir(onceki, (k.profil.ozet, k.program.ozet))
    if not z:
        raise CamError("sıra: bu profil ve program için önce masa basamağı kaydedilmeli")
    kalan = [x.adim for x in z if x.sonuc == "kaldi"]
    if kalan:
        raise CamError(
            f"sıra: zincirde kaldi var ({kalan[0]}); yalnız masa kaydedilebilir (zincir sıfırlanır)"
        )
    for adim in ADIMLAR[: ADIMLAR.index(k.adim)]:
        if _son(z, adim) is None:
            raise CamError(f"sıra: {adim} basamağı kayıtlı değil ({k.adim} ondan sonra gelir)")


def _baglar(
    k: DogrulamaKaydi, kok: str | Path | None, program: str | Path | None, job: JobSheet | None
) -> None:
    if kok is not None and k.is_foyu is not None:
        yol = Path(k.is_foyu.yol)
        if not yol.is_absolute():
            yol = Path(kok) / yol
        if not yol.is_file():
            raise CamError(f"is_foyu: dosya yok: {yol}")
        if dosya_ozeti(yol) != k.is_foyu.ozet:
            raise CamError(f"is_foyu: {k.is_foyu.yol} özeti kayıttakiyle tutmuyor (dosya değişmiş)")
    if program is not None:
        if not Path(program).is_file():
            raise CamError(f"program: dosya yok: {program}")
        if dosya_ozeti(program) != k.program.ozet:
            raise CamError(f"program: {Path(program).name} özeti kayıttakiyle tutmuyor ({k.program.ad})")
    if job is not None and k.adim == "olcum":
        foy = {i.no: i for i in job.inspection}
        for o in k.olcumler:
            i = foy.get(o.no)
            if i is None:
                raise CamError(f"olcumler: {o.no} {o.metin}: iş föyünün ölçüm listesinde yok")
            ayni = (
                o.metin == i.text
                and abs(o.nominal - i.nominal) <= PAY
                and abs(o.alt - i.lower) <= PAY
                and abs(o.ust - i.upper) <= PAY
            )
            if not ayni:
                raise CamError(
                    f"olcumler: {o.no} {o.metin} [{_s(o.alt)}; {_s(o.ust)}] iş föyündekinden farklı "
                    f"({i.no} {i.text} {_s(i.nominal)} [{_s(i.lower)}; {_s(i.upper)}])"
                )
        if k.sonuc == "gecti":
            olculen = {o.no for o in k.olcumler}
            eksik = [i.no for i in job.inspection if i.no not in olculen]
            if eksik:
                raise CamError(f"olcumler: iş föyündeki kalemler ölçülmedi: {', '.join(map(str, eksik))}")


def denetle(
    k: DogrulamaKaydi,
    onceki: Sequence[DogrulamaKaydi],
    *,
    kok: str | Path | None = None,
    program: str | Path | None = None,
    job: JobSheet | None = None,
) -> None:
    """Şema, sıra, ölçüm ve bağ kuralları (B2); ihlal → CamError (mesaj dosya adıyla başlar)."""
    adi = _dosya_adi(k, onceki)
    try:
        _kurallar(k)
        _sira(k, onceki)
        _baglar(k, kok, program, job)
    except CamError as e:
        raise CamError(f"{adi}: {e}") from None


def kaydet(
    k: DogrulamaKaydi,
    klasor: str | Path,
    *,
    program: str | Path | None = None,
    job: JobSheet | None = None,
) -> Path:
    """denetle(k, oku(klasor), kok=klasor, …) + atomik yazım; yazılan dosyanın yolu."""
    klasor = Path(klasor)
    onceki = oku(klasor)
    denetle(k, onceki, kok=klasor, program=program, job=job)
    adi = _dosya_adi(k, onceki)
    yol = klasor / adi
    if yol.exists():
        raise CamError(f"{adi}: dosya zaten var, üzerine yazılmaz")
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".tmp")
    try:
        gecici.write_bytes(kanonik(k.to_dict()).encode("utf-8"))
        os.replace(gecici, yol)
    finally:
        gecici.unlink(missing_ok=True)
    return yol


def oku(klasor: str | Path) -> list[DogrulamaKaydi]:
    """Klasördeki kayıtlar (tarih, sıra, profil adı düzeninde); bozuk kayıt → CamError (dosya adıyla)."""
    klasor = Path(klasor)
    if not klasor.is_dir():
        return []
    out = []
    for yol in sorted(klasor.glob("*/*.json")):
        adi = f"{yol.parent.name}/{yol.name}"
        e = _DOSYA.fullmatch(yol.name)
        try:
            if e is None:
                raise CamError("dosya adı <tarih>-<sıra>-<adim>.json değil")
            try:
                d = json.loads(yol.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError) as h:
                raise CamError(f"JSON okunamadı: {h}") from None
            k = DogrulamaKaydi.from_dict(d)
            if k.profil.ad != yol.parent.name:
                raise CamError(f"profil.ad {k.profil.ad!r} klasör adıyla aynı değil")
            if k.tarih != e.group(1):
                raise CamError(f"tarih {k.tarih} dosya adındakiyle aynı değil")
            if k.adim != e.group(3):
                raise CamError(f"adim {k.adim} dosya adındakiyle aynı değil")
        except CamError as h:
            raise CamError(f"{adi}: {h}") from None
        out.append((k.tarih, int(e.group(2)), k.profil.ad, k))
    out.sort(key=lambda t: t[:3])
    return [t[3] for t in out]


# ---------------------------------------------------------------- hazırlık ve rapor


def hazirlik(m: MachineProfile, kayitlar: Sequence[DogrulamaKaydi]) -> dict:
    """{"profil": ad, "kapsam": {k: "hazir" | "<eksik adim>"}, "uyarilar": [str]}; profili değiştirmez."""
    oz = profil_ozeti(m)
    gecerli = [k for k in kayitlar if k.profil.ad == m.name and k.profil.ozet == oz]
    eski = sum(1 for k in kayitlar if k.profil.ad == m.name and k.profil.ozet != oz)
    durum = {}
    for kapsam in KAPSAMLAR:
        ks = [k for k in gecerli if kapsam in k.kapsam]
        anahtarlar = dict.fromkeys((k.profil.ozet, k.program.ozet) for k in ks)
        if any(_eksik(_zincir(ks, a)) is None for a in anahtarlar):
            durum[kapsam] = "hazir"
        elif ks:
            durum[kapsam] = _eksik(_zincir(ks, (ks[-1].profil.ozet, ks[-1].program.ozet)))
        else:
            durum[kapsam] = "masa"
    uyarilar = []
    if m.verified and "hazir" not in durum.values():
        uyarilar.append(f"{m.name}: verified=true ama geçen doğrulama kaydı yok")
    if eski:
        uyarilar.append(f"{m.name}: profil değişti, {eski} eski kayıt sayılmadı")
    return {"profil": m.name, "kapsam": durum, "uyarilar": uyarilar}


_STIL = """\
@page { size: A4; margin: 12mm }
body { font-family: sans-serif; font-size: 10pt; color: #000; background: #fff; margin: 0 }
h1 { font-size: 16pt; margin: 0 0 4mm }
h2 { font-size: 12pt; margin: 6mm 0 2mm }
table { border-collapse: collapse; margin: 0 0 3mm; width: 100% }
th, td { border: 0.3mm solid #444; padding: 1mm 1.5mm; text-align: left; vertical-align: top }
th { background: #eee }
tr, li { break-inside: avoid; page-break-inside: avoid }
.not { font-size: 8pt; color: #444 }
"""


def _tablo(id_: str, basliklar: list[str], satirlar: list[list[str]]) -> str:
    out = [
        f'<table id="{id_}">',
        "<thead><tr>" + "".join(f"<th>{escape(b)}</th>" for b in basliklar) + "</tr></thead>",
    ]
    out.append("<tbody>")
    out += ["<tr>" + "".join(f"<td>{escape(h)}</td>" for h in r) + "</tr>" for r in satirlar]
    out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


def rapor_html(m: MachineProfile, kayitlar: Sequence[DogrulamaKaydi]) -> str:
    """Tek dosya, dış kaynaksız HTML rapor (SPEC 38 §8 kuralları)."""
    r = hazirlik(m, kayitlar)
    oz = profil_ozeti(m)

    def gecerlilik(k: DogrulamaKaydi) -> str:
        if k.profil.ad != m.name:
            return "başka profil"
        return "geçerli" if k.profil.ozet == oz else "eski profil"

    zincir = [
        [
            k.tarih,
            k.adim,
            k.sonuc,
            k.program.ad,
            k.program.ozet[:12],
            ", ".join(k.kapsam),
            k.operator,
            f"{sum(x.isaret for x in k.maddeler)}/{len(k.maddeler)}",
            k.gerekce,
            k.notlar,
            gecerlilik(k),
        ]
        for k in kayitlar
    ]
    olcum = []
    for k in kayitlar:
        if k.adim not in _OLCUMLU:
            continue
        for o in k.olcumler:
            if o.olculen is None:
                sonuc, deger = "ölçülmedi", ""
            else:
                ici = o.alt - PAY <= o.olculen <= o.ust + PAY
                sonuc, deger = ("içinde" if ici else "dışında"), _s(o.olculen)
            olcum.append(
                [k.tarih, k.adim, str(o.no), o.metin, _s(o.nominal), _s(o.alt), _s(o.ust), deger, sonuc]
            )
    parcalar = [
        "<!DOCTYPE html>",
        '<html lang="tr">',
        '<head><meta charset="utf-8">',
        f"<title>{escape('Tezgâh doğrulama: ' + m.name)}</title>",
        f"<style>\n{_STIL}</style>",
        "</head>",
        "<body>",
        f"<h1>{escape('Tezgâh doğrulama: ' + m.name)}</h1>",
        '<table id="ozet">',
        f"<tr><th>Profil</th><td>{escape(m.name)}</td></tr>",
        f"<tr><th>Kontrol</th><td>{escape(m.controller)}</td></tr>",
        f"<tr><th>Profil özeti</th><td>{oz[:12]}</td></tr>",
        f"<tr><th>verified</th><td>{'true' if m.verified else 'false'}</td></tr>",
        "</table>",
        "<h2>Kapsam</h2>",
        _tablo("kapsam", ["Kapsam", "Durum"], [[k, v] for k, v in r["kapsam"].items()]),
    ]
    if r["uyarilar"]:
        parcalar.append("<h2>Uyarılar</h2>")
        parcalar.append(
            '<ul id="uyarilar">' + "".join(f"<li>{escape(u)}</li>" for u in r["uyarilar"]) + "</ul>"
        )
    parcalar += [
        "<h2>Basamak kayıtları</h2>",
        _tablo(
            "zincir",
            [
                "Tarih",
                "Basamak",
                "Sonuç",
                "Program",
                "Program özeti",
                "Kapsam",
                "Operatör",
                "Maddeler",
                "Gerekçe",
                "Notlar",
                "Profil",
            ],
            zincir,
        ),
        "<h2>Ölçümler</h2>",
        _tablo(
            "olcum", ["Tarih", "Basamak", "No", "Ölçü", "Nominal", "Alt", "Üst", "Ölçülen", "Sonuç"], olcum
        ),
        '<p class="not">Bu rapor profil dosyasını değiştirmez. Kapsam "hazir" ise '
        "<code>verified</code> alanını profil dosyasında kendiniz <code>true</code> yapın.</p>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parcalar) + "\n"
