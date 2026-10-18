"""
SPEC 54 §2 — Hata kartı ve hata günlüğü (saf; FastAPI'ye bağlı değil).

Çekirdek hata metni `<nesne>: <ne oldu> — <ne yapılabilir>` biçimindedir; kart bu üç parçayı ve teknik
ayrıntıyı (istisna zinciri, son 20 satır) taşır:

    {sinif, nesne, ne_oldu, oneri, teknik}
"""

from __future__ import annotations

import json
import os
import re
import time
import traceback
from pathlib import Path

GUNLUK_SINIRI = 5 * 1024 * 1024  # bayt
TEKNIK_SATIR = 20

_BICIM = re.compile(r"^([^:]+): (.+?) — (.+)$", re.DOTALL)


def _metin(e: BaseException) -> str:
    if isinstance(e, KeyError) and e.args:
        return str(e.args[0])
    return str(e)


def _teknik(e: BaseException) -> str:
    return "\n".join(traceback.format_exception(e)[-TEKNIK_SATIR:])


def hata_karti(e: BaseException) -> dict:
    """Çekirdek hatasını karta ayırır; biçim dışı metinde nesne ve öneri boş kalır."""
    metin = _metin(e)
    m = _BICIM.match(metin)
    nesne, ne_oldu, oneri = m.groups() if m else ("", metin, "")
    sinif = type(e).__name__
    return {"sinif": sinif, "nesne": nesne, "ne_oldu": ne_oldu, "oneri": oneri, "teknik": _teknik(e)}


def ic_hata_karti(e: BaseException, uc: str, gunluk: Path) -> dict:
    """Çekirdek dışı istisna (programlama hatası) için 'IcHata' kartı."""
    return {
        "sinif": "IcHata",
        "nesne": uc,
        "ne_oldu": "beklenmeyen hata",
        "oneri": f"son değişikliği geri alın; hata kaydı {gunluk} içinde",
        "teknik": _teknik(e),
    }


def gunluge_yaz(e: BaseException, uc: str, gunluk: Path) -> None:
    """Günlüğe tek satır JSON ekler; sınır aşılacaksa önce hatalar.log → hatalar.log.1 döner."""
    gunluk = Path(gunluk)
    gunluk.parent.mkdir(parents=True, exist_ok=True)
    kayit = {
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "uc": uc,
        "sinif": type(e).__name__,
        "mesaj": str(e),
        "teknik": "".join(traceback.format_exception(e)),
    }
    satir = (json.dumps(kayit, ensure_ascii=False) + "\n").encode("utf-8")
    if len(satir) > GUNLUK_SINIRI:  # tek kayıt sınırı aşmasın
        kayit["teknik"] = _teknik(e)[-GUNLUK_SINIRI // 2 :]
        satir = (json.dumps(kayit, ensure_ascii=False) + "\n").encode("utf-8")
    boy = gunluk.stat().st_size if gunluk.exists() else 0
    if boy + len(satir) > GUNLUK_SINIRI:
        os.replace(gunluk, gunluk.with_name(gunluk.name + ".1"))
    with open(gunluk, "ab") as f:
        f.write(satir)
