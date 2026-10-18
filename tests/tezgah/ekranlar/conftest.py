"""
Ekran testlerinin yalıtımı: paket bitince `tezgah.ekranlar.<modül>` kayıtları `sys.modules`'tan silinir.

Bu klasördeki testler uygulamayı (`uygulama(dist=None)`) keşifle kurar; keşif gerçek ekran modüllerini
(`plan`, `analiz`, ...) `sys.modules`'a yükler. Kayıtlar kalırsa sonra koşan A3 testleri
(`tests/tezgah/test_ekranlar.py`, sahte paket klasörüyle keşif) aynı adlı sahte modül yerine gerçeğini bulur.
Testlerin elindeki modül nesneleri silinmez; yalnız sonraki importlar yeniden yükler.
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture(scope="package", autouse=True)
def _ekran_modullerini_temizle():
    yield
    for k in [k for k in sys.modules if k.startswith("tezgah.ekranlar.")]:
        del sys.modules[k]
    importlib.invalidate_caches()
