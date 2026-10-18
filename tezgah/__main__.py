"""
`python -m tezgah` / `tezgah` komutu: yerel sunucuyu 127.0.0.1'de açar ve tarayıcıyı başlatır.

`arayuz/dist/` yoksa açık bir hata mesajıyla (nasıl derleneceği) 1 döner.
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

HOST = "127.0.0.1"
PORT = 8724


def main(argv: list[str] | None = None) -> int:
    """Seçenekler: --port N, --tarayici-yok (tarayıcı açma). Çıkış kodu döner."""
    ap = argparse.ArgumentParser(prog="tezgah", description="Tezgah: yerel CAM arayüzü (SPEC 24)")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--tarayici-yok", action="store_true", help="tarayıcıyı açma")
    a = ap.parse_args(argv)
    try:
        import uvicorn

        from tezgah.sunucu import DIST, uygulama
    except ImportError as e:
        msg = f'tezgah: web bağımlılıkları eksik ({e.name}). Kurulum: pip install -e ".[web]"'
        print(msg, file=sys.stderr)
        return 1
    if not (DIST / "index.html").is_file():
        print(
            f"tezgah: ön yüz derlenmemiş ({DIST} yok).\n"
            "Derlemek için: cd tezgah/arayuz && npm ci && npm run build",
            file=sys.stderr,
        )
        return 1
    url = f"http://{HOST}:{a.port}/"
    if not a.tarayici_yok:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    print(f"Tezgah: {url}  (durdurmak için Ctrl+C)", flush=True)
    uvicorn.run(uygulama(DIST), host=HOST, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
