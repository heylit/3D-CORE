"""SPEC 57 §3–4 — cam/plan2/ortu.py ve erisim.reachable testleri (K4, K5).

K4'ün saf kısmı OCCT gerektirmez; K5 (plan_auto) gerektirir.
Testler yalnızca SPEC 57 metninden ve iskeletteki imzalardan yazıldı; gövdeler okunmadı.
K4 el hesabı (her yüzünde bir cep olan blok; bağlama adayı c = tablaya dayanan yüzün normali):
- 3 eksen: R(c) = {−c} → her bağlama bir yüz → 6 yüz 6, 5 yüz 5.
- Masa-masa, θ_max = 110°: R(−Z) = {+Z, ±X, ±Y} (alt yüz c'nin kendisi) → 6 yüz 2, 5 yüz 1.
- Yatay B tabla: R(c) = {d ⊥ c}: R(−Z) = dört yan, R(−X) = {±Y, ±Z} → 6 yüz 2, 5 yüz 2.

`min_cover` yalnız anahtar demeti döndürür; örtülemeyen kalanı çağıran `universe − ⋃ cover[k]` ile
bulur; eşitlikte `cover` sözlüğünün ekleme sırası (kodlayıcının arayüz netleştirmesi, durum/57
madde 3, 21cac89).

K5 (durum/57 madde 5): `fixtures` bağlama yerel çerçevesinde `Stock` kutuları (z = 0 parçanın o
bağlamadaki en alt noktası), çene üstü z_c = max(zmax); yan yönden (d ⊥ z) erişilen özelliğin yerel
tabanı z_c + clearance altındaysa o bağlamada `cene_engeli`.
Parça 100 × 60 × 40, +X yüzünde cep: dünyada y ∈ [20, 40], z ∈ [12, 28], 6 derin. Yatay B tablada
+X'e ulaşan bağlamalar c ∈ {±Y, ±Z} (hepsi yandan); yerel taban c = ±Z'de 12, c = ±Y'de 20.
z_c = 14 (taban çene üstünün 2 mm altında), clearance 1 → ±Z'de engel, ±Y'de 20 ≥ 15 → ±Y
bağlamasına atanır (yerel stok yüksekliği 60). z_c = 25 → 20 < 26, hiçbir bağlamada ulaşılamaz →
`cene_engeli`.
"""

from __future__ import annotations

import itertools
import random

import numpy as np
import pytest

from cam.model import MachineProfile
from cam.plan2.erisim import reachable
from cam.plan2.ortu import min_cover
from tests.cam.plan2.ortak import ANA, masa_masa, uc_eksen, yatay_b


def _kaba_kuvvet(universe: set, cover: dict) -> int:
    ortulebilen = universe & set().union(*cover.values()) if cover else set()
    keys = list(cover)
    for k in range(len(keys) + 1):
        for alt in itertools.combinations(keys, k):
            if ortulebilen <= set().union(*(cover[a] for a in alt)):
                return k
    raise AssertionError


def _ortu(universe: set, cover: dict) -> tuple:
    keys = min_cover(universe, cover)
    assert isinstance(keys, tuple)
    assert all(k in cover for k in keys)
    assert len(set(keys)) == len(keys)
    ortulen = set().union(*(cover[k] for k in keys)) if keys else set()
    ortulebilen = universe & set().union(*cover.values()) if cover else set()
    assert ortulebilen <= ortulen
    return keys


# ---------------------------------------------------------------- min_cover


def test_min_cover_basit():
    U = {1, 2, 3, 4, 5}
    cover = {"a": {1, 2, 3}, "b": {2, 4}, "c": {3, 4}, "d": {4, 5}, "e": {5}}
    keys = _ortu(U, cover)
    assert len(keys) == 2 and set(keys) == {"a", "d"}


def test_min_cover_aclgozlu_yaniltir():
    # açgözlü önce en büyüğü (x) alır ve 3 kümeye çıkar; tam arama 2 bulur
    U = set(range(1, 7))
    cover = {"x": {1, 2, 3, 4}, "y": {1, 2, 5}, "z": {3, 4, 6}, "w": {5}, "v": {6}}
    keys = _ortu(U, cover)
    assert len(keys) == 2 and set(keys) == {"y", "z"}


def test_min_cover_ortulemeyen():
    U = {1, 2, 3, 99}
    cover = {"a": {1, 2}, "b": {3}}
    keys = min_cover(U, cover)
    assert set(keys) == {"a", "b"}
    assert U - set().union(*(cover[k] for k in keys)) == {99}  # kalan çağıranda


def test_min_cover_evren_disi_elemanlar():
    # universe'te olmayan elemanlar görmezden gelinir
    U = {1, 2}
    cover = {"a": {1, 7, 8, 9}, "b": {1, 2}}
    assert min_cover(U, cover) == ("b",)


def test_min_cover_esitlikte_ekleme_sirasi():
    U = {1, 2}
    assert min_cover(U, {"q": {1, 2}, "p": {1, 2}}) == ("q",)
    assert min_cover(U, {"p": {1, 2}, "q": {1, 2}}) == ("p",)
    assert min_cover(U, {"a": {1}, "b": {2}, "c": {1}, "d": {2}}) == ("a", "b")


