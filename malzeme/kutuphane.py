"""
Malzeme kütüphanesi (SPEC 66): yerleşik kaynaklı kayıtlar + kullanıcı dosyası.

Yerleşik kayıtlar `malzeme/yerlesik.json` içindedir; her kaydın `kaynak` satırı vardır.
Kullanıcı kayıtları (atölye fiyatı, düzeltilmiş kesme verisi) varsayılan olarak `yerel_parcalar/`
altında durur.
JSON biçimi: {"surum": 1, "malzemeler": [Malzeme.to_dict(), ...]}.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Iterable, Iterator
from functools import lru_cache
from importlib import resources
from pathlib import Path

from malzeme.model import GRUPLAR, Malzeme, ModelError

SURUM = 1


class Kutuphane:
    """Değişmez malzeme kümesi: id → Malzeme. ekle() yeni bir Kutuphane döndürür."""

    def __init__(self, kayitlar: Iterable[Malzeme]) -> None:
        """Yinelenen id → ModelError."""
        sozluk: dict[str, Malzeme] = {}
        for m in kayitlar:
            if m.id in sozluk:
                raise ModelError(f"Kütüphanede yinelenen malzeme id: {m.id!r}")
            sozluk[m.id] = m
        self._kayitlar = dict(sorted(sozluk.items()))

    def get(self, id: str) -> Malzeme:
        """Bilinmeyen id → ModelError (mesajda yakın eşleşmeler, difflib)."""
        if id not in self._kayitlar:
            yakin = difflib.get_close_matches(id, list(self._kayitlar), n=3, cutoff=0.6)
            ek = f"; yakın eşleşmeler: {', '.join(yakin)}" if yakin else ""
            raise ModelError(f"Bilinmeyen malzeme id: {id!r}{ek}")
        return self._kayitlar[id]

    def __contains__(self, id: object) -> bool:
        return id in self._kayitlar

    def __iter__(self) -> Iterator[Malzeme]:
        """id sırasıyla."""
        return iter(self._kayitlar.values())

    def __len__(self) -> int:
        return len(self._kayitlar)

    def ara(self, metin: str) -> list[Malzeme]:
        """id, name, standart içinde büyük/küçük harf duyarsız arama."""
        aranan = metin.casefold()
        return [m for m in self if any(aranan in alan.casefold() for alan in (m.id, m.name, m.standart))]

    def grup(self, grup: str) -> list[Malzeme]:
        """B2 GRUPLAR dışı grup → ModelError."""
        if grup not in GRUPLAR:
            raise ModelError(f"Bilinmeyen malzeme grubu: {grup!r} (geçerli: {', '.join(GRUPLAR)})")
        return [m for m in self if m.grup == grup]

    def ekle(self, m: Malzeme) -> Kutuphane:
        """m.kullanici True olmalı; id çakışması → ModelError. Eski kütüphane değişmez."""
        if not m.kullanici:
            raise ModelError(f"{m.id!r}: yalnız kullanıcı kaydı (kullanici=True) eklenebilir")
        if m.id in self:
            raise ModelError(f"{m.id!r} kütüphanede zaten var; yeni id ile kopyalayın (ör. {m.id}-atolye)")
        return Kutuphane([*self, m])

    def kullanici_kayitlari(self) -> list[Malzeme]:
        return [m for m in self if m.kullanici]


def _oku(metin: str, nereden: str) -> list[Malzeme]:
    """{"surum": 1, "malzemeler": [...]} biçimini okur."""
    try:
        d = json.loads(metin)
    except json.JSONDecodeError as e:
        raise ModelError(f"{nereden}: geçersiz JSON ({e})") from e
    if not isinstance(d, dict) or d.get("surum") != SURUM:
        surum = d.get("surum") if isinstance(d, dict) else None
        raise ModelError(f"{nereden}: bilinmeyen malzeme dosyası sürümü {surum!r} (beklenen {SURUM})")
    return [Malzeme.from_dict(x) for x in d.get("malzemeler", [])]


@lru_cache(maxsize=1)
def yerlesik() -> Kutuphane:
    """malzeme/yerlesik.json (importlib.resources), önbellekli."""
    metin = resources.files("malzeme").joinpath("yerlesik.json").read_text(encoding="utf-8")
    kayitlar = _oku(metin, "malzeme/yerlesik.json")
    for m in kayitlar:
        if m.kullanici:
            raise ModelError(f"malzeme/yerlesik.json: {m.id!r} kullanıcı kaydı olamaz")
    return Kutuphane(kayitlar)


def kullanici_oku(yol: str | Path) -> list[Malzeme]:
    """Kullanıcı dosyası; kullanici=False kayıt ya da bilinmeyen surum → ModelError."""
    yol = Path(yol)
    kayitlar = _oku(yol.read_text(encoding="utf-8"), str(yol))
    yerlesikler = [m.id for m in kayitlar if not m.kullanici]
    if yerlesikler:
        raise ModelError(
            f"{yol}: kullanici=False kayıt kullanıcı dosyasında olamaz: {', '.join(yerlesikler)}"
        )
    return kayitlar


def kullanici_yaz(yol: str | Path, kayitlar: Iterable[Malzeme]) -> None:
    """Yalnız kullanici=True kayıtlar yazılır."""
    d = {"surum": SURUM, "malzemeler": [m.to_dict() for m in kayitlar if m.kullanici]}
    Path(yol).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def kutuphane(kullanici_dosyasi: str | Path | None = None) -> Kutuphane:
    """Yerleşik + kullanıcı kayıtları; yerleşik id ile çakışan kullanıcı kaydı → ModelError."""
    kut = yerlesik()
    if kullanici_dosyasi is not None:
        for m in kullanici_oku(kullanici_dosyasi):
            kut = kut.ekle(m)
    return kut
