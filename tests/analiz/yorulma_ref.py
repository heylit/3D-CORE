"""SPEC 68d testleri için ortak uydurma malzemeler ve kapalı formlar (analiz/yorulma.py gövdesine bakılmadan).

Bu modül test değildir (adı test_ ile başlamaz). Formüller specs/68d-yorulma.md "Teori" bölümünden
(Shigley 10. baskı, bölüm 6):
    Se' = sigma_f; yoksa çelikte 0.5 Rm (Rm ≤ 1400), 700 (Rm > 1400)
    ka = a·Rm^b, kb = 1.24 d^(−0.107) (2.79 ≤ d ≤ 51), 1.51 d^(−0.157) (51 < d ≤ 254)
    n_f = 1/(σa/Se + σm/Rm) (σm ≥ 0), Se/σa (σm < 0); σar = σa/(1 − σm/Rm)
    a = (f Rm)²/Se, b = −(1/3) log10(f Rm/Se), N = (σar/a)^(1/b)
Malzeme.__post_init__ B2 kodu gelene kadar NotImplementedError verir: malzemeler modül düzeyinde kurulmaz.
"""

from __future__ import annotations

import math

import core.model
import malzeme.model
from malzeme.model import Malzeme

# İki ModelError sınıfı da ValueError'dan türer; SPEC "ModelError" der, hangisinin geleceği belirtilmez.
HATALAR = (core.model.ModelError, malzeme.model.ModelError)

E, NU = 210_000.0, 0.3
RM, RP02 = 600.0, 340.0
F_SN = 0.9  # 10³ çevrimde f·Rm

KA_AB = {
    "taslanmis": (1.58, -0.085),
    "islenmis": (4.51, -0.265),
    "sicak_haddelenmis": (57.7, -0.718),
    "dovme": (272.0, -0.995),
}
KE = {50: 1.000, 90: 0.897, 99: 0.814, 99.9: 0.753}
KC = {"egme": 1.0, "eksenel": 0.85, "burulma": 0.59, "birlesik": 1.0}


def celik(Rm: float | None = RM, sigma_f: float | None = None, grup: str = "celik", **kw) -> Malzeme:
    """Uydurma çelik kaydı (C45 benzeri, değerler testlere özel)."""
    alanlar = dict(
        id="TEST-CELIK",
        name="Deneme celigi",
        standart="",
        grup=grup,
        kaynak="uydurma test verisi",
        iso513="M" if grup == "paslanmaz" else "P",
        E=E,
        nu=NU,
        rho=7.85e-9,
        Rp02=RP02,
        Rm=Rm,
        sigma_f=sigma_f,
    )
    alanlar.update(kw)
    return Malzeme(**alanlar)


def aluminyum(sigma_f: float | None = None) -> Malzeme:
    return Malzeme(
        id="TEST-AL",
        name="Deneme aluminyumu",
        standart="",
        grup="aluminyum",
        kaynak="uydurma test verisi",
        iso513="N",
        E=70_000.0,
        nu=0.33,
        rho=2.7e-9,
        Rp02=240.0,
        Rm=290.0,
        sigma_f=sigma_f,
    )


def ka(yuzey: str, Rm: float) -> float:
    a, b = KA_AB[yuzey]
    return a * Rm**b


def kb(d: float | None) -> float:
    if d is None:
        return 1.0
    return 1.24 * d**-0.107 if d <= 51 else 1.51 * d**-0.157


def se_ussu(Rm: float, sigma_f: float | None = None) -> float:
    """Çelik grubunda Se'."""
    if sigma_f is not None:
        return sigma_f
    return 0.5 * Rm if Rm <= 1400 else 700.0


def nf_kapali(sa: float, sm: float, Se: float, Rm: float) -> float:
    if sa == 0:
        return math.inf
    if sm < 0:
        return Se / sa
    return 1.0 / (sa / Se + sm / Rm)


def N_kapali(sa: float, sm: float, Se: float, Rm: float, f: float = F_SN) -> float:
    sar = sa / (1 - sm / Rm) if sm >= 0 else sa
    if sar <= Se:
        return math.inf
    a = (f * Rm) ** 2 / Se
    b = -(1 / 3) * math.log10(f * Rm / Se)
    return (sar / a) ** (1 / b)
