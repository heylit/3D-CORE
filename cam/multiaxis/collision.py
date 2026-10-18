"""
SPEC 44 — Tezgâh gövdeleri arası çarpışma, en az boşluk ve eksen sınırı denetimi, hareket boyunca.

Uzaklıklar (kapsül çiftlerinde işaretli: girişimde negatif):
- kapsül–kapsül: doğru parçaları arası en kısa uzaklık − r_a − r_b,
- kapsül–kutu: min_t uzaklık(x(t), kutu) − r (kutu içindeki nokta için uzaklık 0),
- kutu–kutu: ayırıcı eksen teoremi (15 eksen); kesişimde 0, ayrıksa en büyük eksen boşluğu (alt sınır).
Olay: uzaklık < clearance (kutu–kutuda kutular clearance/2 büyütülerek kesişim; değme kesişim sayılır).

Denetlenen çiftler: kafa zinciri gövdeleri × (masa zinciri + taban) gövdeleri ve masa zinciri × taban
(dönen beşik / fikstür × kolon); `ignore` çiftleri ve (takim | sap) × ham_malzeme hariç (SPEC 43'ün işi).
Kayıtta a kafa (ya da masa × taban'da masa) gövdesi, b öteki.

Örnekleme: n = ⌈(|ΔX, ΔY, ΔZ| + Σ |Δθ_i|·ρ_i) / σ⌉ (Δθ radyan), ilk temas ikiye bölmeyle 1e-6 mm.
Adım indeksi k SPEC 05 kuralıyla: nokta 0 ilk yolun başlangıcı, her hareket bir adım, yollar arasında
uçlar farklıysa bağlantı adımı; yay kirişleri hareketin k'sini taşır, t ∈ [0, 1] hareketin içinde.
Eklem yolu: başlangıç noktasının ekseni ilk hareketin ekseni (SPEC 41 `to_machine`); her nokta 41 `inverse`
ile (önceki açılardan devam); sınır içinde çözüm yoksa sınırsız çözüm alınır ve `eksen_siniri` yazılır.
L verilmezse her yolun `tool.gauge_length`'i (yoksa CamError).
Kayıt bir ihlalin başlangıcıdır: (kind, k, a, b) başına hareket içinde ilk giriş anı; önceki hareketten
süren temas / sınır aşımı yeni kayıt açmaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.model import (
    ARCS,
    CamError,
    Kinematics,
    Move,
    Plane,
    RotaryAxis,
    Setup,
    Toolpath,
)
from cam.multiaxis.indexed import _yay_noktalari
from cam.multiaxis.kinematics import inverse
from cam.multiaxis.machine import (
    Body,
    Box,
    Capsule,
    MachineModel,
    link_poses,
    setup_bodies,
    tool_bodies,
)

EVENT_KINDS = ("tezgah_carpma", "eksen_siniri")
TEMAS_TOL = 1e-9  # [mm] kutu–kutu değme toleransı
BOLME_TOL = 1e-7  # [mm] ikiye bölmenin durduğu yer değiştirme
SINIR_TOL = 1e-9  # eksen sınırı toleransı [mm | derece]
ALTIN = (math.sqrt(5.0) - 1.0) / 2.0
SQRT3 = math.sqrt(3.0)


# ---------------------------------------------------------------- uzaklıklar (iç: dizilerle)


def _kenet(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _d_cc(p1: np.ndarray, q1: np.ndarray, p2: np.ndarray, q2: np.ndarray) -> float:
    """İki doğru parçası arası en kısa uzaklık (Ericson, kapalı form; paralel ve nokta durumları dahil)."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = float(d1 @ d1), float(d2 @ d2), float(d2 @ r)
    if a <= 0.0 and e <= 0.0:
        return float(np.linalg.norm(r))
    if a <= 0.0:
        s, t = 0.0, _kenet(f / e)
    else:
        c = float(d1 @ r)
        if e <= 0.0:
            s, t = _kenet(-c / a), 0.0
        else:
            b = float(d1 @ d2)
            den = a * e - b * b
            s = _kenet((b * f - c * e) / den) if den > 1e-14 * a * e else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                s, t = _kenet(-c / a), 0.0
            elif t > 1.0:
                s, t = _kenet((b - c) / a), 1.0
    return float(np.linalg.norm(p1 + s * d1 - (p2 + t * d2)))


