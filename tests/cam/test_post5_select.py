"""SPEC 51 K1 — biçim seçimi: `meta.axis_mode` × profilin `multiaxis` alanı (SPEC 51 tablosu).

Testler yalnız SPEC 51 metninden ve iskelet imzalarından yazıldı (bkz. `post5_ortak`).
Seçilen biçim programdaki komut sözcüklerinden tanınır (yorumlar hariç):
- döndürülmüş düzlem: `CYCLE800` / `PLANE SPATIAL` / `G68.2`;
- TCP açık: `TRAORI` / `FUNCTION TCPM` / `G43.4`;
- TCP kapalı eş zamanlı: `G93`;
- 3+2, swivel yok: hiçbiri yok, döner eksen sözcüğü var, `G93` yok.
"""

from __future__ import annotations

import pytest

from cam.model import CamError
from cam.multiaxis.indexed import from_xyz
from cam.post import post5, read_program5
from tests.cam.post5_ortak import (
    DILLER,
    KURULUM,
    TAKIMLAR,
    TOL_P,
    ac_masa,
    duz_yol,
    egik_cep,
    kesmeler,
    makine,
    tek_yol,
    var_mi,
    yarim_kure,
)

SWIVEL_SOZ = {"sinumerik": r"\bCYCLE800\b", "heidenhain": r"\bPLANE\s+SPATIAL\b", "fanuc": r"\bG68\.2\b"}
TCP_SOZ = {"sinumerik": r"\bTRAORI\b", "heidenhain": r"\bFUNCTION\s+TCPM\b", "fanuc": r"\bG43\.4\b"}
G93 = r"\bG93\b"
DONER = r"\b[AC]\s*=?\s*[+-]?\d"  # ac_masa eksen sözcükleri

CERCEVE = from_xyz((10.0, -5.0, -8.0), 20.0, -15.0, 30.0)


def _hicbiri(metin: str, dil: str) -> None:
    assert not var_mi(metin, SWIVEL_SOZ[dil])
    assert not var_mi(metin, TCP_SOZ[dil])
    assert not var_mi(metin, G93)


@pytest.mark.parametrize("dil", DILLER)
def test_k1_3arti2_swivel_var_doner_duzlem(dil):
    metin = post5([egik_cep(CERCEVE)], makine(dil, ac_masa()), KURULUM, TAKIMLAR)
    assert var_mi(metin, SWIVEL_SOZ[dil])
    assert not var_mi(metin, TCP_SOZ[dil])
    assert not var_mi(metin, G93)


@pytest.mark.parametrize("dil", DILLER)
def test_k1_3arti2_swivel_yok_makine_koordinati_sabit_aci(dil):
    m = makine(dil, ac_masa(), swivel="yok")
    metin = post5([egik_cep(CERCEVE)], m, KURULUM, TAKIMLAR)
    _hicbiri(metin, dil)
    assert var_mi(metin, DONER)  # sabit açılar yazılıyor


@pytest.mark.parametrize("dil", DILLER)
def test_k1_5_tcp_var_tcp_acik(dil):
    metin = post5([yarim_kure()], makine(dil, ac_masa()), KURULUM, TAKIMLAR)
    assert var_mi(metin, TCP_SOZ[dil])
    assert not var_mi(metin, G93)
    assert not var_mi(metin, SWIVEL_SOZ[dil])


@pytest.mark.parametrize("dil", ["sinumerik", "fanuc"])  # Heidenhain'de TCP kapalı eş zamanlı yok (K8)
def test_k1_5_tcp_yok_g93(dil):
    metin = post5([yarim_kure()], makine(dil, ac_masa(), tcp="yok"), KURULUM, TAKIMLAR)
    assert var_mi(metin, G93)
    assert not var_mi(metin, TCP_SOZ[dil])


# ---------------------------------------------------------------- meta yokken çıkarım


@pytest.mark.parametrize("dil", DILLER)
def test_k1_meta_yok_frame_varsa_3arti2(dil):
    metin = post5([egik_cep(CERCEVE, axis_mode=None)], makine(dil, ac_masa()), KURULUM, TAKIMLAR)
    assert var_mi(metin, SWIVEL_SOZ[dil])
    assert not var_mi(metin, TCP_SOZ[dil])


@pytest.mark.parametrize("dil", DILLER)
def test_k1_meta_yok_eksen_varsa_5(dil):
    metin = post5([yarim_kure(axis_mode=None)], makine(dil, ac_masa()), KURULUM, TAKIMLAR)
    assert var_mi(metin, TCP_SOZ[dil])
    assert not var_mi(metin, SWIVEL_SOZ[dil])


@pytest.mark.parametrize("dil", DILLER)
@pytest.mark.parametrize("axis_mode", [None, "3"])
def test_k1_meta_yok_ya_da_3_uc_eksen_yolu(dil, axis_mode):
    """Çerçeve ve eksen yok → SPEC 30/31 3 eksen yolu: 5 eksen sözcüğü yok, okununca aynı kesme yolu."""
    m = makine(dil, ac_masa())
    tp = duz_yol(axis_mode)
    metin = post5([tp], m, KURULUM, TAKIMLAR)
    _hicbiri(metin, dil)
    okunan = tek_yol(read_program5(metin, m, TAKIMLAR))
    a, b = kesmeler(tp), kesmeler(okunan)
    assert len(a) == len(b)
    for ma, mb in zip(a, b, strict=True):
        assert max(abs(x - y) for x, y in zip(ma.end, mb.end, strict=True)) <= TOL_P


@pytest.mark.parametrize("dil", DILLER)
def test_k1_kinematik_yok_hata(dil):
    m = makine(dil, None, multiaxis=False)
    with pytest.raises(CamError):
        post5([yarim_kure()], m, KURULUM, TAKIMLAR)
