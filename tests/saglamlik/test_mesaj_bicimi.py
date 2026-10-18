"""SPEC 54 K2 — mesaj biçimi: `<nesne>: <ne oldu> — <ne yapılabilir>`.

K1'deki her mesaj `^[^:]+: .+ — .+$` kalıbına uyar; `<ne yapılabilir>` en az 3 kelime; mesajda OCCT sınıf adı
(`Standard_`, `StdFail_`, `BRep`) ve Python izi yok; neden zinciri `__cause__`'da korunur (`raise … from e`,
`from None` değil). Mesajı `*/model.py`'de doğan durumlar Karar 4 gereği ayrı arayüz PR'ına kadar xfail.

Testler yalnız specs/54-saglamlik.md'den ve iskelet imzalarından yazıldı; SPEC 54 kodu okunmadı.
"""

from __future__ import annotations

import re

import pytest

from tests.saglamlik.durumlar import DURUMLAR, Durum, calistir, param

KALIP = re.compile(r"^[^:]+: .+ — .+$", re.DOTALL)
YASAK = ("Standard_", "StdFail_", "BRep", "Traceback", 'File "')


def parcalar(metin: str) -> tuple[str, str, str]:
    """Mesajı (nesne, ne oldu, öneri) olarak ayırır; kalıba uymuyorsa AssertionError."""
    m = re.match(r"^([^:]+): (.+?) — (.+)$", metin, re.DOTALL)
    assert m, f"mesaj biçimi '<nesne>: <ne oldu> — <ne yapılabilir>' değil: {metin!r}"
    return m.group(1), m.group(2), m.group(3)


def _hata(d: Durum, tmp_path) -> BaseException:
    e = calistir(d, tmp_path)
    assert e is not None, f"durum {d.kimlik}: hata çıkmadı"
    return e


@pytest.mark.parametrize("d", [param(d, "format") for d in DURUMLAR])
def test_message_format(d: Durum, tmp_path):
    metin = str(_hata(d, tmp_path))
    assert KALIP.match(metin), f"durum {d.kimlik}: {metin!r}"
    nesne, ne_oldu, oneri = parcalar(metin)
    assert nesne.strip() and ne_oldu.strip()
    assert len(oneri.split()) >= 3, f"durum {d.kimlik}: öneri en az 3 kelime olmalı: {oneri!r}"
    for p in d.nesne:  # model.py durumlarında K1 yalnız sınıfı denetler; nesne burada
        assert p in metin, f"durum {d.kimlik}: mesajda {p!r} yok: {metin!r}"


@pytest.mark.parametrize("d", [param(d, "internal") for d in DURUMLAR])
def test_message_has_no_internal_names(d: Durum, tmp_path):
    metin = str(_hata(d, tmp_path))
    for yasak in YASAK:
        assert yasak not in metin, f"durum {d.kimlik}: mesajda {yasak!r}: {metin!r}"


@pytest.mark.parametrize("d", [param(d, "suggestion") for d in DURUMLAR if d.oneri_icerir or d.oneri_sayi])
def test_suggestion_content(d: Durum, tmp_path):
    """Tablodaki öneri koşulları: durum 4 'katı', 13 'mesnet'; durum 7 bir sınır (sayı)."""
    _, _, oneri = parcalar(str(_hata(d, tmp_path)))
    for kelime in d.oneri_icerir:
        assert kelime.lower() in oneri.lower(), f"durum {d.kimlik}: öneride {kelime!r} yok: {oneri!r}"
    if d.oneri_sayi:
        assert re.search(r"\d", oneri), f"durum {d.kimlik}: öneride sınır sayısı yok: {oneri!r}"


@pytest.mark.parametrize("d", [param(d, "cause") for d in DURUMLAR if not d.model_py])
def test_cause_is_kept(d: Durum, tmp_path):
    """Başka bir istisnadan doğan hata onu `__cause__`'da taşır (`raise … from e`); zincir gizlenmez."""
    e = _hata(d, tmp_path)
    zincir = e
    while zincir is not None:
        if zincir.__context__ is not None:
            assert zincir.__cause__ is zincir.__context__, (
                f"durum {d.kimlik}: {type(zincir).__name__} başka bir istisnadan doğmuş ama "
                f"__cause__'da değil ({type(zincir.__context__).__name__})"
            )
            assert not (zincir.__suppress_context__ and zincir.__cause__ is None)
        zincir = zincir.__cause__