def _d_cb(
    p: np.ndarray, q: np.ndarray, c: np.ndarray, R: np.ndarray, h: np.ndarray, yeter: float = math.inf
) -> float:
    """p–q parçasının kutuya (c, R, h) en kısa uzaklığı.

    f(t) dışbükey; altın oran araması 1e-9 mm'ye kadar. f, t'de |q − p| Lipschitz olduğundan
    min f ≥ min(f1, f2) − (hi − lo)·|q − p|; bu alt sınır `yeter`'i aşınca erken dönülür (alt sınırla).
    """
    pl = (p - c) @ R
    dl = (q - p) @ R
    x0, x1, x2 = (float(v) for v in pl)
    d0, d1, d2 = (float(v) for v in dl)
    h0, h1, h2 = (float(v) for v in h)

    def f(t: float) -> float:
        a = max(abs(x0 + t * d0) - h0, 0.0)
        b = max(abs(x1 + t * d1) - h1, 0.0)
        g = max(abs(x2 + t * d2) - h2, 0.0)
        return math.sqrt(a * a + b * b + g * g)

    boy = math.sqrt(d0 * d0 + d1 * d1 + d2 * d2)
    en = min(f(0.0), f(1.0))
    if boy <= 0.0:
        return en
    lo, hi = 0.0, 1.0
    t1, t2 = hi - ALTIN * (hi - lo), lo + ALTIN * (hi - lo)
    f1, f2 = f(t1), f(t2)
    for _ in range(300):
        if (hi - lo) * boy <= 1e-11:
            break
        alt = min(en, f1, f2) - (hi - lo) * boy
        if alt > yeter:
            return alt
        if f1 <= f2:
            hi, t2, f2 = t2, t1, f1
            t1 = hi - ALTIN * (hi - lo)
            f1 = f(t1)
        else:
            lo, t1, f1 = t1, t2, f2
            t2 = lo + ALTIN * (hi - lo)
            f2 = f(t2)
    return min(en, f1, f2, f((lo + hi) / 2))


def _sat(
    c1: np.ndarray, R1: np.ndarray, h1: np.ndarray, c2: np.ndarray, R2: np.ndarray, h2: np.ndarray
) -> float:
    """15 eksenli SAT: eksenlerdeki en büyük boşluk (> 0 → ayrık; gerçek uzaklığın alt sınırı)."""
    T = c2 - c1
    A, B = R1.T[:, None, :], R2.T[None, :, :]  # satırlar kutuların eksenleri
    X = np.stack(
        [
            A[..., 1] * B[..., 2] - A[..., 2] * B[..., 1],
            A[..., 2] * B[..., 0] - A[..., 0] * B[..., 2],
            A[..., 0] * B[..., 1] - A[..., 1] * B[..., 0],
        ],
        axis=-1,
    ).reshape(9, 3)
    n = np.sqrt(np.einsum("ij,ij->i", X, X))
    sec = n > 1e-9  # paralel kenar çiftlerinin çarpımı eksen değil
    L = np.vstack([R1.T, R2.T, X[sec] / n[sec, None]])
    ra = np.abs(L @ R1) @ h1
    rb = np.abs(L @ R2) @ h2
    return float(np.max(np.abs(L @ T) - ra - rb))


def _kutu(b: Box) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return np.array(b.center), b.matrix, np.array(b.half)


# ---------------------------------------------------------------- uzaklıklar (arayüz)


def dist_capsule_capsule(a: Capsule, b: Capsule) -> float:
    """İki kapsül arası işaretli uzaklık [mm]."""
    d = _d_cc(np.array(a.p), np.array(a.q), np.array(b.p), np.array(b.q))
    return d - a.r - b.r


def dist_capsule_box(c: Capsule, b: Box) -> float:
    """Kapsül–kutu işaretli uzaklık [mm]."""
    return _d_cb(np.array(c.p), np.array(c.q), *_kutu(b)) - c.r


def boxes_overlap(a: Box, b: Box, margin: float = 0.0) -> bool:
    """Kutular (her biri margin/2 büyütülmüş) kesişiyor mu (SAT, 15 eksen)."""
    if not (math.isfinite(margin) and margin >= 0):
        raise CamError(f"boxes_overlap: margin negatif olmayan sonlu sayı olmalı ({margin})")
    ca, Ra, ha = _kutu(a)
    cb, Rb, hb = _kutu(b)
    return _sat(ca, Ra, ha + margin / 2, cb, Rb, hb + margin / 2) <= TEMAS_TOL


