"""SPEC 14 — kesme verisinden devir ve ilerleme: K1 (freze), K2 (etkin çap), K3 (torna, talaş debisi).

Testler sadece SPEC 14 metninden yazıldı; `cam/cutting.py` uygulama kodu okunmadı.

Beklenen değerler (SPEC 14 Teori "Kesme verisinden devir ve ilerleme", "Torna"):
- n = 1000·Vc / (π·D), önce floor(x + 0.5) ile tam sayıya, sonra min(n, n_max); F = n·z·fz.
- Vc = 200, D = 10, z = 3, fz = 0.05 → n = 6366, F = 954.9; n_max = 6000 → 6000, 900, Vc = 188.4955592…
- D_eff = D − 2r + 2·sqrt(r² − (r − ap)²) (ap < r), aksi D.
- Torna Vc = 180, D = 50, fn = 0.2 → n = 1146, F = 229.2; ap = 2 → Q = 72.
"""

from __future__ import annotations

import math

import pytest

from cam.cutting import (
    SpindleFeed,
    css,
    cutting_for,
    cutting_speed,
    effective_diameter,
    milling,
    mrr_milling,
    mrr_turning,
    spindle_speed,
    turning,
)
from cam.model import CamError, CuttingData, LatheTool, LatheToolKind, Tool, ToolKind

REL = 1e-12
NAN = float("nan")
INF = float("inf")

# 1000·100 / (π·D) bu D için tam 1002.5 çıkar (farklı işlem sıraları dahil, kayan nokta olarak birebir).
# Bankacı yuvarlaması 1002, SPEC'in floor(x + 0.5) kuralı 1003 verir.
D_YARIM = 31.751609594393088
VC_YARIM = 100.0
N_YARIM = 1002.5


def freze10(flutes: int | None = 3) -> Tool:
    celik = {"celik": CuttingData(Vc=200.0, fz=0.05)}
    return Tool(1, "freze10", ToolKind.FLAT, D=10.0, flute_length=25.0, flutes=flutes, cutting=celik)


def kuresel10() -> Tool:
    return Tool(
        2,
        "kuresel10",
        ToolKind.BALL,
        D=10.0,
        flute_length=20.0,
        flutes=2,
        cutting={"celik": CuttingData(Vc=200.0, fz=0.05)},
    )


def radyuslu10() -> Tool:
    return Tool(3, "radyuslu10", ToolKind.FLAT, D=10.0, flute_length=20.0, corner_r=2.0, flutes=4)


def torna_ucu() -> LatheTool:
    return LatheTool(
        10,
        "tornalama",
        LatheToolKind.TURN,
        nose_r=0.8,
        tip=3,
        kappa_r=95.0,
        eps_r=80.0,
        cutting={"celik": CuttingData(Vc=180.0, fn=0.2), "yarim": CuttingData(Vc=VC_YARIM, fn=0.1)},
    )


# ---------------------------------------------------------------- K1 temel formüller


def test_spindle_speed_yuvarlanmamis():
    assert spindle_speed(200.0, 10.0) == pytest.approx(1000 * 200 / (math.pi * 10), rel=REL)
    assert spindle_speed(200.0, 10.0) == pytest.approx(6366.197723675814, rel=REL)


def test_cutting_speed():
    assert cutting_speed(6000, 10.0) == pytest.approx(188.4955592153876, rel=REL)
    assert cutting_speed(6366, 10.0) == pytest.approx(math.pi * 10 * 6366 / 1000, rel=REL)


@pytest.mark.parametrize(("Vc", "D"), [(0.0, 10.0), (-200.0, 10.0), (200.0, 0.0), (200.0, -10.0)])
def test_spindle_speed_pozitif_olmali(Vc, D):
    with pytest.raises(CamError):
        spindle_speed(Vc, D)


@pytest.mark.parametrize(("Vc", "D"), [(NAN, 10.0), (200.0, NAN), (INF, 10.0), (200.0, INF)])
def test_spindle_speed_sonlu_olmali(Vc, D):
    with pytest.raises(CamError):
        spindle_speed(Vc, D)


@pytest.mark.parametrize(("n", "D"), [(NAN, 10.0), (6000.0, NAN), (INF, 10.0)])
def test_cutting_speed_sonlu_olmali(n, D):
    with pytest.raises(CamError):
        cutting_speed(n, D)


# ---------------------------------------------------------------- K1 freze


