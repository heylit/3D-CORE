"""SPEC 53 K7–K9 — Tezgah için kademeli ağ (LOD): quadric sadeleştirme, Hausdorff, seviye seçimi.

Testler SPEC 53 "Tezgah'ta kademeli ağ" bölümünden ve arayüzden yazıldı; viz/lod.py kodu okunmadı.

Kaynaklar:
- Keskin kenar (dihedral > keep_angle) ve sınır kenarı daraltılmaz; ağın kapalılığı (topolojisi) korunur.
- Kürede sadeleşmiş seviyenin tek yönlü Hausdorff uzaklığı (sadeleşmiş → asıl) için üst sınır (SPEC 53 K7,
  koordinatör
  kararı 2026-10-18; SPEC metnindeki ρ(1 − cos(θ/2)) bir kenarın kiriş hatasıdır, üçgenin içi daha derindir):
      d_H ≤ ρ − √(ρ² − c²/3) + δ + ε0
  c: seviyenin en uzun kenarı (dar açılı üçgende çevrel yarıçap ≤ c/√3, geniş açılıda üçgen çapı c olan
  çemberde),
  δ: sadeleşmiş köşelerin küreden en büyük sapması, ε0: asıl ağın kendi kiriş hatası (asıl ağa ölçülüyor).
- Seçim: e_px = d_H · f / (z · s) ≤ px olan en kaba seviye. d_H kademeden kademeye iki katına çıkarsa eşik
  uzaklığı
  z_i = d_H,i · f / (s · px) de iki katına çıkar: uzaklık iki katına çıkınca bir kademe kabalaşır.
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from cam.model import CamError
from core.model import ModelError
from tests.cam import tridexref as tr
from viz.lod import Level, hausdorff, levels, pick, simplify
from viz.scene import VizError

HATA = (VizError, ModelError, CamError)  # "paketin hata tipi"

# ------------------------------------------------------------------ ağ yardımcıları


def _kullanilan(V, T) -> np.ndarray:
    return np.asarray(V, dtype=float)[np.unique(np.asarray(T))]


def _kenarlar(T) -> dict[tuple[int, int], int]:
    """Yönlü kenar → sayısı."""
    say: dict[tuple[int, int], int] = {}
    for a, b, c in np.asarray(T):
        for e in ((a, b), (b, c), (c, a)):
            say[(int(e[0]), int(e[1]))] = say.get((int(e[0]), int(e[1])), 0) + 1
    return say


def kapali_ve_yonlu(V, T) -> None:
    """Her yönlü kenar bir kez, tersi bir kez (kapalı, tutarlı yönlü 2-manifold); dejenere üçgen yok; χ =
    2."""
    V = np.asarray(V, dtype=float)
    T = np.asarray(T)
    say = _kenarlar(T)
    assert all(n == 1 for n in say.values())
    assert all((b, a) in say for a, b in say)
    P = V[T]
    alan = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
    assert alan.min() > 0
    nV = len(np.unique(T))
    assert nV - len(say) // 2 + len(T) == 2


def isaretli_hacim(V, T) -> float:
    P = np.asarray(V, dtype=float)[np.asarray(T)]
    return float(np.einsum("ij,ij->i", P[:, 0], np.cross(P[:, 1], P[:, 2])).sum() / 6.0)


def kenar_boylari(V, T) -> np.ndarray:
    P = np.asarray(V, dtype=float)[np.asarray(T)]
    return np.linalg.norm(P[:, [1, 2, 0]] - P, axis=2).ravel()


def koord_kenarlar(V, T, sadece_sinir: bool = False) -> set:
    """Kenarları koordinat çiftleriyle (sırasız, 1e-9'a yuvarlanmış) döndürür; sadece_sinir → tek üçgenli
    kenarlar."""
    V = np.round(np.asarray(V, dtype=float), 9)
    say = _kenarlar(T)
    k = set()
    for a, b in say:
        if sadece_sinir and (b, a) in say:
            continue
        k.add(frozenset((tuple(V[a]), tuple(V[b]))))
    return k


def izgara(nx: int, ny: int, L: float, z=None) -> tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(0.0, L, nx + 1)
    ys = np.linspace(0.0, L, ny + 1)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    Z = np.zeros_like(X) if z is None else z(X, Y)
    V = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    i, j = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
    i, j = i.ravel(), j.ravel()
    v00, v10 = i * (ny + 1) + j, (i + 1) * (ny + 1) + j
    v11, v01 = v10 + 1, v00 + 1
    T = np.vstack([np.column_stack([v00, v10, v11]), np.column_stack([v00, v11, v01])])
    return V, T


def alt_bolunmus_kup(n: int, L: float = 10.0) -> tuple[np.ndarray, np.ndarray]:
    """[0, L]³ küp, her yüz n × n ızgara (dışa yönlü), ortak köşeler birleştirilmiş."""
    Vs, Ts, off = [], [], 0
    u = np.linspace(0.0, L, n + 1)
    A, B = np.meshgrid(u, u, indexing="ij")
    a, b = A.ravel(), B.ravel()
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    i, j = i.ravel(), j.ravel()
    q00, q10 = i * (n + 1) + j, (i + 1) * (n + 1) + j
    q11, q01 = q10 + 1, q00 + 1
    for eksen in range(3):
        for yan in (0.0, L):
            e1, e2 = (eksen + 1) % 3, (eksen + 2) % 3
            P = np.zeros((len(a), 3))
            P[:, eksen], P[:, e1], P[:, e2] = yan, a, b
            T = np.vstack([np.column_stack([q00, q10, q11]), np.column_stack([q00, q11, q01])])
            if yan == 0.0:
                T = T[:, ::-1]  # (e1, e2, eksen) sağ elli: yan = L'de normal +eksen, yan = 0'da ters
            Vs.append(P)
            Ts.append(T + off)
            off += len(P)
    V = np.vstack(Vs)
    T = np.vstack(Ts)
    tekil, ters = np.unique(np.round(V, 9), axis=0, return_inverse=True)
    return tekil, ters.ravel()[T]


def kare(x0, x1, y0, y1, z) -> tuple[np.ndarray, np.ndarray]:
    V = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]], dtype=float)
    return V, np.array([[0, 1, 2], [0, 2, 3]])


def test_yardimci_aglar_kapali():
    kapali_ve_yonlu(*tr.box_mesh((0, 0, 0), (10, 10, 10)))
    kapali_ve_yonlu(*alt_bolunmus_kup(4))
    V, T = alt_bolunmus_kup(4)
    assert isaretli_hacim(V, T) == pytest.approx(1000.0, rel=1e-12)
    kapali_ve_yonlu(*tr.icosphere((0, 0, 0), 50.0, 3))


# ------------------------------------------------------------------ K7 keskin kenarlar ve sınır


@pytest.mark.parametrize("target", [4, 6, 10, 11])
def test_K7_kup_daraltilmiyor(target):
    V, T = tr.box_mesh((0.0, 0.0, 0.0), (10.0, 10.0, 10.0))
    V2, T2 = simplify(V, T, target)
    assert len(T2) == 12
    assert sorted(map(tuple, _kullanilan(V2, T2))) == sorted(map(tuple, V))
    kapali_ve_yonlu(V2, T2)
    assert isaretli_hacim(V2, T2) == pytest.approx(1000.0, rel=1e-12)


def test_K7_alt_bolunmus_kup_sekli_korunuyor():
    """Yüzlerin içindeki köşeler daralabilir (düz, maliyet 0), keskin kenarlar ve köşeler kalır: hacim,
    kutu ve
    yüz düzlemleri aynı. 4 × 4 yüz: 192 üçgen; en az 6·(4·4 − 2) = 84 → 100 erişilebilir."""
    V, T = alt_bolunmus_kup(4)
    V2, T2 = simplify(V, T, 100)
    assert abs(len(T2) - 100) <= 2
    kapali_ve_yonlu(V2, T2)
    assert isaretli_hacim(V2, T2) == pytest.approx(1000.0, rel=1e-9)
    K = _kullanilan(V2, T2)
    for kose in tr.box_mesh((0, 0, 0), (10, 10, 10))[0]:
        assert np.min(np.linalg.norm(K - kose, axis=1)) < 1e-9
    # her köşe küp yüzeyinde, her üçgen bir yüz düzleminde
    assert np.all(np.min(np.minimum(np.abs(K), np.abs(K - 10.0)), axis=1) < 1e-9)
    P = np.asarray(V2, dtype=float)[np.asarray(T2)]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    n /= np.linalg.norm(n, axis=1)[:, None]
    assert np.allclose(np.sort(np.abs(n), axis=1), [0.0, 0.0, 1.0], atol=1e-9)
    # keskin kenarlar (küp kenarları) üstünde kalan kenarlar küp kenarını tümüyle örtüyor
    kenar = [e for e in koord_kenarlar(V2, T2) if _kup_kenarinda(e)]
    assert sum(np.linalg.norm(np.subtract(*map(np.array, e))) for e in kenar) == pytest.approx(
        120.0, rel=1e-9
    )


def _kup_kenarinda(e) -> bool:
    a, b = (np.array(p) for p in e)
    sinirda = (np.abs(a) < 1e-9) | (np.abs(a - 10) < 1e-9)
    sinirda_b = (np.abs(b) < 1e-9) | (np.abs(b - 10) < 1e-9)
    return int((sinirda & sinirda_b & (np.abs(a - b) < 1e-9)).sum()) >= 2


def test_K7_acik_agda_sinir_kenarlari_korunuyor():
    """20 × 20 düz ızgara (800 üçgen) → 200: 80 sınır kenarı aynı, alan 400, hiçbir üçgen ters dönmüyor."""
    V, T = izgara(20, 20, 20.0)
    sinir = koord_kenarlar(V, T, sadece_sinir=True)
    assert len(sinir) == 80
    V2, T2 = simplify(V, T, 200)
    assert abs(len(T2) - 200) <= 2
    assert koord_kenarlar(V2, T2, sadece_sinir=True) == sinir
    P = np.asarray(V2, dtype=float)[np.asarray(T2)]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    assert np.all(n[:, 2] > 0)
    assert 0.5 * n[:, 2].sum() == pytest.approx(400.0, rel=1e-9)


def test_K7_keep_angle_sirt_kenari():
    """Sırt açısı 20° (iki düzlem, x = 10'da birleşir): keep_angle = 10 → sırt keskin, sırt kenarları
    kalır."""
    m = math.tan(math.radians(10.0))

    def cati(X, Y):
        return m * (10.0 - np.abs(X - 10.0))

    V, T = izgara(20, 20, 20.0, cati)
    sirt = {e for e in koord_kenarlar(V, T) if all(abs(p[0] - 10.0) < 1e-9 for p in e)}
    assert len(sirt) == 20
    V2, T2 = simplify(V, T, 200, keep_angle=10.0)
    assert sirt <= koord_kenarlar(V2, T2)
    K = _kullanilan(V2, T2)
    assert np.allclose(K[:, 2], cati(K[:, 0], K[:, 1]), atol=1e-9)  # iki düzlemde kalıyor


# ------------------------------------------------------------------ K7 küre

RHO = 50.0
C0 = (0.0, 0.0, 0.0)


@functools.cache
def _kure(n_bol: int):
    V, T = tr.icosphere(C0, RHO, n_bol)
    return V, T, levels(V, T)


def _kure_seviyesi_dogru(n_bol: int) -> None:
    V0, T0, lv = _kure(n_bol)
    N = len(T0)
    eps0 = tr.sagitta(V0, T0, C0, RHO)
    assert [round(L.ratio, 12) for L in lv] == [1.0, 0.5, 0.25, 0.125]
    assert np.array_equal(lv[0].V, V0) and np.array_equal(lv[0].T, T0) and lv[0].hausdorff == 0.0
    for L in lv[1:]:
        assert isinstance(L, Level)
        assert abs(len(L.T) - L.ratio * N) <= 2
        kapali_ve_yonlu(L.V, L.T)
        K = _kullanilan(L.V, L.T)
        delta = float(np.max(np.abs(np.linalg.norm(K, axis=1) - RHO)))
        c = float(kenar_boylari(L.V, L.T).max())
        sinir = RHO - math.sqrt(RHO**2 - c * c / 3.0) + delta + eps0 + 1e-9  # eşkenarda eşitlik
        assert 0.0 < L.hausdorff <= sinir
        assert hausdorff(V0, T0, L.V, L.T) <= sinir
        hacim = 4.0 / 3.0 * math.pi * RHO**3
        assert abs(isaretli_hacim(L.V, L.T) - hacim) <= 4.0 * math.pi * RHO**2 * sinir


def test_K7_kure_5120():
    _kure_seviyesi_dogru(4)


@pytest.mark.slow
def test_K7_kure_80000_ucgen():
    """SPEC: yoğun ağlı küre ρ = 50, ~80 000 üçgen (ikosfer 6 kez bölünmüş: 81 920)."""
    assert len(_kure(6)[1]) == 81_920
    _kure_seviyesi_dogru(6)


def test_K7_levels_oran_parametresi():
    V, T = tr.icosphere(C0, RHO, 3)
    lv = levels(V, T, ratios=(0.5,))
    assert len(lv) == 2 and lv[1].ratio == 0.5 and abs(len(lv[1].T) - 640) <= 2


# ------------------------------------------------------------------ Hausdorff


def test_hausdorff_ayni_ag_sifir():
    V, T = tr.icosphere(C0, RHO, 2)
    assert hausdorff(V, T, V, T) == pytest.approx(0.0, abs=1e-9)


def test_hausdorff_paralel_kareler():
    """Üstteki küçük kare (izdüşümü alttakinin içinde) → alttaki büyük kareye uzaklık her noktada h."""
    A = kare(0, 10, 0, 10, 0.0)
    B = kare(2, 8, 2, 8, 0.7)
    assert hausdorff(*A, *B) == pytest.approx(0.7, abs=1e-9)


def test_hausdorff_tek_yonlu():
    """B = [0,10]², A = [0,5]×[0,10] (aynı düzlem): B → A en büyük uzaklık 5 (x = 10 kenarı); A ⊂ B → 0."""
    A = kare(0, 5, 0, 10, 0.0)
    B = kare(0, 10, 0, 10, 0.0)
    d = hausdorff(*A, *B)
    assert 4.8 <= d <= 5.0 + 1e-9
    assert hausdorff(*B, *A) == pytest.approx(0.0, abs=1e-9)


# ------------------------------------------------------------------ K8 seçim

# İkili kesirler: e_px hesabı kesin. f = 64, s = 1/128 → z_i = d_H,i · f / (s · px) = 8192 · d_H,i / px.
F, S = 64.0, 1.0 / 128.0
DH = [0.0, 2.0**-10, 2.0**-9, 2.0**-8]  # her kademe iki kat


def _seviyeler(dh=DH) -> list[Level]:
    V, T = kare(0, 1, 0, 1, 0)
    return [Level(V, T, 2.0**-i, d) for i, d in enumerate(dh)]


def _e_px(d, z):
    return d * F / (z * S)


def test_K8_esikler_elle():
    lv = _seviyeler()
    z1, z2, z3 = (8192.0 * d for d in DH[1:])  # 8, 16, 32
    assert (z1, z2, z3) == (8.0, 16.0, 32.0)
    assert pick(lv, 4.0, F, S) == 0
    assert pick(lv, 7.9, F, S) == 0
    assert pick(lv, z1, F, S) == 1  # e_px = 1 ≤ 1
    assert pick(lv, 12.0, F, S) == 1
    assert pick(lv, z2, F, S) == 2
    assert pick(lv, 24.0, F, S) == 2
    assert pick(lv, z3, F, S) == 3
    assert pick(lv, 1e6, F, S) == 3


@pytest.mark.parametrize("z", [9.0, 10.0, 12.5, 15.9])
def test_K8_uzaklik_iki_katina_bir_kademe(z):
    lv = _seviyeler()
    i = pick(lv, z, F, S)
    assert pick(lv, 2 * z, F, S) == i + 1
    assert pick(lv, 4 * z, F, S) == min(i + 2, 3)


def test_K8_px_parametresi():
    """px = 2: eşikler yarıya iner (z_i = 4096 · d_H,i)."""
    lv = _seviyeler()
    assert pick(lv, 4.0, F, S, px=2.0) == 1
    assert pick(lv, 3.9, F, S, px=2.0) == 0
    assert pick(lv, 8.0, F, S, px=2.0) == 2
    assert pick(lv, 16.0, F, S, px=2.0) == 3


def test_K8_px_siniri_rastgele():
    rng = np.random.default_rng(53)
    lv = _seviyeler()
    for _ in range(500):
        z = float(rng.uniform(0.5, 100.0))
        px = float(rng.choice([0.5, 1.0, 2.0, 3.0]))
        i = pick(lv, z, F, S, px=px)
        assert _e_px(lv[i].hausdorff, z) <= px
        assert all(_e_px(L.hausdorff, z) > px for L in lv[i + 1 :])  # en kaba


def test_K8_gercek_seviyelerde_px_siniri():
    V0, T0, lv = _kure(4)
    f, s = 35.0, 0.005
    for z in np.geomspace(10.0, 1e5, 60):
        i = pick(lv, float(z), f, s)
        assert lv[i].hausdorff * f / (z * s) <= 1.0
        assert all(L.hausdorff * f / (z * s) > 1.0 for L in lv[i + 1 :])


# ------------------------------------------------------------------ K9


@pytest.mark.parametrize("target", [3, 0, -1])
def test_K9_target_cok_kucuk(target):
    V, T = tr.icosphere(C0, RHO, 1)
    with pytest.raises(HATA):
        simplify(V, T, target)


@pytest.mark.parametrize("fark", [0, 1, 100])
def test_K9_target_mevcut_ucgen_sayisindan_kucuk_olmali(fark):
    V, T = tr.icosphere(C0, RHO, 1)
    with pytest.raises(HATA):
        simplify(V, T, len(T) + fark)
