"""
SPEC 47b testlerinin ortak yardımcıları (test modülü değil; pytest toplamaz).

- `cekirdek()`: SPEC 41–44 modülleri ve `examples/tezgah_ac_besik.json` yoksa testi atlar
  (SPEC 41 henüz `main`'de değil, 42/43/44 için kod yok).
- `moduller()`: ekranın köprü ve örnek modüllerini verir; `[web]` (fastapi) yoksa atlar
  (`tezgah.ekranlar` paketi A3 kabuğudur ve FastAPI'yi import eder).
- `ornek_is(ad, profil)`: örnek işi bir kez kurar (testler işi DEĞİŞTİRMEZ; değişen iş `dataclasses.replace`).
- `Okuyucu`: ikili dizileri köprünün `*_coz`'undan bağımsız okur. Biçim köprü belgelerindeki gibidir; her
  blok (başlık dahil) 8 baytın katına sıfırla tamamlanır (SPEC 24 `kopru._blok` kuralı). Başlığın da
  tamamlanması tarayıcıda `Float64Array` görünümünün 8 bayt hizalı ofset istemesindendir.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[3]
TEZGAH_JSON = KOK / "examples" / "tezgah_ac_besik.json"

# (modül, SPEC): ekranın kullandığı çekirdek modülleri (SPEC 41–44 "Dosyalar").
CEKIRDEK: tuple[tuple[str, str], ...] = (
    ("cam.multiaxis.kinematics", "SPEC 41"),
    ("cam.multiaxis.indexed", "SPEC 41"),
    ("cam.multiaxis.toolpath5", "SPEC 42"),
    ("cam.multiaxis.linearize", "SPEC 42"),
    ("cam.sim.tridexel", "SPEC 43"),
    ("cam.sim.simulate5", "SPEC 43"),
    ("cam.multiaxis.machine", "SPEC 44"),
    ("cam.multiaxis.collision", "SPEC 44"),
)


def cekirdek() -> None:
    """SPEC 41–44 kodu yoksa testi atlar."""
    for modul, spec in CEKIRDEK:
        pytest.importorskip(modul, reason=f"{spec} ({modul}) henüz yok")
    if not TEZGAH_JSON.is_file():
        pytest.skip("SPEC 44 examples/tezgah_ac_besik.json henüz yok")


def moduller():
    """(köprü, örnekler) modülleri; `[web]` yoksa atlar."""
    pytest.importorskip("fastapi")
    from tezgah.ekranlar import _cok_eksen_kopru as kopru
    from tezgah.ekranlar import _cok_eksen_ornekler as orn

    return kopru, orn


@functools.cache
def _ornek(ad: str, profil: str | None):
    _, orn = moduller()
    return orn.ornek(ad, profil)


def ornek_is(ad: str, profil: str | None = None):
    """Örnek iş (önbellekli). Çekirdek yoksa atlar."""
    cekirdek()
    return _ornek(ad, profil)


def json_tur(x):
    """JSON'a çevrilip geri okunmuş hâli (nan/inf varsa hata)."""
    return json.loads(json.dumps(x, allow_nan=False))


def kontrol(liste: list[dict], kimlik: str) -> dict:
    bulunan = [k for k in liste if k["kimlik"] == kimlik]
    assert len(bulunan) == 1, f"{kimlik!r} kontrolü tam bir kez olmalı: {[k['kimlik'] for k in liste]}"
    return bulunan[0]


def ornekle(n: int, en_cok: int = 200) -> np.ndarray:
    """0..n-1 arasından uçlar dahil en çok `en_cok` eşit aralıklı indeks."""
    return np.unique(np.linspace(0, n - 1, min(n, en_cok)).round().astype(int))


class Okuyucu:
    """Little-endian ikili okuyucu; her okunan blok 8 baytın katına tamamlanmış sayılır."""

    def __init__(self, veri: bytes):
        self.veri = veri
        self.ofs = 0

    def oku(self, dtype: str, n: int) -> np.ndarray:
        dt = np.dtype(dtype).newbyteorder("<")
        boy = dt.itemsize * n
        assert self.ofs + boy <= len(self.veri), "ikili dizi beklenenden kısa"
        a = np.frombuffer(self.veri, dtype=dt, count=n, offset=self.ofs).astype(dt.newbyteorder("="))
        dolgu = self.veri[self.ofs + boy : self.ofs + boy + (-boy % 8)]
        assert dolgu == bytes(len(dolgu)), "blok dolgusu sıfır olmalı"
        self.ofs += boy + (-boy % 8)
        return a

    def bitti(self) -> None:
        assert self.ofs == len(self.veri), f"fazladan bayt: {len(self.veri) - self.ofs}"
