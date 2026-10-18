"""SPEC 57 — plan_auto uçtan uca testleri (K4 tam, K6, K9, K11). OCCT gerektirir.

Testler yalnızca SPEC 57 metninden ve iskeletteki imzalardan yazıldı; gövdeler okunmadı.
Takımlar SPEC 29 Ek A (tests/cam/plan_ek_a.py), malzeme "al". Tezgâh profilleri ortak.py.
Yan yüzlerdeki özellikler, parça o yüz üste bakacak biçimde döndürülüp `geometry.features.pocket` /
`hole` ile kesilerek kurulur (`ortak.yuzde`); delik kayıtları `Part.moved` ile dünyaya taşınır.

Yerleşim: cep görünümde x = 0.35·W, delik x = 0.75·W (W ≥ 60): komşu yüzlerin özellikleri kesişmez.
Sayım: bir cep tam bir "cep" işlemiyle (kalan işleme "cep_kalan" ayrı sayılmaz), bir delik
"holes[i,j,…]" grubundaki tam bir indeksle planlanmış sayılır; `AutoPlan.plans[k]` bağlama k'nın
`MillPlan`'ıdır, adresler plan içidir.

K9 parçası: 100 × 60 × 30 blok, üstte 30 × 20 (r = 5, 8 derin) cep, +X ve −X yüzlerinde Ø8 × 12 kör
delik, stok altta 3 mm fazla (alt yüz alma). Masa-masa θ = 110°: c = −Z bağlamasında
R = {+Z, ±X, ±Y} → cep ve iki delik (3 yönelim); alt yüz alma ikinci bağlamada (1 yönelim)
→ 2 bağlama. 3 eksen: her yön ayrı bağlama → 4. Fikstürlü sürümde (SPEC 10 sonrası) her
bağlamanın her setup'ı `check_setup` ile temiz. Hangi bağlamanın "ilk" olduğu SPEC §4 eşitlik
kuralına bağlı olduğundan yönelim sayıları sırasız karşılaştırılır.
"""

from __future__ import annotations

import random
import re

import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

import build123d as bd  # noqa: E402

from cam.model import CamError, Stock, Toolpath  # noqa: E402
from cam.plan import MillOptions, MillPlan  # noqa: E402
from cam.plan2.plan import AutoOptions, AutoPlan, plan_auto  # noqa: E402
from cam.plan2.stok import StockSize  # noqa: E402
from cam.plan_verify import PlanCheck  # noqa: E402
from cam.setups import check_setup  # noqa: E402
from geometry.features import block, hole, pocket  # noqa: E402
from geometry.part import Part  # noqa: E402
from tests.cam.plan2.ortak import ANA, masa_masa, uc_eksen, yatay_b, yuzde  # noqa: E402
from tests.cam.plan_ek_a import MALZEME, freze_lib  # noqa: E402

pytestmark = pytest.mark.occt

HIZLI = AutoOptions(verify=False)
SIKI = AutoOptions(mill=MillOptions(strict=True), verify=False)


def _cep(yuz: str, du: float = 0.0, dv: float = 0.0, w: float = 20.0, b: float = 16.0, t: float = 6.0):
    def islem(g: Part) -> Part:
        _, hi = g.bbox
        return pocket(g, 0.35 * hi[0] + du, 0.5 * hi[1] + dv, w, b, t, r=4.0)

    return islem


def _delik(du: float = 0.0, dv: float = 0.0, d: float = 8.0, t: float = 10.0):
    def islem(g: Part) -> Part:
        _, hi = g.bbox
        return hole(g, 0.75 * hi[0] + du, 0.5 * hi[1] + dv, d, t)

    return islem


def _stok(part: Part) -> Stock:
    lo, hi = part.bbox
    return Stock(*lo, *hi)


def _kodlar(p: AutoPlan) -> list[str]:
    return [u.code for u in p.unplanned] + [u.code for m in p.plans for u in m.unplanned]


def _sayim(p: AutoPlan) -> tuple[int, int]:
    """(planlanan cep, planlanan delik), bağlama planları boyunca."""
    cep = delik = 0
    for m in p.plans:
        cep += len({o.feature for o in m.ops if o.kind == "cep"})
        idx = set()
        for o in m.ops:
            if o.kind == "delik":
                idx |= {int(i) for i in re.findall(r"\d+", o.feature)}
        delik += len(idx)
    return cep, delik


def _her_yuzde_cep(yuzler) -> Part:
    p = block(100, 80, 60)
    for y in yuzler:
        p = yuzde(p, y, _cep(y))
    return p


def _yapi(p: AutoPlan) -> None:
    assert isinstance(p, AutoPlan)
    n = len(p.clamps)
    assert len(p.frames) == n and len(p.plans) == n and len(p.order) == n
    assert all(isinstance(m, MillPlan) for m in p.plans)
    assert all(len(f) >= 1 for f in p.frames)
    for m, sira in zip(p.plans, p.order, strict=True):
        assert sorted(sira) == sorted(o.name for o in m.ops)
    assert p.tool_changes >= len({o.tool_id for m in p.plans for o in m.ops})  # alt sınır (§5)


