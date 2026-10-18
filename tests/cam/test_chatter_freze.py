"""SPEC 71 — frezeleme lobu testleri (K1 freze, K5, K6, K7 K_r kısmı, K10, hatalar).

Testler yalnız SPEC 71 metninden ve iskelet arayüzünden yazıldı; cam/chatter.py gövdeleri okunmadı.
Bağımsız referans: tests/cam/chatter_ref.py (Altintas–Budak sıfırıncı mertebe).

- Yönsel katsayılar elle: tam kanal (0 → π): α_xx = α_yy = −πK_r, α_xy = −π, α_yx = π.
  Yarım daldırma karşı yön (0 → π/2): α_xx = −1 − πK_r/2, α_xy = −π/2 − K_r, α_yx = π/2 − K_r,
  α_yy = 1 − πK_r/2. Aynı yön (π/2 → π): α_xx = 1 − πK_r/2, α_xy = −π/2 + K_r, α_yx = π/2 + K_r,
  α_yy = −1 − πK_r/2.
- İzotrop G = g·I: Φ = [α] g, özdeğerler μ g (μ, [α]'nın özdeğerleri; tam kanalda π(−K_r ± i)).
  Λ = −1/λ ⇒ a_lim = 2π / (N K_t λ_R) (λ_R > 0 iken pozitif).
- Örnek: SDOF k = 2·10⁴ N/mm, ζ = 0.03, f_n = 800 Hz; Ø10, 4 ağız; K_t = 800 MPa, K_r = 0.3.

Varsayımlar (SPEC'te açık değil):
- Daldırma açıları Altintas kuralıyla: karşı yön φ_st = 0, φ_ex = acos(1 − 2ae/D); aynı yön
  φ_st = acos(2ae/D − 1), φ_ex = π. Ağız sayısı N = Tool.flutes.
- `Lob.loblar[k]` k numaralı lobdur ve iki özdeğer ailesinin noktalarını içerebilir; her nokta ailelerden
  birine uymalıdır. K6'daki 1e-9 noktasal sınanır (lob noktası (n, a) ↔ aynı n'yi veren ω_c'deki a).
- K6 "lob zarfı" ızgarada bağımsız zarfla göreli 1e-6 içinde karşılaştırılır (zarf lob eğrilerinden ara
  değerle bulunur; frekans ızgarası 0,002 Hz).
- K10: izin verilen importlar numpy, math, csv, cam.model, aynı SPEC'in cam.frf'i ve yalnız tip / veri sınıfı
  için standart kütüphane (__future__, dataclasses, typing, collections.abc).
"""

from __future__ import annotations

import ast
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from cam.chatter import FRF_GEREKLI, Lob, lob_freze, yonsel_katsayilar
from cam.frf import FRF, TakimFRF, frf_modal
from cam.model import CamError, MachineProfile, Tool, ToolKind
from tests.cam.chatter_ref import alpha, freze_n_a, match_rel, roots_a, sample_idx, sdof_g

K, ZETA, FN = 2.0e4, 0.03, 800.0
KT, KR, NZ, D = 800.0, 0.3, 4, 10.0
F_LO, F_HI = 700.0, 950.0
N_ARALIK = (3000.0, 30000.0)
ROOT = Path(__file__).resolve().parents[2]


def g(f):
    return sdof_g(f, FN, ZETA, K)


def takim() -> Tool:
    return Tool(id=1, name="freze10", kind=ToolKind.FLAT, D=D, flute_length=30.0, flutes=NZ)


def izotrop(df: float = 0.002) -> TakimFRF:
    f = np.linspace(F_LO, F_HI, int(round((F_HI - F_LO) / df)) + 1)
    frf = frf_modal([(FN, ZETA, K)], f)
    return TakimFRF(xx=frf, yy=frf)


_LOB: dict[tuple, Lob] = {}


def lob(ae: float = D, yon: str = "karsi") -> Lob:
    key = (ae, yon)
    if key not in _LOB:
        _LOB[key] = lob_freze(izotrop(), takim(), ae=ae, yon=yon, n_aralik=N_ARALIK, K_t=KT, K_r=KR)
    return _LOB[key]


def families(phi_st: float, phi_ex: float):
    """[α]'nın özdeğerleri μ_j ve her biri için lob k eğrisi üreten fonksiyon."""
    mus = np.linalg.eigvals(alpha(phi_st, phi_ex, KR))
    return [lambda k, mu=mu: lambda f: freze_n_a(f, g, complex(mu), NZ, KT, k) for mu in mus]