@dataclass
class MachineEvent:
    """kind: "tezgah_carpma" (a, b gövde adları) veya "eksen_siniri" (a eksen adı, b = "")."""

    kind: str
    k: int
    t: float
    a: str
    b: str
    distance: float
    detail: str


# ---------------------------------------------------------------- program → adımlar


@dataclass
class _Adim:
    k: int
    op: int
    p0: np.ndarray
    p1: np.ndarray
    a0: np.ndarray
    a1: np.ndarray
    u0: float  # kiriş: hareket içindeki t aralığı
    u1: float


def _eksen(tp: Toolpath, m: Move | None) -> np.ndarray:
    a = np.array((0.0, 0.0, 1.0) if m is None or m.axis is None else m.axis)
    return a if tp.frame is None else tp.frame.to_world_vec(a)


def _nokta(tp: Toolpath, p) -> np.ndarray:
    p = np.array(p, dtype=float)
    return p if tp.frame is None else tp.frame.to_world(p)


def _adimlar(ops: list[Toolpath], arc_tol: float) -> list[_Adim]:
    """SPEC 05 adım indeksi: her hareket bir k, yollar arası uçlar farklıysa bağlantı G0'ı."""
    out: list[_Adim] = []
    k = 0
    pos: np.ndarray | None = None
    ax: np.ndarray | None = None
    for i, tp in enumerate(ops):
        bas = _nokta(tp, tp.start)
        a_bas = _eksen(tp, tp.moves[0] if tp.moves else None)
        if pos is None:
            pos, ax = bas, a_bas
        elif not np.array_equal(pos, bas):
            k += 1
            out.append(_Adim(k, i, pos, bas, ax, a_bas, 0.0, 1.0))
            pos, ax = bas, a_bas
        p_yerel = tp.start
        for m in tp.moves:
            k += 1
            a = _eksen(tp, m)
            if m.type in ARCS:
                if tp.plane is not Plane.XY:
                    raise CamError(f"Takım yolu '{tp.name}': yaylar yalnız XY (G17) düzleminde")
                kiris = [_nokta(tp, c) for c in _yay_noktalari(np.array(p_yerel, dtype=float), m, arc_tol)]
            else:
                kiris = [_nokta(tp, m.end)]
            nk = len(kiris)
            for j, p in enumerate(kiris):
                aj = ax + (a - ax) * (j + 1) / nk if nk > 1 else a
                aj = aj / np.linalg.norm(aj)
                out.append(_Adim(k, i, pos, p, ax, aj, j / nk, (j + 1) / nk))
                pos, ax = p, aj
            p_yerel = m.end
    return out


def _slerp(a0: np.ndarray, a1: np.ndarray, t: float) -> np.ndarray:
    c = float(np.clip(a0 @ a1, -1.0, 1.0))
    w = math.acos(c)
    if w < 1e-12:
        return a0
    if math.pi - w < 1e-9:
        raise CamError(f"Tezgâh çarpışması: zıt takım eksenleri arasında ara yön belirsiz ({a0}, {a1})")
    s = math.sin(w)
    a = (math.sin((1 - t) * w) * a0 + math.sin(t * w) * a1) / s
    return a / np.linalg.norm(a)


# ---------------------------------------------------------------- yol başına gövde kümesi


@dataclass
class _Govde:
    name: str
    link: str
    zincir: str
    kapsul: bool
    v: tuple  # kapsül: (p, q, r); kutu: (c, R, h) — sıfır konumunda
    merkez: np.ndarray  # sınır küresi ve kutusu merkezi (sıfır konumunda)
    yaricap: float
    yari: np.ndarray  # eksenlere hizalı sınır kutusunun yarı boyları (sıfır konumunda)


def _govde(model: MachineModel, b: Body) -> _Govde:
    s = b.shape
    if isinstance(s, Capsule):
        p, q = np.array(s.p), np.array(s.q)
        v = (p, q, s.r)
        m, r = (p + q) / 2, float(np.linalg.norm(q - p)) / 2 + s.r
        e = np.abs(q - p) / 2 + s.r
        return _Govde(b.name, b.link, model.chain(b.link), True, v, m, r, e)
    c, R, h = _kutu(s)
    e = np.abs(R) @ h
    return _Govde(b.name, b.link, model.chain(b.link), False, (c, R, h), c, float(np.linalg.norm(h)), e)


