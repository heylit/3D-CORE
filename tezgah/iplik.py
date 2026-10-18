"""
SPEC 25 — Tek iplik: parametre bağları, yeniden hesaplama zinciri ve ikiye bölme önerisi.

Bir parametre değişince parça → torna işi (yol, G-code, sim, süre) → montaj (çözüm, girişim) birlikte
yeniden hesaplanır. Öneri: v(p) = girişim hacmi; p₀'da v > 0 iken p₀'a en yakın v = 0 sınırı
ikiye bölmeyle |Δp| ≤ eps içinde bulunur ve v = 0 tarafındaki uç önerilir. Bulunamazsa öneri yok
(sahte sayı yok, altın kural 5).

Saf Python, web bağımlılığı yok. Durum (`Depo`) tek kullanıcılık sunucu belleğindedir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

ONERI_EPS = 1e-3  # parametre birimi (mm)
ONERI_EN_FAZLA = 40  # en fazla v(p) değerlendirmesi


@dataclass(frozen=True)
class Bag:
    """Bir iş parametresinin hangi parçaları değiştirdiği. min ≤ deger ≤ max."""

    is_ad: str
    anahtar: str
    deger: float
    min: float
    max: float
    parcalar: tuple[str, ...]


@dataclass(frozen=True)
class Oneri:
    """İkiye bölme sonucu. deger None → öneri yok, `neden` açıklar."""

    deger: float | None
    hacim: float | None
    neden: str | None
    degerlendirme: int


def oneri(
    v: Callable[[float], float],
    p0: float,
    pmin: float,
    pmax: float,
    eps: float = ONERI_EPS,
    en_fazla: int = ONERI_EN_FAZLA,
) -> Oneri:
    """v(p0) > 0 iken [pmin, pmax] içinde p0'a en yakın v = 0 sınırını ikiye bölmeyle bulur (K16)."""
    raise NotImplementedError("SPEC 25: tezgah.iplik.oneri")


@dataclass
class Depo:
    """Sunucu belleğindeki güncel parametreler: iş adı → {anahtar: değer}.

    `sifirla` örnek değerlerine döndürür.
    """

    parametreler: dict[str, dict[str, float]] = field(default_factory=dict)

    def sifirla(self) -> None:
        raise NotImplementedError("SPEC 25: tezgah.iplik.Depo.sifirla")

    def torna_isi(self, ad: str):
        """Güncel parametrelerle `TornaIsi` (tezgah.ornekler_25). Bilinmeyen ad → KeyError."""
        raise NotImplementedError("SPEC 25: tezgah.iplik.Depo.torna_isi")

    def montaj(self, ad: str):
        """Güncel parametrelerle `MontajTanimi`. Bilinmeyen ad → KeyError."""
        raise NotImplementedError("SPEC 25: tezgah.iplik.Depo.montaj")

    def ayarla(self, montaj_ad: str, is_ad: str, anahtar: str, deger: float) -> dict:
        """Parametreyi ayarlar; {"montaj": Montaj, "is": Is, "sure_farki": s} (K15).

        Aralık dışı → CamError.
        """
        raise NotImplementedError("SPEC 25: tezgah.iplik.Depo.ayarla")

    def oneri(self, montaj_ad: str, is_ad: str, anahtar: str, cift: tuple[str, str]) -> Oneri:
        """Bağlı parametre için girişimi sıfırlayan öneri (K16)."""
        raise NotImplementedError("SPEC 25: tezgah.iplik.Depo.oneri")
