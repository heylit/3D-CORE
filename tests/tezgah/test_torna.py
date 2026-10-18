"""
SPEC 25 — torna köprüsü (`tezgah/torna.py`): K1–K6.

Beklenen değerler köprüden değil, doğrudan SPEC 20 `Toolpath`'inden,
SPEC 21 okuyucusundan (`cam.gcode.lathe`),
SPEC 22 simülasyonundan (`cam.sim.simulate_lathe`) ve Teori bölümündeki kapalı formlardan hesaplanır.
SPEC 21 / 22 modülleri henüz yoksa ilgili testler atlanır.

Şema seçimi (SPEC metni yerini söylemiyor): K1'deki `plane`, `feed_mode`, `css`, `rpm` her işlemin
`Is["islemler"][i]` sözlüğünde, `Toolpath` alanlarıyla aynı adla durur (`plane`/`feed_mode` enum değeri).
"""

from __future__ import annotations

import json
import math
import re
import struct

import numpy as np
import pytest

from cam.model import ARCS, CamError, FeedMode, Plane
from tests.tezgah import torna_ornekleri as o
from tezgah.torna import (
    KONUM_EPS,
    devir,
    gcode_satirlari,
    hareketler,
    is_json,
    noktalar_coz,
    noktalar_ikili,
    sim_ikili,
    sim_kesit,
)


def _ornek_mil():
    from tezgah.ornekler_25 import kademeli_mil

    return kademeli_mil()


YAPICILAR = [
    pytest.param(o.kucuk_torna, id="kucuk"),
    pytest.param(_ornek_mil, id="kademeli_mil", marks=pytest.mark.occt),
]


@pytest.fixture(params=YAPICILAR)
def yapici(request):
    return request.param


def _lathe():
    return pytest.importorskip("cam.gcode.lathe", reason="SPEC 21 (cam.gcode.lathe) henüz yok")


def _lsim():
    pytest.importorskip("cam.sim.lathe", reason="SPEC 22 (cam.sim.simulate_lathe) henüz yok")
    from cam.sim import simulate_lathe

    return simulate_lathe


def _ops(tanim):
    return [isl.op for isl in tanim.islemler]


def _simule(tanim):
    """SPEC 22 simülasyonu, köprünün kullandığı girdilerle (kurulum, hücre; makine varsayılan)."""
    return _lsim()(_ops(tanim), tanim.kurulum, cell=tanim.hucre)


def _json_tur(x):
    return json.loads(json.dumps(x, allow_nan=False))


def _gcode_metni(G: list[dict]) -> str:
    return "\n".join(g["metin"] for g in G) + "\n"


def _takimlar(tanim) -> dict:
    return {op.tool.id: op.tool for op in _ops(tanim)}


def _stok(tanim):
    return tanim.kurulum.stock if hasattr(tanim.kurulum, "stock") else tanim.kurulum


# ---------------------------------------------------------------- K1: geri dönüş


def test_round_trip(yapici):
    """K1: JSON'a yazılıp okunan `Is` hareketleri SPEC 20 yollarıyla birebir; `tur == "torna"`."""
    tanim = yapici()
    J = _json_tur(is_json(tanim))
    assert J["tur"] == "torna"
    assert J["kurulum"]["stok"] == _stok(tanim).to_dict()
    H = J["hareketler"]
    assert H == _json_tur(hareketler(tanim))
    k = 0
    for i, op in enumerate(_ops(tanim)):
        a = np.array(op.start)
        for m in op.moves:
            h = H[k]
            assert h["islem"] == i
            assert h["g"] == {"G0": 0, "G1": 1, "G2": 2, "G3": 3}[m.type.value]
            assert h["a"] == list(a)
            assert h["b"] == list(m.end)
            assert h["b"][1] == 0.0
            assert h["F"] == m.feed
            if m.type in ARCS:
                assert h["c"] == list(m.center)
            else:
                assert "c" not in h or h["c"] is None
            a = np.array(m.end)
            k += 1
        isl = J["islemler"][i]
        assert isl["plane"] == Plane.ZX.value == op.plane.value
        assert isl["feed_mode"] == FeedMode.PER_REV.value == op.feed_mode.value
        assert isl["css"] == op.css
        assert isl["rpm"] == op.rpm
        assert isl["anahtar"] == tanim.islemler[i].anahtar
        assert isl["takim"]["T"] == op.tool.id
        assert isl["takim"]["r"] == op.tool.nose_r
    assert k == len(H)


