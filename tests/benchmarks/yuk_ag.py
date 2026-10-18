"""
SPEC 67b testlerinin ortak yardımcıları (test dosyası değil).

Testler specs/67-fem-genisletme.md (67b) metninden ve arayüzünden yazıldı; core/yukler.py,
mesh/yuz_esleme.py ve analiz/dayanim.py gövdeleri okunmadı. Kullanılan arayüzler: core.model,
tests/benchmarks/tet_ag.py (SPEC 11'in Kuhn ağı).

- `tet10_agi`: tet4 Kuhn ağına düz kenar ortası düğümleri ekler (C3D10 sırası: köşeler 1–4, kenarlar 5 (1–2),
  6 (2–3), 7 (3–1), 8 (1–4), 9 (2–4), 10 (3–4)). Düz elemanda N_a barisentrik koordinatların polinomudur.
- `L_integrali`: ∫_tet L₁^a L₂^b L₃^c L₄^d dV = 6 V a! b! c! d! / (a + b + c + d + 3)!
  (kapalı form; tutarlı yük beklenen değerleri bununla elle hesaplanır, kodun kuralından bağımsız).
- `SahteMalzeme`: B2 `Malzeme`'nin SPEC 67b'nin kullandığı kısmı (ördek tipi): `id`, `grup`, `iste(alan)`,
  `fem_malzemesi()`. Eksik alan istenince ModelError (B2 Teori).
- `SahteSicaklik`: SPEC 56 `ThermalResult`'ın kullanılan kısmı (ördek tipi): `node_ids`, `T`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from core.model import BC, Element, Load, Material, Model, ModelError, Node
from tests.benchmarks.tet_ag import kutu_agi

__all__ = ["kutu_agi"]

DOF = ("ux", "uy", "uz")
KENARLAR = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))  # C3D10 düğüm 5..10


def tet10_agi(m4: Model, name: str = "tet10_kutu") -> Model:
    """tet4 ağından düz tet10 ağı: her kenara ortak bir orta düğüm (id'ler köşelerden sonra).

    Sol el tet4 elemanlarında köşe 2 ↔ 3 değiştirilir; bütün tet10 elemanları sağ el (det J > 0) olur.
    """
    nodes = [Node(n.id, n.x, n.y, n.z) for n in m4.nodes]
    sonraki = max(n.id for n in nodes) + 1
    orta: dict[frozenset[int], int] = {}
    elements = []
    for e in m4.elements:
        kn = list(e.nodes)
        X = np.array([m4.node(n).xyz for n in kn])
        if np.linalg.det(X[1:] - X[0]) < 0:  # sol el → sağ el (tet10 det J > 0 ister, SPEC 67a K10)
            kn[1], kn[2] = kn[2], kn[1]
        ek = []
        for i, j in KENARLAR:
            a, b = kn[i], kn[j]
            anahtar = frozenset((a, b))
            if anahtar not in orta:
                p = (m4.node(a).xyz + m4.node(b).xyz) / 2
                nodes.append(Node(sonraki, *p))
                orta[anahtar] = sonraki
                sonraki += 1
            ek.append(orta[anahtar])
        elements.append(Element(e.id, "tet10", kn + ek, e.material))
    return Model(dim=3, nodes=nodes, elements=elements, materials=list(m4.materials), name=name)


def tek_tet(order: int, X=None, malzeme: Material | None = None) -> Model:
    """Tek elemanlı model; X (4, 3) köşeler (sağ el), varsayılan genel (eğik) bir tetrahedron."""
    if X is None:
        X = np.array([[1.0, 2.0, 0.5], [11.0, 3.0, 1.0], [3.0, 14.0, 2.0], [4.0, 5.0, 9.0]])
    X = np.asarray(X, dtype=float)
    assert np.linalg.det(X[1:] - X[0]) > 0
    mat = malzeme or Material("celik", 210_000.0, 0.3, 7.85e-9)
    m4 = Model(
        dim=3,
        nodes=[Node(i + 1, *X[i]) for i in range(4)],
        elements=[Element(1, "tet4", [1, 2, 3, 4], mat.name)],
        materials=[mat],
    )
    return m4 if order == 1 else tet10_agi(m4)


def L_integrali(V: float, us: tuple[int, int, int, int]) -> float:
    """∫ Π L_k^us[k] dV (kapalı form)."""
    pay = math.prod(math.factorial(a) for a in us)
    return 6.0 * V * pay / math.factorial(sum(us) + 3)


def tet_hacmi(X: np.ndarray) -> float:
    return float(np.linalg.det(X[1:4] - X[0])) / 6.0


def grad_L(X: np.ndarray) -> np.ndarray:
    """Barisentrik koordinatların gradyanları (4, 3): L = A⁻¹ [1, x, y, z]."""
    A = np.vstack([np.ones(4), X[:4].T])  # (4, 4)
    return np.linalg.inv(A)[:, 1:]


def yuk_sozlugu(loads) -> dict[tuple[int, str], float]:
    """(düğüm, dof) → toplam kuvvet."""
    d: dict[tuple[int, str], float] = {}
    for ld in loads:
        d[(ld.node, ld.dof)] = d.get((ld.node, ld.dof), 0.0) + ld.value
    return d


def dugum_kuvveti(loads, nid: int) -> np.ndarray:
    d = yuk_sozlugu(loads)
    return np.array([d.get((nid, dof), 0.0) for dof in DOF])


def toplam_kuvvet(loads) -> np.ndarray:
    F = np.zeros(3)
    for ld in loads:
        F[DOF.index(ld.dof)] += ld.value
    return F


def mesnet_321(model: Model, x0: int, x1: int, x2: int) -> None:
    """3-2-1 mesnet: x0 üç yön; x1 (x0'dan x yönünde) uy, uz; x2 (x0'dan y yönünde) uz."""
    model.bcs += [BC(x0, "ux"), BC(x0, "uy"), BC(x0, "uz"), BC(x1, "uy"), BC(x1, "uz"), BC(x2, "uz")]


def dugum_bul(model: Model, p) -> int:
    p = np.asarray(p, dtype=float)
    for n in model.nodes:
        if np.allclose(n.xyz, p, atol=1e-9):
            return n.id
    raise AssertionError(f"{p} noktasında düğüm yok")


def u_dugum(model: Model, u: np.ndarray, nid: int) -> np.ndarray:
    i = model.dof_index(nid, "ux")
    return np.asarray(u[i : i + 3])


@dataclass(frozen=True)
class SahteMalzeme:
    """B2 Malzeme'nin ördek tipi (id, grup, iste, fem_malzemesi)."""

    id: str = "S355-sahte"
    grup: str = "celik"
    E: float | None = 210_000.0
    nu: float | None = 0.3
    rho: float | None = 7.85e-9
    Rp02: float | None = 355.0
    alpha: float | None = 1.2e-5

    def iste(self, alan: str) -> float:
        v = getattr(self, alan, None)
        if v is None:
            raise ModelError(f"'{self.id}' malzemesinde '{alan}' yok")
        return float(v)

    def fem_malzemesi(self) -> Material:
        return Material(self.id, self.iste("E"), self.iste("nu"), self.rho if self.rho is not None else 0.0)


@dataclass(frozen=True)
class SahteSicaklik:
    """SPEC 56 ThermalResult'ın ördek tipi: node_ids (n,), T (n,) model.nodes sırasında."""

    node_ids: np.ndarray
    T: np.ndarray

    @classmethod
    def alandan(cls, model: Model, T: dict[int, float]) -> SahteSicaklik:
        ids = np.array([n.id for n in model.nodes])
        return cls(ids, np.array([T[i] for i in ids], dtype=float))


def load_listesi(d: dict[tuple[int, str], float]) -> list[Load]:
    return [Load(n, dof, v) for (n, dof), v in d.items()]


def _duffy(n: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """Birim tetrahedronda çökertilmiş Gauss kuralı: barisentrik noktalar (k, 4), ağırlıklar (toplam 1/6)."""
    x, w = np.polynomial.legendre.leggauss(n)
    x, w = (x + 1) / 2, w / 2
    P, W = [], []
    for a, wa in zip(x, w, strict=True):
        for b, wb in zip(x, w, strict=True):
            for c, wc in zip(x, w, strict=True):
                u, v, t = a, b * (1 - a), c * (1 - a) * (1 - b)
                P.append((1 - u - v - t, u, v, t))
                W.append(wa * wb * wc * (1 - a) ** 2 * (1 - b))
    return np.array(P), np.array(W)


def tet10_hacim_merkez(X: np.ndarray) -> tuple[float, np.ndarray]:
    """Eğri (izoparametrik) tet10'un hacmi ve ağırlık merkezi; X (10, 3) C3D10 sırasında.

    x(L) = Σ N_a(L) X_a; |det J| ile çökertilmiş Gauss kuralı (5³ nokta; 2. derece ağda tam).
    """
    P, W = _duffy()
    V, S = 0.0, np.zeros(3)
    for L, w in zip(P, W, strict=True):
        dN = np.zeros((10, 4))  # ∂N/∂L
        N = np.zeros(10)
        for i in range(4):
            N[i] = L[i] * (2 * L[i] - 1)
            dN[i, i] = 4 * L[i] - 1
        for k, (i, j) in enumerate(KENARLAR):
            N[4 + k] = 4 * L[i] * L[j]
            dN[4 + k, i], dN[4 + k, j] = 4 * L[j], 4 * L[i]
        dxdL = X.T @ dN  # (3, 4); bağımsız ξ = (L2, L3, L4), L1 = 1 − ξ toplamı
        J = dxdL[:, 1:] - dxdL[:, [0]]
        d = abs(float(np.linalg.det(J))) * w
        V += d
        S += d * (N @ X)
    return V, S / V
