"""
Yüksek çevrimli yorulma: Marin düzeltmesi, Basquin S-N doğrusu, Goodman (SPEC 68d).

Statik çözümün sonrasında, ek FEM çözümü olmadan düğüm başına iki sonuç:
    n_f   yorulma emniyet katsayısı (Goodman)
    N     tahmini ömür [çevrim] (S-N, Basquin)
Çok eksenli gerilme, genlik ve ortalama tensörlerinin (işaretli) von Mises eşdeğeriyle tek eksene indirgenir.
Sonuç bir ön değerlendirmedir: çentik hassasiyeti, yük spektrumu ve rainflow sayımı yok.

Teori: specs/68d-yorulma.md
Kaynak: Budynas–Nisbett, Shigley's Mechanical Engineering Design, 10. baskı, bölüm 6.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np

from core.model import Model
from malzeme.model import Malzeme

YUZEYLER = ("taslanmis", "islenmis", "sicak_haddelenmis", "dovme")


@dataclass(frozen=True)
class Marin:
    """Marin düzeltme faktörlerinin girdileri:  Se = ka kb kc kd ke · Se'."""

    yuzey: str = "islenmis"  # YUZEYLER'den biri
    d: float | None = None  # mm, eşdeğer çap; None → kb = 1
    yuk: Literal["egme", "eksenel", "burulma", "birlesik"] = "birlesik"
    kd: float = 1.0  # sıcaklık faktörü
    guvenilirlik: Literal[50, 90, 99, 99.9] = 50  # %

    def katsayilar(self, Rm: float) -> dict[str, float]:
        """ka, kb, kc, kd, ke. Bilinmeyen yüzey, aralık dışı d, geçersiz güvenilirlik → ModelError."""
        raise NotImplementedError("SPEC 68d: Marin.katsayilar")


MARIN_VARSAYILAN = Marin()


def dayanim_siniri(malzeme: Malzeme, marin: Marin) -> float:
    """Düzeltilmiş dayanım sınırı Se [MPa].

    Se' = sigma_f; yoksa çelik grubunda Rm'den (0.5 Rm, en çok 700); diğer gruplarda ModelError.
    """
    raise NotImplementedError("SPEC 68d: dayanim_siniri")


def goodman(sigma_a, sigma_m, Se: float, Rm: float) -> np.ndarray:
    """n_f (vektörel). σ_m ≥ 0: 1/(σ_a/Se + σ_m/Rm); σ_m < 0: Se/σ_a; σ_a = 0: inf."""
    raise NotImplementedError("SPEC 68d: goodman")


def omur(sigma_a, sigma_m, Se: float, Rm: float, f: float = 0.9) -> np.ndarray:
    """N [çevrim] (vektörel), Basquin doğrusu 10³'te f·Rm, 10⁶'da Se. σ_ar ≤ Se → inf."""
    raise NotImplementedError("SPEC 68d: omur")


@dataclass(frozen=True)
class Yorulma:
    """Düğüm başına yorulma sonucu; diziler (n_dugum,), model.nodes sırasında."""

    sigma_a: np.ndarray  # MPa, genlik (von Mises)
    sigma_m: np.ndarray  # MPa, ortalama (işaretli von Mises)
    n_f: np.ndarray  # Goodman emniyet katsayısı
    n_y: np.ndarray  # ilk çevrim akma (Langer)
    N: np.ndarray  # çevrim; inf olabilir
    dusuk_cevrim: np.ndarray  # bool
    n_f_min: float
    dugum: int  # n_f_min'in düğüm id'si
    konum: np.ndarray  # (3,) mm
    N_min: float
    Se: float  # MPa
    katsayilar: Mapping[str, float]  # ka, kb, kc, kd, ke
    not_: str  # "ön değerlendirme; çentik/spektrum yok" ve uyarılar


def yorulma(
    model: Model,
    u_A: np.ndarray,
    u_B: np.ndarray | None = None,
    *,
    R: float | None = None,
    malzeme: Malzeme,
    marin: Marin = MARIN_VARSAYILAN,
) -> Yorulma:
    """İki yük durumu (u_A, u_B) ya da tek yük ve R = σ_min/σ_max oranından düğüm başına yorulma.

    u_B ile R ikisi birden ya da hiçbiri → ModelError; R ∉ [−1, 1) → ModelError.
    """
    raise NotImplementedError("SPEC 68d: yorulma")


def parca_yorulmasi(
    part,
    h: float,
    malzeme: Malzeme,
    *,
    marin: Marin,
    sabit,
    yuk_A,
    yuk_B=None,
    R: float | None = None,
    order: int = 2,
) -> Yorulma:
    """Parça → ağ → statik çözüm → yorulma (67b köprü dili)."""
    raise NotImplementedError("SPEC 68d: parca_yorulmasi")
