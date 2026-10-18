"""
SPEC 47b — çok eksen köprüsü (`tezgah/ekranlar/_cok_eksen_kopru.py`), K8–K12.

Beklenen değerler çekirdeğin kendisinden (SPEC 41 `to_machine`, `forward`; SPEC 42 `joint_path`, `deviation`,
`inverse_time`; SPEC 43 `simulate5`; SPEC 44 `poses`, `check`) testte ayrıca hesaplanır; köprü çıktısından
kopyalanmaz. İkili diziler köprünün `*_coz`'undan bağımsız olarak da okunur (`Okuyucu`, bayt düzeyi).

SPEC 41–44 kodu yoksa testler atlanır (`cekirdek()`); `[web]` yoksa da (`tezgah.ekranlar` A3 paketi).
Örnek işlerin varsayılan profilleri (kodlayıcının kabul edilen seçimi): `kubbe_5eksen` → `ac_besik_dar`,
diğerleri → `ac_besik`; `kubbe_5eksen`'in olaysız hâli `ornek("kubbe_5eksen", profil="ac_besik")`.

Nokta dizisi sözleşmesi (köprü belgesi): işlemler art arda; işlem j'nin noktaları `islemler[j].k0..k1`,
satırları 5 eksende `joint_path(ops[j], kin, wcs, L)`, 3+2'de `to_machine(ham[j], kin, wcs, L)`.
Noktanın takım ekseni: `k0 + 1 + i` noktası için `moves[i].axis`, `k0` (işlem başı) için `moves[0].axis`.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from cam.model import MoveType
from tests.tezgah.ekranlar.cok_eksen_ortak import (
    Okuyucu,
    cekirdek,
    json_tur,
    kontrol,
    moduller,
    ornek_is,
    ornekle,
)

ORNEKLER = ("egik_yuz_3arti2", "kubbe_5eksen", "kubbe_carpisma")
KONTROL_ALANLARI = {"kimlik", "baslik", "deger", "birim", "durum", "aciklama", "spec"}


def _kin(is_):
    return is_.model.profile.kinematics


def _k(is_) -> int:
    """Döner eksen sayısı."""
    return len(_kin(is_).rotary)


def _kaynak(is_) -> list:
    """Nokta dizisini üreten yollar: 5 eksen `ops`, 3+2 `ham` (köprü belgesi)."""
    return list(is_.ops) if is_.tur == "5eksen" else list(is_.ham)


def _q_beklenen(is_) -> list[np.ndarray]:
    kin, wcs, L = _kin(is_), is_.setup.wcs, is_.L
    if is_.tur == "5eksen":
        from cam.multiaxis.linearize import joint_path

        return [np.asarray(joint_path(op, kin, wcs, L), dtype=float) for op in is_.ops]
    from cam.multiaxis.indexed import to_machine

    return [np.asarray(to_machine(h, kin, wcs, L), dtype=float) for h in is_.ham]


def _eksenler(tp) -> np.ndarray:
    """Yolun noktalarındaki takım ekseni (n+1, 3); None → +Z."""
    a = [m.axis if m.axis is not None else (0.0, 0.0, 1.0) for m in tp.moves]
    return np.array([a[0]] + a, dtype=float)


def _noktalar(is_):
    kopru, _ = moduller()
    return kopru.noktalar_coz(kopru.noktalar_ikili(is_))


def _araliklar(is_) -> list[tuple[int, int]]:
    kopru, _ = moduller()
    return [(isl["k0"], isl["k1"]) for isl in kopru.cok_json(is_)["islemler"]]


# ---------------------------------------------------------------- ortak: JSON şekli


@pytest.mark.parametrize("ad", ORNEKLER)
def test_cok_json_sekli(ad):
    kopru, orn = moduller()
    is_ = ornek_is(ad)
    J = json_tur(kopru.cok_json(is_))
    assert J["sema"] == 1
    assert J["ad"] == ad
    assert J["tur"] == ("3arti2" if ad == "egik_yuz_3arti2" else "5eksen")
    assert J["profil"] == ("ac_besik_dar" if ad == "kubbe_5eksen" else "ac_besik")
    assert J["L"] == is_.L
    assert J["sim"] is None
    assert set(J["parametreler"]) == set(orn.PARAMETRELER)
    eksenler = J["tezgah"]["eksenler"]
    assert [e["ad"] for e in eksenler if e["tur"] == "doner"] == [a.name for a in _kin(is_).rotary]
    assert {e["ad"] for e in eksenler if e["tur"] == "dogrusal"} == {"X", "Y", "Z"}
    for k in J["kontroller"]:
        assert set(k) == KONTROL_ALANLARI
        assert k["durum"] in ("tamam", "uyari", "hata")
    # Simülasyon yokken SPEC 43 kontrolleri listede yok.
    assert not {"govde_carpma", "cakma", "sure"} & {k["kimlik"] for k in J["kontroller"]}
    # İşlemler art arda ve nokta dizisini tam kaplıyor.
    araliklar = [(isl["k0"], isl["k1"]) for isl in J["islemler"]]
    assert [isl["i"] for isl in J["islemler"]] == list(range(len(is_.ops)))
    assert araliklar[0][0] == 0
    for (_, k1), (k0, _) in zip(araliklar, araliklar[1:], strict=False):
        assert k0 == k1 + 1
    assert araliklar[-1][1] == len(_noktalar(is_)["zaman"]) - 1


# ---------------------------------------------------------------- K8: eklem değerleri


@pytest.mark.parametrize("ad", ["kubbe_5eksen", "egik_yuz_3arti2"])
def test_eklemler(ad):
    is_ = ornek_is(ad)
    from cam.multiaxis.kinematics import forward
    from cam.multiaxis.linearize import inverse_time

    d = _noktalar(is_)
    k = _k(is_)
    n = len(d["zaman"])
    assert d["q"].shape == (n, 3 + k)
    assert d["q"].dtype == np.float64
    assert d["konum"].shape == (n, 3) and d["a"].shape == (n, 3)

    araliklar = _araliklar(is_)
    for j, (q_op, tp, (k0, k1)) in enumerate(zip(_q_beklenen(is_), _kaynak(is_), araliklar, strict=True)):
        assert k1 - k0 + 1 == len(q_op) == len(tp.moves) + 1
        # q: çekirdekle birebir (float64).
        np.testing.assert_array_equal(d["q"][k0 : k1 + 1], q_op)
        assert np.all(d["islem"][k0 : k1 + 1] == j)
        if is_.tur == "3arti2":
            # 3+2: döner eksenler işlem boyunca sabit.
            assert np.ptp(q_op[:, 3:], axis=0).max() <= 1e-9
        # G93: inverse_time ile float32 birebir; işlem başında ve hızlı harekette 0.
        hizli = np.array([m.type is MoveType.RAPID for m in tp.moves])
        np.testing.assert_array_equal(d["hizli"][k0 + 1 : k1 + 1], hizli.astype(np.uint8))
        g93 = np.asarray(inverse_time(tp, q_op), dtype=float).astype(np.float32)
        g93[hizli] = 0
        assert d["g93"][k0] == 0
        np.testing.assert_array_equal(d["g93"][k0 + 1 : k1 + 1], g93)

    # Takım ekseni birim (float32).
    np.testing.assert_allclose(np.linalg.norm(d["a"].astype(float), axis=1), 1.0, atol=1e-6)
    # Zaman: azalmayan, 0'dan başlar.
    assert d["zaman"][0] == 0
    assert np.all(np.diff(d["zaman"]) >= 0)
    # Konum ve eksen, eklem değerlerinin ileri kinematiğiyle tutarlı (float32 yuvarlaması içinde).
    kin, wcs, L = _kin(is_), is_.setup.wcs, is_.L
    for i in ornekle(n):
        tip, a = forward(kin, d["q"][i], L, wcs)
        np.testing.assert_allclose(d["konum"][i], tip, atol=1e-4)
        np.testing.assert_allclose(d["a"][i], a, atol=1e-6)


@pytest.mark.parametrize("ad", ["kubbe_5eksen", "egik_yuz_3arti2"])
def test_noktalar_bayt(ad):
    """`noktalar` ikilisi belgedeki biçimde (bağımsız okuma) ve `noktalar_coz` ile aynı."""
    kopru, _ = moduller()
    is_ = ornek_is(ad)
    veri = kopru.noktalar_ikili(is_)
    assert veri == kopru.noktalar_ikili(is_)  # belirlenimci
    o = Okuyucu(veri)
    sema, n, k = o.oku("u4", 3)
    assert (sema, k) == (1, _k(is_))
    bag = {
        "konum": o.oku("f4", 3 * n).reshape(n, 3),
        "zaman": o.oku("f8", n),
        "islem": o.oku("i2", n),
        "hizli": o.oku("u1", n),
        "a": o.oku("f4", 3 * n).reshape(n, 3),
        "q": o.oku("f8", n * (3 + k)).reshape(n, 3 + k),
        "g93": o.oku("f4", n),
    }
    o.bitti()
    d = kopru.noktalar_coz(veri)
    for ad_, dizi in bag.items():
        assert d[ad_].dtype == dizi.dtype, ad_
        np.testing.assert_array_equal(d[ad_], dizi, err_msg=ad_)


# ---------------------------------------------------------------- K9: pozlar


@pytest.mark.parametrize("ad", ["kubbe_5eksen", "egik_yuz_3arti2"])
def test_pozlar(ad):
    kopru, _ = moduller()
    is_ = ornek_is(ad)
    from cam.multiaxis.machine import poses

    J = kopru.cok_json(is_)
    govdeler = J["tezgah"]["govdeler"]
    m = len(govdeler)
    assert m >= 1
    q = _noktalar(is_)["q"]
    n = len(q)

    veri = kopru.pozlar_ikili(is_)
    o = Okuyucu(veri)
    sema, n_, m_ = o.oku("u4", 3)
    assert (sema, n_, m_) == (1, n, m)
    ham = o.oku("f4", n * m * 12).reshape(n, m, 12)
    o.bitti()
    P = kopru.pozlar_coz(veri)
    assert P["R"].shape == (n, m, 3, 3) and P["t"].shape == (n, m, 3)
    np.testing.assert_array_equal(P["R"].reshape(n, m, 9), ham[:, :, :9])
    np.testing.assert_array_equal(P["t"], ham[:, :, 9:])

    kin = _kin(is_)
    tip0 = np.array(kin.gauge) - is_.L * np.array(kin.spindle)
    o_wcs = np.array(is_.setup.wcs.origin)
    konum = _noktalar(is_)["konum"]
    halka = [g["halka"] for g in govdeler]
    for i in ornekle(n):
        dp = poses(is_.model, q[i], is_.setup, is_.tool)
        for b, h in enumerate(halka):
            R, t = dp[h]
            np.testing.assert_array_equal(P["R"][i, b], np.asarray(R).astype(np.float32))
            np.testing.assert_array_equal(P["t"][i, b], np.asarray(t).astype(np.float32))
        # Göreli görünüm: iş mili ve iş parçası halkalarının pozlarından takım ucunun WCS konumu.
        R_m, t_m = _halka_pozu(P, halka, dp, i, "is_mili")
        R_p, t_p = _halka_pozu(P, halka, dp, i, "is_parcasi")
        uc_makine = R_m @ tip0 + t_m
        uc_wcs = R_p.T @ (uc_makine - t_p) - o_wcs
        np.testing.assert_allclose(uc_wcs, konum[i], atol=1e-4)


def _halka_pozu(P, halka, dp, i, ad):
    """Halkanın pozu: `pozlar` ikilisinden (o halkada gövde varsa), yoksa çekirdeğinki float32'de."""
    if ad in halka:
        b = halka.index(ad)
        return P["R"][i, b].astype(float), P["t"][i, b].astype(float)
    R, t = dp[ad]
    return np.asarray(R).astype(np.float32).astype(float), np.asarray(t).astype(np.float32).astype(float)


