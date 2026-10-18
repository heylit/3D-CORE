"""SPEC 58 — süre ve maliyet: K1 süre, K2 kalemler, K3 ham malzeme, K4 eksik veri, K5 takım payı, K6 kademe,
K7 oran sınırları, K9 gizlilik; Ek: K1b (SPEC 72) ve K5b (SPEC 59), ilgili SPEC main'de değilse skip.

Testler sadece SPEC 58 metninden (ve koordinatörün onayladığı dört varsayılandan) yazıldı; `atolye/maliyet.py`
uygulama kodu okunmadı. Beklenen değerler §1–§4 formülleriyle bu dosyada elle hesaplanır:
    t_parca(n) = Σ_b [t_isleme(b) + t_yukle(b)] + Σ_b t_hazirlik(b) / n
    tezgah   = Σ_b (t_isleme + t_yukle) · U_m(b) / 3600
    hazirlik = Σ_b t_hazirlik · (U_m(b) + U_i) / 3600 / n
    iscilik  = Σ_b (t_isleme + t_yukle) · U_i · k_op / 3600
    malzeme  = fiyat[€/kg] · 1000 · ρ · V_ham · (1 + f_fire)          (ρ t/mm³, V mm³ → kütle t)
    takim    = Σ_satır c_kenar · (t_kesme[s] / 60) / T_omur[dk]
    fiyat    = M · (1 + g) · (1 + k)
t_isleme(b) föyden okunur (`JobSheet.setups[b].time`), t_kesme `ToolRow.time`.
Uydurma iş: SPEC 38 Ek A iki bağlamalı iş (`tests/atolye/ek_a.py`); ücretler ve C45 kaydı uydurma.
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import pytest

from atolye.is_foyu import JobSheet, build_job_sheet
from atolye.maliyet import (
    KALEM_ADLARI,
    Kalem,
    Maliyet,
    ModelError,
    Ucretler,
    ham_hacim,
    kademeler,
    maliyet,
    ucretleri_oku,
)
from cam.model import CylinderStock, MachineProfile, Move, MoveType, Setup, Stock, ToolLibrary, Toolpath, Wcs
from cam.sim import Machine
from malzeme.model import Malzeme
from tests.atolye import ek_a

REL = 1e-12
KOK = Path(__file__).resolve().parents[2]

U_I = 30.0  # €/saat işçilik
K_OP = 0.5
G = 0.2
K = 0.15
FIRE = 0.05
U_M = {"VMC-A": 60.0, "VMC-B": 80.0}
TAKIM = {"freze6": (12.0, 30.0), "matkap5": (8.0, 20.0)}  # (kenar €, kenar ömrü dk)
FIYAT = 1.5  # €/kg
RHO = 7.85e-9  # t/mm³
SURELER = [(60.0, 1800.0), (45.0, 900.0)]  # bağlama başına (yükle s, hazırlık s)
DIS = [("Isıl işlem", 4.5), ("Kaplama", 2.25)]
STOK = Stock(0, 0, 0, 100, 60, 30)
V_PRIZMA = 104 * 64 * 34  # p = 2


def ucret_sozlugu(**degis) -> dict:
    d = {
        "sema": 1,
        "aciklama": "UYDURMA test ücretleri",
        "para_birimi": "EUR",
        "iscilik_saat": U_I,
        "operator_orani": K_OP,
        "genel_gider": G,
        "kar_payi": K,
        "fire_orani": FIRE,
        "tezgah_saat": dict(U_M),
        "varsayilan_sureler": {"yukle_s": 60.0, "hazirlik_s": 1800.0},
        "malzeme_fiyati": {"1.0503": FIYAT},
        "takim": {ad: {"kenar_eur": c, "kenar_omru_dk": T} for ad, (c, T) in TAKIM.items()},
        "kesim_payi": {"prizma_mm": 2.0, "testere_mm": 3.0, "alin_mm": 1.0},
    }
    d.update(degis)
    return d


def ucretler(**degis) -> Ucretler:
    return Ucretler.from_dict(ucret_sozlugu(**degis))


def c45(fiyat: float | None = None) -> Malzeme:
    return Malzeme(
        id="1.0503",
        name="C45",
        standart="EN 10083-2",
        grup="celik",
        kaynak="uydurma test kaydı",
        rho=RHO,
        fiyat=fiyat,
    )


def profil(ad: str) -> MachineProfile:
    return MachineProfile(ad, "grbl", rpm_max=12000.0, feed_max=5000.0)


PROFILLER = [profil("VMC-A"), profil("VMC-B")]


def is_foyu() -> JobSheet:
    """SPEC 38 Ek A: bağlama 1 (cep, delik, 4 delik), bağlama 2 (yüz alma)."""
    return build_job_sheet(
        "Ek A",
        [ek_a.setup(), ek_a.setup2()],
        [[ek_a.tp1(), ek_a.tp2(), ek_a.drill4()], [ek_a.face2()]],
        ek_a.lib(),
        "C45",
        machine=ek_a.machine(),
    )


def calistir(n: int, job: JobSheet | None = None, **kw) -> Maliyet:
    args = dict(sureler=SURELER, dis_islem=DIS)
    args.update(kw)
    u = args.pop("u", None) or ucretler()
    return maliyet(
        job or is_foyu(),
        args.pop("profiller", PROFILLER),
        args.pop("stok", STOK),
        args.pop("malzeme", c45()),
        u,
        n,
        **args,
    )


# ---------------------------------------------------------------- elle hesap


def el_hesabi(job: JobSheet, n: int) -> dict[str, float]:
    T = [s.time for s in job.setups]
    yuk = [y for y, _ in SURELER]
    haz = [h for _, h in SURELER]
    um = [U_M["VMC-A"], U_M["VMC-B"]]
    tezgah = sum((T[b] + yuk[b]) * um[b] for b in range(2)) / 3600
    hazirlik = sum(haz[b] * (um[b] + U_I) for b in range(2)) / 3600 / n
    iscilik = sum(T[b] + yuk[b] for b in range(2)) * U_I * K_OP / 3600
    malzeme = FIYAT * 1000 * RHO * V_PRIZMA * (1 + FIRE)
    takim = sum(TAKIM[r.name][0] * (r.time / 60) / TAKIM[r.name][1] for s in job.setups for r in s.tools)
    dis = sum(c for _, c in DIS)
    M = tezgah + hazirlik + iscilik + malzeme + takim + dis
    return {
        "t_parca": sum(T) + sum(yuk) + sum(haz) / n,
        "tezgah": tezgah,
        "hazirlik": hazirlik,
        "iscilik": iscilik,
        "malzeme": malzeme,
        "takim": takim,
        "dis_islem": dis,
        "M": M,
        "fiyat": M * (1 + G) * (1 + K),
    }


# ---------------------------------------------------------------- K1 süre


@pytest.mark.parametrize("n", [1, 10])
def test_sure(n):
    job = is_foyu()
    assert len(job.setups) == 2
    m = calistir(n, job)
    assert isinstance(m, Maliyet)
    assert m.n == n
    # t_isleme = JobSheet.setups[b].time (föyden; yeniden hesap yok)
    T = [s.time for s in job.setups]
    beklenen = T[0] + 60 + T[1] + 45 + (1800 + 900) / n
    assert m.t_parca_s == pytest.approx(beklenen, rel=REL)
    assert m.t_parca_s == pytest.approx(el_hesabi(job, n)["t_parca"], rel=REL)


def test_sure_foyden_okunur():
    # föydeki süre değişirse (aynı iş, farklı tezgâh hızı modeli) t_parca doğrudan onu izler
    job = is_foyu()
    hizli = build_job_sheet(
        "Ek A",
        [ek_a.setup(), ek_a.setup2()],
        [[ek_a.tp1(), ek_a.tp2(), ek_a.drill4()], [ek_a.face2()]],
        ek_a.lib(),
        "C45",
        machine=Machine(rapid=(12000, 12000, 6000), accel=None, tool_change=4),
    )
    assert sum(s.time for s in hizli.setups) != sum(s.time for s in job.setups)
    m = calistir(1, hizli)
    assert m.t_parca_s == pytest.approx(sum(s.time for s in hizli.setups) + 105 + 2700, rel=REL)


def test_sure_varsayilan_sureler():
    # sureler = None → her bağlamaya varsayilan_sureler (yukle_s 60, hazirlik_s 1800)
    job = is_foyu()
    a = calistir(10, job, sureler=None)
    b = calistir(10, job, sureler=[(60.0, 1800.0), (60.0, 1800.0)])
    assert a == b
    assert a.t_parca_s == pytest.approx(sum(s.time for s in job.setups) + 120 + 3600 / 10, rel=REL)


def test_sure_kaynagi_uyarisi():
    # Ek 1: SPEC 72 zaman profili verilmeyen her tezgâh için uyarı; tezgah kalemi kaynağı söyler (Ek 3)
    m = calistir(1)
    for ad in ("VMC-A", "VMC-B"):
        assert f"Süre SPEC 05 modelinden (72 zaman profili yok: {ad})" in m.uyarilar
    tezgah = next(k for k in m.kalemler if k.ad == "tezgah")
    assert "süre: SPEC 05 (iş föyü)" in tezgah.aciklama


@pytest.mark.parametrize("sayi", [1, 3])
def test_sure_profil_sayisi_baglama_sayisina_esit(sayi):
    with pytest.raises(ModelError):
        calistir(1, profiller=[profil("VMC-A")] * sayi)


def test_sure_sureler_sayisi_baglama_sayisina_esit():
    with pytest.raises(ModelError):
        calistir(1, sureler=[(60.0, 1800.0)])


# ---------------------------------------------------------------- K2 kalemler


@pytest.mark.parametrize("n", [1, 10])
def test_kalemler(n):
    job = is_foyu()
    m = calistir(n, job)
    e = el_hesabi(job, n)
    assert [k.ad for k in m.kalemler] == list(KALEM_ADLARI)
    assert KALEM_ADLARI == ("tezgah", "hazirlik", "iscilik", "malzeme", "takim", "dis_islem")
    for k in m.kalemler:
        assert isinstance(k, Kalem)
        assert k.tutar_eur == pytest.approx(e[k.ad], rel=REL), k.ad
    assert m.ara_toplam_eur == pytest.approx(sum(k.tutar_eur for k in m.kalemler), rel=REL)
    assert m.ara_toplam_eur == pytest.approx(e["M"], rel=REL)
    # fiyat = M · (1 + g) · (1 + k), çarpımsal (Kararlar 2)
    assert m.fiyat_eur == pytest.approx(e["fiyat"], rel=REL)
    assert m.fiyat_eur == pytest.approx(m.ara_toplam_eur * 1.2 * 1.15, rel=REL)


def test_kalemler_aciklama_girdileri_icerir():
    m = calistir(10)
    a = {k.ad: k.aciklama for k in m.kalemler}
    assert all(isinstance(v, str) and v for v in a.values())
    assert "60" in a["tezgah"] and "80" in a["tezgah"]  # U_m(b)
    assert "30" in a["iscilik"]  # U_i
    assert "0.5" in a["iscilik"] or "0,5" in a["iscilik"]  # k_op
    assert "10" in a["hazirlik"]  # n
    assert "1.5" in a["malzeme"] or "1,5" in a["malzeme"]  # €/kg
    assert "12" in a["takim"] and "30" in a["takim"]  # c_kenar, T_omur
    assert "kenar ömrü (yerel dosya)" in a["takim"]  # Ek 3
    assert "4.5" in a["dis_islem"] or "4,5" in a["dis_islem"]


def test_kalemler_sifir_gider_kar():
    # g = k = 0 → fiyat = ara toplam
    m = calistir(1, u=ucretler(genel_gider=0.0, kar_payi=0.0))
    assert m.fiyat_eur == pytest.approx(m.ara_toplam_eur, rel=REL)


def test_kalemler_fire_yok():
    # fire_orani dosyada yoksa 0 (varsayılan): malzeme = fiyat · 1000 · ρ · V_ham
    d = ucret_sozlugu()
    del d["fire_orani"]
    m = calistir(1, u=Ucretler.from_dict(d))
    malz = next(k for k in m.kalemler if k.ad == "malzeme")
    assert malz.tutar_eur == pytest.approx(FIYAT * 1000 * RHO * V_PRIZMA, rel=REL)


def test_kalemler_dis_islem_adetten_bagimsiz():
    a = next(k for k in calistir(1).kalemler if k.ad == "dis_islem")
    b = next(k for k in calistir(200).kalemler if k.ad == "dis_islem")
    assert a.tutar_eur == b.tutar_eur == pytest.approx(6.75, rel=REL)


# ---------------------------------------------------------------- K3 ham malzeme


def test_ham():
    u = ucretler()
    # 100×60×30 prizma, p = 2 → (100 + 4)(60 + 4)(30 + 4)
    assert ham_hacim(Stock(0, 0, 0, 100, 60, 30), u) == pytest.approx(104 * 64 * 34, rel=REL)
    assert ham_hacim(Stock(-50, -30, -30, 50, 30, 0), u) == pytest.approx(104 * 64 * 34, rel=REL)
    # Ø40×120 çubuk, testere 3, alın 1 → π·20²·124
    assert ham_hacim(CylinderStock(40, -120, 0), u) == pytest.approx(math.pi * 20**2 * 124, rel=REL)


def test_ham_malzeme_tutari_prizma_ve_cubuk():
    # C45 ρ = 7.85e-9 t/mm³, yerel fiyat 1.5 €/kg, fire 0.05
    for stok, V in ((STOK, V_PRIZMA), (CylinderStock(40, -120, 0), math.pi * 20**2 * 124)):
        m = calistir(1, stok=stok)
        malz = next(k for k in m.kalemler if k.ad == "malzeme")
        assert malz.tutar_eur == pytest.approx(1.5 * 1000 * 7.85e-9 * V * 1.05, rel=REL)


def test_ham_fiyat_onceligi():
    # yerel malzeme_fiyati, Malzeme.fiyat'tan önce gelir; yerelde yoksa Malzeme.fiyat
    yerel = calistir(1, malzeme=c45(fiyat=9.0))
    malz = next(k for k in yerel.kalemler if k.ad == "malzeme")
    assert malz.tutar_eur == pytest.approx(1.5 * 1000 * RHO * V_PRIZMA * 1.05, rel=REL)
    kayit = calistir(1, malzeme=c45(fiyat=2.0), u=ucretler(malzeme_fiyati={}))
    malz = next(k for k in kayit.kalemler if k.ad == "malzeme")
    assert malz.tutar_eur == pytest.approx(2.0 * 1000 * RHO * V_PRIZMA * 1.05, rel=REL)


def test_ham_yerlesik_c45():
    # SPEC 66 yerleşik C45: ρ = 7.85e-9, fiyat boş (D7) → yerel fiyat 1.5 €/kg
    from malzeme.kutuphane import yerlesik

    m45 = yerlesik().get("1.0503")
    assert m45.rho == pytest.approx(7.85e-9, rel=REL)
    m = calistir(1, malzeme=m45)
    malz = next(k for k in m.kalemler if k.ad == "malzeme")
    assert malz.tutar_eur == pytest.approx(1.5 * 1000 * 7.85e-9 * V_PRIZMA * 1.05, rel=REL)


# ---------------------------------------------------------------- K4 eksik veri


@pytest.fixture
def ucret_dosyasi(tmp_path):
    """Ücret dosyasını varsayılan adıyla yazar ve ucretleri_oku ile okur."""

    def yaz(**degis) -> tuple[Ucretler, Path]:
        yol = tmp_path / "atolye-ucretleri.json"
        yol.write_text(json.dumps(ucret_sozlugu(**degis)), encoding="utf-8")
        return ucretleri_oku(yol), yol

    return yaz


def test_eksik_fiyat(ucret_dosyasi):
    u, _ = ucret_dosyasi(malzeme_fiyati={})
    with pytest.raises(ModelError, match=r"1\.0503") as e:
        calistir(1, u=u, malzeme=c45(fiyat=None))
    assert "malzeme_fiyati" in str(e.value)
    assert "atolye-ucretleri.json" in str(e.value)


def test_eksik_tezgah_ucreti(ucret_dosyasi):
    u, _ = ucret_dosyasi(tezgah_saat={"VMC-A": 60.0})
    with pytest.raises(ModelError, match="VMC-B") as e:
        calistir(1, u=u)
    assert "tezgah_saat" in str(e.value)
    assert "atolye-ucretleri.json" in str(e.value)


def test_eksik_takim_omru(ucret_dosyasi):
    takim = {
        "freze6": {"kenar_eur": 12.0, "kenar_omru_dk": None},
        "matkap5": {"kenar_eur": 8.0, "kenar_omru_dk": 20.0},
    }
    u, _ = ucret_dosyasi(takim=takim)
    with pytest.raises(ModelError, match="freze6") as e:
        calistir(1, u=u)
    assert "kenar_omru_dk" in str(e.value)
    assert "atolye-ucretleri.json" in str(e.value)


def test_eksik_takim_kaydi(ucret_dosyasi):
    u, _ = ucret_dosyasi(takim={"freze6": {"kenar_eur": 12.0, "kenar_omru_dk": 30.0}})
    with pytest.raises(ModelError, match="matkap5"):
        calistir(1, u=u)


def test_eksik_ucret_dosyasi(tmp_path):
    yol = tmp_path / "yok" / "atolye-ucretleri.json"
    with pytest.raises(ModelError) as e:
        ucretleri_oku(yol)
    mesaj = str(e.value)
    assert "Atölye ücret dosyası yok" in mesaj
    assert str(yol) in mesaj
    assert "examples/58_atolye_ucretleri_ornek.json" in mesaj


def test_eksik_varsayilan_yol(tmp_path, monkeypatch):
    # varsayılan yol yerel_parcalar/atolye-ucretleri.json (çalışma klasörüne göre)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ModelError, match="yerel_parcalar/atolye-ucretleri.json"):
        ucretleri_oku()


@pytest.mark.parametrize(
    "degis",
    [
        {"bilinmeyen_alan": 1},
        {"sema": 2},
        {"iscilik_saat": -1.0},
        {"tezgah_saat": {"VMC-A": -60.0}},
        {"malzeme_fiyati": {"1.0503": float("nan")}},
        {"iscilik_saat": float("inf")},
    ],
    ids=["bilinmeyen", "sema2", "negatif_iscilik", "negatif_tezgah", "nan_fiyat", "inf_iscilik"],
)
def test_eksik_bozuk_ucret_sozlugu(degis):
    with pytest.raises(ModelError):
        Ucretler.from_dict(ucret_sozlugu(**degis))


def test_ucretler_sozluk_gidis_donus(ucret_dosyasi):
    u, yol = ucret_dosyasi()
    assert Ucretler.from_dict(u.to_dict()) == u
    assert u.iscilik_saat == U_I and u.operator_orani == K_OP and u.fire_orani == FIRE


def test_eksik_hicbir_kalem_nan_degil():
    m = calistir(50)
    for k in m.kalemler:
        assert math.isfinite(k.tutar_eur) and k.tutar_eur >= 0
    assert math.isfinite(m.fiyat_eur) and m.fiyat_eur > 0


# ---------------------------------------------------------------- K5 takım payı


def k5_isi() -> JobSheet:
    """Tek bağlama, tek takım (freze6): G1 6 mm + 294 mm, F100 → 3.6 + 176.4 = 180 s = 3 dk kesme."""
    st = Setup("uzun", Wcs("G54", (0.0, 0.0, 0.0)), Stock(0, 0, -20, 300, 40, 0))
    tp = Toolpath(
        "uzun",
        ek_a.T1(),
        start=(2, 20, 5),
        moves=[Move(MoveType.LINEAR, (2, 20, -1), 100), Move(MoveType.LINEAR, (296, 20, -1), 100)],
        rpm=8000,
    )
    return build_job_sheet("K5", [st], [[tp]], ToolLibrary([ek_a.T1()]), "C45", machine=ek_a.machine())


def k5_maliyet(**kw) -> Maliyet:
    job = k5_isi()
    assert [(r.name, r.time) for r in job.setups[0].tools] == [("freze6", pytest.approx(180.0, rel=REL))]
    return maliyet(job, [profil("VMC-A")], STOK, c45(), ucretler(), 1, sureler=[(0.0, 0.0)], **kw)


def test_takim():
    # 3 dk kesme, 30 dk ömür, kenar 12 € → 0.1 · 12 = 1.2 € (kesirli)
    m = k5_maliyet()
    takim = next(k for k in m.kalemler if k.ad == "takim")
    assert takim.tutar_eur == pytest.approx(1.2, rel=REL)
    assert "kenar ömrü (yerel dosya)" in takim.aciklama


def test_takim_59():
    # Ek 2 / K5b: SPEC 59 varken takım payı c_kenar · D (ToolWear.D, parça başı Miner toplamı)
    omur = pytest.importorskip("cam.omur")
    # sabit Vc: D = t / T = 3 / 30 = 0.1 → 1.2 € (K5 ile aynı)
    sabit = omur.ToolWear(tool_id=1, tool_material="karbur", t_cut=3.0, D=0.1, Vc_max=150.0, steps=())
    m = k5_maliyet(asinma=[sabit])
    takim = next(k for k in m.kalemler if k.ad == "takim")
    assert takim.tutar_eur == pytest.approx(1.2, rel=REL)
    assert "takım: SPEC 59 Miner D" in takim.aciklama
    # iki hızlı örnek (SPEC 59): D = 0.75 → 12 · 0.75 = 9.0 €
    iki_hiz = omur.ToolWear(tool_id=1, tool_material="karbur", t_cut=3.0, D=0.75, Vc_max=300.0, steps=())
    m = k5_maliyet(asinma=[iki_hiz])
    takim = next(k for k in m.kalemler if k.ad == "takim")
    assert takim.tutar_eur == pytest.approx(9.0, rel=REL)


# ---------------------------------------------------------------- K6 kademe


def test_kademe():
    job = is_foyu()
    satirlar = kademeler(job, PROFILLER, STOK, c45(), ucretler(), sureler=SURELER, dis_islem=DIS)
    assert [m.n for m in satirlar] == [1, 10, 50, 200]
    fiyat = [m.fiyat_eur for m in satirlar]
    # hazırlık > 0 → kesin azalan
    assert all(a > b for a, b in zip(fiyat, fiyat[1:], strict=False))
    # her satır tek başına maliyet(n) ile birebir aynı (baştan hesap)
    for m in satirlar:
        assert m == calistir(m.n, job)


def test_kademe_ozel_adetler():
    satirlar = kademeler(is_foyu(), PROFILLER, STOK, c45(), ucretler(), adetler=(5, 2), sureler=SURELER)
    assert [m.n for m in satirlar] == [5, 2]
    assert satirlar[0] == calistir(5, dis_islem=())


def test_kademe_hazirliksiz_esit():
    # hazırlık 0 → adet fiyatı değiştirmez (azalan ama kesin değil)
    satirlar = kademeler(is_foyu(), PROFILLER, STOK, c45(), ucretler(), sureler=[(60.0, 0.0), (45.0, 0.0)])
    fiyat = [m.fiyat_eur for m in satirlar]
    assert fiyat == pytest.approx([fiyat[0]] * 4, rel=REL)


# ---------------------------------------------------------------- K7 oran sınırları


@pytest.mark.parametrize(
    "degis",
    [
        {"genel_gider": -0.01},
        {"genel_gider": 5.01},
        {"kar_payi": -0.01},
        {"kar_payi": 5.5},
        {"operator_orani": 0.0},
        {"operator_orani": -0.5},
        {"operator_orani": 1.01},
        {"fire_orani": 1.0},
        {"fire_orani": -0.1},
    ],
    ids=[
        "g_negatif",
        "g_buyuk",
        "k_negatif",
        "k_buyuk",
        "kop_sifir",
        "kop_negatif",
        "kop_buyuk",
        "fire_1",
        "fire_neg",
    ],
)
def test_sinir(degis):
    # hata ücret sözlüğü okunurken ya da maliyet hesabında: ikisinden biri ModelError vermeli
    with pytest.raises(ModelError):
        calistir(1, u=Ucretler.from_dict(ucret_sozlugu(**degis)))


@pytest.mark.parametrize(
    "degis", [{"genel_gider": 5.0, "kar_payi": 5.0}, {"genel_gider": 0.0, "operator_orani": 1.0}]
)
def test_sinir_kenar_degerleri_gecerli(degis):
    m = calistir(1, u=ucretler(**degis))
    g, k = degis.get("genel_gider", G), degis.get("kar_payi", K)
    assert m.fiyat_eur == pytest.approx(m.ara_toplam_eur * (1 + g) * (1 + k), rel=REL)


@pytest.mark.parametrize("n", [0, -1, 2.5, "3"])
def test_sinir_adet(n):
    with pytest.raises(ModelError):
        calistir(n)


def test_sinir_kademe_adedi():
    with pytest.raises(ModelError):
        kademeler(is_foyu(), PROFILLER, STOK, c45(), ucretler(), adetler=(1, 0), sureler=SURELER)


# ---------------------------------------------------------------- K9 gizlilik


def test_gizlilik():
    izlenen = subprocess.run(
        ["git", "ls-files", "yerel_parcalar"], cwd=KOK, capture_output=True, text=True, check=True
    ).stdout.split()
    assert izlenen == []
    ornek = json.loads((KOK / "examples" / "58_atolye_ucretleri_ornek.json").read_text(encoding="utf-8"))
    assert next(iter(ornek)) == "aciklama"  # ilk alan
    assert "UYDURMA" in ornek["aciklama"]
    satirlar = [s.strip() for s in (KOK / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert any(s in ("yerel_parcalar/", "yerel_parcalar", "/yerel_parcalar/") for s in satirlar)


def test_gizlilik_ornek_dosya_okunur():
    u = ucretleri_oku(KOK / "examples" / "58_atolye_ucretleri_ornek.json")
    assert isinstance(u, Ucretler)
    assert "UYDURMA" in u.aciklama
