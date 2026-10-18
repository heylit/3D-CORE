"""
SPEC 55 — Windows kurulumu hazırlık denetimi (yalnızca stdlib).

`kur.bat` bunu kurulan ortamın Python'uyla çalıştırır; mantık burada, `.bat` yalnızca sırayla çağırır.
Her madde "tamam" / "uyari" / "eksik"; çıkış kodu: herhangi bir "eksik" → 1, yoksa herhangi bir "uyari" → 2,
değilse 0. Mesajlar SPEC 54 §1 biçiminde: `<ne oldu> — <ne yapılabilir>`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Madde:
    ad: str  # "python", "web", "occt", "on_yuz", "port"
    durum: str  # "tamam" | "uyari" | "eksik"
    mesaj: str  # SPEC 54 §1 biçimi


def python_denetle(surum: tuple[int, int, int] | None = None) -> Madde:
    """Python ≥ 3.11 değilse "eksik"; surum None → çalışan yorumlayıcı."""
    raise NotImplementedError


def ice_aktarma_denetle(modul: str, ad: str, zorunlu: bool) -> Madde:
    """importlib.util.find_spec ile modül var mı; yoksa zorunluysa "eksik", değilse "uyari"."""
    raise NotImplementedError


def on_yuz_denetle(kok: Path) -> Madde:
    """`kok/tezgah/arayuz/dist/index.html` var mı."""
    raise NotImplementedError


def port_denetle(port: int = 8724, host: str = "127.0.0.1") -> Madde:
    """Boş port: "tamam"; Tezgah dinliyorsa: "uyari"; başka program: "eksik"."""
    raise NotImplementedError


def rapor(maddeler: list[Madde]) -> tuple[str, int]:
    """Her madde bir satır `[TAMAM]/[UYARI]/[EKSİK] ad: mesaj`; çıkış kodu 0 / 2 / 1."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """Komut satırı: --kok, --port, --yalniz-port."""
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
