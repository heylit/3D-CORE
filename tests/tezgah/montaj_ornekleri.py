"""SPEC 25 montaj testleri için elle kurulmuş, uydurma montajlar (gizlilik kuralı: gerçek parça yok).

Saf kısım (`Assembly` + kısıtlar, OCCT'siz) K10 serbestlik testleri içindir; `MontajTanimi` kuranlar
build123d ister (parçalar `geometry.features` ile). Bütün kısıtlar başlangıç konumunda sağlanmıştır.
"""

from __future__ import annotations

import numpy as np

from assy.model import Assembly, Component, Mate, MateKind, Node, Ref, RefKind, transform

EZ = (0.0, 0.0, 1.0)


def eksen(bilesen: str, nokta, yon=EZ) -> Ref:
    return Ref(bilesen, RefKind.AXIS, tuple(nokta), tuple(yon))


def duzlem(bilesen: str, nokta, normal) -> Ref:
    return Ref(bilesen, RefKind.PLANE, tuple(nokta), tuple(normal))


def es_eksen(a: Ref, b: Ref) -> Mate:
    return Mate(MateKind.CONCENTRIC, a, b)


def cakisik(a: Ref, b: Ref) -> Mate:
    return Mate(MateKind.COINCIDENT, a, b)


# ---------------------------------------------------------------- K10: saf montajlar

Q = (5.0, 3.0, 0.0)  # serbest parçanın dönme ekseni (dünya), yön +Z; eksen başlangıçtan geçmez


def iki_bilesen(kisitlar: str) -> Assembly:
    """'taban' sabit, 'parca' serbest; ikisi de T = I (Δt'nin referans noktası dünya başlangıcıyla aynı).

    kisitlar: "yok" | "es_eksen" | "es_eksen+duzlem" | "uc_duzlem"
    """
    mates = []
    if kisitlar.startswith("es_eksen"):
        mates.append(es_eksen(eksen("taban", Q), eksen("parca", Q)))
    if kisitlar == "es_eksen+duzlem":
        mates.append(cakisik(duzlem("taban", (0, 0, 0), EZ), duzlem("parca", (0, 0, 0), (0, 0, -1))))
    if kisitlar == "uc_duzlem":
        for e in np.eye(3):
            mates.append(cakisik(duzlem("taban", (0, 0, 0), e), duzlem("parca", (0, 0, 0), -e)))
    return Assembly(
        name=kisitlar,
        components=[
            Component("taban", "taban", np.eye(4), fixed=True),
            Component("parca", "parca", np.eye(4)),
        ],
        mates=mates,
    )


# ---------------------------------------------------------------- OCCT'li küçük montajlar


def _parcalar(ust: str):
    from geometry.features import block, cylinder

    taban = block(40.0, 40.0, 10.0, name="taban")  # x, y ∈ [0, 40], z ∈ [0, 10]
    if ust == "blok":
        p = block(20.0, 10.0, 5.0, name="blok")  # dönel simetrik değil
    else:
        p = cylinder(5.0, 8.0, name="tapa")  # eksen yerel Z, taban merkezi başlangıçta
    return taban, p


def deney(ust: str = "blok", yer: str = "ust", kisit: str = "es_eksen+duzlem", sira=None):
    """Kök 'deney': 'taban' yaprağı (sabit) + 'grup' alt montajı içinde 'ust' yaprağı.

    ust: "blok" (20 × 10 × 5) | "tapa" (Ø10 × 8 silindir).
    yer: "ust"  — taban üst yüzüne (z = 10) oturur, eksen dünyada (10, 20)
         "alt"  — taban alt yüzüne (z = 0) asılı, üst parça aşağıda (işaret kuralı: −a)
         "yan"  — taban x = 40 yüzüne yaslanır (yalnız düzlem kısıtı, normal +x)
    kisit: "es_eksen+duzlem" | "duzlem" | "yok"
    """
    from tezgah.montaj import MontajTanimi

    taban, p = _parcalar(ust)
    yol = "grup/ust"
    # Üst parçanın yerel eksen noktası: blokta (10, 5) (ortası değil, yerel köşeye göre), tapada (0, 0).
    yerel = (10.0, 5.0) if ust == "blok" else (0.0, 0.0)
    h = 5.0 if ust == "blok" else 8.0
    if yer == "ust":
        T = transform(t=(10.0 - yerel[0], 20.0 - yerel[1], 10.0))
        mates = [
            es_eksen(eksen("taban", (10.0, 20.0, 10.0)), eksen(yol, (*yerel, 0.0))),
            cakisik(duzlem("taban", (0, 0, 10.0), EZ), duzlem(yol, (0, 0, 0), (0, 0, -1))),
        ]
    elif yer == "alt":
        T = transform(t=(10.0 - yerel[0], 20.0 - yerel[1], -h))
        mates = [
            es_eksen(eksen("taban", (10.0, 20.0, 0.0)), eksen(yol, (*yerel, h))),
            cakisik(duzlem("taban", (0, 0, 0), (0, 0, -1)), duzlem(yol, (0, 0, h), EZ)),
        ]
    else:  # yan
        T = transform(t=(40.0, 0.0, 0.0))
        mates = [cakisik(duzlem("taban", (40.0, 0, 0), (1, 0, 0)), duzlem(yol, (0, 0, 0), (-1, 0, 0)))]
    if kisit == "duzlem":
        mates = [m for m in mates if m.kind is MateKind.COINCIDENT]
    elif kisit == "yok":
        mates = []
    agac = Node(
        "deney",
        children=[
            Node("taban", part="taban"),
            Node("grup", children=[Node("ust", T=T, part=ust)]),
        ],
    )
    return MontajTanimi(
        ad="deney",
        agac=agac,
        parcalar={"taban": taban, ust: p},
        malzemeler={"taban": ("C45", 7.85e-9), ust: ("AlMg3", 2.66e-9)},
        kisitlar=mates,
        sabit=("taban",),
        sira=list(sira) if sira is not None else ["taban", yol],
    )
