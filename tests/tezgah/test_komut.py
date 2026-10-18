"""SPEC 24 — `tezgah` komutu (`tezgah/__main__.py`): yalnız 127.0.0.1, `dist/` yoksa açık hata ve çıkış 1."""

from __future__ import annotations

from pathlib import Path

import pytest

import tezgah.__main__ as komut

DIST = Path(komut.__file__).parent / "arayuz" / "dist"


def test_listens_only_on_localhost():
    assert komut.HOST == "127.0.0.1"
    assert isinstance(komut.PORT, int) and 0 < komut.PORT < 65536


def test_missing_dist_explains_build_and_returns_1(capsys):
    """Derlenmiş ön yüz yoksa sunucu açılmaz; mesaj nasıl derleneceğini (npm) söyler."""
    if DIST.exists():
        pytest.skip("arayuz/dist/ derlenmiş; bu test yalnız derlenmemiş depoda (CI) anlamlı")
    pytest.importorskip("fastapi")
    kod = komut.main(["--port", "8799", "--tarayici-yok"])
    assert kod == 1
    cikti = capsys.readouterr()
    metin = cikti.out + cikti.err
    assert "npm" in metin
    assert "dist" in metin
