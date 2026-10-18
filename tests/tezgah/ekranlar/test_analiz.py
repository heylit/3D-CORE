"""
SPEC 47c — Analiz ekranının köprüsü (`tezgah/ekranlar/_analiz_kopru.py`): K14 ağ, K15 seçim, K16 çözüm ve
denge, K17 sonda, K18 analitik satırlar, K19 yakınsama; ikili dizilerin bayt düzeyinde geri dönüşü.

Beklenen değerler köprüden değil, SPEC 11–13 fonksiyonlarından (`tet_mesh`, `boundary_triangles`, `on_plane`,
`on_cylinder`, `select_nodes`, `select_triangles`, `triangle_areas`, `triangle_normals`, `fix`,
`add_traction`, `add_pressure`, `solve`, `nodal_stress_tensors`, `von_mises`, `principal_stresses`) ve kapalı
formüllerden hesaplanır (`analiz_ortak`). Örnek işler OCCT + gmsh ister (`@occt`, `importorskip("gmsh")`);
K17'nin doğrusal alan testi elle kurulmuş tet4 küpleriyle gmsh'sizdir. Gerilme tensörü sırası core sırasıdır:
(xx, yy, zz, xy, xz, yz).
"""

from __future__ import annotations

import copy
import dataclasses
import math

import numpy as np
import pytest

pytest.importorskip("fastapi", reason="[web] kurulu değil (pip install -e .[web])")

from core.model import Material, ModelError  # noqa: E402
from tests.benchmarks.tet_ag import kutu_agi  # noqa: E402
from tests.tezgah.ekranlar import analiz_ortak as o  # noqa: E402
from tezgah.ekranlar import _analiz_kopru as ak  # noqa: E402

CELIK = Material("celik", E=210_000.0, nu=0.3)
BILESEN_SUTUNU = {"sxx": 0, "syy": 1, "szz": 2, "sxy": 3, "sxz": 4, "syz": 5}


# ---------------------------------------------------------------- örnek önbelleği (modül boyu)


# Fikstür değil, test içinde çağrılan önbellek: iskelette NotImplementedError kurulumda değil testte doğsun
# ("uygulanmamış" sayılır, conftest).
_ONBELLEK: dict[str, tuple] = {}


def _hazirla(ad: str) -> tuple:
    """(tanım, köprü ağı, koşullu model, bağımsız çözüm) — modül boyunca bir kez."""
    if ad not in _ONBELLEK:
        t = o.ornek(ad)
        ag = ak.ag_kur(t)
        m = ak.model_kur(t, ag)
        _ONBELLEK[ad] = (t, ag, m, o.cozum(m))
    return _ONBELLEK[ad]


@pytest.fixture
def plaka():
    return lambda: _hazirla("delikli_plaka")


@pytest.fixture
def kiris():
    return lambda: _hazirla("konsol_kiris")


def _ucgen_x(X_id: dict[int, np.ndarray], tris: np.ndarray, x: float) -> int:
    """Üç köşesi de x düzleminde olan ilk sınır üçgeninin indeksi."""
    for j, tr in enumerate(tris):
        if all(abs(X_id[int(k)][0] - x) <= 1e-9 for k in tr):
            return j
    raise AssertionError(f"x = {x} yüzünde üçgen yok")


# ---------------------------------------------------------------- örnek tanımları


@pytest.mark.occt
def test_ornek_tanimlari():
    """delikli_plaka çelik (E, ν, Re), konsol_kiris; kilitli örnek koşulları ve analitik satırları var."""
    t = o.ornek("delikli_plaka")
    assert (t.malzeme.E, t.malzeme.nu, t.Re) == (210_000.0, 0.3, 235.0)
    lo, hi = t.parca.bbox()
    assert np.allclose(lo, [0, 0, 0], atol=1e-6) and np.allclose(hi, [200, 100, 5], atol=1e-6)
    assert t.parca.volume() == pytest.approx(200 * 100 * 5 - math.pi * 5**2 * 5, rel=1e-6)
    assert t.refine, "delik çevresinde Refine küresi"
    turler = sorted(k.tur for k in t.kosullar)
    assert turler.count("cekme") == 1 and turler.count("mesnet") >= 1
    assert all(k.kilitli for k in t.kosullar)
    cekme = next(k for k in t.kosullar if k.tur == "cekme")
    assert tuple(cekme.deger) == (100.0, 0.0, 0.0)

    k = o.ornek("konsol_kiris")
    lo, hi = k.parca.bbox()
    assert np.allclose(lo, [0, 0, 0], atol=1e-6) and np.allclose(hi, [200, 20, 20], atol=1e-6)
    cekme = next(x for x in k.kosullar if x.tur == "cekme")
    assert tuple(cekme.deger) == (0.0, 0.0, -2.5)
    assert len(k.analitik) >= 2


