"""
SPEC 37 — örnek proje (uydurma geometri): SPEC 25 "yatak grubu" (kademeli mil torna işi + montaj, L = 20,
girişim var) ve SPEC 24 flanş freze işi tek projede; SPEC 26 varsa "model" bölümü de eklenir.
"""

from __future__ import annotations

from fileio.proje import Proje

ORNEK_PROJELER = ("yatak_grubu",)


def ornek_proje(ad: str) -> Proje:
    """Adı verilen örnek projeyi bellekte kurar. Bilinmeyen ad → KeyError."""
    raise NotImplementedError
