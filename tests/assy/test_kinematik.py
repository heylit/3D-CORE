"""SPEC 33 — assy/kinematik.py testleri (OCCT'siz): eklem artıkları, Jacobian, koordinatlar, serbestlik,
sürme, süpürme, sürükleme, değişmezlik ve hatalar (K1–K13).

Testler sadece specs/33-kinematik.md'deki teori ve arayüzden yazıldı; assy/kinematik.py gövdesi okunmadı.
Beklenen değerler SPEC'in "Analitik doğrulama değerleri" bölümündeki kapalı formlardan (sarkaç, krank–biyel,
dört çubuk + Freudenstein, Grashof kilidi) elle türetildi; her yardımcının açıklamasında formül yazılı.

Montajlar Assembly(joints=[...]) ile doğrudan kurulur (A1: validate / to_dict henüz eklemleri işlemiyor);
yalnız SPEC 33 fonksiyonları sınanır.

K2 notu: sürme kısıtlarının (dönme / öteleme kilidi) artık ve Jacobian'ı arayüzde açık değil; onların
doğruluğu `drive` / `sweep` yakınsamasıyla (K5–K8, 1e-9) dolaylı sınanır.
Açık eklem Jacobian'ı merkezi farkla sınanır.
Karakteristik uzunluk L (SPEC 08: referans noktalarının dünya çapı, en az 1 mm) merkezi farkta sabit kalsın
diye K2'de tüm referans noktaları 1 mm'lik bir küre içinde tutulur (L = 1).

Toleranslar (SPEC 33): konum 1e-9 mm, açı 1e-9 derece, artık özdeşliği 1e-12.
Kod henüz yokken (NotImplementedError) testler kök conftest.py ile "uygulanmamış" (xfail) sayılır.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from assy.kinematik import (
    Mobility,
    Motion,
    drag,
    drive,
    joint_jacobian,
    joint_residual,
    joint_value,
    mobility,
    sweep,
)
from assy.mates import rodrigues
from assy.model import (
    Assembly,
    AssyError,
    Component,
    Joint,
    JointKind,
    Mate,
    MateKind,
    Ref,
    RefKind,
    is_rigid,
    rot_x,
    rot_y,
    rot_z,
    transform,
)

FIX, REV, PRI, CYL, SPH = (
    JointKind.FIXED,
    JointKind.REVOLUTE,
    JointKind.PRISMATIC,
    JointKind.CYLINDRICAL,
    JointKind.SPHERICAL,
)
TOL_POS = 1e-9  # mm
TOL_ACI = 1e-9  # derece
TOL_R = 1e-10  # çözüm artığı (drive / drag tol varsayılanı)
# Karakteristik uzunluk L = 1 mm olan küçük mekanizmalarda (sarkaç, mil, blok: tüm eklem noktaları tek yerde)
# varsayılan tol = 1e-10 artık ≈ 1e-10 rad ≈ 6e-9 derece demektir, 1e-9 derece kontrolünü garanti etmez; bu
# testler tol = 1e-11 ile çağrılır. L ≈ 70 mm olan krank–biyel / dört çubukta varsayılan tol yeter.
TOL_COZ = 1e-11

# ---------- Yardımcılar ----------


def eksen(comp: str, o=(0.0, 0.0, 0.0), z=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.AXIS, o, z)


def nokta(comp: str, o=(0.0, 0.0, 0.0)) -> Ref:
    return Ref(comp, RefKind.POINT, o)


def bilesen(name: str, T=None, fixed: bool = False) -> Component:
    return Component(name=name, part=name, T=np.eye(4) if T is None else T, fixed=fixed)


def montaj(components, joints, mates=()) -> Assembly:
    return Assembly(name="mekanizma", components=list(components), mates=list(mates), joints=list(joints))


def dn(T: np.ndarray, p) -> np.ndarray:
    """Yerel noktanın dünya karşılığı: R p + t."""
    return T[:3, :3] @ np.asarray(p, dtype=float) + T[:3, 3]


def aci_farki(a: float, b: float) -> float:
    """a − b, (−180, 180] aralığına sarılmış (derece)."""
    return (a - b + 180.0) % 360.0 - 180.0


def birim(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def sifir_yonu(z, zero=None) -> np.ndarray:
    """SPEC 33 sıfır yönü kuralı (yerel): zero verilirse onun z'ye dik bileşeni; yoksa |z·e| en küçük taban
    vektörü (eşitlikte x, y, z sırası), x = birim(e − (e·z) z)."""
    z = birim(z)
    if zero is None:
        k = int(np.argmin(np.abs(z)))  # argmin eşitlikte ilk indisi verir: x, y, z sırası
        e = np.eye(3)[k]
    else:
        e = np.asarray(zero, dtype=float)
    return birim(e - (e @ z) * z)


def snapshot(asm: Assembly) -> dict[str, np.ndarray]:
    return {c.name: c.T.copy() for c in asm.components}


def degismedi(asm: Assembly, onceki: dict[str, np.ndarray]) -> bool:
    return all(np.array_equal(asm.component(n).T, T) for n, T in onceki.items())


def uygula(asm: Assembly, res) -> Assembly:
    work = copy.deepcopy(asm)
    res.apply(work)
    return work


def max_eklem_artigi(asm: Assembly) -> float:
    return max(float(np.max(np.abs(joint_residual(asm, j)))) for j in asm.joints)


# ---------- Mekanizmalar ----------

L_SARKAC = 10.0


def sarkac(theta: float = 0.0, limits=None) -> Assembly:
    """Zemin + kol, REVOLUTE eksen z, merkez orijin.

    Kol ucu yerelde (L, 0, 0): θ'da uç (L cos θ, L sin θ, 0)."""
    zemin = bilesen("zemin", fixed=True)
    kol = bilesen("kol", T=transform(rot_z(theta)))
    return montaj([zemin, kol], [Joint("J", REV, eksen("zemin"), eksen("kol"), limits=limits)])


