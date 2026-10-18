"""
Malzeme kütüphanesi (SPEC 66): yerleşik kaynaklı kayıtlar + kullanıcı dosyası.

Yerleşik kayıtlar `malzeme/yerlesik.json` içindedir; her kaydın `kaynak` satırı vardır.
Kullanıcı kayıtları (atölye fiyatı, düzeltilmiş kesme verisi) varsayılan olarak `yerel_parcalar/`
altında durur.
JSON biçimi: {"surum": 1, "malzemeler": [Malzeme.to_dict(), ...]}.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from malzeme.model import Malzeme

SURUM = 1


class Kutuphane:
    """Değişmez malzeme kümesi: id → Malzeme. ekle() yeni bir Kutuphane döndürür."""

    def __init__(self, kayitlar: Iterable[Malzeme]) -> None:
        """Yinelenen id → ModelError."""
        raise NotImplementedError("SPEC 66: Kutuphane.__init__")

    def get(self, id: str) -> Malzeme:
        """Bilinmeyen id → ModelError (mesajda yakın eşleşmeler, difflib)."""
        raise NotImplementedError("SPEC 66: Kutuphane.get")

    def __contains__(self, id: object) -> bool:
        raise NotImplementedError("SPEC 66: Kutuphane.__contains__")

    def __iter__(self) -> Iterator[Malzeme]:
        """id sırasıyla."""
        raise NotImplementedError("SPEC 66: Kutuphane.__iter__")

    def __len__(self) -> int:
        raise NotImplementedError("SPEC 66: Kutuphane.__len__")

    def ara(self, metin: str) -> list[Malzeme]:
        """id, name, standart içinde büyük/küçük harf duyarsız arama."""
        raise NotImplementedError("SPEC 66: Kutuphane.ara")

    def grup(self, grup: str) -> list[Malzeme]:
        """B2 GRUPLAR dışı grup → ModelError."""
        raise NotImplementedError("SPEC 66: Kutuphane.grup")

    def ekle(self, m: Malzeme) -> Kutuphane:
        """m.kullanici True olmalı; id çakışması → ModelError. Eski kütüphane değişmez."""
        raise NotImplementedError("SPEC 66: Kutuphane.ekle")

    def kullanici_kayitlari(self) -> list[Malzeme]:
        raise NotImplementedError("SPEC 66: Kutuphane.kullanici_kayitlari")


def yerlesik() -> Kutuphane:
    """malzeme/yerlesik.json (importlib.resources), önbellekli."""
    raise NotImplementedError("SPEC 66: yerlesik")


def kullanici_oku(yol: str | Path) -> list[Malzeme]:
    """Kullanıcı dosyası; kullanici=False kayıt ya da bilinmeyen surum → ModelError."""
    raise NotImplementedError("SPEC 66: kullanici_oku")


def kullanici_yaz(yol: str | Path, kayitlar: Iterable[Malzeme]) -> None:
    """Yalnız kullanici=True kayıtlar yazılır."""
    raise NotImplementedError("SPEC 66: kullanici_yaz")


def kutuphane(kullanici_dosyasi: str | Path | None = None) -> Kutuphane:
    """Yerleşik + kullanıcı kayıtları; yerleşik id ile çakışan kullanıcı kaydı → ModelError."""
    raise NotImplementedError("SPEC 66: kutuphane")
