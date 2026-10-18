"""
SPEC 55 — Windows kurulumu hazırlık denetimi (yalnızca stdlib).

`kur.bat` bunu kurulan ortamın Python'uyla çalıştırır; mantık burada, `.bat` yalnızca sırayla çağırır.
Her madde "tamam" / "uyari" / "eksik"; çıkış kodu: herhangi bir "eksik" → 1, yoksa herhangi bir "uyari" → 2,
değilse 0. Mesajlar SPEC 54 §1 biçiminde: `<ne oldu> — <ne yapılabilir>`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PY_EN_AZ = (3, 11)
ZAMAN_ASIMI = 2.0  # s
ETIKET = {"tamam": "[TAMAM]", "uyari": "[UYARI]", "eksik": "[EKSİK]"}


@dataclass(frozen=True)
class Madde:
    ad: str  # "python", "web", "occt", "on_yuz", "port"
    durum: str  # "tamam" | "uyari" | "eksik"
    mesaj: str  # SPEC 54 §1 biçimi


def python_denetle(surum: tuple[int, int, int] | None = None) -> Madde:
    """Python ≥ 3.11 değilse "eksik"; surum None → çalışan yorumlayıcı."""
    v = tuple(surum) if surum is not None else tuple(sys.version_info[:3])
    s = ".".join(str(k) for k in v)
    if v[:2] >= PY_EN_AZ:
        return Madde("python", "tamam", f"Python {s} — hazır")
    ipucu = "TEZGAH_PYTHON=3.14 ile kur.bat'ı yeniden çalıştırın"
    return Madde("python", "eksik", f"Python {s} çok eski — {ipucu}")


def ice_aktarma_denetle(modul: str, ad: str, zorunlu: bool) -> Madde:
    """importlib.util.find_spec ile modül var mı; yoksa zorunluysa "eksik", değilse "uyari"."""
    try:
        var = importlib.util.find_spec(modul) is not None
    except (ImportError, ValueError):
        var = False
    if var:
        return Madde(ad, "tamam", f"{modul} yüklü — hazır")
    if zorunlu:
        return Madde(ad, "eksik", f"{modul} yüklenmemiş — kur.bat'ı yeniden çalıştırın, kurulum.log'a bakın")
    if ad == "occt":
        return Madde(ad, "uyari", f"OCCT yok ({modul}): STEP açma ve katı modelleme kapalı — uyarı")
    return Madde(ad, "uyari", f"{modul} yüklenmemiş — bu özellik kapalı, diğerleri çalışır")


def on_yuz_denetle(kok: Path) -> Madde:
    """`kok/tezgah/arayuz/dist/index.html` var mı."""
    if (Path(kok) / "tezgah" / "arayuz" / "dist" / "index.html").is_file():
        return Madde("on_yuz", "tamam", "Tezgah ön yüzü derlenmiş — hazır")
    return Madde(
        "on_yuz",
        "eksik",
        "Tezgah ön yüzü derlenmemiş — Node.js kurun (npm ci, npm run build) ya da derlenmiş dist klasörünü "
        "tezgah\\arayuz\\dist içine kopyalayın",
    )


def _tezgah_mi(host: str, port: int) -> bool:
    """Dinleyen program Tezgah mı: /api/openapi.json başlığı "Tezgah" (SPEC 55 karar 4)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/openapi.json", timeout=ZAMAN_ASIMI) as y:
            veri = json.loads(y.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return False
    bilgi = veri.get("info") if isinstance(veri, dict) else None
    return isinstance(bilgi, dict) and bilgi.get("title") == "Tezgah"


def port_denetle(port: int = 8724, host: str = "127.0.0.1") -> Madde:
    """Boş port: "tamam"; Tezgah dinliyorsa: "uyari"; başka program: "eksik"."""
    try:
        with socket.create_connection((host, port), timeout=ZAMAN_ASIMI):
            pass
    except OSError:
        return Madde("port", "tamam", f"{host}:{port} boş — hazır")
    if _tezgah_mi(host, port):
        return Madde("port", "uyari", f"Tezgah zaten {host}:{port}'te açık — tarayıcıdan bu adrese gidin")
    return Madde(
        "port", "eksik", f"{host}:{port} başka bir program tarafından kullanılıyor — o programı kapatın"
    )


def rapor(maddeler: list[Madde]) -> tuple[str, int]:
    """Her madde bir satır `[TAMAM]/[UYARI]/[EKSİK] ad: mesaj`; çıkış kodu 0 / 2 / 1."""
    satirlar = [f"{ETIKET[m.durum]} {m.ad}: {m.mesaj}" for m in maddeler]
    durumlar = {m.durum for m in maddeler}
    kod = 1 if "eksik" in durumlar else 2 if "uyari" in durumlar else 0
    return "\n".join(satirlar), kod


def main(argv: list[str] | None = None) -> int:
    """Komut satırı: --kok, --port, --yalniz-port."""
    ap = argparse.ArgumentParser(prog="kontrol.py", description="Tezgah kurulumu hazırlık denetimi (SPEC 55)")
    ap.add_argument("--kok", type=Path, default=Path(__file__).resolve().parent.parent, help="depo kökü")
    ap.add_argument("--port", type=int, default=8724)
    ap.add_argument("--yalniz-port", action="store_true", help="yalnız port denetimi (başlatıcı için)")
    a = ap.parse_args(argv)
    if a.yalniz_port:
        maddeler = [port_denetle(a.port)]
    else:
        maddeler = [
            python_denetle(),
            ice_aktarma_denetle("fastapi", "web", zorunlu=True),
            ice_aktarma_denetle("build123d", "occt", zorunlu=False),
            on_yuz_denetle(a.kok),
            port_denetle(a.port),
        ]
    metin, kod = rapor(maddeler)
    print(metin)
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
