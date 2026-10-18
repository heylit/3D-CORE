"""
SPEC 24 — köprü (`tezgah/kopru.py`): K1 geri dönüş, K2 canlı bağ, K3 süre, K6 sim ikili dizisi,
ikili nokta dizisinin biçimi.

Testler yalnızca SPEC 24 metnine, `tezgah/kopru.py` iskeletindeki imza ve belgelere ve `cam` paketinin
herkese açık fonksiyonlarına (SPEC 03, 04, 05) dayanır. Beklenen değerler `cam.model.Toolpath`,
`cam.gcode.write` / `read` ve `cam.sim.simulate` çıktılarından ya da analitik formüllerden gelir.

K3, K6 ve nokta dizisi SPEC 05'e (`cam.sim`) bağlıdır: `cam.sim` yoksa atlanır.

Nokta dizisinin sonunda iskelet belgesine eklenen blok (kod thread'inin biçim notu, koordinatör üzerinden):
`hareket: int32[n]`, noktayı oraya getiren `Is["hareketler"]` indeksi; nokta 0'da ve bağlantı noktalarında −1.
"""

from __future__ import annotations

import json
import struct

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL, read, write
from cam.model import ARCS, CamError, MoveType, Toolpath
from tests.tezgah import ornekler as o
from tezgah import SEMA
from tezgah.kopru import (
    KONUM_EPS,
    gcode_satirlari,
    hareketler,
    is_json,
    noktalar_coz,
    noktalar_ikili,
    sim_ikili,
    sim_yuzey,
)


def _flans():
    from tezgah.isler import ornek_is

    return ornek_is("flans-plakasi")


ISLER = {
    "kucuk-grbl": lambda: o.kucuk_is(GRBL),
    "kucuk-fanuc": lambda: o.kucuk_is(FANUC),
    "flans": _flans,
}


@pytest.fixture(params=sorted(ISLER))
def yapici(request):
    """İşi kuran fonksiyon. İş testin içinde kurulur: iskeletteki NotImplementedError fixture'da değil
    test gövdesinde düşsün (conftest bunu "uygulanmamış" sayar)."""
    return ISLER[request.param]


def _json_tur(x):
    """JSON'a yazıp geri oku (K1: float JSON'da kayıpsız olmalı)."""
    return json.loads(json.dumps(x, allow_nan=False))


def _sim():
    return pytest.importorskip("cam.sim", reason="SPEC 05 (cam.sim) henüz yok")


def _simule(tanim, cell: float = 1.0):
    sim = _sim()
    part_z = None
    if tanim.parca_ag is not None:
        grid = sim.ZMap.from_stock(tanim.kurulum.stock, cell)
        part_z = sim.mesh_zmap(*tanim.parca_ag, grid)
    return sim.simulate(o.ops(tanim), tanim.kurulum.stock, cell=cell, dialect=tanim.dialect, part_z=part_z)


def _beklenen_yollar(tanim) -> list[Toolpath]:
    """İşlem başına çekirdeğin yolu: Toolpath olduğu gibi, DrillOp kanonik açılımıyla."""
    yollar = []
    for i in tanim.islemler:
        op = i.op
        yollar.append(op if isinstance(op, Toolpath) else op.to_toolpath(tanim.dialect))
    return yollar


# ---------------------------------------------------------------- K1: köprü geri dönüşü


def test_toolpath_round_trip(yapici):
    """K1: hareketler JSON'a yazılıp okununca uç noktalar, merkezler, F ve türler yolla birebir aynı."""
    tanim = yapici()
    H = _json_tur(hareketler(tanim))
    yollar = _beklenen_yollar(tanim)
    assert len(H) == sum(len(tp.moves) for tp in yollar)

    k = 0
    for i, tp in enumerate(yollar):
        onceki = list(tp.start)
        for m in tp.moves:
            h = H[k]
            assert h["islem"] == i
            assert h["g"] == int(m.type.value[1:])
            assert h["a"] == onceki
            assert h["b"] == list(m.end)
            if m.type in ARCS:
                assert h["c"] == list(m.center)
            else:
                assert h.get("c") is None
            if m.type is MoveType.RAPID:
                assert h["F"] is None
            else:
                assert h["F"] == m.feed
            assert isinstance(h["satir"], int)
            onceki = list(m.end)
            k += 1