# ---------------------------------------------------------------- K10: olaylar


def _olaylar_beklenen(is_) -> list[dict]:
    from cam.multiaxis.collision import check

    olaylar = check(is_.model, is_.setup, list(is_.ops), is_.L, tcp=True, clearance=is_.clearance)
    return json_tur([dataclasses.asdict(e) for e in olaylar])


@pytest.mark.parametrize(
    ("ad", "profil"),
    [
        ("kubbe_5eksen", None),
        ("kubbe_5eksen", "ac_besik"),
        ("kubbe_carpisma", None),
        ("egik_yuz_3arti2", None),
    ],
)
def test_olaylar(ad, profil):
    kopru, _ = moduller()
    is_ = ornek_is(ad, profil)
    J = json_tur(kopru.cok_json(is_))
    beklenen = _olaylar_beklenen(is_)
    assert J["olaylar"] == beklenen
    assert json_tur(kopru.olaylar(is_)) == beklenen

    turler = [e["kind"] for e in beklenen]
    sinir, carpma = kontrol(J["kontroller"], "eksen_siniri"), kontrol(J["kontroller"], "tezgah_carpma")
    if (ad, profil) == ("kubbe_5eksen", None):
        assert is_.profil == "ac_besik_dar"
        assert "eksen_siniri" in turler
        assert sinir["durum"] == "hata"
    elif (ad, profil) == ("kubbe_5eksen", "ac_besik"):
        assert is_.profil == "ac_besik"
        assert turler == []
        assert sinir["durum"] == "tamam" and carpma["durum"] == "tamam"
    elif ad == "kubbe_carpisma":
        assert "tezgah_carpma" in turler
        assert carpma["durum"] == "hata"
        adlar = {g["ad"] for g in J["tezgah"]["govdeler"]} | {b.name for b in is_.model.bodies}
        for e in beklenen:
            if e["kind"] == "tezgah_carpma":
                assert e["a"] in adlar and e["b"] in adlar
    # Kontrol durumu olay sayısından.
    assert sinir["durum"] == ("hata" if "eksen_siniri" in turler else "tamam")
    assert carpma["durum"] == ("hata" if "tezgah_carpma" in turler else "tamam")
    # Her olayın t'si nokta dizisinin süre dizisinde k ile k+1 arasında.
    zaman = _noktalar(is_)["zaman"]
    for e in beklenen:
        assert 0 <= e["k"] < len(zaman) - 1
        assert zaman[e["k"]] <= e["t"] <= zaman[e["k"] + 1]


