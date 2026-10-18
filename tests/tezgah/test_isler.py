"""
SPEC 24 — örnek işler (`tezgah/isler.py`): flanş plakası, parametre ezme, hatalar.

Belgedeki tanım: 120 × 80 × 20 mm blok; işlemler sırasıyla yuzey, kontur, cep, delik (G83);
parametre anahtarları D, ap, F, rpm (+ cep: stepover, delik: q yerine ap). Bilinmeyen iş / işlem / anahtar
→ KeyError; çekirdeğin reddettiği değer → çekirdeğin CamError / ModelError'ı (sessiz düzeltme yok).
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from cam.gcode import DrillOp, write
from cam.model import CamError, MoveType, Stock, Toolpath
from core.model import ModelError
from tezgah.isler import ORNEK_ISLER, ornek_is, parametre_uygula
from tezgah.kopru import IsTanimi

AD = "flans-plakasi"
ANAHTARLAR = [
    ("yuzey", {"D", "ap", "F", "rpm"}),
    ("kontur", {"D", "ap", "F", "rpm"}),
    ("cep", {"D", "ap", "F", "rpm", "stepover"}),
    ("delik", {"D", "q", "F", "rpm"}),
]
HATALAR = (CamError, ModelError)


def _kesme_zleri(tp: Toolpath) -> set[float]:
    return {m.end[2] for m in tp.moves if m.type is not MoveType.RAPID}


def test_sample_jobs_listed():
    assert AD in ORNEK_ISLER
    assert ORNEK_ISLER[0] == AD


def test_flange_plate_definition():
    """120 × 80 × 20 mm blok, dört işlem belgedeki sırayla ve anahtarlarla."""
    flans = ornek_is(AD)
    assert isinstance(flans, IsTanimi)
    assert flans.ad == AD
    stok = flans.kurulum.stock
    assert isinstance(stok, Stock)
    np.testing.assert_allclose(stok.size, [120.0, 80.0, 20.0], rtol=0, atol=1e-12)
    assert [i.anahtar for i in flans.islemler] == [a for a, _ in ANAHTARLAR]
    for isl, (_, anahtarlar) in zip(flans.islemler, ANAHTARLAR, strict=True):
        assert set(isl.parametreler) == anahtarlar
        assert all(isinstance(v, float) for v in isl.parametreler.values())
        assert isl.ad
    assert all(isinstance(i.op, Toolpath) for i in flans.islemler[:3])
    delik = flans.islemler[3].op
    assert isinstance(delik, DrillOp)
    assert delik.kind == "G83"


def test_flange_plate_ops_match_parameters():
    """Parametreler op'larda gerçekten kullanılır: D takım çapı, rpm devir, F ilerleme, q gagalama."""
    flans = ornek_is(AD)
    for isl in flans.islemler:
        p, op = isl.parametreler, isl.op
        assert op.tool.D == p["D"]
        assert op.rpm == p["rpm"]
        if isinstance(op, DrillOp):
            assert op.feed == p["F"]
            assert op.q == p["q"]
        else:
            assert p["F"] in {m.feed for m in op.moves if m.type is not MoveType.RAPID}


def test_flange_plate_is_valid_and_inside_stock():
    """Örnek iş çekirdekten geçer (doğrulama + G-code yazımı) ve stok tabanının altına inmez."""
    flans = ornek_is(AD)
    write([i.op for i in flans.islemler], flans.dialect, safe_z=flans.safe_z)
    stok = flans.kurulum.stock
    for isl in flans.islemler:
        op = isl.op
        tp = op if isinstance(op, Toolpath) else op.to_toolpath(flans.dialect)
        lo, hi = tp.bbox()
        assert lo[2] >= stok.zmin - 1e-9
        assert hi[2] > stok.zmax  # güvenli yükseklikten gelir


def test_override_parameters():
    """`parametreler` {işlem: {anahtar: değer}} varsayılanları ezer; diğer işlemler değişmez."""
    varsayilan = ornek_is(AD)
    tanim = ornek_is(AD, {2: {"D": 8.0}, 3: {"q": 3.0}})
    assert tanim.islemler[2].parametreler["D"] == 8.0
    assert tanim.islemler[2].op.tool.D == 8.0
    assert tanim.islemler[3].op.q == 3.0
    for i in (0, 1):
        assert tanim.islemler[i].parametreler == varsayilan.islemler[i].parametreler
        assert tanim.islemler[i].op.to_dict() == varsayilan.islemler[i].op.to_dict()


