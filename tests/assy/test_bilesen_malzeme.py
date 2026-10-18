"""SPEC B2 — assy/model.py `Component.material` testleri (K8).

Testler sadece specs/B2-malzeme-arayuz.md'deki `assy/model.py` ekinden yazıldı.
- material: None (atanmamış) ya da boş olmayan metin (malzeme.model.Malzeme.id); aksi halde AssyError.
- Eşitlik (name, part, fixed, material) ve T'yi karşılaştırır.
- Assembly.to_dict "material" anahtarını yalnız None değilse yazar; from_dict anahtar yoksa None okur.
Kimliğin kütüphanede olup olmadığını assy bilmez (SPEC 66), burada denetlenmez.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from assy.model import Assembly, AssyError, Component, rot_z, transform


def test_k8_varsayilan_none():
    assert Component("govde", "govde.step").material is None


def test_k8_material_atanir():
    c = Component("govde", "govde.step", material="1.0503")
    assert c.material == "1.0503"


@pytest.mark.parametrize("material", ["", 5])
def test_k8_gecersiz_material_hata(material):
    with pytest.raises(AssyError):
        Component("govde", "govde.step", material=material)


def test_k8_malzemesi_farkli_bilesenler_esit_degil():
    T = transform(rot_z(30.0), (1.0, 2.0, 3.0))
    a = Component("govde", "govde.step", T=T, material="1.0503")
    b = Component("govde", "govde.step", T=T.copy(), material="EN-AW-6061-T6")
    c = Component("govde", "govde.step", T=T.copy())
    assert a != b
    assert a != c
    assert a == Component("govde", "govde.step", T=T.copy(), material="1.0503")


def test_k8_to_dict_malzemesiz_anahtar_yok():
    d = Assembly("m", components=[Component("govde", "govde.step")]).to_dict()
    assert "material" not in d["components"][0]


def test_k8_to_dict_malzemeli_anahtar_var():
    d = Assembly("m", components=[Component("govde", "govde.step", material="1.0503")]).to_dict()
    assert d["components"][0]["material"] == "1.0503"


def test_k8_gidis_donus():
    assy = Assembly(
        "m",
        components=[
            Component("govde", "govde.step", fixed=True, material="1.0503"),
            Component("kapak", "kapak.step", T=transform(rot_z(90), (0.0, 0.0, 40.0))),
        ],
    )
    geri = Assembly.from_dict(json.loads(json.dumps(assy.to_dict())))
    assert geri.component("govde").material == "1.0503"
    assert geri.component("kapak").material is None
    for a, b in zip(assy.components, geri.components, strict=True):
        assert a == b
        np.testing.assert_array_equal(a.T, b.T)


def test_k8_eski_json_material_yok():
    """material anahtarı olmayan eski JSON aynen okunur."""
    d = {"name": "m", "components": [{"name": "govde", "part": "govde.step", "T": np.eye(4).tolist()}]}
    assert Assembly.from_dict(d).component("govde").material is None