R_K, L_B = 20.0, 70.0  # krank yarıçapı, biyel boyu


def piston_x(theta: float, r: float = R_K, l: float = L_B) -> float:  # noqa: E741 (formüldeki sembol)
    """Krank–biyel: x = r cos θ + √(l² − r² sin² θ) (Uicker–Pennock–Shigley, Bölüm 3)."""
    t = math.radians(theta)
    return r * math.cos(t) + math.sqrt(l * l - (r * math.sin(t)) ** 2)


def krank_biyel(theta: float) -> Assembly:
    """Krank–biyel θ'da kapalı formla kurulmuş, düzlem z = 0, piston x ekseninde.

    krank: orijinde döner, pim yerelde (r, 0, 0) → A = r(cos θ, sin θ, 0)
    biyel: yerel orijin A'da, öbür pim yerelde (l, 0, 0) → piston pimi (x, 0, 0)
    piston: yerel orijin (x, 0, 0); zemine x ekseni boyunca PRISMATIC (s = x)
    """
    t = math.radians(theta)
    A = np.array([R_K * math.cos(t), R_K * math.sin(t), 0.0])
    x = piston_x(theta)
    phi = math.degrees(math.atan2(-A[1], x - A[0]))
    comps = [
        bilesen("zemin", fixed=True),
        bilesen("krank", T=transform(rot_z(theta))),
        bilesen("biyel", T=transform(rot_z(phi), A)),
        bilesen("piston", T=transform(t=(x, 0.0, 0.0))),
    ]
    ex = (1.0, 0.0, 0.0)
    joints = [
        Joint("J_krank", REV, eksen("zemin"), eksen("krank")),
        Joint("J_A", REV, eksen("krank", (R_K, 0, 0)), eksen("biyel")),
        Joint("J_B", REV, eksen("biyel", (L_B, 0, 0)), eksen("piston")),
        Joint("J_kayar", PRI, eksen("zemin", z=ex), eksen("piston", z=ex)),
    ]
    return montaj(comps, joints)


def dort_cubuk_B(a: float, b: float, c: float, d: float, theta2: float) -> np.ndarray:
    """A = a(cos θ2, sin θ2) merkezli b ve B0 = (d, 0) merkezli c yarıçaplı çemberlerin kesişimi; açık dal
    (A→B0 doğrultusunun solu, θ2 = 0'da B_y > 0)."""
    t = math.radians(theta2)
    A = np.array([a * math.cos(t), a * math.sin(t)])
    D = np.array([d, 0.0]) - A
    delta = float(np.linalg.norm(D))
    u = D / delta
    aa = (b * b - c * c + delta * delta) / (2.0 * delta)
    h = math.sqrt(b * b - aa * aa)
    return A + aa * u + h * np.array([-u[1], u[0]])


def theta4(a, b, c, d, theta2) -> float:
    B = dort_cubuk_B(a, b, c, d, theta2)
    return math.degrees(math.atan2(B[1], B[0] - d))


def dort_cubuk(a, b, c, d, theta2: float = 0.0, limits_kol=None) -> Assembly:
    """Düzlemsel dört çubuk θ2'de kapalı formla kurulmuş. Kol ekleminin koordinatı θ4."""
    t = math.radians(theta2)
    A = np.array([a * math.cos(t), a * math.sin(t), 0.0])
    B = np.append(dort_cubuk_B(a, b, c, d, theta2), 0.0)
    phi3 = math.degrees(math.atan2(B[1] - A[1], B[0] - A[0]))
    th4 = math.degrees(math.atan2(B[1], B[0] - d))
    comps = [
        bilesen("zemin", fixed=True),
        bilesen("krank", T=transform(rot_z(theta2))),
        bilesen("biyel", T=transform(rot_z(phi3), A)),
        bilesen("kol", T=transform(rot_z(th4), (d, 0.0, 0.0))),
    ]
    joints = [
        Joint("J_krank", REV, eksen("zemin"), eksen("krank")),
        Joint("J_A", REV, eksen("krank", (a, 0, 0)), eksen("biyel")),
        Joint("J_B", REV, eksen("biyel", (b, 0, 0)), eksen("kol", (c, 0, 0))),
        Joint("J_kol", REV, eksen("zemin", (d, 0, 0)), eksen("kol"), limits=limits_kol),
    ]
    return montaj(comps, joints)


GRASHOF = (20.0, 60.0, 50.0, 70.0)  # a, b, c, d: krank–sarkaç
GRASHOF_DISI = (40.0, 30.0, 30.0, 60.0)


# ---------- Elle kurulmuş eklem konumları (K1) ----------


def rastgele_R(rng: np.random.Generator) -> np.ndarray:
    return rodrigues(rng.normal(size=3) * 1.5)


def bagli_T_b(Ta, oa, za, ob, zb, theta=0.0, s=0.0, zero_a=None, zero_b=None, ters=False) -> np.ndarray:
    """b'nin çerçevesini a'nınkine oturtan T_b: z_b = z_a, x_b = cos θ x_a + sin θ y_a, p_b = p_a + s z_a.
    ters=True: z_b = −z_a (yanlış dal, x_b korunur)."""
    Ra = Ta[:3, :3]
    p = dn(Ta, oa)
    z = Ra @ birim(za)
    x = Ra @ sifir_yonu(za, zero_a)
    y = np.cross(z, x)
    t = math.radians(theta)
    xb_w = math.cos(t) * x + math.sin(t) * y
    zb_w = -z if ters else z
    W = np.column_stack([xb_w, np.cross(zb_w, xb_w), zb_w])
    xl = sifir_yonu(zb, zero_b)
    zl = birim(zb)
    Lb = np.column_stack([xl, np.cross(zl, xl), zl])
    Rb = W @ Lb.T
    return transform(Rb, p + s * z - Rb @ np.asarray(ob, dtype=float))


