"""SPEC 51 K8–K9 — yazma öncesi denetimler ve okuyucu hataları.

Testler yalnız SPEC 51 metninden ve iskelet imzalarından yazıldı (bkz. `post5_ortak`).
Varsayımlar (koordinatöre bildirildi):
- "TCP kapalı yolda `linearize` atlanmış" genel arayüzden ancak toleransı kapatarak denenebilir:
  `tol_p` / `tol_a` ≤ 0 ya da sonlu değil → CamError (doğrusallaştırma kapatılamaz).
- "Eksen adı uyuşmazlığı": B/C kinematikli profille yazılan program A/C kinematikli profille
  okununca CamError.
- Okuyucu hatasındaki "satır numarası" programın 1 tabanlı metin satırıdır.
- Hareket indeksi mesajda 0 ya da 1 tabanlı olabilir; ikisinden biri yeter.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pytest

from cam.model import CamError, Kinematics, Move, RotaryAxis, Toolpath
from cam.post import post5, read_program5
from tests.cam.post5_ortak import (
    G1,
    KURULUM,
    RPM,
    TAKIM,
    TAKIMLAR,
    ac_masa,
    bc_kafa_masa,
    ilk_satir,
    makine,
    meta,
    satir_ekle,
    sozcukler,
    yarim_kure,
    yon,
)


def _yol(eksenler, feed: float = 600.0) -> Toolpath:
    """Uç x boyunca 5 mm adımla ilerler; her harekete verilen eksen."""
    moves = [Move(G1, (5.0 * i, 0.0, 0.0), feed=feed, axis=tuple(a)) for i, a in enumerate(eksenler)]
    start = tuple(np.array(moves[0].end) + 10.0 * np.array(moves[0].axis))
    return Toolpath(name="HATA", tool=TAKIM, start=start, moves=moves, rpm=RPM, meta=meta("5"))


def _ac_sinirli(a_min: float, a_max: float) -> Kinematics:
    k = ac_masa()
    a, c = k.rotary
    return Kinematics(rotary=(RotaryAxis("A", "masa", a.u, a.pivot, a_min, a_max), c))


def _indeks_var(mesaj: str, i: int) -> bool:
    return re.search(rf"\b({i}|{i + 1})\b", mesaj) is not None


# ---------------------------------------------------------------- K8 yazma öncesi denetimler


@pytest.mark.parametrize("tcp", ["traori", "yok"])
def test_k8_eksen_siniri_disi_aci(tcp):
    """A ∈ [−20°, 20°]; 3. hareketin ekseni 30° eğik → sınır dışı; mesajda hareket ve eksen."""
    eksenler = [yon(10.0, 90.0)] * 3 + [yon(30.0, 90.0)] + [yon(10.0, 90.0)]
    m = makine("sinumerik", _ac_sinirli(-20.0, 20.0), tcp=tcp)
    with pytest.raises(CamError) as e:
        post5([_yol(eksenler)], m, KURULUM, TAKIMLAR)
    assert _indeks_var(str(e.value), 3)
    assert "A" in str(e.value)


def test_k8_tekillik_gecisi_max_jump():
    """A ≥ 0 sınırlı AC masada kutbun öbür yanına geçiş: C 180° sıçrar > varsayılan 90° → CamError."""
    eksenler = [yon(5.0, 0.0), yon(5.0, 0.0), yon(5.0, 180.0)]
    m = makine("sinumerik", _ac_sinirli(0.0, 120.0))
    with pytest.raises(CamError) as e:
        post5([_yol(eksenler)], m, KURULUM, TAKIMLAR)
    assert _indeks_var(str(e.value), 2)


@pytest.mark.parametrize("dil, tcp", [("sinumerik", "traori"), ("fanuc", "g43.4"), ("fanuc", "yok")])
def test_k8_max_jump_parametresi(dil, tcp):
    """Yarım küre yolunda ardışık açı değişimi birkaç derece: max_jump = 0.5° aşılır, 90° aşılmaz."""
    m = makine(dil, ac_masa(), tcp=tcp)
    with pytest.raises(CamError):
        post5([yarim_kure()], m, KURULUM, TAKIMLAR, max_jump=0.5)
    assert isinstance(post5([yarim_kure()], m, KURULUM, TAKIMLAR), str)


@pytest.mark.parametrize("ad, deger", [("tol_p", 0.0), ("tol_p", -1e-3), ("tol_p", math.nan), ("tol_a", 0.0)])
def test_k8_tcp_kapali_linearize_atlanamaz(ad, deger):
    m = makine("fanuc", ac_masa(), tcp="yok")
    with pytest.raises(CamError):
        post5([yarim_kure()], m, KURULUM, TAKIMLAR, **{ad: deger})


def test_k8_heidenhain_tcp_kapali_es_zamanli_yok():
    m = makine("heidenhain", ac_masa(), tcp="yok")
    with pytest.raises(CamError):
        post5([yarim_kure()], m, KURULUM, TAKIMLAR)


def test_k8_eksen_adi_uyusmazligi():
    """B/C kinematikli profille yazılan program A/C profille okunamaz: ilk B sözcüğünün satırı mesajda."""
    yazan = makine("sinumerik", bc_kafa_masa())
    metin = post5([yarim_kure()], yazan, KURULUM, TAKIMLAR)
    satir = ilk_satir(metin, r"\bB\s*=?\s*[+-]?[\d.]") + 1
    with pytest.raises(CamError) as e:
        read_program5(metin, makine("sinumerik", ac_masa()), TAKIMLAR)
    assert re.search(rf"\b{satir}\b", str(e.value))


# ---------------------------------------------------------------- K9 okuyucu hataları


def _program(dil: str, **kw) -> tuple[str, object]:
    m = makine(dil, ac_masa(), **kw)
    return post5([yarim_kure()], m, KURULUM, TAKIMLAR), m


def _ekle_ve_oku(metin: str, m, sonra: str, satir: str) -> None:
    """`sonra` desenli ilk satırın arkasına `satir` eklenir; okuyucu o satırın numarasıyla CamError verir."""
    yeni, no = satir_ekle(metin, ilk_satir(metin, sonra) + 1, satir)
    with pytest.raises(CamError) as e:
        read_program5(yeni, m, TAKIMLAR)
    assert re.search(rf"\b{no}\b", str(e.value)), str(e.value)


def test_k9_gecerli_program_okunur():
    """Taban durum: eklemesiz programlar hatasız okunur (aşağıdaki hatalar eklenen satırdan)."""
    for dil in ("sinumerik", "heidenhain", "fanuc"):
        metin, m = _program(dil)
        assert read_program5(metin, m, TAKIMLAR)


@pytest.mark.parametrize(
    "satir", ["TRAORI(2)", "ORIEULER", "ORIRPY", "ORIPATH", "CYCLE832(0.01,_ORI_FINISH,1)"]
)
def test_k9_sinumerik_desteklenmeyen(satir):
    metin, m = _program("sinumerik")
    _ekle_ve_oku(metin, m, r"\bTRAORI\b", satir)


@pytest.mark.parametrize("satir", ["ORIAXES", "ORIVECT"])
def test_k9_sinumerik_desteklenen_yonelim_kipleri_hata_degil(satir):
    """ORIAXES / ORIVECT desteklenen yönelim kipleri: eklenince okuma hata vermez."""
    metin, m = _program("sinumerik")
    yeni, _ = satir_ekle(metin, ilk_satir(metin, r"\bTRAORI\b") + 1, satir)
    assert read_program5(yeni, m, TAKIMLAR)


@pytest.mark.parametrize("satir", ["FN 0: Q1 = +5", "FN 1: Q2 = +Q1 + +3"])
def test_k9_heidenhain_fn(satir):
    metin, m = _program("heidenhain")
    _ekle_ve_oku(metin, m, r"\bFUNCTION\s+TCPM\b", satir)


def test_k9_fanuc_g43_4_ile_vektor_karisimi():
    metin, m = _program("fanuc")
    _ekle_ve_oku(metin, m, r"\bG43\.4\b", "G1 X1. Y2. Z3. I0. J0. K1.")


def test_k9_yorumlar_sayilmaz():
    """Desteklenmeyen sözcük yalnız yorumdaysa hata yok (yorum: Sinumerik `;`, Fanuc `( )`)."""
    for dil, yorum in (("sinumerik", "; TRAORI(2) ORIEULER"), ("fanuc", "(G43.5 I0 J0 K1)")):
        metin, m = _program(dil)
        yeni, no = satir_ekle(metin, ilk_satir(metin, r"\bG\d") + 1, yorum)
        assert sozcukler(yeni.splitlines()[no - 1]).strip() == ""
        assert read_program5(yeni, m, TAKIMLAR)