def _noktalar(g: _Govde) -> list[tuple[np.ndarray, float]]:
    """Gövdeyi kapsayan noktalar ve ek yarıçap: kutu köşeleri, kapsül uçları (+ r)."""
    if g.kapsul:
        p, q, r = g.v
        return [(p, r), (q, r)]
    c, R, h = g.v
    return [(c + R @ ((2.0 * np.array(s) - 1.0) * h), 0.0) for s in np.ndindex(2, 2, 2)]


class _Kume:
    """Bir yolun gövdeleri, denetlenen çiftler ve döner eksenlerin ρ_i değerleri."""

    def __init__(self, model: MachineModel, setup: Setup, tool, L: float) -> None:
        kin = model.kinematics
        govdeler = list(model.bodies) + setup_bodies(setup) + tool_bodies(kin, tool, L)
        self.G = [_govde(model, b) for b in govdeler]
        hari = {frozenset(c) for c in model.ignore}
        hari |= {frozenset((t, "ham_malzeme")) for t in ("takim", "sap")}
        cift = []
        for i, a in enumerate(self.G):
            for j, b in enumerate(self.G):
                ok = (a.zincir == "kafa" and b.zincir in ("masa", "taban")) or (
                    a.zincir == "masa" and b.zincir == "taban"
                )
                if ok and frozenset((a.name, b.name)) not in hari:
                    cift.append((i, j))
        self.I = np.array([c[0] for c in cift], dtype=int)
        self.J = np.array([c[1] for c in cift], dtype=int)
        self.C0 = np.array([g.merkez for g in self.G]).reshape(-1, 3)
        self.Rs = np.array([g.yaricap for g in self.G])
        self.E0 = np.array([g.yari for g in self.G]).reshape(-1, 3)
        self.links = sorted({g.link for g in self.G})
        self.by_link = {lk: np.array([i for i, g in enumerate(self.G) if g.link == lk]) for lk in self.links}
        self.rho = self._rho(kin)

    def _rho(self, kin: Kinematics) -> list[float]:
        """ρ_i: taşınan gövde noktalarının pivota uzaklığının üst sınırı (alt eksen dönmeleri dahil)."""
        rho = []
        for i, a in enumerate(kin.rotary):
            zincir = [j for j, b in enumerate(kin.rotary) if b.carrier == a.carrier]
            alt = zincir[zincir.index(i) :]
            halkalar = {kin.rotary[j].name for j in alt} | {
                "is_mili" if a.carrier == "kafa" else "is_parcasi"
            }
            ci = np.array(a.pivot)
            en = 0.0
            for g in self.G:
                if g.link not in halkalar:
                    continue
                for x, r in _noktalar(g):
                    en = max(en, float(np.linalg.norm(x - ci)) + r)
                    for j in alt[1:]:
                        cj = np.array(kin.rotary[j].pivot)
                        en = max(en, float(np.linalg.norm(cj - ci) + np.linalg.norm(x - cj)) + r)
            rho.append(en)
        return rho

    def sinirlar(self, P: dict) -> tuple[np.ndarray, np.ndarray]:
        """Şimdiki konumda sınır küresi / kutusu merkezleri ve kutu yarı boyları (|R|·e, güvenli taraf)."""
        C = np.empty_like(self.C0)
        E = np.empty_like(self.E0)
        for lk, idx in self.by_link.items():
            R, t = P[lk]
            C[idx] = self.C0[idx] @ R.T + t
            E[idx] = self.E0[idx] @ np.abs(R).T
        return C, E

    def dunya(self, i: int, P: dict) -> tuple:
        g = self.G[i]
        R, t = P[g.link]
        if g.kapsul:
            p, q, r = g.v
            return (R @ p + t, R @ q + t, r)
        c, Rb, h = g.v
        return (R @ c + t, R @ Rb, h)


