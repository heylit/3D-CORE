"""
SPEC 26 — modelleme köprüsü: SolveResult / Rapor / Part → JSON ve ikili dizi; "Tezgah'a gönder" → SPEC 24 Is.

Saf fonksiyonlar, FastAPI'siz test edilir. Her JSON yanıtında "sema": SEMA.

SolveResult JSON: {sema, points: {kimlik: [x, y]}, radii, sides: {"k": ±1}, iterations, residual, dof,
                   freedom, directions: {kimlik: [x, y]}, redundant: [k]}
Ağ ikilisi (SPEC 24 ikili blok biçimi): float32 köşeler (n, 3), int32 üçgenler (m, 3), int32 yüz index (m,).
"""

from __future__ import annotations

import numpy as np

from geometry.part import Part
from sketch.solver import SolveResult
from tezgah.kopru import IsTanimi


def cozum_json(res: SolveResult) -> dict:
    """SolveResult → JSON sözlüğü (float kayıpsız)."""
    raise NotImplementedError("SPEC 26: cozum_json")


def eskiz_coz(eskiz: dict) -> dict:
    """Sketch.to_dict() → sketch.solver.solve → cozum_json. Çelişki SketchError olarak yükselir."""
    raise NotImplementedError("SPEC 26: eskiz_coz")


def eskiz_surukle(eskiz: dict, nokta: str, hedef) -> dict:
    """Sketch.to_dict() → sketch.solver.drag → cozum_json. Sabit nokta SketchError olarak yükselir."""
    raise NotImplementedError("SPEC 26: eskiz_surukle")


def rapor_json(rapor) -> dict:
    """modelleme.Rapor → JSON sözlüğü."""
    raise NotImplementedError("SPEC 26: rapor_json")


def ag_ikili(part: Part) -> bytes:
    """Parçanın üçgen ağı: float32 köşe, int32 üçgen, int32 yüz index."""
    raise NotImplementedError("SPEC 26: ag_ikili")


def ag_coz(veri: bytes) -> dict[str, np.ndarray]:
    """ag_ikili'nin tersi: {"kose": (n, 3), "ucgen": (m, 3), "yuz": (m,)}."""
    raise NotImplementedError("SPEC 26: ag_coz")


def yuz_json(part: Part, index: int) -> dict:
    """{sema, plane: Plane.to_dict(), outline: [[seg JSON]]} (face_plane, face_outline)."""
    raise NotImplementedError("SPEC 26: yuz_json")


def tezgaha_gonder(model: dict) -> IsTanimi:
    """Modelin geçmişinden freze işi: stok = sınır kutusu + pay (XY 2 mm, üst 1 mm, alt 0); yüz alma;
    +Z kör kesim → cep; boydan boya iç bölge → iç kontur; en alt kesit dış sınırı → dış kontur;
    düşey Part.holes → delme. +Z dışı kesim / delik Kontrol(durum="uyari") ile atlanır."""
    raise NotImplementedError("SPEC 26: tezgaha_gonder")