# ---------------------------------------------------------------- K4 (tam)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("yuzler", "beklenen"),
    [(tuple(ANA), (6, 2, 2)), (tuple(y for y in ANA if y != "-Z"), (5, 1, 2))],
    ids=["6-yuz", "5-yuz"],
)
def test_en_az_baglama_plan(yuzler, beklenen):
    part = _her_yuzde_cep(yuzler)
    stok = _stok(part)
    sonuc = []
    for prof in (uc_eksen(), masa_masa(110.0), yatay_b()):
        p = plan_auto(part, freze_lib(), MALZEME, prof, stock=stok, options=HIZLI)
        _yapi(p)
        assert _kodlar(p) == []
        assert _sayim(p) == (len(yuzler), 0)
        sonuc.append(len(p.clamps))
    assert tuple(sonuc) == beklenen


# ---------------------------------------------------------------- K6


def _rastgele_parca(seed: int) -> tuple[Part, int, int]:
    rng = random.Random(5760 + seed)
    p = block(100, 80, 60)
    n_cep = n_delik = 0
    secim = {y: rng.choice(("bos", "cep", "delik", "ikisi")) for y in ANA}
    if all(s == "bos" for s in secim.values()):
        secim["+Z"] = "ikisi"
    for y, s in secim.items():  # önce cepler: delik kayıtları sonraki adımlarda korunur
        if s in ("cep", "ikisi"):
            p = yuzde(p, y, _cep(y, du=rng.uniform(-1, 1), dv=rng.uniform(-5, 5)))
            n_cep += 1
    for y, s in secim.items():
        if s in ("delik", "ikisi"):
            p = yuzde(p, y, _delik(du=rng.uniform(-1, 1), dv=rng.uniform(-5, 5)))
            n_delik += 1
    return p, n_cep, n_delik


@pytest.mark.slow
@pytest.mark.parametrize("seed", range(20))
def test_hicbir_ozellik_kaybolmuyor(seed):
    part, n_cep, n_delik = _rastgele_parca(seed)
    assert len(part.holes) == n_delik
    p = plan_auto(part, freze_lib(), MALZEME, masa_masa(110.0), stock=_stok(part), options=HIZLI)
    _yapi(p)
    assert _kodlar(p) == []  # 5 eksende her yüz erişilebilir, takımlar yeterli
    assert _sayim(p) == (n_cep, n_delik)  # tam bir kez: eksik de fazla da yok


# ---------------------------------------------------------------- K9


def k9_parcasi() -> Part:
    p = pocket(block(100, 60, 30), 50, 30, 30, 20, 8, r=5)
    p = yuzde(p, "+X", lambda g: hole(g, g.bbox[1][0] / 2, g.bbox[1][1] / 2, 8.0, 12.0))
    return yuzde(p, "-X", lambda g: hole(g, g.bbox[1][0] / 2, g.bbox[1][1] / 2, 8.0, 12.0))


K9_STOK = Stock(0, 0, -3, 100, 60, 30)


@pytest.mark.slow
def test_uctan_uca_bes_eksen():
    part = k9_parcasi()
    assert len(part.holes) == 2
    p = plan_auto(part, freze_lib(), MALZEME, masa_masa(110.0), stock=K9_STOK)
    _yapi(p)
    assert len(p.clamps) == 2
    assert sorted(len(f) for f in p.frames) == [1, 3]
    assert _sayim(p) == (1, 2)
    assert sum(1 for m in p.plans for o in m.ops if o.kind == "yuz_alma") >= 1
    assert len(p.checks) == len(p.clamps)
    for c in p.checks:
        assert isinstance(c, PlanCheck)
        assert c.ok and c.collisions == ()
        assert c.gouge_volume <= 1e-9
    prog = p.gcode(freze_lib())
    assert isinstance(prog, list) and len(prog) == 2  # bağlama başına ayrı program
    assert all(isinstance(s, str) and s.strip() for s in prog)


@pytest.mark.slow
def test_uctan_uca_uc_eksen():
    part = k9_parcasi()
    p = plan_auto(part, freze_lib(), MALZEME, uc_eksen(), stock=K9_STOK, options=HIZLI)
    _yapi(p)
    assert len(p.clamps) == 4
    assert all(len(f) == 1 for f in p.frames)
    assert _sayim(p) == (1, 2)
    assert len(p.gcode(freze_lib())) == 4


# Mengene çeneleri (durum/57 madde 5): bağlama yerel çerçevesinde Stock kutuları, z = 0 parçanın o bağlamadaki
# en alt noktası. Çene üstü z_c = 5; yan delikler tabanı 11 (15 − 4) ≥ z_c + clearance = 6 → engel yok.
# Çeneler parçanın her iki yanında, parça boyutlarından (≤ 100) uzakta: x, y kökenine bağlı değil.
CENELER = (Stock(-200, -200, -20, 200, -120, 5), Stock(-200, 120, -20, 200, 200, 5))