def test_milling_teori_ornegi():
    sf = milling(freze10(), "celik")
    assert isinstance(sf, SpindleFeed)
    assert sf.n == 6366
    assert isinstance(sf.n, int)
    assert sf.F == pytest.approx(954.9, rel=REL)
    assert sf.F == pytest.approx(6366 * 3 * 0.05, rel=REL)
    assert sf.Vc == pytest.approx(math.pi * 10 * 6366 / 1000, rel=REL)
    assert sf.f == pytest.approx(0.05, rel=REL)


def test_milling_devir_siniri():
    """n_max = 6000: devir sınıra iner, ilerleme yuvarlanmış devirden orantılı düşer."""
    sf = milling(freze10(), "celik", n_max=6000)
    assert sf.n == 6000
    assert isinstance(sf.n, int)
    assert sf.F == pytest.approx(900.0, rel=REL)
    assert sf.Vc == pytest.approx(188.4955592153876, rel=REL)
    assert sf.f == pytest.approx(0.05, rel=REL)


def test_milling_sinir_ustu_n_max_etkisiz():
    sf = milling(freze10(), "celik", n_max=8000)
    assert sf.n == 6366
    assert sf.F == pytest.approx(954.9, rel=REL)


def test_yuvarlama_yarim_yukari():
    """x.5 yukarı yuvarlanır (floor(x + 0.5)); Python round() bankacı yuvarlaması 1002 verirdi."""
    assert spindle_speed(VC_YARIM, D_YARIM) == N_YARIM  # ön koşul: girdi tam .5
    yarim = {"yarim": CuttingData(Vc=VC_YARIM, fz=0.01)}
    tool = Tool(4, "yarim", ToolKind.FLAT, D=D_YARIM, flute_length=30.0, flutes=2, cutting=yarim)
    sf = milling(tool, "yarim")
    assert sf.n == 1003
    assert sf.F == pytest.approx(1003 * 2 * 0.01, rel=REL)


def test_milling_dis_sayisi_yoksa_hata():
    with pytest.raises(CamError):
        milling(freze10(flutes=None), "celik")


def test_milling_malzeme_yoksa_hata():
    with pytest.raises(CamError):
        milling(freze10(), "titanyum")


@pytest.mark.parametrize("n_max", [0.0, -6000.0, NAN, INF])
def test_milling_n_max_gecersiz(n_max):
    with pytest.raises(CamError):
        milling(freze10(), "celik", n_max=n_max)


# ---------------------------------------------------------------- cutting_for


def test_cutting_for_kaydi_dondurur():
    tool = freze10()
    assert cutting_for(tool, "celik") == CuttingData(Vc=200.0, fz=0.05)
    lt = torna_ucu()
    assert cutting_for(lt, "celik") == CuttingData(Vc=180.0, fn=0.2)


def test_cutting_for_yoksa_hata_mesajda_takim_ve_malzeme():
    with pytest.raises(CamError) as e:
        cutting_for(freze10(), "titanyum")
    assert "freze10" in str(e.value)
    assert "titanyum" in str(e.value)
    with pytest.raises(CamError) as e:
        cutting_for(torna_ucu(), "pirinc")
    assert "tornalama" in str(e.value)
    assert "pirinc" in str(e.value)


# ---------------------------------------------------------------- K2 etkin çap


def test_effective_diameter_kuresel():
    assert effective_diameter(kuresel10(), 1.0) == pytest.approx(6.0, rel=REL)
    # küresel uç formülü 2·sqrt(ap·(D − ap))
    assert effective_diameter(kuresel10(), 2.0) == pytest.approx(2 * math.sqrt(2 * 8), rel=REL)


def test_effective_diameter_kose_radyuslu():
    assert effective_diameter(radyuslu10(), 1.0) == pytest.approx(6 + 2 * math.sqrt(3), rel=REL)


@pytest.mark.parametrize("ap", [2.0, 3.0, 10.0])
def test_effective_diameter_ap_r_den_buyuk_esit_D(ap):
    """r = 2: ap ≥ r → D_eff = D."""
    assert effective_diameter(radyuslu10(), ap) == pytest.approx(10.0, rel=REL)


@pytest.mark.parametrize("ap", [5.0, 7.0])
def test_effective_diameter_kuresel_ap_r_den_buyuk_esit_D(ap):
    assert effective_diameter(kuresel10(), ap) == pytest.approx(10.0, rel=REL)


@pytest.mark.parametrize("ap", [0.1, 1.0, 5.0])
def test_effective_diameter_duz_uc_D(ap):
    assert effective_diameter(freze10(), ap) == pytest.approx(10.0, rel=REL)