SATIR = {FIX: 9, REV: 6, PRI: 9, CYL: 6, SPH: 3}
KOORDINAT = {FIX: (0.0, 0.0), REV: (73.0, 0.0), PRI: (0.0, -12.5), CYL: (-121.0, 8.0)}


def tek_eklem(kind, rng, theta=0.0, s=0.0, ters=False, kaydir=None):
    """İki serbest olmayan gövde: a sabit değil (genel konum), b eklemle a'ya oturtulmuş."""
    Ta = transform(rastgele_R(rng), rng.uniform(-30, 30, 3))
    oa, ob = rng.uniform(-20, 20, 3), rng.uniform(-20, 20, 3)
    za, zb = birim(rng.normal(size=3)), birim(rng.normal(size=3))
    if kind is SPH:
        Tb = transform(rastgele_R(rng))
        Tb[:3, 3] = dn(Ta, oa) - Tb[:3, :3] @ ob
        j = Joint("J", SPH, nokta("a", oa), nokta("b", ob))
    else:
        Tb = bagli_T_b(Ta, oa, za, ob, zb, theta, s, ters=ters)
        j = Joint("J", kind, eksen("a", oa, za), eksen("b", ob, zb))
    if kaydir is not None:
        Tb[:3, 3] += kaydir(Ta, za)
    asm = montaj([bilesen("a", Ta), bilesen("b", Tb)], [j])
    return asm, j


# ---------- K1 Eklem artıkları ----------


@pytest.mark.parametrize("kind", [FIX, REV, PRI, CYL, SPH])
def test_joint_residual_satisfied(kind):
    rng = np.random.default_rng(33)
    theta, s = KOORDINAT.get(kind, (0.0, 0.0))
    asm, j = tek_eklem(kind, rng, theta, s)
    r = joint_residual(asm, j)
    assert r.shape == (SATIR[kind],)
    assert np.max(np.abs(r)) <= 1e-12


def test_joint_residual_revolute_offset():
    """b, eklem noktasından 3 mm kaçık: konum satırları p_b − p_a, |·| = 3."""
    u = birim([1.0, -2.0, 0.5])
    asm, j = tek_eklem(REV, np.random.default_rng(1), theta=20.0, kaydir=lambda Ta, za: 3.0 * u)
    r = joint_residual(asm, j)
    assert np.linalg.norm(r[:3]) == pytest.approx(3.0, abs=1e-12)
    assert np.max(np.abs(r[3:])) <= 1e-12  # yön satırları etkilenmez


def test_joint_residual_prismatic_sideways():
    """PRISMATIC'te b ekseni 2 mm yana (ve eksen boyunca 4 mm) kayık: |(p_b − p_a) × z_a| = 2."""

    def yana(Ta, za):
        z = Ta[:3, :3] @ birim(za)
        n = birim(np.cross(z, [0.3, 1.0, -0.2]))
        return 2.0 * n + 4.0 * z

    asm, j = tek_eklem(PRI, np.random.default_rng(2), kaydir=yana)
    r = joint_residual(asm, j)
    assert np.linalg.norm(r[:3]) == pytest.approx(2.0, abs=1e-12)
    assert np.max(np.abs(r[3:])) <= 1e-12


@pytest.mark.parametrize("kind", [FIX, REV, PRI, CYL])
def test_joint_residual_reversed_axis_not_satisfied(kind):
    """Eklemler yönlü: z_b = −z_a sağlanmış sayılmaz (L(z_b − z_a) = −2 L z_a, L ≥ 1)."""
    asm, j = tek_eklem(kind, np.random.default_rng(3), ters=True)
    assert np.max(np.abs(joint_residual(asm, j))) >= 1.0


# ---------- K2 Jacobian = merkezi fark ----------


def _kucuk_rastgele_eklem(kind, rng, a_sabit: bool):
    """Tüm referans noktaları 1 mm'lik küre içinde (L = 1 sabit): orijinler ve ötelemeler ≤ 0.2 mm."""

    def kucuk():
        return rng.uniform(-0.2, 0.2, 3)

    Ta = transform(rastgele_R(rng), kucuk())
    Tb = transform(rastgele_R(rng), kucuk())
    if kind is SPH:
        j = Joint("J", SPH, nokta("a", kucuk()), nokta("b", kucuk()))
    else:
        zero_b = tuple(rng.normal(size=3)) if rng.uniform() < 0.5 else None
        j = Joint(
            "J",
            kind,
            eksen("a", kucuk(), rng.normal(size=3)),
            eksen("b", kucuk(), rng.normal(size=3)),
            zero_b=zero_b,
        )
    return montaj([bilesen("a", Ta, fixed=a_sabit), bilesen("b", Tb)], [j]), j


def _pertur(asm: Assembly, name: str, k: int, h: float) -> None:
    """x = [Δt, ω] bileşeninin k. elemanına h: R' = exp([ω]×) R, t' = t + Δt (SPEC 08)."""
    c = asm.component(name)
    dx = np.zeros(6)
    dx[k] = h
    T = c.T.copy()
    T[:3, :3] = rodrigues(dx[3:]) @ T[:3, :3]
    T[:3, 3] = T[:3, 3] + dx[:3]
    c.T = T


def _fd_jacobian(asm: Assembly, j: Joint, unknowns: list[str], h: float = 1e-6) -> np.ndarray:
    cols = []
    for name in unknowns:
        for k in range(6):
            artı, eksi = copy.deepcopy(asm), copy.deepcopy(asm)
            _pertur(artı, name, k, h)
            _pertur(eksi, name, k, -h)
            ja = next(x for x in artı.joints if x.name == j.name)
            je = next(x for x in eksi.joints if x.name == j.name)
            cols.append((joint_residual(artı, ja) - joint_residual(eksi, je)) / (2 * h))
    return np.column_stack(cols)


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("kind", [FIX, REV, PRI, CYL, SPH])
def test_joint_jacobian_matches_fd(kind, seed):
    rng = np.random.default_rng(100 + seed)
    asm, j = _kucuk_rastgele_eklem(kind, rng, a_sabit=False)
    for unknowns in (["a", "b"], ["b", "a"]):
        J = joint_jacobian(asm, j, unknowns)
        assert J.shape == (SATIR[kind], 12)
        np.testing.assert_allclose(J, _fd_jacobian(asm, j, unknowns), rtol=0, atol=1e-6)