# ---------------------------------------------------------------- K14: ağ


@pytest.mark.occt
def test_ag(plaka):
    t, ag, _, _ = plaka()
    m, ids, X, tris = o.ag_modeli(t)
    assert np.array_equal(np.asarray(ag.kimlik), ids)
    assert np.array_equal(np.asarray(ag.X, dtype=float), X)
    assert np.array_equal(np.asarray(ag.ucgenler), tris)
    assert ag.hacim == pytest.approx(o.eleman_hacmi(m), rel=1e-12)
    assert ag.L_kutu == pytest.approx(o.L_kutu(t.parca), rel=1e-12)

    # ikili: düğümler float32, sınır üçgenleri 0 tabanlı indeks, kimlik int32
    d = ak.ag_coz(ak.ag_ikili(ag))
    assert d["dugum"].dtype == np.float32 and np.array_equal(d["dugum"], X.astype(np.float32))
    assert d["kimlik"].dtype == np.int32 and np.array_equal(d["kimlik"], ids.astype(np.int32))
    sira = {int(k): i for i, k in enumerate(ids)}
    beklenen = np.vectorize(sira.__getitem__)(tris).astype(np.uint32)
    assert d["ucgen"].dtype == np.uint32 and np.array_equal(d["ucgen"], beklenen)

    J = o.jt(ak.analiz_json(t, ag))
    assert J["sema"] == 1 and J["ad"] == "delikli_plaka"
    assert (J["ag"]["dugum"], J["ag"]["eleman"]) == (len(ids), len(m.elements))
    assert J["ag"]["h"] == t.h
    assert J["ag"]["hacim"] == pytest.approx(o.eleman_hacmi(m), rel=1e-12)
    assert J["parca"]["hacim"] == pytest.approx(t.parca.volume(), rel=1e-12)
    assert (J["malzeme"]["E"], J["malzeme"]["nu"], J["malzeme"]["Re"]) == (210_000.0, 0.3, 235.0)
    assert J["cozum"] is None and J["yakinsama"] is None
    K = J["kontroller"]
    assert o.kontrol(K, "ag_hacmi")["durum"] == "tamam"
    assert not o.kimlikler(K) & {"denge", "akma", "analitik_sapma", "yakinsama"}  # çözüm yok: sahte tamam yok


# ---------------------------------------------------------------- K15: seçim


@pytest.mark.occt
def test_secim_duzlem(plaka):
    """x = 200 yüzünde bir üçgene tıklama: aynı düzlemdeki bütün sınır yüzü; alan 100·5 (düzlemde kesin)."""
    from mesh import on_plane, select_nodes, select_triangles, triangle_areas, triangle_normals

    t, ag, _, _ = plaka()
    m, ids, X, tris = o.ag_modeli(t)
    X_id = dict(zip(ids.tolist(), X, strict=True))
    j = _ucgen_x(X_id, tris, 200.0)
    s = ak.ucgen_secimi(t, ag, j)
    assert s.tur == "duzlem"
    dugum, ucgen, alan = ak.secim_uygula(ag, s)

    c = np.mean([X_id[int(k)] for k in tris[j]], axis=0)
    n = triangle_normals(m, tris[j : j + 1])[0]
    pred = on_plane(c, n, 1e-6 * o.L_kutu(t.parca))
    assert list(dugum) == select_nodes(m, pred)
    U = select_triangles(m, pred)
    assert np.array_equal(np.asarray(ucgen), U)
    assert alan == pytest.approx(float(triangle_areas(m, U).sum()), rel=1e-12)
    assert alan == pytest.approx(100.0 * 5.0, rel=1e-9)

    t2 = ak.secim_ekle(t, s)
    assert len(t2.secimler) == len(t.secimler) + 1 and t.secimler == t2.secimler[:-1]  # yeni tanım
    J = o.jt(ak.analiz_json(t2, ag))
    yeni = J["secimler"][-1]
    assert yeni["kimlik"] == s.kimlik and yeni["tur"] == "duzlem"
    assert yeni["dugumler"] == list(dugum)
    assert yeni["alan"] == pytest.approx(500.0, rel=1e-9)