# ---------------------------------------------------------------- K11: sapma


def _sapma_oku(veri: bytes):
    o = Okuyucu(veri)
    sema, s, ara = o.oku("u4", 3)
    assert sema == 1
    e = o.oku("f4", 2 * s).reshape(s, 2)
    tcp = o.oku("f4", s * ara * 3).reshape(s, ara, 3)
    o.bitti()
    return e, tcp, int(ara)


def test_sapma():
    kopru, _ = moduller()
    is_ = ornek_is("kubbe_5eksen")
    from cam.multiaxis.kinematics import forward
    from cam.multiaxis.linearize import deviation

    kin, wcs, L = _kin(is_), is_.setup.wcs, is_.L
    veri = kopru.sapma_ikili(is_)
    e, tcp, ara = _sapma_oku(veri)
    assert ara == kopru.SAPMA_ARA
    d = kopru.sapma_coz(veri)
    np.testing.assert_array_equal(d["e"], e)
    np.testing.assert_array_equal(d["tcp"], tcp)

    # Segmentler: her işlemin ardışık iki noktası, işlemler sırayla.
    seg = []
    for op, q_op in zip(is_.ops, _q_beklenen(is_), strict=True):
        p, a = op.points(), _eksenler(op)
        seg += [(q_op[i], q_op[i + 1], p[i], p[i + 1], a[i], a[i + 1]) for i in range(len(op.moves))]
    assert len(e) == len(seg)
    u = (np.arange(ara) + 1) / (ara + 1)
    for i in ornekle(len(seg)):
        q0, q1, p0, p1, a0, a1 = seg[i]
        e_p, e_a = deviation(kin, wcs, L, q0, q1, p0, p1, a0, a1, 0.5)
        np.testing.assert_array_equal(e[i], np.array([e_p, e_a], dtype=np.float32))
        uclar = np.array([forward(kin, q0 + ui * (q1 - q0), L, wcs)[0] for ui in u], dtype=np.float32)
        np.testing.assert_array_equal(tcp[i], uclar)

    # Doğrusallaştırılmış yol toleransta, kontrol tamam; özet ikilinin en büyükleriyle aynı.
    oz = kopru.sapma_ozeti(is_)
    assert (oz["tol_p"], oz["tol_a"]) == (is_.tol_p, is_.tol_a)
    assert oz["e_p_max"] <= is_.tol_p and oz["e_a_max"] <= is_.tol_a
    assert oz["e_p_max"] == pytest.approx(float(e[:, 0].max()), rel=1e-6, abs=1e-12)
    assert oz["e_a_max"] == pytest.approx(float(e[:, 1].max()), rel=1e-6, abs=1e-12)
    J = kopru.cok_json(is_)
    assert json_tur(J["sapma"]) == json_tur(oz)
    assert kontrol(J["kontroller"], "dogrusallastirma")["durum"] == "tamam"

    # linearize atlanmış (ham finish5) yol: sapma tol_p'yi aşar, kontrol hata.
    ham = dataclasses.replace(is_, ops=list(is_.ham))
    oz_ham = kopru.sapma_ozeti(ham)
    assert oz_ham["e_p_max"] > is_.tol_p
    assert kontrol(kopru.kontroller(ham), "dogrusallastirma")["durum"] == "hata"


