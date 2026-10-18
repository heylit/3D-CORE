"""
SPEC 25 — Torna köprüsü: SPEC 20 yolları + SPEC 21 G-code + SPEC 22 simülasyonu →
`Is` (tur "torna") ve ikili diziler.

Saf fonksiyonlar, web bağımlılığı yok. Birimler mm, mm/dev, m/dk, dev/dk, s.
Modelde x yarıçaptır (SPEC 20); G-code'da X çaptır (SPEC 21). `Is` sözlüğü SPEC 24 biçimindedir, ek alanlar:
    "tur": "torna"
    "kurulum": {"stok": CylinderStock.to_dict(), "wcs", "malzeme", "aynalar": [CylinderStock.to_dict()]}
    "islemler[].takim": {"T", "ad", "r" (burun yarıçapı), "uc" (uç numarası), "q": [q_z, q_x], "tur"}
    "gcode[]": {"metin", "islem", "dro": {"X": çap, "Z"} | None}   (hareket satırında satırın uç noktası)
    "sure": {"toplam", "islem", "kumulatif_url", "n_max": G50 sınırı | None}
Hareketler `(x, 0, z)`, yay merkezi `(x, z)` (cam.model kuralı).

Hata: geçersiz iş tanımı `CamError` fırlatır; sessiz düzeltme yok (altın kural 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from cam.model import CylinderStock, Setup, Toolpath

if TYPE_CHECKING:
    from geometry.part import Part

KONUM_EPS = 5e-4  # mm: canlı bağ ve DRO toleransı (K2, K3)


@dataclass
class TornaIslem:
    """Torna işindeki bir işlem: SPEC 20 yolu + arayüzde gösterilen kimlik ve parametreler.

    anahtar     : işlem türü ("alin", "kaba", "ince", "kanal", "dis", "boy")
    op          : SPEC 20 `Toolpath` (plane ZX, feed_mode PER_REV)
    parametreler: arayüzde değiştirilebilen sayılar (ör. {"a_p": 2.0, "f": 0.25, "Vc": 200.0})
    """

    anahtar: str
    ad: str
    op: Toolpath
    parametreler: dict[str, float] = field(default_factory=dict)


@dataclass
class TornaIsi:
    """Bir torna işi.

    kurulum    : `CylinderStock` ya da ayna / punta bağlama elemanlı `Setup` (SPEC 22)
    spindle    : "M3" | "M4" (SPEC 21 yazıcısı)
    tool_change: (x, z) takım değiştirme noktası, yarıçap (SPEC 21)
    parca      : hedef CAD parçası (sapma, çakma, kalan malzeme için); None → bu kontroller yapılmaz
    hucre      : SPEC 22 radyal ızgara hücresi Δz [mm]
    """

    ad: str
    kurulum: CylinderStock | Setup
    malzeme: str
    islemler: list[TornaIslem]
    spindle: str = "M3"
    tool_change: tuple[float, float] = (100.0, 100.0)
    parca: Part | None = None
    hucre: float = 0.5


def hareketler(tanim: TornaIsi) -> list[dict]:
    """İşlemlerin hareketleri art arda, SPEC 24 `hareketler` biçiminde (K1)."""
    raise NotImplementedError("SPEC 25: tezgah.torna.hareketler")


def gcode_satirlari(tanim: TornaIsi) -> tuple[list[dict], list[list[int] | None]]:
    """SPEC 21 yazıcısının satırları (`dro` dahil) ve satır → hareket aralığı (K2, K3)."""
    raise NotImplementedError("SPEC 25: tezgah.torna.gcode_satirlari")


def devir(tanim: TornaIsi) -> np.ndarray:
    """Her noktada iş mili devri n_k [dev/dk], float64 (n,) (K4).

    G96'da min(1000·Vc/(π·2x), n_max), G97'de rpm.
    """
    raise NotImplementedError("SPEC 25: tezgah.torna.devir")


def kontroller(tanim: TornaIsi) -> list[dict]:
    """SPEC 21/22 kontrolleri (K7).

    cakma, kalan_malzeme, hizli_carpma, ayna_carpma, geri_okuma, devir_siniri.
    """
    raise NotImplementedError("SPEC 25: tezgah.torna.kontroller")


def is_json(tanim: TornaIsi) -> dict:
    """İşin tamamı: `Is` sözlüğü, `tur = "torna"` (modül belgesi). `json.dumps` ile yazılabilir (K1)."""
    raise NotImplementedError("SPEC 25: tezgah.torna.is_json")


def noktalar_ikili(tanim: TornaIsi) -> bytes:
    """SPEC 24 nokta dizisi biçimi + son blok `devir: float32[n]` [dev/dk] (K4, K5).

    Konum (x, 0, z): hayali uç.
    """
    raise NotImplementedError("SPEC 25: tezgah.torna.noktalar_ikili")


def noktalar_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`noktalar_ikili` çıktısı → SPEC 24 alanları + "devir"."""
    raise NotImplementedError("SPEC 25: tezgah.torna.noktalar_coz")


def sim_ikili(tanim: TornaIsi) -> bytes:
    """Torna kesit olay listesi, little-endian ikili (K6).

    Biçim (bloklar 8 baytın katına sıfırla tamamlanır):
        başlık : uint32 sema, uint32 nz, uint32 m (olay sayısı), uint32 0
        ızgara : float64[4]   z0, dz, r_dis0 (= D/2), r_ic0 (= d/2)
        ofset  : uint32[nz+1] hücre i'nin olayları [ofset[i], ofset[i+1])
        k      : int32[m]     olayın nokta indeksi (hücre içinde artan)
        r_dis  : float32[m]   olaydan sonraki dış yarıçap (SPEC 22 `outer()`)
        r_ic   : float32[m]   olaydan sonraki iç yarıçap (SPEC 22 `inner()`)
        islem  : int16[m]
        hedef  : float32[nz]  hedef parçanın hücre merkezlerindeki dış yarıçapı (parça yoksa NaN)
    k anındaki kesit: her hücrede k'si ≤ k olan son olay; yoksa (r_dis0, r_ic0).
    """
    raise NotImplementedError("SPEC 25: tezgah.torna.sim_ikili")


def sim_kesit(veri: bytes, k: int) -> tuple[np.ndarray, np.ndarray]:
    """`sim_ikili` çıktısından k anındaki (r_dis, r_ic), float32 (nz,) (K6)."""
    raise NotImplementedError("SPEC 25: tezgah.torna.sim_kesit")
