"""
SPEC 33 — Montaj kinematiği: eklemler, serbestlik, sürme, sürükleme, süpürme ve hareket boyunca çarpışma.

Bilinmeyenler SPEC 08 ile aynı: sabit olmayan bileşen başına x = [Δt, ω], dönme dünya ekseninde sol çarpım.
Eklem artıkları (yönlü, z_b = +z_a), yön satırları karakteristik uzunluk L ile ölçekli:
    FIXED        p_b − p_a ; L(z_b − z_a) ; L(x_b − x_a)          c = 6
    REVOLUTE     p_b − p_a ; L(z_b − z_a)                         c = 5
    PRISMATIC    (p_b − p_a) × z_a ; L(z_b − z_a) ; L(x_b − x_a)  c = 5
    CYLINDRICAL  (p_b − p_a) × z_a ; L(z_b − z_a)                 c = 4
    SPHERICAL    p_b − p_a                                        c = 3
Sürme kısıtları:  dönme  L(x_b − (cos v x_a + sin v y_a)),   öteleme  (p_b − p_a)·z_a − v
Grübler–Kutzbach:  M = 6 (n − 1) − Σ c_i      (tüm sabit bileşenler tek zemin gövdesi)
Gerçek serbestlik: dof = 6·n_serbest − rank(J);  redundant = dof − M
Sürükleme:  δx = N (S_p N)⁺ (h − p),  ardından Gauss–Newton ile r = 0'a dönüş.
Kaynak: Uicker–Pennock–Shigley, Theory of Machines and Mechanisms, Bölüm 1.6 ve 3.

Eklem veri modeli (Joint, JointKind, Assembly.joints) assy/model.py'dedir (arayüz A1).
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from assy.girisim import Clash, check
from assy.mates import angular_rows, jacobian, residual, rodrigues, skew
from assy.model import Assembly, AssyError, Joint, JointKind, MateKind, Node, Ref, RefKind
from assy.solver import SolveResult

if TYPE_CHECKING:
    from geometry.part import Part

JointValue = float | tuple[float | None, float | None]  # CYLINDRICAL: (θ, s), None = serbest

# Eklemin kaldırdığı serbestlik c = 6 − f
_C_EKLEM = {
    JointKind.FIXED: 6,
    JointKind.REVOLUTE: 5,
    JointKind.PRISMATIC: 5,
    JointKind.CYLINDRICAL: 4,
    JointKind.SPHERICAL: 3,
}
# Sayısal rank eşiği (SPEC 08 ile aynı): σ_i > 1e-8 · σ_max
_RANK_RTOL = 1e-8
# Geri izlemede en küçük adım: α = 2⁻¹⁰ (SPEC 08)
_MIN_HALVINGS = 10
# Durağan noktadan kaçış (SPEC 08): en fazla 3 itme, |ω| = 1e-3 rad
_MAX_KICKS = 3
_KICK = 1e-3 * np.array([1.0, 2.0, 3.0]) / np.sqrt(14.0)
# Sınır kontrolü payı
_SINIR_PAYI = 1e-9


@dataclass(frozen=True)
class Mobility:
    gruebler: int  # Kutzbach M
    dof: int  # rank ile gerçek serbestlik
    redundant: int  # dof − gruebler


@dataclass
class Motion:
    joint: str
    values: list[float]  # başarıyla çözülen adımların sürme değerleri
    poses: list[dict[str, np.ndarray]]  # adım başına bileşen adı → 4x4 T (sabitler dahil)
    joint_values: list[dict[str, JointValue]]  # adım başına koordinatı olan her eklemin değeri
    stopped: str | None = None  # partial=True ile durduysa sebep

    def apply(self, assembly: Assembly, step: int) -> None:
        """step. adımın T'lerini bileşenlere yazar."""
        for name, T in self.poses[step].items():
            assembly.component(name).T = np.array(T, dtype=float)


@dataclass(frozen=True)
class MotionClash:
    step: int
    value: float  # o adımın sürme değeri
    clash: Clash  # SPEC 09 Clash; a, b bileşen adları


# ---------- Eklem çerçeveleri ve artıklar ----------