@pytest.mark.slow
def test_uctan_uca_fikstur_check_setup():
    part = k9_parcasi()
    p = plan_auto(part, freze_lib(), MALZEME, masa_masa(110.0), stock=K9_STOK, fixtures=CENELER)
    _yapi(p)
    assert "cene_engeli" not in _kodlar(p)
    assert len(p.clamps) == 2
    assert sorted(len(f) for f in p.frames) == [1, 3]
    assert _sayim(p) == (1, 2)
    for baglama in p.clamps:
        assert len(baglama.fixtures) >= len(CENELER)  # aynı fikstür her bağlamaya uygulanır
    for m in p.plans:
        for i, setup in enumerate(m.setups):
            yollar = [op for op in m.ops_for(i) if isinstance(op, Toolpath)]
            check_setup(setup, yollar)  # çarpma / stok altı / kesici boyu → CamError
    for c in p.checks:
        assert c.ok and c.collisions == ()


# ---------------------------------------------------------------- K11


def _basit() -> Part:
    return pocket(block(100, 60, 20), 50, 30, 30, 20, 5, r=5)


def test_determinizm():
    part = _basit()
    a = plan_auto(part, freze_lib(), MALZEME, uc_eksen(), stock=_stok(part), options=HIZLI)
    b = plan_auto(_basit(), freze_lib(), MALZEME, uc_eksen(), stock=_stok(part), options=HIZLI)
    assert a.summary() == b.summary()
    assert a.order == b.order
    assert a.gcode(freze_lib()) == b.gcode(freze_lib())


def test_stok_kucuk():
    part = _basit()
    kucuk = Stock(1, 0, 0, 100, 60, 20)
    p = plan_auto(part, freze_lib(), MALZEME, uc_eksen(), stock=kucuk, options=HIZLI)
    assert "stok_kucuk" in _kodlar(p)
    with pytest.raises(CamError):
        plan_auto(part, freze_lib(), MALZEME, uc_eksen(), stock=kucuk, options=SIKI)


def test_stok_yok():
    part = _basit()
    katalog = (StockSize("blok", 50, 50, 50), StockSize("cubuk", 40, max_len=500))
    p = plan_auto(part, freze_lib(), MALZEME, uc_eksen(), catalog=katalog, options=HIZLI)
    assert "stok_yok" in _kodlar(p)
    assert p.plans == ()  # plan durur
    with pytest.raises(CamError, match="stok_yok"):
        plan_auto(part, freze_lib(), MALZEME, uc_eksen(), catalog=katalog, options=SIKI)


def test_katalogdan_stok():
    part = _basit()  # 100 × 60 × 20 → gereken 102 × 62 × 26
    katalog = (StockSize("blok", 101, 62, 30, name="dar"), StockSize("blok", 110, 70, 30, name="uyan"))
    p = plan_auto(part, freze_lib(), MALZEME, uc_eksen(), catalog=katalog, options=HIZLI)
    assert isinstance(p.stock, Stock)
    boy = sorted((p.stock.xmax - p.stock.xmin, p.stock.ymax - p.stock.ymin, p.stock.zmax - p.stock.zmin))
    assert boy == pytest.approx([30, 70, 110])
    assert _sayim(p)[0] == 1


def _pahli() -> Part:
    kesici = (
        bd.Pos(90, -10, 20)
        * bd.Rot(0, 30, 0)
        * bd.Box(400, 80, 400, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    )
    (solid,) = (block(100, 60, 20).shape - kesici).solids()
    return Part(solid, name="pahli")  # 7 aday yön


def test_aday_siniri():
    part = _pahli()
    secenek = AutoOptions(verify=False, max_candidates=6)
    try:
        p = plan_auto(part, freze_lib(), MALZEME, masa_masa(110.0), stock=_stok(part), options=secenek)
    except CamError as e:
        assert "aday_siniri" in str(e) or "aday" in str(e).lower()
    else:
        assert "aday_siniri" in _kodlar(p)
    # sınır yeterliyse plan kurulur
    p = plan_auto(part, freze_lib(), MALZEME, masa_masa(110.0), stock=_stok(part), options=HIZLI)
    assert "aday_siniri" not in _kodlar(p)


def test_strict_her_unplanned_hata():
    # 10 × 10, 40 derin cep: sığan en büyük Ek A frezesi Ø6 (kesici boy 18) → 29 kuralıyla planlanamaz
    part = pocket(block(100, 60, 50), 50, 30, 10, 10, 40, r=2.5)
    p = plan_auto(part, freze_lib(), MALZEME, uc_eksen(), stock=_stok(part), options=HIZLI)
    assert _kodlar(p)
    with pytest.raises(CamError):
        plan_auto(part, freze_lib(), MALZEME, uc_eksen(), stock=_stok(part), options=SIKI)