def test_round_trip_ints_are_floats():
    """K1: koordinatlar float; JSON'dan geri okunan sayı türü değişmez (ör. 27 → 27.0)."""
    H = _json_tur(is_json(o.kucuk_torna()))["hareketler"]
    for h in H:
        for v in h["a"] + h["b"]:
            assert isinstance(v, float)


def test_milling_job_without_tur_is_milling():
    """K1: `tur` alanı olmayan eski (SPEC 24) iş freze sayılır; freze köprüsü torna demez."""
    from tests.tezgah import ornekler as fo
    from tezgah.kopru import is_json as freze_is_json

    pytest.importorskip("cam.sim", reason="SPEC 05 (cam.sim) henüz yok")
    J = freze_is_json(fo.kucuk_is())
    assert J.get("tur", "freze") == "freze"


# ---------------------------------------------------------------- K2: satır ↔ hareket


def _okuyucu_uc_noktalari(metin: str, tanim, satirlar: list[int]) -> dict[int, tuple]:
    """SPEC 21 okuyucusuna göre satır i işlendikten sonraki konum (x yarıçap) ve satırın hareket sayısı.

    Okuyucu satır bilgisi vermez; programın ilk i+1 satırı okunur ve son hareketin ucu alınır.
    """
    lathe = _lathe()
    S = metin.splitlines()
    tools = _takimlar(tanim)

    def oku(n: int) -> list:
        return [m for tp in lathe.read_lathe("\n".join(S[:n]) + "\n", tools) for m in tp.moves]

    sonuc = {}
    for i in satirlar:
        mv = oku(i + 1)
        n0 = len(oku(i)) if i else 0
        sonuc[i] = (np.array(mv[-1].end) if mv else None, len(mv) - n0)
    return sonuc


def test_line_move_ranges_partition_moves(yapici):
    """K2: `satir_hareket` aralıkları artan, ayrık ve her hareketi tam bir kez kapsar;
    `satir` alanı tersidir."""
    tanim = yapici()
    H = hareketler(tanim)
    G, SH = gcode_satirlari(tanim)
    assert len(G) == len(SH)
    kapsanan = []
    for i, ar in enumerate(SH):
        if ar is None:
            continue
        ilk, son = ar
        assert 0 <= ilk <= son < len(H)
        for k in range(ilk, son + 1):
            assert H[k]["satir"] == i
            kapsanan.append(k)
        assert G[i]["islem"] == H[ilk]["islem"] == H[son]["islem"]
    assert kapsanan == list(range(len(H)))


def test_gcode_is_spec21_writer(yapici):
    """K2: `gcode` metni SPEC 21 yazıcısının çıktısı satır satır (yön, takım değiştirme noktası işten)."""
    lathe = _lathe()
    tanim = yapici()
    G, _ = gcode_satirlari(tanim)
    beklenen = lathe.write_lathe(_ops(tanim), tanim.spindle, tanim.tool_change)
    assert [g["metin"] for g in G] == beklenen.splitlines()


def test_line_move_map(yapici):
    """K2: hareket satırının son hareketinin `b`'si, SPEC 21 okuyucusunun o satır için verdiği uçtan
    (çap → yarıçap okuyucuda) koordinat başına ≤ 5·10⁻⁴ mm;
    satır aralığının boyu satırın ürettiği hareket sayısı.

    SPEC 21 kontrolör çevrimi (G71/G70/G76) yazmaz: her hareket satırı tek hareket grubudur.
    Büyük işte satırların eşit aralıklı bir örneği denetlenir (ilk ve son hareket satırı dahil).
    """
    tanim = yapici()
    assert KONUM_EPS == pytest.approx(5e-4)
    H = hareketler(tanim)
    G, SH = gcode_satirlari(tanim)
    hareketli = [i for i, ar in enumerate(SH) if ar is not None]
    assert hareketli
    if len(hareketli) > 40:
        sec = np.unique(np.linspace(0, len(hareketli) - 1, 40).round().astype(int))
        hareketli = [hareketli[j] for j in sec]
    uc = _okuyucu_uc_noktalari(_gcode_metni(G), tanim, hareketli)
    for i in hareketli:
        p, n = uc[i]
        assert p is not None, f"satır {i} ({G[i]['metin']!r}): okuyucu hareket üretmedi"
        ilk, son = SH[i]
        b = np.array(H[son]["b"])
        assert np.max(np.abs(b - p)) <= 5e-4, f"satır {i}: {G[i]['metin']!r}"
        assert n == son - ilk + 1, f"satır {i}: {G[i]['metin']!r}"
    for i, ar in enumerate(SH):
        if re.search(r"\bG7[016]\b", G[i]["metin"]):  # çevrim satırı (yazılırsa) açılımın tamamını kapsar
            assert ar is not None


