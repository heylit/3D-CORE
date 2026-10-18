"""SPEC 69 K7 — parça köprüsü (OCCT): `kutleler_parcadan` ve gerçek parçalı krank–biyelde güç dengesi.

B2/66 köprüsü (`Component.material`, malzeme kütüphanesi: `1.0503`, `EN-AW-6061-T6`) bu dalın tabanında (main)
henüz yok; arayüzü bilinmeden kütüphane çağrısı uydurulmaz. Test 66 birleşince yazılır; o zamana dek atlanır.
"""

from __future__ import annotations

import dataclasses

import pytest

from assy.model import Component


def _b2_66_var() -> bool:
    try:
        import malzeme  # noqa: F401
    except ImportError:
        return False
    return "material" in {f.name for f in dataclasses.fields(Component)}


@pytest.mark.occt
@pytest.mark.skipif(
    not _b2_66_var(), reason="B2/66 (Component.material, malzeme/) main'de yok; K7 66 ile yazılır"
)
def test_k7_parca_koprusu_66_bekliyor():
    pytest.fail("B2/66 birleşti: K7 testini malzeme kütüphanesi arayüzüyle yaz (SPEC 69 K7)")
