"""
SPEC 58 — Süre, maliyet ve teklif: parça başı maliyet dökümü.

Süre iş föyünden (SPEC 38 `JobSheet`) okunur, yeniden hesaplanmaz; SPEC 72 zaman profili verilirse bağlama
süresi `CycleTime.total`'dan gelir (Ek 1). Ücretler gizli veridir: `yerel_parcalar/atolye-ucretleri.json`
(repoya girmez; örnek: examples/58_atolye_ucretleri_ornek.json).

Süre s, ücret €/saat (çarpımda / 3600), kütle t, fiyat €/kg (· 1000). Kodda başka birim dönüşümü yok.
Bağımlılık (K11): yalnız stdlib, cam.model, malzeme.model, malzeme.kutuphane, atolye.is_foyu.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atolye.is_foyu import JobSheet
from cam.model import CylinderStock, MachineProfile, Stock
from malzeme.model import Malzeme, ModelError

if TYPE_CHECKING:  # SPEC 72 / 59 main'de değilken de içe aktarılabilsin diye yalnız tip
    TimeProfile = Any
    ToolWear = Any

VARSAYILAN_YOL = "yerel_parcalar/atolye-ucretleri.json"
ORNEK_YOL = "examples/58_atolye_ucretleri_ornek.json"
KALEM_ADLARI = ("tezgah", "hazirlik", "iscilik", "malzeme", "takim", "dis_islem")

__all__ = [
    "KALEM_ADLARI",
    "Kalem",
    "Maliyet",
    "ModelError",
    "Ucretler",
    "ham_hacim",
    "kademeler",
    "maliyet",
    "ucretleri_oku",
]


@dataclass(frozen=True)
class Ucretler:
    """Atölye ücret dosyasının alanları (şema 1). Adlar JSON anahtarlarıyla aynıdır.

    aciklama: örnek dosyanın ilk alanı ("UYDURMA ÖRNEK ..."); hesapta kullanılmaz.
    fire_orani: §2 malzeme kalemindeki f_fire, [0, 1); dosyada yoksa 0.
    """

    sema: int = 1
    aciklama: str = ""
    para_birimi: str = "EUR"
    iscilik_saat: float = 0.0  # U_i €/saat
    operator_orani: float = 1.0  # k_op, (0, 1]
    genel_gider: float = 0.0  # g, [0, 5]
    kar_payi: float = 0.0  # k, [0, 5]
    fire_orani: float = 0.0  # f_fire, [0, 1)
    tezgah_saat: Mapping[str, float] = field(default_factory=dict)  # MachineProfile.name → U_m €/saat
    varsayilan_sureler: Mapping[str, float] = field(default_factory=dict)  # yukle_s, hazirlik_s
    malzeme_fiyati: Mapping[str, float] = field(default_factory=dict)  # Malzeme.id → €/kg
    takim: Mapping[str, Mapping[str, float | None]] = field(default_factory=dict)  # kenar_eur, kenar_omru_dk
    kesim_payi: Mapping[str, float] = field(default_factory=dict)  # prizma_mm, testere_mm, alin_mm

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Ucretler:
        """Şema 1 sözlüğü → Ucretler; bilinmeyen alan, yanlış şema, negatif ücret → ModelError."""
        raise NotImplementedError("SPEC 58: Ucretler.from_dict")

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError("SPEC 58: Ucretler.to_dict")


def ucretleri_oku(yol: str | Path = VARSAYILAN_YOL) -> Ucretler:
    """Ücret dosyasını okur. Dosya yoksa ModelError:
    "Atölye ücret dosyası yok: <yol>. Örnek: examples/58_atolye_ucretleri_ornek.json"."""
    raise NotImplementedError("SPEC 58: ucretleri_oku")


@dataclass(frozen=True)
class Kalem:
    ad: str  # KALEM_ADLARI'ndan biri
    aciklama: str  # formül + girdiler, okunur metin
    tutar_eur: float  # parça başı


@dataclass(frozen=True)
class Maliyet:
    n: int
    t_parca_s: float
    kalemler: tuple[Kalem, ...]
    ara_toplam_eur: float  # M = Σ kalem
    fiyat_eur: float  # parça başı, M · (1 + g) · (1 + k)
    uyarilar: tuple[str, ...]


def ham_hacim(stok: Stock | CylinderStock, u: Ucretler) -> float:
    """Ham malzeme hacmi [mm³] (§3): prizma (Lx+2p)(Ly+2p)(Lz+2p); çubuk π(D/2)²(L + p_testere + p_alin)."""
    raise NotImplementedError("SPEC 58: ham_hacim")


def maliyet(
    job: JobSheet,
    profiller: Sequence[MachineProfile],
    stok: Stock | CylinderStock,
    malzeme: Malzeme,
    u: Ucretler,
    n: int,
    sureler: Sequence[tuple[float, float]] | None = None,
    dis_islem: Sequence[tuple[str, float]] = (),
    zaman_profilleri: Mapping[str, TimeProfile] | None = None,
    asinma: Sequence[ToolWear] | None = None,
) -> Maliyet:
    """n adetlik partide parça başı maliyet (§1, §2; Ek 1–3).

    profiller: bağlama başına tezgâh (len = len(job.setups)). sureler: bağlama başına (yukle_s, hazirlik_s);
    None → u.varsayilan_sureler. dis_islem: (ad, € / parça). zaman_profilleri: tezgâh adı → SPEC 72 profili.
    asinma: SPEC 59 ToolWear listesi (takım payı c_kenar · D).
    """
    raise NotImplementedError("SPEC 58: maliyet")


def kademeler(
    job: JobSheet,
    profiller: Sequence[MachineProfile],
    stok: Stock | CylinderStock,
    malzeme: Malzeme,
    u: Ucretler,
    adetler: Sequence[int] = (1, 10, 50, 200),
    sureler: Sequence[tuple[float, float]] | None = None,
    dis_islem: Sequence[tuple[str, float]] = (),
    zaman_profilleri: Mapping[str, TimeProfile] | None = None,
    asinma: Sequence[ToolWear] | None = None,
) -> list[Maliyet]:
    """Her adet için maliyet(...) baştan hesaplanır (§5); satırlar birbirinden türetilmez."""
    raise NotImplementedError("SPEC 58: kademeler")
