"""SPEC 51 K4–K5 — TCP açık eş zamanlı çıkış: açı biçimi ve vektör biçimi, gidiş-dönüş.

Testler yalnız SPEC 51 metninden ve iskelet imzalarından yazıldı (bkz. `post5_ortak`).
Uç konumu WCS'de yazılır: okunan uç `TOL_P` içinde. Açı biçiminde eksen iki döner açıdan kurulur; her açı
en çok `TOL_ACI` yuvarlanır, dönmeler yönü en çok açı hatası kadar saptırır → eksen sapması ≤ 2·`TOL_ACI`.
Vektör biçiminde bileşenler (en az profil ondalığıyla) yazılır: sapma ≤ 0.5·10^−d·√3 rad.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.post import post5, read_program5
from tests.cam.post5_ortak import (
    DILLER,
    KINEMATIKLER,
    KURULUM,
    TAKIMLAR,
    TCP_VEKTOR,
    TOL_ACI,
    TOL_P,
    D,
    aci,
    eksen,
    kesmeler,
    makine,
    tek_yol,
    var_mi,
    yarim_kure,
)

TCP_SOZ = {
    ("sinumerik", "traori"): r"\bTRAORI\b",
    ("heidenhain", "tcpm"): r"\bFUNCTION\s+TCPM\b",
    ("heidenhain", "m128"): r"\bM128\b",
    ("fanuc", "g43.4"): r"\bG43\.4\b",
}
TCP_ACI = [("sinumerik", "traori"), ("heidenhain", "tcpm"), ("heidenhain", "m128"), ("fanuc", "g43.4")]
VEKTOR_SOZ = {
    "sinumerik": (r"\bORIWKS\b", r"\bA3\s*=", r"\bB3\s*=", r"\bC3\s*="),
    "heidenhain": (r"\bLN\b", r"\bTX\b", r"\bTY\b", r"\bTZ\b"),
    "fanuc": (r"\bG43\.5\b", r"\bI\s*[+-]?[\d.]", r"\bK\s*[+-]?[\d.]"),
}
TOL_EKSEN_ACI = 2.0 * TOL_ACI + 1e-9  # derece
TOL_EKSEN_VEKTOR = math.degrees(0.5 * 10.0**-D * math.sqrt(3.0)) + 1e-9  # derece


def _ayni_yol(tp, okunan, tol_eksen: float) -> None:
    a, b = kesmeler(tp), kesmeler(okunan)
    assert len(b) == len(a)
    for i, (ma, mb) in enumerate(zip(a, b, strict=True)):
        assert np.linalg.norm(np.subtract(mb.end, ma.end)) <= TOL_P, f"hareket {i} uç"
        assert mb.axis is not None, f"hareket {i}: okunan eksen yok"
        assert abs(np.linalg.norm(mb.axis) - 1.0) <= 1e-9, f"hareket {i}: okunan eksen birim değil"
        assert aci(mb.axis, eksen(ma)) <= tol_eksen, f"hareket {i} eksen"


# ---------------------------------------------------------------- K4 açı biçimi


@pytest.mark.parametrize("kin_ad", list(KINEMATIKLER))
@pytest.mark.parametrize("dil, tcp", TCP_ACI, ids=[f"{d}-{t}" for d, t in TCP_ACI])
def test_k4_aci_bicimi_gidis_donus(dil, tcp, kin_ad):
    m = makine(dil, KINEMATIKLER[kin_ad](), tcp=tcp)
    tp = yarim_kure()
    metin = post5([tp], m, KURULUM, TAKIMLAR)
    assert var_mi(metin, TCP_SOZ[(dil, tcp)])
    _ayni_yol(tp, tek_yol(read_program5(metin, m, TAKIMLAR)), TOL_EKSEN_ACI)


@pytest.mark.parametrize("dil", DILLER)
def test_k4_tcp_bitisi_yaziliyor(dil):
    """TCP kapanışı: `TRAFOOF`, `FUNCTION RESET TCPM` (veya `M129`), `G49`."""
    bitis = {
        "sinumerik": r"\bTRAFOOF\b",
        "heidenhain": r"\bFUNCTION\s+RESET\s+TCPM\b|\bM129\b",
        "fanuc": r"\bG49\b",
    }
    metin = post5([yarim_kure()], makine(dil, KINEMATIKLER["ac_masa"]()), KURULUM, TAKIMLAR)
    assert var_mi(metin, bitis[dil])


# ---------------------------------------------------------------- K5 vektör biçimi


@pytest.mark.parametrize("kin_ad", list(KINEMATIKLER))
@pytest.mark.parametrize("dil", DILLER)
def test_k5_vektor_bicimi_gidis_donus(dil, kin_ad):
    m = makine(dil, KINEMATIKLER[kin_ad](), tcp=TCP_VEKTOR[dil], vector=True)
    tp = yarim_kure()
    metin = post5([tp], m, KURULUM, TAKIMLAR)
    for desen in VEKTOR_SOZ[dil]:
        assert var_mi(metin, desen), desen
    _ayni_yol(tp, tek_yol(read_program5(metin, m, TAKIMLAR)), TOL_EKSEN_VEKTOR)
