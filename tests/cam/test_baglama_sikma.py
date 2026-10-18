"""SPEC 10 — K5 sıkma denetimi (`check_clamping`), analitik (kütüphane elemanları, OCCT'siz).

Testler sadece SPEC 10 metninden yazıldı; `cam/baglama.py` uygulama kodu okunmadı.
Kural (Teori, "Bağlama denetimi"): bağlama elemanı stoğa değebilir ama içine giremez; ilkel ile stok kutusunun
iç kısımları kesişirse (her eksende açık aralık örtüşmesi > tol_l = 1e-9) CamError, mesajda bağlama adı.
Yerleşimler K2–K4 Teori örnekleri: Stock(0, 0, 0, 80, 50, 30).
"""

from __future__ import annotations

import pytest

from cam.model import CamError, CylinderStock, Stock
from tests.cam.baglama_ara import Clamp, check_clamping, chuck_for, clamp_for, make_fixture, vise_for
from tests.cam.baglama_ref import (
    CHUCK_GRIP,
    CHUCK_OLCU,
    CHUCK_STOK,
    CLAMP_OLCU,
    STOK,
    VISE_GRIP,
    VISE_OLCU,
    Rz,
    frame,
)


def mengene(dy: float = 0.0, ad: str = "mengene_A"):
    v, fr = vise_for(STOK, VISE_GRIP, "x", **VISE_OLCU)
    o = fr.origin
    return make_fixture(ad, v, frame((o[0], o[1] + dy, o[2]), fr.R))


def pabuc(side: str = "y-", at: float = 40.0, dz: float = 0.0, ad: str = "pabuc_B"):
    c, fr = clamp_for(STOK, side, at, 8.0, **CLAMP_OLCU)
    o = fr.origin
    return make_fixture(ad, c, frame((o[0], o[1], o[2] + dz), fr.R))


def test_k5_mengene_degen_yuzler_gecer():
    # çeneler stoğun y = 0 ve y = 50 yüzlerine, paraleller z = 0 tabanına değer: iç kesişim yok
    assert check_clamping(STOK, [mengene()]) is None


@pytest.mark.parametrize(("side", "at"), [("y-", 40.0), ("y+", 40.0), ("x-", 25.0), ("x+", 25.0)])
def test_k5_pabuc_degen_yuz_gecer(side, at):
    # kol altı stok üstüne (z = 30) değer; cıvata ve topuk stok dışında
    assert check_clamping(STOK, [pabuc(side, at)]) is None


def test_k5_mengene_ve_iki_pabuc_birlikte_gecer():
    fx = [mengene(), pabuc("x-", 25.0, ad="p1"), pabuc("x+", 25.0, ad="p2")]
    assert check_clamping(STOK, fx) is None


def test_k5_mengene_1mm_iceri_hata():
    # çerçeve +Y'de 1 mm: sabit çene y ∈ [−19, 1], stokla 1 mm örtüşür
    with pytest.raises(CamError, match="mengene_A"):
        check_clamping(STOK, [mengene(dy=1.0)])


def test_k5_mengene_1mm_eksi_y_hata():
    # −Y'de 1 mm: sabit çene stoktan ayrılır, hareketli çene y ∈ [49, 69] stoğa 1 mm girer
    with pytest.raises(CamError, match="mengene_A"):
        check_clamping(STOK, [mengene(dy=-1.0)])


def test_k5_tolerans_siniri():
    # örtüşme 1e-6 > tol_l = 1e-9 → hata; 1e-10 < tol_l → geçer
    with pytest.raises(CamError, match="mengene_A"):
        check_clamping(STOK, [mengene(dy=1e-6)])
    assert check_clamping(STOK, [mengene(dy=1e-10)]) is None


def test_k5_pabuc_1mm_asagi_hata():
    # burun z'si 1 mm aşağı: kol z ∈ [29, 41], stok üst 1 mm'sine girer
    with pytest.raises(CamError, match="pabuc_B"):
        check_clamping(STOK, [pabuc(dz=-1.0)])


def test_k5_ikinci_eleman_ihlali_adiyla():
    # ilk eleman temiz, ikincisi ihlalde: mesajda ikinci elemanın adı
    with pytest.raises(CamError, match="pabuc_ikinci"):
        check_clamping(STOK, [mengene(), pabuc(dz=-1.0, ad="pabuc_ikinci")])


def test_k5_civata_stoga_giriyor_hata():
    # elle konmuş pabuç: R_z(90°), burun (40, 40, 30) → cıvata ekseni (40, 40 − L_a/2) = (40, 0), yarıçap 6:
    # cıvata y ∈ [−6, 6], z ∈ [0, 57] stoğa girer; kol (z ∈ [30, 42]) yalnız değer,
    # topuk y ∈ [−40, −25] dışarıda
    c = Clamp(support_height=30.0, **CLAMP_OLCU)
    fx = make_fixture("pabuc_civata", c, frame((40.0, 40.0, 30.0), Rz(90)))
    with pytest.raises(CamError, match="pabuc_civata"):
        check_clamping(STOK, [fx])


def test_k5_elle_konmus_pabuc_gecer():
    # Teori yerleşiminin elle kurulmuşu: burun (40, 8, 30), cıvata ekseni (40, −32) stok dışında
    c = Clamp(support_height=30.0, **CLAMP_OLCU)
    fx = make_fixture("pabuc_ok", c, frame((40.0, 8.0, 30.0), Rz(90)))
    assert check_clamping(STOK, [fx]) is None


def test_k5_civata_stok_disina_teget_gecer():
    # cıvata ekseni (40, −6): disk y ∈ [−12, 0], stok yüzü y = 0'a teğet → uzaklık 6 = r, iç kesişim yok.
    # Burun (40, 34, 30): kol y ∈ [−46, 34] stok üstüne değer.
    c = Clamp(support_height=30.0, **CLAMP_OLCU)
    fx = make_fixture("pabuc_teget", c, frame((40.0, 34.0, 30.0), Rz(90)))
    assert check_clamping(STOK, [fx]) is None


def test_k5_ayna_silindir_stok_gecer():
    c, fr = chuck_for(CHUCK_STOK, CHUCK_GRIP, **CHUCK_OLCU)
    assert check_clamping(CHUCK_STOK, [make_fixture("ayna_C", c, fr)]) is None


def test_k5_ayna_tutma_capi_uyusmuyor_hata():
    # grip_d = 40 ama stok D = 42 → CamError (çene iç yüzü d/2'de stoğa değmeli)
    c, fr = chuck_for(CHUCK_STOK, CHUCK_GRIP, **CHUCK_OLCU)
    with pytest.raises(CamError, match="ayna_C"):
        check_clamping(CylinderStock(42, -60, 0), [make_fixture("ayna_C", c, fr)])


def test_k5_silindir_stokta_yalniz_ayna():
    # CylinderStock ile yalnız Chuck3 desteklenir
    with pytest.raises(CamError):
        check_clamping(CHUCK_STOK, [mengene()])


def test_k5_bos_liste_gecer():
    assert check_clamping(Stock(0, 0, 0, 1, 1, 1), []) is None
