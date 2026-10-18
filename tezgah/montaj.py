"""
SPEC 25 — Montaj köprüsü: ağaç (07), kısıtlar (08), girişim (09) → `Montaj` JSON ve ikili ağlar.

Saf fonksiyonlar, web bağımlılığı yok. Birimler mm, t (kütle), t/mm³ (yoğunluk).

Montaj sözlüğü:
    {
      "sema": 1, "ad",
      "agac": Node.to_dict(),
      "parcalar": [{"kimlik", "ad", "malzeme", "rho", "kaynak": {"is", "tur"} | None, "hacim"}],
      "bilesenler": [{"yol", "parca", "T": 4x4 (satır öncelikli liste), "sabit"}],  # çözülmüş
      "bom": [BomLine sözlüğü], "kutle": {"toplam", "merkez": [x, y, z]},
      "sira": [Adim], "girisimler": [Girisim], "kontroller": [Kontrol], "baglar": [Bag]
    }
    Adim = {"i", "yol", "ad", "yaklasma": [ax, ay, az], "mesafe", "T_once": {yol: 4x4}, "T_sonra": {yol: 4x4},
            "dof_toplam", "serbestlik": {yol: Serbestlik}}
    Serbestlik = {"sayi", "oteleme": [[ux, uy, uz]], "vida": [{"yon", "nokta", "hatve"}], "etiketler": [str]}
    Girisim = {"i", "a", "b", "hacim", "bosluk", "ag": "/api/montaj/{ad}/ag/girisim/{i}"}

Kısıtlar bileşen adı olarak yaprak yolunu (SPEC 07 `walk`) kullanır.
Hata: yapı hatası `AssyError`, şekil hatası `GeometryError`; sessiz düzeltme yok (altın kural 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from assy.model import Assembly, Mate, Node

if TYPE_CHECKING:
    from geometry.part import Part
    from tezgah.iplik import Bag

ETIKET_TOL = 1e-9  # 1 − |yön·e| eşiği: dünya eksenine paralel serbestlik etiketi
SIMETRI_ACI = 37.0  # derece: dönel simetri sınaması
SIMETRI_TOL = 1e-6  # rel: common(parça, döndürülmüş) hacmi / parça hacmi


@dataclass
class Vida:
    """Serbest hareket vida ekseni (Murray–Li–Sastry 2.4).

    yön ω/|ω|, eksen noktası ω×Δt/|ω|², hatve ω·Δt/|ω|².
    """

    yon: np.ndarray  # (3,) birim
    nokta: np.ndarray  # (3,)
    hatve: float  # mm/rad


@dataclass
class Serbestlik:
    """Bir bileşenin diğerleri sabitken kalan serbest hareketleri.

    sayi     : 6 − rank(J_c)
    oteleme  : (a, 3) ortonormal öteleme yönleri ({v ∈ N : ω = 0})
    vida     : öteleme alt uzayının N içindeki dik tümleyeninin taban vektörlerinden vida eksenleri
    etiketler: "Tx".."Tz", "Rx".."Rz" (dünya eksenine paralel) ya da "T" / "vida"
    """

    sayi: int
    oteleme: np.ndarray
    vida: list[Vida] = field(default_factory=list)
    etiketler: list[str] = field(default_factory=list)


@dataclass
class MontajTanimi:
    """Bir montaj örneği.

    agac       : SPEC 07 kök düğümü
    parcalar   : parça kimliği → Part (parçanın kendi koordinatında)
    malzemeler : parça kimliği → (malzeme adı, ρ [t/mm³])
    kisitlar   : SPEC 08 kısıtları; Ref.component = yaprak yolu
    sabit      : sabit yaprak yolları (flatten `fixed`)
    sira       : yaprak yolları, montaj sırası; ilk eleman sabit olmalı
    kaynaklar  : parça kimliği → (iş adı, "torna" | "freze") — parça bir işten geliyorsa
    baglar     : parametre bağları (tezgah.iplik.Bag)
    """

    ad: str
    agac: Node
    parcalar: dict[str, Part]
    malzemeler: dict[str, tuple[str, float]]
    kisitlar: list[Mate]
    sabit: tuple[str, ...]
    sira: list[str]
    kaynaklar: dict[str, tuple[str, str]] = field(default_factory=dict)
    baglar: list[Bag] = field(default_factory=list)


def montaj(tanim: MontajTanimi) -> Assembly:
    """`flatten(agac, sabit)` + kısıtlar: çözülmemiş SPEC 08 montajı."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.montaj")


def serbestlik(assembly: Assembly, bilesen: str) -> Serbestlik:
    """Diğer bileşenler sabitken `bilesen`in serbestliği: J_c'nin sıfır uzayı (SPEC 08 `jacobian`) (K10)."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.serbestlik")


def yaklasma(
    tanim: MontajTanimi, assembly: Assembly, bilesen: str, yerlesmis: list[str]
) -> tuple[np.ndarray, float]:
    """Yaklaşma yönü a (birim) ve mesafe (bileşenin sınır kutusu köşegeni); SPEC 25 kuralı (K11)."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.yaklasma")


def sira_adimlari(tanim: MontajTanimi) -> list[dict]:
    """Montaj sırasının adımları (`Adim` sözlükleri). Geçersiz sıra → AssyError (K9, K11)."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.sira_adimlari")


def donel_simetrik(part: Part, yon: np.ndarray, nokta: np.ndarray) -> bool:
    """Parça (nokta, yon) ekseni etrafında 37° döndürülünce common hacmi parça hacmine rel 1e-6 ile eşit mi.

    common: SPEC 09.
    """
    raise NotImplementedError("SPEC 25: tezgah.montaj.donel_simetrik")


def girisimler(tanim: MontajTanimi) -> list[dict]:
    """Tam montajda hacmi > 0 olan çiftler (SPEC 09 `assy.girisim.check`), `Girisim` sözlükleri (K12)."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.girisimler")


def kontroller(tanim: MontajTanimi) -> list[dict]:
    """kisit_artigi, serbestlik (SPEC 25 kuralı), girisim, kutle kontrolleri (K13)."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.kontroller")


def montaj_json(tanim: MontajTanimi) -> dict:
    """`Montaj` sözlüğü (modül belgesi) (K8)."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.montaj_json")


def ag_ikili(V: np.ndarray, T: np.ndarray) -> bytes:
    """Üçgen ağ, little-endian (K14).

    uint32 sema, uint32 nv, uint32 nt, uint32 0, float32[nv·3], uint32[nt·3]; bloklar 8'e tamamlanır.
    """
    raise NotImplementedError("SPEC 25: tezgah.montaj.ag_ikili")


def ag_coz(veri: bytes) -> tuple[np.ndarray, np.ndarray]:
    """`ag_ikili` çıktısı → (V (nv, 3) float32, T (nt, 3) uint32)."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.ag_coz")


def parca_agi(tanim: MontajTanimi, kimlik: str, tol: float = 0.01) -> bytes:
    """Parçanın kendi koordinatındaki ağı (`Part.mesh`), `ag_ikili` biçiminde (K14)."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.parca_agi")


def girisim_agi(tanim: MontajTanimi, i: int, tol: float = 0.01) -> bytes:
    """i. girişimin kesişim katısının dünya koordinatındaki ağı, `ag_ikili` biçiminde (K12)."""
    raise NotImplementedError("SPEC 25: tezgah.montaj.girisim_agi")