# ---------------------------------------------------------------- K3: DRO çap

_X = re.compile(r"(?<![A-Z])X([+-]?(?:\d+\.?\d*|\.\d+))")
_Z = re.compile(r"(?<![A-Z])Z([+-]?(?:\d+\.?\d*|\.\d+))")


def test_dro_diameter(yapici):
    """K3: hareket satırının DRO'su X = 2·x (satırın son hareketinin ucu), Z = z; satırda X / Z sözcüğü varsa
    sayısı DRO ile ≤ 5·10⁻⁴ mm aynı. Hareket üretmeyen satırda DRO yok (None)."""
    tanim = yapici()
    H = hareketler(tanim)
    G, SH = gcode_satirlari(tanim)
    for i, (g, ar) in enumerate(zip(G, SH, strict=True)):
        if ar is None:
            assert g.get("dro") is None, f"satır {i}: {g['metin']!r}"
            continue
        b = H[ar[1]]["b"]
        dro = g["dro"]
        assert dro["X"] == pytest.approx(2 * b[0], rel=1e-12, abs=1e-12), f"satır {i}"
        assert dro["Z"] == pytest.approx(b[2], rel=1e-12, abs=1e-12), f"satır {i}"
        metin = re.sub(r"\([^()]*\)", "", g["metin"])
        if (mx := _X.search(metin)) is not None:
            assert abs(float(mx.group(1)) - dro["X"]) <= 5e-4, f"satır {i}: {g['metin']!r}"
        if (mz := _Z.search(metin)) is not None:
            assert abs(float(mz.group(1)) - dro["Z"]) <= 5e-4, f"satır {i}: {g['metin']!r}"


def test_dro_diameter_is_twice_radius_known_line():
    """K3, elle: kucuk_torna'nın boy pasosunda x = 23 → DRO X = 46 olan bir satır vardır."""
    tanim = o.kucuk_torna()
    G, SH = gcode_satirlari(tanim)
    X = [g["dro"]["X"] for g, ar in zip(G, SH, strict=True) if ar is not None]
    assert any(abs(v - 46.0) <= 1e-12 for v in X)
    assert any(abs(v - 54.0) <= 1e-12 for v in X)  # alın başlangıcı x = 27


# ---------------------------------------------------------------- K4: devir


def _beklenen_devir(tanim, res) -> np.ndarray:
    """Nokta k için n_k: noktayı üreten adımın işleminin iş mili durumu (nokta 0: işlem 0)."""
    ops = _ops(tanim)
    P = res.points()
    op_k = [0] + [st.op for st in res.steps]
    n = np.empty(len(P))
    for k, (p, j) in enumerate(zip(P, op_k, strict=True)):
        tp = ops[j]
        x = abs(float(p[0]))
        if tp.css is None:
            n[k] = tp.rpm
        elif x == 0.0:
            n[k] = tp.rpm
        else:
            n[k] = min(1000.0 * tp.css / (math.pi * 2.0 * x), tp.rpm)
    return n


def test_spindle_speed(yapici):
    """K4: G96'da n = min(1000·Vc/(π·2x), n_max) (rel 1e-12), x = 0'da n_max; G97'de rpm."""
    tanim = yapici()
    n = np.asarray(devir(tanim), dtype=float)
    res = _simule(tanim)
    assert n.shape == (len(res.points()),)
    np.testing.assert_allclose(n, _beklenen_devir(tanim, res), rtol=1e-12, atol=0)


