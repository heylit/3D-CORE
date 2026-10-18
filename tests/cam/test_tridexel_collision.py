"""SPEC 43 K10 — hızlı çarpma, sap ve tutucu çarpışması (tri-dexel).

Testler SPEC 43 "Çarpışma ve çakma" bölümünden yazıldı; cam.sim.simulate5 kodu okunmadı.

Kaynaklar (SPEC 43):
- hizli_carpma: G0'ın kaldırdığı en uzun ışın parçası > tol; depth o parçanın boyu.
- sap / tutucu: alt adımdan önceki malzemeyle gövde basamağının ışın kesişimi; batma = kesişim aralığının
  boyu, üç aileden en büyüğü.
Beklenen değerler:
- Stoğu X boyunca baştan sona geçen G0: süpürmenin YZ izdüşümündeki X ışınları [xmin, xmax]'ın tamamını
  kaybeder → en uzun parça = stok X boyu (Y ve Z ışınlarında parça bu boydan kısa).
- +X eksenli takım (yan kanal), eksen z_c bir hücre merkezinde: Y ışını (x, z_c) gövde ekseninden geçer,
  kirişi 2ρ; X ışınındaki parça ve Z ışınlarındaki kirişler daha kısa → batma = 2ρ.
"""

from __future__ import annotations

import pytest

from cam.model import MoveType, Stock, Tool, ToolHolder, ToolKind
from cam.sim import simulate5
from tests.cam import tridexref as tr
from tests.cam.simref import flat


def _tek_kayit(res):
    anahtar = [(c.kind, c.k) for c in res.collisions]
    assert len(anahtar) == len(set(anahtar))
    for c in res.collisions:
        assert c.kind in {"hizli_carpma", "sap_carpma", "tutucu_carpma", "cakma"}


def test_K10_egik_g0_stoktan_gecer():
    stok = Stock(0.0, 0.0, 0.0, 40.0, 30.0, 10.0)
    a = tr.unit(0.0, 0.5, 3**0.5 / 2)  # YZ düzleminde düşeyden 30°
    tool = flat(D=6.0, Lf=30.0)
    yol = tr.tilted_path(tool, a, [(-10.0, 15.0, 8.0), (50.0, 15.0, 8.0)], kinds=[MoveType.RAPID])
    res = simulate5([yol], stok, cell=1.0)
    k = [c for c in res.collisions if c.kind == "hizli_carpma"]
    assert len(k) == 1
    assert (k[0].k, k[0].op) == (1, 0)
    assert k[0].depth == pytest.approx(40.0, abs=1e-6)
    assert res.removed_volume > 0
    _tek_kayit(res)


def test_K10_g0_havada_kayit_yok():
    stok = Stock(0.0, 0.0, 0.0, 40.0, 30.0, 10.0)
    a = tr.unit(0.0, 0.5, 3**0.5 / 2)
    tool = flat(D=6.0, Lf=30.0)
    yol = tr.tilted_path(tool, a, [(-10.0, 15.0, 14.0), (50.0, 15.0, 14.0)], kinds=[MoveType.RAPID])
    res = simulate5([yol], stok, cell=1.0)
    assert res.collisions == []
    assert res.removed_volume == pytest.approx(0.0, abs=1e-12)


K_STOK = Stock(0.0, 0.0, 0.0, 40.0, 30.0, 21.0)  # hücre 1: z merkezleri k + ½, z_c = 10.5 bir merkez
ZC = 10.5


def _yan_kanal(tool: Tool, x_uc: float):
    """+X eksenli takım, uç x = x_uc'de, y = −10 → 40 boyunca z = z_c'de."""
    return tr.tilted_path(tool, (1.0, 0.0, 0.0), [(x_uc, -10.0, ZC), (x_uc, 40.0, ZC)])


def test_K10_sap_carpar():
    """L_f = 10, sap çapı 5: uç x = 26 → kesici x ∈ [26, 36], sap x ≥ 36 malzemeye (x ≤ 40) girer.
    Y ışını (x = 36.5..39.5, z = 10.5) sap ekseninden geçer: batma = 2ρ = 5 (X'te 4, Z'de ≤ 5)."""
    tool = Tool(1, "kisa", ToolKind.FLAT, 6.0, 10.0, shank_d=5.0)
    res = simulate5([_yan_kanal(tool, 26.0)], K_STOK, cell=1.0)
    k = [c for c in res.collisions if c.kind == "sap_carpma"]
    assert len(k) == 1
    assert (k[0].k, k[0].op) == (1, 0)
    assert k[0].depth == pytest.approx(5.0, abs=1e-6)
    assert [c for c in res.collisions if c.kind == "tutucu_carpma"] == []
    _tek_kayit(res)


def test_K10_sap_disarida_kayit_yok():
    """Uç x = 31 → sap x ≥ 41: stok dışında."""
    tool = Tool(1, "kisa", ToolKind.FLAT, 6.0, 10.0, shank_d=5.0)
    res = simulate5([_yan_kanal(tool, 31.0)], K_STOK, cell=1.0)
    assert [c for c in res.collisions if c.kind in ("sap_carpma", "tutucu_carpma")] == []


def test_K10_tutucu_carpar():
    """stickout 20, silindir tutucu r = 10: uç x = 18 → tutucu x ≥ 38 malzemeye girer; Y ışını eksenden geçer,
    malzeme y ∈ [0, 30] ve z ∈ [0, 21] kirişi kesmez → batma 2r = 20."""
    holder = ToolHolder("silindir", 60.0, ((0.0, 10.0), (40.0, 10.0)))
    tool = Tool(2, "tutuculu", ToolKind.FLAT, 6.0, 10.0, stickout=20.0, holder=holder)
    res = simulate5([_yan_kanal(tool, 18.0)], K_STOK, cell=1.0)
    k = [c for c in res.collisions if c.kind == "tutucu_carpma"]
    assert len(k) == 1
    assert (k[0].k, k[0].op) == (1, 0)
    assert k[0].depth == pytest.approx(20.0, abs=1e-6)
    _tek_kayit(res)
