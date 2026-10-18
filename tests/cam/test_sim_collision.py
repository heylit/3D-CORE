"""SPEC 05 K10–K12 — hızlı harekette çarpma, sap ve tutucu çarpışması, gövde basamakları.

Testler SPEC 05 "Çarpışma ve çakma denetimleri" bölümünden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 05):
- Hızlı çarpma: G0 adımı bir hücrede tol'dan uzun malzeme kaldırırsa; depth = hücre başına en büyük alçalma.
- Gövde: basamak j (d ≤ ρ_j için uca göre H_j); e_B(q) = min_j [H_j + min{z(t) : d(t) ≤ ρ_j}];
  çarpma z_önce(q) − e_B(q) > tol. Sap: (shank/2, L_f). Tutucu: stickout + ζ_alt, dilim yarıçapı büyük uç.
- Aynı (kind, k) için tek kayıt (en büyük depth).
"""

from __future__ import annotations

import pytest

from cam.model import Stock, Tool, ToolHolder, ToolKind
from cam.sim import body_steps, simulate
from tests.cam.simref import G0, G1, flat, path


def _kayitlar(res, kind: str):
    return [c for c in res.collisions if c.kind == kind]


def _tek_kayit_kurali(res):
    anahtarlar = [(c.kind, c.k) for c in res.collisions]
    assert len(anahtarlar) == len(set(anahtarlar))
    assert [c.k for c in res.collisions] == sorted(c.k for c in res.collisions)
    for c in res.collisions:
        assert c.kind in {"hizli_carpma", "sap_carpma", "tutucu_carpma", "cakma"}
        assert c.op == res.steps[c.k - 1].op


# ------------------------------------------------------------------ K10 hızlı çarpma

STOK = Stock(0.0, 0.0, -10.0, 40.0, 20.0, 0.0)


def test_K10_stoktan_gecen_g0():
    """z = −3'te stoğu boydan geçen G0: geçilen malzeme kalınlığı zmax − (−3) = 3."""
    tool = flat(D=6.0, Lf=20.0)
    yol = path(tool, (-10.0, 10.0, -3.0), [G0(50.0, 10.0, -3.0)])
    res = simulate([yol], STOK, cell=1.0)
    k = _kayitlar(res, "hizli_carpma")
    assert len(k) == 1
    assert k[0].k == 1 and k[0].op == 0
    assert k[0].depth == pytest.approx(3.0, abs=1e-9)
    x, y, z = k[0].at
    assert 0.0 <= x <= 40.0 and abs(y - 10.0) <= 3.0
    assert z == pytest.approx(-3.0, abs=1e-9)
    assert res.collisions == k  # gövde L_f = 20 > 3: sap çarpması yok
    # malzeme yine kaldırılır
    assert res.zmap.z.min() == pytest.approx(-3.0, abs=1e-12)
    _tek_kayit_kurali(res)


def test_K10_stok_ustunden_g0():
    tool = flat(D=6.0, Lf=20.0)
    yol = path(tool, (-10.0, 10.0, 0.0), [G0(50.0, 10.0, 0.0), G0(50.0, 10.0, 5.0)])
    res = simulate([yol], STOK, cell=1.0)
    assert res.collisions == []
    assert res.removed_volume == 0.0


def test_K10_baglanti_malzemeden_geciyor():
    """Yol 0 stok dışında (x = −10) z = −3'te biter; yol 1 x = 50'de başlar: araya eklenen G0 bağlantısı
    stoğu geçer → bağlantı adımında (link = True, op = 1) hızlı çarpma."""
    tool = flat(D=6.0, Lf=20.0)
    y0 = path(tool, (-10.0, 10.0, 5.0), [G1(-10.0, 10.0, -3.0)], "a")
    y1 = path(tool, (50.0, 10.0, -3.0), [G1(50.0, 10.0, 5.0)], "b")
    res = simulate([y0, y1], STOK, cell=1.0)
    assert len(res.steps) == 3
    bag = res.steps[1]
    assert bag.link and bag.k == 2 and bag.op == 1
    k = _kayitlar(res, "hizli_carpma")
    assert len(k) == 1
    assert (k[0].k, k[0].op) == (2, 1)
    assert k[0].depth == pytest.approx(3.0, abs=1e-9)
    _tek_kayit_kurali(res)


def test_K10_tol_altinda_kayit_yok():
    """Kaldırılan boy ≤ tol → kayıt yok (tol = 1e-6)."""
    tool = flat(D=6.0, Lf=20.0)
    yol = path(tool, (-10.0, 10.0, -5e-7), [G0(50.0, 10.0, -5e-7)])
    res = simulate([yol], STOK, cell=1.0)
    assert _kayitlar(res, "hizli_carpma") == []


# ------------------------------------------------------------------ K11 sap

S_STOK = Stock(0.0, 0.0, -20.0, 40.0, 20.0, 0.0)


def _yandan_kanal(tool: Tool, z: float):
    """Stok dışında z'ye in, yandan girip boydan geç, stok dışında çık. Kanal y = 10."""
    return path(tool, (-10.0, 10.0, 5.0), [G1(-10.0, 10.0, z), G1(50.0, 10.0, z), G1(50.0, 10.0, 5.0)])


