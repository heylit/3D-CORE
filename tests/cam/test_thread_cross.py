"""SPEC 52 K8 — diş olmayan senkron kesim (P çok büyük, düz kanala yakın): PolarMap hacmi kapalı formla.

Koordinatör kararı (2026-10-18,
SPEC metni #119'da güncellenir): tri-dexel (43) torna / kılavuz profilini temsil
edemediği için 43 karşılaştırması yerine Pappus kapalı formu. cam.sim kodu okunmadı.

Kaynak (SPEC 52 "Senkron helis süpürmesi"): z_c(θ) = z₀ + P·(θ − θ₀)/360;
P = 100'de paso (23.5 mm) en çok ~85°'lik
bir açı bandını keser, her θ sütununda profil bir kez yer alır. Sütun hacimlerinin θ üzerinden toplamı,
sürekli
limitte (2π/P)·∫Ψ(z_c)dz_c;
mil bölgesindeki her z için iç integral sivri V yivin Pappus yoğunluğu A·r_c olduğundan
kaldırılan hacim = (L_mil/P)·A·2π·r_c (A = h²·tan 30°, r_c = 10 − h/3,
L_mil = 20). Boyun ve kanalda malzeme yiv
dibinin altında. Tolerans ızgaraya göre: rel (Δθ[rad])² + (Δz/h)².
"""

from __future__ import annotations

import math

import pytest

from cam.sim import PolarMap, simulate_thread
from tests.cam.threadref import MIL_Z, dis_kalemi, groove_volume_per_turn, mil_rmap, torna_disi

P_BUYUK = 100.0
h = 1.5
DZ = 0.02


def test_K8_buyuk_hatve_kanal_hacmi():
    tp = torna_disi(20.0, P_BUYUK, dis_kalemi(0.0), h)
    bas = PolarMap.from_radial(mil_rmap(20.0, 7.0, DZ), dtheta_deg=1.0)
    m = simulate_thread([tp], bas)
    beklenen = (MIL_Z[1] - MIL_Z[0]) / P_BUYUK * groove_volume_per_turn(h, 10.0)
    tol = math.radians(1.0) ** 2 + (DZ / h) ** 2
    assert bas.volume() - m.volume() == pytest.approx(beklenen, rel=tol)


def test_K8_kesilen_aci_bandi():
    """Kesilen sütunlar: yiv mil malzemesine değen z_c aralığı L_mil + 2·h·tan 30° = 21.73 mm → 78.2°;
    band dışı sütunlar dokunulmamış."""
    tp = torna_disi(20.0, P_BUYUK, dis_kalemi(0.0), h)
    bas = PolarMap.from_radial(mil_rmap(20.0, 7.0, DZ), dtheta_deg=1.0)
    m = simulate_thread([tp], bas)
    kesilen = (m.r_out < bas.r_out - 1e-12).any(axis=1)
    n = int(kesilen.sum())
    assert (
        76 <= n <= math.ceil(360 * (MIL_Z[1] - MIL_Z[0] + 2 * h * math.tan(math.radians(30))) / P_BUYUK) + 2
    )
