"""SPEC 64 test düzeni: her test kendi geçici çalışma klasöründe (yerel_parcalar/ orada oluşur)."""

from __future__ import annotations

import pytest

from tests.tezgah.mes.ortak import IS_ADI, ornek_tanim


@pytest.fixture
def calisma(tmp_path, monkeypatch):
    """Çalışma klasörü tmp_path: yerel_parcalar/mes/... ve gonderim-kaydi.jsonl buraya göre."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def ornek_is():
    """Uydurma işi Tezgah deposuna ekler; test sonunda depo sıfırlanır."""
    from tezgah import depo

    depo.kaydet(IS_ADI, ornek_tanim())
    yield IS_ADI
    depo.sifirla()


@pytest.fixture
def istemci(calisma, ornek_is):
    """Tüm uygulama (A3 ekranları dahil); sunucu hatası teste yükselir (K9: 500 yok)."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    with TestClient(uygulama(dist=None), raise_server_exceptions=True) as c:
        yield c