# ---------------------------------------------------------------- K12: tri-dexel


def _dexel_oku(veri: bytes) -> list[dict]:
    o = Okuyucu(veri)
    sema, g = o.oku("u4", 2)
    assert sema == 1
    sonuc = []
    for _ in range(g):
        x0, y0, z0, dx, dy, dz = o.oku("f8", 6)
        nx, ny, nz = (int(v) for v in o.oku("u4", 3))
        goruntu = {"izgara": dict(x0=x0, y0=y0, z0=z0, dx=dx, dy=dy, dz=dz, nx=nx, ny=ny, nz=nz)}
        for eksen in ("z", "x", "y"):
            (isin,) = o.oku("u4", 1)
            sayi = o.oku("u2", int(isin))
            uc = o.oku("f4", 2 * int(sayi.sum())).reshape(-1, 2)
            bas = np.concatenate([[0], np.cumsum(sayi)]).astype(int)
            goruntu[eksen] = [uc[bas[r] : bas[r + 1]] for r in range(int(isin))]
        sonuc.append(goruntu)
    o.bitti()
    return sonuc


# eksen → (dış indeks boyu, iç indeks boyu) adları
_ISINLAR = {"z": ("nx", "ny"), "x": ("ny", "nz"), "y": ("nx", "nz")}