@pytest.mark.occt
def test_secim_silindir(plaka):
    """Delik yüzeyi silindir seçimiyle (r = 5): alan π·10·5 (ağ yaklaşımı, rel 1e-2)."""
    from mesh import on_cylinder, select_nodes, select_triangles

    t, ag, _, _ = plaka()
    m, _, _, _ = o.ag_modeli(t)
    s = ak.silindir_secimi(t, ag, (100.0, 50.0, 0.0), (0.0, 0.0, 1.0), 5.0)
    assert s.tur == "silindir"
    dugum, ucgen, alan = ak.secim_uygula(ag, s)
    pred = on_cylinder((100.0, 50.0, 0.0), (0.0, 0.0, 1.0), 5.0, 1e-6 * o.L_kutu(t.parca))
    assert list(dugum) == select_nodes(m, pred)
    assert np.array_equal(np.asarray(ucgen), select_triangles(m, pred))
    assert alan == pytest.approx(math.pi * 10.0 * 5.0, rel=1e-2)


@pytest.mark.occt
def test_secim_hatalar(plaka):
    t, ag, _, _ = plaka()
    m = len(np.asarray(ag.ucgenler))
    for j in (m, m + 10, -1):
        with pytest.raises(ModelError):
            ak.ucgen_secimi(t, ag, j)
    with pytest.raises(ModelError):
        ak.silindir_secimi(t, ag, (100.0, 50.0, 0.0), (0.0, 0.0, 0.0), 5.0)
    with pytest.raises(ModelError):
        ak.silindir_secimi(t, ag, (100.0, 50.0, 0.0), (0.0, 0.0, 1.0), 0.0)
    bos = ak.silindir_secimi(t, ag, (100.0, 50.0, 0.0), (0.0, 0.0, 1.0), 2.0)  # delik içinde: düğüm yok
    with pytest.raises(ModelError):
        ak.secim_ekle(t, bos)


# ---------------------------------------------------------------- koşullar


@pytest.mark.occt
def test_model_kur(plaka):
    """Koşullar listedeki sırayla SPEC 12 fix / add_traction / add_pressure ile; ağın modeli değişmez."""
    from mesh import add_pressure, add_traction, fix

    t, ag, m, _ = plaka()
    beklenen = copy.deepcopy(ag.model)
    secim = {s.kimlik: s for s in t.secimler}
    for k in t.kosullar:
        dugum, ucgen, _ = ak.secim_uygula(ag, secim[k.secim])
        if k.tur == "mesnet":
            fix(beklenen, dugum, tuple(k.deger))
        elif k.tur == "cekme":
            add_traction(beklenen, np.asarray(ucgen), tuple(k.deger))
        else:
            add_pressure(beklenen, np.asarray(ucgen), float(np.ravel(k.deger)[0]))
    assert m.bcs == beklenen.bcs
    assert m.loads == beklenen.loads
    assert not ag.model.bcs and not ag.model.loads
    assert ak.model_kur(t, ag).loads == m.loads  # her seferinde temiz kopyadan


@pytest.mark.occt
def test_kosul_ekle_sil(plaka):
    t, ag, _, _ = plaka()
    m, ids, X, tris = o.ag_modeli(t)
    X_id = dict(zip(ids.tolist(), X, strict=True))
    s = ak.ucgen_secimi(t, ag, _ucgen_x(X_id, tris, 200.0))
    t1 = ak.secim_ekle(t, s)
    t2 = ak.kosul_ekle(t1, s.kimlik, "basinc", 2.0)
    assert len(t2.kosullar) == len(t1.kosullar) + 1
    yeni = t2.kosullar[-1]
    assert (yeni.secim, yeni.tur, yeni.kilitli) == (s.kimlik, "basinc", False)
    t3 = ak.kosul_sil(t2, yeni.kimlik)
    assert t3.kosullar == t1.kosullar

    for args in (
        ("yok", "mesnet", ["ux"]),
        (s.kimlik, "tork", [1.0]),
        (s.kimlik, "mesnet", ["rx"]),
        (s.kimlik, "cekme", [1.0, 2.0]),
        (s.kimlik, "cekme", [math.nan, 0.0, 0.0]),
        (s.kimlik, "basinc", math.inf),
    ):
        with pytest.raises(ModelError):
            ak.kosul_ekle(t1, *args)
    with pytest.raises(KeyError):
        ak.kosul_sil(t1, "k999")
    with pytest.raises(ModelError):
        ak.kosul_sil(t1, t.kosullar[0].kimlik)  # örneğin kilitli koşulu
    for h in (0.0, -1.0, math.nan):
        with pytest.raises(ModelError):
            ak.h_degistir(t, h)
    assert ak.h_degistir(t, 7.5).h == 7.5


