"""
SPEC 23 — Yuvarlatma (fillet): dikey kenarlar, üst kenarlar, tüm kenarlar.

Hiçbir işlem girdi parçayı değiştirmez, her zaman yeni Part döner; delik kayıtları (Part.holes) korunur.
Birimler: mm.
"""

from __future__ import annotations

import math

import build123d as bd

from geometry.features import DV_MIN, _pozitif, _ust_kenarlar, _yeni_part
from geometry.part import GeometryError, Part

EPS_KENAR = 1e-3  # mm: dışbükeylik sınamasında kenar çevresindeki örnek noktaların uzaklığı


def _tek_kati(part: Part):
    solids = list(part.shape.solids())
    if len(solids) != 1:
        raise GeometryError(f"fillet tek katıda uygulanır ({len(solids)} katı)")
    return solids[0]


def _disbukey(kati, kenar) -> bool:
    """Kenarın çevresinde, kenara dik küçük bir çemberde 8 nokta: içeride kalanlar yarıdan azsa dışbükey.

    Dik kenarda (90°) dışbükey 2/8, içbükey 6/8 nokta içeridedir; teğet geçiş ve silindir dikişi 4/8 verir.
    Açılar 22.5° kaydırılır ki noktalar yüz düzlemlerinin tam üstüne düşmesin.
    """
    m = kenar.position_at(0.5)
    t = kenar.tangent_at(0.5)
    u = t.cross(bd.Vector(1, 0, 0) if abs(t.X) < 0.9 else bd.Vector(0, 1, 0)).normalized()
    v = t.cross(u).normalized()
    icerde = 0
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        q = m + u * (EPS_KENAR * math.cos(a)) + v * (EPS_KENAR * math.sin(a))
        icerde += kati.is_inside(q)
    return icerde < 4


def _dikey_kenarlar(kati) -> list:
    """Z eksenine paralel, dışbükey doğrusal kenarlar (dikiş ve içbükey kenarlar hariç)."""
    kenarlar = []
    for e in kati.edges():
        if e.geom_type != bd.GeomType.LINE:
            continue
        t = e.tangent_at(0.5)
        if abs(abs(t.Z) - 1) > 1e-9:
            continue
        if _disbukey(kati, e):
            kenarlar.append(e)
    return kenarlar


def _fillet(part: Part, r: float, kati, kenarlar: list, islem: str) -> Part:
    """kati'nın kenarlarını r ile yuvarlatır; OCCT hatası veya geçersiz sonuç → GeometryError."""
    if not kenarlar:
        raise GeometryError(
            f"{part.name} / {islem}: yuvarlatılacak kenar yok — dışbükey kenarı olan bir parça seçin"
        )
    try:
        sonuc = _yeni_part(kati.fillet(r, kenarlar), part.name, part.holes)
    except GeometryError:
        raise
    except Exception as e:  # OCCT istisnası
        raise GeometryError(
            f"{part.name} / {islem}: fillet kurulamadı (r = {r:g} mm) — {_sinir_onerisi(kati, kenarlar, r)}"
        ) from e
    dV = part.volume - sonuc.volume
    if dV <= DV_MIN:
        raise GeometryError(
            f"{part.name} / {islem}: fillet malzeme kaldırmadı (r = {r:g} mm, ΔV = {dV:.3g} mm³) — "
            "yarıçapı büyütün ya da başka kenar seçin"
        )
    return sonuc


def _sinir_onerisi(kati, kenarlar: list, r: float) -> str:
    """OCCT'nin kabul ettiği en büyük yarıçapı arar (SPEC 54: öneride sınır); bulunamazsa genel öneri."""
    try:
        r_max = float(kati.max_fillet(kenarlar, tolerance=0.1, max_iterations=50))
    except Exception:  # noqa: BLE001 — arama da başarısız olabilir; öneri yine verilir
        r_max = 0.0
    if 0.0 < r_max < r:
        return f"yarıçapı {r_max:.2f} mm'nin altına indirin"
    return f"yarıçapı {r / 2:g} mm ya da daha küçük deneyin"


def fillet_vertical(part: Part, r: float) -> Part:
    """Z eksenine paralel tüm dışbükey doğrusal kenarları r yarıçapıyla yuvarlatır.

    Blokta ΔV = (4 − π) r² c (SPEC 23).
    """
    _pozitif(r=r)
    kati = _tek_kati(part)
    return _fillet(part, r, kati, _dikey_kenarlar(kati), "fillet_vertical")


def fillet_top(part: Part, r: float) -> Part:
    """Üst yüzün (zmax) tüm kenarlarını r yarıçapıyla yuvarlatır (delik ağızları dahil)."""
    _pozitif(r=r)
    kati = _tek_kati(part)
    return _fillet(part, r, kati, _ust_kenarlar(part), "fillet_top")


def fillet_all(part: Part, r: float) -> Part:
    """Parçanın tüm kenarlarını r yarıçapıyla yuvarlatır."""
    _pozitif(r=r)
    kati = _tek_kati(part)
    return _fillet(part, r, kati, list(kati.edges()), "fillet_all")