@pytest.mark.slow
def test_tridexel():
    kopru, _ = moduller()
    is_ = ornek_is("egik_yuz_3arti2")
    from cam.sim.simulate5 import simulate5

    # Zincirleme simulate5, testte ayrıca.
    beklenen, onceki = [], None
    for op in is_.ops:
        r = simulate5(
            [op],
            is_.stock,
            kopru.SIM_HUCRE,
            part=is_.part,
            initial=None if onceki is None else onceki.tridexel,
        )
        beklenen.append(r)
        onceki = r
    sims = kopru.simule(is_)
    assert len(sims) == len(beklenen) == len(is_.ops)
    for r, b in zip(sims, beklenen, strict=True):
        assert r.removed_volume == b.removed_volume
        assert r.total_time == b.total_time
        assert [dataclasses.asdict(c) for c in r.collisions] == [dataclasses.asdict(c) for c in b.collisions]

    son = beklenen[-1].tridexel
    oz = json_tur(kopru.sim_ozeti(sims))
    assert oz["removed_volume"] == pytest.approx(is_.stock.volume - son.volume(), rel=1e-9)
    assert oz["total_time"] == pytest.approx(sum(b.total_time for b in beklenen), rel=1e-12)
    assert oz["collisions"] == json_tur([dataclasses.asdict(c) for b in beklenen for c in b.collisions])
    if is_.part is None:
        assert oz["rest_volume"] is None and oz["gouge_volume"] is None
    else:
        assert oz["rest_volume"] == pytest.approx(beklenen[-1].rest_volume(), rel=1e-12)
        assert oz["gouge_volume"] == pytest.approx(beklenen[-1].gouge_volume(), rel=1e-12)
    J = json_tur(kopru.cok_json(is_, sims))
    assert J["sim"] == oz
    kimlikler = {k["kimlik"] for k in J["kontroller"]}
    assert {"govde_carpma", "sure"} <= kimlikler
    assert kontrol(J["kontroller"], "govde_carpma")["durum"] == ("hata" if oz["collisions"] else "tamam")
    if is_.part is not None:
        cakma = kontrol(J["kontroller"], "cakma")
        assert cakma["durum"] == ("hata" if oz["gouge_volume"] > kopru.GOUGE_TOL else "tamam")

    # dexel ikilisi: işlem sonu görüntüleri, her ışının aralıkları son TriDexel ile float32 birebir.
    veri = kopru.dexel_ikili([r.tridexel for r in sims])
    bag = _dexel_oku(veri)
    coz = kopru.dexel_coz(veri)
    assert len(bag) == len(coz) == len(sims)
    for g, (b, c, r) in enumerate(zip(bag, coz, beklenen, strict=True)):
        T = r.tridexel
        izgara = {a: getattr(T, a) for a in ("x0", "y0", "z0", "dx", "dy", "dz", "nx", "ny", "nz")}
        assert b["izgara"] == izgara, g
        assert c["izgara"] == b["izgara"]
        for eksen, (dis, ic) in _ISINLAR.items():
            ni, nj = izgara[dis], izgara[ic]
            assert len(b[eksen]) == len(c[eksen]) == ni * nj, (g, eksen)
            for i in range(ni):
                for j in range(nj):
                    r_ = i * nj + j
                    ar = np.array(T.intervals(eksen, i, j), dtype=np.float32).reshape(-1, 2)
                    np.testing.assert_array_equal(b[eksen][r_], ar)
                    np.testing.assert_array_equal(np.array(c[eksen][r_], dtype=np.float32).reshape(-1, 2), ar)