def test_K11_15mm_kanal_sap_carpar():
    """L_f = 10, kanal 15 mm: sap tabanı uçtan 10 yukarıda (z = −5), üstteki 5 mm'ye batar."""
    tool = flat(D=6.0, Lf=10.0)
    res = simulate([_yandan_kanal(tool, -15.0)], S_STOK, cell=1.0)
    k = _kayitlar(res, "sap_carpma")
    assert len(k) == 1
    assert k[0].k == 2
    assert k[0].depth == pytest.approx(5.0, abs=1e-9)
    assert k[0].at[2] == pytest.approx(-5.0, abs=1e-9)  # orada gövde yüzeyinin Z'si
    assert _kayitlar(res, "tutucu_carpma") == []
    _tek_kayit_kurali(res)


def test_K11_8mm_kanal_kayit_yok():
    tool = flat(D=6.0, Lf=10.0)
    res = simulate([_yandan_kanal(tool, -8.0)], S_STOK, cell=1.0)
    assert res.collisions == []


@pytest.mark.parametrize("shank", [None, 6.0, 5.0])
def test_K11_sap_ince_dalma_kayit_yok(shank):
    """Sap çapı ≤ D: 15 mm dalmada kesici yolu açar, sap çarpması yok."""
    tool = flat(D=6.0, Lf=10.0, shank_d=shank)
    yol = path(tool, (20.0, 10.0, 5.0), [G1(20.0, 10.0, -15.0, F=100.0), G1(20.0, 10.0, 5.0)])
    res = simulate([yol], S_STOK, cell=0.5)
    assert res.collisions == []
    assert res.zmap.z.min() == -15.0


def test_K11_genis_sap_yuksek_duvar():
    """Uzun takım y ∈ [0, 6] şeridini z = −12'ye indirir (y > 6 duvar, üstü 0). Geniş saplı (ρ = 5) kısa
    takım aynı şeritte 2 mm'lik sığ paso alır (z = −14): kesici yalnız tabana değer, sap tabanı z = −4'te
    y ∈ (6, 8] duvarına 4 mm batar."""
    uzun = Tool(1, "uzun", ToolKind.FLAT, 6.0, 40.0)
    genis = Tool(2, "genis_sap", ToolKind.FLAT, 6.0, 10.0, shank_d=10.0)
    y0 = path(uzun, (-10.0, 3.0, 5.0), [G1(-10.0, 3.0, -12.0), G1(50.0, 3.0, -12.0), G1(50.0, 3.0, 5.0)], "a")
    y1 = path(
        genis, (-10.0, 3.0, 5.0), [G1(-10.0, 3.0, -14.0), G1(50.0, 3.0, -14.0), G1(50.0, 3.0, 5.0)], "b"
    )
    res = simulate([y0, y1], S_STOK, cell=1.0)
    k = _kayitlar(res, "sap_carpma")
    assert len(k) == 1
    assert k[0].op == 1
    assert res.steps[k[0].k - 1].end == (50.0, 3.0, -14.0)
    assert k[0].depth == pytest.approx(4.0, abs=1e-9)
    assert 6.0 < k[0].at[1] <= 8.0
    _tek_kayit_kurali(res)


def test_K11_genis_sap_duvarsiz_kayit_yok():
    """Aynı sığ paso düz stokta: sap tabanı stok üstünün üstünde (−2 + 10 > 0)."""
    genis = Tool(2, "genis_sap", ToolKind.FLAT, 6.0, 10.0, shank_d=10.0)
    res = simulate([_yandan_kanal(genis, -2.0)], S_STOK, cell=1.0)
    assert res.collisions == []


# ------------------------------------------------------------------ K12 tutucu

T_STOK = Stock(0.0, 0.0, -30.0, 40.0, 30.0, 0.0)


def _silindir_tutucu() -> ToolHolder:
    return ToolHolder("silindir", gauge_length=60.0, profile=((0.0, 15.0), (50.0, 15.0)))


def _duvar_programi(tutuculu: bool):
    """Uzun takım y ∈ [0, 6] şeridini z = −25'e indirir. İkinci takım (L_f = 10, stickout 20, tutucu R 15)
    aynı şeritte aynı derinlikte kontur geçer: kesici ve sap tabana değer, tutucu tabanı z = −25 + 20 = −5'te
    y ≤ 18 duvarına (üstü 0) 5 mm batar. İniş ve çıkış stoktan 30 mm uzakta (tutucu stoğa değmez)."""
    uzun = Tool(1, "uzun", ToolKind.FLAT, 6.0, 40.0)
    if tutuculu:
        t2 = Tool(2, "tutuculu", ToolKind.FLAT, 6.0, 10.0, stickout=20.0, holder=_silindir_tutucu())
    else:
        t2 = Tool(2, "tutucusuz", ToolKind.FLAT, 6.0, 10.0)
    y0 = path(uzun, (-10.0, 3.0, 5.0), [G1(-10.0, 3.0, -25.0), G1(50.0, 3.0, -25.0), G1(50.0, 3.0, 5.0)], "a")
    y1 = path(t2, (-30.0, 3.0, 5.0), [G1(-30.0, 3.0, -25.0), G1(70.0, 3.0, -25.0), G1(70.0, 3.0, 5.0)], "b")
    return [y0, y1]


