"""
SPEC 67a testlerinin kendi tet10 araçları: Kuhn kutu ağından ikinci dereceden (10 düğümlü) ağ,
düz kenarlı elemanlarda şekil fonksiyonları, Gauss noktaları, Jacobian ve tri6 tutarlı yük.

Hepsi specs/67-fem-genisletme.md (67a, Teori) formüllerinden yazıldı; core/elements/tet10.py
okunmadı. Düğüm sırası CalculiX C3D10:
    köşe 1, 2, 3, 4;  kenar 5 (1–2), 6 (2–3), 7 (3–1), 8 (1–4), 9 (2–4), 10 (3–4)

Kullanılan arayüz: core.model (Model, Node, Element, Material, Load) ve tests/benchmarks/tet_ag.py.
"""

from __future__ import annotations

import itertools
import math

import numpy as np

from core.model import Element, Load, Material, Model, Node
from tests.benchmarks.tet_ag import kutu_agi

# Kenar düğümü -> iki köşe (0 tabanlı köşe indeksleri)
KENARLAR = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]

# 4 noktalı Gauss kuralı (SPEC 67a): hacim koordinatları (a, b, b, b) permütasyonları, w = 1/24
GAUSS_A, GAUSS_B = 0.5854101966249685, 0.1381966011250105
GAUSS_L = np.array([[GAUSS_B] * i + [GAUSS_A] + [GAUSS_B] * (3 - i) for i in range(4)])
GAUSS_W = 1.0 / 24.0


# --- şekil fonksiyonları (hacim koordinatlarında) -----------------------------------------


def N(L: np.ndarray) -> np.ndarray:
    """N_1..N_10 (10,), L = (L1, L2, L3, L4), ΣL = 1."""
    L = np.asarray(L, dtype=float)
    kose = L * (2.0 * L - 1.0)
    kenar = [4.0 * L[i] * L[j] for i, j in KENARLAR]
    return np.concatenate([kose, kenar])


def dN_dL(L: np.ndarray) -> np.ndarray:
    """∂N_a/∂L_k (10, 4), L'ler bağımsız sayılarak."""
    L = np.asarray(L, dtype=float)
    G = np.zeros((10, 4))
    for i in range(4):
        G[i, i] = 4.0 * L[i] - 1.0
    for a, (i, j) in enumerate(KENARLAR):
        G[4 + a, i] = 4.0 * L[j]
        G[4 + a, j] = 4.0 * L[i]
    return G


def dN_dxi(L: np.ndarray) -> np.ndarray:
    """Yerel koordinatlar ξ = (L2, L3, L4), L1 = 1 − ξ − η − ζ: ∂N/∂ξ_k = ∂N/∂L_(k+1) − ∂N/∂L_1 (10, 3)."""
    G = dN_dL(L)
    return G[:, 1:] - G[:, [0]]


def jacobian(X: np.ndarray, L: np.ndarray) -> np.ndarray:
    """J_ik = ∂x_i/∂ξ_k = Σ_a x_a,i ∂N_a/∂ξ_k (3, 3); X düğüm koordinatları (10, 3)."""
    return X.T @ dN_dxi(L)


def dN_dx(X: np.ndarray, L: np.ndarray) -> tuple[np.ndarray, float]:
    """(∂N_a/∂x_i (10, 3), det J)."""
    J = jacobian(X, L)
    return dN_dxi(L) @ np.linalg.inv(J), float(np.linalg.det(J))


def gauss_konumlari(X: np.ndarray) -> np.ndarray:
    """4 Gauss noktasının fiziksel konumu (4, 3) (izoparametrik eşleme)."""
    return np.array([N(L) @ X for L in GAUSS_L])


