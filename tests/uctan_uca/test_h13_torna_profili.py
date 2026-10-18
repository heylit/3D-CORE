"""SPEC 46 H13 — katı milden torna profili (SPEC 28). K13.

`turn_profile(mil).outer` (ön → arka, (z, x)): alın (60, 0) → (60, 9), pah → (59, 10), Ø20 silindir → (0, 10).
Pah ve silindir, H7'nin elle kurulan profilinin ilk iki doğrusuyla aynı olmalı; uydurma yok (tam kesit).
"""

from __future__ import annotations

import numpy as np
import pytest

from cam.profile import Line
from tests.uctan_uca.conftest import L_MIL, PAH, R_MIL, halka, mil_profili

tprof = halka("28", "cam.turn_profile", "turn_profile")

pytestmark = pytest.mark.occt

TOL = 1e-3


def test_k13_profil_elle_kurulanla_ayni(mil):
    tp = tprof.turn_profile(mil)
    assert tp.inner is None
    assert tp.fitted_length == pytest.approx(0.0)
    seg = tp.outer.segments
    assert all(isinstance(s, Line) for s in seg)
    assert len(seg) == 3
    # alın: z = 60 düzleminde eksenden pah başlangıcına
    assert np.allclose(seg[0].p0, [L_MIL, 0.0], atol=TOL)
    assert np.allclose(seg[0].p1, [L_MIL, R_MIL - PAH], atol=TOL)
    # pah ve Ø20 silindir = elle profilin ilk iki doğrusu
    for s, e in zip(seg[1:], mil_profili().segments[:2], strict=True):
        assert np.allclose(s.p0, e.p0, atol=TOL)
        assert np.allclose(s.p1, e.p1, atol=TOL)