@pytest.mark.parametrize("seed", range(10))
def test_min_cover_kaba_kuvvet(seed):
    rng = random.Random(570 + seed)
    U = set(range(rng.randint(4, 10)))
    cover = {f"c{i}": {e for e in U if rng.random() < 0.35} for i in range(rng.randint(3, 9))}
    keys = _ortu(U, cover)
    assert len(keys) == _kaba_kuvvet(U, cover)


def test_min_cover_deterministik():
    U = {1, 2, 3, 4}
    cover = {"p": {1, 2}, "q": {3, 4}, "r": {1, 3}, "s": {2, 4}}
    assert min_cover(U, cover) == min_cover(U, dict(cover)) == ("p", "q")


# ---------------------------------------------------------------- reachable (§3)


def _ulasilan(c: str, prof: MachineProfile) -> set[str]:
    R = reachable(np.array(ANA[c]), prof)
    return {d for d, v in ANA.items() if R(np.array(v))}


def test_reachable_uc_eksen():
    assert _ulasilan("-Z", uc_eksen()) == {"+Z"}
    assert _ulasilan("+X", uc_eksen()) == {"-X"}


def test_reachable_masa_masa():
    prof = masa_masa(110.0)
    assert _ulasilan("-Z", prof) == {"+Z", "+X", "-X", "+Y", "-Y"}
    R = reachable(np.array(ANA["-Z"]), prof)
    for aci, beklenen in ((105.0, True), (115.0, False)):
        a = np.radians(aci)
        assert bool(R(np.array([np.sin(a), 0.0, np.cos(a)]))) == beklenen
    # θ_max = 80°: yanlar (90°) ulaşılamaz
    assert _ulasilan("-Z", masa_masa(80.0)) == {"+Z"}


def test_reachable_yatay_b():
    prof = yatay_b()
    assert _ulasilan("-Z", prof) == {"+X", "-X", "+Y", "-Y"}
    assert _ulasilan("-X", prof) == {"+Y", "-Y", "+Z", "-Z"}


# ---------------------------------------------------------------- K4 (saf)


def _blok_ortusu(yuzler: list[str], prof: MachineProfile) -> int:
    U = set(yuzler)
    cover = {c: {d for d in _ulasilan(c, prof) if d in U} for c in ANA}
    keys = _ortu(U, cover)
    assert len(keys) == _kaba_kuvvet(U, cover)
    return len(keys)


@pytest.mark.parametrize(
    ("yuzler", "beklenen"),
    [
        (list(ANA), (6, 2, 2)),
        ([d for d in ANA if d != "-Z"], (5, 1, 2)),
    ],
)
def test_en_az_baglama(yuzler, beklenen):
    sonuc = tuple(_blok_ortusu(yuzler, p) for p in (uc_eksen(), masa_masa(110.0), yatay_b()))
    assert sonuc == beklenen


# ---------------------------------------------------------------- K5


def _k5(z_c: float | None, options=None):
    pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')
    from cam.model import Stock
    from cam.plan2.plan import AutoOptions, plan_auto
    from geometry.features import block, pocket
    from tests.cam.plan2.ortak import yuzde
    from tests.cam.plan_ek_a import MALZEME, freze_lib

    # +X görünümünde x_g = 40 − z, y_g = y → cep merkezi (20, 30), 16 (z boyunca) × 20 (y boyunca)
    part = yuzde(block(100, 60, 40), "+X", lambda g: pocket(g, 20, 30, 16, 20, 6, r=4))
    fikstur = () if z_c is None else (Stock(-80, -80, 0, 80, 80, z_c),)
    secenek = options or AutoOptions(verify=False)
    return plan_auto(
        part,
        freze_lib(),
        MALZEME,
        yatay_b(),
        stock=Stock(0, 0, 0, 100, 60, 40),
        fixtures=fikstur,
        options=secenek,
    )


def _kodlar(p) -> list[str]:
    return [u.code for u in p.unplanned] + [u.code for m in p.plans for u in m.unplanned]


def _cep_sayisi(p) -> int:
    return sum(len({o.feature for o in m.ops if o.kind == "cep"}) for m in p.plans)


@pytest.mark.occt
@pytest.mark.parametrize("z_c", [None, 5.0])
def test_cene_engeli_yok(z_c):
    p = _k5(z_c)
    assert _kodlar(p) == []
    assert len(p.clamps) == 1 and _cep_sayisi(p) == 1


@pytest.mark.occt
def test_cene_engeli_baska_baglama():
    p = _k5(14.0)
    assert "cene_engeli" not in _kodlar(p)
    assert _kodlar(p) == []
    assert len(p.clamps) == 1 and _cep_sayisi(p) == 1
    (baglama,) = p.clamps
    assert baglama.stock.zmax - baglama.stock.zmin == pytest.approx(60.0)  # c = ±Y: yerel yükseklik y boyu


@pytest.mark.occt
def test_cene_engeli_hicbir_baglamada():
    from cam.model import CamError
    from cam.plan import MillOptions
    from cam.plan2.plan import AutoOptions

    p = _k5(25.0)
    assert "cene_engeli" in _kodlar(p)
    assert _cep_sayisi(p) == 0
    with pytest.raises(CamError):
        _k5(25.0, AutoOptions(mill=MillOptions(strict=True), verify=False))
