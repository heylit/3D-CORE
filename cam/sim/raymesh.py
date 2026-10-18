"""
SPEC 43 — Parça dexel'i: kapalı üçgen ağı ile ışın kesişimi (Möller–Trumbore).

Kesişimler sıralanır, çiftler halinde parça içi aralıkları verir. Tek sayıda kesişim → ışın 1e-9·Δ
kaydırılıp yeniden denenir; yine tekse CamError.
"""

from __future__ import annotations

from cam.dropcutter import TriMesh


def part_intervals(mesh: TriMesh, origin, direction) -> list[tuple[float, float]]:
    """Işın origin + s·direction üzerinde parça içi aralıklar [(s_giriş, s_çıkış), ...], sıralı."""
    raise NotImplementedError("SPEC 43")