@pytest.mark.parametrize("kind", [FIX, REV, PRI, CYL, SPH])
def test_joint_jacobian_fixed_parent_has_no_columns(kind):
    """Sabit bileşenin sütunu yok (SPEC 08 jacobian düzeni): unknowns = ["b"] → 6 sütun."""
    asm, j = _kucuk_rastgele_eklem(kind, np.random.default_rng(7), a_sabit=True)
    J = joint_jacobian(asm, j, ["b"])
    assert J.shape == (SATIR[kind], 6)
    np.testing.assert_allclose(J, _fd_jacobian(asm, j, ["b"]), rtol=0, atol=1e-6)


# ---------- K3 joint_value ----------


@pytest.mark.parametrize("alpha", [-170.0, -90.0, 0.0, 37.0, 135.0, 180.0])
def test_joint_value_revolute(alpha):
    """b, z_a etrafında rot(α): θ = α, (−180, 180] aralığında (180 dahil)."""
    asm = sarkac(alpha)
    assert joint_value(asm, "J") == pytest.approx(alpha, abs=TOL_ACI)
    assert joint_value(asm, asm.joints[0]) == pytest.approx(alpha, abs=TOL_ACI)


def test_joint_value_revolute_180_is_positive():
    asm = sarkac(180.0)
    v = joint_value(asm, "J")
    assert -180.0 < v <= 180.0
    assert v == pytest.approx(180.0, abs=TOL_ACI)


def test_joint_value_revolute_general_axis_and_frames():
    """Genel konumlu zemin, eksen x: b'yi a çerçevesinde rot_x(α) ile döndürmek θ = α.

    (sağ el kuralı, z_a etrafında)"""
    G = transform(rot_z(25.0) @ rot_y(-40.0), (3.0, -4.0, 8.0))
    ex = (1.0, 0.0, 0.0)
    for alpha in (-60.0, 15.0, 170.0):
        asm = montaj(
            [bilesen("zemin", G, fixed=True), bilesen("kol", G @ transform(rot_x(alpha)))],
            [Joint("J", REV, eksen("zemin", z=ex), eksen("kol", z=ex))],
        )
        assert joint_value(asm, "J") == pytest.approx(alpha, abs=TOL_ACI)


@pytest.mark.parametrize("s", [-7.5, 0.0, 12.25])
def test_joint_value_prismatic(s):
    ey = (0.0, 1.0, 0.0)
    asm = montaj(
        [bilesen("zemin", fixed=True), bilesen("blok", transform(t=(0.0, s, 0.0)))],
        [Joint("P", PRI, eksen("zemin", (1, 2, 3), ey), eksen("blok", (1, 2, 3), ey))],
    )
    assert joint_value(asm, "P") == pytest.approx(s, abs=TOL_POS)


def test_joint_value_cylindrical():
    asm = montaj(
        [bilesen("zemin", fixed=True), bilesen("mil", transform(rot_z(-110.0), (0.0, 0.0, -4.0)))],
        [Joint("C", CYL, eksen("zemin"), eksen("mil"))],
    )
    theta, s = joint_value(asm, "C")
    assert theta == pytest.approx(-110.0, abs=TOL_ACI)
    assert s == pytest.approx(-4.0, abs=TOL_POS)


@pytest.mark.parametrize(
    ("z", "x_beklenen", "R", "alpha"),
    [
        ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), rot_z, 30.0),
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), rot_x, 30.0),
    ],
)
def test_joint_value_auto_zero_direction(z, x_beklenen, R, alpha):
    """zero_a verilmez (otomatik kural), zero_b açıkça beklenen x: θ = α ancak x_a = beklenen x ise."""
    asm = montaj(
        [bilesen("zemin", fixed=True), bilesen("kol", transform(R(alpha)))],
        [Joint("J", REV, eksen("zemin", z=z), eksen("kol", z=z), zero_b=x_beklenen)],
    )
    assert joint_value(asm, "J") == pytest.approx(alpha, abs=TOL_ACI)


def test_joint_value_spherical_and_fixed_raise():
    asm = montaj(
        [bilesen("zemin", fixed=True), bilesen("top"), bilesen("govde")],
        [
            Joint("S", SPH, nokta("zemin"), nokta("top")),
            Joint("F", FIX, eksen("zemin"), eksen("govde")),
        ],
    )
    with pytest.raises(AssyError):
        joint_value(asm, "S")
    with pytest.raises(AssyError):
        joint_value(asm, "F")


# ---------- K4 mobility ----------


def _tek_govde(kind) -> Assembly:
    a, b = (nokta("zemin"), nokta("govde")) if kind is SPH else (eksen("zemin"), eksen("govde"))
    return montaj([bilesen("zemin", fixed=True), bilesen("govde")], [Joint("J", kind, a, b)])


@pytest.mark.parametrize(
    ("kind", "beklenen"),
    [(REV, (1, 1, 0)), (PRI, (1, 1, 0)), (CYL, (2, 2, 0)), (SPH, (3, 3, 0)), (FIX, (0, 0, 0))],
)
def test_mobility_single_body(kind, beklenen):
    m = mobility(_tek_govde(kind))
    assert isinstance(m, Mobility)
    assert (m.gruebler, m.dof, m.redundant) == beklenen


def test_mobility_serial_arm():
    """M = 6·2 − 2·5 = 2."""
    asm = montaj(
        [bilesen("zemin", fixed=True), bilesen("kol1"), bilesen("kol2", transform(t=(10, 0, 0)))],
        [
            Joint("J1", REV, eksen("zemin"), eksen("kol1")),
            Joint("J2", REV, eksen("kol1", (10, 0, 0)), eksen("kol2")),
        ],
    )
    assert mobility(asm) == Mobility(2, 2, 0)


