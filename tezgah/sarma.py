"""
SPEC 62 — simülasyonu ileri-geri sarma: her N adımda bir anahtar kare, k'ya karenin üstünden ileri oynatma.

Sonuç düz simülasyonla bit düzeyinde aynıdır: Sarici(girdi).durum(k) == simulate(**girdi).zmap_at(k)
(np.array_equal, dtype dahil). İlk sürüm freze z-haritası (model="zmap").
Bellek: kare = nx·ny·8 bayt; kare sayısı × kare > bellek_mb MiB ise N iki katına çıkar (sonuç değişmez).
"""

from __future__ import annotations

import numpy as np


class Sarici:
    """sim_girdisi: cam.sim.simulate anahtar sözcükleri ({"ops", "stock", "cell", ...}).

    n: adım sayısı (durum(0) başlangıç stoku, durum(n) son stok); N: kullanılan kare aralığı;
    kareler: anahtar kare adımları, artan, 0 ile başlar. k ∉ 0..n → core.model.ModelError.
    """

    def __init__(self, sim_girdisi: dict, N: int = 200, bellek_mb: float = 256):
        raise NotImplementedError("SPEC 62: Sarici")

    n: int
    N: int
    kareler: list[int]

    def durum(self, k: int) -> np.ndarray:
        """k adımdan sonraki z-haritası, (ny, nx) float64 kopya."""
        raise NotImplementedError("SPEC 62: Sarici.durum")