# ---------------------------------------------------------------- K16: çözüm ve denge


@pytest.mark.occt
def test_coz(plaka):
    t, ag, m, (u, sigma, vm, asal, r) = plaka()
    c = ak.coz(t, ag)
    assert np.allclose(c.u, u, rtol=1e-12, atol=1e-15)
    assert np.allclose(c.sigma, sigma, rtol=1e-12, atol=1e-9)
    assert np.allclose(c.vm, vm, rtol=1e-12, atol=1e-9)
    assert np.allclose(c.asal, asal, rtol=1e-12, atol=1e-9)

    # alan ikilisi: float32 birebir
    A = ak.alan_coz(ak.alan_ikili(c))
    for ad, beklenen in (("u", u), ("vm", vm), ("asal", asal), ("tensor", sigma)):
        assert A[ad].dtype == np.float32, ad
        assert np.array_equal(A[ad], beklenen.astype(np.float32)), ad

    R, F = o.toplamlar(m, r)
    ozet = c.ozet
    assert ozet["yuk"][0] == pytest.approx(100.0 * 500.0, rel=1e-9)
    assert ozet["yuk"][1:] == pytest.approx([0.0, 0.0], abs=1e-6)
    assert ozet["yuk"] == pytest.approx(F, rel=1e-12, abs=1e-9)
    assert ozet["tepki"] == pytest.approx(R, rel=1e-12, abs=1e-9)
    assert ozet["denge"] == pytest.approx(R + F, abs=1e-9 * max(abs(F).max(), 1))

    nu = np.linalg.norm(u, axis=1)
    ids = np.asarray(ag.kimlik)
    assert ozet["u_max"] == pytest.approx(float(nu.max()), rel=1e-12)
    assert ozet["u_max_dugum"] == int(ids[int(np.argmax(nu))])
    assert ozet["vm_max"] == pytest.approx(float(vm.max()), rel=1e-12)
    assert ozet["vm_max_dugum"] == int(ids[int(np.argmax(vm))])
    assert ozet["guvenlik"] == pytest.approx(235.0 / float(vm.max()), rel=1e-12)
    assert ozet["olcek"] == pytest.approx(0.1 * o.L_kutu(t.parca) / float(nu.max()), rel=1e-12)
    # ikiliden bulunan uç değerler özetle aynı
    assert float(np.linalg.norm(A["u"], axis=1).max()) == pytest.approx(ozet["u_max"], rel=1e-6)
    assert float(A["vm"].max()) == pytest.approx(ozet["vm_max"], rel=1e-6)

    J = o.jt(ak.analiz_json(t, ag, c))
    for alan in (
        "u_max",
        "u_max_dugum",
        "vm_max",
        "vm_max_dugum",
        "tepki",
        "yuk",
        "denge",
        "guvenlik",
        "olcek",
    ):
        assert J["cozum"][alan] == pytest.approx(o.jt(ozet[alan]), rel=1e-12), alan
    K = J["kontroller"]
    assert o.kontrol(K, "denge")["durum"] == "tamam"
    akma = o.kontrol(K, "akma")
    g = 235.0 / float(vm.max())
    assert akma["durum"] == ("hata" if g < 1 else "uyari" if g < 1.5 else "tamam")


@pytest.mark.parametrize("sutun", list(BILESEN_SUTUNU))
@pytest.mark.occt
def test_bilesen_degerleri(plaka, sutun):
    t, ag, _, (_, sigma, vm, asal, _) = plaka()
    c = ak.coz(t, ag)
    assert np.allclose(ak.bilesen_degerleri(c, sutun), sigma[:, BILESEN_SUTUNU[sutun]], rtol=1e-12, atol=1e-9)
    assert np.allclose(ak.bilesen_degerleri(c, "vm"), vm, rtol=1e-12, atol=1e-9)
    for i, ad in enumerate(("s1", "s2", "s3")):
        assert np.allclose(ak.bilesen_degerleri(c, ad), asal[:, i], rtol=1e-12, atol=1e-9)
    with pytest.raises(ModelError):
        ak.bilesen_degerleri(c, "tau")