def test_mobility_four_bar():
    """Uzaysal Kutzbach M = 6·3 − 4·5 = −2, gerçek dof = 1 (paralel eksenler): redundant = 3."""
    assert mobility(dort_cubuk(*GRASHOF, theta2=30.0)) == Mobility(-2, 1, 3)


def test_mobility_slider_crank():
    """3 REVOLUTE + 1 PRISMATIC: M = 18 − 20 = −2, dof = 1."""
    assert mobility(krank_biyel(45.0)) == Mobility(-2, 1, 3)


def test_mobility_duplicate_joint():
    """Aynı eklem iki kez (farklı adla): rank değişmez, M 5 azalır."""
    asm = sarkac(10.0)
    asm.joints.append(Joint("J_kopya", REV, eksen("zemin"), eksen("kol")))
    assert mobility(asm) == Mobility(1 - 5, 1, 5)


def test_mobility_joint_plus_mate():
    """REVOLUTE (z) + eksene dik iki AXIS arasında ANGLE 60° (c = 1): M = 0, dof = 0."""
    ex = (1.0, 0.0, 0.0)
    asm = montaj(
        [bilesen("zemin", fixed=True), bilesen("kol", transform(rot_z(60.0)))],
        [Joint("J", REV, eksen("zemin"), eksen("kol"))],
        [Mate(MateKind.ANGLE, eksen("zemin", z=ex), eksen("kol", z=ex), value=60.0)],
    )
    assert mobility(asm) == Mobility(0, 0, 0)


def test_mobility_joint_between_fixed_components_ignored():
    """İki ucu da sabit bileşende olan eklem M'ye girmez (zemin üzerinde döngü)."""
    asm = montaj(
        [bilesen("zemin", fixed=True), bilesen("zemin2", fixed=True), bilesen("kol")],
        [
            Joint("J_zz", REV, eksen("zemin"), eksen("zemin2")),
            Joint("J", REV, eksen("zemin"), eksen("kol")),
        ],
    )
    assert mobility(asm) == Mobility(1, 1, 0)


# ---------- K5 drive, sarkaç ----------


@pytest.mark.parametrize("theta", [30.0, 90.0, 180.0, -135.0])
def test_drive_pendulum(theta):
    """Başlangıç 10°: 0°'dan tam 180° sürmede dönme kilidi artığı durağan noktada başlar
    (Gauss–Newton adımı 0);
    bu SPEC 08 çözücüsünün itme konusu, burada sınanmaz."""
    asm = sarkac(10.0)
    onceki = snapshot(asm)
    res = drive(asm, {"J": theta}, tol=TOL_COZ)
    t = math.radians(theta)
    np.testing.assert_allclose(
        dn(res.T["kol"], (L_SARKAC, 0, 0)),
        [L_SARKAC * math.cos(t), L_SARKAC * math.sin(t), 0.0],
        atol=TOL_POS,
    )
    assert is_rigid(res.T["kol"])
    assert res.residual <= TOL_R
    assert res.dof == 0
    work = uygula(asm, res)
    assert abs(aci_farki(joint_value(work, "J"), theta)) <= TOL_ACI
    assert degismedi(asm, onceki)


def test_drive_pendulum_periodic():
    """v ve v + 360 aynı konum."""
    asm = sarkac(0.0)
    np.testing.assert_allclose(
        drive(asm, {"J": 400.0}, tol=TOL_COZ).T["kol"],
        drive(asm, {"J": 40.0}, tol=TOL_COZ).T["kol"],
        atol=TOL_POS,
    )
    work = uygula(asm, drive(asm, {"J": 400.0}, tol=TOL_COZ))
    assert joint_value(work, "J") == pytest.approx(40.0, abs=TOL_ACI)


def test_drive_already_there_zero_iterations():
    asm = sarkac(25.0)
    res = drive(asm, {"J": 25.0}, tol=TOL_COZ)
    assert res.iterations == 0
    np.testing.assert_allclose(res.T["kol"], asm.component("kol").T, atol=1e-12)


def test_drive_cylindrical():
    """CYLINDRICAL (θ, s) birlikte; None = serbest koordinat (en küçük normlu adım onu değiştirmez)."""

    def mil():
        return montaj(
            [bilesen("zemin", fixed=True), bilesen("mil", transform(rot_z(10.0), (0.0, 0.0, 1.0)))],
            [Joint("C", CYL, eksen("zemin"), eksen("mil"))],
        )

    asm = mil()
    res = drive(asm, {"C": (30.0, 5.0)}, tol=TOL_COZ)
    np.testing.assert_allclose(res.T["mil"], transform(rot_z(30.0), (0.0, 0.0, 5.0)), atol=TOL_POS)
    assert res.dof == 0

    res = drive(asm, {"C": (None, 7.0)}, tol=TOL_COZ)
    theta, s = joint_value(uygula(asm, res), "C")
    assert s == pytest.approx(7.0, abs=TOL_POS)
    assert theta == pytest.approx(10.0, abs=TOL_ACI)
    assert res.dof == 1

    res = drive(asm, {"C": (25.0, None)}, tol=TOL_COZ)
    theta, s = joint_value(uygula(asm, res), "C")
    assert theta == pytest.approx(25.0, abs=TOL_ACI)
    assert s == pytest.approx(1.0, abs=TOL_POS)


# ---------- K6 drive, krank–biyel ----------


