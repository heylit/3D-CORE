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

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np

from core.model import Model, ModelError
from core.post import nodal_stress_tensors, von_mises
from malzeme.model import Malzeme

YUZEYLER = ("taslanmis", "islenmis", "sicak_haddelenmis", "dovme")

# ka = a · Rm^b (Shigley tablo 6-2)
_KA_AB = {
    "taslanmis": (1.58, -0.085),
    "islenmis": (4.51, -0.265),
    "sicak_haddelenmis": (57.7, -0.718),
    "dovme": (272.0, -0.995),
}
# kc: von Mises eşdeğeri kullanılan birleşik yükte burulma da 1 (Shigley birleşik yük kuralı)
_KC = {"egme": 1.0, "eksenel": 0.85, "burulma": 0.59, "birlesik": 1.0}
# ke: güvenilirlik % → faktör (Shigley tablo 6-5)
_KE = {50: 1.000, 90: 0.897, 99: 0.814, 99.9: 0.753}
_CELIK_GRUPLARI = ("celik", "paslanmaz")
_N_DUSUK = 1e3  # S-N doğrusunun düşük çevrim ucu
_NOT = "ön değerlendirme; çentik hassasiyeti, yük spektrumu ve rainflow sayımı yok"


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
        if self.yuzey not in _KA_AB:
            raise ModelError(f"Bilinmeyen yüzey '{self.yuzey}': {YUZEYLER} olmalı")
        if self.yuk not in _KC:
            raise ModelError(f"Bilinmeyen yük tipi '{self.yuk}': {tuple(_KC)} olmalı")
        if self.guvenilirlik not in _KE:
            raise ModelError(f"Güvenilirlik %{self.guvenilirlik} tabloda yok: {tuple(_KE)} olmalı")
        if not (math.isfinite(self.kd) and self.kd > 0):
            raise ModelError(f"Sıcaklık faktörü kd pozitif ve sonlu olmalı ({self.kd})")
        if not (math.isfinite(Rm) and Rm > 0):
            raise ModelError(f"Rm pozitif ve sonlu olmalı ({Rm})")
        a, b = _KA_AB[self.yuzey]
        return {
            "ka": a * Rm**b,
            "kb": _kb(self.d),
            "kc": _KC[self.yuk],
            "kd": float(self.kd),
            "ke": _KE[self.guvenilirlik],
        }


def _kb(d: float | None) -> float:
    """Boyut faktörü: 2.79 ≤ d ≤ 51 → 1.24 d^(−0.107); 51 < d ≤ 254 → 1.51 d^(−0.157); d yok → 1."""
    if d is None:
        return 1.0
    if not 2.79 <= d <= 254.0:  # nan da buraya düşer
        raise ModelError(f"Eşdeğer çap d = {d} mm, kb aralığı 2.79–254 mm dışında")
    return 1.24 * d**-0.107 if d <= 51.0 else 1.51 * d**-0.157


MARIN_VARSAYILAN = Marin()


def dayanim_siniri(malzeme: Malzeme, marin: Marin) -> float:
    """Düzeltilmiş dayanım sınırı Se [MPa].

    Se' = sigma_f; yoksa çelik grubunda Rm'den (0.5 Rm, en çok 700); diğer gruplarda ModelError.
    """
    Rm = _Rm(malzeme)
    if malzeme.sigma_f is not None:
        Se_ussu = float(malzeme.sigma_f)
    elif malzeme.grup in _CELIK_GRUPLARI:
        Se_ussu = 0.5 * Rm if Rm <= 1400.0 else 700.0  # Shigley eş. 6-8
    else:
        raise ModelError(
            f"'{malzeme.id}' ({malzeme.grup}) için dayanım sınırı yok: sigma_f verilmeli "
            "(çelik dışı malzemede Rm'den tahmin edilmez)"
        )
    k = marin.katsayilar(Rm)
    return k["ka"] * k["kb"] * k["kc"] * k["kd"] * k["ke"] * Se_ussu


def _Rm(malzeme: Malzeme) -> float:
    if malzeme.Rm is None:
        raise ModelError(f"'{malzeme.id}' malzemesinde Rm yok")
    return float(malzeme.Rm)


def _sigma_ar(sigma_a: np.ndarray, sigma_m: np.ndarray, Rm: float) -> np.ndarray:
    """Eşdeğer tam değişken genlik: σ_m ≥ 0 → σ_a / (1 − σ_m/Rm); σ_m < 0 → σ_a. σ_m ≥ Rm → inf."""
    with np.errstate(divide="ignore", invalid="ignore"):
        payda = 1.0 - sigma_m / Rm
        sar = np.where(sigma_m >= 0, sigma_a / np.where(payda > 0, payda, 1.0), sigma_a)
    return np.where((sigma_m >= Rm) & (sigma_a > 0), np.inf, sar)