def _cift(ga: _Govde, va: tuple, gb: _Govde, vb: tuple, clearance: float) -> tuple[bool, float, float]:
    """(ihlal mi, atlama için boşluk alt sınırı − clearance, raporlanan uzaklık)."""
    if ga.kapsul and gb.kapsul:
        d = _d_cc(va[0], va[1], vb[0], vb[1]) - va[2] - vb[2]
    elif ga.kapsul:
        d = _d_cb(va[0], va[1], *vb, yeter=clearance + va[2] + 1.0) - va[2]
    elif gb.kapsul:
        d = _d_cb(vb[0], vb[1], *va, yeter=clearance + vb[2] + 1.0) - vb[2]
    else:
        g = _sat(va[0], va[1], va[2] + clearance / 2, vb[0], vb[1], vb[2] + clearance / 2)
        return g <= TEMAS_TOL, g, max(0.0, _sat(*va, *vb))
    return d < clearance, d - clearance, d


# ---------------------------------------------------------------- denetim


def _sinirlar(model: MachineModel) -> list[tuple[str, float, float] | None]:
    pr = model.profile
    out: list[tuple[str, float, float] | None] = []
    for ad, lim in (("X", pr.x), ("Y", pr.y), ("Z", pr.z)):
        out.append(None if lim is None else (ad, float(lim.min), float(lim.max)))
    for a in model.kinematics.rotary:
        out.append(None if a.min is None else (a.name, float(a.min), float(a.max)))
    return out


def _disarida(v: float, lo: float, hi: float) -> bool:
    return v < lo - SINIR_TOL or v > hi + SINIR_TOL


def check(
    model: MachineModel,
    setup: Setup,
    ops: list[Toolpath],
    L: float | None = None,
    tcp: bool = True,
    sigma: float = 1.0,
    clearance: float = 0.0,
    prev: tuple[float, ...] | None = None,
) -> list[MachineEvent]:
    """Program boyunca tezgâh çarpışması ve eksen sınırı olayları; (kind, k, a, b) başına ilk t."""
    if not isinstance(model, MachineModel):
        raise CamError(f"check: model MachineModel olmalı ({type(model).__name__})")
    if not isinstance(setup, Setup):
        raise CamError(f"check: setup Setup olmalı ({type(setup).__name__})")
    if not (math.isfinite(sigma) and sigma > 0):
        raise CamError(f"check: sigma pozitif olmalı ({sigma})")
    if not (math.isfinite(clearance) and clearance >= 0):
        raise CamError(f"check: clearance negatif olmayan sonlu sayı olmalı ({clearance})")
    if L is not None and not (math.isfinite(L) and L > 0):
        raise CamError(f"check: L pozitif olmalı ({L})")
    return _Denetim(model, setup, list(ops), L, bool(tcp), sigma, clearance, prev).calistir()


