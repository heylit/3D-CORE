"""
SPEC 08 — Montaj kısıtlarının artıkları ve Jacobian'ları.

Her kısıt bir artık vektörü r üretir; kısıt sağlanınca r = 0 (tablo: specs/08-kisitlar.md).
Bilinmeyenler, sabit olmayan her bileşen için x = [Δt (3), ω (3)]:
    R' = exp([ω]×) R,   t' = t + Δt      (dünya ekseninde küçük dönme, sol çarpım)
Türevler:  δp = Δt − [R p0]× ω,   δd = −[d]× ω
Kaynak: Murray–Li–Sastry, A Mathematical Introduction to Robotic Manipulation, Bölüm 2.

Uygulama: her artık önce referansların dünya değerleri (p_a, d_a, p_b, d_b) cinsinden yazılır ve
bu dört büyüklüğe göre kısmi türevleri (her biri m×3) birlikte hesaplanır. Jacobian sonra zincir kuralıyla
bileşen bilinmeyenlerine taşınır:
    ∂r/∂Δt = ∂r/∂p,     ∂r/∂ω = −∂r/∂p [R p0]× − ∂r/∂d [d]×
"""

from __future__ import annotations

import math

import numpy as np

from assy.model import Assembly, AssyError, Mate, MateKind, RefKind

# Normlu artıklarda (|v| − D) |v| bu değerin altındaysa yön tanımsız: türev sıfır alınır
_EPS_NORM = 1e-12

_PLANE, _AXIS, _POINT = RefKind.PLANE, RefKind.AXIS, RefKind.POINT


def skew(v) -> np.ndarray:
    """[v]×: skew(a) @ b == np.cross(a, b)."""
    x, y, z = np.asarray(v, dtype=float)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def rodrigues(omega) -> np.ndarray:
    """exp([ω]×) = I + sin θ [k]× + (1 − cos θ) [k]×²,  θ = |ω|,  k = ω/θ. |ω| < 1e-12 → I."""
    omega = np.asarray(omega, dtype=float)
    theta = float(np.linalg.norm(omega))
    if theta < 1e-12:
        return np.eye(3)
    K = skew(omega / theta)
    return np.eye(3) + math.sin(theta) * K + (1.0 - math.cos(theta)) * (K @ K)


# ---------------------------------------------------------------------------
# Artık + kısmi türevler (dünya büyüklükleri cinsinden)
# ---------------------------------------------------------------------------
# Her yardımcı (r, G) döndürür; G = {"pa", "da", "pb", "db"} -> ∂r/∂(o büyüklük), boyut (m, 3).


def _zeros(m: int) -> dict[str, np.ndarray]:
    return {k: np.zeros((m, 3)) for k in ("pa", "da", "pb", "db")}


def _plane_plane(pa, na, pb, nb, D: float):
    """n_a + n_b (3) ; (p_b − p_a)·n_a − D (1). Normaller zıt (yüz yüze)."""
    v = pb - pa
    r = np.concatenate([na + nb, [v @ na - D]])
    G = _zeros(4)
    G["da"][:3] = np.eye(3)
    G["db"][:3] = np.eye(3)
    G["pb"][3] = na
    G["pa"][3] = -na
    G["da"][3] = v
    return r, G


def _point_point(pa, pb):
    """p_b − p_a (3)."""
    G = _zeros(3)
    G["pb"][:] = np.eye(3)
    G["pa"][:] = -np.eye(3)
    return pb - pa, G


def _point_plane(p, q, n, D: float):
    """(p − q)·n − D (1). Türevler ("p", "q", "n") anahtarlarıyla döner."""
    v = p - q
    r = np.array([v @ n - D])
    return r, {"p": n[None, :], "q": -n[None, :], "n": v[None, :]}


def _point_axis(p, q, d):
    """(p − q) × d (3).  (p − q) × d = −[d]× (p − q) = [p − q]× d."""
    v = p - q
    return np.cross(v, d), {"p": -skew(d), "q": skew(d), "n": skew(v)}


