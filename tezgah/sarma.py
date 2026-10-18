"""
SPEC 62 — simülasyonu ileri-geri sarma: her N adımda bir anahtar kare, k'ya karenin üstünden ileri oynatma.

Sonuç düz simülasyonla bit düzeyinde aynıdır: Sarici(girdi).durum(k) == simulate(**girdi).zmap_at(k)
(np.array_equal, dtype dahil). İlk sürüm freze z-haritası (model="zmap").
Bellek: kare = nx·ny·8 bayt; kare sayısı × kare > bellek_mb MiB ise N iki katına çıkar (sonuç değişmez).

Yöntem: SPEC 05 olay listesi (hücre, k, z) hesaplanır. Kare j: her hücrede k' ≤ j olan son olayın z'si;
k'ya gitmek için kare j = max{K ≤ k}'nin kopyasına j < k' ≤ k olaylarının hücre başına sonuncusu yazılır.
Geri sarma aynı yoldur (önceki kareden ileri), bu yüzden zmap_at(k) ile aynı sayılar aynı yere yazılır.
"""

from __future__ import annotations

import numpy as np

from core.model import ModelError

MIB = 1 << 20


class Sarici:
    """sim_girdisi: cam.sim.simulate anahtar sözcükleri ({"ops", "stock", "cell", ...}).

    n: adım sayısı (durum(0) başlangıç stoku, durum(n) son stok); N: kullanılan kare aralığı;
    kareler: anahtar kare adımları, artan, 0 ile başlar. k ∉ 0..n → core.model.ModelError.
    """

    def __init__(self, sim_girdisi: dict, N: int = 200, bellek_mb: float = 256):
        from cam.sim import simulate

        girdi = dict(sim_girdisi)
        if girdi.get("model", "zmap") != "zmap":
            raise ModelError(f"Sarma ilk sürümde yalnız z-haritası ister (model={girdi['model']!r})")
        self._kur(simulate(**girdi), N, bellek_mb)

    @classmethod
    def sonuctan(cls, sim, N: int = 200, bellek_mb: float = 256) -> Sarici:
        """Hesaplanmış bir SimResult'tan (z-haritası) sarıcı; simülasyon yeniden koşmaz."""
        s = cls.__new__(cls)
        if getattr(sim, "dexel", None) is not None:
            raise ModelError("Sarma ilk sürümde yalnız z-haritası simülasyonunu sarar")
        s._kur(sim, N, bellek_mb)
        return s

    def _kur(self, sim, N: int, bellek_mb: float) -> None:
        if isinstance(N, bool) or not isinstance(N, int | np.integer) or N < 1:
            raise ModelError(f"Kare aralığı N pozitif tamsayı olmalı (N={N!r})")
        if not (isinstance(bellek_mb, int | float) and np.isfinite(bellek_mb) and bellek_mb > 0):
            raise ModelError(f"bellek_mb pozitif olmalı ({bellek_mb!r})")
        self._sim = sim
        self.n = len(sim.steps)
        g = sim.zmap
        kare_bayt = g.nx * g.ny * 8
        N = int(N)
        while N < max(self.n, 1) and (self.n // N + 1) * kare_bayt > bellek_mb * MIB:
            N *= 2
        self.N = N
        self.kareler = list(range(0, self.n + 1, N))
        # olaylar k'ya göre (kararlı) sıralı: (j, k] aralığı ardışık bir dilimdir
        sira = np.argsort(sim.event_k, kind="stable")
        self._k = np.asarray(sim.event_k)[sira]
        self._c = np.asarray(sim.event_cell)[sira]
        self._z = np.asarray(sim.event_z)[sira]
        self._kare: dict[int, np.ndarray] = {}
        z = sim.zmap_at(0).ravel().copy()
        onceki = 0
        for j in self.kareler:
            self._uygula(z, onceki, j)
            self._kare[j], onceki = z.copy(), j

    def _uygula(self, z: np.ndarray, j: int, k: int) -> None:
        """z (kare j) üstüne j < k' ≤ k olaylarının hücre başına sonuncusunu yazar (yerinde)."""
        a = int(np.searchsorted(self._k, j, side="right"))
        b = int(np.searchsorted(self._k, k, side="right"))
        if a == b:
            return
        c = self._c[a:b][::-1]
        hucre, ilk = np.unique(c, return_index=True)  # ters dizide ilk = asıl dizide son
        z[hucre] = self._z[a:b][::-1][ilk]

    def durum(self, k: int) -> np.ndarray:
        """k adımdan sonraki z-haritası, (ny, nx) float64 kopya."""
        if isinstance(k, bool) or not isinstance(k, int | np.integer) or not 0 <= k <= self.n:
            raise ModelError(f"Sarma: k 0..{self.n} olmalı (k={k!r})")
        j = self.kareler[int(k) // self.N]
        z = self._kare[j].copy()
        self._uygula(z, j, int(k))
        g = self._sim.zmap
        return z.reshape(g.ny, g.nx)