# ---------------------------------------------------------------- gövde ağı


def test_govde_agi():
    kopru, _ = moduller()
    is_ = ornek_is("kubbe_carpisma")
    from cam.multiaxis.machine import Box, Capsule

    govdeler = {g["ad"]: g for g in kopru.cok_json(is_)["tezgah"]["govdeler"]}
    sekiller = {b.name: b.shape for b in is_.model.bodies}
    for ad, g in govdeler.items():
        veri = kopru.govde_ikili(is_.model, ad)
        o = Okuyucu(veri)
        sema, nv, nt = (int(v) for v in o.oku("u4", 3))
        V = o.oku("f4", 3 * nv).reshape(nv, 3)
        T = o.oku("u4", 3 * nt).reshape(nt, 3)
        o.bitti()
        d = kopru.govde_coz(veri)
        np.testing.assert_array_equal(d["V"], V)
        np.testing.assert_array_equal(d["T"], T)
        assert sema == 1 and T.max() < nv
        if ad not in sekiller:
            continue
        sekil = sekiller[ad]
        if isinstance(sekil, Box):
            assert g["sekil"] == "kutu" and nt == 12
            # Kutu köşeleri: center ± R·half (halka çerçevesinde, sıfır konumu).
            c, h, R = np.array(sekil.center), np.array(sekil.half), np.array(sekil.R, dtype=float)
            yerel = (V.astype(float) - c) @ R
            np.testing.assert_allclose(np.abs(yerel), np.broadcast_to(h, yerel.shape), atol=1e-4)
        elif isinstance(sekil, Capsule):
            assert g["sekil"] == "kapsul"
            # Her köşe kapsül yüzeyinde: doğru parçasına uzaklık r.
            p, q, r = np.array(sekil.p), np.array(sekil.q), sekil.r
            w = q - p
            s = np.clip(((V.astype(float) - p) @ w) / (w @ w), 0, 1)
            uz = np.linalg.norm(V - (p + s[:, None] * w), axis=1)
            np.testing.assert_allclose(uz, r, atol=1e-4)
    with pytest.raises(KeyError):
        kopru.govde_ikili(is_.model, "olmayan_govde")