def test_override_ap_and_stepover_change_path():
    """Daha küçük paso derinliği daha çok Z seviyesi; daha küçük yanal adım daha uzun cep yolu."""
    v = ornek_is(AD)
    ap = v.islemler[2].parametreler["ap"]
    s = v.islemler[2].parametreler["stepover"]
    sig = ornek_is(AD, {2: {"ap": ap / 2}})
    assert len(_kesme_zleri(sig.islemler[2].op)) > len(_kesme_zleri(v.islemler[2].op))
    assert min(_kesme_zleri(sig.islemler[2].op)) == pytest.approx(min(_kesme_zleri(v.islemler[2].op)))
    dar = ornek_is(AD, {2: {"stepover": s / 2}})
    assert dar.islemler[2].op.length() > v.islemler[2].op.length()


def test_override_feed_and_rpm():
    tanim = ornek_is(AD, {1: {"F": 432.0, "rpm": 7654.0}})
    op = tanim.islemler[1].op
    assert op.rpm == 7654.0
    assert 432.0 in {m.feed for m in op.moves if m.type is not MoveType.RAPID}


@pytest.mark.parametrize(
    "ad, parametreler",
    [
        ("olmayan-is", None),
        (AD, {9: {"D": 8.0}}),
        (AD, {2: {"yok": 1.0}}),
        (AD, {3: {"stepover": 1.0}}),  # delikte stepover yok
    ],
)
def test_unknown_job_op_or_key(ad, parametreler):
    with pytest.raises(KeyError):
        ornek_is(ad, parametreler)


@pytest.mark.parametrize(
    "islem, anahtar, deger",
    [
        (0, "D", 0.0),
        (2, "D", -4.0),
        (2, "D", 500.0),  # cep takımdan dar
        (1, "F", 0.0),
        (3, "q", 0.0),
    ],
)
def test_core_rejects_invalid_values(islem, anahtar, deger):
    """Çekirdeğin reddettiği değer çekirdeğin hatasını olduğu gibi geçirir (altın kural 5)."""
    with pytest.raises(HATALAR):
        ornek_is(AD, {islem: {anahtar: deger}})


def test_apply_parameter_returns_new_job():
    """`parametre_uygula` yeni iş döndürür; girdi değişmez; sonuç ornek_is(..., ezme) ile aynı."""
    flans = ornek_is(AD)
    once = copy.deepcopy(flans.islemler[2].parametreler)
    once_op = flans.islemler[2].op.to_dict()
    yeni = parametre_uygula(flans, 2, "D", 8.0)
    assert yeni is not flans
    assert flans.islemler[2].parametreler == once
    assert flans.islemler[2].op.to_dict() == once_op
    assert yeni.islemler[2].parametreler["D"] == 8.0
    beklenen = ornek_is(AD, {2: {"D": 8.0}})
    for a, b in zip(yeni.islemler, beklenen.islemler, strict=True):
        assert a.parametreler == b.parametreler
        assert type(a.op) is type(b.op)
        if isinstance(a.op, Toolpath):
            assert a.op.to_dict() == b.op.to_dict()
        else:
            assert a.op == b.op


def test_apply_parameter_chains():
    """Art arda uygulanan parametreler birikir."""
    flans = ornek_is(AD)
    t = parametre_uygula(parametre_uygula(flans, 2, "D", 8.0), 0, "rpm", 9000.0)
    assert t.islemler[2].op.tool.D == 8.0
    assert t.islemler[0].op.rpm == 9000.0


def test_apply_parameter_errors():
    flans = ornek_is(AD)
    with pytest.raises(KeyError):
        parametre_uygula(flans, 7, "D", 8.0)
    with pytest.raises(KeyError):
        parametre_uygula(flans, 2, "yok", 8.0)
    with pytest.raises(HATALAR):
        parametre_uygula(flans, 2, "D", 0.0)
