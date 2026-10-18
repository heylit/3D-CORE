"""SPEC 44 testleri için bağımsız geometri ve kinematik referansları.

`cam.multiaxis.machine` / `collision` gövdeleri kullanılmaz; yalnız analitik geometri:
- Doğru parçası – doğru parçası en kısa uzaklık: Ericson, Real-Time Collision Detection, 5.1.9
  (paralel ve yozlaşmış parçalar dahil kapalı form).
- Noktanın yönlendirilmiş kutuya uzaklığı: kutu çerçevesinde her eksende kenetleme (Ericson 5.1.4).
- Doğru parçası – kutu: uzaklık t'de dışbükey → sınırlı Brent araması (scipy) + uç noktalar.
- Kutu – kutu kesişimi: iki dışbükey çokyüzlünün ortak noktası doğrusal programla (scipy linprog);
  SAT'tan bağımsız bir kâhin.
- Halka dönüşümleri: SPEC 44 / machine.py modül docstring'indeki zincir kuralı, dönmeler
  `cam.multiaxis.kinematics.rotation` (SPEC 41, ayrıca test edilmiş) ile.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import linprog, minimize_scalar

# --- uzaklıklar ------------------------------------------------------------------------------------


def seg_seg(p1, q1, p2, q2) -> float:
    """İki doğru parçası arası en kısa uzaklık (Ericson ClosestPtSegmentSegment)."""
    p1, q1, p2, q2 = (np.asarray(v, dtype=float) for v in (p1, q1, p2, q2))
    d1 = q1 - p1
    d2 = q2 - p2
    r = p1 - p2
    a = float(d1 @ d1)
    e = float(d2 @ d2)
    f = float(d2 @ r)
    eps = 1e-300
    if a <= eps and e <= eps:
        return float(np.linalg.norm(p1 - p2))
    if a <= eps:
        s = 0.0
        t = min(max(f / e, 0.0), 1.0)
    else:
        c = float(d1 @ r)
        if e <= eps:
            t = 0.0
            s = min(max(-c / a, 0.0), 1.0)
        else:
            b = float(d1 @ d2)
            den = a * e - b * b
            s = min(max((b * f - c * e) / den, 0.0), 1.0) if den > 0 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t = 0.0
                s = min(max(-c / a, 0.0), 1.0)
            elif t > 1.0:
                t = 1.0
                s = min(max((b - c) / a, 0.0), 1.0)
    return float(np.linalg.norm((p1 + d1 * s) - (p2 + d2 * t)))


def point_box(x, center, half, R) -> float:
    """Noktanın yönlendirilmiş kutuya uzaklığı (içeride 0). R sütunları kutu eksenleri."""
    R = np.asarray(R, dtype=float)
    local = R.T @ (np.asarray(x, dtype=float) - np.asarray(center, dtype=float))
    h = np.asarray(half, dtype=float)
    return float(np.linalg.norm(local - np.clip(local, -h, h)))


def seg_box(p, q, center, half, R) -> float:
    """Doğru parçasının kutuya en kısa uzaklığı: dışbükey f(t) için Brent + uç noktalar."""
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)

    def f(t: float) -> float:
        return point_box(p + t * (q - p), center, half, R)

    ts = np.linspace(0.0, 1.0, 201)
    v = [f(t) for t in ts]
    k = int(np.argmin(v))
    lo, hi = ts[max(k - 1, 0)], ts[min(k + 1, len(ts) - 1)]
    best = min(v)
    if hi > lo:
        res = minimize_scalar(f, bounds=(lo, hi), method="bounded", options={"xatol": 1e-14})
        best = min(best, float(res.fun))
    return best


def boxes_intersect_lp(ca, ha, Ra, cb, hb, Rb) -> bool:
    """İki kutunun (kapalı) ortak noktası var mı: −h ≤ Rᵀ(x − c) ≤ h her iki kutu için, LP fizibilitesi.
    Sınırda kararsızlığı önlemek için testler ayrık / kesişen durumları en az 1e-6 farkla kurar."""
    A_ub = []
    b_ub = []
    for c, h, R in ((ca, ha, Ra), (cb, hb, Rb)):
        R = np.asarray(R, dtype=float)
        c = np.asarray(c, dtype=float)
        h = np.asarray(h, dtype=float)
        for i in range(3):
            n = R[:, i]
            A_ub.append(n)
            b_ub.append(h[i] + n @ c)
            A_ub.append(-n)
            b_ub.append(h[i] - n @ c)
    res = linprog(np.zeros(3), A_ub=np.array(A_ub), b_ub=np.array(b_ub), bounds=[(None, None)] * 3)
    return bool(res.status == 0)


def face_axes_separate(ca, ha, Ra, cb, hb, Rb) -> bool:
    """Yalnız 6 yüz ekseniyle ayırma (kenar–kenar eksenleri olmadan): SAT'ta 9 kenar ekseninin gerekli
    olduğu durumu kurmak için."""
    Ra, Rb = np.asarray(Ra, dtype=float), np.asarray(Rb, dtype=float)
    d = np.asarray(cb, dtype=float) - np.asarray(ca, dtype=float)
    for L in [Ra[:, i] for i in range(3)] + [Rb[:, i] for i in range(3)]:
        ra = sum(ha[i] * abs(Ra[:, i] @ L) for i in range(3))
        rb = sum(hb[i] * abs(Rb[:, i] @ L) for i in range(3))
        if abs(d @ L) > ra + rb:
            return True
    return False


# --- dönmeler ve halka dönüşümleri ----------------------------------------------------------------


def Rx(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def Rz(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def apply(pose, x) -> np.ndarray:
    R, t = pose
    return np.asarray(R, dtype=float) @ np.asarray(x, dtype=float) + np.asarray(t, dtype=float)


def _rot_pose(u, pivot, deg: float):
    from cam.multiaxis.kinematics import rotation

    R = rotation(u, deg)
    c = np.asarray(pivot, dtype=float)
    return R, c - R @ c


def compose(a, b):
    """(a ∘ b)(x) = a(b(x))."""
    Ra, ta = a
    Rb, tb = b
    return Ra @ Rb, Ra @ tb + ta


def ref_poses(kin, carrier: dict[str, str], q) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """SPEC 44 zincir kuralı: masa halkası Trans(−Σ masa doğrusalları) ∘ Rot(t1) ∘ Rot(t2),
    kafa halkası Trans(Σ kafa doğrusalları) ∘ Rot(h1) ∘ Rot(h2); doğrusal halkalar X, Y, Z sırasıyla."""
    q = np.asarray(q, dtype=float)
    rotary = tuple(kin.rotary) if kin is not None else ()
    out = {"taban": (np.eye(3), np.zeros(3))}
    acc = {"masa": np.zeros(3), "kafa": np.zeros(3)}
    for i, ad in enumerate("XYZ"):
        c = carrier[ad]
        e = np.zeros(3)
        e[i] = q[i]
        acc[c] = acc[c] + e
        out[ad] = (np.eye(3), (-acc[c] if c == "masa" else acc[c]).copy())
    son = {"masa": (np.eye(3), -acc["masa"]), "kafa": (np.eye(3), acc["kafa"].copy())}
    for j, a in enumerate(rotary):
        son[a.carrier] = compose(son[a.carrier], _rot_pose(a.u, a.pivot, q[3 + j]))
        out[a.name] = son[a.carrier]
    out["is_parcasi"] = son["masa"]
    out["is_mili"] = son["kafa"]
    return out