@pytest.mark.occt
def test_coz_mesnetsiz(plaka):
    """Mesnetsiz model: çekirdeğin (tekil matris) ModelError'ı, metni aynen."""
    from core.solver import solve

    t, ag, _, _ = plaka()
    t0 = dataclasses.replace(t, kosullar=tuple(k for k in t.kosullar if k.tur != "mesnet"))
    with pytest.raises(ModelError) as beklenen:
        solve(ak.model_kur(t0, ag))
    with pytest.raises(ModelError) as e:
        ak.coz(t0, ag)
    assert str(e.value) == str(beklenen.value)


@pytest.mark.occt
def test_guvenlik_re_yok(plaka):
    """Re verilmemişse güvenlik katsayısı yok (null) ve `akma` kontrolü listede yok."""
    t, ag, _, _ = plaka()
    t0 = dataclasses.replace(t, Re=None)
    c = ak.coz(t0, ag)
    assert c.ozet["guvenlik"] is None
    J = o.jt(ak.analiz_json(t0, ag, c))
    assert J["cozum"]["guvenlik"] is None
    assert "akma" not in o.kimlikler(J["kontroller"])


# ---------------------------------------------------------------- K17: sonda


@pytest.mark.parametrize("bolum, kaydirma", [(1, 0.0), (3, 0.2)], ids=["6_tet_kup", "duzensiz_kup"])
def test_sonda_dogrusal_alan(bolum, kaydirma):
    """Doğrusal alan f = 3 + 2x − y + 0.5z tet4 ara değeriyle tam: sonda analitik değerle 1e-9."""
    m = kutu_agi(10.0, 10.0, 10.0, bolum, bolum, bolum, CELIK, kaydirma=kaydirma, tohum=3)
    X = np.array([[n.x, n.y, n.z] for n in m.nodes])

    def f(P):
        return 3.0 + 2.0 * P[..., 0] - P[..., 1] + 0.5 * P[..., 2]

    p0, p1, n = np.array([1.0, 2.0, 3.0]), np.array([9.0, 7.0, 4.0]), 11
    s, d, ic = ak.sonda_degerleri(m, f(X), p0, p1, n)
    assert s.dtype == np.float64 and d.dtype == np.float64 and ic.dtype == np.uint8
    t = np.linspace(0.0, 1.0, n)
    assert s == pytest.approx(t * np.linalg.norm(p1 - p0), abs=1e-12)
    assert d == pytest.approx(f(p0 + t[:, None] * (p1 - p0)), abs=1e-9)
    assert ic.tolist() == [1] * n


def test_sonda_parca_disi():
    """Parça dışındaki noktada bayrak 0 ve değer 0 (sahte sayı yok); kenardaki nokta içeride."""
    m = kutu_agi(10.0, 10.0, 10.0, 1, 1, 1, CELIK)
    X = np.array([[n.x, n.y, n.z] for n in m.nodes])
    p0, p1 = np.array([-5.0, 5.0, 5.0]), np.array([15.0, 5.0, 5.0])
    s, d, ic = ak.sonda_degerleri(m, 1.0 + X[:, 0], p0, p1, 21)  # x = −5, −4, …, 15
    x = np.linspace(-5.0, 15.0, 21)
    assert ic.tolist() == [1 if 0.0 <= xi <= 10.0 else 0 for xi in x]
    assert d == pytest.approx(np.where((x >= 0) & (x <= 10), 1.0 + x, 0.0), abs=1e-9)


def test_sonda_hatalar():
    m = kutu_agi(10.0, 10.0, 10.0, 1, 1, 1, CELIK)
    v = np.zeros(len(m.nodes))
    with pytest.raises(ModelError):
        ak.sonda_degerleri(m, v, (1.0, 1.0, 1.0), (2.0, 2.0, 2.0), 2001)
    with pytest.raises(ModelError):
        ak.sonda_degerleri(m, v, (1.0, 1.0, 1.0), (1.0, 1.0, 1.0), 10)
    s, d, ic = ak.sonda_degerleri(m, v, (1.0, 1.0, 1.0), (2.0, 2.0, 2.0), 2000)  # sınırda geçerli
    assert len(s) == len(d) == len(ic) == 2000