def test_round_trip_json_has_plain_floats():
    """K1: sayılar Python float'ı; JSON metninden okunan değer bellekteki değerle aynı (numpy float32 yok)."""
    H = hareketler(o.kucuk_is())
    metin = json.dumps(H, allow_nan=False)
    assert json.loads(metin) == H
    for h in H:
        for p in (h["a"], h["b"]):
            assert all(type(v) is float for v in p)


def test_moves_validate_ops():
    """Her op önce doğrulanır: geçersiz yol CamError (sessiz düzeltme yok)."""
    tanim = o.kucuk_is()
    tanim.islemler[0].op.rpm = 0.0
    with pytest.raises(CamError):
        hareketler(tanim)


# ---------------------------------------------------------------- K2: canlı bağ


def _gcode_metni(G: list[dict]) -> str:
    return "\n".join(g["metin"] for g in G) + "\n"


def test_gcode_is_writer_output(yapici):
    """`gcode` satırları `cam.gcode.write` çıktısının kendisi, satır satır."""
    tanim = yapici()
    G, SH = gcode_satirlari(tanim)
    assert _gcode_metni(G) == write(o.ops(tanim), tanim.dialect, safe_z=tanim.safe_z)
    assert len(SH) == len(G)
    assert G[0]["islem"] is None
    assert G[-1]["islem"] is None


def test_line_move_ranges_partition_moves(yapici):
    """satir_hareket aralıkları artan, ayrık ve her hareketi tam bir kez kapsar; `satir` alanı tersidir."""
    tanim = yapici()
    H = hareketler(tanim)
    G, SH = gcode_satirlari(tanim)
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


def _okuyucu_uc_noktalari(metin: str, tanim, satirlar: list[int]) -> dict[int, tuple]:
    """SPEC 04 okuyucusuna göre satır i işlendikten sonraki konum ve o satırın ürettiği hareket sayısı.

    Okuyucu satır bilgisi vermez; programın ilk i+1 satırı okunur ve son hareketin ucu alınır.
    """
    S = metin.splitlines()
    sonuc = {}
    for i in satirlar:
        onek = "\n".join(S[: i + 1]) + "\n"
        onceki = "\n".join(S[:i]) + "\n"
        mv = [m for tp in read(onek, o.takimlar(tanim), tanim.dialect) for m in tp.moves]
        n0 = sum(len(tp.moves) for tp in read(onceki, o.takimlar(tanim), tanim.dialect)) if i else 0
        sonuc[i] = (np.array(mv[-1].end) if mv else None, len(mv) - n0)
    return sonuc


