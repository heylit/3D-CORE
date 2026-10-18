"""
SPEC 54 §5 — Otomatik kayıt: kurtarma dosyasının kitaplık kısmı.

Zamanlama kararı saftır (saat parametre olarak gelir); iş parçacığı ve saat yalnız kabukta
(`tezgah/ekranlar/kabuk.py`). Asıl proje dosyası `P` hiçbir zaman yazılmaz, silinmez, taşınmaz.

    P = <klasör>/<ad>.3dc  →  <klasör>/.<ad>.3dc.kurtarma  (+ .json yan dosyası)

Bağımlılık: yalnız stdlib ve `fileio.proje` (K12).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from fileio.proje import Proje, ProjeError, ac, kanonik, proje_baytlari

UZANTI = ".kurtarma"
ESKI = ".eski"


@dataclass(frozen=True)
class KurtarmaAyari:
    """T: s cinsinden yazım aralığı (≥ 10); K: yazım için yeni geçmiş kaydı sayısı (≥ 1)."""

    T: float = 60.0
    K: int = 10

    def __post_init__(self) -> None:
        if not self.T >= 10.0:
            raise ProjeError(f"kurtarma ayarı: T = {self.T} s çok kısa — T'yi en az 10 s yapın")
        if not self.K >= 1:
            raise ProjeError(f"kurtarma ayarı: K = {self.K} geçersiz — K'yi en az 1 kayıt yapın")


def kurtarma_yolu(proje_yolu: Path | None, ad: str, ilk_ozet: str, klasor: Path | None = None) -> Path:
    """Kurtarma dosyasının yolu; hiç kaydedilmemiş proje için `.kurtarma/<ad>-<ilk_ozet[:8]>.3dc.kurtarma`."""
    if proje_yolu is not None:
        P = Path(proje_yolu)
        return P.parent / f".{P.name}{UZANTI}"
    if klasor is None:
        klasor = Path.home() / "3D-CORE projeleri" / ".kurtarma"
    return Path(klasor) / f"{ad}-{ilk_ozet[:8]}.3dc{UZANTI}"


def yazmali_mi(simdi: float, son_yazim: float | None, yeni_kayit: int, kirli: bool, a: KurtarmaAyari) -> bool:
    """Saf zamanlama kararı: kirliyse ve (T doldu ya da K kayıt eklendi) ise yaz."""
    if not kirli:
        return False
    if son_yazim is None:
        return True
    return simdi - son_yazim >= a.T or yeni_kayit >= a.K


def _yan(yol: Path) -> Path:
    return yol.with_name(yol.name + ".json")


def _atomik_yaz(yol: Path, veri: bytes) -> None:
    gecici = yol.with_name(yol.name + ".tmp")
    try:
        with open(gecici, "wb") as f:
            f.write(veri)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, yol)
    except BaseException:
        try:
            gecici.unlink()
        except FileNotFoundError:
            pass
        raise


def kurtarma_yaz(p: Proje, yol: Path, kaynak_ozet: str | None, sayac: int) -> None:
    """Önbelleksiz .3dc ve .json yan dosyasını atomik yazar; yarıda hata → eski dosyalar aynı, .tmp yok."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    veri = proje_baytlari(replace(p, onbellek={}))
    yan = {"kaynak": p.ad, "kaynak_ozet": kaynak_ozet, "sayac": sayac}
    _atomik_yaz(yol, veri)
    _atomik_yaz(_yan(yol), json.dumps(yan, ensure_ascii=False).encode("utf-8"))


def _durum(p: Proje) -> bytes:
    gecmis = {"kayitlar": [dict(k) for k in p.gecmis.kayitlar], "konum": p.gecmis.konum}
    return kanonik({"bolumler": dict(p.bolumler), "gecmis": gecmis})


def _sha(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def kurtarma_bul(proje_yolu: Path) -> dict | None:
    """{"yol", "okunur", "kaynak_tutuyor", "farkli", "neden"}; kurtarma dosyası yoksa None."""
    P = Path(proje_yolu)
    yol = kurtarma_yolu(P, P.stem, "")
    if not yol.exists():
        return None
    sonuc = {"yol": str(yol), "okunur": False, "kaynak_tutuyor": False, "farkli": False, "neden": None}
    try:
        kurtarilan = ac(yol)
    except (ProjeError, OSError) as e:
        sonuc["neden"] = (
            f"{yol.name}: kurtarma dosyası okunamadı ({e}) — asıl proje açıldı; "
            "kurtarma dosyasını silebilirsiniz"
        )
        return sonuc
    try:
        yan = json.loads(_yan(yol).read_text(encoding="utf-8"))
        if not isinstance(yan, dict) or "kaynak_ozet" not in yan:
            raise ValueError("kaynak_ozet alanı yok")
    except (OSError, ValueError) as e:
        sonuc["neden"] = (
            f"{_yan(yol).name}: kurtarma bilgisi okunamadı ({e}) — asıl proje açıldı; "
            "kurtarma dosyasını silebilirsiniz"
        )
        return sonuc
    sonuc["okunur"] = True
    if not P.exists():
        sonuc["kaynak_tutuyor"] = sonuc["farkli"] = True
        return sonuc
    sonuc["kaynak_tutuyor"] = yan["kaynak_ozet"] == _sha(P)
    try:
        sonuc["farkli"] = _durum(kurtarilan) != _durum(ac(P))
    except ProjeError:
        sonuc["farkli"] = True
    return sonuc


def kurtarma_temizle(proje_yolu: Path) -> None:
    """Kurtarma .3dc ve .json'unu siler; yoksa sessizce geçer."""
    P = Path(proje_yolu)
    yol = kurtarma_yolu(P, P.stem, "")
    for a in (yol, _yan(yol)):
        try:
            a.unlink()
        except FileNotFoundError:
            pass


def kurtarma_eskit(proje_yolu: Path) -> Path:
    """ "Yok say": kurtarma dosyalarını .eski'ye taşır, yeni yolu döndürür; dosya yoksa ProjeError."""
    P = Path(proje_yolu)
    yol = kurtarma_yolu(P, P.stem, "")
    if not yol.exists():
        raise ProjeError(f"{yol.name}: kurtarma dosyası yok — yok sayılacak bir şey kalmadı, projeyle sürün")
    eski = yol.with_name(yol.name + ESKI)
    os.replace(yol, eski)
    if _yan(yol).exists():
        os.replace(_yan(yol), _yan(eski))
    return eski
