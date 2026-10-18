"""SPEC 68b K7: bimetal şerit (Timoshenko 1925), termo-mekanik zincirle tet10 ağında.

Testler yalnız SPEC metninden ve arayüzden yazıldı; uygulama kodu okunmadı.

İki katman eşit kalınlıkta (t1 = t2 = h/2), eşit E, ν = 0, düzgün ΔT:
κ = 3 (α2 − α1) ΔT / (2h), ankastre uç sehimi δ = κ L² / 2.
h = 2, L = 100, α1 = 1.0e-5, α2 = 2.2e-5, ΔT = 100 → κ = 9e-4 1/mm, δ = 4.5 mm.

67a (tet10) ve 67b (core.yukler.thermal_loads) birleşmeden bu test "uygulanmamış" (NotImplementedError) düşer.

Varsayımlar (metin biçim vermiyor):
- tet10 düğüm sırası C3D10 (SPEC 67a): köşe 1–4, kenar 5 (1–2), 6 (2–3), 7 (3–1), 8 (1–4), 9 (2–4), 10 (3–4);
  köşeler pozitif yönlü (det J > 0) dizilir.
- Isıl alan, köşe düğümlerinde düzgün T = T_ref + ΔT olan bir SPEC 56 `ThermalResult`'tır (zincir, köşe
  düğümleri eşleşen tet10 ağını kabul eder). Zincir `zamanlar=[0.0]` ile çağrılır; kararlı sonuç tek zaman
  0.0 sayılır ve `alanlar[0.0] = (u, σ_vM)`; `u` düğüm başına (ux, uy, uz), `reshape(-1, 3)` ile okunur.
- Mesnet 3-2-1'dir (serbest şerit, gerilmesiz eğilir). "Ankastre uç sehimi", orta düzlemdeki (z = h/2, y = 0)
  düğümlerin w(x)'ine uydurulan parabolün `c2·L²` değeridir (kök teğetine göre sehim); eğrilik `2·c2`,
  `x ∈ [30, 70]` aralığına uydurulan parabolden.
"""

from __future__ import annotations

import functools
import importlib.util

import numpy as np
import pytest

from core import elements
from core.isil import ThermalResult
from core.model import BC, Element, Material, Model, Node
from tests.benchmarks.tet_ag import kutu_agi

L, B, H = 100.0, 2.0, 2.0
NX, NY, NZ = 50, 1, 4  # katman başına kalınlıkta 2 eleman
E = 200_000.0
ALFA = {"alt": 1.0e-5, "ust": 2.2e-5}
T_REF, DT = 20.0, 100.0
KAPPA = 3 * (ALFA["ust"] - ALFA["alt"]) * DT / (2 * H)
DELTA = KAPPA * L**2 / 2


def gerekli_67() -> None:
    if importlib.util.find_spec("core.yukler") is None or "tet10" not in elements.ELEMENTS:
        raise NotImplementedError("SPEC 67a (tet10) ve 67b (core.yukler) birleşmeden çalışmaz")


KENARLAR = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))  # C3D10 5..10


def tet10_agi(tet4: Model) -> Model:
    """tet4 ağından tet10: köşeler pozitif yönlü, kenar düğümleri ortak ve kenar ortasında."""
    xyz = {n.id: n.xyz for n in tet4.nodes}
    nodes = list(tet4.nodes)
    kenar_id: dict[tuple[int, int], int] = {}
    sonraki = max(xyz) + 1
    els = []
    for e in tet4.elements:
        k = list(e.nodes)
        X = np.array([xyz[i] for i in k])
        if np.linalg.det(X[1:] - X[0]) < 0:
            k[1], k[2] = k[2], k[1]
        orta = []
        for a, b in KENARLAR:
            anahtar = tuple(sorted((k[a], k[b])))
            if anahtar not in kenar_id:
                kenar_id[anahtar] = sonraki
                p = (xyz[k[a]] + xyz[k[b]]) / 2
                nodes.append(Node(sonraki, *p))
                sonraki += 1
            orta.append(kenar_id[anahtar])
        els.append(Element(e.id, "tet10", k + orta, e.material))
    return Model(dim=3, nodes=nodes, elements=els, materials=tet4.materials, name="bimetal10")


def bimetal() -> tuple[Model, Model]:
    """(ısıl tet4 köşe ağı, mekanik tet10 ağı), malzemeler eleman merkezine göre."""
    malz = [Material("alt", E, 0.0), Material("ust", E, 0.0)]
    t4 = kutu_agi(L, B, H, NX, NY, NZ, malz[0])
    t4.materials = malz
    for e in t4.elements:
        zc = np.mean([t4.node(n).z for n in e.nodes])
        e.material = "alt" if zc < H / 2 else "ust"
    m10 = tet10_agi(t4)

    def bul(x, y, z) -> int:
        return next(n.id for n in t4.nodes if np.allclose(n.xyz, (x, y, z)))

    A, Bx, Cy = bul(0, 0, 0), bul(L, 0, 0), bul(0, B, 0)
    m10.bcs = [BC(A, "ux"), BC(A, "uy"), BC(A, "uz"), BC(Bx, "uy"), BC(Bx, "uz"), BC(Cy, "uz")]
    return t4, m10


@functools.cache
def cozum() -> tuple[Model, np.ndarray]:
    """Zincir bir kez çözülür; testler önce `gerekli_67()` çağırır (uygulanmamış, kurulum hatası değil)."""
    from analiz.termomekanik import zincir

    t4, m10 = bimetal()
    ids = np.array([n.id for n in t4.nodes])
    T = np.full(len(ids), T_REF + DT)
    sicaklik = ThermalResult(ids, T, np.zeros(len(ids)), 0.0, 0.0, 0.0)
    tm = zincir(m10, sicaklik, T_REF, ALFA, zamanlar=[0.0])
    u = np.asarray(tm.alanlar[0.0][0]).reshape(-1, 3)
    return m10, u


def orta_cizgi(m10: Model, u: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    secim = [i for i, n in enumerate(m10.nodes) if abs(n.y) < 1e-9 and abs(n.z - H / 2) < 1e-9]
    x = np.array([m10.nodes[i].x for i in secim])
    w = u[secim, 2]
    sira = np.argsort(x)
    return x[sira], w[sira]


def test_referans_degerler():
    assert KAPPA == pytest.approx(9e-4, rel=1e-12)
    assert DELTA == pytest.approx(4.5, rel=1e-12)


@pytest.mark.slow
def test_bimetal_uc_sehimi():
    gerekli_67()
    m10, u = cozum()
    x, w = orta_cizgi(m10, u)
    c2 = np.polyfit(x, w, 2)[0]
    assert abs(c2) * L**2 == pytest.approx(DELTA, rel=0.02)


@pytest.mark.slow
def test_bimetal_egrilik_orta_bolge():
    gerekli_67()
    m10, u = cozum()
    x, w = orta_cizgi(m10, u)
    orta = (x >= 30.0 - 1e-9) & (x <= 70.0 + 1e-9)
    c2 = np.polyfit(x[orta], w[orta], 2)[0]
    assert abs(2 * c2) == pytest.approx(KAPPA, rel=0.02)