def finite(n, a):
    n, a = np.asarray(n, dtype=float), np.asarray(a, dtype=float)
    m = np.isfinite(n) & np.isfinite(a)
    return n[m], a[m]


# ---------------------------------------------------------------- K1: ölçüm zorunluluğu


def test_no_frf_raises_with_message():
    """K1: lob_freze(None, …) → hata, mesaj kullanıcı kararındaki metni içerir."""
    with pytest.raises(CamError) as e:
        lob_freze(None, takim(), ae=D, yon="karsi", n_aralik=N_ARALIK, K_t=KT, K_r=KR)
    assert FRF_GEREKLI in str(e.value)


def test_frf_modal_not_called_in_package():
    """K1: sessiz varsayılan FRF yok — cam/ paketinde frf_modal çağrısı yoktur (yalnız testlerde)."""
    for py in sorted((ROOT / "cam").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
                assert name != "frf_modal", f"{py.relative_to(ROOT)}:{node.lineno}"


# ---------------------------------------------------------------- K5: yönsel katsayılar


def test_alpha_full_slot():
    """K5: tam kanal (φ_st = 0, φ_ex = π): α_xx = α_yy = −πK_r, α_xy = −π, α_yx = π (abs 1e-12)."""
    for kr in (0.0, 0.3, 0.45):
        A = np.asarray(yonsel_katsayilar(0.0, math.pi, kr), dtype=float)
        exp = np.array([[-math.pi * kr, -math.pi], [math.pi, -math.pi * kr]])
        assert A.shape == (2, 2)
        assert np.allclose(A, exp, rtol=0.0, atol=1e-12)


def test_alpha_half_immersion_up_milling():
    """K5: yarım daldırma, karşı yön (0 → π/2), elle türetilmiş değerler (abs 1e-12)."""
    A = np.asarray(yonsel_katsayilar(0.0, math.pi / 2, KR), dtype=float)
    p = math.pi
    exp = np.array([[-1 - p * KR / 2, -p / 2 - KR], [p / 2 - KR, 1 - p * KR / 2]])
    assert np.allclose(A, exp, rtol=0.0, atol=1e-12)


def test_alpha_half_immersion_down_milling():
    """K5: yarım daldırma, aynı yön (π/2 → π), elle türetilmiş değerler (abs 1e-12)."""
    A = np.asarray(yonsel_katsayilar(math.pi / 2, math.pi, KR), dtype=float)
    p = math.pi
    exp = np.array([[1 - p * KR / 2, -p / 2 + KR], [p / 2 + KR, -1 - p * KR / 2]])
    assert np.allclose(A, exp, rtol=0.0, atol=1e-12)


@pytest.mark.parametrize("phi_st, phi_ex", [(0.0, 0.4), (0.3, 1.9), (2.2, math.pi), (1.0, 1.0)])
def test_alpha_general_angles(phi_st, phi_ex):
    """K5: herhangi bir aralıkta SPEC ifadeleri (üst sınır − alt sınır); boş aralıkta sıfır matris."""
    A = np.asarray(yonsel_katsayilar(phi_st, phi_ex, KR), dtype=float)
    assert np.allclose(A, alpha(phi_st, phi_ex, KR), rtol=0.0, atol=1e-12)


def test_full_slot_eigenvalues():
    """K6: tam kanal [α]'nın özdeğerleri π(−K_r ± i) ⇒ izotrop G = gI için Φ'nin özdeğerleri g·π(−K_r ± i)."""
    mus = np.sort_complex(np.linalg.eigvals(np.asarray(yonsel_katsayilar(0.0, math.pi, KR), dtype=float)))
    exp = np.sort_complex(np.array([math.pi * (-KR - 1j), math.pi * (-KR + 1j)]))
    assert np.allclose(mus, exp, rtol=0.0, atol=1e-12)


# ---------------------------------------------------------------- K6: izotrop tam kanal kapalı form


def test_lob_fields_and_coefficients():
    """Lob alanları: n artan, a_lim / gecerli aynı boyda; K_t ve K_r verilen değerler, varsayilan_Kr False."""
    lb = lob()
    n = np.asarray(lb.n, dtype=float)
    assert np.all(np.diff(n) > 0)
    assert n[0] >= N_ARALIK[0] - 1e-9 and n[-1] <= N_ARALIK[1] + 1e-9
    assert np.shape(lb.a_lim) == n.shape == np.shape(lb.gecerli)
    assert lb.K_t == KT and lb.K_r == KR
    assert lb.varsayilan_Kr is False
    assert len(lb.loblar) >= 3


def test_full_slot_lobe_points_match_closed_form():
    """K6: her lobun örnek noktaları (n, a), özdeğerlerden bağımsız türetilen a_lim(ω_c) ile
    göreli 1e-9 içinde (n'yi veren ω_c'de, iki aileden biri)."""
    fams = families(0.0, math.pi)
    for k in range(3):
        n, a = finite(*lob().loblar[k])
        assert len(n) > 10
        assert np.all(a > 0)
        keep = a < 100.0 * a.min()  # Λ_R → 0 yakınındaki çok büyük a (lob kolu) dışarıda
        n, a = n[keep], a[keep]
        curves = [fam(k) for fam in fams]
        for i in sample_idx(len(n), 25):
            assert match_rel(n[i], a[i], curves, F_LO, F_HI) <= 1e-9, (k, n[i], a[i])


def ref_envelope(n_i: float, fams, lob_sayisi: int = 10) -> float:
    """Bağımsız zarf: bütün aileler ve k = 0..lob_sayisi−1 için n'yi veren köklerde en küçük a."""
    vals = [aa for k in range(lob_sayisi) for fam in fams for aa in roots_a(n_i, fam(k), F_LO, F_HI)]
    return min(vals) if vals else math.inf


def test_full_slot_envelope_matches_reference():
    """K6: lob zarfı (geçerli ızgara noktaları) bağımsız zarfla göreli 1e-6 içinde; en küçük paso pozitif."""
    lb = lob()
    n = np.asarray(lb.n, dtype=float)
    a = np.asarray(lb.a_lim, dtype=float)
    ok = np.asarray(lb.gecerli)
    assert ok.sum() > 10
    assert np.min(a[ok]) > 0.0
    fams = families(0.0, math.pi)
    for i in np.flatnonzero(ok)[sample_idx(int(ok.sum()), 30)]:
        assert a[i] == pytest.approx(ref_envelope(float(n[i]), fams), rel=1e-6), n[i]


def test_full_slot_min_depth():
    """K6: en küçük paso, kapalı form a = 2π/(N K_t λ_R)'nin bant içindeki en küçüğüne eşit (göreli 1e-3)."""
    f = np.linspace(F_LO, F_HI, 250001)
    lam_R = np.vstack([(mu * g(f)).real for mu in np.linalg.eigvals(alpha(0.0, math.pi, KR))])
    a_ref = (2 * math.pi / (NZ * KT * lam_R[lam_R > 0])).min()
    assert a_ref == pytest.approx(0.73691, rel=1e-4)  # öz denetim
    lb = lob()
    ok = np.asarray(lb.gecerli)
    assert float(np.min(np.asarray(lb.a_lim, dtype=float)[ok])) == pytest.approx(a_ref, rel=1e-3)


def test_zero_cross_terms_same_as_none():
    """G_xy = G_yx = 0 ölçülmüşse sonuç çapraz terimsiz FRF ile aynı."""
    t = izotrop(df=0.05)
    zero = FRF(f=t.xx.f, G=np.zeros_like(t.xx.G))
    kw = dict(ae=D, yon="karsi", n_aralik=N_ARALIK, K_t=KT, K_r=KR)
    l1 = lob_freze(t, takim(), **kw)
    l2 = lob_freze(TakimFRF(xx=t.xx, yy=t.yy, xy=zero, yx=zero), takim(), **kw)
    ok = np.asarray(l1.gecerli)
    assert np.array_equal(ok, np.asarray(l2.gecerli))
    assert np.allclose(np.asarray(l1.a_lim)[ok], np.asarray(l2.a_lim)[ok], rtol=1e-12)


# ---------------------------------------------------------------- K5 lob_freze: yön → daldırma açıları


@pytest.mark.parametrize("yon, phi", [("karsi", (0.0, math.pi / 2)), ("ayni", (math.pi / 2, math.pi))])
def test_half_immersion_direction(yon, phi):
    """K5: yarım daldırma (ae = D/2) karşı ve aynı yön lob noktaları elle türetilmiş [α] ile (göreli 1e-9)."""
    fams = families(*phi)
    found = 0
    for k in range(2):
        n, a = finite(*lob(D / 2, yon).loblar[k])
        keep = a < 100.0 * a.min()  # Λ_R → 0 yakınındaki çok büyük a (lob kolu) dışarıda
        n, a = n[keep], a[keep]
        curves = [fam(k) for fam in fams]
        for i in sample_idx(len(n), 15):
            assert match_rel(n[i], a[i], curves, F_LO, F_HI) <= 1e-9, (yon, k, n[i])
            found += 1
    assert found > 10


# ---------------------------------------------------------------- K7 (K_r kısmı; Kienzle ikinci aşamada)


def test_default_kr():
    """K7: K_r verilmezse 0.3 kullanılır ve varsayilan_Kr = True."""
    lb = lob_freze(izotrop(df=0.05), takim(), ae=D, yon="karsi", n_aralik=N_ARALIK, K_t=KT)
    assert lb.K_r == pytest.approx(0.3, abs=0.0)
    assert lb.varsayilan_Kr is True
    lb2 = lob_freze(izotrop(df=0.05), takim(), ae=D, yon="karsi", n_aralik=N_ARALIK, K_t=KT, K_r=0.3)
    assert lb2.varsayilan_Kr is False
    assert np.allclose(np.asarray(lb.a_lim)[lb.gecerli], np.asarray(lb2.a_lim)[lb2.gecerli], rtol=1e-12)


# ---------------------------------------------------------------- hatalar


def kw(**over):
    d = dict(ae=D, yon="karsi", n_aralik=N_ARALIK, K_t=KT, K_r=KR)
    d.update(over)
    return d


@pytest.mark.parametrize("ae", [0.0, -1.0, D + 1e-6, 2 * D])
def test_bad_ae_raises(ae):
    """Hatalar: ae ≤ 0 ya da ae > D → hata."""
    with pytest.raises(CamError):
        lob_freze(izotrop(df=0.5), takim(), **kw(ae=ae))


@pytest.mark.parametrize("aralik", [(30000.0, 3000.0), (8000.0, 8000.0)])
def test_bad_speed_range_raises(aralik):
    """Hatalar: n_aralik ters (veya boş) → hata."""
    with pytest.raises(CamError):
        lob_freze(izotrop(df=0.5), takim(), **kw(n_aralik=aralik))


def test_speed_range_above_machine_profile_raises():
    """Hatalar: n_aralik profilin rpm_max'ını aşıyor → hata; aşmıyorsa kabul."""
    prof = MachineProfile(name="FREZE1", controller="fanuc", rpm_max=24000.0, feed_max=8000.0)
    with pytest.raises(CamError):
        lob_freze(izotrop(df=0.5), takim(), **kw(profil=prof))
    assert isinstance(lob_freze(izotrop(df=0.5), takim(), **kw(n_aralik=(3000.0, 24000.0), profil=prof)), Lob)


def test_missing_kt_raises():
    """Hatalar: K_t yok ve malzeme yok → hata."""
    with pytest.raises(CamError):
        lob_freze(izotrop(df=0.5), takim(), **kw(K_t=None))


def test_missing_kt_material_without_kienzle_raises():
    """Hatalar: K_t yok ve malzeme kc11 / mc içermiyor → hata."""

    class Bos:
        name = "uydurma"

    with pytest.raises(CamError):
        lob_freze(izotrop(df=0.5), takim(), **kw(K_t=None, malzeme=Bos(), fz=0.1))


# ---------------------------------------------------------------- K10: bağımlılık


IZINLI = {"numpy", "math", "csv", "__future__", "dataclasses", "typing", "collections"}


@pytest.mark.parametrize("dosya", ["cam/chatter.py", "cam/frf.py"])
def test_imports_restricted(dosya):
    """K10: yalnız numpy, math, csv, cam.model (+ cam.frf, tip / veri sınıfı için stdlib)."""
    tree = ast.parse((ROOT / dosya).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{dosya}: göreli import"
            mods = [node.module or ""]
        else:
            continue
        for m in mods:
            if m.split(".")[0] == "cam":
                assert m in ("cam.model", "cam.frf"), f"{dosya}: {m}"
            else:
                assert m.split(".")[0] in IZINLI, f"{dosya}: {m}"


def test_no_occt_needed():
    """K10: cam.chatter ve cam.frf içe aktarılınca OCCT / build123d yüklenmez."""
    code = (
        "import sys, cam.chatter, cam.frf; "
        "bad = [m for m in sys.modules if m.split('.')[0] in ('OCP', 'build123d', 'OCC')]; "
        "print(','.join(bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""