@pytest.mark.parametrize("theta", [0.0, 45.0, 90.0, 135.0, 180.0, 270.0])
def test_drive_slider_crank(theta):
    """Başlangıç θ − 10° (aynı dal): piston x = r cos θ + √(l² − r² sin² θ)."""
    asm = krank_biyel(theta - 10.0)
    res = drive(asm, {"J_krank": theta})
    x = piston_x(theta)
    np.testing.assert_allclose(res.T["piston"][:3, 3], [x, 0.0, 0.0], atol=TOL_POS)
    assert res.residual <= TOL_R
    work = uygula(asm, res)
    assert joint_value(work, "J_kayar") == pytest.approx(x, abs=TOL_POS)
    assert abs(aci_farki(joint_value(work, "J_krank"), theta)) <= TOL_ACI
    # biyel pimleri: krank pimi A ve piston pimi (x, 0, 0)
    t = math.radians(theta)
    np.testing.assert_allclose(
        dn(res.T["biyel"], (0, 0, 0)), [R_K * math.cos(t), R_K * math.sin(t), 0], atol=TOL_POS
    )
    np.testing.assert_allclose(dn(res.T["biyel"], (L_B, 0, 0)), [x, 0.0, 0.0], atol=TOL_POS)


# ---------- K7 sweep, dört çubuk ----------


def test_sweep_four_bar_grashof():
    a, b, c, d = GRASHOF
    asm = dort_cubuk(a, b, c, d, 0.0)
    values = [5.0 * k for k in range(73)]  # 0..360
    motion = sweep(asm, "J_krank", values)
    assert isinstance(motion, Motion)
    assert motion.joint == "J_krank"
    assert motion.stopped is None
    assert motion.values == pytest.approx(values)
    assert len(motion.poses) == len(values) == len(motion.joint_values)
    K1, K2, K3 = d / a, d / c, (a * a - b * b + c * c + d * d) / (2 * a * c)
    for k, th2 in enumerate(values):
        poz, jv = motion.poses[k], motion.joint_values[k]
        assert set(poz) == {"zemin", "krank", "biyel", "kol"}
        assert set(jv) == {"J_krank", "J_A", "J_B", "J_kol"}
        assert abs(aci_farki(jv["J_krank"], th2)) <= TOL_ACI
        th4 = jv["J_kol"]
        assert abs(aci_farki(th4, theta4(a, b, c, d, th2))) <= TOL_ACI
        t2, t4 = math.radians(th2), math.radians(th4)
        assert K1 * math.cos(t4) - K2 * math.cos(t2) + K3 == pytest.approx(math.cos(t2 - t4), abs=1e-9)
        # dal değişmiyor: B açık daldaki kesişim
        np.testing.assert_allclose(
            dn(poz["biyel"], (b, 0, 0))[:2], dort_cubuk_B(a, b, c, d, th2), atol=TOL_POS
        )
        np.testing.assert_allclose(dn(poz["kol"], (c, 0, 0))[:2], dort_cubuk_B(a, b, c, d, th2), atol=TOL_POS)
        np.testing.assert_allclose(poz["zemin"], np.eye(4), atol=0)


def test_motion_apply_writes_poses():
    asm = dort_cubuk(*GRASHOF, theta2=0.0)
    motion = sweep(asm, "J_krank", [0.0, 10.0, 20.0, 30.0])
    work = copy.deepcopy(asm)
    motion.apply(work, 2)
    for name, T in motion.poses[2].items():
        np.testing.assert_allclose(work.component(name).T, T, atol=0)
    assert abs(aci_farki(joint_value(work, "J_krank"), 20.0)) <= TOL_ACI


# ---------- K8 ulaşılamaz konum ----------


def _kilit_acisi(a, b, c, d) -> float:
    """|A − B0| = b + c: a² + d² − 2ad cos θ2 = (b + c)²."""
    return math.degrees(math.acos((a * a + d * d - (b + c) ** 2) / (2 * a * d)))


def test_drive_unreachable_raises():
    asm = dort_cubuk(*GRASHOF_DISI, theta2=0.0)
    assert _kilit_acisi(*GRASHOF_DISI) < 90.0
    with pytest.raises(AssyError):
        drive(asm, {"J_krank": 90.0})


def test_sweep_unreachable_partial_stops_before_lock():
    asm = dort_cubuk(*GRASHOF_DISI, theta2=0.0)
    values = [5.0 * k for k in range(19)]  # 0..90
    motion = sweep(asm, "J_krank", values, partial=True)
    kilit = _kilit_acisi(*GRASHOF_DISI)  # ≈ 70.53°
    assert motion.stopped
    son = motion.values[-1]
    assert son < kilit
    assert kilit - son <= 5.0
    assert len(motion.poses) == len(motion.values) == len(motion.joint_values)
    assert motion.values == pytest.approx(values[: len(motion.values)])


def test_sweep_unreachable_not_partial_raises():
    asm = dort_cubuk(*GRASHOF_DISI, theta2=0.0)
    with pytest.raises(AssyError):
        sweep(asm, "J_krank", [5.0 * k for k in range(19)])


# ---------- K9 sınırlar ----------


def test_drive_beyond_limit_raises():
    asm = sarkac(0.0, limits=(-45.0, 45.0))
    with pytest.raises(AssyError):
        drive(asm, {"J": 60.0}, tol=TOL_COZ)
    with pytest.raises(AssyError):
        drive(asm, {"J": -45.5}, tol=TOL_COZ)


def test_drive_on_limit_ok():
    """Sınır kapalı aralık: 45 kabul."""
    res = drive(sarkac(0.0, limits=(-45.0, 45.0)), {"J": 45.0}, tol=TOL_COZ)
    t = math.radians(45.0)
    np.testing.assert_allclose(
        dn(res.T["kol"], (L_SARKAC, 0, 0)), [L_SARKAC * math.cos(t), L_SARKAC * math.sin(t), 0], atol=TOL_POS
    )


def test_sweep_undriven_joint_exceeds_limit_raises():
    """Krank–sarkaçta θ4 ≈ 98.2..146.0; kol eklemine (90, 130) sınırı: 130'u aşan adımda hata, mesajda ad."""
    asm = dort_cubuk(*GRASHOF, theta2=0.0, limits_kol=(90.0, 130.0))
    with pytest.raises(AssyError, match="J_kol"):
        sweep(asm, "J_krank", [5.0 * k for k in range(73)])


