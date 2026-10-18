"""
Çözücünün mekanizma (tekil K_ff) kararı model boyundan bağımsız olmalı
(inceleme bulgusu Y3: koşul sayısı mekanizma dedektörü değildir).
"""

from __future__ import annotations

import pytest

from core.model import BC, Element, Load, Material, Model, ModelError, Node, Section
from core.solver import solve
from tests.conftest import STEEL_E

E_YUMUSAK = 1e-6  # MPa: çok yumuşak ama sıfırdan büyük; model fiziksel olarak geçerli


def _yumusak_halkali_cubuk(n_elem: int, L_e: float = 1.0, A: float = 1.0, F: float = 10.0) -> Model:
    """Sol ucu ankastre çelik çubuk; ortadaki tek eleman çok yumuşak, uçtan F çekiliyor."""
    orta = n_elem // 2 + 1
    return Model(
        dim=1,
        nodes=[Node(i + 1, L_e * i) for i in range(n_elem + 1)],
        elements=[
            Element(i, "bar1d", [i, i + 1], "yumusak" if i == orta else "celik", "s1")
            for i in range(1, n_elem + 1)
        ],
        materials=[Material("celik", STEEL_E), Material("yumusak", E_YUMUSAK)],
        sections=[Section("s1", A)],
        bcs=[BC(1, "ux", 0.0)],
        loads=[Load(n_elem + 1, "ux", F)],
    )


@pytest.mark.parametrize("n_elem", [10, 1500, 3000])
def test_soft_element_solves_at_any_size(n_elem):
    """Seri yaylar: δ = F Σ L_i / (E_i A). Karar 1500 ve 3000 düğümde aynı olmalı."""
    L_e, A, F = 1.0, 1.0, 10.0
    m = _yumusak_halkali_cubuk(n_elem, L_e, A, F)
    beklenen = F * ((n_elem - 1) * L_e / (STEEL_E * A) + L_e / (E_YUMUSAK * A))
    r = solve(m)
    # Birleştirilmiş K'da k_yumusak, köşegende k_celik + k_yumusak toplamı içinde
    # saklanır: göreli kesinliği eps·k_celik/k_yumusak ≈ 5e-5. Daha sıkı tolerans
    # hiçbir çözücüyle tutturulamaz.
    assert r.displacement(m, n_elem + 1) == pytest.approx(beklenen, rel=1e-3)


def _kopuk_cubuk(n_elem: int) -> Model:
    """İki parça: sol parça ankastre, sağ parça hiçbir yere bağlı değil (mekanizma)."""
    kopuk = n_elem // 2  # bu eleman yok: düğüm kopuk ile kopuk+1 arası boş
    elemanlar = [Element(i, "bar1d", [i, i + 1], "celik", "s1") for i in range(1, n_elem + 1) if i != kopuk]
    return Model(
        dim=1,
        nodes=[Node(i + 1, float(i)) for i in range(n_elem + 1)],
        elements=elemanlar,
        materials=[Material("celik", STEEL_E)],
        sections=[Section("s1", 1.0)],
        bcs=[BC(1, "ux", 0.0)],
        loads=[Load(n_elem + 1, "ux", 10.0)],
    )


@pytest.mark.parametrize("n_elem", [4, 1500, 3000])
def test_disconnected_part_raises_at_any_size(n_elem):
    with pytest.raises(ModelError):
        solve(_kopuk_cubuk(n_elem))


@pytest.mark.parametrize("n_elem", [3, 3000])
def test_unsupported_bar_raises_at_any_size(n_elem):
    """Mesnetsiz ve yüksüz çubuk: sağ taraf sıfır olsa da mekanizma -> ModelError."""
    m = Model(
        dim=1,
        nodes=[Node(i + 1, float(i)) for i in range(n_elem + 1)],
        elements=[Element(i, "bar1d", [i, i + 1], "celik", "s1") for i in range(1, n_elem + 1)],
        materials=[Material("celik", STEEL_E)],
        sections=[Section("s1", 1.0)],
    )
    with pytest.raises(ModelError):
        solve(m)
