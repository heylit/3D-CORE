"""
Chatter kararlılık lobu, ölçülmüş FRF ile. SPEC 71.

Frezeleme: Altintas–Budak sıfırıncı mertebe (2 serbestlik, x–y).
    Λ = −1/λ,  κ = Λ_I / Λ_R,  a_lim = −2π Λ_R (1 + κ²) / (N K_t),
    ε = π − 2 atan κ,  T = (ε + 2kπ)/ω_c,  n = 60/(N T)
Tornalama: Tlusty tek yönlü,  a_lim = −1 / (2 K_s Re[G_or(iω_c)]),  Re G_or < 0.
Kaynak: Altintas & Budak, CIRP Annals 44 (1995); Altintas, Manufacturing Automation (2012), bölüm 2–3;
Tlusty, Manufacturing Processes and Equipment (2000), bölüm 9.

Birimler: FRF mm/N, K_t N/mm², paso mm, devir dev/dk, frekans Hz. Hatalar cam.model.CamError
(SPEC'teki "ModelError"; cam paketinin hata sınıfı). FRF verilmezse varsayılan yoktur, hata verilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

if TYPE_CHECKING:
    from cam.frf import FRF, TakimFRF
    from cam.model import MachineProfile, Tool

FRF_GEREKLI = "Chatter lobu için takım ucunun çekiç testi FRF ölçümü gerekir"


@dataclass(frozen=True)
class Lob:
    n: np.ndarray  # (p,) dev/dk, ızgara
    a_lim: np.ndarray  # (p,) mm, lob zarfı; geçersiz noktalarda değer yok ('gecerli' maskesi)
    gecerli: np.ndarray  # (p,) bool, ölçüm bandından hesaplanabildi mi
    loblar: tuple[tuple[np.ndarray, np.ndarray], ...]  # k başına (n, a)
    K_t: float
    K_r: float
    varsayilan_Kr: bool


def yonsel_katsayilar(phi_st: float, phi_ex: float, K_r: float) -> np.ndarray:
    """Altintas–Budak yönsel katsayı matrisi [[α_xx, α_xy], [α_yx, α_yy]] (φ_st'den φ_ex'e)."""
    raise NotImplementedError("SPEC 71: yonsel_katsayilar")


def kesme_katsayisi(malzeme, fz: float, phi_st: float, phi_ex: float) -> float:
    """Kienzle'den eşdeğer teğetsel katsayı K_t = kc11 · h_m^(−mc) [N/mm²] (K7).

    h_m = fz / (φ_ex − φ_st) · (cos φ_st − cos φ_ex). `malzeme` kc11 ve mc özniteliği taşır:
    malzeme.model.Malzeme (66) ya da cam.kuvvet.KienzleMaterial (32); import edilmez (K10).
    kc11 / mc yoksa (None) CamError.
    """
    raise NotImplementedError("SPEC 71: kesme_katsayisi")


def lob_freze(
    frf: TakimFRF | None,
    takim: Tool,
    *,
    ae: float,
    yon: Literal["karsi", "ayni"],
    n_aralik: tuple[float, float],
    fz: float | None = None,
    K_t: float | None = None,
    K_r: float | None = None,
    malzeme=None,  # kc11, mc öznitelikli (Malzeme 66 / KienzleMaterial 32); K_t yoksa gerekir
    lob_sayisi: int = 10,
    profil: MachineProfile | None = None,
) -> Lob:
    """Frezeleme kararlılık lobu (sıfırıncı mertebe)."""
    raise NotImplementedError("SPEC 71: lob_freze")


def lob_torna(
    frf: FRF | None,
    *,
    K_s: float | None = None,
    malzeme=None,
    fn: float | None = None,
    u: float = 1.0,
    n_aralik: tuple[float, float],
    lob_sayisi: int = 10,
    profil: MachineProfile | None = None,
) -> Lob:
    """Tornalama kararlılık lobu (Tlusty, tek yönlü)."""
    raise NotImplementedError("SPEC 71: lob_torna")


def karar(lob: Lob, n: float, ap: float, pay: float = 0.8) -> dict:
    """{"durum": "kararli" | "sinirda" | "kararsiz" | "bilinmiyor", "a_lim", "oneri_n", "oneri_ap"}.

    sinirda: pay·a_lim < ap ≤ a_lim.
    """
    raise NotImplementedError("SPEC 71: karar")