def test_line_move_map_matches_reader(yapici):
    """K2: hareket satırının son hareketinin `b`'si okuyucunun o satır için verdiği uçtan ≤ 5e-4 mm.

    Delik çevrimi satırı (Fanuc G83) kanonik açılımın son noktasına eşlenir. Büyük işte satırların
    eşit aralıklı bir örneği denetlenir (ilk ve son hareket satırı her zaman dahil).
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
        p, _ = uc[i]
        assert p is not None, f"satır {i} ({G[i]['metin']!r}): okuyucu hareket üretmedi"
        b = np.array(H[SH[i][1]]["b"])
        assert np.max(np.abs(b - p)) <= 5e-4, f"satır {i}: {G[i]['metin']!r}"


@pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["grbl", "fanuc"])
def test_line_move_counts_small_job(dialect):
    """Küçük işte her hareket satırının aralık boyu, okuyucunun o satırda ürettiği hareket sayısına eşit
    (Fanuc'ta G83 satırı bir deliğin tüm gagalama hareketlerini kapsar)."""
    tanim = o.kucuk_is(dialect)
    G, SH = gcode_satirlari(tanim)
    hareketli = [i for i, ar in enumerate(SH) if ar is not None]
    uc = _okuyucu_uc_noktalari(_gcode_metni(G), tanim, hareketli)
    for i in hareketli:
        ilk, son = SH[i]
        assert uc[i][1] == son - ilk + 1, f"satır {i}: {G[i]['metin']!r}"
    if dialect is FANUC:
        G83 = [i for i, g in enumerate(G) if "G83" in g["metin"]]
        assert G83 and SH[G83[0]][1] > SH[G83[0]][0]


# ---------------------------------------------------------------- K3: süre


def test_times_match_cam_sim(yapici):
    """K3: toplam ve işlem başına süre SPEC 05 süre tahminiyle aynı (rel 1e-12)."""
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
    assert J["islemler"][-1]["t1"] == pytest.approx(J["sure"]["toplam"], rel=1e-12)


def test_times_single_g1_analytic():
    """K3: tek doğru G1 için t = 60·L/F (L = 100 mm, F = 600 mm/dk → 10 s)."""
    _sim()
    J = is_json(o.tek_g1_is(L=100.0, F=600.0))
    assert J["sure"]["toplam"] == pytest.approx(10.0, rel=1e-12)
    assert J["sure"]["islem"] == [pytest.approx(10.0, rel=1e-12)]


# ---------------------------------------------------------------- Is sözlüğü


ANAHTARLAR = {
    "sema",
    "ad",
    "kurulum",
    "islemler",
    "hareketler",
    "gcode",
    "satir_hareket",
    "sure",
    "kontroller",
}


def test_is_json_schema(yapici):
    """`Is` sözlüğü: alanlar, sürüm, kurulum, işlemler; JSON'a nan'sız yazılır ve parçalarla tutarlı."""
    tanim = yapici()
    _sim()
    J = is_json(tanim)
    assert set(J) == ANAHTARLAR
    assert J["sema"] == SEMA == 1
    assert J["ad"] == tanim.ad
    assert _json_tur(J) == J

    s = tanim.kurulum.stock
    k = J["kurulum"]
    assert k["stok"] == {"x0": s.xmin, "x1": s.xmax, "y0": s.ymin, "y1": s.ymax, "z0": s.zmin, "z1": s.zmax}
    assert k["wcs"] == tanim.kurulum.wcs.code
    assert k["malzeme"] == tanim.malzeme

    assert J["hareketler"] == _json_tur(hareketler(tanim))
    G, SH = gcode_satirlari(tanim)
    assert J["gcode"] == _json_tur(G)
    assert J["satir_hareket"] == _json_tur(SH)
    assert J["sure"]["kumulatif_url"] == f"/api/is/{tanim.ad}/noktalar"

    assert [i["i"] for i in J["islemler"]] == list(range(len(tanim.islemler)))
    for isl, tan in zip(J["islemler"], tanim.islemler, strict=True):
        assert isl["anahtar"] == tan.anahtar
        assert isl["ad"] == tan.ad
        assert isl["parametreler"] == tan.parametreler
        assert isl["takim"]["T"] == tan.op.tool.id
        assert isl["takim"]["R"] == pytest.approx(tan.op.tool.D / 2, rel=1e-15)
        assert isinstance(isl["takim"]["ad"], str) and isinstance(isl["takim"]["tur"], str)
        assert isl["t0"] <= isl["t1"]


# ---------------------------------------------------------------- ikili nokta dizisi


def _hizala(n: int) -> int:
    return (n + 7) // 8 * 8


def _bloklari_oku(veri: bytes, baslik_fmt: str, bloklar: list[tuple[str, int]]) -> tuple[tuple, list]:
    """Bağımsız çözücü: başlık + (numpy dtype, eleman sayısı) blokları; her blok 8 bayta sıfırla hizalı."""
    bas = struct.unpack_from(baslik_fmt, veri, 0)
    yer = _hizala(struct.calcsize(baslik_fmt))
    diziler = []
    for dtype, n in bloklar:
        dt = np.dtype(dtype)
        a = np.frombuffer(veri, dtype=dt, count=n, offset=yer)
        son = yer + n * dt.itemsize
        assert veri[son : _hizala(son)] == bytes(_hizala(son) - son), "dolgu sıfır olmalı"
        diziler.append(a)
        yer = _hizala(son)
    assert len(veri) == yer, "veri uzunluğu blokların toplamı olmalı"
    return bas, diziler


def _noktalari_oku(veri: bytes) -> dict[str, np.ndarray]:
    sema, n = struct.unpack_from("<II", veri, 0)
    _, d = _bloklari_oku(
        veri,
        "<II",
        [("<f4", 3 * n), ("<f8", n), ("<i4", n), ("<i2", n), ("u1", n), ("<f4", n), ("<i4", n)],
    )
    return {
        "sema": sema,
        "konum": d[0].reshape(n, 3),
        "zaman": d[1],
        "satir": d[2],
        "islem": d[3],
        "hizli": d[4],
        "yuk": d[5],
        "hareket": d[6],
    }


def test_points_binary_layout_and_decoder(yapici):
    """Nokta dizisi belgede yazılan little-endian düzende; `noktalar_coz` bağımsız çözücüyle aynı."""
    tanim = yapici()
    veri = noktalar_ikili(tanim)
    assert isinstance(veri, bytes)
    B = _noktalari_oku(veri)
    assert B["sema"] == SEMA
    C = noktalar_coz(veri)
    for ad in ("konum", "zaman", "satir", "islem", "hizli", "yuk", "hareket"):
        np.testing.assert_array_equal(np.asarray(C[ad]), B[ad])
    assert C["konum"].shape == (len(B["zaman"]), 3)


def test_points_match_cam_sim(yapici):
    """Noktalar SPEC 05 adımlarıdır: konum, kümülatif süre, işlem, G0 bayrağı, satır ve yük."""
    tanim = yapici()
    res = _simule(tanim)
    B = _noktalari_oku(noktalar_ikili(tanim))
    P = res.points()
    n = len(P)
    assert len(B["zaman"]) == n
    np.testing.assert_array_equal(B["konum"], P.astype(np.float32))
    np.testing.assert_array_equal(B["zaman"], res.cumulative_time())
    assert B["zaman"][0] == 0.0
    assert np.all(np.diff(B["zaman"]) >= 0)
    assert B["zaman"][-1] == pytest.approx(is_json(tanim)["sure"]["toplam"], rel=1e-12)

    adimlar = res.steps
    np.testing.assert_array_equal(B["islem"][1:], [s.op for s in adimlar])
    np.testing.assert_array_equal(B["hizli"][1:], [int(s.type is MoveType.RAPID) for s in adimlar])

    # Bağlantı olmayan adımlar sırasıyla köprünün hareketleridir; noktanın satırı hareketin satırı.
    H = hareketler(tanim)
    G, _ = gcode_satirlari(tanim)
    gercek = [k for k, s in enumerate(adimlar, start=1) if not s.link]
    assert len(gercek) == len(H)
    for k, h in zip(gercek, H, strict=True):
        assert B["satir"][k] == h["satir"]
    # hareket bloğu: noktayı getiren hareketin indeksi; nokta 0 ve bağlantılarda −1.
    beklenen_hareket = np.full(n, -1, dtype=np.int32)
    beklenen_hareket[gercek] = np.arange(len(H))
    np.testing.assert_array_equal(B["hareket"], beklenen_hareket)
    assert np.all((B["satir"] >= -1) & (B["satir"] < len(G)))

    # Yük normalize: 0..1, malzeme kaldıran işte en büyüğü 1; kaldırmayan adımın yükü 0.
    yuk = B["yuk"]
    assert np.all((yuk >= 0) & (yuk <= 1))
    if res.removed_volume > 0:
        assert yuk.max() == pytest.approx(1.0, abs=1e-6)
    for k, s in enumerate(adimlar, start=1):
        if s.removed == 0:
            assert yuk[k] == 0


# ---------------------------------------------------------------- K6: sim ikili dizisi


def _sim_oku(veri: bytes) -> dict:
    sema, nx, ny, m = struct.unpack_from("<IIII", veri, 0)
    bas, d = _bloklari_oku(
        veri, "<IIII", [("<f8", 6), ("<u4", nx * ny + 1), ("<i4", m), ("<f4", m), ("<i2", m)]
    )
    x0, y0, dx, dy, z_ust, z_alt = d[0]
    return {
        "sema": sema, "nx": nx, "ny": ny, "m": m,
        "x0": x0, "y0": y0, "dx": dx, "dy": dy, "z_ust": z_ust, "z_alt": z_alt,
        "ofset": d[1], "k": d[2], "z": d[3], "islem": d[4],
    }  # fmt: skip


def _yuzey_kur(S: dict, k: int) -> np.ndarray:
    """Belgedeki tanım: her hücrede k'si ≤ k olan son olayın z'si; yoksa z_ust."""
    Z = np.full(S["nx"] * S["ny"], np.float32(S["z_ust"]), dtype=np.float32)
    for c in range(S["nx"] * S["ny"]):
        a, b = S["ofset"][c], S["ofset"][c + 1]
        ks = S["k"][a:b]
        sec = np.nonzero(ks <= k)[0]
        if len(sec):
            Z[c] = S["z"][a + sec[-1]]
    return Z.reshape(S["ny"], S["nx"])


@pytest.mark.parametrize("hucre", [1.0, 2.0])
def test_sim_events_reconstruct(hucre):
    """K6: olay listesinden her k için kurulan yüzey, SPEC 05'in aynı k'daki z-haritasıyla float32 birebir."""
    tanim = o.kucuk_is()
    res = _simule(tanim, cell=hucre)
    veri = sim_ikili(tanim, hucre=hucre)
    S = _sim_oku(veri)
    zm = res.zmap
    assert S["sema"] == SEMA
    assert (S["nx"], S["ny"]) == (zm.nx, zm.ny)
    assert (S["x0"], S["y0"], S["dx"], S["dy"]) == (zm.x0, zm.y0, zm.dx, zm.dy)
    assert S["z_ust"] == tanim.kurulum.stock.zmax
    assert S["z_alt"] == tanim.kurulum.stock.zmin

    # Olaylar SPEC 05'in olay listesidir.
    np.testing.assert_array_equal(S["ofset"], res.offsets)
    np.testing.assert_array_equal(S["k"], res.event_k)
    np.testing.assert_array_equal(S["z"], np.asarray(res.event_z).astype(np.float32))
    np.testing.assert_array_equal(S["islem"], [res.steps[k - 1].op for k in res.event_k])
    for c in range(S["nx"] * S["ny"]):
        assert np.all(np.diff(S["k"][S["ofset"][c] : S["ofset"][c + 1]]) > 0)

    n = len(res.points()) - 1
    for k in sorted({0, 1, n // 3, n // 2, n - 1, n}):
        beklenen = res.zmap_at(k).astype(np.float32)
        np.testing.assert_array_equal(_yuzey_kur(S, k), beklenen)
        Y = sim_yuzey(veri, k)
        assert Y.dtype == np.float32 and Y.shape == (zm.ny, zm.nx)
        np.testing.assert_array_equal(Y, beklenen)
    np.testing.assert_array_equal(sim_yuzey(veri, n), zm.z.astype(np.float32))


def test_sim_events_sample_job():
    """K6: örnek flanş işinde son yüzey SPEC 05'in son z-haritası; başlangıç yüzeyi stok üstü."""
    tanim = _flans()
    res = _simule(tanim)
    veri = sim_ikili(tanim)
    n = len(res.points()) - 1
    np.testing.assert_array_equal(sim_yuzey(veri, n), res.zmap.z.astype(np.float32))
    np.testing.assert_array_equal(sim_yuzey(veri, n // 2), res.zmap_at(n // 2).astype(np.float32))
    assert np.all(sim_yuzey(veri, 0) == np.float32(tanim.kurulum.stock.zmax))
