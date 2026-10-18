"""
SPEC 55 — `kurulum/kontrol.py` hazırlık denetimi (K6–K11, `main`).

Ağ: yalnızca 127.0.0.1; testin kendi açtığı yuvalar ve küçük HTTP sunucuları.
"""

from __future__ import annotations

import ast
import json
import socket
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from kurulum import kontrol
from kurulum.kontrol import (
    Madde,
    ice_aktarma_denetle,
    on_yuz_denetle,
    port_denetle,
    python_denetle,
    rapor,
)

HOST = "127.0.0.1"
AYRAC = " — "
ETIKET = {"tamam": "[TAMAM]", "uyari": "[UYARI]", "eksik": "[EKSİK]"}


def _bos_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


@contextmanager
def _http(govde: bytes | None, durum: int = 200, tur: str = "application/json"):
    """127.0.0.1'de geçici HTTP sunucusu: her GET'e (durum, govde) döner. Port döndürür."""

    class Isleyici(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(durum)
            self.send_header("Content-Type", tur)
            veri = govde or b""
            self.send_header("Content-Length", str(len(veri)))
            self.end_headers()
            self.wfile.write(veri)

        def log_message(self, *a):
            pass

    sunucu = ThreadingHTTPServer((HOST, 0), Isleyici)
    t = threading.Thread(target=sunucu.serve_forever, daemon=True)
    t.start()
    try:
        yield sunucu.server_address[1]
    finally:
        sunucu.shutdown()
        sunucu.server_close()


@contextmanager
def _kapatan_yuva():
    """Bağlantıyı kabul edip hemen kapatan, HTTP konuşmayan yuva."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, 0))
    s.listen(8)
    dur = threading.Event()

    def dongu():
        s.settimeout(0.1)
        while not dur.is_set():
            try:
                c, _ = s.accept()
                c.close()
            except OSError:
                continue

    t = threading.Thread(target=dongu, daemon=True)
    t.start()
    try:
        yield s.getsockname()[1]
    finally:
        dur.set()
        t.join(1)
        s.close()


def _openapi(baslik: str) -> bytes:
    return json.dumps({"openapi": "3.1.0", "info": {"title": baslik, "version": "0.1"}, "paths": {}}).encode()


def _bicim(m: Madde) -> None:
    assert m.durum in {"tamam", "uyari", "eksik"}
    assert isinstance(m.mesaj, str) and m.mesaj
    if m.durum != "tamam":
        assert AYRAC in m.mesaj, f"SPEC 54 §1 biçimi değil: {m.mesaj!r}"


# ---------------------------------------------------------------- K6


@pytest.mark.parametrize(
    "surum, durum",
    [
        ((3, 10, 0), "eksik"),
        ((3, 10, 99), "eksik"),
        ((2, 7, 18), "eksik"),
        ((3, 11, 0), "tamam"),
        ((3, 14, 7), "tamam"),
    ],
)
def test_python_version(surum, durum):
    m = python_denetle(surum)
    assert isinstance(m, Madde)
    assert m.ad == "python"
    assert m.durum == durum
    _bicim(m)


def test_python_version_default_is_running_interpreter():
    m = python_denetle()
    assert m.durum == ("tamam" if sys.version_info[:2] >= (3, 11) else "eksik")


# ---------------------------------------------------------------- K7


def test_import_missing_optional_is_warning():
    m = ice_aktarma_denetle("olmayan_modul_xyz", "occt", zorunlu=False)
    assert (m.ad, m.durum) == ("occt", "uyari")
    _bicim(m)


def test_import_missing_required_is_missing():
    m = ice_aktarma_denetle("olmayan_modul_xyz", "occt", zorunlu=True)
    assert (m.ad, m.durum) == ("occt", "eksik")
    _bicim(m)


@pytest.mark.parametrize("zorunlu", [True, False])
def test_import_present_is_ok(zorunlu):
    m = ice_aktarma_denetle("json", "web", zorunlu=zorunlu)
    assert (m.ad, m.durum) == ("web", "tamam")


def test_import_check_does_not_import(monkeypatch):
    """find_spec ile denetler: modülü yüklemez (yan etkisi olan paketler çalıştırılmaz)."""
    sys.modules.pop("this", None)
    m = ice_aktarma_denetle("this", "web", zorunlu=True)
    assert m.durum == "tamam"
    assert "this" not in sys.modules


# ---------------------------------------------------------------- K8


def test_front_end_missing(tmp_path):
    m = on_yuz_denetle(tmp_path)
    assert (m.ad, m.durum) == ("on_yuz", "eksik")
    assert "npm" in m.mesaj and "dist" in m.mesaj
    _bicim(m)


def test_front_end_empty_dist_is_missing(tmp_path):
    (tmp_path / "tezgah" / "arayuz" / "dist").mkdir(parents=True)
    assert on_yuz_denetle(tmp_path).durum == "eksik"


def test_front_end_present(tmp_path):
    dist = tmp_path / "tezgah" / "arayuz" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    m = on_yuz_denetle(tmp_path)
    assert (m.ad, m.durum) == ("on_yuz", "tamam")


# ---------------------------------------------------------------- K9


def test_port_free_is_ok():
    m = port_denetle(_bos_port(), HOST)
    assert (m.ad, m.durum) == ("port", "tamam")


def test_port_default_arguments():
    import inspect

    p = inspect.signature(port_denetle).parameters
    assert p["port"].default == 8724
    assert p["host"].default == "127.0.0.1"


def test_port_other_socket_is_missing():
    """K9: Tezgah olmayan, HTTP konuşmayan bir yuva dinlerken "eksik"."""
    with _kapatan_yuva() as port:
        m = port_denetle(port, HOST)
    assert (m.ad, m.durum) == ("port", "eksik")
    _bicim(m)


@pytest.mark.parametrize(
    "govde, durum_kodu",
    [(_openapi("Baska Program"), 200), (b"<html>merhaba</html>", 200), (b"", 404), (b"{bozuk json", 200)],
    ids=["baska-baslik", "html", "404", "bozuk-json"],
)
def test_port_other_http_is_missing(govde, durum_kodu):
    """Karar 4: bağlanıyor ama openapi.json'da info.title == "Tezgah" tutmuyorsa başka program."""
    with _http(govde, durum_kodu) as port:
        m = port_denetle(port, HOST)
    assert m.durum == "eksik"
    _bicim(m)


def test_port_tezgah_is_warning():
    """Karar 4: GET /api/openapi.json → info.title == "Tezgah" ise Tezgah zaten çalışıyor: "uyari"."""
    istekler: list[str] = []

    class Isleyici(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            istekler.append(self.path)
            veri = _openapi("Tezgah") if self.path == "/api/openapi.json" else b"{}"
            self.send_response(200 if self.path == "/api/openapi.json" else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(veri)))
            self.end_headers()
            self.wfile.write(veri)

        def log_message(self, *a):
            pass

    sunucu = ThreadingHTTPServer((HOST, 0), Isleyici)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    try:
        m = port_denetle(sunucu.server_address[1], HOST)
    finally:
        sunucu.shutdown()
        sunucu.server_close()
    assert (m.ad, m.durum) == ("port", "uyari")
    assert "/api/openapi.json" in istekler
    _bicim(m)


# ---------------------------------------------------------------- K10


def _m(ad: str, durum: str) -> Madde:
    return Madde(ad, durum, f"{ad} {durum} — deneme")


@pytest.mark.parametrize(
    "durumlar, kod",
    [
        (["tamam", "tamam"], 0),
        (["tamam", "uyari"], 2),
        (["uyari", "eksik"], 1),
        (["eksik", "tamam"], 1),
        (["uyari", "uyari"], 2),
        (["tamam"], 0),
    ],
)
def test_report_exit_code(durumlar, kod):
    _, c = rapor([_m(f"m{i}", d) for i, d in enumerate(durumlar)])
    assert c == kod


def test_report_lines():
    maddeler = [
        Madde("python", "tamam", "Python 3.14.7"),
        Madde("occt", "uyari", "OCCT yok: STEP açma ve katı modelleme kapalı — uyarı"),
        Madde("on_yuz", "eksik", "ön yüz derlenmemiş — npm run build"),
    ]
    metin, kod = rapor(maddeler)
    assert kod == 1
    satirlar = metin.splitlines()
    for m in maddeler:
        beklenen = f"{ETIKET[m.durum]} {m.ad}: {m.mesaj}"
        assert beklenen in satirlar, f"{beklenen!r} satırı yok:\n{metin}"
    sira = [
        next(i for i, s in enumerate(satirlar) if s.startswith(ETIKET[m.durum] + " " + m.ad))
        for m in maddeler
    ]
    assert sira == sorted(sira)


# ---------------------------------------------------------------- K11


def test_only_stdlib_imports():
    kaynak = Path(kontrol.__file__).read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    adlar = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar |= {a.name.split(".")[0] for a in d.names}
        elif isinstance(d, ast.ImportFrom):
            assert d.level == 0, "göreli import yok (betik olarak da çalışır)"
            adlar.add(d.module.split(".")[0])
    disari = adlar - set(sys.stdlib_module_names) - {"__future__"}
    assert not disari, disari


# ---------------------------------------------------------------- main


def test_main_reports_missing_front_end(tmp_path, capsys):
    kod = kontrol.main(["--kok", str(tmp_path), "--port", str(_bos_port())])
    assert kod == 1
    cikti = capsys.readouterr().out
    assert "[EKSİK] on_yuz:" in cikti
    assert "python:" in cikti and "port:" in cikti


def test_main_only_port_free(capsys):
    assert kontrol.main(["--yalniz-port", "--port", str(_bos_port())]) == 0
    assert "[TAMAM] port:" in capsys.readouterr().out


def test_main_only_port_tezgah_and_other():
    with _http(_openapi("Tezgah")) as port:
        assert kontrol.main(["--yalniz-port", "--port", str(port)]) == 2
    with _kapatan_yuva() as port:
        assert kontrol.main(["--yalniz-port", "--port", str(port)]) == 1