def B_matrisi(G: np.ndarray) -> np.ndarray:
    """∂N/∂x (10, 3) -> B (6, 30), Voigt xx, yy, zz, xy, xz, yz (mühendislik kayması)."""
    B = np.zeros((6, 30))
    for a in range(10):
        bx, by, bz = G[a]
        B[:, 3 * a : 3 * a + 3] = [[bx, 0, 0], [0, by, 0], [0, 0, bz], [by, bx, 0], [bz, 0, bx], [0, bz, by]]
    return B


def D_matrisi(E: float, nu: float) -> np.ndarray:
    lam, G = E * nu / ((1 + nu) * (1 - 2 * nu)), E / (2 * (1 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[:3, :3] += 2 * G * np.eye(3)
    D[3:, 3:] = G * np.eye(3)
    return D


def ke_referans(X: np.ndarray, E: float, nu: float) -> np.ndarray:
    """Testin kendi ke'si: Σ_g w_g Bᵀ D B det J (4 noktalı Gauss)."""
    D = D_matrisi(E, nu)
    k = np.zeros((30, 30))
    for L in GAUSS_L:
        G, detJ = dN_dx(X, L)
        B = B_matrisi(G)
        k += GAUSS_W * detJ * B.T @ D @ B
    return k


# --- kesin polinom integrali (düz kenarlı eleman) ------------------------------------------


def _N_polinom() -> list[dict[tuple[int, int, int, int], float]]:
    """N_a, L1..L4 tek terimlilerinin toplamı: {(p, q, r, s): katsayı}."""

    def us(*k: int) -> tuple[int, int, int, int]:
        e = [0, 0, 0, 0]
        for i in k:
            e[i] += 1
        return tuple(e)  # type: ignore[return-value]

    pol = [{us(i, i): 2.0, us(i): -1.0} for i in range(4)]
    pol += [{us(i, j): 4.0} for i, j in KENARLAR]
    return pol


def tek_terim_integrali(us: tuple[int, ...], V: float) -> float:
    """∫ L1^p L2^q L3^r L4^s dV = 6V p! q! r! s! / (p + q + r + s + 3)!."""
    return 6.0 * V * math.prod(math.factorial(k) for k in us) / math.factorial(sum(us) + 3)


def M_kesin(V: float, rho: float) -> np.ndarray:
    """Tutarlı kütle ρ ∫ N_a N_b dV ⊗ I₃ (30, 30), kesin (düz kenarlı eleman)."""
    pol = _N_polinom()
    m = np.zeros((10, 10))
    for a, b in itertools.product(range(10), repeat=2):
        for (ua, ca), (ub, cb) in itertools.product(pol[a].items(), pol[b].items()):
            m[a, b] += ca * cb * tek_terim_integrali(tuple(x + y for x, y in zip(ua, ub, strict=True)), V)
    return rho * np.kron(m, np.eye(3))


def N_integrali(V: float) -> np.ndarray:
    """∫ N_a dV (10,): köşe −V/20, kenar V/5 (kesin)."""
    return np.array([sum(c * tek_terim_integrali(u, V) for u, c in p.items()) for p in _N_polinom()])


# --- ağ ---------------------------------------------------------------------------------------


def koordinatlar(model: Model, e: Element) -> np.ndarray:
    return np.array([model.node(n).xyz for n in e.nodes])


def ikinci_derece(model4: Model, name: str | None = None) -> Model:
    """
    tet4 modelinden tet10 modeli: her kenarın ortasına bir düğüm (düz kenar), id'ler köşelerden sonra.
    Sol el (det < 0) köşe sırasında 2 ↔ 3 değiştirilir, kenar düğümleri yeni köşe sırasına göre
    yeniden eşlenir; böylece her elemanda det J > 0. BC ve yükler taşınmaz.
    """
    nodes = [Node(n.id, n.x, n.y, n.z) for n in model4.nodes]
    sonraki = max(n.id for n in nodes) + 1
    orta: dict[frozenset[int], int] = {}
    elements = []
    for e in model4.elements:
        c = list(e.nodes)
        X = np.array([model4.node(n).xyz for n in c])
        if np.linalg.det(X[1:] - X[0]) < 0:
            c = [c[0], c[2], c[1], c[3]]
        kenar_id = []
        for i, j in KENARLAR:
            anahtar = frozenset((c[i], c[j]))
            if anahtar not in orta:
                xm = 0.5 * (model4.node(c[i]).xyz + model4.node(c[j]).xyz)
                nodes.append(Node(sonraki, *xm))
                orta[anahtar] = sonraki
                sonraki += 1
            kenar_id.append(orta[anahtar])
        elements.append(Element(e.id, "tet10", c + kenar_id, e.material))
    return Model(
        dim=3,
        nodes=nodes,
        elements=elements,
        materials=list(model4.materials),
        name=name or f"{model4.name}_tet10",
    )


def kutu_agi10(
    L: float,
    b: float,
    h: float,
    nx: int,
    ny: int,
    nz: int,
    malzeme: Material,
    kaydirma: float = 0.0,
    tohum: int = 0,
    name: str = "tet10_kutu",
) -> Model:
    """Kuhn kutu ağı (tet_ag.kutu_agi), ikinci dereceden: nx·ny·nz·6 tet10 eleman."""
    return ikinci_derece(kutu_agi(L, b, h, nx, ny, nz, malzeme, kaydirma=kaydirma, tohum=tohum), name=name)


def kose_dugumleri(model: Model) -> set[int]:
    return {n for e in model.elements for n in e.nodes[:4]}


def _duzlemde(model: Model, eksen: int, deger: float) -> set[int]:
    olcek = max(1.0, abs(deger))
    return {n.id for n in model.nodes if abs(n.xyz[eksen] - deger) <= 1e-9 * olcek}


# Tetrahedron yüzleri (köşe indeksleri) ve yüzün tri6 kenar düğümleri (1–2, 2–3, 3–1)
_YUZLER = [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)]


def _kenar_indeksi(i: int, j: int) -> int:
    for a, (p, q) in enumerate(KENARLAR):
        if {p, q} == {i, j}:
            return 4 + a
    raise ValueError((i, j))


def sinir_ucgenleri6(model: Model, eksen: int, deger: float) -> list[tuple[int, ...]]:
    """x_eksen = deger düzlemindeki tri6 yüzler (3 köşe, sonra 1–2, 2–3, 3–1 kenar düğümleri)."""
    duzlem = _duzlemde(model, eksen, deger)
    sonuc = []
    for e in model.elements:
        for i, j, k in _YUZLER:
            kose = (e.nodes[i], e.nodes[j], e.nodes[k])
            if all(n in duzlem for n in kose):
                kenar = tuple(e.nodes[_kenar_indeksi(p, q)] for p, q in ((i, j), (j, k), (k, i)))
                sonuc.append(kose + kenar)
    return sonuc


def yuzey_cekmesi10(model: Model, eksen: int, deger: float, t: tuple[float, float, float]) -> list[Load]:
    """
    Düz tri6 yüzde düzgün çekme t: f_a = ∫ N_a t dA → köşeler 0, kenar düğümleri t·A/3
    (∫ N_köşe dA = 0, ∫ N_kenar dA = A/3). Aynı düğüm/DOF tek Load'da toplanır.
    """
    F: dict[int, np.ndarray] = {}
    for tri in sinir_ucgenleri6(model, eksen, deger):
        X = np.array([model.node(n).xyz for n in tri[:3]])
        A = 0.5 * np.linalg.norm(np.cross(X[1] - X[0], X[2] - X[0]))
        for n in tri[3:]:
            F.setdefault(n, np.zeros(3))
            F[n] += np.asarray(t, dtype=float) * A / 3.0
    yukler = []
    for n in sorted(F):
        for d, ad in enumerate(("ux", "uy", "uz")):
            if F[n][d] != 0.0:
                yukler.append(Load(n, ad, float(F[n][d])))
    return yukler
