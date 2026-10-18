"""
SPEC 11 testlerinin kendi yapılandırılmış tetrahedron ağ üreticisi (gmsh yok; gmsh SPEC 12).

Kutu [0, L] x [0, b] x [0, h], nx x ny x nz altı yüzlüye bölünür; her altı yüzlü Kuhn
(Freudenthal) bölümüyle 6 tetrahedrona ayrılır. Kuhn bölümünde her tetrahedron, kutunun
(0,0,0) köşesinden (1,1,1) köşesine eksenler boyunca birer adım giden bir yoldur; 3! = 6 eksen
sırası 6 tetrahedron verir. Tüm kutular aynı yönde bölündüğü için ağ uyumludur (komşu yüzlerin
köşegenleri çakışır) ve k -> 2k inceltmesi iç içedir (kaba ağın her tetrahedronu ince ağdaki
tetrahedronların birleşimidir).

Düğüm sırası permütasyonun işaretine göre sağ el veya sol el olabilir; SPEC 11 iki sırayı da
kabul eder, bu yüzden ağ bilerek iki türü de içerir.

Kullanılan tek arayüz core.model'dir (Model, Node, Element, Material, Load).
"""

from __future__ import annotations

import itertools

import numpy as np

from core.model import Element, Load, Material, Model, Node

# Kuhn bölümü: eksen sıraları (0 = x, 1 = y, 2 = z)
KUHN_SIRALARI = list(itertools.permutations(range(3)))


def dugum_id(i: int, j: int, k: int, nx: int, ny: int) -> int:
    """(i, j, k) ızgara noktasının düğüm id'si (1'den başlar)."""
    return 1 + i + (nx + 1) * (j + (ny + 1) * k)


def kutu_agi(
    L: float,
    b: float,
    h: float,
    nx: int,
    ny: int,
    nz: int,
    malzeme: Material,
    kaydirma: float = 0.0,
    tohum: int = 0,
    name: str = "tet_kutu",
) -> Model:
    """
    Kutu tet4 ağı (dim = 3), mesnet ve yük olmadan.

    kaydirma > 0 ise SADECE iç düğümler (hiçbir sınır yüzünde olmayan) her eksende
    [-kaydirma, +kaydirma] · (o eksendeki kutu boyu) aralığında düzensiz (tohumlu rastgele)
    kaydırılır; sınır düğümleri ve dolayısıyla sınır yüzleri düz kalır.
    """
    hx, hy, hz = L / nx, b / ny, h / nz
    rng = np.random.default_rng(tohum)

    nodes: list[Node] = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                x, y, z = L * i / nx, b * j / ny, h * k / nz
                ic = 0 < i < nx and 0 < j < ny and 0 < k < nz
                if ic and kaydirma > 0.0:
                    dx, dy, dz = rng.uniform(-kaydirma, kaydirma, size=3)
                    x, y, z = x + dx * hx, y + dy * hy, z + dz * hz
                nodes.append(Node(dugum_id(i, j, k, nx, ny), x, y, z))

    elements: list[Element] = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                for sira in KUHN_SIRALARI:
                    p = [i, j, k]
                    yol = [dugum_id(*p, nx, ny)]
                    for eksen in sira:
                        p[eksen] += 1
                        yol.append(dugum_id(*p, nx, ny))
                    elements.append(Element(len(elements) + 1, "tet4", yol, malzeme.name))

    m = Model(dim=3, nodes=nodes, elements=elements, materials=[malzeme], name=name)
    _hacim_kontrol(m, hx * hy * hz / 6.0)
    return m


def _hacim_kontrol(model: Model, V0: float) -> None:
    """Kaydırma bir tetrahedronu ezmemeli veya ters çevirmemeli (testin kendi güvencesi)."""
    for e in model.elements:
        X = np.array([model.node(n).xyz for n in e.nodes])
        V = np.linalg.det(X[1:] - X[0]) / 6.0
        if abs(V) < 0.1 * V0:
            raise ValueError(f"tet_ag: eleman {e.id} çok basık (V = {V}); kaydırmayı küçült")


def _duzlemde(model: Model, eksen: int, deger: float) -> set[int]:
    olcek = max(1.0, abs(deger))
    return {n.id for n in model.nodes if abs(n.xyz[eksen] - deger) <= 1e-9 * olcek}


def yuz_dugumleri(model: Model, eksen: int, deger: float) -> list[int]:
    """x_eksen = deger düzlemindeki düğümlerin id'leri (sıralı)."""
    return sorted(_duzlemde(model, eksen, deger))


def sinir_ucgenleri(model: Model, eksen: int, deger: float) -> list[tuple[int, int, int]]:
    """x_eksen = deger düzlemindeki sınır üçgenleri: üç düğümü de o düzlemde olan tetrahedron yüzleri."""
    duzlem = _duzlemde(model, eksen, deger)
    ucgenler = []
    for e in model.elements:
        for yuz in itertools.combinations(e.nodes, 3):
            if all(n in duzlem for n in yuz):
                ucgenler.append(yuz)
    return ucgenler


def yuzey_cekmesi(model: Model, eksen: int, deger: float, t: tuple[float, float, float]) -> list[Load]:
    """
    Düzgün yüzey çekmesi t = (tx, ty, tz) [MPa]'yı düğüm kuvvetlerine çevirir: doğrusal üçgen
    yüzün her köşesine t · A / 3 (SPEC 11, Teori / Global sistem). Aynı düğüm/DOF tek Load'da toplanır.
    """
    F: dict[int, np.ndarray] = {}
    for ucgen in sinir_ucgenleri(model, eksen, deger):
        X = np.array([model.node(n).xyz for n in ucgen])
        A = 0.5 * np.linalg.norm(np.cross(X[1] - X[0], X[2] - X[0]))
        for n in ucgen:
            F.setdefault(n, np.zeros(3))
            F[n] += np.asarray(t, dtype=float) * A / 3.0
    yukler = []
    for n in sorted(F):
        for d, ad in enumerate(("ux", "uy", "uz")):
            if F[n][d] != 0.0:
                yukler.append(Load(n, ad, float(F[n][d])))
    return yukler
