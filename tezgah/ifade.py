"""
SPEC 26 — güvenli ifade değerlendirici (ölçüler ve parametreler).

Dil: sayılar, + − * / **, parantez, tekli eksi, parametre adları, pi, sqrt, sin, cos, tan (derece),
abs, min, max. Python eval kullanılmaz; ast ağacı beyaz listeyle yürünür. Başka her düğüm, bilinmeyen ad,
sıfıra bölme, sonsuz / nan sonuç ve parametreler arası döngü → IfadeError (adlarla).
"""

from __future__ import annotations


class IfadeError(ValueError):
    """Geçersiz ya da değerlendirilemeyen ifade."""


def degerlendir(ifade: str | float, ortam: dict[str, float] | None = None) -> float:
    """İfadeyi ortamdaki parametre değerleriyle değerlendirir.

    ifade: sayı, "40" ya da "=genislik/2" (baştaki "=" isteğe bağlı).
    """
    raise NotImplementedError("SPEC 26: degerlendir")


def parametreleri_coz(parametreler: dict[str, str | float]) -> dict[str, float]:
    """Parametre tablosunu bağımlılık grafiğinin topolojik sırasıyla değerlendirir.
    Döngü (a = b, b = a) → IfadeError (döngüdeki adlarla)."""
    raise NotImplementedError("SPEC 26: parametreleri_coz")