def test_sonda_ikili():
    s = np.linspace(0.0, 3.5, 7)
    d = np.array([1.0, -2.5, 1 / 3, 0.0, 1e6, 2.0, 0.0])
    ic = np.array([1, 1, 1, 0, 1, 1, 0], dtype=np.uint8)
    S = ak.sonda_coz(ak.sonda_ikili(s, d, ic))
    assert S["s"].dtype == np.float64 and np.array_equal(S["s"], s)
    assert S["deger"].dtype == np.float64 and np.array_equal(S["deger"], d)
    assert S["iceride"].dtype == np.uint8 and np.array_equal(S["iceride"], ic)


@pytest.mark.occt
def test_sonda_plaka(plaka):
    """θ = 90° doğrultusunda σxx sondası, içeren tetin barisentrik ağırlıklarıyla elle hesaplananla aynı."""
    t, ag, m, (_, sigma, _, _, _) = plaka()
    p0, p1, n = (100.0, 55.5, 2.5), (100.0, 99.5, 2.5), 45
    s, d, ic = ak.sonda_degerleri(m, sigma[:, 0], p0, p1, n)
    s_e, d_e, ic_e = o.barisentrik_sonda(m, sigma[:, 0], p0, p1, n)
    assert ic.tolist() == ic_e.tolist() == [1] * n
    assert s == pytest.approx(s_e, abs=1e-12)
    assert d == pytest.approx(d_e, rel=1e-9, abs=1e-9)

    # delik içindeki noktalar parça dışı
    s, d, ic = ak.sonda_degerleri(m, sigma[:, 0], (100.0, 50.0, 2.5), (100.0, 60.0, 2.5), 11)
    y = np.linspace(50.0, 60.0, 11)
    assert all(ic[y < 54.9] == 0) and all(d[y < 54.9] == 0.0)
    assert all(ic[y > 55.1] == 1)


# ---------------------------------------------------------------- K18: analitik satırlar


def test_heywood_ve_kirsch():
    assert ak.heywood_kt(0.1) == pytest.approx((2.0 + 0.9**3) / 0.9, rel=1e-12)
    assert round(ak.heywood_kt(0.1), 3) == 3.032
    y = np.array([5.0, 5.5, 7.5, 10.0, 25.0, 50.0])
    beklenen = 100.0 / 2 * (2 + 5.0**2 / y**2 + 3 * 5.0**4 / y**4)
    assert np.asarray(ak.kirsch_sxx(100.0, 5.0, y)) == pytest.approx(beklenen, rel=1e-12)
    assert float(np.asarray(ak.kirsch_sxx(100.0, 5.0, 5.0))) == pytest.approx(300.0, rel=1e-12)  # 3σ
    with pytest.raises(ModelError):
        ak.kirsch_sxx(100.0, 5.0, 4.0)


def test_konsol_formulleri():
    P, L, E, nu, b, h = 1000.0, 200.0, 210_000.0, 0.3, 20.0, 20.0
    I_ = b * h**3 / 12
    d = P * L**3 / (3 * E * I_)
    G = E / (2 * (1 + nu))
    dT = d + P * L / (5 / 6 * G * b * h)
    assert ak.konsol_sehim(P, L, E, b, h) == pytest.approx(d, rel=1e-12)
    assert ak.timoshenko_sehim(P, L, E, nu, b, h) == pytest.approx(dT, rel=1e-12)


def _satir(fark):
    fem = None if fark is None else 1.0 + fark
    return {"ad": "a", "formul": "f", "deger": 1.0, "birim": "mm", "fem": fem, "fark": fark}


@pytest.mark.parametrize(
    "farklar, beklenen",
    [
        ([0.05], "tamam"),
        ([0.0999], "tamam"),
        ([0.10], "tamam"),
        ([0.1001], "uyari"),
        ([-0.15], "uyari"),
        ([0.02, -0.3], "uyari"),
        ([None, 0.02], "tamam"),
    ],
)
def test_analitik_sapma_kurali(farklar, beklenen):
    """`|fark| > 0.10` → uyari, aksi tamam (iki yönlü, uydurma fem değerleriyle)."""
    k = ak.analitik_sapma_kontrolu([_satir(f) for f in farklar])
    assert set(k) == o.KONTROL_ALANLARI
    assert k["kimlik"] == "analitik_sapma"
    assert k["durum"] == beklenen


def test_analitik_sapma_fem_yok():
    assert ak.analitik_sapma_kontrolu([_satir(None)]) is None
    assert ak.analitik_sapma_kontrolu([]) is None


