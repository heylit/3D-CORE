"""SPEC 49 testleri için uydurma tezgâh profilleri, takımlar ve bağımsız referans hesaplar.

Bu modül test değildir (adı test_ ile başlamaz). Yalnız sabit arayüzler (cam/model.py), numpy ve scipy
kullanılır; cam/millturn, cam/sim/millturn.py ve cam/post/millturn.py gövdeleri okunmadı. Beklenen değerler
SPEC 49 "Teori" ve "Hacim formülleri" bölümlerinden yazıldı.

Profiller (`ORNEK-NTX`) uydurmadır (SPEC 49 Karar 1); gerçek tezgâh verisi değildir.
- C ekseni sürekli, rpm_max = 200 dev/dk; Fanuc / MAPPS ikizinde C ekseni M kodları M45 / M46.
- Taret: 1 sabit (torna), 2 canlı radyal, 3 canlı eksenel; canlı takım devri ≤ 6000.
- Y kursu ±10 mm (K5: e = 8 içeride, e = 15 dışarıda).

Hacim formülleri (SPEC 49, dolu mil yarıçapı R, taban düzlemi x = R − t):
- Kama kesiti A = (b/2)·√(R² − b²/4) + R²·asin(b / 2R) − b·(R − t).
- Kama uçları V_uç = ∫_{−b/2}^{b/2} 2√(b²/4 − y²)·(√(R² − y²) − (R − t)) dy.
- Kaçık düz tabanlı delik V = ∫_{−ρ}^{ρ} 2√(ρ² − y²)·(√(R² − (y + e)²) − x_b) dy.
Tek katlı integraller scipy.integrate.quad ile 1e-10 göreli doğrulukta referanstır.
"""

from __future__ import annotations

import math

from scipy.integrate import quad

from cam.model import (
    AxisLimits,
    CAxis,
    CylinderStock,
    MachineProfile,
    Tool,
    ToolKind,
    Turret,
    TurretStation,
)

C_RPM_MAX = 200.0  # dev/dk, C modunda iş mili üst sınırı (uydurma)
ST_SABIT, ST_RADYAL, ST_EKSENEL = 1, 2, 3

STOK = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0)  # dolu mil, R = 20
R = STOK.D / 2


def taret() -> Turret:
    return Turret(
        "ust",
        (
            TurretStation(ST_SABIT),
            TurretStation(ST_RADYAL, live=True),
            TurretStation(ST_EKSENEL, live=True, direction="eksenel"),
        ),
        live_rpm_max=6000.0,
    )


def profil(controller: str = "fanuc", c_axis: CAxis | None = None) -> MachineProfile:
    """Uydurma ORNEK-NTX torna-freze profili (X çap cinsinden kurs)."""
    if c_axis is None:
        if controller == "fanuc":
            c_axis = CAxis(rpm_max=C_RPM_MAX, m_on="M45", m_off="M46")
        else:
            c_axis = CAxis(rpm_max=C_RPM_MAX)
    m = MachineProfile(
        "ORNEK-NTX",
        controller,
        kind="millturn",
        x=AxisLimits(-20.0, 400.0),
        y=AxisLimits(-10.0, 10.0),
        z=AxisLimits(-300.0, 100.0),
        rpm_max=4000.0,
        feed_max=10000.0,
        tool_slots=12,
        c_axis=c_axis,
        turrets=(taret(),),
    )
    m.validate()
    return m


def freze_profili() -> MachineProfile:
    """Uydurma 3 eksen freze profili (torna-freze işlemleri için yanlış tür)."""
    m = MachineProfile("ORNEK-FREZE", "fanuc", rpm_max=8000.0, feed_max=5000.0)
    m.validate()
    return m


def freze(D: float, Lf: float = 30.0, id: int = 5) -> Tool:
    """Düz uçlu canlı freze / düz tabanlı delik takımı (merkezden keser)."""
    return Tool(id, "canli", ToolKind.FLAT, D, Lf)


# ------------------------------------------------------------------ hacim formülleri


def kama_kesit(R: float, b: float, t: float) -> float:
    return (b / 2) * math.sqrt(R * R - b * b / 4) + R * R * math.asin(b / (2 * R)) - b * (R - t)


def kama_kesit_quad(R: float, b: float, t: float) -> float:
    v, _ = quad(lambda y: math.sqrt(R * R - y * y) - (R - t), -b / 2, b / 2, epsrel=1e-10)
    return v


def kama_uc(R: float, b: float, t: float) -> float:
    def f(y: float) -> float:
        return 2 * math.sqrt(max(b * b / 4 - y * y, 0.0)) * (math.sqrt(R * R - y * y) - (R - t))

    v, _ = quad(f, -b / 2, b / 2, epsrel=1e-10)
    return v


def kama_hacmi(R: float, b: float, t: float, L: float) -> float:
    """V = A·L + V_uç (L iki uç merkezi arası boy)."""
    return kama_kesit(R, b, t) * L + kama_uc(R, b, t)


def kacik_delik_hacmi(R: float, rho: float, e: float, x_b: float) -> float:
    def f(y: float) -> float:
        return 2 * math.sqrt(max(rho * rho - y * y, 0.0)) * (math.sqrt(R * R - (y + e) ** 2) - x_b)

    v, _ = quad(f, -rho, rho, epsrel=1e-10)
    return v


def aci_farki(a: float, b: float) -> float:
    """İki açının (derece) mod 360 farkı, (−180, 180]."""
    d = (a - b) % 360.0
    return d - 360.0 if d > 180.0 else d