def goodman(sigma_a, sigma_m, Se: float, Rm: float) -> np.ndarray:
    """n_f (vektörel). σ_m ≥ 0: 1/(σ_a/Se + σ_m/Rm); σ_m < 0: Se/σ_a; σ_a = 0: inf."""
    sa, sm = np.broadcast_arrays(np.asarray(sigma_a, dtype=float), np.asarray(sigma_m, dtype=float))
    with np.errstate(divide="ignore"):
        n_f = np.where(sm >= 0, 1.0 / (sa / Se + np.maximum(sm, 0.0) / Rm), Se / sa)
    return np.where(sa == 0, np.inf, n_f)


def omur(sigma_a, sigma_m, Se: float, Rm: float, f: float = 0.9) -> np.ndarray:
    """N [çevrim] (vektörel), Basquin doğrusu 10³'te f·Rm, 10⁶'da Se. σ_ar ≤ Se → inf.

    σ_ar ≥ f·Rm (düşük çevrim, kapsam dışı): nan yerine (0, 1e3] aralığına kırpılmış N.
    """
    sa, sm = np.broadcast_arrays(np.asarray(sigma_a, dtype=float), np.asarray(sigma_m, dtype=float))
    sar = _sigma_ar(sa, sm, Rm)
    a = (f * Rm) ** 2 / Se
    b = -(1.0 / 3.0) * math.log10(f * Rm / Se)
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        N = (np.where(sar > Se, sar, a) / a) ** (1.0 / b)
    N = np.clip(N, np.finfo(float).tiny, None)  # sar = inf → 0 olmasın
    N = np.where(sar >= f * Rm, np.minimum(N, _N_DUSUK), N)
    return np.where(sar <= Se, np.inf, N)


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
    if (u_B is None) == (R is None):
        raise ModelError("İkinci yük durumu için u_B ya da R'den yalnız biri verilmeli")
    if R is not None and not -1.0 <= R < 1.0:  # nan da buraya düşer
        raise ModelError(f"R = {R}: −1 ≤ R < 1 olmalı (R = 1 değişken yük değildir)")
    Rm = _Rm(malzeme)
    if malzeme.Rp02 is None:
        raise ModelError(f"'{malzeme.id}' malzemesinde Rp02 yok")
    Se = dayanim_siniri(malzeme, marin)
    katsayilar = marin.katsayilar(Rm)

    S_A = _dugum_gerilmeleri(model, u_A)
    S_B = R * S_A if R is not None else _dugum_gerilmeleri(model, u_B)
    S_a, S_m = (S_A - S_B) / 2.0, (S_A + S_B) / 2.0
    sigma_a = np.atleast_1d(von_mises(S_a))
    iz = S_m[:, 0] + S_m[:, 1] + S_m[:, 2]
    sigma_m = np.where(iz < 0, -1.0, 1.0) * np.atleast_1d(von_mises(S_m))  # işaretli von Mises

    n_f = goodman(sigma_a, sigma_m, Se, Rm)
    with np.errstate(divide="ignore"):
        n_y = float(malzeme.Rp02) / (sigma_a + np.abs(sigma_m))  # Langer
    N = omur(sigma_a, sigma_m, Se, Rm)
    dusuk = _sigma_ar(sigma_a, sigma_m, Rm) >= 0.9 * Rm

    i = int(np.argmin(n_f))
    dugum = model.nodes[i]
    notlar = [_NOT]
    if marin.d is None:
        notlar.append("kb = 1 alındı (eşdeğer çap d verilmedi)")
    if dusuk.any():
        notlar.append(f"{int(dusuk.sum())} düğümde düşük çevrim, kapsam dışı (N ≤ 1e3 kırpıldı)")
    return Yorulma(
        sigma_a=sigma_a,
        sigma_m=sigma_m,
        n_f=n_f,
        n_y=n_y,
        N=N,
        dusuk_cevrim=dusuk,
        n_f_min=float(n_f[i]),
        dugum=dugum.id,
        konum=np.asarray(dugum.xyz, dtype=float),
        N_min=float(np.min(N)),
        Se=Se,
        katsayilar=katsayilar,
        not_="; ".join(notlar),
    )


def _dugum_gerilmeleri(model: Model, u: np.ndarray) -> np.ndarray:
    """(n_dugum, 6) düğüm gerilme tensörleri, model.nodes sırasında (SPEC 13)."""
    u = np.asarray(u, dtype=float)
    if u.shape != (model.n_dof,):
        raise ModelError(f"u boyu {u.shape}, modelin {model.n_dof} serbestlik derecesiyle uyuşmuyor")
    S = nodal_stress_tensors(model, u)
    eksik = [n.id for n in model.nodes if n.id not in S]
    if eksik:
        raise ModelError(f"{len(eksik)} düğüm katı elemana ait değil, gerilmesi yok (ilk: {eksik[0]})")
    return np.array([S[n.id] for n in model.nodes], dtype=float)


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
    """Parça → ağ → statik çözüm → yorulma (67b köprü dili). 67b birleşince yazılacak (K7)."""
    raise NotImplementedError("SPEC 68d: parca_yorulmasi (SPEC 67b parça köprüsünü bekliyor)")