def test_sweep_undriven_joint_limit_partial():
    asm = dort_cubuk(*GRASHOF, theta2=0.0, limits_kol=(90.0, 130.0))
    motion = sweep(asm, "J_krank", [5.0 * k for k in range(73)], partial=True)
    assert motion.stopped
    assert 0 < len(motion.values) < 73
    assert all(90.0 - 1e-9 <= jv["J_kol"] <= 130.0 + 1e-9 for jv in motion.joint_values)
    # durulan ilk adımın kapalı form θ4'ü sınırın dışında
    ilk_durulan = 5.0 * len(motion.values)
    assert theta4(*GRASHOF, ilk_durulan) > 130.0


def _kol_ust_siniri() -> float:
    """θ4 krank açısı arttıkça azalır: θ4(0) ≈ 106.26, θ4(20) ≈ 100.07, θ4(−20) ≈ 115.29.
    Üst sınır θ4(0) ile θ4(−20)'nin ortası: başlangıç ve θ2 = 20 içeride, θ2 = −20 dışarıda."""
    a, b, c, d = GRASHOF
    return 0.5 * (theta4(a, b, c, d, 0.0) + theta4(a, b, c, d, -20.0))


def test_drive_undriven_joint_exceeds_limit_raises():
    a, b, c, d = GRASHOF
    ust = _kol_ust_siniri()
    assert theta4(a, b, c, d, 20.0) < theta4(a, b, c, d, 0.0) < ust < theta4(a, b, c, d, -20.0)
    asm = dort_cubuk(a, b, c, d, 0.0, limits_kol=(90.0, ust))
    with pytest.raises(AssyError, match="J_kol"):
        drive(asm, {"J_krank": -20.0})
    res = drive(asm, {"J_krank": 20.0})
    assert joint_value(uygula(asm, res), "J_kol") == pytest.approx(theta4(a, b, c, d, 20.0), abs=TOL_ACI)


# ---------- K10 drag ----------


def test_drag_pendulum_tip():
    """Uç (30, 40, 7)'ye: L (hx, hy, 0)/|(hx, hy)| = (6, 8, 0)."""
    asm = sarkac(0.0)
    onceki = snapshot(asm)
    res = drag(asm, "kol", (L_SARKAC, 0, 0), (30.0, 40.0, 7.0), tol=TOL_COZ)
    np.testing.assert_allclose(dn(res.T["kol"], (L_SARKAC, 0, 0)), [6.0, 8.0, 0.0], atol=TOL_POS)
    assert res.residual <= TOL_R
    assert max_eklem_artigi(uygula(asm, res)) <= TOL_R
    assert degismedi(asm, onceki)


def test_drag_prismatic_projects_onto_axis():
    """Blok x ekseninde kayar; yerel (5, 5, 5) noktası (20, 30, −4)'e.

    Erişilebilir küme (5 + s, 5, 5) → en yakın s = 15."""
    ex = (1.0, 0.0, 0.0)
    asm = montaj(
        [bilesen("zemin", fixed=True), bilesen("blok")],
        [Joint("P", PRI, eksen("zemin", z=ex), eksen("blok", z=ex))],
    )
    onceki = snapshot(asm)
    res = drag(asm, "blok", (5.0, 5.0, 5.0), (20.0, 30.0, -4.0), tol=TOL_COZ)
    np.testing.assert_allclose(dn(res.T["blok"], (5, 5, 5)), [20.0, 5.0, 5.0], atol=TOL_POS)
    work = uygula(asm, res)
    assert joint_value(work, "P") == pytest.approx(15.0, abs=TOL_POS)
    assert max_eklem_artigi(work) <= TOL_R
    assert degismedi(asm, onceki)


def test_drag_stops_at_limit():
    """(−45, 45) sınırlı sarkaç 90°'lik hedefe: aktif küme, θ = 45."""
    asm = sarkac(0.0, limits=(-45.0, 45.0))
    onceki = snapshot(asm)
    res = drag(asm, "kol", (L_SARKAC, 0, 0), (0.0, 10.0, 0.0), tol=TOL_COZ)
    work = uygula(asm, res)
    assert joint_value(work, "J") == pytest.approx(45.0, abs=TOL_ACI)
    t = math.radians(45.0)
    np.testing.assert_allclose(
        dn(res.T["kol"], (L_SARKAC, 0, 0)), [L_SARKAC * math.cos(t), L_SARKAC * math.sin(t), 0], atol=TOL_POS
    )
    assert max_eklem_artigi(work) <= TOL_R
    assert degismedi(asm, onceki)


def test_drag_fixed_joint_component_stays():
    G = transform(rot_z(15.0), (2.0, 3.0, 4.0))
    asm = montaj(
        [bilesen("zemin", fixed=True), bilesen("govde", G)],
        [
            Joint(
                "F",
                FIX,
                eksen("zemin", (2, 3, 4)),
                eksen("govde"),
                zero_a=(math.cos(math.radians(15.0)), math.sin(math.radians(15.0)), 0.0),
            )
        ],
    )
    onceki = snapshot(asm)
    res = drag(asm, "govde", (1.0, 2.0, 3.0), (50.0, 50.0, 50.0), tol=TOL_COZ)
    np.testing.assert_allclose(res.T["govde"], G, atol=TOL_POS)
    assert max_eklem_artigi(uygula(asm, res)) <= TOL_R
    assert degismedi(asm, onceki)


def test_drag_fixed_component_raises():
    with pytest.raises(AssyError):
        drag(sarkac(0.0), "zemin", (0, 0, 0), (1, 1, 1), tol=TOL_COZ)


# ---------- K11 krank–biyel drag ----------


