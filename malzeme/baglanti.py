"""
Malzeme kaydının kullanıldığı yerlere köprüler (SPEC 66): BOM kütlesi, FEM, kesme verisi, maliyet.

Bağımlılık yönü: malzeme → malzeme.model, assy.model, assy.bom, cam.model, core.model (açık arayüzler).
Bu paketleri hiçbir alt paket import etmez.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from assy.model import Assembly
from cam.model import CuttingData
from core.model import Material
from malzeme.kutuphane import Kutuphane
from malzeme.model import Malzeme

if TYPE_CHECKING:
    from geometry.part import Part


def bilesen_malzemeleri(assembly: Assembly, kut: Kutuphane) -> dict[str, Malzeme]:
    """Component.name → Malzeme; malzemesi None olan bileşen → ModelError (adlar listelenir)."""
    raise NotImplementedError("SPEC 66: bilesen_malzemeleri")


def yogunluk_haritasi(assembly: Assembly, kut: Kutuphane) -> dict[str, float]:
    """Component.part → rho [t/mm³]; aynı parça farklı malzemeyle ya da rho yok → ModelError."""
    raise NotImplementedError("SPEC 66: yogunluk_haritasi")


def kutle_tablosu(assembly: Assembly, parts: Mapping[str, Part], kut: Kutuphane) -> dict[str, float]:
    """Parça kimliği → birim kütle [t]; assy.bom.unit_masses(parts, yogunluk_haritasi(...)) ile aynı."""
    raise NotImplementedError("SPEC 66: kutle_tablosu")


def fem_malzemeleri(kut: Kutuphane, ids: Iterable[str]) -> list[Material]:
    """Her id için Malzeme.fem_malzemesi()."""
    raise NotImplementedError("SPEC 66: fem_malzemeleri")


def kesme_tablosu(
    kut: Kutuphane, takim: str, ap: float, ae: float | None = None, ids: Iterable[str] | None = None
) -> dict[str, CuttingData]:
    """Malzeme.id → CuttingData.

    ids verilmişse önerisi olmayan kayıt → ModelError; verilmemişse yalnız önerisi olanlar döner.
    """
    raise NotImplementedError("SPEC 66: kesme_tablosu")


def malzeme_maliyeti_eur(m: Malzeme, kutle_t: float) -> float:
    """fiyat [€/kg] · 1000 · kutle_t [t]; kutle_t < 0 ya da fiyat yok → ModelError."""
    raise NotImplementedError("SPEC 66: malzeme_maliyeti_eur")