@pytest.mark.occt
def test_analitik_satirlari(plaka, kiris):
    """konsol_kiris δ, δ_T formüllerle (rel 1e-12); delikli_plaka Kt_g = 3.032; fark = fem / analitik − 1."""
    t, ag, m, _ = kiris()
    E, nu = t.malzeme.E, t.malzeme.nu
    I_ = 20.0 * 20.0**3 / 12
    d = 1000.0 * 200.0**3 / (3 * E * I_)
    dT = d + 1000.0 * 200.0 / (5 / 6 * E / (2 * (1 + nu)) * 400.0)

    bos = o.jt(ak.analitik_satirlari(t, None))
    assert all(r["fem"] is None and r["fark"] is None for r in bos)
    degerler = [r["deger"] for r in bos]
    assert any(v == pytest.approx(d, rel=1e-12) for v in degerler), degerler
    assert any(v == pytest.approx(dT, rel=1e-12) for v in degerler), degerler

    c = ak.coz(t, ag)
    satirlar = o.jt(ak.analitik_satirlari(t, c))
    fem_li = [r for r in satirlar if r["fem"] is not None]
    assert fem_li
    for r in fem_li:
        assert r["fark"] == pytest.approx(r["fem"] / r["deger"] - 1.0, rel=1e-12, abs=1e-15)
    J = o.jt(ak.analiz_json(t, ag, c))
    assert J["analitik"] == satirlar
    assert o.kontrol(J["kontroller"], "analitik_sapma") == o.jt(ak.analitik_sapma_kontrolu(satirlar))

    tp, _, _, _ = plaka()
    kt = [r for r in o.jt(ak.analitik_satirlari(tp, None)) if round(r["deger"], 3) == 3.032]
    assert kt, "delikli_plaka Heywood Kt_g satırı"


# ---------------------------------------------------------------- K19: yakınsama


@pytest.mark.slow
@pytest.mark.occt
def test_yakinsama(kiris):
    """Üç satır: h, h/1.5, h/2.25 ile ayrı ayrı kurulup çözülen modelin dugum, u_max, vm_max değerleri."""
    t, _, _, _ = kiris()
    satirlar = o.jt(ak.yakinsama(t))
    assert len(satirlar) == 3
    vm_son = []
    for r, k in zip(satirlar, (1.0, 1.5, 2.25), strict=True):
        h = t.h / k
        assert r["h"] == pytest.approx(h, rel=1e-12)
        agk = ak.ag_kur(t, h)
        m = ak.model_kur(t, agk)
        u, _, vm, _, _ = o.cozum(m)
        assert r["dugum"] == len(m.nodes)
        assert r["u_max"] == pytest.approx(float(np.linalg.norm(u, axis=1).max()), rel=1e-12)
        assert r["vm_max"] == pytest.approx(float(vm.max()), rel=1e-12)
        assert not r.get("neden")
        vm_son.append(float(vm.max()))
    _, ag, _, _ = kiris()
    c = ak.coz(t, ag)
    K = o.jt(ak.kontroller(t, ag, c, satirlar))
    fark = abs(vm_son[2] / vm_son[1] - 1.0)
    assert o.kontrol(K, "yakinsama")["durum"] == ("uyari" if fark > 0.05 else "tamam")
    assert "yakinsama" not in o.kimlikler(o.jt(ak.kontroller(t, ag, c, None)))


@pytest.mark.slow
@pytest.mark.occt
def test_yakinsama_max_nodes(kiris):
    """`max_nodes` aşılan satırda sayı yok, neden metni var (sahte sayı yok)."""
    t, ag, _, _ = kiris()
    n0 = len(o.ag_modeli(t)[0].nodes)
    t2 = dataclasses.replace(t, max_nodes=n0)
    satirlar = o.jt(ak.yakinsama(t2))
    assert satirlar[0]["dugum"] == n0 and satirlar[0]["u_max"] is not None
    for r in satirlar[1:]:
        assert (r["dugum"], r["u_max"], r["vm_max"]) == (None, None, None)
        assert isinstance(r["neden"], str) and r["neden"].strip()


# ---------------------------------------------------------------- K20: dışa aktarım (köprü düzeyi)


@pytest.mark.occt
def test_inp(plaka):
    from fileio.calculix import to_inp

    t, ag, m, _ = plaka()
    assert ak.inp(t, ag) == to_inp(m)