def test_spindle_speed_face_reaches_limit():
    """K4, elle: alın pasosu x = 0'a iner → o noktada n = n_max = 3000; x = 27'de n = 1000·200/(π·54)."""
    tanim = o.kucuk_torna()
    n = np.asarray(devir(tanim), dtype=float)
    res = _simule(tanim)
    P = res.points()
    eksen = [k for k, p in enumerate(P) if p[0] == 0.0 and abs(p[2] - 59.0) < 1e-12]
    assert eksen and all(n[k] == 3000.0 for k in eksen)
    bas = [k for k, p in enumerate(P) if p[0] == 27.0 and abs(p[2] - 59.0) < 1e-12]
    assert bas and n[bas[0]] == pytest.approx(1000 * 200 / (math.pi * 54), rel=1e-12)
    G97 = [k for k, st in enumerate(res.steps, start=1) if st.op == 1]
    assert G97 and all(n[k] == 1500.0 for k in G97)


def test_spindle_speed_g96_without_limit_raises():
    """K4: G96 altında n_max (G50) tanımsızsa CamError (sonsuz devir yok, altın kural 5)."""
    with pytest.raises(CamError):
        devir(o.g96_sinirsiz())


# ---------------------------------------------------------------- K5: süre


def test_times(yapici):
    """K5: toplam ve işlem başına süre SPEC 22 süre fonksiyonuyla aynı (rel 1e-12)."""
    tanim = yapici()
    res = _simule(tanim)
    J = is_json(tanim)
    assert J["sure"]["toplam"] == pytest.approx(res.total_time, rel=1e-12)
    assert len(J["sure"]["islem"]) == len(tanim.islemler)
    for s, r in zip(J["sure"]["islem"], res.op_times, strict=True):
        assert s == pytest.approx(r, rel=1e-12, abs=1e-12)
    kum = 0.0
    for i, isl in enumerate(J["islemler"]):
        assert isl["t0"] == pytest.approx(kum, rel=1e-12, abs=1e-9)
        kum += res.op_times[i]
        assert isl["t1"] == pytest.approx(kum, rel=1e-12, abs=1e-9)
    assert J["sure"]["kumulatif_url"] == f"/api/is/{tanim.ad}/noktalar"


def _alin_suresi(x1: float, x0: float, Vc: float, f: float, n_max: float) -> float:
    """Teori: t = 60·[π(x₁² − x_c²)/(1000·Vc·f) + (x_c − x₀)/(f·n_max)],
    x_c = 1000·Vc/(2π·n_max), [x₀, x₁]'e kırpılır."""
    xc = min(max(1000 * Vc / (2 * math.pi * n_max), x0), x1)
    return 60 * (math.pi * (x1**2 - xc**2) / (1000 * Vc * f) + (xc - x0) / (f * n_max))


@pytest.mark.parametrize(
    ("x1", "x0", "n_max", "durum"),
    [
        (25.0, 0.0, 2500.0, "x_c içeride"),  # x_c = 200000/(2π·2500) ≈ 12.73
        (25.0, 15.0, 2500.0, "x_c aralığın altında"),  # hep sınırsız bölge
        (10.0, 0.0, 2500.0, "x_c aralığın üstünde"),  # hep G50 sınırında
        (1000 * 200 / (2 * math.pi * 2500), 0.0, 2500.0, "x_c tam uçta"),
    ],
)
def test_times_face_closed_form(x1, x0, n_max, durum):
    """K5: sabit kesme hızında alın tornalama (Vc = 200 m/dk, f = 0.2 mm/dev) kapalı formla rel 1e-9."""
    Vc, f = 200.0, 0.2
    J = is_json(o.tek_alin(x1, x0, Vc, f, n_max))
    beklenen = _alin_suresi(x1, x0, Vc, f, n_max)
    assert J["sure"]["toplam"] == pytest.approx(beklenen, rel=1e-9), durum
    assert J["sure"]["islem"][0] == pytest.approx(beklenen, rel=1e-9), durum


def test_times_face_closed_form_sanity():
    """Kapalı formun kendisi: x_c dışarıdayken iki uç formüle iner (testin beklenen değeri doğru mu)."""
    Vc, f, n = 200.0, 0.2, 2500.0
    assert _alin_suresi(25, 15, Vc, f, n) == pytest.approx(60 * math.pi * (25**2 - 15**2) / (1000 * Vc * f))
    assert _alin_suresi(10, 0, Vc, f, n) == pytest.approx(60 * 10 / (f * n))


