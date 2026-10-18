"""
SPEC 25 — tek iplik: ikiye bölme önerisi (`tezgah.iplik.oneri`, `Depo.oneri`): K16.

Saf testlerde v(p) elle seçilmiş parçalı doğrusal fonksiyonlardır; sayaçla değerlendirme sayısı ölçülür.
Örnek testleri build123d ve SPEC 09'u ister (girişim hacmi `assy.girisim.check`'ten); yoksa atlanır.
"""

from __future__ import annotations

import math

import pytest

from tezgah.iplik import ONERI_EN_FAZLA, ONERI_EPS, Depo, oneri


class Sayac:
    """v(p) ve çağrı sayısı."""

    def __init__(self, f):
        self.f = f
        self.n = 0
        self.p: list[float] = []

    def __call__(self, p: float) -> float:
        self.n += 1
        self.p.append(p)
        return self.f(p)


def mil_hacmi(p: float) -> float:
    """Örnekteki gibi: V = π·12²·(L − 10), L ≤ 10'da 0."""
    return math.pi * 144 * max(0.0, p - 10.0)


def test_constants():
    assert ONERI_EPS == 1e-3
    assert ONERI_EN_FAZLA == 40


def test_suggestion_one_sided():
    """K16: p₀ = 20, [5, 30] → |öneri − 10| ≤ 1e-3, v(öneri) = 0, değerlendirme ≤ 40."""
    v = Sayac(mil_hacmi)
    o = oneri(v, 20.0, 5.0, 30.0)
    assert o.deger is not None
    assert abs(o.deger - 10.0) <= 1e-3
    assert mil_hacmi(o.deger) == 0.0
    assert o.hacim == 0.0
    assert o.neden is None
    assert v.n <= 40
    assert o.degerlendirme == v.n
    assert all(5.0 <= p <= 30.0 for p in v.p)


def test_suggestion_upper_side():
    """K16: v = 0 tarafı yukarıdaysa (p ≥ 14'te girişim yok) öneri o taraftan, ≥ 14."""
    v = Sayac(lambda p: max(0.0, 14.0 - p))
    o = oneri(v, 12.0, 5.0, 30.0)
    assert o.deger is not None and 14.0 <= o.deger <= 14.0 + 1e-3
    assert v.n <= 40


def test_suggestion_nearest_of_two_sides():
    """K16: iki uçta da v = 0 ise p₀'a en yakın sınır:
    v > 0 yalnız (8, 14)'te, p₀ = 12 → 14 (uzaklık 2 < 4)."""
    v = Sayac(lambda p: max(0.0, min(p - 8.0, 14.0 - p)))
    o = oneri(v, 12.0, 0.0, 30.0)
    assert o.deger is not None
    assert abs(o.deger - 14.0) <= 1e-3 and o.deger >= 14.0
    assert v.n <= 40
    v = Sayac(lambda p: max(0.0, min(p - 8.0, 14.0 - p)))
    o = oneri(v, 9.0, 0.0, 30.0)  # bu kez alt sınır daha yakın (1 < 5)
    assert o.deger is not None and abs(o.deger - 8.0) <= 1e-3 and o.deger <= 8.0


def test_suggestion_eps():
    """K16: eps verilince |Δp| ≤ eps."""
    o = oneri(mil_hacmi, 20.0, 5.0, 30.0, eps=1e-6)
    assert o.deger is not None and 10.0 - 1e-6 <= o.deger <= 10.0


def test_no_suggestion_everywhere_interfering():
    """K16: aralık [12, 30] (her yerde girişim) → deger None ve neden metni; sahte sayı yok."""
    v = Sayac(mil_hacmi)
    o = oneri(v, 20.0, 12.0, 30.0)
    assert o.deger is None and o.hacim is None
    assert isinstance(o.neden, str) and o.neden
    assert v.n <= 40


def test_no_suggestion_without_interference():
    """K16: v(p₀) = 0 (girişim yok) → deger None, neden metni."""
    o = oneri(mil_hacmi, 8.0, 5.0, 30.0)
    assert o.deger is None and o.neden


def test_suggestion_respects_budget():
    """K16: en fazla `en_fazla` değerlendirme; dar bütçede eps'e inemiyorsa sahte sayı yok."""
    v = Sayac(mil_hacmi)
    o = oneri(v, 20.0, 5.0, 30.0, en_fazla=5)
    assert v.n <= 5
    if o.deger is not None:
        assert mil_hacmi(o.deger) == 0.0 and abs(o.deger - 10.0) <= 1e-3
    else:
        assert o.neden


# ---------------------------------------------------------------- örnek: Depo.oneri


def _ornek_hazir():
    pytest.importorskip("build123d")
    from geometry.part import Part

    if not (hasattr(Part, "common") and hasattr(Part, "fuse")):
        pytest.skip("SPEC 09 (Part.common / Part.fuse) henüz yok")
    return pytest.importorskip("assy.girisim", reason="SPEC 09 (assy.girisim) henüz yok")


def _hacim(gm, L: float, a: str, b: str) -> float:
    """SPEC 09: tam montajda (a, b) çiftinin kesişim hacmi (girişim yoksa 0)."""
    from assy.solver import solve
    from assy.tree import apply, flatten
    from tezgah.ornekler_25 import yatak_grubu

    tanim = yatak_grubu({"kademeli_mil": {"L": L}})
    asm = flatten(tanim.agac, tanim.sabit)
    asm.mates = list(tanim.kisitlar)
    solve(asm).apply(asm)
    for c in gm.check(apply(tanim.agac, asm), tanim.parcalar):
        if c.kind == gm.ClashKind.GIRISIM and {c.a, c.b} == {a, b}:
            return c.volume
    return 0.0


def test_depot_suggestion_example():
    """K16, örnek: L = 20'de öneri |L − 10| ≤ 1e-3, L_öneri'de SPEC 09 hacmi 0, değerlendirme ≤ 40."""
    gm = _ornek_hazir()
    depo = Depo()
    depo.sifirla()
    tanim = depo.montaj("yatak_grubu")
    a, b = tanim.sira[2], tanim.sira[0]  # mil, plaka
    o = depo.oneri("yatak_grubu", "kademeli_mil", "L", (a, b))
    assert o.deger is not None and abs(o.deger - 10.0) <= 1e-3
    assert o.degerlendirme <= 40
    assert _hacim(gm, o.deger, a, b) == 0.0
    assert depo.parametreler["kademeli_mil"]["L"] == 20.0  # öneri parametreyi değiştirmez


def test_depot_no_suggestion_when_clear():
    """K16, örnek: girişimsiz durumda (L = 9.5) öneri istenirse deger None."""
    _ornek_hazir()
    depo = Depo()
    depo.sifirla()
    depo.ayarla("yatak_grubu", "kademeli_mil", "L", 9.5)
    tanim = depo.montaj("yatak_grubu")
    o = depo.oneri("yatak_grubu", "kademeli_mil", "L", (tanim.sira[2], tanim.sira[0]))
    assert o.deger is None and o.neden


def test_depot_reset_and_unknown():
    """Depo: sifirla → VARSAYILAN (L = 20); bilinmeyen iş / montaj adı KeyError."""
    from tezgah.ornekler_25 import VARSAYILAN

    depo = Depo()
    depo.sifirla()
    assert depo.parametreler == VARSAYILAN
    assert depo.parametreler is not VARSAYILAN
    with pytest.raises(KeyError):
        depo.torna_isi("yok")
    with pytest.raises(KeyError):
        depo.montaj("yok")