def _concentric(pa, da, pb, db):
    """d_a × d_b (3) ; (p_b − p_a) × d_a (3)."""
    v = pb - pa
    r = np.concatenate([np.cross(da, db), np.cross(v, da)])
    G = _zeros(6)
    # d_a × d_b = −[d_b]× d_a = [d_a]× d_b
    G["da"][:3] = -skew(db)
    G["db"][:3] = skew(da)
    # (p_b − p_a) × d_a = −[d_a]× (p_b − p_a) = [v]× d_a
    G["pb"][3:] = -skew(da)
    G["pa"][3:] = skew(da)
    G["da"][3:] = skew(v)
    return r, G


def _unit_or_zero(w: np.ndarray) -> np.ndarray:
    """w / |w|; |w| ≈ 0 iken |w|'nin türevi tanımsız, sıfır döner (sıfıra bölme yok)."""
    n = float(np.linalg.norm(w))
    return w / n if n > _EPS_NORM else np.zeros(3)


def _distance_point_point(pa, pb, D: float):
    """|p_b − p_a| − D (1)."""
    v = pb - pa
    e = _unit_or_zero(v)
    G = _zeros(1)
    G["pb"][0] = e
    G["pa"][0] = -e
    return np.array([np.linalg.norm(v) - D]), G


def _distance_axis_axis(pa, da, pb, db, D: float):
    """d_a × d_b (3) ; |(p_b − p_a) × d_a| − D (1)."""
    v = pb - pa
    w = np.cross(v, da)
    e = _unit_or_zero(w)
    r = np.concatenate([np.cross(da, db), [np.linalg.norm(w) - D]])
    G = _zeros(4)
    G["da"][:3] = -skew(db)
    G["db"][:3] = skew(da)
    # ∂|w| = eᵀ ∂w,  ∂w/∂p_b = −[d_a]×,  ∂w/∂p_a = [d_a]×,  ∂w/∂d_a = [v]×
    G["pb"][3] = e @ -skew(da)
    G["pa"][3] = e @ skew(da)
    G["da"][3] = e @ skew(v)
    return r, G


def _angle(da, db, theta_deg: float):
    """θ = 0: d_a − d_b (3); θ = 180: d_a + d_b (3); arada: d_a·d_b − cos θ (1)."""
    if abs(theta_deg) < 1e-12:
        G = _zeros(3)
        G["da"][:] = np.eye(3)
        G["db"][:] = -np.eye(3)
        return da - db, G
    if abs(theta_deg - 180.0) < 1e-12:
        G = _zeros(3)
        G["da"][:] = np.eye(3)
        G["db"][:] = np.eye(3)
        return da + db, G
    G = _zeros(1)
    G["da"][0] = db
    G["db"][0] = da
    return np.array([da @ db - math.cos(math.radians(theta_deg))]), G


def _mixed(fn, a_is_point: bool, pa, da, pb, db, *args):
    """POINT–PLANE / POINT–AXIS her iki sıra: p = POINT origin'i, q, n = diğer referans."""
    if a_is_point:
        r, g = fn(pa, pb, db, *args)
        G = _zeros(len(r))
        G["pa"], G["pb"], G["db"] = g["p"], g["q"], g["n"]
    else:
        r, g = fn(pb, pa, da, *args)
        G = _zeros(len(r))
        G["pb"], G["pa"], G["da"] = g["p"], g["q"], g["n"]
    return r, G


def _unsupported(mate: Mate) -> AssyError:
    return AssyError(
        f"Desteklenmeyen kısıt: {mate.kind.name} {mate.a.kind.name}–{mate.b.kind.name} "
        f"('{mate.a.component}' – '{mate.b.component}')"
    )