# ---------------------------------------------------------------- ikili nokta dizisi (K4, K5)

NOKTA_BLOKLARI = (("konum", "<f4", 3), ("zaman", "<f8", 1), ("satir", "<i4", 1), ("islem", "<i2", 1),
                  ("hizli", "u1", 1), ("yuk", "<f4", 1), ("hareket", "<i4", 1),
                  ("devir", "<f4", 1))  # fmt: skip


def _noktalari_oku(veri: bytes) -> dict[str, np.ndarray]:
    """Belgedeki biçimin bağımsız okuyucusu:
    SPEC 24 blokları + son blok devir float32[n]; bloklar 8'e tamamlı."""
    sema, n = struct.unpack_from("<II", veri, 0)
    assert sema == 1
    out, ofs = {}, 8
    for ad, dt, m in NOKTA_BLOKLARI:
        d = np.dtype(dt)
        out[ad] = np.frombuffer(veri, dtype=d, count=n * m, offset=ofs).copy()
        ofs += d.itemsize * n * m
        ofs += -ofs % 8
    assert ofs == len(veri)
    out["konum"] = out["konum"].reshape(n, 3)
    return out


def test_points_binary(yapici):
    """K4/K5: nokta dizisi SPEC 24 biçimi + devir;
    konum SPEC 22 noktaları, zaman kümülatif süre, devir n_k."""
    tanim = yapici()
    veri = noktalar_ikili(tanim)
    N = _noktalari_oku(veri)
    res = _simule(tanim)
    P = res.points()
    np.testing.assert_array_equal(N["konum"], P.astype(np.float32))
    np.testing.assert_allclose(N["zaman"], res.cumulative_time(), rtol=1e-12, atol=1e-12)
    assert N["zaman"][0] == 0.0 and np.all(np.diff(N["zaman"]) >= 0)
    np.testing.assert_array_equal(N["devir"], np.asarray(devir(tanim)).astype(np.float32))
    np.testing.assert_array_equal(N["islem"], np.array([0] + [st.op for st in res.steps], dtype=np.int16))
    C = noktalar_coz(veri)
    for ad in N:
        np.testing.assert_array_equal(C[ad], N[ad], err_msg=ad)


# ---------------------------------------------------------------- K6: sim olayları


def _sim_oku(veri: bytes) -> dict:
    """`sim_ikili` belgesindeki biçimin bağımsız okuyucusu."""
    sema, nz, m, sifir = struct.unpack_from("<IIII", veri, 0)
    assert sema == 1 and sifir == 0
    ofs = 16
    out = {"nz": nz, "m": m}
    for ad, dt, n in (("izgara", "<f8", 4), ("ofset", "<u4", nz + 1), ("k", "<i4", m), ("r_dis", "<f4", m),
                      ("r_ic", "<f4", m), ("islem", "<i2", m), ("hedef", "<f4", nz)):  # fmt: skip
        d = np.dtype(dt)
        out[ad] = np.frombuffer(veri, dtype=d, count=n, offset=ofs).copy()
        ofs += d.itemsize * n
        ofs += -ofs % 8
    assert ofs == len(veri)
    return out


def _kesit_oku(S: dict, k: int) -> tuple[np.ndarray, np.ndarray]:
    """k anındaki kesit: her hücrede k'si ≤ k olan son olay; yoksa (r_dis0, r_ic0)."""
    _, _, r0, ri0 = S["izgara"]
    dis = np.full(S["nz"], r0, dtype=np.float32)
    ic = np.full(S["nz"], ri0, dtype=np.float32)
    for i in range(S["nz"]):
        for j in range(S["ofset"][i], S["ofset"][i + 1]):
            if S["k"][j] <= k:
                dis[i], ic[i] = S["r_dis"][j], S["r_ic"][j]
    return dis, ic


def _dis_ic(kesit: list[tuple[float, float]]) -> tuple[float, float]:
    """SPEC 22 `outer()` / `inner()` tanımı: max u, min l; aralık yoksa 0."""
    if not kesit:
        return 0.0, 0.0
    return max(u for _, u in kesit), min(lo for lo, _ in kesit)


def _ornek_k(n: int) -> list[int]:
    if n <= 60:
        return list(range(n))
    return sorted(set(np.linspace(0, n - 1, 40).round().astype(int).tolist()))


