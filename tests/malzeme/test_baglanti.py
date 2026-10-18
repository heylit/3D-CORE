"""SPEC 66 — malzeme/baglanti.py testleri: BOM, FEM, kesme verisi, maliyet köprüleri (K6–K9, K11).

Testler yalnız specs/66-malzeme-kutuphanesi.md (onaylı metin), B2 arayüzü (malzeme/model.py) ve açık
arayüzlerden (assy.model, assy.bom, cam.model, core.model, core.solver) yazıldı;
malzeme/baglanti.py gövdesi okunmadı.

Kütle: m = ρ · V  (ρ t/mm³, V mm³ → t). Maliyet: fiyat [€/kg] · 1000 · m [t].
K6'da Part yerine yalnız `volume` özelliği olan bir test ikamesi kullanılır (OCCT gerekmez, K11).
K7 kirişi: SPEC 11 K10 konsolu (L = 100, b = h = 10, P = 1000 N, Kuhn kutu ağı, k = 1). Doğrusal elastisitede
aynı ν ile δ ∝ 1/E olduğundan δ_C45 / δ_ref = 210000 / E_C45 (göreli 1e-9);
referans kiriş C45'in ν'sıyla çözülür.
Kod henüz yokken (NotImplementedError) testler kök conftest.py ile "uygulanmamış" sayılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from assy.bom import total_mass, unit_masses
from assy.model import Assembly, Component, Node, transform
from cam.model import CuttingData, Tool, ToolKind
from core.model import BC, Material
from core.solver import solve
from malzeme.baglanti import (
    bilesen_malzemeleri,
    fem_malzemeleri,
    kesme_tablosu,
    kutle_tablosu,
    malzeme_maliyeti_eur,
    yogunluk_haritasi,
)
from malzeme.kutuphane import Kutuphane, yerlesik
from malzeme.model import KesmeOnerisi, Malzeme, ModelError
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri, yuzey_cekmesi

KOK = Path(__file__).resolve().parents[2]
REL = 1e-12
C45, AL = "1.0503", "EN-AW-6061-T6"


@dataclass
class Kutu:
    """Part ikamesi: yalnız hacim [mm³]."""

    a: float
    b: float
    c: float

    @property
    def volume(self) -> float:
        return self.a * self.b * self.c


def montaj(kapak_malzemesi: str | None = AL, govde_malzemesi: str | None = C45) -> Assembly:
    """K6: govde (C45, 100×50×20), kapak (6061, 100×50×5) ve aynı parçadan ikinci kapak."""
    return Assembly(
        "malzemeli",
        [
            Component("govde", "govde_p", fixed=True, material=govde_malzemesi),
            Component("kapak", "kapak_p", T=transform(t=(0, 0, 20)), material=kapak_malzemesi),
            Component("kapak_2", "kapak_p", T=transform(t=(0, 0, -5)), material=AL),
        ],
    )


PARTS = {"govde_p": Kutu(100.0, 50.0, 20.0), "kapak_p": Kutu(100.0, 50.0, 5.0)}


def mk(id: str, **kw) -> Malzeme:
    """Uydurma kayıt (gerçek veri değil)."""
    alanlar = dict(E=200_000.0, nu=0.3, rho=7.8e-9)
    alanlar.update(kw)
    return Malzeme(id=id, name=id, standart="", grup="celik", kaynak="test: uydurma kayıt", **alanlar)


def rel(x: float, y: float, tol: float = REL) -> bool:
    return abs(x - y) <= tol * abs(y)


# ---------------------------------------------------------------- K6 BOM


class TestK6:
    def test_bilesen_malzemeleri(self):
        kut = yerlesik()
        d = bilesen_malzemeleri(montaj(), kut)
        assert set(d) == {"govde", "kapak", "kapak_2"}
        assert d["govde"] == kut.get(C45)
        assert d["kapak"] == kut.get(AL) and d["kapak_2"] == kut.get(AL)

    def test_yogunluk_haritasi(self):
        kut = yerlesik()
        assert yogunluk_haritasi(montaj(), kut) == {"govde_p": kut.get(C45).rho, "kapak_p": kut.get(AL).rho}

    def test_kutle_tablosu_kapali_form(self):
        kut = yerlesik()
        m = kutle_tablosu(montaj(), PARTS, kut)
        assert set(m) == {"govde_p", "kapak_p"}
        assert rel(m["govde_p"], kut.get(C45).rho * 100_000.0)
        assert rel(m["kapak_p"], kut.get(AL).rho * 25_000.0)

    def test_unit_masses_ile_birebir(self):
        kut = yerlesik()
        asm = montaj()
        assert kutle_tablosu(asm, PARTS, kut) == unit_masses(PARTS, yogunluk_haritasi(asm, kut))

    def test_total_mass(self):
        kut = yerlesik()
        m = kutle_tablosu(montaj(), PARTS, kut)
        kok = Node(
            "malzemeli",
            children=[
                Node("govde", part="govde_p"),
                Node("kapak", part="kapak_p"),
                Node("kapak_2", part="kapak_p"),
            ],
        )
        beklenen = kut.get(C45).rho * 100_000.0 + 2.0 * kut.get(AL).rho * 25_000.0
        assert rel(total_mass(kok, m), beklenen)

    def test_malzemesiz_bilesen(self):
        with pytest.raises(ModelError, match="kapak"):
            bilesen_malzemeleri(montaj(kapak_malzemesi=None), yerlesik())
        with pytest.raises(ModelError):
            yogunluk_haritasi(montaj(kapak_malzemesi=None), yerlesik())
        with pytest.raises(ModelError):
            kutle_tablosu(montaj(govde_malzemesi=None), PARTS, yerlesik())

    def test_ayni_parca_iki_malzeme(self):
        # kapak 7075, kapak_2 6061: aynı parça kimliği farklı malzemeyle
        with pytest.raises(ModelError):
            yogunluk_haritasi(montaj(kapak_malzemesi="EN-AW-7075-T6"), yerlesik())

    def test_kutuphanede_olmayan_malzeme(self):
        # Component.material'ın kütüphanede varlığı bu köprüde denetlenir (B2)
        with pytest.raises(ModelError):
            bilesen_malzemeleri(montaj(govde_malzemesi="1.0505"), yerlesik())

    def test_rho_yok(self):
        kut = Kutuphane([mk("R-0", rho=None), mk("R-1")])
        asm = Assembly(
            "r", [Component("a", "pa", fixed=True, material="R-0"), Component("b", "pb", material="R-1")]
        )
        with pytest.raises(ModelError):
            yogunluk_haritasi(asm, kut)


# ---------------------------------------------------------------- K7 FEM


L_, b_, h_, P_ = 100.0, 10.0, 10.0, 1000.0


def konsol_sehim(mat: Material) -> float:
    """SPEC 11 K10 konsolu, k = 1 (10×1×1 kutu, Kuhn): x = 0 ankastre, x = L'de −z düzgün kayma P.
    δ_uç = serbest uç yüzündeki düğümlerin −u_z ortalaması."""
    m = kutu_agi(L_, b_, h_, 10, 1, 1, mat, name="konsol")
    m.bcs = [BC(n, d, 0.0) for n in yuz_dugumleri(m, 0, 0.0) for d in ("ux", "uy", "uz")]
    m.loads = yuzey_cekmesi(m, 0, L_, (0.0, 0.0, -P_ / (b_ * h_)))
    r = solve(m)
    return -float(np.mean([r.displacement(m, n, "uz") for n in yuz_dugumleri(m, 0, L_)]))


class TestK7:
    def test_fem_malzemesi(self):
        kut = yerlesik()
        mats = fem_malzemeleri(kut, [C45])
        assert len(mats) == 1
        mat, k = mats[0], kut.get(C45)
        assert isinstance(mat, Material)
        assert mat.name == C45
        assert (mat.E, mat.nu, mat.rho) == (k.E, k.nu, k.rho)

    def test_sira_korunur(self):
        mats = fem_malzemeleri(yerlesik(), [AL, C45, "Ti-6Al-4V"])
        assert [m.name for m in mats] == [AL, C45, "Ti-6Al-4V"]

    def test_bilinmeyen_id(self):
        with pytest.raises(ModelError):
            fem_malzemeleri(yerlesik(), ["1.0505"])

    def test_konsol_sehim_orani(self):
        mat = fem_malzemeleri(yerlesik(), [C45])[0]
        ref = Material("ref", 210_000.0, mat.nu, mat.rho)
        d_c45, d_ref = konsol_sehim(mat), konsol_sehim(ref)
        assert d_c45 > 0.0
        assert rel(d_c45 / d_ref, 210_000.0 / mat.E, 1e-9)


# ---------------------------------------------------------------- K8 kesme verisi


class TestK8:
    def test_iki_kayit(self):
        kut = yerlesik()
        t = kesme_tablosu(kut, "karbur", ap=2, ae=5, ids=[C45, AL])
        assert set(t) == {C45, AL}
        for id, cd in t.items():
            oneri = kut.get(id).kesme["karbur"]
            assert isinstance(cd, CuttingData)
            assert cd.Vc == oneri.Vc
            assert (cd.ap, cd.ae) == (2, 5)
            assert cd == kut.get(id).kesme_verisi("karbur", 2, 5)

    def test_tool_gidis_donus(self):
        t = kesme_tablosu(yerlesik(), "karbur", ap=2, ae=5, ids=[C45, AL])
        tool = Tool(id=1, name="T1 D10", kind=ToolKind.FLAT, D=10.0, flute_length=25.0, flutes=4, cutting=t)
        geri = Tool.from_dict(tool.to_dict())
        assert geri == tool
        assert set(geri.cutting) == {C45, AL}

    def test_onerisi_olmayan_kayit_ids_icinde(self):
        # D4: ids verilmişse önerisi olmayan kayıt atlanmaz
        with pytest.raises(ModelError):
            kesme_tablosu(yerlesik(), "karbur", ap=2, ae=5, ids=[C45, "POM-C"])

    def test_bilinmeyen_takim(self):
        with pytest.raises(ModelError):
            kesme_tablosu(yerlesik(), "elmas", ap=2, ae=5, ids=[C45])

    def test_bilinmeyen_id(self):
        with pytest.raises(ModelError):
            kesme_tablosu(yerlesik(), "karbur", ap=2, ids=["1.0505"])

    def test_ids_yok_yalniz_onerisi_olanlar(self):
        kut = yerlesik()
        t = kesme_tablosu(kut, "karbur", ap=1.5)
        assert set(t) == {m.id for m in kut if "karbur" in m.kesme}
        assert {C45, AL} <= set(t)  # K2: talaşlı grupların hepsinde karbur önerisi var
        assert all(cd.ap == 1.5 and cd.ae is None for cd in t.values())

    def test_uydurma_kutuphane(self):
        # veriden bağımsız: önerisi olmayan kayıt ids=None'da atlanır
        kut = Kutuphane([mk("K-1", kesme={"HSS": KesmeOnerisi(Vc=30.0, fz=0.05)}), mk("K-2")])
        t = kesme_tablosu(kut, "HSS", ap=1.0, ae=2.0)
        assert t == {"K-1": CuttingData(Vc=30.0, fz=0.05, ap=1.0, ae=2.0)}
        with pytest.raises(ModelError):
            kesme_tablosu(kut, "HSS", ap=1.0, ids=["K-1", "K-2"])


# ---------------------------------------------------------------- K9 maliyet


class TestK9:
    def test_iki_kg(self):
        m = mk("F-1", fiyat=1.5, kullanici=True)
        assert rel(malzeme_maliyeti_eur(m, 0.002), 3.0)

    def test_sifir_kutle(self):
        assert malzeme_maliyeti_eur(mk("F-1", fiyat=1.5), 0.0) == 0.0

    def test_negatif_kutle(self):
        with pytest.raises(ModelError):
            malzeme_maliyeti_eur(mk("F-1", fiyat=1.5), -1.0)

    def test_fiyat_yok(self):
        with pytest.raises(ModelError):
            malzeme_maliyeti_eur(mk("F-1"), 0.002)

    def test_yerlesik_kayitta_fiyat_yok(self):
        # D7: yerleşik kayıtlarda fiyat boş → maliyet hesabı hata verir
        with pytest.raises(ModelError):
            malzeme_maliyeti_eur(yerlesik().get(C45), 0.002)


# ---------------------------------------------------------------- K11 bağımlılık yönü

IMPORT = re.compile(r"^\s*(import\s+malzeme\b|from\s+malzeme\b)", re.MULTILINE)


@pytest.mark.parametrize("paket", ["core", "cam", "assy", "geometry", "mesh"])
def test_K11_alt_paketler_malzemeyi_import_etmez(paket):
    dosyalar = sorted((KOK / paket).rglob("*.py"))
    assert dosyalar, f"{paket}/ altında kaynak yok"
    ihlal = [str(p.relative_to(KOK)) for p in dosyalar if IMPORT.search(p.read_text(encoding="utf-8"))]
    assert ihlal == []
