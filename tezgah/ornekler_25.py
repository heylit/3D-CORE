"""
SPEC 25 — Örnekler (uydurma geometri, gizlilik kuralı).

"kademeli_mil" (torna): C45, ham Ø50 × 101. Ön uçtan arkaya Ø24 × L, Ø35 × 30, Ø44 × 30, Ø50 kalan.
    İşlemler: alın, kaba boyuna, ince profil, kanal (SPEC 20). Parça eş eksenli silindirlerden (SPEC 02/09),
    profil parçadan (SPEC 28) çıkarılır. Parametre: L (uç boyu, varsayılan 20, aralık [5, 30]).
"yatak_grubu" (montaj): plaka 120 × 80 × 30 (üst yüz z = 0, Ø40,02 × 10 cep, dört Ø8,02 × 20 kör delik),
    rulman (iç Ø24,02, dış Ø40, genişlik 10), kademeli_mil, dört pim Ø8 × 24.
    Sıra: plaka, rulman, mil, pimler.
    L > 10 ise girişim hacmi V = π·12²·(L − 10) mm³; öneri L* = 10.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from geometry.part import Part
    from tezgah.montaj import MontajTanimi
    from tezgah.torna import TornaIsi

TORNA_ISLERI: tuple[str, ...] = ("kademeli_mil",)
MONTAJLAR: tuple[str, ...] = ("yatak_grubu",)
VARSAYILAN: dict[str, dict[str, float]] = {"kademeli_mil": {"L": 20.0}}
ARALIK: dict[tuple[str, str], tuple[float, float]] = {("kademeli_mil", "L"): (5.0, 30.0)}


def mil_parcasi(L: float) -> Part:
    """Kademeli mil katısı, kendi koordinatında (ön yüz z = 0, eksen Z). L ≤ 0 → GeometryError."""
    raise NotImplementedError("SPEC 25: tezgah.ornekler_25.mil_parcasi")


def kademeli_mil(parametreler: dict[str, float] | None = None) -> TornaIsi:
    """Torna işi; parametreler None → VARSAYILAN. Aralık dışı → CamError."""
    raise NotImplementedError("SPEC 25: tezgah.ornekler_25.kademeli_mil")


def yatak_grubu(parametreler: dict[str, dict[str, float]] | None = None) -> MontajTanimi:
    """Montaj; parametreler iş adı → {anahtar: değer}, None → VARSAYILAN."""
    raise NotImplementedError("SPEC 25: tezgah.ornekler_25.yatak_grubu")
