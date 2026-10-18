"""SPEC 52 K5 — kılavuz (G84) ile iç diş: ISO iç profil ölçümü, eğik delikte yerel çerçeve.

Testler SPEC 52 "Senkron helis süpürmesi" ve "Ölçüm" bölümlerinden, kılavuz yolu SPEC 04b "Kanonik açılımlar"
(G84: G0 → R düzlemi, G1 dibe F, G1 R'ye F, G0 dönüş; F = S·P, G94) tanımından yazıldı; cam.sim kodu okunmadı.

Kaynaklar:
- ISO 68-1 iç diş: d₂ = 8 − 0.649519·1.25, küçük çap D₁ = 8 − 1.082532·1.25 (ön delik çapı;
  kılavuz tepeyi kesmez).
- Ölçümde d_root = 2·min r_iç (iç dişte küçük çap), d₂ dolu oranı ½ (SPEC 52 "Ölçüm").
- Kılavuz giriş pahı lead·P = 3·1.25 = 3.75 mm ucta tam profil kesmez: ölçüm bölgesi pah bölgesinin üstünde.
- Yerel harita: delik ekseni Frame ile; aynı yerel yol eğik çerçevede aynı haritayı verir.
- 04b (TapOp) main'e girmeden TapOp'lu test "uygulanmamış" görünür (NotImplementedError).
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from cam.model import CylinderStock, FeedMode, Frame, Move, MoveType, Plane, Tool, ToolKind, Toolpath
from cam.sim import PolarMap, simulate_thread, thread_measure
from tests.cam.threadref import D1_iso, d2_iso

P = 1.25
D = 8.0
S = 400.0  # dev/dk → F = S·P = 500 mm/dk
DZ = 0.05
Z_R, Z_DIP, Z_BAS = -1.5, -15.0, -1.0  # R düzlemi, kılavuz ucu dibi, başlangıç (hepsi harita içinde)
HAVSA = -3.0  # z > −3: malzemesiz havşa (delik ağzı); kılavuz malzemeye z = −3'te girer
OLCUM = (-10.0, -4.0)  # tam profil: pah bölgesi (ucun 3.75 mm üstü, z < −11.25) ve havşanın dışında
BIRIM = Frame((0.0, 0.0, 0.0), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))


def _kilavuz() -> Tool:
    return Tool(20, "M8x1.25", ToolKind.TAP, D, 20.0, pitch=P, lead=3.0)


def _egik() -> Frame:
    a, b = math.radians(35.0), math.radians(20.0)
    Ry = np.array([[math.cos(a), 0.0, math.sin(a)], [0.0, 1.0, 0.0], [-math.sin(a), 0.0, math.cos(a)]])
    Rz = np.array([[math.cos(b), -math.sin(b), 0.0], [math.sin(b), math.cos(b), 0.0], [0.0, 0.0, 1.0]])
    R = Ry @ Rz
    return Frame((30.0, -20.0, 15.0), tuple(tuple(float(v) for v in row) for row in R))


def _g84(frame: Frame) -> Toolpath:
    """G84 kanonik açılımı yerel (0, 0) deliğinde; noktalar WCS'ye frame ile taşınır."""
    yerel = [(0.0, 0.0, Z_R), (0.0, 0.0, Z_DIP), (0.0, 0.0, Z_R), (0.0, 0.0, Z_BAS)]
    W = frame.to_world(np.array([(0.0, 0.0, Z_BAS)] + yerel))
    F = S * P
    tipler = [MoveType.RAPID, MoveType.LINEAR, MoveType.LINEAR, MoveType.RAPID]
    moves = [
        Move(t, tuple(float(v) for v in p), None if t is MoveType.RAPID else F)
        for t, p in zip(tipler, W[1:], strict=True)
    ]
    tp = Toolpath("kilavuz", _kilavuz(), tuple(float(v) for v in W[0]), moves, S, Plane.XY, FeedMode.PER_MIN)
    tp.validate()
    return tp


def _delik() -> PolarMap:
    """Yerel harita: Ø20 blokta D₁ ön delik, z ∈ [−20, 0]; z > −3 havşa (r_iç = r_dış, malzeme yok)."""
    m = PolarMap.from_stock(
        CylinderStock(D=20.0, zmin=-20.0, zmax=0.0, d=D1_iso(D, P)), dtheta_deg=1.0, dz=DZ
    )
    ust = m.centers() > HAVSA
    m.r_in[:, ust] = m.r_out[:, ust]
    return m


@functools.cache
def _sonuc(egik: bool):
    # fixture değil: simülasyon test gövdesinde çağrılsın (uygulanmamış kod "uygulanmamış" sayılsın)
    fr = _egik() if egik else BIRIM
    return simulate_thread([_g84(fr)], _delik(), frame=fr)


def test_K5_kilavuz_iso_ic_profil():
    m = _sonuc(False)
    s = thread_measure(m, "ic", OLCUM)
    assert s.P == pytest.approx(P, abs=1e-3)
    assert s.d2 == pytest.approx(8.0 - 0.649519 * 1.25, abs=DZ)
    assert s.d2 == pytest.approx(d2_iso(D, P), abs=DZ)
    assert s.d_root == pytest.approx(8.0 - 1.082532 * 1.25, abs=DZ)
    assert s.lead_err <= DZ


def test_K5_kilavuz_dis_cap_ve_dokunulmayan_bolge():
    """Kılavuz yalnız delik duvarını keser: r_dış değişmez; dibin altı (z < −15 − pay) dokunulmamış."""
    m = _sonuc(False)
    bas = _delik()
    np.testing.assert_array_equal(np.asarray(m.r_out), np.asarray(bas.r_out))
    alt = m.centers() < Z_DIP - 0.5
    np.testing.assert_allclose(np.asarray(m.r_in)[:, alt], D1_iso(D, P) / 2, atol=1e-12)
    assert m.volume() < bas.volume()


def test_K5_egik_delik_ayni_sonuc():
    a, b = _sonuc(False), _sonuc(True)
    np.testing.assert_allclose(np.asarray(b.r_in), np.asarray(a.r_in), rtol=0, atol=1e-6)
    np.testing.assert_allclose(np.asarray(b.r_out), np.asarray(a.r_out), rtol=0, atol=1e-6)
    sa, sb = thread_measure(a, "ic", OLCUM), thread_measure(b, "ic", OLCUM)
    assert sb.d2 == pytest.approx(sa.d2, abs=1e-6)
    assert sb.d_root == pytest.approx(sa.d_root, abs=1e-6)


def test_K5_04b_tapop_yolu():
    """04b TapOp.to_toolpath() (G84 kanonik açılımı) aynı sonucu verir. 04b main'de değilse uygulanmamış."""
    try:
        from cam.cevrimler import TapOp
    except ImportError as e:  # 04b (#81) birleşince yeşile döner
        raise NotImplementedError("SPEC 04b TapOp henüz main'de değil") from e
    op = TapOp("kilavuz", _kilavuz(), S, (0.0, 0.0, Z_BAS), [(0.0, 0.0)], z=Z_DIP, r=Z_R)
    m = simulate_thread([op.to_toolpath()], _delik(), frame=BIRIM)
    np.testing.assert_allclose(np.asarray(m.r_in), np.asarray(_sonuc(False).r_in), rtol=0, atol=1e-9)