@pytest.mark.parametrize("ap", [0.0, -1.0, NAN, INF])
def test_effective_diameter_ap_gecersiz(ap):
    with pytest.raises(CamError):
        effective_diameter(kuresel10(), ap)


def test_milling_ap_ile_etkin_cap():
    """Küresel D = 10, ap = 1 → D_eff = 6: n = round(1000·200 / (π·6)) = 10610."""
    sf = milling(kuresel10(), "celik", ap=1.0)
    n = math.floor(1000 * 200 / (math.pi * 6) + 0.5)
    assert n == 10610
    assert sf.n == n
    assert sf.F == pytest.approx(n * 2 * 0.05, rel=REL)


def test_milling_ap_yoksa_tam_cap():
    sf = milling(kuresel10(), "celik")
    assert sf.n == 6366
    assert sf.F == pytest.approx(6366 * 2 * 0.05, rel=REL)


def test_milling_ap_ve_n_max():
    sf = milling(kuresel10(), "celik", n_max=8000, ap=1.0)
    assert sf.n == 8000
    assert sf.F == pytest.approx(8000 * 2 * 0.05, rel=REL)


# ---------------------------------------------------------------- K3 torna


def test_turning_teori_ornegi():
    sf = turning(torna_ucu(), "celik", D=50.0)
    assert sf.n == 1146
    assert isinstance(sf.n, int)
    assert sf.F == pytest.approx(229.2, rel=REL)
    assert sf.Vc == pytest.approx(math.pi * 50 * 1146 / 1000, rel=REL)
    assert sf.f == pytest.approx(0.2, rel=REL)


def test_turning_devir_siniri():
    sf = turning(torna_ucu(), "celik", D=50.0, n_max=1000)
    assert sf.n == 1000
    assert sf.F == pytest.approx(200.0, rel=REL)
    assert sf.Vc == pytest.approx(math.pi * 50 * 1000 / 1000, rel=REL)


def test_turning_yuvarlama_yarim_yukari():
    sf = turning(torna_ucu(), "yarim", D=D_YARIM)
    assert sf.n == 1003
    assert sf.F == pytest.approx(100.3, rel=REL)


@pytest.mark.parametrize("D", [0.0, -50.0, NAN, INF])
def test_turning_cap_gecersiz(D):
    with pytest.raises(CamError):
        turning(torna_ucu(), "celik", D=D)


@pytest.mark.parametrize("n_max", [0.0, -1000.0, NAN])
def test_turning_n_max_gecersiz(n_max):
    with pytest.raises(CamError):
        turning(torna_ucu(), "celik", D=50.0, n_max=n_max)


def test_turning_malzeme_yoksa_hata():
    with pytest.raises(CamError):
        turning(torna_ucu(), "titanyum", D=50.0)


def test_css_degerleri():
    Vc, n_max = css(torna_ucu(), "celik", n_max=3000)
    assert Vc == pytest.approx(180.0, rel=REL)
    assert n_max == 3000
    assert isinstance(n_max, int)


@pytest.mark.parametrize("n_max", [None, 0, -3000, NAN])
def test_css_n_max_zorunlu(n_max):
    """G96'da devir üst sınırı (G50) yoksa küçük çapta devir sınırsız artar: sessiz tehlike."""
    with pytest.raises(CamError):
        css(torna_ucu(), "celik", n_max=n_max)


def test_css_malzeme_yoksa_hata():
    with pytest.raises(CamError):
        css(torna_ucu(), "titanyum", n_max=3000)


# ---------------------------------------------------------------- K3 talaş debisi


def test_mrr_milling():
    assert mrr_milling(2.0, 5.0, 954.9) == pytest.approx(9.549, rel=REL)


def test_mrr_turning():
    assert mrr_turning(180.0, 2.0, 0.2) == pytest.approx(72.0, rel=REL)


@pytest.mark.parametrize("args", [(NAN, 5.0, 954.9), (2.0, INF, 954.9), (2.0, 5.0, NAN)])
def test_mrr_milling_sonlu_olmali(args):
    with pytest.raises(CamError):
        mrr_milling(*args)


@pytest.mark.parametrize("args", [(NAN, 2.0, 0.2), (180.0, NAN, 0.2), (180.0, 2.0, INF)])
def test_mrr_turning_sonlu_olmali(args):
    with pytest.raises(CamError):
        mrr_turning(*args)
