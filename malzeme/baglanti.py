"""
Malzeme kaydının kullanıldığı yerlere köprüler (SPEC 66): BOM kütlesi, FEM, kesme verisi, maliyet.

Bağımlılık yönü: malzeme → malzeme.model, assy.model, assy.bom, cam.model, core.model (açık arayüzler).
Bu paketleri hiçbir alt paket import etmez.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from assy.bom import unit_masses
from assy.model import Assembly, AssyError
from cam.model import CuttingData
from core.model import Material
from malzeme.kutuphane import Kutuphane
from malzeme.model import TAKIM_MALZEMELERI, Malzeme, ModelError

if TYPE_CHECKING:
    from geometry.part import Part


def bilesen_malzemeleri(assembly: Assembly, kut: Kutuphane) -> dict[str, Malzeme]:
    """Component.name → Malzeme; malzemesi None olan bileşen → ModelError (adlar listelenir)."""
    eksik = [c.name for c in assembly.components if c.material is None]
    if eksik:
        raise ModelError(f"Montaj {assembly.name!r}: malzemesi atanmamış bileşen: {', '.join(eksik)}")
    return {c.name: kut.get(c.material) for c in assembly.components}


def yogunluk_haritasi(assembly: Assembly, kut: Kutuphane) -> dict[str, float]:
    """Component.part → rho [t/mm³]; aynı parça farklı malzemeyle ya da rho yok → ModelError."""
    parca_malzeme: dict[str, Malzeme] = {}
    for ad, m in bilesen_malzemeleri(assembly, kut).items():
        parca = next(c.part for c in assembly.components if c.name == ad)
        onceki = parca_malzeme.setdefault(parca, m)
        if onceki.id != m.id:
            raise ModelError(f"Parça {parca!r} iki farklı malzemeyle kullanılıyor: {onceki.id!r} ve {m.id!r}")
    return {parca: m.iste("rho") for parca, m in parca_malzeme.items()}


def kutle_tablosu(assembly: Assembly, parts: Mapping[str, Part], kut: Kutuphane) -> dict[str, float]:
    """Parça kimliği → birim kütle [t]; assy.bom.unit_masses(parts, yogunluk_haritasi(...)) ile aynı."""
    try:
        return unit_masses(parts, yogunluk_haritasi(assembly, kut))
    except AssyError as e:
        raise ModelError(str(e)) from e


def fem_malzemeleri(kut: Kutuphane, ids: Iterable[str]) -> list[Material]:
    """Her id için Malzeme.fem_malzemesi()."""
    return [kut.get(id).fem_malzemesi() for id in ids]


def kesme_tablosu(
    kut: Kutuphane, takim: str, ap: float, ae: float | None = None, ids: Iterable[str] | None = None
) -> dict[str, CuttingData]:
    """Malzeme.id → CuttingData.

    ids verilmişse önerisi olmayan kayıt → ModelError; verilmemişse yalnız önerisi olanlar döner.
    """
    if takim not in TAKIM_MALZEMELERI:
        raise ModelError(f"Bilinmeyen takım malzemesi: {takim!r} (geçerli: {', '.join(TAKIM_MALZEMELERI)})")
    if ids is None:
        secilen = [m for m in kut if takim in set(m.kesme)]
    else:
        secilen = [kut.get(id) for id in ids]
    return {m.id: m.kesme_verisi(takim, ap, ae) for m in secilen}


def malzeme_maliyeti_eur(m: Malzeme, kutle_t: float) -> float:
    """fiyat [€/kg] · 1000 · kutle_t [t]; kutle_t < 0 ya da fiyat yok → ModelError."""
    if kutle_t < 0:
        raise ModelError(f"{m.name!r}: kütle negatif olamaz ({kutle_t} t)")
    return m.iste("fiyat") * 1000.0 * kutle_t