@pytest.mark.parametrize(("baslangic", "isaret"), [(45.0, 1.0), (-45.0, -1.0)])
def test_drag_slider_crank_piston(baslangic, isaret):
    """Piston pimi (X, 0, 0)'a (l − r < X < l + r): cos θ = (X² + r² − l²)/(2 r X), başlangıç dalının kökü."""
    X = 80.0
    asm = krank_biyel(baslangic)
    res = drag(asm, "piston", (0.0, 0.0, 0.0), (X, 0.0, 0.0))
    np.testing.assert_allclose(res.T["piston"][:3, 3], [X, 0.0, 0.0], atol=TOL_POS)
    beklenen = isaret * math.degrees(math.acos((X * X + R_K * R_K - L_B * L_B) / (2 * R_K * X)))
    work = uygula(asm, res)
    assert joint_value(work, "J_krank") == pytest.approx(beklenen, abs=TOL_ACI)
    assert max_eklem_artigi(work) <= TOL_R


# ---------- K12 değişmezlik ----------

G_KEYFI = transform(rot_x(30.0) @ rot_y(-50.0) @ rot_z(20.0), (5.0, -7.0, 11.0))


def _tasi(asm: Assembly, G: np.ndarray) -> Assembly:
    out = copy.deepcopy(asm)
    for c in out.components:
        c.T = G @ c.T
    return out


def test_drive_rigid_invariance():
    asm = krank_biyel(35.0)
    asmG = _tasi(asm, G_KEYFI)
    res, resG = drive(asm, {"J_krank": 100.0}), drive(asmG, {"J_krank": 100.0})
    for c in asm.components:
        np.testing.assert_allclose(resG.T[c.name], G_KEYFI @ res.T[c.name], atol=TOL_POS)
    w, wG = uygula(asm, res), uygula(asmG, resG)
    for j in ("J_krank", "J_A", "J_B"):
        assert abs(aci_farki(joint_value(wG, j), joint_value(w, j))) <= TOL_ACI
    assert joint_value(wG, "J_kayar") == pytest.approx(joint_value(w, "J_kayar"), abs=TOL_POS)


def test_sweep_rigid_invariance():
    asm = dort_cubuk(*GRASHOF, theta2=0.0)
    asmG = _tasi(asm, G_KEYFI)
    values = [10.0 * k for k in range(7)]
    m, mG = sweep(asm, "J_krank", values), sweep(asmG, "J_krank", values)
    assert len(m.poses) == len(mG.poses) == len(values)
    for k in range(len(values)):
        for name, T in m.poses[k].items():
            np.testing.assert_allclose(mG.poses[k][name], G_KEYFI @ T, atol=TOL_POS)
        for j, v in m.joint_values[k].items():
            assert abs(aci_farki(mG.joint_values[k][j], v)) <= TOL_ACI


# ---------- K13 hatalar ----------


def _serbest_zeminli_sarkac() -> Assembly:
    asm = sarkac(0.0)
    asm.component("zemin").fixed = False
    return asm


def _kuresel_ve_sabit() -> Assembly:
    return montaj(
        [bilesen("zemin", fixed=True), bilesen("top"), bilesen("govde")],
        [Joint("S", SPH, nokta("zemin"), nokta("top")), Joint("F", FIX, eksen("zemin"), eksen("govde"))],
    )


def _silindirik() -> Assembly:
    return montaj(
        [bilesen("zemin", fixed=True), bilesen("mil")], [Joint("C", CYL, eksen("zemin"), eksen("mil"))]
    )


def _bilinmeyen_bilesenli() -> Assembly:
    asm = sarkac(0.0)
    asm.joints.append(Joint("J2", REV, eksen("kol"), eksen("yok")))
    return asm


def _yinelenen_eklem_adli() -> Assembly:
    asm = sarkac(0.0)
    asm.joints.append(Joint("J", REV, eksen("zemin"), eksen("kol")))
    return asm


def _ayni_bilesende_iki_uc() -> Assembly:
    asm = sarkac(0.0)
    asm.joints.append(Joint("J2", REV, eksen("kol"), eksen("kol", (1, 0, 0))))
    return asm


HATALAR = {
    "validate_bilinmeyen_bilesen_mobility": lambda: mobility(_bilinmeyen_bilesenli()),
    "validate_bilinmeyen_bilesen_drive": lambda: drive(_bilinmeyen_bilesenli(), {"J": 10.0}),
    "validate_yinelenen_eklem_adi": lambda: mobility(_yinelenen_eklem_adli()),
    "validate_iki_uc_ayni_bilesen": lambda: mobility(_ayni_bilesende_iki_uc()),
    "sabit_bilesen_yok_mobility": lambda: mobility(_serbest_zeminli_sarkac()),
    "sabit_bilesen_yok_drive": lambda: drive(_serbest_zeminli_sarkac(), {"J": 10.0}),
    "bilinmeyen_eklem_joint_value": lambda: joint_value(sarkac(), "yok"),
    "bilinmeyen_eklem_drive": lambda: drive(sarkac(), {"yok": 10.0}),
    "bilinmeyen_eklem_sweep": lambda: sweep(sarkac(), "yok", [0.0, 10.0]),
    "drive_kuresel": lambda: drive(_kuresel_ve_sabit(), {"S": 10.0}),
    "drive_sabit": lambda: drive(_kuresel_ve_sabit(), {"F": 10.0}),
    "drive_silindirik_tek_sayi": lambda: drive(_silindirik(), {"C": 10.0}),
    "drive_sinir_disi": lambda: drive(sarkac(0.0, limits=(-45.0, 45.0)), {"J": 46.0}),
    "surulmeyen_eklem_siniri": lambda: drive(
        dort_cubuk(*GRASHOF, limits_kol=(90.0, _kol_ust_siniri())), {"J_krank": -20.0}
    ),
    "ulasilamaz": lambda: drive(dort_cubuk(*GRASHOF_DISI), {"J_krank": 90.0}),
    "sabit_bileseni_surukleme": lambda: drag(sarkac(), "zemin", (0, 0, 0), (1, 2, 3)),
    "sweep_bos_values": lambda: sweep(sarkac(), "J", []),
}


@pytest.mark.parametrize("durum", list(HATALAR))
def test_errors(durum):
    with pytest.raises(AssyError):
        HATALAR[durum]()
