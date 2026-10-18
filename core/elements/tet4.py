"""
3B dört düğümlü doğrusal tetrahedron elemanı (tet4, düğüm başına 3 DOF: ux, uy, uz).

Şekil değiştirme eleman içinde sabittir (CST'nin 3B karşılığı). Voigt düzeni CalculiX / Abaqus ile
aynı: [xx, yy, zz, xy, xz, yz], kayma bileşenleri mühendislik kayması γ = 2ε.

Teori: specs/11-tet4.md (Logan, Bölüm 11; Zienkiewicz–Taylor–Zhu, Bölüm 6).
"""

from __future__ import annotations

import numpy as np

from core.model import Element, Material, Model, ModelError

# Yassılık sınırı: V <= YASSI * ℓ_max³ ise eleman bozuk sayılır
YASSI = 1e-12

DOF_SIRASI = ("ux", "uy", "uz")


def _koordinatlar(element: Element, model: Model) -> np.ndarray:
    """Düğüm koordinatları X (4 x 3), element.nodes sırasında. Biçim hatası → ModelError."""
    if model.dim != 3:
        raise ModelError(f"Eleman {element.id}: tet4 sadece 3B modelde kullanılır (dim={model.dim})")
    if len(element.nodes) != 4:
        raise ModelError(f"Eleman {element.id}: tet4 4 düğüm ister ({len(element.nodes)} verildi)")
    if len(set(element.nodes)) != 4:
        raise ModelError(f"Eleman {element.id}: tekrarlanan düğüm {element.nodes}")
    return np.array([model.node(nid).xyz for nid in element.nodes])


def _C(X: np.ndarray) -> np.ndarray:
    """C = [1 x y z] satırları (4 x 4); det C = 6V (işaretli)."""
    return np.hstack([np.ones((4, 1)), X])


def _hacim_ve_gradyan(element: Element, model: Model) -> tuple[float, np.ndarray]:
    """(V, G): V = |det C|/6, G (3 x 4) = [β; γ; δ], G[:, a] = ∇N_a.

    C⁻¹'in a. sütunu N_a'nın [α, β, γ, δ] katsayılarıdır; düğüm sırasından (det işaretinden)
    bağımsız olarak doğru gradyanı verir.
    """
    X = _koordinatlar(element, model)
    C = _C(X)
    V = abs(np.linalg.det(C)) / 6.0
    kenarlar = X[:, None, :] - X[None, :, :]
    l_max = np.sqrt((kenarlar**2).sum(axis=2)).max()
    if V <= YASSI * l_max**3:
        raise ModelError(f"Eleman {element.id}: bozuk (yassı) tetrahedron (V={V}, ℓ_max={l_max})")
    G = np.linalg.inv(C)[1:, :]
    return V, G


def volume(element: Element, model: Model) -> float:
    """V = |det C| / 6 [mm³]. Bozuk (yassı) eleman → ModelError."""
    return float(_hacim_ve_gradyan(element, model)[0])


def _B(G: np.ndarray) -> np.ndarray:
    """B = [B_1 B_2 B_3 B_4] (6 x 12), gradyan matrisi G (3 x 4)'ten."""
    Bm = np.zeros((6, 12))
    for a in range(4):
        b, g, d = G[:, a]  # β_a, γ_a, δ_a
        c = 3 * a
        Bm[0, c] = b  # ε_xx = ∂u/∂x
        Bm[1, c + 1] = g  # ε_yy = ∂v/∂y
        Bm[2, c + 2] = d  # ε_zz = ∂w/∂z
        Bm[3, c], Bm[3, c + 1] = g, b  # γ_xy = ∂u/∂y + ∂v/∂x
        Bm[4, c], Bm[4, c + 2] = d, b  # γ_xz = ∂u/∂z + ∂w/∂x
        Bm[5, c + 1], Bm[5, c + 2] = d, g  # γ_yz = ∂v/∂z + ∂w/∂y
    return Bm


def B(element: Element, model: Model) -> np.ndarray:
    """Şekil değiştirme – yer değiştirme matrisi (6 x 12), Voigt: xx, yy, zz, xy, xz, yz."""
    return _B(_hacim_ve_gradyan(element, model)[1])


def D(material: Material) -> np.ndarray:
    """İzotrop doğrusal elastik malzeme matrisi (6 x 6). ν ∉ (−1, 0.5) → ModelError.

    λ = Eν / ((1+ν)(1−2ν)),  G = E / (2(1+ν))
    """
    E, nu = material.E, material.nu
    if not -1.0 < nu < 0.5:
        raise ModelError(f"Malzeme '{material.name}': tet4 için −1 < ν < 0.5 olmalı (ν={nu})")
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    G = E / (2.0 * (1.0 + nu))
    Dm = np.zeros((6, 6))
    Dm[:3, :3] = lam
    Dm[[0, 1, 2], [0, 1, 2]] += 2.0 * G
    Dm[[3, 4, 5], [3, 4, 5]] = G
    return Dm


def ke(element: Element, model: Model) -> np.ndarray:
    """ke = V · Bᵀ D B  (12 x 12)."""
    V, G = _hacim_ve_gradyan(element, model)
    Bm = _B(G)
    k = V * Bm.T @ D(model.material(element.material)) @ Bm
    return 0.5 * (k + k.T)  # yuvarlama asimetrisini temizle


def dofs(element: Element, model: Model) -> list[int]:
    """[ux1, uy1, uz1, ..., uz4], element.nodes sırasında."""
    _koordinatlar(element, model)
    return [model.dof_index(nid, d) for nid in element.nodes for d in DOF_SIRASI]


def strain(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """ε = B d  (6,)."""
    d = np.asarray(u, dtype=float)[dofs(element, model)]
    return B(element, model) @ d


def stress(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """σ = D B d  (6,) [MPa]."""
    return D(model.material(element.material)) @ strain(element, model, u)


def me(element: Element, model: Model, lumped: bool = False) -> np.ndarray:
    """Kütle matrisi (12 x 12) [t], DOF sırası ke ile aynı (specs/45-modal.md).

    tutarlı:   ρV/20 · (1 + δ_ab) ⊗ I₃       toplanmış: ρV/4 · I₁₂
    Hatalar ke ile aynı, ek olarak ρ ≤ 0 → ModelError.
    """
    V = volume(element, model)
    rho = model.material(element.material).rho
    if rho <= 0.0:
        raise ModelError(f"Eleman {element.id}: kütle matrisi için ρ > 0 olmalı (ρ={rho})")
    m = rho * V
    if lumped:
        return m / 4.0 * np.eye(12)
    return np.kron(m / 20.0 * (np.ones((4, 4)) + np.eye(4)), np.eye(3))


def kg(element: Element, model: Model, sigma0: np.ndarray) -> np.ndarray:
    """Geometrik rijitlik (12 x 12): Kg_e = V Gᵀ Ŝ G, Ŝ = diag(S, S, S) (specs/68a-burkulma.md).

    sigma0: (6,) Voigt [xx, yy, zz, xy, xz, yz] [MPa], eleman içinde sabit. DOF sırası ke ile aynı.
    """
    raise NotImplementedError("specs/68a-burkulma.md uygulanacak")
