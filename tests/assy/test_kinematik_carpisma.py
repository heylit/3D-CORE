"""SPEC 33 — hareket boyunca çarpışma testleri (OCCT): sweep_clashes ve first_contact (K14–K16, K13'ün
parça gerektiren hata durumları).

Testler sadece specs/33-kinematik.md'deki teori ve arayüzden yazıldı; assy/kinematik.py gövdesi okunmadı.
Parçalar geometry.features.block / cylinder ile kurulur (uydurma geometri). Her adımda montaj düz bir SPEC 07
ağacına çevrilip SPEC 09 check çağrılır; Clash a, b bileşen adlarıdır. Eklemle doğrudan bağlı çiftler
varsayılan olarak atlanır (ignore_joined=True), bu yüzden engeller zemine eklemsiz bağlı ayrı sabit
bileşenlerdir; zeminin kendi parçası mekanizmadan uzağa konur.

Analitik değerler (SPEC 33 Teori):
    kayan blok: 10 mm küp x boyunca kayar, s = 0'da duvara uzaklık g → ilk temas s = g;
                s > g'de girişim hacmi 10·10·(s − g)
    dönen kol:  kutu [0, Lk] × [−e, e] × [0, h], z etrafında; engel y ≥ w →
                θ* = asin(w / √(Lk² + e²)) − atan2(e, Lk)
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("build123d")

from assy.girisim import ClashKind  # noqa: E402
from assy.kinematik import MotionClash, first_contact, sweep, sweep_clashes  # noqa: E402
from assy.model import Assembly, AssyError, Component, Joint, JointKind, Ref, RefKind, transform  # noqa: E402
from geometry.features import block, cylinder  # noqa: E402

pytestmark = pytest.mark.occt

EX = (1.0, 0.0, 0.0)
EZ = (0.0, 0.0, 1.0)


def eksen(comp: str, o=(0.0, 0.0, 0.0), z=EZ) -> Ref:
    return Ref(comp, RefKind.AXIS, o, z)


def _zemin_parcasi():
    """Zeminin parçası mekanizmadan uzakta küçük bir küp (hiçbir şeye değmez)."""
    return block(1.0, 1.0, 1.0, name="taban").moved(transform(t=(-100.0, -100.0, -100.0)))


def kayan_blok(g: float = 5.0) -> tuple[Assembly, dict]:
    """kup: 10 mm küp x ∈ [0, 10], zemine x ekseni boyunca PRISMATIC (s = öteleme).
    duvar: sabit, x ∈ [10 + g, 20 + g], aynı y, z aralığı."""
    asm = Assembly(
        name="kizak",
        components=[
            Component("zemin", "taban", fixed=True),
            Component("duvar", "duvar", T=transform(t=(10.0 + g, 0.0, 0.0)), fixed=True),
            Component("kup", "kup"),
        ],
        joints=[Joint("J", JointKind.PRISMATIC, eksen("zemin", z=EX), eksen("kup", z=EX))],
    )
    parts = {
        "taban": _zemin_parcasi(),
        "duvar": block(10.0, 10.0, 10.0, name="duvar"),
        "kup": block(10.0, 10.0, 10.0, name="kup"),
    }
    return asm, parts


LK, E, H, W = 50.0, 3.0, 5.0, 20.0


def donen_kol() -> tuple[Assembly, dict]:
    """kol: [0, Lk] × [−e, e] × [0, h], zemine z ekseni etrafında REVOLUTE. engel: sabit, y ∈ [w, w + 50],
    x ∈ [0, Lk + 10], z ∈ [−5, 15]."""
    asm = Assembly(
        name="kol",
        components=[
            Component("zemin", "taban", fixed=True),
            Component("engel", "engel", fixed=True),
            Component("kol", "kol"),
        ],
        joints=[Joint("J", JointKind.REVOLUTE, eksen("zemin"), eksen("kol"))],
    )
    parts = {
        "taban": _zemin_parcasi(),
        "engel": block(LK + 10.0, 50.0, 20.0, name="engel").moved(transform(t=(0.0, W, -5.0))),
        "kol": block(LK, 2 * E, H, name="kol").moved(transform(t=(0.0, -E, 0.0))),
    }
    return asm, parts


def theta_yildiz() -> float:
    return math.degrees(math.asin(W / math.hypot(LK, E)) - math.atan2(E, LK))


def pimli() -> tuple[Assembly, dict]:
    """plaka (sabit) içinden geçen pim; REVOLUTE ile bağlı, tasarım gereği iç içe (girişim)."""
    asm = Assembly(
        name="pim",
        components=[
            Component("plaka", "plaka", fixed=True),
            Component("pim", "pim", T=transform(t=(15.0, 15.0, -5.0))),
        ],
        joints=[Joint("J", JointKind.REVOLUTE, eksen("plaka", (15.0, 15.0, -5.0)), eksen("pim"))],
    )
    parts = {"plaka": block(30.0, 30.0, 10.0, name="plaka"), "pim": cylinder(5.0, 20.0, name="pim")}
    return asm, parts


def _adim_raporu(clashes: list[MotionClash]) -> dict[int, list[MotionClash]]:
    out: dict[int, list[MotionClash]] = {}
    for mc in clashes:
        out.setdefault(mc.step, []).append(mc)
    return out


# ---------- K14 first_contact, kayan blok ----------


def test_first_contact_sliding_block():
    asm, parts = kayan_blok(g=5.0)
    tol = 1e-3
    s = first_contact(asm, parts, "J", 0.0, 10.0, steps=50, tol=tol)
    assert s is not None
    assert 5.0 - tol <= s <= 5.0


def test_first_contact_sliding_block_none_before_wall():
    asm, parts = kayan_blok(g=5.0)
    assert first_contact(asm, parts, "J", 0.0, 4.0, steps=20) is None


def test_first_contact_already_clashing_returns_start():
    asm, parts = kayan_blok(g=5.0)
    asm.component("kup").T = transform(t=(7.0, 0.0, 0.0))
    assert first_contact(asm, parts, "J", 7.0, 10.0, steps=10) == pytest.approx(7.0, abs=1e-12)


# ---------- K15 first_contact, dönen kol ----------


def test_first_contact_rotating_arm():
    asm, parts = donen_kol()
    tol = 1e-3
    beklenen = theta_yildiz()  # ≈ 20.0997°
    theta = first_contact(asm, parts, "J", 0.0, 45.0, steps=45, tol=tol)
    assert theta is not None
    assert beklenen - tol <= theta <= beklenen


# ---------- K16 sweep_clashes ----------


def test_sweep_clashes_sliding_block():
    asm, parts = kayan_blok(g=5.0)
    values = [float(k) for k in range(11)]  # 0..10 mm
    motion = sweep(asm, "J", values)
    clashes = sweep_clashes(asm, parts, motion)
    assert all(isinstance(mc, MotionClash) for mc in clashes)
    assert [mc.step for mc in clashes] == sorted(mc.step for mc in clashes)  # adım sırasıyla
    rapor = _adim_raporu(clashes)
    for k, s in enumerate(values):
        adim = rapor.get(k, [])
        if s < 5.0:
            assert adim == []
            continue
        assert len(adim) == 1
        mc = adim[0]
        assert mc.value == pytest.approx(s, abs=1e-9)
        assert {mc.clash.a, mc.clash.b} == {"kup", "duvar"}
        if s == 5.0:
            assert mc.clash.kind is ClashKind.TEMAS
        else:
            assert mc.clash.kind is ClashKind.GIRISIM
            assert mc.clash.volume == pytest.approx(10.0 * 10.0 * (s - 5.0), rel=1e-6)


def test_sweep_clashes_clearance_narrow():
    """clearance = 2: 3 < s < 5 adımları (s = 4) DAR; s = 3'te boşluk tam 2 (DAR değil)."""
    asm, parts = kayan_blok(g=5.0)
    values = [float(k) for k in range(11)]
    rapor = _adim_raporu(sweep_clashes(asm, parts, sweep(asm, "J", values), clearance=2.0))
    for k in range(4):
        assert rapor.get(k, []) == []
    assert [mc.clash.kind for mc in rapor[4]] == [ClashKind.DAR]
    assert rapor[4][0].clash.distance == pytest.approx(1.0, abs=1e-6)
    assert [mc.clash.kind for mc in rapor[5]] == [ClashKind.TEMAS]
    for k in range(6, 11):
        assert [mc.clash.kind for mc in rapor[k]] == [ClashKind.GIRISIM]


