"""
`python -m tezgah` / `tezgah` komutu: yerel sunucuyu 127.0.0.1'de açar ve tarayıcıyı başlatır.

`arayuz/dist/` yoksa açık bir hata mesajıyla (nasıl derleneceği) 1 döner.
"""

from __future__ import annotations

import sys

HOST = "127.0.0.1"
PORT = 8724


def main(argv: list[str] | None = None) -> int:
    """Seçenekler: --port N, --tarayici-yok (tarayıcı açma). Çıkış kodu döner."""
    raise NotImplementedError("SPEC 24: uygulanmadı")


if __name__ == "__main__":
    sys.exit(main())
