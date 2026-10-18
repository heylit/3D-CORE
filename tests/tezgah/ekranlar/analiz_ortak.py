"""
SPEC 47c testlerinin ortak yardımcıları: beklenen değerleri köprüden bağımsız kurmak.

Ağ `mesh.tet_mesh` + `boundary_triangles` (SPEC 12), çözüm `core.solver.solve` + `nodal_stress_tensors` +
`von_mises` + `principal_stresses` (SPEC 11, 13), eleman hacmi ve barisentrik ara değer elle (numpy).
Örnek işler OCCT ve gmsh ister: bunları kullanan testler `@pytest.mark.occt` ile işaretlidir ve gmsh'i
`pytest.importorskip("gmsh")` ile ister (SPEC 47 kabul kriterleri).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

ANALIZ = "/api/ekran/analiz"
ORNEK_ADLARI = ("delikli_plaka", "konsol_kiris")
KONTROL_ALANLARI = {"kimlik", "baslik", "deger", "birim", "durum", "aciklama", "spec"}


def jt(x):
    """JSON gidiş-dönüşü (nan/inf yasak)."""
    return json.loads(json.dumps(x, allow_nan=False))


def ornek(ad: str):
    """Örnek tanımı (`_analiz_ornekler.ORNEKLER`); gmsh yoksa atlanır (OCCT işareti testte)."""
    pytest.importorskip("gmsh", reason="gmsh kurulu değil (pip install -e .[mesh])")
    from tezgah.ekranlar import _analiz_ornekler as ao

    return ao.ORNEKLER[ad]()


def ag_modeli(tanim, h: float | None = None):
    """Tanımın temiz ağı, doğrudan SPEC 12 ile: (model, düğüm kimlikleri, X, sınır üçgenleri)."""
    from mesh import boundary_triangles, tet_mesh

    m = tet_mesh(
        tanim.parca,
        tanim.h if h is None else h,
        tanim.malzeme,
        refine=tanim.refine,
        max_nodes=tanim.max_nodes,
    )
    ids = np.array([n.id for n in m.nodes], dtype=np.int64)
    X = np.array([[n.x, n.y, n.z] for n in m.nodes], dtype=float)
    return m, ids, X, boundary_triangles(m)


def L_kutu(parca) -> float:
    lo, hi = parca.bbox
    return float(np.linalg.norm(np.asarray(hi) - np.asarray(lo)))


def tet_dizileri(model) -> tuple[np.ndarray, np.ndarray]:
    """(X (nd, 3), tet düğüm indeksleri (ne, 4)) model.nodes sırasıyla."""
    idx = {n.id: i for i, n in enumerate(model.nodes)}
    X = np.array([[n.x, n.y, n.z] for n in model.nodes], dtype=float)
    E = np.array([[idx[k] for k in e.nodes] for e in model.elements if e.type == "tet4"], dtype=np.int64)
    return X, E


def eleman_hacmi(model) -> float:
    """Σ |det[x1 − x0, x2 − x0, x3 − x0]| / 6."""
    X, E = tet_dizileri(model)
    P = X[E]
    D = np.linalg.det(np.stack([P[:, 1] - P[:, 0], P[:, 2] - P[:, 0], P[:, 3] - P[:, 0]], axis=-1))
    return float(np.abs(D).sum() / 6.0)


def barisentrik_sonda(model, degerler, p0, p1, n: int, eps: float = 1e-9):
    """[p0, p1] üzerinde n eşit aralıklı noktada, içeren tetin (λ ≥ −eps) barisentrik değeri (elle)."""
    X, E = tet_dizileri(model)
    v = np.asarray(degerler, dtype=float)
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    t = np.linspace(0.0, 1.0, n)
    P = p0 + t[:, None] * (p1 - p0)
    s = t * np.linalg.norm(p1 - p0)
    A = X[E]
    M = np.stack([A[:, 1] - A[:, 0], A[:, 2] - A[:, 0], A[:, 3] - A[:, 0]], axis=-1)  # (ne, 3, 3)
    Minv = np.linalg.inv(M)
    deger = np.zeros(n)
    iceride = np.zeros(n, dtype=np.uint8)
    for k, p in enumerate(P):
        l123 = np.einsum("eij,ej->ei", Minv, p - A[:, 0])
        lam = np.column_stack([1.0 - l123.sum(axis=1), l123])
        ok = np.flatnonzero((lam >= -eps).all(axis=1))
        if len(ok):
            e = ok[0]
            deger[k] = float(lam[e] @ v[E[e]])
            iceride[k] = 1
    return s, deger, iceride


def cozum(model):
    """Doğrudan SPEC 11 / 13: (u (nd, 3), σ (nd, 6) core sırası, vm (nd,), asal (nd, 3), Result)."""
    from core.post import nodal_stress_tensors, principal_stresses, von_mises
    from core.solver import solve

    r = solve(model)
    u = np.asarray(r.u, dtype=float).reshape(-1, 3)
    S = nodal_stress_tensors(model, r.u)
    sigma = np.array([S[n.id] for n in model.nodes], dtype=float)
    return u, sigma, von_mises(sigma), principal_stresses(sigma), r


def toplamlar(model, r) -> tuple[np.ndarray, np.ndarray]:
    """(tepki toplamı (3,), Load toplamı (3,)) eksen başına."""
    R = np.asarray(r.reactions, dtype=float).reshape(-1, 3).sum(axis=0)
    F = np.zeros(3)
    for ld in model.loads:
        F[("ux", "uy", "uz").index(ld.dof)] += ld.value
    return R, F


def kontrol(kontroller: list[dict], kimlik: str) -> dict:
    k = [x for x in kontroller if x["kimlik"] == kimlik]
    assert len(k) == 1, (kimlik, [x["kimlik"] for x in kontroller])
    assert set(k[0]) == KONTROL_ALANLARI, k[0]
    assert k[0]["durum"] in ("tamam", "uyari", "hata")
    return k[0]


def kimlikler(kontroller: list[dict]) -> set[str]:
    return {k["kimlik"] for k in kontroller}
