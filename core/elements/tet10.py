"""
3B on düğümlü ikinci dereceden tetrahedron elemanı (tet10, düğüm başına 3 DOF: ux, uy, uz).

Düğüm sırası CalculiX/Abaqus C3D10: köşeler 1–4,
kenarlar 5 (1–2), 6 (2–3), 7 (3–1), 8 (1–4), 9 (2–4), 10 (3–4).
İzoparametrik: geometri ve yer değiştirme aynı N ile. Hacim koordinatları L1 = 1 − ξ − η − ζ, L2 = ξ,
L3 = η, L4 = ζ (referans hacmi 1/6). Voigt düzeni tet4 ile aynı: [xx, yy, zz, xy, xz, yz], γ = 2ε.

Teori: specs/67-fem-genisletme.md (67a).
"""

from __future__ import annotations

import numpy as np

from core.elements.tet4 import DOF_SIRASI, D
from core.model import Element, Model, ModelError

__all__ = ["D", "volume", "ke", "dofs", "me", "stress_gauss", "stress", "stress_nodes"]

# Kenar düğümü (0 tabanlı indeks 4..9) -> iki köşesi
KENARLAR = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))

# 4 noktalı Gauss kuralı (2. derece): bir L = a, diğerleri b; ağırlık 1/24 (Σw = 1/6)
GAUSS_A = 0.5854101966249685
GAUSS_B = 0.1381966011250105
GAUSS_L = np.full((4, 4), GAUSS_B) + np.eye(4) * (GAUSS_A - GAUSS_B)  # satır g: (L1..L4), L_g = a
GAUSS_W = np.full(4, 1.0 / 24.0)


def _keast15() -> tuple[np.ndarray, np.ndarray]:
    """15 noktalı Keast kuralı (5. derece), hacim koordinatlarında (15, 4) ve ağırlıklar (Σw = 1/6)."""
    L, w = [], []

    def ekle(nokta, agirlik):
        import itertools

        for p in sorted(set(itertools.permutations(nokta))):
            L.append(p)
            w.append(agirlik / 6.0)

    ekle((0.25, 0.25, 0.25, 0.25), 0.1817020685825351)
    ekle((0.0, 1 / 3, 1 / 3, 1 / 3), 0.0361607142857143)
    ekle((8 / 11, 1 / 11, 1 / 11, 1 / 11), 0.0698714945161738)
    c, d = 0.0665501535736643, 0.4334498464263357
    ekle((c, c, d, d), 0.0656948493683187)
    return np.array(L), np.array(w)


KEAST_L, KEAST_W = _keast15()


def N(L: np.ndarray) -> np.ndarray:
    """Şekil fonksiyonları (10,) hacim koordinatlarında L (4,)."""
    k = L * (2.0 * L - 1.0)
    e = [4.0 * L[i] * L[j] for i, j in KENARLAR]
    return np.concatenate([k, e])


def _dN_dL(L: np.ndarray) -> np.ndarray:
    """∂N_a / ∂L_i (10 x 4)."""
    G = np.zeros((10, 4))
    G[range(4), range(4)] = 4.0 * L - 1.0
    for a, (i, j) in enumerate(KENARLAR, start=4):
        G[a, i] = 4.0 * L[j]
        G[a, j] = 4.0 * L[i]
    return G