class _Denetim:
    def __init__(self, model, setup, ops, L, tcp, sigma, clearance, prev) -> None:
        self.model, self.setup, self.ops = model, setup, ops
        self.L_arg, self.tcp, self.sigma, self.clr = L, tcp, sigma, clearance
        kin = model.kinematics
        self.kin = kin
        serbest = tuple(RotaryAxis(a.name, a.carrier, a.u, a.pivot) for a in kin.rotary)
        self.kin_serbest = Kinematics(rotary=serbest, spindle=kin.spindle, gauge=kin.gauge)
        self.aci = None if prev is None else tuple(float(v) for v in prev)
        self.sinir = _sinirlar(model)
        self.olaylar: list[MachineEvent] = []
        self.temas: dict[tuple[str, str], bool] = {}
        self.disari: dict[str, bool] = {}
        self.kayitli: set[tuple[str, int, str, str]] = set()

    # -- yardımcılar

    def _L(self, tp: Toolpath) -> float:
        if self.L_arg is not None:
            return float(self.L_arg)
        L = getattr(tp.tool, "gauge_length", None)
        if L is None:
            raise CamError(f"check: takım boyu L verilmedi ve '{tp.name}' takımında tutucu + taşma yok")
        return float(L)

    def _ik(self, p, a, L: float, prev) -> np.ndarray:
        try:
            return inverse(self.kin, p, a, L, self.setup.wcs, prev)
        except CamError:
            return inverse(self.kin_serbest, p, a, L, self.setup.wcs, prev)

    def _q(self, ad: _Adim, t: float, L: float, q0: np.ndarray, q1: np.ndarray, prev) -> np.ndarray:
        if not self.tcp:
            return q0 + t * (q1 - q0)
        p = ad.p0 + t * (ad.p1 - ad.p0)
        return self._ik(p, _slerp(ad.a0, ad.a1, t), L, prev)

    def _yer(self, dq: np.ndarray, rho: list[float]) -> float:
        """Eklem farkı dq için gövde noktalarının yer değiştirme üst sınırı [mm]."""
        return float(
            np.linalg.norm(dq[:3]) + sum(abs(math.radians(v)) * r for v, r in zip(dq[3:], rho, strict=True))
        )

    def _ornekle(self, ad: _Adim, L: float, rho: list[float]) -> np.ndarray:
        q0 = self._ik(ad.p0, ad.a0, L, self.aci)
        q1 = self._ik(ad.p1, ad.a1, L, tuple(q0[3:]))
        n = max(1, math.ceil(self._yer(q1 - q0, rho) / self.sigma - 1e-12))
        if not self.tcp:
            t = np.linspace(0.0, 1.0, n + 1)
            return q0 + t[:, None] * (q1 - q0)
        for _ in range(2):
            Q = [q0]
            for i in range(1, n + 1):
                Q.append(self._q(ad, i / n, L, q0, q1, tuple(Q[-1][3:])))
            Q = np.array(Q)
            toplam = sum(self._yer(Q[i] - Q[i - 1], rho) for i in range(1, n + 1))
            n2 = math.ceil(toplam / self.sigma - 1e-12)
            if n2 <= n:
                break
            n = n2
        return Q

    def _t(self, ad: _Adim, t: float) -> float:
        return ad.u0 + t * (ad.u1 - ad.u0)

    # -- eksen sınırları

    def _sinir_adim(self, ad: _Adim, Q: np.ndarray, L: float, rho: list[float]) -> None:
        n = len(Q) - 1
        for j, s in enumerate(self.sinir):
            if s is None:
                continue
            isim, lo, hi = s
            V = Q[:, j]
            dis = (V < lo - SINIR_TOL) | (V > hi + SINIR_TOL)
            once = self.disari.get(isim, False)
            for i in range(n + 1):
                if dis[i] and not (once if i == 0 else dis[i - 1]):
                    break
            else:
                self.disari[isim] = bool(dis[n])
                continue
            self.disari[isim] = bool(dis[n])
            key = ("eksen_siniri", ad.k, isim, "")
            if key in self.kayitli:
                continue
            t = 0.0 if i == 0 else self._sinir_t(ad, Q, i, j, lo, hi, L, rho)
            asim = np.maximum(lo - V, V - hi)
            m = int(np.argmax(asim))
            yon = "alt" if V[m] < lo else "üst"
            lim = lo if V[m] < lo else hi
            self.kayitli.add(key)
            self.olaylar.append(
                MachineEvent(
                    "eksen_siniri",
                    ad.k,
                    self._t(ad, t),
                    isim,
                    "",
                    float(asim[m]),
                    f"{isim} = {V[m]:.6g}, {yon} sınır {lim:.6g}",
                )
            )

    def _sinir_t(self, ad, Q, i, j, lo, hi, L, rho) -> float:
        n = len(Q) - 1
        v0, v1 = Q[0, j], Q[n, j]
        if not self.tcp:
            lim = lo if Q[i, j] < lo else hi
            return float(min(1.0, max(0.0, (lim - v0) / (v1 - v0))))
        t_lo, t_hi = (i - 1) / n, i / n
        prev = tuple(Q[i - 1][3:])
        D = self._yer(Q[i] - Q[i - 1], rho) * n
        q0, q1 = Q[0], Q[n]
        while (t_hi - t_lo) * D > BOLME_TOL and t_hi - t_lo > 1e-15:
            tm = (t_lo + t_hi) / 2
            v = self._q(ad, tm, L, q0, q1, prev)[j]
            if _disarida(v, lo, hi):
                t_hi = tm
            else:
                t_lo = tm
        return t_hi

    # -- çarpışma

    def _degerlendir(self, K: _Kume, q: np.ndarray) -> tuple[dict[int, tuple[bool, float, float]], float]:
        """Yakın çiftlerin (ihlal, boşluk, uzaklık) sonuçları ve uzak çiftlerin en küçük boşluğu."""
        P = link_poses(self.model, q)
        C, E = K.sinirlar(P)
        dC = C[K.I] - C[K.J]
        lb_kure = np.linalg.norm(dC, axis=1) - K.Rs[K.I] - K.Rs[K.J]
        lb_kutu = np.max(np.abs(dC) - E[K.I] - E[K.J], axis=1)
        lb = np.maximum(lb_kure, lb_kutu)
        esik = self.clr * SQRT3 + TEMAS_TOL
        yakin = np.nonzero(lb <= esik)[0]
        uzak = lb > esik
        g_uzak = float(np.min(lb[uzak]) - esik) if np.any(uzak) else math.inf
        sonuc = {}
        for c in yakin:
            i, j = int(K.I[c]), int(K.J[c])
            sonuc[int(c)] = _cift(K.G[i], K.dunya(i, P), K.G[j], K.dunya(j, P), self.clr)
        return sonuc, g_uzak

    def _cift_t(self, K: _Kume, c: int, q: np.ndarray) -> tuple[bool, float]:
        P = link_poses(self.model, q)
        i, j = int(K.I[c]), int(K.J[c])
        ih, _, d = _cift(K.G[i], K.dunya(i, P), K.G[j], K.dunya(j, P), self.clr)
        return ih, d

    def _carpisma_adim(self, ad: _Adim, Q: np.ndarray, K: _Kume, L: float, ilk: bool) -> None:
        n = len(Q) - 1
        adlar = [(K.G[int(i)].name, K.G[int(j)].name) for i, j in zip(K.I, K.J, strict=True)]
        dq = [self._yer(Q[i] - Q[i - 1], K.rho) for i in range(1, n + 1)]
        delta = 2.0 * max(dq, default=0.0)
        i = 0 if ilk else 1
        while i <= n:
            sonuc, g = self._degerlendir(K, Q[i])
            for c, ad_c in enumerate(adlar):
                ih = sonuc[c][0] if c in sonuc else False
                if ih and not self.temas.get(ad_c, False):
                    key = ("tezgah_carpma", ad.k, *ad_c)
                    if key not in self.kayitli:
                        self.kayitli.add(key)
                        t, d = (0.0, sonuc[c][2]) if i == 0 else self._carpisma_t(ad, Q, K, c, i, L, dq)
                        self.olaylar.append(
                            MachineEvent(
                                "tezgah_carpma",
                                ad.k,
                                self._t(ad, t),
                                ad_c[0],
                                ad_c[1],
                                float(d),
                                f"{ad_c[0]} × {ad_c[1]}: uzaklık {d:.6g} mm < boşluk {self.clr:.6g} mm",
                            )
                        )
                self.temas[ad_c] = ih
            if i == n:
                break
            serbest = [r[1] for c, r in sonuc.items() if not r[0]]
            g = min([g, *serbest])
            if any(r[0] for r in sonuc.values()) or delta <= 0.0:
                adim = 1 if delta > 0.0 else n - i
            else:
                adim = max(1, int(g / delta))
            i = min(n, i + adim)

    def _carpisma_t(self, ad, Q, K, c, i, L, dq) -> tuple[float, float]:
        n = len(Q) - 1
        t_lo, t_hi = (i - 1) / n, i / n
        D = dq[i - 1] * n
        prev = tuple(Q[i - 1][3:])
        q0, q1 = Q[0], Q[n]
        _, d = self._cift_t(K, c, Q[i])
        while (t_hi - t_lo) * D > BOLME_TOL and t_hi - t_lo > 1e-15:
            tm = (t_lo + t_hi) / 2
            ih, dm = self._cift_t(K, c, self._q(ad, tm, L, q0, q1, prev))
            if ih:
                t_hi, d = tm, dm
            else:
                t_lo = tm
        return t_hi, d

    # -- akış

    def calistir(self) -> list[MachineEvent]:
        adimlar = _adimlar(self.ops, 1e-3)
        kumeler: dict[int, _Kume] = {}
        Ls: dict[int, float] = {}
        onceki_op = None
        for ad in adimlar:
            if ad.op not in kumeler:
                tp = self.ops[ad.op]
                Ls[ad.op] = self._L(tp)
                kumeler[ad.op] = _Kume(self.model, self.setup, tp.tool, Ls[ad.op])
            K, L = kumeler[ad.op], Ls[ad.op]
            Q = self._ornekle(ad, L, K.rho)
            self._sinir_adim(ad, Q, L, K.rho)
            self._carpisma_adim(ad, Q, K, L, ilk=ad.op != onceki_op)
            onceki_op = ad.op
            self.aci = tuple(float(v) for v in Q[-1][3:])
        self.olaylar.sort(key=lambda e: (e.k, e.t, e.kind, e.a, e.b))
        return self.olaylar