def _terms(assembly: Assembly, mate: Mate) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Kısıtın artığı ve dünya büyüklüklerine göre kısmi türevleri.

    flip: yönlü referansın (b; b NOKTA ise a) dünya yönü d yerine d' = −d kullanılır. Zincir kuralı:
    ∂r/∂d = −∂r/∂d', yani o anahtarın türevi işaret değiştirir.
    """
    pa, da = assembly.world(mate.a)
    pb, db = assembly.world(mate.b)
    if not mate.flip:
        return _terms_world(mate, pa, da, pb, db)
    if mate.b.kind is _POINT:
        r, G = _terms_world(mate, pa, -da, pb, db)
        G["da"] = -G["da"]
    else:
        r, G = _terms_world(mate, pa, da, pb, -db)
        G["db"] = -G["db"]
    return r, G


def _terms_world(mate: Mate, pa, da, pb, db) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Dünya büyüklükleri verilmiş kısıtın artığı ve kısmi türevleri (tablo: specs/08-kisitlar.md)."""
    ka, kb = mate.a.kind, mate.b.kind
    pair = {ka, kb}
    D = float(mate.value)
    kind = mate.kind

    if kind is MateKind.COINCIDENT:
        if ka is _PLANE and kb is _PLANE:
            return _plane_plane(pa, da, pb, db, 0.0)
        if ka is _POINT and kb is _POINT:
            return _point_point(pa, pb)
        if pair == {_POINT, _PLANE}:
            return _mixed(_point_plane, ka is _POINT, pa, da, pb, db, 0.0)
        if pair == {_POINT, _AXIS}:
            return _mixed(_point_axis, ka is _POINT, pa, da, pb, db)
        if ka is _AXIS and kb is _AXIS:
            return _concentric(pa, da, pb, db)

    elif kind is MateKind.CONCENTRIC:
        if ka is _AXIS and kb is _AXIS:
            return _concentric(pa, da, pb, db)

    elif kind is MateKind.DISTANCE:
        if ka is _PLANE and kb is _PLANE:
            return _plane_plane(pa, da, pb, db, D)
        if pair == {_POINT, _PLANE}:
            return _mixed(_point_plane, ka is _POINT, pa, da, pb, db, D)
        if (ka is _POINT and kb is _POINT) or (ka is _AXIS and kb is _AXIS):
            if D <= 0.0:
                raise AssyError(
                    f"Mesafe kısıtı {ka.name}–{kb.name} ('{mate.a.component}' – '{mate.b.component}'): "
                    "D = 0 normlu artıkta türevsiz; COINCIDENT kullanın"
                )
            if ka is _POINT:
                return _distance_point_point(pa, pb, D)
            return _distance_axis_axis(pa, da, pb, db, D)

    elif kind is MateKind.ANGLE:
        if pair <= {_PLANE, _AXIS}:
            return _angle(da, db, D)

    raise _unsupported(mate)


def residual(assembly: Assembly, mate: Mate) -> np.ndarray:
    """Kısıtın artık vektörü (mevcut bileşen T'leriyle). Desteklenmeyen çift → AssyError."""
    r, _ = _terms(assembly, mate)
    return r


def jacobian(assembly: Assembly, mate: Mate, unknowns: list[str]) -> np.ndarray:
    """∂r/∂x, boyut (m, 6·len(unknowns)); unknowns[i] sütunları [Δt, ω]."""
    r, G = _terms(assembly, mate)
    J = np.zeros((len(r), 6 * len(unknowns)))
    for ref, gp, gd in ((mate.a, G["pa"], G["da"]), (mate.b, G["pb"], G["db"])):
        if ref.component not in unknowns:
            continue  # sabit bileşen: sütunu yok
        i = unknowns.index(ref.component)
        T = assembly.component(ref.component).T
        R = T[:3, :3]
        Rp0 = R @ np.array(ref.origin)  # R p0 (dönme kolu)
        d = R @ np.array(ref.direction)
        # δp = Δt − [R p0]× ω,   δd = −[d]× ω
        J[:, 6 * i : 6 * i + 3] += gp
        J[:, 6 * i + 3 : 6 * i + 6] += -gp @ skew(Rp0) - gd @ skew(d)
    return J