@dataclass(frozen=True)
class _Kilit:
    """Sürme kısıtı: eklemin dönme ('aci', derece) veya öteleme ('oteleme', mm) koordinatı = v."""

    joint: Joint
    tur: str
    v: float


def _cerceve(assembly: Assembly, joint: Joint, side: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Eklem ucunun dünya çerçevesi (p, z, x)."""
    o, z, x = joint.axis_frame(side)
    ref = joint.a if side == "a" else joint.b
    T = assembly.component(ref.component).T
    R = T[:3, :3]
    return R @ o + T[:3, 3], R @ z, R @ x


def _L(assembly: Assembly) -> float:
    """Karakteristik uzunluk (SPEC 08): kısıt ve eklem referans noktalarının dünya çapı, en az 1 mm."""
    refs = [r for m in assembly.mates for r in (m.a, m.b)] + [r for j in assembly.joints for r in (j.a, j.b)]
    if not refs:
        return 1.0
    p = np.array([assembly.world(r)[0] for r in refs])
    return max(1.0, float(np.max(np.linalg.norm(p[:, None, :] - p[None, :, :], axis=2))))


_ANAHTARLAR = ("pa", "pb", "za", "zb", "xa", "xb")


def _eklem_terimleri(assembly: Assembly, joint: Joint, L: float) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Artık r ve dünya büyüklüklerine göre türevler (∂r/∂p_a, ∂r/∂p_b, ∂r/∂z_a, ...)."""
    pa, za, xa = _cerceve(assembly, joint, "a")
    pb, zb, xb = _cerceve(assembly, joint, "b")
    I3 = np.eye(3)
    bloklar: list[tuple[np.ndarray, dict[str, np.ndarray]]] = []

    def konum():  # p_b − p_a
        bloklar.append((pb - pa, {"pa": -I3, "pb": I3}))

    def eksen_ustu():  # (p_b − p_a) × z_a = −[z_a]× v  ;  ∂/∂z_a = [v]×
        v = pb - pa
        bloklar.append((np.cross(v, za), {"pa": skew(za), "pb": -skew(za), "za": skew(v)}))

    def yon(k: str, a: np.ndarray, b: np.ndarray):  # L(b − a)
        bloklar.append((L * (b - a), {k + "a": -L * I3, k + "b": L * I3}))

    kind = joint.kind
    if kind in (JointKind.FIXED, JointKind.REVOLUTE, JointKind.SPHERICAL):
        konum()
    else:
        eksen_ustu()
    if kind is not JointKind.SPHERICAL:
        yon("z", za, zb)
    if kind in (JointKind.FIXED, JointKind.PRISMATIC):
        yon("x", xa, xb)
    return _birlestir(bloklar)


def _kilit_terimleri(assembly: Assembly, kilit: _Kilit, L: float) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Sürme kısıtının artığı ve türevleri (bkz. modül açıklaması)."""
    pa, za, xa = _cerceve(assembly, kilit.joint, "a")
    pb, zb, xb = _cerceve(assembly, kilit.joint, "b")
    if kilit.tur == "aci":
        t = math.radians(kilit.v)
        c, s = math.cos(t), math.sin(t)
        ya = np.cross(za, xa)
        r = L * (xb - (c * xa + s * ya))
        # y_a = [z_a]× x_a = −[x_a]× z_a
        G = {"xb": L * np.eye(3), "xa": -L * (c * np.eye(3) + s * skew(za)), "za": L * s * skew(xa)}
        return _birlestir([(r, G)])
    v = pb - pa
    r = np.array([v @ za - kilit.v])
    G = {"pa": -za[None, :], "pb": za[None, :], "za": v[None, :]}
    return _birlestir([(r, G)])


def _birlestir(bloklar) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Satır bloklarını alt alta: r ve her dünya büyüklüğü için türev (eksik anahtar = 0)."""
    r = np.concatenate([b[0] for b in bloklar])
    G = {}
    for k in _ANAHTARLAR:
        G[k] = np.vstack([b[1].get(k, np.zeros((len(b[0]), 3))) for b in bloklar])
    return r, G


def _jacobian_terimden(
    assembly: Assembly, joint: Joint, G: dict[str, np.ndarray], m: int, unknowns: list[str]
) -> np.ndarray:
    """Dünya türevlerinden [Δt, ω] sütunlarına zincir kuralı: δp = Δt − [R o]× ω, δd = −[d]× ω."""
    J = np.zeros((m, 6 * len(unknowns)))
    for side, ref in (("a", joint.a), ("b", joint.b)):
        if ref.component not in unknowns:
            continue  # sabit bileşen: sütunu yok
        i = unknowns.index(ref.component)
        T = assembly.component(ref.component).T
        R = T[:3, :3]
        o, z, x = joint.axis_frame(side)
        Ro, d_z, d_x = R @ o, R @ z, R @ x
        gp, gz, gx = G["p" + side], G["z" + side], G["x" + side]
        J[:, 6 * i : 6 * i + 3] += gp
        J[:, 6 * i + 3 : 6 * i + 6] += -gp @ skew(Ro) - gz @ skew(d_z) - gx @ skew(d_x)
    return J


def joint_residual(assembly: Assembly, joint: Joint) -> np.ndarray:
    """Eklemin ölçekli artığı (SPEC 33 Teori tablosu)."""
    return _eklem_terimleri(assembly, joint, _L(assembly))[0]


def joint_jacobian(assembly: Assembly, joint: Joint, unknowns: list[str]) -> np.ndarray:
    """Eklem artığının Jacobian'ı; sütun düzeni SPEC 08 jacobian ile aynı ([Δt, ω] / bilinmeyen)."""
    r, G = _eklem_terimleri(assembly, joint, _L(assembly))
    return _jacobian_terimden(assembly, joint, G, len(r), unknowns)


def _eklem(assembly: Assembly, joint: str | Joint) -> Joint:
    if isinstance(joint, Joint):
        return joint
    for j in assembly.joints:
        if j.name == joint:
            return j
    raise AssyError(f"Bilinmeyen eklem: {joint!r}")


def _aci(assembly: Assembly, joint: Joint) -> float:
    """θ = atan2((x_a × x_b)·z_a, x_a·x_b), (−180, 180]."""
    _, za, xa = _cerceve(assembly, joint, "a")
    _, _, xb = _cerceve(assembly, joint, "b")
    v = math.degrees(math.atan2(float(np.cross(xa, xb) @ za), float(xa @ xb)))
    return v + 360.0 if v <= -180.0 else v


def _oteleme(assembly: Assembly, joint: Joint) -> float:
    """s = (p_b − p_a)·z_a."""
    pa, za, _ = _cerceve(assembly, joint, "a")
    pb, _, _ = _cerceve(assembly, joint, "b")
    return float((pb - pa) @ za)


def joint_value(assembly: Assembly, joint: str | Joint) -> JointValue:
    """REVOLUTE θ (derece, (−180, 180]), PRISMATIC s (mm), CYLINDRICAL (θ, s).

    SPHERICAL / FIXED → AssyError.
    """
    j = _eklem(assembly, joint)
    if j.kind is JointKind.REVOLUTE:
        return _aci(assembly, j)
    if j.kind is JointKind.PRISMATIC:
        return _oteleme(assembly, j)
    if j.kind is JointKind.CYLINDRICAL:
        return (_aci(assembly, j), _oteleme(assembly, j))
    raise AssyError(f"Eklem '{j.name}' ({j.kind.name}): koordinatı yok")


def _koordinatlar(assembly: Assembly) -> dict[str, JointValue]:
    return {
        j.name: joint_value(assembly, j)
        for j in assembly.joints
        if j.kind in (JointKind.REVOLUTE, JointKind.PRISMATIC, JointKind.CYLINDRICAL)
    }


# ---------- Sistem: mate + eklem + kilit satırları ----------


@dataclass
class _Sistem:
    """Bir montajın tüm kısıt satırları; L çözüm boyunca sabit (başlangıç konumundan)."""

    asm: Assembly
    L: float
    kilitler: list[_Kilit]

    @property
    def unknowns(self) -> list[str]:
        return [c.name for c in self.asm.components if not c.fixed]

    def _mate_olcek(self, m) -> np.ndarray:
        return np.where(angular_rows(self.asm, m), self.L, 1.0)

    def r(self) -> np.ndarray:
        parcalar = [self._mate_olcek(m) * residual(self.asm, m) for m in self.asm.mates]
        parcalar += [_eklem_terimleri(self.asm, j, self.L)[0] for j in self.asm.joints]
        parcalar += [_kilit_terimleri(self.asm, k, self.L)[0] for k in self.kilitler]
        return np.concatenate(parcalar) if parcalar else np.zeros(0)

    def J(self) -> np.ndarray:
        u = self.unknowns
        parcalar = [self._mate_olcek(m)[:, None] * jacobian(self.asm, m, u) for m in self.asm.mates]
        for j in self.asm.joints:
            r, G = _eklem_terimleri(self.asm, j, self.L)
            parcalar.append(_jacobian_terimden(self.asm, j, G, len(r), u))
        for k in self.kilitler:
            r, G = _kilit_terimleri(self.asm, k, self.L)
            parcalar.append(_jacobian_terimden(self.asm, k.joint, G, len(r), u))
        return np.vstack(parcalar) if parcalar else np.zeros((0, 6 * len(u)))

    def dof(self) -> int:
        return 6 * len(self.unknowns) - _rank(self.J())

    def T(self) -> dict[str, np.ndarray]:
        return {c.name: c.T.copy() for c in self.asm.components}

    def ata(self, T: dict[str, np.ndarray]) -> None:
        for name in self.unknowns:
            self.asm.component(name).T = T[name].copy()


def _rank(J: np.ndarray) -> int:
    if J.size == 0:
        return 0
    sigma = np.linalg.svd(J, compute_uv=False)
    if float(sigma.max()) == 0.0:
        return 0
    return int(np.sum(sigma > _RANK_RTOL * float(sigma.max())))


def _nearest_rotation(R: np.ndarray) -> np.ndarray:
    U, _, Vt = np.linalg.svd(R)
    Q = U @ Vt
    if np.linalg.det(Q) < 0:
        U[:, -1] *= -1
        Q = U @ Vt
    return Q


def _adim(sis: _Sistem, T0: dict[str, np.ndarray], dx: np.ndarray) -> None:
    """Bilinmeyenleri T0 + dx konumuna getirir: R = exp([ω]×) R0, t = t0 + Δt."""
    for i, name in enumerate(sis.unknowns):
        T = T0[name].copy()
        T[:3, :3] = rodrigues(dx[6 * i + 3 : 6 * i + 6]) @ T[:3, :3]
        T[:3, 3] = T[:3, 3] + dx[6 * i : 6 * i + 3]
        sis.asm.component(name).T = T


def _gauss_newton(sis: _Sistem, tol: float, max_iter: int) -> tuple[int, float]:
    """SPEC 08 Gauss–Newton: en küçük normlu adım, geri izleme, durağan noktadan kaçış.

    Yakınsamazsa AssyError.
    """
    u = sis.unknowns
    r = sis.r()
    iterations, kicks = 0, 0
    while not (r.size == 0 or float(np.max(np.abs(r))) <= tol):
        if iterations >= max_iter:
            raise AssyError(
                f"Ulaşılamaz konum: {max_iter} iterasyonda yakınsamadı (max|r| = {np.max(np.abs(r)):.3e})"
            )
        J = sis.J()
        if J.shape[1] == 0:
            raise AssyError(
                "Ulaşılamaz konum: sabit bileşenler arasındaki kısıt sağlanmıyor "
                f"(max|r| = {np.max(np.abs(r)):.3e})"
            )
        dx = np.linalg.lstsq(J, -r, rcond=None)[0]
        T0 = sis.T()
        norm0 = float(np.linalg.norm(r))
        kabul = False
        for k in range(_MIN_HALVINGS + 1):
            _adim(sis, T0, 0.5**k * dx)
            if float(np.linalg.norm(sis.r())) < norm0:
                kabul = True
                break
        if not kabul:
            g = np.linalg.norm(J.T @ r)
            if kicks < _MAX_KICKS and g <= 1e-9 * np.linalg.norm(J) * norm0:
                _adim(sis, T0, np.tile(np.concatenate([np.zeros(3), _KICK]), len(u)))
                kicks += 1
                r = sis.r()
                iterations += 1
                continue
            sis.ata(T0)
            raise AssyError(f"Ulaşılamaz konum: artık azalmıyor (max|r| = {np.max(np.abs(r)):.3e})")
        for name in u:
            T = sis.asm.component(name).T
            T[:3, :3] = _nearest_rotation(T[:3, :3])
        r = sis.r()
        iterations += 1
    return iterations, float(np.max(np.abs(r))) if r.size else 0.0


def _hazirla(assembly: Assembly) -> Assembly:
    """validate + sabit bileşen kontrolü + çalışma kopyası (girdi değişmez)."""
    assembly.validate()
    if not any(c.fixed for c in assembly.components):
        raise AssyError("Montajda sabit bileşen yok: montaj dünyaya bağlı değil")
    return copy.deepcopy(assembly)


def _sinir_ihlali(assembly: Assembly) -> tuple[float, Joint, str, float] | None:
    """Sınırı en çok aşan eklem: (aşım, eklem, tür, aşılan sınır) ya da None."""
    en_kotu = None
    for j in assembly.joints:
        if j.limits is None:
            continue
        if j.kind is JointKind.CYLINDRICAL:
            adaylar = [
                ("aci", j.limits[0], _aci(assembly, j)),
                ("oteleme", j.limits[1], _oteleme(assembly, j)),
            ]
        elif j.kind is JointKind.REVOLUTE:
            adaylar = [("aci", j.limits, _aci(assembly, j))]
        else:
            adaylar = [("oteleme", j.limits, _oteleme(assembly, j))]
        for tur, sinir, q in adaylar:
            if sinir is None:
                continue
            alt, ust = sinir
            asim, hedef = (alt - q, alt) if q < alt else (q - ust, ust)
            if asim > _SINIR_PAYI and (en_kotu is None or asim > en_kotu[0]):
                en_kotu = (asim, j, tur, hedef)
    return en_kotu


def _sinir_kontrol(assembly: Assembly) -> None:
    ihlal = _sinir_ihlali(assembly)
    if ihlal is not None:
        asim, j, tur, hedef = ihlal
        raise AssyError(f"Eklem '{j.name}' sınırı aşıldı ({tur}, sınır {hedef}, aşım {asim:.3e})")


def _sarili(v: float) -> float:
    """Açıyı (−180, 180]'e sarar."""
    w = math.fmod(v, 360.0)
    if w <= -180.0:
        w += 360.0
    elif w > 180.0:
        w -= 360.0
    return w


def _icinde(v: float, sinir, ad: str) -> None:
    if sinir is not None and not (sinir[0] - _SINIR_PAYI <= v <= sinir[1] + _SINIR_PAYI):
        raise AssyError(f"Eklem '{ad}': sürme değeri {v} sınır {tuple(sinir)} dışında")


def _kilitler(assembly: Assembly, values: Mapping[str, JointValue]) -> list[_Kilit]:
    out = []
    for ad, deger in values.items():
        j = _eklem(assembly, ad)
        if j.kind in (JointKind.SPHERICAL, JointKind.FIXED):
            raise AssyError(f"Eklem '{j.name}' ({j.kind.name}) sürülemez")
        if j.kind is JointKind.CYLINDRICAL:
            if not isinstance(deger, (tuple, list)) or len(deger) != 2:
                raise AssyError(f"Silindirik eklem '{j.name}' için (θ, s) verilmeli ({deger!r})")
            sinirlar = j.limits or (None, None)
            parcalar = [("aci", deger[0], sinirlar[0]), ("oteleme", deger[1], sinirlar[1])]
        else:
            if isinstance(deger, (tuple, list)) or deger is None:
                raise AssyError(f"Eklem '{j.name}' için tek sayı verilmeli ({deger!r})")
            tur = "aci" if j.kind is JointKind.REVOLUTE else "oteleme"
            parcalar = [(tur, deger, j.limits)]
        for tur, v, sinir in parcalar:
            if v is None:
                continue
            v = float(v)
            if not math.isfinite(v):
                raise AssyError(f"Eklem '{j.name}': sürme değeri sonlu olmalı ({v})")
            _icinde(_sarili(v) if tur == "aci" else v, sinir, j.name)
            out.append(_Kilit(j, tur, v))
    return out


def _sonuc(sis: _Sistem, iterations: int, res: float) -> SolveResult:
    return SolveResult(T=sis.T(), iterations=iterations, residual=res, dof=sis.dof())


# ---------- Serbestlik ----------


def _mate_c(m) -> int:
    """SPEC 08 tablosundaki 'kaldırdığı serbestlik'."""
    cift = frozenset((m.a.kind, m.b.kind))
    P, A, N = RefKind.PLANE, RefKind.AXIS, RefKind.POINT
    if m.kind is MateKind.ANGLE:
        return 2 if m.value in (0.0, 180.0) else 1
    tablo = {
        MateKind.COINCIDENT: {
            frozenset((P,)): 3,
            frozenset((N,)): 3,
            frozenset((N, P)): 1,
            frozenset((N, A)): 2,
            frozenset((A,)): 4,
        },
        MateKind.CONCENTRIC: {frozenset((A,)): 4},
        MateKind.DISTANCE: {frozenset((P,)): 3, frozenset((N, P)): 1, frozenset((N,)): 1, frozenset((A,)): 3},
    }
    c = tablo.get(m.kind, {}).get(cift)
    if c is None:
        raise AssyError(f"Desteklenmeyen kısıt: {m.kind.name} {m.a.kind.name}–{m.b.kind.name}")
    return c


def mobility(assembly: Assembly) -> Mobility:
    """Grübler–Kutzbach M, rank ile dof ve fark (mevcut konumda)."""
    work = _hazirla(assembly)
    sabit = {c.name for c in work.components if c.fixed}

    def zeminde(a: Ref, b: Ref) -> bool:
        return a.component in sabit and b.component in sabit

    M = 6 * (len(work.components) - len(sabit))
    M -= sum(_C_EKLEM[j.kind] for j in work.joints if not zeminde(j.a, j.b))
    M -= sum(_mate_c(m) for m in work.mates if not zeminde(m.a, m.b))
    dof = _Sistem(work, _L(work), []).dof()
    return Mobility(gruebler=M, dof=dof, redundant=dof - M)


# ---------- Sürme ----------


def _surme(
    work: Assembly, kilitler: list[_Kilit], L: float, tol: float, max_iter: int
) -> tuple[_Sistem, int, float]:
    sis = _Sistem(work, L, kilitler)
    it, res = _gauss_newton(sis, tol, max_iter)
    _sinir_kontrol(work)
    return sis, it, res


def drive(
    assembly: Assembly, values: Mapping[str, JointValue], tol: float = 1e-10, max_iter: int = 50
) -> SolveResult:
    """Eklem koordinatlarını değerlere kilitleyip mevcut konumdan çözer; girdiyi değiştirmez."""
    work = _hazirla(assembly)
    kilitler = _kilitler(work, values)
    sis, it, res = _surme(work, kilitler, _L(work), tol, max_iter)
    return _sonuc(sis, it, res)


# ---------- Sürükleme ----------


def _nokta(asm: Assembly, component: str, p0: np.ndarray) -> np.ndarray:
    T = asm.component(component).T
    return T[:3, :3] @ p0 + T[:3, 3]


def _surukle(
    work: Assembly, kilitler: list[_Kilit], L: float, component: str, p0, h, tol: float, max_iter: int
) -> tuple[_Sistem, int, float]:
    """Kısıtlar sağlanırken noktayı hedefe yerel olarak en yakın konuma taşır (geri izlemeli)."""
    sis = _Sistem(work, L, kilitler)
    _, res = _gauss_newton(sis, tol, max_iter)
    u = sis.unknowns
    i = u.index(component)
    iterations = 0
    for iterations in range(1, max_iter + 1):  # noqa: B007 (son değer sonuçta döner)
        J = sis.J()
        n = 6 * len(u)
        if J.size:
            _, sigma, Vt = np.linalg.svd(J)
            rank = int(np.sum(sigma > _RANK_RTOL * sigma.max())) if sigma.size and sigma.max() > 0 else 0
            N = Vt[rank:].T
        else:
            N = np.eye(n)
        if N.shape[1] == 0:
            break
        R = work.component(component).T[:3, :3]
        S = np.zeros((3, n))
        S[:, 6 * i : 6 * i + 3] = np.eye(3)
        S[:, 6 * i + 3 : 6 * i + 6] = -skew(R @ p0)
        p = _nokta(work, component, p0)
        e = h - p
        dx = N @ np.linalg.lstsq(S @ N, e, rcond=None)[0]
        if float(np.linalg.norm(S @ dx)) <= 1e-12 * L:
            break
        T0 = sis.T()
        d0 = float(np.linalg.norm(e))
        kabul = False
        for k in range(_MIN_HALVINGS + 1):
            _adim(sis, T0, 0.5**k * dx)
            try:
                _, res = _gauss_newton(sis, tol, max_iter)
            except AssyError:
                continue
            if float(np.linalg.norm(h - _nokta(work, component, p0))) < d0:
                kabul = True
                break
        if not kabul:
            sis.ata(T0)
            _, res = _gauss_newton(sis, tol, max_iter)
            break
        if float(np.linalg.norm(S @ dx)) * 0.5**k <= 1e-12 * L:
            break
    return sis, iterations, res


def drag(
    assembly: Assembly,
    component: str,
    point: Sequence[float],
    target: Sequence[float],
    tol: float = 1e-10,
    max_iter: int = 100,
) -> SolveResult:
    """Bileşenin yerel noktasını dünya hedefine kısıtları bozmadan sürükler; sınırda durur."""
    work0 = _hazirla(assembly)
    if work0.component(component).fixed:
        raise AssyError(f"Sabit bileşen sürüklenemez: '{component}'")
    p0 = np.asarray(point, dtype=float)
    h = np.asarray(target, dtype=float)
    if p0.shape != (3,) or h.shape != (3,) or not (np.all(np.isfinite(p0)) and np.all(np.isfinite(h))):
        raise AssyError("Sürükleme noktası ve hedefi sonlu (3,) olmalı")
    L = _L(work0)
    kilitler: list[_Kilit] = []
    limitli = sum(1 for j in work0.joints if j.limits is not None) * 2
    for _ in range(limitli + 1):
        work = copy.deepcopy(work0)
        sis, it, res = _surukle(work, kilitler, L, component, p0, h, tol, max_iter)
        ihlal = _sinir_ihlali(work)
        if ihlal is None:
            return _sonuc(sis, it, res)
        _, j, tur, hedef = ihlal  # aktif küme: en çok aşan eklemi sınıra kilitle, baştan çöz
        kilitler.append(_Kilit(j, tur, hedef))
    _sinir_kontrol(work)
    return _sonuc(sis, it, res)


# ---------- Süpürme ----------


def sweep(
    assembly: Assembly,
    joint: str,
    values: Sequence[float],
    tol: float = 1e-10,
    max_iter: int = 50,
    partial: bool = False,
) -> Motion:
    """Eklemi değer dizisi boyunca sürer; her adım bir öncekinin çözümünden başlar."""
    values = [float(v) for v in values]
    if not values:
        raise AssyError("sweep: değer listesi boş")
    work = _hazirla(assembly)
    j = _eklem(work, joint)
    L = _L(work)
    motion = Motion(joint=j.name, values=[], poses=[], joint_values=[])
    for _, v in _adimlar(work, j, values, L, tol, max_iter, partial, motion):
        motion.values.append(v)
        motion.poses.append({c.name: c.T.copy() for c in work.components})
        motion.joint_values.append(_koordinatlar(work))
    return motion


def _surme_degeri(j: Joint, v: float) -> JointValue:
    return (v, None) if j.kind is JointKind.CYLINDRICAL else v


def _adimlar(work, j, values, L, tol, max_iter, partial, motion=None):
    """Her değere sırayla sürer ve (indis, değer) verir; work her adımda çözülmüş konumdadır."""
    for k, v in enumerate(values):
        T0 = {c.name: c.T.copy() for c in work.components}
        try:
            kilitler = _kilitler(work, {j.name: _surme_degeri(j, v)})
            _surme(work, kilitler, L, tol, max_iter)
        except AssyError as hata:
            if not partial:
                raise AssyError(f"sweep adım {k} (değer {v}): {hata}") from hata
            for c in work.components:
                c.T = T0[c.name]
            if motion is not None:
                motion.stopped = f"adım {k} (değer {v}): {hata}"
            return
        yield k, v


# ---------- Hareket boyunca çarpışma ----------


def _agac(asm: Assembly) -> Node:
    """Düz SPEC 07 ağacı: kök 'montaj', yaprak adı = bileşen adı."""
    return Node("montaj", children=[Node(c.name, T=c.T.copy(), part=c.part) for c in asm.components])


def _atlanacak(asm: Assembly, ignore_joined: bool, ignore) -> list[tuple[str, str]]:
    out = [tuple(c) for c in ignore]
    if ignore_joined:
        out += [(j.a.component, j.b.component) for j in asm.joints]
    return out


def _carpismalar(asm: Assembly, parts, clearance: float, atla) -> list[Clash]:
    return check(_agac(asm), parts, clearance=clearance, ignore=atla)


def _clearance(clearance: float) -> float:
    if not (math.isfinite(clearance) and clearance >= 0):
        raise AssyError(f"clearance sonlu ve ≥ 0 olmalı ({clearance})")
    return float(clearance)


def sweep_clashes(
    assembly: Assembly,
    parts: Mapping[str, Part],
    motion: Motion,
    clearance: float = 0.0,
    ignore_joined: bool = True,
    ignore: Iterable[tuple[str, str]] = (),
) -> list[MotionClash]:
    """Hareketin her adımında SPEC 09 girişim kontrolü; yollar bileşen adlarıdır."""
    clearance = _clearance(clearance)
    work = copy.deepcopy(assembly)
    atla = _atlanacak(work, ignore_joined, ignore)
    out = []
    for k, v in enumerate(motion.values):
        motion.apply(work, k)
        out += [MotionClash(step=k, value=v, clash=c) for c in _carpismalar(work, parts, clearance, atla)]
    return out


def first_contact(
    assembly: Assembly,
    parts: Mapping[str, Part],
    joint: str,
    start: float,
    end: float,
    steps: int = 50,
    tol: float = 1e-3,
    clearance: float = 0.0,
    ignore_joined: bool = True,
    ignore: Iterable[tuple[str, str]] = (),
) -> float | None:
    """Örnekleme + ikiye bölme ile ilk temas değeri (serbest taraf); çarpışma yoksa None."""
    if steps < 1:
        raise AssyError(f"first_contact: steps ≥ 1 olmalı ({steps})")
    if not (math.isfinite(tol) and tol > 0):
        raise AssyError(f"first_contact: tol > 0 olmalı ({tol})")
    if start == end:
        raise AssyError("first_contact: start ve end farklı olmalı")
    clearance = _clearance(clearance)
    work = _hazirla(assembly)
    j = _eklem(work, joint)
    L = _L(work)
    atla = _atlanacak(work, ignore_joined, ignore)
    values = [float(v) for v in np.linspace(start, end, steps + 1)]

    def carpiyor() -> bool:
        return bool(_carpismalar(work, parts, clearance, atla))

    onceki: tuple[float, dict[str, np.ndarray]] | None = None
    for k, v in _adimlar(work, j, values, L, 1e-10, 50, partial=True):
        if carpiyor():
            if k == 0:
                return start
            lo, T_lo = onceki
            hi = v
            while abs(hi - lo) >= tol:
                orta = 0.5 * (lo + hi)
                for c in work.components:
                    c.T = T_lo[c.name].copy()
                _surme(work, _kilitler(work, {j.name: _surme_degeri(j, orta)}), L, 1e-10, 50)
                if carpiyor():
                    hi = orta
                else:
                    lo, T_lo = orta, {c.name: c.T.copy() for c in work.components}
            return lo
        onceki = (v, {c.name: c.T.copy() for c in work.components})
    return None