def test_sweep_clashes_ignore_joined():
    asm, parts = pimli()
    motion = sweep(asm, "J", [0.0, 45.0, 90.0])
    assert sweep_clashes(asm, parts, motion) == []
    assert sweep_clashes(asm, parts, motion, ignore_joined=True) == []
    rapor = _adim_raporu(sweep_clashes(asm, parts, motion, ignore_joined=False))
    assert sorted(rapor) == [0, 1, 2]
    for k in range(3):
        assert len(rapor[k]) == 1
        assert {rapor[k][0].clash.a, rapor[k][0].clash.b} == {"plaka", "pim"}
        assert rapor[k][0].clash.kind is ClashKind.GIRISIM
    # açık ignore listesi de çifti atlar
    assert sweep_clashes(asm, parts, motion, ignore_joined=False, ignore=[("plaka", "pim")]) == []


# ---------- K13 parça gerektiren hatalar ----------


def _hareket():
    asm, parts = kayan_blok(g=5.0)
    return asm, parts, sweep(asm, "J", [0.0, 1.0])


HATALAR = {
    "first_contact_steps_0": lambda a, p, m: first_contact(a, p, "J", 0.0, 10.0, steps=0),
    "first_contact_tol_0": lambda a, p, m: first_contact(a, p, "J", 0.0, 10.0, tol=0.0),
    "first_contact_tol_negatif": lambda a, p, m: first_contact(a, p, "J", 0.0, 10.0, tol=-1e-3),
    "first_contact_start_esit_end": lambda a, p, m: first_contact(a, p, "J", 3.0, 3.0),
    "first_contact_clearance_negatif": lambda a, p, m: first_contact(a, p, "J", 0.0, 10.0, clearance=-1.0),
    "first_contact_bilinmeyen_eklem": lambda a, p, m: first_contact(a, p, "yok", 0.0, 10.0),
    "sweep_clashes_clearance_negatif": lambda a, p, m: sweep_clashes(a, p, m, clearance=-1.0),
    "sweep_clashes_eksik_parca": lambda a, p, m: sweep_clashes(
        a, {k: v for k, v in p.items() if k != "duvar"}, m
    ),
    "first_contact_eksik_parca": lambda a, p, m: first_contact(
        a, {k: v for k, v in p.items() if k != "kup"}, "J", 0.0, 10.0
    ),
}


@pytest.mark.parametrize("durum", list(HATALAR))
def test_errors_with_parts(durum):
    asm, parts, motion = _hareket()
    with pytest.raises(AssyError):
        HATALAR[durum](asm, parts, motion)