def test_K12_tutucu_carpar():
    res = simulate(_duvar_programi(True), T_STOK, cell=1.0)
    k = _kayitlar(res, "tutucu_carpma")
    assert len(k) == 1
    assert k[0].op == 1
    assert res.steps[k[0].k - 1].end == (70.0, 3.0, -25.0)
    assert k[0].depth == pytest.approx(5.0, abs=1e-9)
    assert k[0].at[2] == pytest.approx(-5.0, abs=1e-9)
    assert _kayitlar(res, "sap_carpma") == []
    _tek_kayit_kurali(res)


def test_K12_tutucusuz_kayit_yok():
    res = simulate(_duvar_programi(False), T_STOK, cell=1.0)
    assert res.collisions == []


# ------------------------------------------------------------------ body_steps


def test_body_steps_yalniz_sap():
    ((rho, H, tur),) = body_steps(flat(D=6.0, Lf=10.0))
    assert (rho, H, tur) == (pytest.approx(3.0), pytest.approx(10.0), "sap")
    t = Tool(1, "t", ToolKind.FLAT, 6.0, 12.0, shank_d=8.0)
    ((rho, H, tur),) = body_steps(t)
    assert (rho, H, tur) == (pytest.approx(4.0), pytest.approx(12.0), "sap")


def test_body_steps_stickout_yoksa_tutucu_yok():
    """Tutucu ancak holder ve stickout birlikte verilirse gövdeye girer."""
    t = Tool(1, "t", ToolKind.FLAT, 6.0, 10.0, holder=_silindir_tutucu())
    assert [s[2] for s in body_steps(t)] == ["sap"]


def test_body_steps_silindir_tutucu():
    """Silindir tutucu: tüm dilimler aynı yarıçap → en alçak dilim dışındakiler gölgede."""
    t = Tool(2, "t", ToolKind.FLAT, 6.0, 10.0, stickout=20.0, holder=_silindir_tutucu())
    adimlar = body_steps(t)
    assert len(adimlar) == 2
    assert adimlar[0] == (pytest.approx(3.0), pytest.approx(10.0), "sap")
    assert adimlar[1] == (pytest.approx(15.0), pytest.approx(20.0), "tutucu")


KONIK = ((0.0, 8.0), (10.0, 20.0), (30.0, 20.0), (40.0, 12.0))  # genişleyen koni, silindir, daralan koni


def _r_profil(zeta: float) -> float:
    """Profilin ζ'daki yarıçapı (parça parça doğrusal)."""
    for (z0, r0), (z1, r1) in zip(KONIK[:-1], KONIK[1:], strict=True):
        if z0 <= zeta <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (zeta - z0) / (z1 - z0)
    raise ValueError(zeta)


@pytest.mark.parametrize("dz", [1.0, 0.7, 2.5])
def test_body_steps_konik_tutucu(dz):
    stickout = 25.0
    t = Tool(2, "t", ToolKind.FLAT, 6.0, 10.0, stickout=stickout, holder=ToolHolder("konik", 60.0, KONIK))
    adimlar = body_steps(t, dz=dz)
    assert adimlar[0] == (pytest.approx(3.0), pytest.approx(10.0), "sap")
    tut = [a for a in adimlar if a[2] == "tutucu"]
    assert [a[2] for a in adimlar] == ["sap"] + ["tutucu"] * len(tut)
    rho = [a[0] for a in adimlar]
    H = [a[1] for a in adimlar]
    assert all(b > a for a, b in zip(rho, rho[1:], strict=False)), "ρ kesin artan"
    assert all(b > a for a, b in zip(H, H[1:], strict=False)), "H kesin artan"
    # ilk tutucu dilimi ağızda; ardışık H farkı ≤ dz; genişleyen koni ζ ∈ [0, 10] boyunca dilimleniyor
    assert tut[0][1] == pytest.approx(stickout, abs=1e-12)
    assert len(tut) >= 10 / dz - 1e-9
    for a, b in zip(tut, tut[1:], strict=False):
        assert b[1] - a[1] <= dz + 1e-12
    # dilim yarıçapı dilimdeki büyük uç: dilim [H_j, H_j+1] → ρ_j = r(ζ_üst) (genişleyen koni)
    for a, b in zip(tut, tut[1:], strict=False):
        assert a[0] == pytest.approx(_r_profil(b[1] - stickout), abs=1e-12)
    assert tut[-1][0] == pytest.approx(20.0, abs=1e-12)
    assert tut[-1][1] - stickout >= 10.0 - dz - 1e-12
    # silindir ve daralan bölümün dilimleri (ζ ≥ 10, yarıçap ≤ 20) gölgede: atılmış
    assert all(a[1] - stickout < 10.0 - 1e-12 for a in tut)