def test_sim_events_reconstruct(yapici):
    """K6: her k için olaylardan kurulan (r_dis, r_ic), SPEC 22'nin k sonrası kesitinin hücre merkezlerindeki
    örneğiyle float32 birebir; son kesit SPEC 22'nin son durumu; ham değerler D/2, d/2."""
    tanim = yapici()
    veri = sim_ikili(tanim)
    S = _sim_oku(veri)
    z0, dz, r0, ri0 = S["izgara"]
    stok = _stok(tanim)
    assert r0 == stok.D / 2 and ri0 == stok.d / 2
    assert dz > 0 and S["nz"] > 0
    assert np.all(np.diff(S["ofset"].astype(np.int64)) >= 0) and S["ofset"][-1] == S["m"]
    for i in range(S["nz"]):
        ks = S["k"][S["ofset"][i] : S["ofset"][i + 1]]
        assert np.all(np.diff(ks) > 0), f"hücre {i}: k artan değil"
    res = _simule(tanim)
    g = res.rmap
    zc = z0 + (np.arange(S["nz"]) + 0.5) * dz
    stokta = (zc > stok.zmin) & (zc < stok.zmax)
    j = np.floor((zc - g.z0) / g.dz).astype(int)  # SPEC 22 ızgarasında z_c'yi içeren hücre
    assert np.all((j[stokta] >= 0) & (j[stokta] < g.nz))
    n = len(res.points())
    for k in _ornek_k(n):
        kesit = res.section_at(k)
        bek_dis = np.array([_dis_ic(kesit[jj])[0] for jj in j[stokta]], dtype=np.float32)
        bek_ic = np.array([_dis_ic(kesit[jj])[1] for jj in j[stokta]], dtype=np.float32)
        dis, ic = sim_kesit(veri, k)
        np.testing.assert_array_equal(dis[stokta], bek_dis, err_msg=f"k = {k}")
        np.testing.assert_array_equal(ic[stokta], bek_ic, err_msg=f"k = {k}")
        d2, i2 = _kesit_oku(S, k)
        np.testing.assert_array_equal(dis, d2, err_msg=f"k = {k}")
        np.testing.assert_array_equal(ic, i2, err_msg=f"k = {k}")
    son_dis, son_ic = sim_kesit(veri, n - 1)
    np.testing.assert_array_equal(son_dis[stokta], g.outer()[j[stokta]].astype(np.float32))
    np.testing.assert_array_equal(son_ic[stokta], g.inner()[j[stokta]].astype(np.float32))


def test_sim_initial_section_is_stock():
    """K6: k = 0 (ilk hareketten önce) kesit ham malzeme: her hücre D/2 ve d/2 (boru ham, d = 20)."""
    tanim = o.kucuk_torna(kurulum=o.stok(d=20.0))
    dis, ic = sim_kesit(sim_ikili(tanim), 0)
    S = _sim_oku(sim_ikili(tanim))
    zc = S["izgara"][0] + (np.arange(S["nz"]) + 0.5) * S["izgara"][1]
    stokta = (zc > o.ZMIN) & (zc < o.ZMAX)
    assert np.all(dis[stokta] == np.float32(25.0))
    assert np.all(ic[stokta] == np.float32(10.0))


def test_sim_target_nan_without_part():
    """K6: hedef parça yoksa hedef dizisi NaN."""
    S = _sim_oku(sim_ikili(o.kucuk_torna()))
    assert S["hedef"].shape == (S["nz"],) and np.all(np.isnan(S["hedef"]))


@pytest.mark.occt
def test_sim_target_is_part_outer_radius():
    """K6: hedef dizi, parçanın hücre merkezlerindeki dış yarıçapı (Ø40 silindir, z ∈ [0, 60] → 20)."""
    pytest.importorskip("build123d")
    from geometry.features import cylinder

    tanim = o.kucuk_torna(parca=cylinder(20.0, 60.0, name="hedef"))
    S = _sim_oku(sim_ikili(tanim))
    zc = S["izgara"][0] + (np.arange(S["nz"]) + 0.5) * S["izgara"][1]
    ic = (zc > 0.5) & (zc < 59.5)
    np.testing.assert_allclose(S["hedef"][ic], 20.0, atol=1e-2)  # ağ toleransı 0.01
