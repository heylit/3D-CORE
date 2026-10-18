"""SPEC 51 K6 — TCP kapalı eş zamanlı çıkış ve G93 ters zaman ilerlemesi.

Testler yalnız SPEC 51 metninden, iskelet imzalarından ve main'deki SPEC 42 işlevlerinden yazıldı
(bkz. `post5_ortak`). Analitik durum 42 K7: A masalı 4 eksen, uç A ekseninden r = 50 uzakta, Δ = 30°.

Beklenen F değerleri 42'nin kendisiyle hesaplanır: `linearize` (post5 varsayılanları tol_p = 1e-3,
tol_a = 0.05) → `joint_path` → `inverse_time`. Yazılan F, yazılan ondalığın yuvarlaması içinde ve rel 1e-9.
G1 kipseldir: G93 kipinde koordinat sözcüğü taşıyan her kesme satırı (G1 açıkça yazılsın ya da yazılmasın)
F içermeli; G0'dan önce ve program sonunda G94.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from cam.model import Wcs
from cam.multiaxis.linearize import inverse_time, joint_path, linearize
from cam.post import post5, read_program5
from tests.cam.post5_ortak import (
    KURULUM,
    L_TAKIM,
    TAKIMLAR,
    TOL_P,
    a_masa,
    kesmeler,
    makine,
    sozcukler,
    tek_yol,
    yay_yolu,
)

TOL_P_POST = 1e-3  # post5 varsayılanı
TOL_A_POST = 0.05
DILLER_G93 = ["sinumerik", "fanuc"]  # Heidenhain'de TCP kapalı eş zamanlı yok (K8)

_G = re.compile(r"\bG0*(\d+(?:\.\d+)?)\b")
_KOORD = re.compile(r"\b[XYZABC]\s*=?\s*(?:[A-Z]+\()?\s*[+-]?[\d.]")
_F = re.compile(r"\bF\s*=?\s*([+-]?(?:\d+\.?\d*|\.\d+))")


def g93_tara(metin: str) -> tuple[list[tuple[int, str | None]], list[str]]:
    """G93 kipindeki kesme satırları [(satır indeksi, F sözcüğü ya da None)] ve kural ihlalleri."""
    satirlar: list[tuple[int, str | None]] = []
    ihlal: list[str] = []
    g93 = False
    hareket = None
    son_g93 = -1
    for i, ham in enumerate(metin.splitlines()):
        s = sozcukler(ham)
        gler = set(_G.findall(s))
        if "94" in gler:
            g93 = False
        if "93" in gler:
            g93 = True
        if "0" in gler:
            hareket = 0
            if g93:
                ihlal.append(f"satır {i + 1}: G93 kipinde G0 (önce G94 gerekir): {ham!r}")
        elif "1" in gler:
            hareket = 1
        if g93 and hareket == 1 and _KOORD.search(s):
            f = _F.search(s)
            satirlar.append((i, None if f is None else f.group(1)))
            son_g93 = i
    if g93:
        ihlal.append("program G93 kipinde bitiyor (sonda G94 yok)")
    if son_g93 < 0:
        ihlal.append("G93 kipinde kesme satırı yok")
    return satirlar, ihlal


def _beklenen(wcs: Wcs):
    tp = yay_yolu(50.0, 30.0)
    kin = a_masa()
    lin = linearize(tp, kin, wcs, L_TAKIM, tol_p=TOL_P_POST, tol_a=TOL_A_POST)
    Q = joint_path(lin, kin, wcs, L_TAKIM)
    return tp, lin, inverse_time(lin, Q)


def test_beklenen_analitik_durum():
    """42 K7: dönme hareketi 2⁶ parçaya bölünür; yaklaşma bölünmez."""
    _, lin, F = _beklenen(KURULUM.wcs)
    assert len(lin.moves) == 1 + 2**6
    assert F.shape == (len(lin.moves),)
    assert np.all(F > 0)


@pytest.mark.parametrize("dil", DILLER_G93)
def test_k6_g93_f_degerleri_ve_kurallar(dil):
    tp, lin, F = _beklenen(KURULUM.wcs)
    m = makine(dil, a_masa(), tcp="yok")
    metin = post5([tp], m, KURULUM, TAKIMLAR)
    satirlar, ihlal = g93_tara(metin)
    assert not ihlal, "\n".join(ihlal)
    eksik = [i + 1 for i, f in satirlar if f is None]
    assert not eksik, f"F'siz G1 satırları (G93 kipel değil): {eksik}"
    assert len(satirlar) == len(F)
    for (i, tok), f in zip(satirlar, F, strict=True):
        k = len(tok.split(".")[1]) if "." in tok else 0
        tol = 0.5 * 10.0**-k + 1e-9 * f
        assert abs(float(tok) - f) <= tol, f"satır {i + 1}: F{tok} ≠ {f:.9g}"


@pytest.mark.parametrize("dil", DILLER_G93)
def test_k6_okununca_uc_yolu(dil):
    """Okuyucu eklem değerlerinden `forward` ile uç yolunu kurar: doğrusallaştırılmış noktalarla aynı."""
    tp, lin, _ = _beklenen(KURULUM.wcs)
    m = makine(dil, a_masa(), tcp="yok")
    okunan = tek_yol(read_program5(post5([tp], m, KURULUM, TAKIMLAR), m, TAKIMLAR))
    a, b = kesmeler(lin), kesmeler(okunan)
    assert len(b) == len(a)
    for i, (ma, mb) in enumerate(zip(a, b, strict=True)):
        assert np.linalg.norm(np.subtract(mb.end, ma.end)) <= TOL_P_POST + TOL_P, f"hareket {i}"
    # özgün iki uç (yaklaşma sonu ve dönme sonu) okunan yolda
    for p in tp.points()[1:]:
        assert min(np.linalg.norm(np.subtract(mb.end, p)) for mb in b) <= TOL_P_POST + TOL_P