# ---------------------------------------------------------------- *_coz hataları


@pytest.mark.parametrize("ad", ["noktalar", "pozlar", "sapma"])
def test_coz_hatalari(ad):
    kopru, _ = moduller()
    is_ = ornek_is("kubbe_5eksen", "ac_besik")
    from cam.model import CamError

    veri = getattr(kopru, f"{ad}_ikili")(is_)
    coz = getattr(kopru, f"{ad}_coz")
    with pytest.raises(CamError):
        coz((2).to_bytes(4, "little") + veri[4:])  # bilinmeyen sürüm
    with pytest.raises(CamError):
        coz(veri[: len(veri) // 2])  # kısa


# ---------------------------------------------------------------- parametre ve parmak izi (saf)


def test_parametre_uygula_saf():
    kopru, _ = moduller()
    is_ = ornek_is("kubbe_5eksen", "ac_besik")
    from cam.model import CamError

    _, orn = moduller()
    yeni = kopru.parametre_uygula(is_, "tilt", 15.0)
    assert yeni is not is_ and yeni.tilt == 15.0 and is_.tilt == orn.TILT
    beklenen = orn.ornek("kubbe_5eksen", "ac_besik", tilt=15.0)
    assert json_tur(kopru.cok_json(yeni)) == json_tur(kopru.cok_json(beklenen))
    assert kopru.sure(yeni) - kopru.sure(is_) == pytest.approx(
        _noktalar(beklenen)["zaman"][-1] - _noktalar(is_)["zaman"][-1], rel=1e-12, abs=1e-12
    )
    assert kopru.sure(is_) == _noktalar(is_)["zaman"][-1]
    # Parmak izi: aynı girdi aynı, girdi değişince farklı.
    assert kopru.parmak_izi(is_) == kopru.parmak_izi(orn.ornek("kubbe_5eksen", "ac_besik"))
    assert kopru.parmak_izi(yeni) != kopru.parmak_izi(is_)
    assert len(kopru.parmak_izi(is_)) == 64
    with pytest.raises(CamError):
        kopru.parametre_uygula(is_, "bilinmeyen", 1.0)
    for anahtar, deger in (("tol_p", 0.0), ("tol_a", -1.0), ("L", 0.0), ("L", -5.0)):
        with pytest.raises(CamError):
            kopru.parametre_uygula(is_, anahtar, deger)


def test_ornek_hatalari():
    cekirdek()
    _, orn = moduller()
    from cam.model import CamError

    with pytest.raises(KeyError):
        orn.ornek("olmayan_ornek")
    with pytest.raises(CamError):
        orn.ornek("kubbe_5eksen", profil="olmayan_profil")
    with pytest.raises(CamError):
        orn.ornek("kubbe_5eksen", bilinmeyen=1.0)
    with pytest.raises(CamError):
        orn.tezgah_modeli("olmayan_profil")
    # Dar profil: aynı tezgâh, A sınırı daha dar.
    genis, dar = orn.tezgah_modeli("ac_besik"), orn.tezgah_modeli("ac_besik_dar")
    A_g = next(a for a in genis.profile.kinematics.rotary if a.name == "A")
    A_d = next(a for a in dar.profile.kinematics.rotary if a.name == "A")
    assert A_d.max - A_d.min < A_g.max - A_g.min
    assert [b.name for b in dar.bodies] == [b.name for b in genis.bodies]
