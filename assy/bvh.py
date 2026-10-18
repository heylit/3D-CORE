"""
SPEC 53 — Girişim aday çiftleri için sınır kutusu ağacı (BVH).

Yaprak kutuları orta nokta bölmesiyle (en uzun eksende medyan) ikili ağaca dizilir. İki düğüm aday olur ancak
kutu boşluğu g = |max(0, lo_b − hi_a, lo_a − hi_b)| için g < esik_c veya g ≤ tol_d ise (SPEC 09 ölçütü).
Aday kümesi sort and sweep ile aynıdır; ağaç yalnız aramayı budar.

İki düğümün kutu boşluğu, içlerindeki her yaprak çiftinin boşluğundan büyük olamaz (düğüm kutusu yaprakları
kapsar); bu yüzden budanan düğüm çiftinde aday kalmaz. Arama düğüm çiftleri üzerinde seviye seviye, numpy ile.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from assy.model import AssyError

_YAPRAK = 4  # yapraktaki en çok kutu
_PAY = 1e-9  # budama eşiği payı (son karar SPEC 09 formülüyle tek tek verilir)


@dataclass
class Bvh:
    lo: np.ndarray  # (n, 3) yaprak kutuları
    hi: np.ndarray
    # düğümler: kutu, alt düğümler (yaprakta −1), kapsadığı sıralı kutu aralığı [bas, son)
    n_lo: np.ndarray = field(default=None, repr=False)
    n_hi: np.ndarray = field(default=None, repr=False)
    sol: np.ndarray = field(default=None, repr=False)
    sag: np.ndarray = field(default=None, repr=False)
    bas: np.ndarray = field(default=None, repr=False)
    son: np.ndarray = field(default=None, repr=False)
    sira: np.ndarray = field(default=None, repr=False)  # ağaç sırasındaki kutu indeksleri

    @classmethod
    def build(cls, boxes) -> Bvh:
        """boxes: [(lo, hi), ...] eksen hizalı kutular."""
        try:
            lo = np.array([np.asarray(b[0], dtype=float) for b in boxes], dtype=float).reshape(-1, 3)
            hi = np.array([np.asarray(b[1], dtype=float) for b in boxes], dtype=float).reshape(-1, 3)
        except (TypeError, ValueError, IndexError) as e:
            raise AssyError(f"Bvh: kutular [(lo, hi), ...] ve 3 bileşenli olmalı ({e})") from e
        if len(lo) != len(boxes) or len(hi) != len(boxes):
            raise AssyError("Bvh: her kutu 3 bileşenli lo ve hi olmalı")
        if not (np.all(np.isfinite(lo)) and np.all(np.isfinite(hi))) or np.any(hi < lo):
            raise AssyError("Bvh: kutular sonlu ve lo ≤ hi olmalı")
        t = cls(lo, hi)
        t._kur()
        return t

    def _kur(self) -> None:
        n = len(self.lo)
        sira = np.arange(n)
        merkez = (self.lo + self.hi) / 2
        n_lo, n_hi, sol, sag, bas, son = [], [], [], [], [], []

        def yeni(b: int, s: int) -> int:
            idx = sira[b:s]
            n_lo.append(self.lo[idx].min(axis=0) if s > b else np.zeros(3))
            n_hi.append(self.hi[idx].max(axis=0) if s > b else np.zeros(3))
            sol.append(-1)
            sag.append(-1)
            bas.append(b)
            son.append(s)
            return len(bas) - 1

        yigin = [yeni(0, n)]
        while yigin:
            d = yigin.pop()
            b, s = bas[d], son[d]
            if s - b <= _YAPRAK:
                continue
            idx = sira[b:s]
            m = merkez[idx]
            eksen = int(np.argmax(m.max(axis=0) - m.min(axis=0)))
            k = (s - b) // 2
            p = np.argpartition(m[:, eksen], k, kind="introselect")
            sira[b:s] = idx[p]
            sol[d] = yeni(b, b + k)
            sag[d] = yeni(b + k, s)
            yigin += [sol[d], sag[d]]
        self.n_lo, self.n_hi = np.array(n_lo), np.array(n_hi)
        self.sol, self.sag = np.array(sol), np.array(sag)
        self.bas, self.son = np.array(bas), np.array(son)
        self.sira = sira

    def pairs(self, esik_c: float, tol_d: float) -> list[tuple[int, int]]:
        """g < esik_c veya g ≤ tol_d olan çiftler (i < j), sıralı."""
        n = len(self.lo)
        if n < 2:
            return []
        esik = max(esik_c, tol_d)
        budama = esik * (1 + _PAY) + _PAY
        A = np.zeros(1, dtype=np.int64)
        B = np.zeros(1, dtype=np.int64)
        yaprak_a, yaprak_b = [], []
        while A.size:
            ayni = A == B
            g = _bosluk(self.n_lo[A], self.n_hi[A], self.n_lo[B], self.n_hi[B])
            tut = ayni | (g <= budama)
            A, B, ayni = A[tut], B[tut], ayni[tut]
            ya = self.sol[A] < 0
            yb = self.sol[B] < 0
            ikisi = ya & yb
            yaprak_a.append(A[ikisi])
            yaprak_b.append(B[ikisi])
            A, B, ayni, ya, yb = A[~ikisi], B[~ikisi], ayni[~ikisi], ya[~ikisi], yb[~ikisi]
            # aynı düğüm: (L, L), (R, R), (L, R)
            L, R = self.sol[A[ayni]], self.sag[A[ayni]]
            yA = [L, R, L]
            yB = [L, R, R]
            # farklı düğümler: büyüğü (yaprak değilse) böl
            Af, Bf, yaf, ybf = A[~ayni], B[~ayni], ya[~ayni], yb[~ayni]
            boy_a = self.son[Af] - self.bas[Af]
            boy_b = self.son[Bf] - self.bas[Bf]
            bol_a = ~yaf & (ybf | (boy_a >= boy_b))
            for maske, bolunen, sabit in ((bol_a, Af, Bf), (~bol_a, Bf, Af)):
                for cocuk in (self.sol, self.sag):
                    yA.append(cocuk[bolunen[maske]])
                    yB.append(sabit[maske])
            A = np.concatenate(yA)
            B = np.concatenate(yB)
        return self._yapraklar(np.concatenate(yaprak_a), np.concatenate(yaprak_b), esik_c, tol_d)

    def _yapraklar(self, A, B, esik_c, tol_d) -> list[tuple[int, int]]:
        """Yaprak çiftlerinden kutu çiftleri; son karar SPEC 09'un formülüyle."""
        k = _YAPRAK
        ofs = np.arange(k)
        ia = self.bas[A][:, None] + ofs  # (m, k)
        ib = self.bas[B][:, None] + ofs
        ga = ia < self.son[A][:, None]
        gb = ib < self.son[B][:, None]
        Ia = np.broadcast_to(ia[:, :, None], (len(A), k, k))
        Jb = np.broadcast_to(ib[:, None, :], (len(A), k, k))
        gec = ga[:, :, None] & gb[:, None, :]
        ayni = (A == B)[:, None, None]
        gec &= ~ayni | (Ia < Jb)  # aynı yaprakta her çift bir kez, kendisiyle değil
        i = self.sira[Ia[gec]]
        j = self.sira[Jb[gec]]
        i, j = np.minimum(i, j), np.maximum(i, j)
        g = _bosluk(self.lo[i], self.hi[i], self.lo[j], self.hi[j])
        esik = max(esik_c, tol_d)
        aday = g <= esik * (1 + _PAY) + _PAY
        sonuc = []
        for a, b in zip(i[aday].tolist(), j[aday].tolist(), strict=True):
            lo_i, hi_i, lo_j, hi_j = self.lo[a], self.hi[a], self.lo[b], self.hi[b]
            gg = float(np.linalg.norm(np.maximum(0.0, np.maximum(lo_j - hi_i, lo_i - hi_j))))
            if gg < esik_c or gg <= tol_d:
                sonuc.append((a, b))
        return sorted(sonuc)


def _bosluk(lo_a, hi_a, lo_b, hi_b) -> np.ndarray:
    """Kutu boşluğu |max(0, lo_b − hi_a, lo_a − hi_b)|, satır başına."""
    m = np.maximum(0.0, np.maximum(lo_b - hi_a, lo_a - hi_b))
    return np.sqrt(np.einsum("ij,ij->i", m, m))
