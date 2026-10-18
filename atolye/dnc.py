"""
SPEC 63 — DNC (dosya yoluyla): denetlenmiş programı kontrolör kurallarına uygun adla, satır sonuyla ve
atomik olarak hedef klasöre yazar; var olan dosyayı sessizce ezmez; her gönderimi kayda
(`gonderim-kaydi.jsonl`) ekler.

Ağ, seri hat ve alt süreç yoktur (karar 3): yalnız yerel dosya yazımı.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cam.model import MachineProfile, Toolpath


@dataclass(frozen=True)
class DosyaKurali:
    """Bir kontrolörün dosya kuralı (`atolye/dnc_kurallari.json` satırı)."""

    kontrolor: str
    ad_deseni: str  # regex, tam eşleşme
    uzanti: str
    satir_sonu: str  # "\n" | "\r\n"
    satir_uzunlugu: int
    sinirlayici: str | None  # "%" ya da None


@dataclass(frozen=True)
class Gonderim:
    """Bir gönderimin sonucu."""

    yol: Path
    sonuc: str  # "yazildi" | "ayni" | "ezildi"
    kayit: dict  # §5 satırı


def dosya_kurali(m: MachineProfile) -> DosyaKurali:
    """Profilin kontrolörüne ait dosya kuralı; tabloda yoksa CamError."""
    raise NotImplementedError("SPEC 63")


def dosya_adi(m: MachineProfile, program_no: int, ad: str | None = None) -> str:
    """Kontrolör kuralına uyan dosya adı (uzantı dahil); uymayan ad CamError."""
    raise NotImplementedError("SPEC 63")


def denetle(
    metin: str, m: MachineProfile, yollar: Sequence[Toolpath], kontroller: Sequence[dict]
) -> list[str]:
    """Ö1–Ö5 ön koşulları: hata varsa CamError, yoksa uyarı listesi."""
    raise NotImplementedError("SPEC 63")


def gonder(
    metin: str,
    m: MachineProfile,
    yollar: Sequence[Toolpath],
    kontroller: Sequence[dict],
    hedef: str | Path,
    operator: str,
    zaman: str,
    program_no: int,
    ad: str | None = None,
    ezme: bool = False,
    gerekce: str = "",
    is_foyu: Path | None = None,
    kayit_dosyasi: str | Path = "yerel_parcalar/gonderim-kaydi.jsonl",
) -> Gonderim:
    """Denetle, kurala göre biçimle, ezme korumasıyla atomik yaz ve kayda ekle."""
    raise NotImplementedError("SPEC 63")


def kayitlari_oku(kayit_dosyasi: str | Path) -> list[dict]:
    """Gönderim kaydının satırları (yazım sırasıyla)."""
    raise NotImplementedError("SPEC 63")
