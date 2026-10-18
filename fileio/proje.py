"""
Tek proje dosyası `.3dc` (SPEC 37): adlı JSON bölümleri, önbellek, geri al / yinele geçmişi.

Dosya standart bir zip'tir:
    proje.json                 bildirim (sema, ad, bölüm / önbellek / geçmiş özetleri)
    bolumler/<ad>.json         kanonik JSON
    onbellek/<anahtar>.bin     ikili
    gecmis.json                Gecmis, kanonik JSON
Yazım belirlenimci (aynı proje → aynı bayt) ve atomiktir (tmp + os.replace). Bölümlerin içeriği burada
yorumlanmaz; yalnız kanonik JSON oldukları ve "sema" alanları denetlenir. Yalnız standart kitaplık kullanılır.

Şema sürümü ve göç (B1, specs/37-ek-b1-proje-surumu.md): eski sürümlü dosya ya kayıtlı göç adımlarıyla güncele
getirilerek açılır ya da hangi bölümün hangi sürümden getirilemediği yazılarak ProjeError ile reddedilir.
Bölüm sahiplerinin yükümlülüğü: bir ekran bölüm biçimini değiştiren her PR'da o bölümün güncel sürümünü bir
artıran `Goc` adımını `GOCLER`'e kaydeder ve `tests/fileio/goc/` altına eski sürümde yazılmış uydurma
bir örnek `.3dc` ekleyip açıldığını test eder. Göç kaydı olmayan bölüm "sahipsiz" sayılır ve
olduğu gibi korunur.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

SEMA = 1
UZANTI = ".3dc"
GECMIS_SINIRI = 200

UYGULAMA = "3D-CORE"
BILDIRIM = "proje.json"
GECMIS = "gecmis.json"
EN_FAZLA_BOYUT = 2**30  # açılmış toplam boyut sınırı (bayt)
EN_FAZLA_ORAN = 200  # tek girdinin açılmış / sıkışmış boyut oranı sınırı

BOLUM_ADI = re.compile(r"[a-z0-9_]{1,40}")
ANAHTAR_ADI = re.compile(r"[a-z0-9_.]{1,80}")
_GIRDI_BOLUM = re.compile(r"bolumler/([a-z0-9_]{1,40})\.json")
_GIRDI_ONBELLEK = re.compile(r"onbellek/([a-z0-9_.]{1,80})\.bin")

# Belirlenimci zip girdisi: sabit tarih, sistem, izin ve sıkıştırma düzeyi.
_TARIH = (1980, 1, 1, 0, 0, 0)
_IZIN = 0o100644 << 16
_DUZEY = 6


class ProjeError(ValueError):
    """Bozuk ya da geçersiz proje / proje dosyası (sessiz hata yok)."""


@dataclass(frozen=True)
class Onbellek:
    """Pahalı bir sonucun baytları ve onu üreten girdilerin özeti."""

    girdi_ozeti: str
    veri: bytes


@dataclass(frozen=True)
class Gecmis:
    """Doğrusal geri al geçmişi. `konum`: geri alınabilecek kayıt sayısı (0 ≤ konum ≤ len(kayitlar)).

    Kayit = {etiket, ekran, bolumler: {ad: [once | None, sonra | None]}}
    """

    kayitlar: tuple[dict, ...] = ()
    konum: int = 0


@dataclass(frozen=True)
class Proje:
    """Değişmez proje durumu. İşlemler yeni nesne döndürür."""

    ad: str
    bolumler: Mapping[str, dict]
    onbellek: Mapping[str, Onbellek] = field(default_factory=dict)
    gecmis: Gecmis = field(default_factory=Gecmis)
    uyarilar: tuple[dict, ...] = ()  # SPEC 24 Kontrol biçimi; dosyaya yazılmaz
    goc: Mapping[str, tuple[int, int]] = field(
        default_factory=dict
    )  # {bolum: (eski, yeni)}; dosyaya yazılmaz
    kaynak_yol: str | None = None  # ac'ın açtığı dosya; yedek kuralı için (B1 §4)


# ---------------------------------------------------------------- şema göçü (B1)


@dataclass(frozen=True)
class Goc:
    """Bir göç adımı: `bolum` belgesini `kaynak` sürümünden `kaynak + 1`'e taşır; `bolum == ""` dosya düzeyi.

    `uygula` saftır (girdiyi değiştirmez), çıktısının `sema`'sı tam `kaynak + 1`'dir; `aciklama` kullanıcıya
    gösterilir.
    """

    bolum: str
    kaynak: int
    uygula: Callable[[dict], dict]
    aciklama: str


class GocKaydi:
    """Göç adımlarının kaydı. Bir bölüm için en az bir adım kayıtlıysa o bölüm sahiplenilmiş sayılır."""

    def __init__(self) -> None:
        self._adimlar: dict[str, dict[int, Goc]] = {}

    def kaydet(self, g: Goc) -> None:
        """Adımı ekler; aynı (bolum, kaynak) ikinci kez, kaynak < 1 ya da boş açıklama → ProjeError."""
        yer = g.bolum or "dosya"
        if g.bolum and not BOLUM_ADI.fullmatch(g.bolum):
            raise ProjeError(f"göç adımı: geçersiz bölüm adı {g.bolum!r}")
        if type(g.kaynak) is not int or g.kaynak < 1:
            raise ProjeError(
                f"göç adımı {yer}: kaynak sürüm 1 ya da daha büyük tam sayı olmalı ({g.kaynak!r})"
            )
        if not callable(g.uygula):
            raise ProjeError(f"göç adımı {yer} {g.kaynak} → {g.kaynak + 1}: uygula çağrılabilir değil")
        if not isinstance(g.aciklama, str) or not g.aciklama.strip():
            raise ProjeError(f"göç adımı {yer} {g.kaynak} → {g.kaynak + 1}: açıklama boş olamaz")
        adimlar = self._adimlar.setdefault(g.bolum, {})
        if g.kaynak in adimlar:
            raise ProjeError(f"göç adımı {yer} {g.kaynak} → {g.kaynak + 1} zaten kayıtlı")
        adimlar[g.kaynak] = g

    def _sahip(self, bolum: str) -> bool:
        """Bölüm için en az bir adım kayıtlı mı (kayıtsız bölüm göçe sokulmaz)."""
        return bool(self._adimlar.get(bolum))

    def guncel(self, bolum: str) -> int:
        """S_g: bölüm için kayıtlı göçlerin en büyük hedefi; kayıt yoksa 1 (`""` için SEMA)."""
        if bolum == "":
            return SEMA
        adimlar = self._adimlar.get(bolum)
        return max(adimlar) + 1 if adimlar else 1

    def zincir(self, bolum: str, k: int) -> list[Goc]:
        """k → guncel(bolum) adımları sırayla; boşluk ya da k > guncel → ProjeError."""
        hedef = self.guncel(bolum)
        yer = bolum or "dosya"
        if type(k) is not int or k < 1:
            raise ProjeError(f"{yer}: geçersiz sema {k!r}")
        if k > hedef:
            raise ProjeError(f"{yer}: daha yeni bir sürümle yazılmış; programı güncelleyin")
        adimlar = self._adimlar.get(bolum, {})
        eksik = [i for i in range(k, hedef) if i not in adimlar]
        if eksik:
            raise ProjeError(f"{yer}: göç adımı eksik ({eksik[0]} → {eksik[0] + 1})")
        return [adimlar[i] for i in range(k, hedef)]


GOCLER = GocKaydi()  # varsayılan kayıt; ekranlar içe aktarılırken doldurur


def _surum_hatasi(dosya: str, yer: str, ne: str, bulunan: int, guncel: int) -> ProjeError:
    """B1 hata biçimi: "<dosya adı>: <bolum|dosya>: <ne oldu> (sema <bulunan>, beklenen ≤ <güncel>)"."""
    return ProjeError(f"{dosya}: {yer}: {ne} (sema {bulunan}, beklenen ≤ {guncel})")


def _adim_uygula(g: Goc, belge: dict, dosya: str) -> dict:
    """Tek göç adımı: saflık, tek adım ve kanonik çıktı denetimiyle."""
    yer = g.bolum or "dosya"
    ad = f"{dosya}: {yer}: göç {g.kaynak} → {g.kaynak + 1} ({g.aciklama})"
    once = kanonik(belge)
    girdi = _kopya(belge)
    try:
        cikti = g.uygula(girdi)
    except ProjeError as e:
        raise ProjeError(f"{ad}: {e}") from None
    if kanonik(girdi) != once:
        raise ProjeError(f"{ad}: adım girdisini değiştirdi")
    if not isinstance(cikti, dict):
        raise ProjeError(f"{ad}: çıktı JSON nesnesi değil")
    if type(cikti.get("sema")) is not int or cikti["sema"] != g.kaynak + 1:
        raise ProjeError(f"{ad}: çıktının sema'sı {cikti.get('sema')!r}, {g.kaynak + 1} olmalı")
    try:
        return json.loads(kanonik(cikti))
    except (ProjeError, ValueError, TypeError) as e:
        raise ProjeError(f"{ad}: çıktı kanonik JSON değil ({e})") from None


def _belge_goc(belge: dict, bolum: str, gocler: GocKaydi, dosya: str) -> dict:
    """Belgeyi bölüm zincirinden güncele getirir; daha yeni sürüm ya da boşluk → ProjeError."""
    k, hedef = belge["sema"], gocler.guncel(bolum)
    yer = bolum or "dosya"
    if k > hedef:
        raise _surum_hatasi(dosya, yer, "daha yeni bir sürümle yazılmış; programı güncelleyin", k, hedef)
    try:
        zincir = gocler.zincir(bolum, k)
    except ProjeError as e:
        raise _surum_hatasi(dosya, yer, str(e), k, hedef) from None
    for g in zincir:
        belge = _adim_uygula(g, belge, dosya)
    return belge


# ---------------------------------------------------------------- kanonik JSON


def _nan_reddet(s: str):
    raise ValueError(f"JSON'da {s} yok")


def kanonik(belge: dict) -> bytes:
    """sort_keys, ayırıcısız, ensure_ascii=False, allow_nan=False UTF-8 JSON; nan / inf → ProjeError."""
    try:
        metin = json.dumps(belge, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as e:
        raise ProjeError(f"kanonik JSON'a çevrilemiyor: {e}") from None
    return metin.encode("utf-8")


def ozet(belge: dict) -> str:
    """sha256(kanonik(belge)) onaltılık."""
    return hashlib.sha256(kanonik(belge)).hexdigest()


def _sha(veri: bytes) -> str:
    return hashlib.sha256(veri).hexdigest()


def _kopya(belge):
    """Derin ve bağımsız kopya (kanonik JSON gidiş-dönüşü; float kayıpsız)."""
    return None if belge is None else json.loads(kanonik(belge))


def _kanonik_coz(veri: bytes, ad: str):
    """Kanonik JSON baytını çözer; geçersiz UTF-8 / JSON, nan ya da kanonik olmayan biçim → ProjeError."""
    try:
        belge = json.loads(veri.decode("utf-8"), parse_constant=_nan_reddet)
    except (UnicodeDecodeError, ValueError) as e:
        raise ProjeError(f"{ad}: geçerli JSON değil ({e})") from None
    if kanonik(belge) != veri:
        raise ProjeError(f"{ad}: kanonik JSON değil")
    return belge


# ---------------------------------------------------------------- doğrulama


def _bolum_denetle(ad: str, belge) -> None:
    if not isinstance(ad, str) or not BOLUM_ADI.fullmatch(ad):
        raise ProjeError(f"geçersiz bölüm adı: {ad!r} ([a-z0-9_]{{1,40}})")
    if not isinstance(belge, dict):
        raise ProjeError(f"bölüm {ad!r} bir JSON nesnesi değil")
    sema = belge.get("sema")
    if type(sema) is not int or sema < 1:
        raise ProjeError(f"bölüm {ad!r}: 'sema' 1 ya da daha büyük tam sayı olmalı (bulunan {sema!r})")


def _anahtar_denetle(anahtar: str) -> None:
    if not isinstance(anahtar, str) or not ANAHTAR_ADI.fullmatch(anahtar):
        raise ProjeError(f"geçersiz önbellek anahtarı: {anahtar!r} ([a-z0-9_.]{{1,80}})")


def _proje_denetle(p: Proje) -> None:
    if not isinstance(p.ad, str) or not p.ad.strip():
        raise ProjeError("proje adı boş")
    for ad, belge in p.bolumler.items():
        _bolum_denetle(ad, belge)
    for anahtar, o in p.onbellek.items():
        _anahtar_denetle(anahtar)
        if not isinstance(o.veri, (bytes, bytearray)) or not isinstance(o.girdi_ozeti, str):
            raise ProjeError(f"önbellek {anahtar!r}: veri bayt, girdi_ozeti metin olmalı")
    g = p.gecmis
    if type(g.konum) is not int or not 0 <= g.konum <= len(g.kayitlar):
        raise ProjeError(f"geçmiş konumu geçersiz: {g.konum!r}")


def _uyari(kimlik: str, aciklama: str) -> dict:
    return {
        "kimlik": kimlik,
        "baslik": "Proje dosyası",
        "deger": None,
        "birim": "",
        "durum": "uyari",
        "aciklama": aciklama,
        "spec": "SPEC 37",
    }


# ---------------------------------------------------------------- proje ve geçmiş


def bos_proje(ad: str) -> Proje:
    """Yalnız "kabuk" bölümü olan boş proje."""
    return Proje(ad=ad, bolumler={"kabuk": {"sema": 1, "aktif_ekran": "freze"}})


def uygula(p: Proje, etiket: str, ekran: str, yeni: Mapping[str, dict | None]) -> Proje:
    """Değişen bölümleri tek kayıtla geçmişe ekler (None: bölüm silinir); hiçbiri değişmediyse kayıt yok."""
    bolumler = dict(p.bolumler)
    fark: dict[str, list] = {}
    for ad, belge in yeni.items():
        if belge is not None:
            _bolum_denetle(ad, belge)
        once = bolumler.get(ad)
        if (None if once is None else kanonik(once)) == (None if belge is None else kanonik(belge)):
            continue
        sonra = _kopya(belge)
        fark[ad] = [_kopya(once), _kopya(sonra)]
        if sonra is None:
            del bolumler[ad]
        else:
            bolumler[ad] = sonra
    if not fark:
        return p
    kayitlar = list(p.gecmis.kayitlar[: p.gecmis.konum])
    kayitlar.append({"etiket": etiket, "ekran": ekran, "bolumler": fark})
    kayitlar = kayitlar[-GECMIS_SINIRI:]
    return replace(p, bolumler=bolumler, gecmis=Gecmis(tuple(kayitlar), len(kayitlar)))


def _kaydi_uygula(p: Proje, kayit: dict, taraf: int, konum: int) -> Proje:
    bolumler = dict(p.bolumler)
    for ad, cift in kayit["bolumler"].items():
        belge = cift[taraf]
        if belge is None:
            bolumler.pop(ad, None)
        else:
            bolumler[ad] = _kopya(belge)
    return replace(p, bolumler=bolumler, gecmis=Gecmis(p.gecmis.kayitlar, konum))


def geri_al(p: Proje) -> Proje:
    """Son kaydı geri alır; konum 0 ise ProjeError."""
    k = p.gecmis.konum
    if k == 0:
        raise ProjeError("geri alınacak değişiklik yok")
    return _kaydi_uygula(p, p.gecmis.kayitlar[k - 1], 0, k - 1)


def yinele(p: Proje) -> Proje:
    """Geri alınan kaydı yineler; yinelenecek kayıt yoksa ProjeError."""
    k = p.gecmis.konum
    if k == len(p.gecmis.kayitlar):
        raise ProjeError("yinelenecek değişiklik yok")
    return _kaydi_uygula(p, p.gecmis.kayitlar[k], 1, k + 1)


# ---------------------------------------------------------------- yazma


def _girdiler(p: Proje) -> dict[str, bytes]:
    """Projenin zip girdileri (ad → bayt). Geçersizse ProjeError; diske hiçbir şey yazılmaz."""
    _proje_denetle(p)
    girdiler: dict[str, bytes] = {}
    bildirim = {"sema": SEMA, "uygulama": UYGULAMA, "ad": p.ad, "bolumler": {}, "onbellek": {}}
    for ad, belge in p.bolumler.items():
        veri = kanonik(belge)
        girdiler[f"bolumler/{ad}.json"] = veri
        bildirim["bolumler"][ad] = {"sema": belge["sema"], "ozet": _sha(veri)}
    for anahtar, o in p.onbellek.items():
        veri = bytes(o.veri)
        girdiler[f"onbellek/{anahtar}.bin"] = veri
        bildirim["onbellek"][anahtar] = {"girdi_ozeti": o.girdi_ozeti, "boyut": len(veri), "ozet": _sha(veri)}
    gecmis = kanonik({"kayitlar": list(p.gecmis.kayitlar), "konum": p.gecmis.konum})
    girdiler[GECMIS] = gecmis
    bildirim["gecmis"] = {"ozet": _sha(gecmis), "konum": p.gecmis.konum, "sayi": len(p.gecmis.kayitlar)}
    girdiler[BILDIRIM] = kanonik(bildirim)
    return girdiler


def _zip_yaz(dosya, girdiler: dict[str, bytes]) -> None:
    with zipfile.ZipFile(dosya, "w", zipfile.ZIP_DEFLATED, compresslevel=_DUZEY) as z:
        for ad in sorted(girdiler):
            bilgi = zipfile.ZipInfo(ad, date_time=_TARIH)
            bilgi.compress_type = zipfile.ZIP_DEFLATED
            bilgi.create_system = 3
            bilgi.external_attr = _IZIN
            z.writestr(bilgi, girdiler[ad], compress_type=zipfile.ZIP_DEFLATED, compresslevel=_DUZEY)


def kaydet(p: Proje, yol: str | Path) -> None:
    """Belirlenimci, atomik yazım; uzantı .3dc değilse ya da bölüm geçersizse ProjeError (diske yazılmaz).

    B1 §4: `p.goc` doluysa ve `yol` `p.kaynak_yol` ise özgün dosya önce `.yedek` olarak kopyalanır; yedek
    yazılamazsa kayıt yapılmaz.
    """
    yol = Path(yol)
    if yol.suffix != UZANTI:
        raise ProjeError(f"proje dosyası {UZANTI} uzantılı olmalı: {yol.name}")
    girdiler = _girdiler(p)
    _yedekle(p, yol)
    gecici = yol.with_name(yol.name + ".tmp")
    try:
        with open(gecici, "wb") as f:
            _zip_yaz(f, girdiler)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, yol)
    except BaseException:
        try:
            gecici.unlink()
        except FileNotFoundError:
            pass
        raise


def _eski_surumler(yol: Path) -> dict[str, int] | None:
    """Diskteki dosyanın bildirim sürümleri {"": D, bolum: S_b}; okunamazsa None."""
    try:
        with zipfile.ZipFile(yol) as z:
            b = json.loads(z.read(BILDIRIM).decode("utf-8"))
        surumler = {"": int(b["sema"])}
        surumler.update({ad: int(bilgi["sema"]) for ad, bilgi in b["bolumler"].items()})
        return surumler
    except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile):
        return None


def _yedekle(p: Proje, yol: Path) -> None:
    """B1 §4: göç edilmiş proje açıldığı dosyanın üstüne yazılırken özgün baytlar `.yedek` olarak kopyalanır.

    Diskteki dosya artık eski sürümde değilse (proje bir kez kaydedilmiş) yedek gerekmez. Yedek yazılamazsa
    ProjeError: kayıt yapılmaz, kullanıcının eski dosyası yedeksiz ezilmez.
    """
    if not p.goc or p.kaynak_yol is None or not yol.exists():
        return
    if yol.resolve() != Path(p.kaynak_yol).resolve():
        return
    surumler = _eski_surumler(yol)
    eski = surumler is None or surumler[""] < SEMA
    eski = eski or any(surumler.get(b, yeni) < yeni for b, (_, yeni) in p.goc.items() if b)
    if not eski:
        return
    try:
        ozgun = yol.read_bytes()
    except OSError as e:
        raise ProjeError(f"{yol.name}: özgün dosya okunamadı, kayıt yapılmadı ({e})") from None
    d = (surumler or {}).get("", SEMA)
    bolum_surumleri = {b: s for b, s in sorted((surumler or {}).items()) if b}
    kok = f"{yol.stem}.sema{d}-{_sha(kanonik(bolum_surumleri))[:8]}"
    for n in range(1, 1000):
        yedek = yol.with_name(f"{kok}{'' if n == 1 else f'-{n}'}{UZANTI}.yedek")
        if not yedek.exists():
            break
        if yedek.read_bytes() == ozgun:
            return
    else:
        raise ProjeError(f"{yol.name}: yedek adı bulunamadı, kayıt yapılmadı")
    gecici = yedek.with_name(yedek.name + ".tmp")
    try:
        with open(gecici, "wb") as f:
            f.write(ozgun)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, yedek)
    except OSError as e:
        try:
            gecici.unlink()
        except FileNotFoundError:
            pass
        raise ProjeError(f"{yol.name}: yedek yazılamadı, kayıt yapılmadı ({e})") from None


def proje_baytlari(p: Proje) -> bytes:
    """Projenin .3dc baytları (kaydet ile aynı içerik; diske yazmaz)."""
    tampon = io.BytesIO()
    _zip_yaz(tampon, _girdiler(p))
    return tampon.getvalue()


# ---------------------------------------------------------------- okuma


def _boyut_denetle(z: zipfile.ZipFile) -> None:
    toplam = 0
    for bilgi in z.infolist():
        if bilgi.file_size > EN_FAZLA_BOYUT:
            raise ProjeError(f"{bilgi.filename}: açılmış boyut {bilgi.file_size} bayt, sınır 1 GiB")
        if bilgi.file_size > 0 and bilgi.file_size > EN_FAZLA_ORAN * max(bilgi.compress_size, 1):
            raise ProjeError(f"{bilgi.filename}: sıkıştırma oranı {EN_FAZLA_ORAN}'ü aşıyor (zip bombası)")
        toplam += bilgi.file_size
    if toplam > EN_FAZLA_BOYUT:
        raise ProjeError(f"proje dosyasının açılmış toplam boyutu {toplam} bayt, sınır 1 GiB")


def _adlari_denetle(z: zipfile.ZipFile) -> list[str]:
    adlar = z.namelist()
    if len(set(adlar)) != len(adlar):
        raise ProjeError("zip'te aynı adlı girdi birden fazla")
    for ad in adlar:
        if ad in (BILDIRIM, GECMIS) or _GIRDI_BOLUM.fullmatch(ad) or _GIRDI_ONBELLEK.fullmatch(ad):
            continue
        raise ProjeError(f"izin verilmeyen girdi adı: {ad!r}")
    return adlar


def _bildirim_oku(z: zipfile.ZipFile, adlar: list[str], dosya: str = "") -> dict:
    if BILDIRIM not in adlar:
        raise ProjeError(f"{BILDIRIM} yok: proje dosyası değil")
    try:
        b = json.loads(z.read(BILDIRIM).decode("utf-8"), parse_constant=_nan_reddet)
    except (UnicodeDecodeError, ValueError) as e:
        raise ProjeError(f"{BILDIRIM}: geçerli JSON değil ({e})") from None
    if not isinstance(b, dict):
        raise ProjeError(f"{BILDIRIM}: JSON nesnesi değil")
    sema = b.get("sema")
    if type(sema) is not int or sema < 1:
        raise ProjeError(f"{BILDIRIM}: geçersiz sema {sema!r}")
    if sema > SEMA:
        ne = f"bu 3D-CORE en çok {SEMA} okuyabilir; programı güncelleyin"
        raise _surum_hatasi(dosya, f"dosya ({BILDIRIM})", ne, sema, SEMA)
    for alan, tur in (("ad", str), ("bolumler", dict), ("onbellek", dict), ("gecmis", dict)):
        if not isinstance(b.get(alan), tur):
            raise ProjeError(f"{BILDIRIM}: '{alan}' alanı eksik ya da geçersiz")
    return b


def _bolumleri_oku(z: zipfile.ZipFile, adlar: list[str], b: dict) -> dict[str, dict]:
    bolumler: dict[str, dict] = {}
    for ad, bilgi in b["bolumler"].items():
        girdi = f"bolumler/{ad}.json"
        if not isinstance(ad, str) or not BOLUM_ADI.fullmatch(ad) or not isinstance(bilgi, dict):
            raise ProjeError(f"{BILDIRIM}: geçersiz bölüm kaydı {ad!r}")
        if girdi not in adlar:
            raise ProjeError(f"{girdi}: bildirimde var, zip'te yok")
        veri = z.read(girdi)
        if _sha(veri) != bilgi.get("ozet"):
            raise ProjeError(f"{girdi}: özet tutmuyor (dosya bozuk)")
        belge = _kanonik_coz(veri, girdi)
        _bolum_denetle(ad, belge)
        if belge["sema"] != bilgi.get("sema"):
            raise ProjeError(f"{girdi}: sema bildirimdekiyle aynı değil")
        bolumler[ad] = belge
    return bolumler


def _gecmisi_oku(z: zipfile.ZipFile, adlar: list[str], b: dict) -> Gecmis:
    if GECMIS not in adlar:
        raise ProjeError(f"{GECMIS} yok")
    veri = z.read(GECMIS)
    if _sha(veri) != b["gecmis"].get("ozet"):
        raise ProjeError(f"{GECMIS}: özet tutmuyor (dosya bozuk)")
    g = _kanonik_coz(veri, GECMIS)
    if not isinstance(g, dict):
        raise ProjeError(f"{GECMIS}: geçersiz geçmiş")
    kayitlar, konum = g.get("kayitlar"), g.get("konum")
    if not isinstance(kayitlar, list) or type(konum) is not int or not 0 <= konum <= len(kayitlar):
        raise ProjeError(f"{GECMIS}: geçersiz geçmiş")
    if len(kayitlar) > GECMIS_SINIRI:
        raise ProjeError(f"{GECMIS}: {len(kayitlar)} kayıt, sınır {GECMIS_SINIRI}")
    for i, k in enumerate(kayitlar):
        if (
            not isinstance(k, dict)
            or not isinstance(k.get("etiket"), str)
            or not isinstance(k.get("ekran"), str)
            or not isinstance(k.get("bolumler"), dict)
            or not all(isinstance(c, list) and len(c) == 2 for c in k["bolumler"].values())
        ):
            raise ProjeError(f"{GECMIS}: {i}. kayıt geçersiz")
    return Gecmis(tuple(kayitlar), konum)


def _onbellegi_oku(z, adlar, b, uyarilar: list[dict]) -> dict[str, Onbellek]:
    onbellek: dict[str, Onbellek] = {}
    for anahtar, bilgi in b["onbellek"].items():
        girdi = f"onbellek/{anahtar}.bin"
        neden = None
        if not isinstance(anahtar, str) or not ANAHTAR_ADI.fullmatch(anahtar) or not isinstance(bilgi, dict):
            neden = "bildirim kaydı geçersiz"
        elif girdi not in adlar:
            neden = "zip'te yok"
        else:
            veri = z.read(girdi)
            if _sha(veri) != bilgi.get("ozet") or len(veri) != bilgi.get("boyut"):
                neden = "özet tutmuyor"
            elif not isinstance(bilgi.get("girdi_ozeti"), str):
                neden = "girdi özeti yok"
            else:
                onbellek[anahtar] = Onbellek(bilgi["girdi_ozeti"], veri)
        if neden:
            uyarilar.append(_uyari("proje_onbellek", f"{girdi}: {neden}; atıldı, yeniden hesaplanacak"))
    return onbellek


def ac(yol: str | Path, gocler: GocKaydi = GOCLER) -> Proje:
    """Dosyayı okur ve denetler; bozuk girdi → ProjeError (mesajda girdi adı).

    B1: denetimlerden sonra eski sürümlü dosya / bölüm / geçmiş `gocler` zinciriyle güncele getirilir.
    """
    yol = Path(yol)
    try:
        z = zipfile.ZipFile(yol)
    except zipfile.BadZipFile:
        raise ProjeError(f"{yol.name}: zip değil, proje dosyası olamaz") from None
    with z:
        try:
            adlar = _adlari_denetle(z)
            _boyut_denetle(z)
            b = _bildirim_oku(z, adlar, yol.name)
            bolumler = _bolumleri_oku(z, adlar, b)
            gecmis = _gecmisi_oku(z, adlar, b)
            uyarilar: list[dict] = []
            onbellek = _onbellegi_oku(z, adlar, b, uyarilar)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError) as e:
            raise ProjeError(f"{yol.name}: zip okunamadı ({e})") from None
        bilinen = {BILDIRIM, GECMIS} | {f"bolumler/{a}.json" for a in bolumler}
        bilinen |= {f"onbellek/{a}.bin" for a in b["onbellek"]}
        for ad in adlar:
            if ad not in bilinen:
                uyarilar.append(_uyari("proje_fazla_girdi", f"{ad}: bildirimde yok; okunmadı"))
    if not b["ad"].strip():
        raise ProjeError(f"{BILDIRIM}: proje adı boş")
    p = Proje(b["ad"], bolumler, onbellek, gecmis, tuple(uyarilar), kaynak_yol=str(yol.resolve()))
    return _goc_uygula(p, b["sema"], gocler, yol.name)


def _goc_uygula(p: Proje, d: int, gocler: GocKaydi, dosya: str) -> Proje:
    """B1 §3: denetlenmiş projede dosya düzeyi, bölümler ve geçmiş güncel şemaya getirilir."""
    goc: dict[str, tuple[int, int]] = {}
    uyarilar = list(p.uyarilar)
    if d < SEMA:
        # Dosya düzeyi adımları bildirimi taşır; bildirim okunduktan sonra yalnız sürüm bilgisi kalır.
        _belge_goc({"sema": d}, "", gocler, dosya)
        goc[""] = (d, SEMA)
        aciklama = "; ".join(g.aciklama for g in gocler.zincir("", d))
        uyarilar.append(_uyari("proje_goc", f"dosya: sema {d} → {SEMA} ({aciklama})"))
    sahipli = sorted(b for b in set(p.bolumler) | _gecmis_bolumleri(p.gecmis) if gocler._sahip(b))
    bolumler = dict(p.bolumler)
    kayitlar = [dict(k, bolumler=dict(k["bolumler"])) for k in p.gecmis.kayitlar]
    for b in sahipli:
        hedef = gocler.guncel(b)
        belgeler = [bolumler[b]] if b in bolumler else []
        belgeler += [x for k in kayitlar for x in k["bolumler"].get(b, ()) if x is not None]
        en_eski = min((x["sema"] for x in belgeler), default=hedef)
        if b in bolumler:
            bolumler[b] = _belge_goc(bolumler[b], b, gocler, dosya)
        for k in kayitlar:
            if b in k["bolumler"]:
                k["bolumler"][b] = [
                    None if x is None else _belge_goc(x, b, gocler, dosya) for x in k["bolumler"][b]
                ]
        if en_eski < hedef:
            goc[b] = (en_eski, hedef)
            aciklama = "; ".join(g.aciklama for g in gocler.zincir(b, en_eski))
            uyarilar.append(_uyari("proje_goc", f"{b}: sema {en_eski} → {hedef} ({aciklama})"))
    if not goc:
        return p
    gecmis = Gecmis(tuple(kayitlar), p.gecmis.konum)
    return replace(p, bolumler=bolumler, gecmis=gecmis, uyarilar=tuple(uyarilar), goc=goc)


def _gecmis_bolumleri(g: Gecmis) -> set[str]:
    return {b for k in g.kayitlar for b in k["bolumler"]}


def incele(yol: str | Path, gocler: GocKaydi = GOCLER) -> dict:
    """Dosyayı açmadan sürümlerini raporlar (göç fonksiyonu çağırmaz, dosyayı değiştirmez).

    {"dosya": (D, D_g), "bolumler": {b: (S_b, S_g)}, "acilir": bool, "neden": str | None}
    """
    yol = Path(yol)
    rapor: dict = {"dosya": None, "bolumler": {}, "acilir": True, "neden": None}
    try:
        with zipfile.ZipFile(yol) as z:
            b = json.loads(z.read(BILDIRIM).decode("utf-8"), parse_constant=_nan_reddet)
        d = b["sema"]
        rapor["dosya"] = (d, SEMA)
        for ad, bilgi in sorted(b["bolumler"].items()):
            s = bilgi["sema"]
            rapor["bolumler"][ad] = (s, gocler.guncel(ad) if gocler._sahip(ad) else s)
    except (OSError, KeyError, TypeError, ValueError, AttributeError, zipfile.BadZipFile) as e:
        return {**rapor, "acilir": False, "neden": f"{yol.name}: proje bildirimi okunamadı ({e})"}
    try:
        if type(d) is not int or d > SEMA:
            raise _surum_hatasi(yol.name, "dosya", "bu 3D-CORE bu dosya şemasını okuyamaz", d, SEMA)
        if d < SEMA:
            gocler.zincir("", d)
        for ad, (s, hedef) in rapor["bolumler"].items():
            if gocler._sahip(ad):
                if s > hedef:
                    raise _surum_hatasi(yol.name, ad, "daha yeni bir sürümle yazılmış", s, hedef)
                try:
                    gocler.zincir(ad, s)
                except ProjeError as e:
                    raise _surum_hatasi(yol.name, ad, str(e), s, hedef) from None
        ac(yol, GocKaydi())  # SPEC 37 okuma denetimleri; boş kayıtla hiçbir göç çağrılmaz
    except ProjeError as e:
        return {**rapor, "acilir": False, "neden": str(e)}
    return rapor