# L1 = 1 − ξ − η − ζ, L2..L4 = ξ, η, ζ  →  ∂L / ∂ξ (4 x 3)
_DL_DXI = np.array([[-1.0, -1.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])


def _koordinatlar(element: Element, model: Model) -> np.ndarray:
    """Düğüm koordinatları X (10 x 3), element.nodes sırasında. Biçim hatası → ModelError."""
    if model.dim != 3:
        raise ModelError(f"Eleman {element.id}: tet10 sadece 3B modelde kullanılır (dim={model.dim})")
    if len(element.nodes) != 10:
        raise ModelError(f"Eleman {element.id}: tet10 10 düğüm ister ({len(element.nodes)} verildi)")
    if len(set(element.nodes)) != 10:
        raise ModelError(f"Eleman {element.id}: tekrarlanan düğüm {element.nodes}")
    return np.array([model.node(nid).xyz for nid in element.nodes])


def _nokta(element: Element, X: np.ndarray, L: np.ndarray) -> tuple[np.ndarray, float]:
    """Bir integrasyon noktasında (∂N/∂x (10 x 3), det J). det J ≤ 0 → ModelError.

    J = ∂x/∂ξ = Xᵀ ∂N/∂ξ,  ∂N/∂x = ∂N/∂ξ J⁻¹
    """
    dN_dxi = _dN_dL(L) @ _DL_DXI  # (10, 3)
    J = X.T @ dN_dxi  # (3, 3), J[i, j] = ∂x_i / ∂ξ_j
    detJ = float(np.linalg.det(J))
    olcek = float(np.abs(X - X.mean(axis=0)).max()) ** 3
    if not detJ > 1e-12 * olcek:
        raise ModelError(f"Eleman {element.id}: det J ≤ 0 (ters çevrilmiş veya bozuk tet10, det J = {detJ})")
    return np.linalg.solve(J.T, dN_dxi.T).T, detJ


def _B(dN_dx: np.ndarray) -> np.ndarray:
    """B (6 x 30) düğüm gradyanlarından (10 x 3)."""
    Bm = np.zeros((6, 30))
    for a, (b, g, d) in enumerate(dN_dx):
        c = 3 * a
        Bm[0, c] = b
        Bm[1, c + 1] = g
        Bm[2, c + 2] = d
        Bm[3, c], Bm[3, c + 1] = g, b
        Bm[4, c], Bm[4, c + 2] = d, b
        Bm[5, c + 1], Bm[5, c + 2] = d, g
    return Bm


def _gauss(element: Element, model: Model) -> list[tuple[np.ndarray, float]]:
    """4 Gauss noktasında (B, w · det J)."""
    X = _koordinatlar(element, model)
    sonuc = []
    for L, w in zip(GAUSS_L, GAUSS_W, strict=True):
        dN_dx, detJ = _nokta(element, X, L)
        sonuc.append((_B(dN_dx), w * detJ))
    return sonuc


def volume(element: Element, model: Model) -> float:
    """V = Σ_g w_g det J [mm³]. det J ≤ 0 olan Gauss noktası → ModelError."""
    return float(sum(wdet for _, wdet in _gauss(element, model)))


def ke(element: Element, model: Model) -> np.ndarray:
    """ke = Σ_g w_g Bᵀ D B det J  (30 x 30), 4 noktalı Gauss kuralı."""
    Dm = D(model.material(element.material))
    k = sum(wdet * Bm.T @ Dm @ Bm for Bm, wdet in _gauss(element, model))
    return 0.5 * (k + k.T)  # yuvarlama asimetrisini temizle


def dofs(element: Element, model: Model) -> list[int]:
    """[ux1, uy1, uz1, ..., uz10], element.nodes sırasında."""
    _koordinatlar(element, model)
    return [model.dof_index(nid, d) for nid in element.nodes for d in DOF_SIRASI]


def me(element: Element, model: Model, lumped: bool = False) -> np.ndarray:
    """Tutarlı kütle matrisi (30 x 30) [t]: ρ Σ_q w_q N Nᵀ det J ⊗ I₃, 15 noktalı Keast kuralı.

    lumped=True → ModelError (satır toplamı köşelerde negatif kütle verir). ρ ≤ 0 → ModelError.
    """
    if lumped:
        raise ModelError(f"Eleman {element.id}: tet10 için toplanmış kütle yok (köşe ağırlıkları negatif)")
    rho = model.material(element.material).rho
    if rho <= 0.0:
        raise ModelError(f"Eleman {element.id}: kütle matrisi için ρ > 0 olmalı (ρ={rho})")
    X = _koordinatlar(element, model)
    m = np.zeros((10, 10))
    for L, w in zip(KEAST_L, KEAST_W, strict=True):
        _, detJ = _nokta(element, X, L)
        n = N(L)
        m += w * detJ * np.outer(n, n)
    return np.kron(rho * m, np.eye(3))


def stress_gauss(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """4 Gauss noktasında σ = D B d  (4, 6) [MPa], Voigt: xx, yy, zz, xy, xz, yz."""
    d = np.asarray(u, dtype=float)[dofs(element, model)]
    Dm = D(model.material(element.material))
    return np.array([Dm @ Bm @ d for Bm, _ in _gauss(element, model)])


def stress(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """Eleman gerilmesi σ (6,) [MPa]: Gauss noktalarının ortalaması."""
    return stress_gauss(element, model, u).mean(axis=0)


def stress_nodes(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """Düğüm gerilmeleri (10, 6) [MPa]: köşelere doğrusal dış değerleme, kenarlara iki köşenin ortalaması.

    Doğrusal alan σ(L) = Σ c_i L_i, Gauss noktası g'de L_g = a, diğerleri b:
    σ_g = (a − b) c_g + b S,  S = Σ c_i = Σ σ_g (a + 3b = 1)  →  c_g = (σ_g − b S) / (a − b).
    Köşe i'deki değer c_i'dir (L_i = 1).
    """
    sg = stress_gauss(element, model, u)
    S = sg.sum(axis=0)
    kose = (sg - GAUSS_B * S) / (GAUSS_A - GAUSS_B)
    kenar = np.array([0.5 * (kose[i] + kose[j]) for i, j in KENARLAR])
    return np.vstack([kose, kenar])
