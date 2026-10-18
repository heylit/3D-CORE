"""SPEC 57 §1 — Stok kataloğu ve stok seçimi. Birimler: mm."""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, fields
from os import PathLike
from pathlib import Path

import numpy as np

from cam.model import CamError, CylinderStock, Stock

KINDS = ("blok", "cubuk")
TOL = 1e-9  # mm: sınırda uyma toleransı


@dataclass(frozen=True)
class StockSize:
    """Katalog satırı: blok (a × b × c) ya da çubuk (Ø a, boy ≤ max_len)."""

    kind: str  # "blok" | "cubuk"
    a: float
    b: float = 0.0
    c: float = 0.0
    max_len: float | None = None
    name: str = ""


def _pozitif(nerede: str, ad: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise CamError(f"{nerede}: {ad} sonlu ve pozitif olmalı ({v!r})")
    return float(v)


def _satir(s: StockSize, nerede: str) -> StockSize:
    """Satırı denetler; ölçüleri float yapar."""
    if not isinstance(s, StockSize):
        raise CamError(f"{nerede}: StockSize bekleniyor ({type(s).__name__})")
    if s.kind not in KINDS:
        raise CamError(f"{nerede}: tür 'blok' veya 'cubuk' olmalı ({s.kind!r})")
    a = _pozitif(nerede, "a", s.a)
    if s.kind == "blok":
        b, c = _pozitif(nerede, "b", s.b), _pozitif(nerede, "c", s.c)
    else:
        b = c = 0.0
    L = None if s.max_len is None else _pozitif(nerede, "max_len", s.max_len)
    if not isinstance(s.name, str):
        raise CamError(f"{nerede}: ad metin olmalı ({s.name!r})")
    return StockSize(s.kind, a, b, c, L, s.name)


def load_catalog(path: str | PathLike) -> tuple[StockSize, ...]:
    """JSON stok kataloğunu okur: StockSize alanlarıyla nesne listesi; hatalı satır → CamError."""
    try:
        veri = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CamError(f"Stok kataloğu okunamadı ({path}): {e}") from e
    if not isinstance(veri, list):
        raise CamError("Stok kataloğu nesne listesi olmalı")
    izinli = {f.name for f in fields(StockSize)}
    out = []
    for i, d in enumerate(veri):
        nerede = f"Stok kataloğu satır {i}"
        if not isinstance(d, dict):
            raise CamError(f"{nerede}: nesne olmalı")
        fazla = set(d) - izinli
        if fazla:
            raise CamError(f"{nerede}: bilinmeyen anahtar {sorted(fazla)}")
        for ad in ("kind", "a"):
            if ad not in d:
                raise CamError(f"{nerede}: '{ad}' eksik")
        out.append(_satir(StockSize(**d), nerede))
    return tuple(out)


def _bbox(bbox) -> tuple[np.ndarray, np.ndarray]:
    try:
        lo, hi = (np.asarray(b, dtype=float) for b in bbox)
    except (TypeError, ValueError) as e:
        raise CamError(f"Stok seçimi: bbox (b_min, b_max) olmalı ({bbox!r})") from e
    if lo.shape != (3,) or hi.shape != (3,) or not (np.all(np.isfinite(lo)) and np.all(np.isfinite(hi))):
        raise CamError(f"Stok seçimi: bbox iki sonlu 3'lü dizi olmalı ({bbox!r})")
    if np.any(hi - lo <= 0):
        raise CamError(f"Stok seçimi: sınır kutusu boyu pozitif olmalı ({hi - lo})")
    return lo, hi


def _donmeler() -> list[np.ndarray]:
    """Parça eksenlerinin stok eksenlerine altı permütasyonu (det = +1; ters permütasyonda bir eksen eksi)."""
    out = []
    for p in itertools.permutations(range(3)):
        R = np.zeros((3, 3))
        for i, j in enumerate(p):
            R[i, j] = 1.0  # stok ekseni i ← parça ekseni j
        if np.linalg.det(R) < 0:
            R[2] *= -1.0
        out.append(R)
    return out


def _T(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def select_stock(
    bbox, catalog, m: float = 1.0, g: float = 5.0, saw: float = 3.0
) -> tuple[Stock | CylinderStock, np.ndarray]:
    """En küçük hacimli uyan stok ve parçanın stok içindeki dönüşümü (4×4); uyan yoksa CamError(stok_yok).

    Blok: gereken (Lx + 2m, Ly + 2m, Lz + m + g), altı permütasyon denenir. Çubuk: d ≥ √(L1² + L2²) + 2m,
    boy L3 + m + g + saw. Eşitlikte ilk katalog satırı, satır içinde ilk yerleşim. Parça x, y'de ortalanır,
    üstte m payı kalır (kavrama ve testere payı altta).
    """
    lo, hi = _bbox(bbox)
    m, g, saw = (_pozitif_veya_sifir("Stok seçimi", ad, v) for ad, v in (("m", m), ("g", g), ("saw", saw)))
    katalog = [_satir(s, f"Stok kataloğu satır {i}") for i, s in enumerate(catalog)]
    L = hi - lo
    merkez = (lo + hi) / 2
    en_iyi = None  # (hacim, stok, T)
    for s in katalog:
        for R in _donmeler():
            Lp = np.abs(R @ L)  # stok eksenlerinde parça boyu
            if s.kind == "blok":
                boy = np.array([s.a, s.b, s.c])
                if np.any(Lp + np.array([2 * m, 2 * m, m + g]) > boy + TOL):
                    continue
                stok = Stock(0.0, 0.0, 0.0, s.a, s.b, s.c)
                hedef = np.array([s.a / 2, s.b / 2, s.c - m - Lp[2] / 2])
                V = s.a * s.b * s.c
            else:
                uzunluk = Lp[2] + m + g + saw
                if math.hypot(Lp[0], Lp[1]) + 2 * m > s.a + TOL:
                    continue
                if s.max_len is not None and uzunluk > s.max_len + TOL:
                    continue
                stok = CylinderStock(D=s.a, d=0.0, zmin=0.0, zmax=uzunluk)
                hedef = np.array([0.0, 0.0, uzunluk - m - Lp[2] / 2])
                V = math.pi * s.a**2 / 4 * uzunluk
            if en_iyi is None or V < en_iyi[0] - TOL:
                en_iyi = (V, stok, _T(R, hedef - R @ merkez))  # eşitlikte ilk satır / ilk yerleşim
    if en_iyi is None:
        raise CamError(f"stok_yok: katalogda {L[0]:g} × {L[1]:g} × {L[2]:g} parçayı kapsayan stok yok")
    return en_iyi[1], en_iyi[2]


def _pozitif_veya_sifir(nerede: str, ad: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise CamError(f"{nerede}: {ad} sonlu ve ≥ 0 olmalı ({v!r})")
    return float(v)
